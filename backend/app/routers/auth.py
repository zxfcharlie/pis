from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import create_access_token, get_current_user, hash_password, verify_password
from ..database import get_db
from ..models import gen_relay_key

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=schemas.RegisterOut)
def register(payload: schemas.RegisterIn, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    is_first_user = db.query(models.User).count() == 0
    cfg = crud.get_or_create_global_config(db)

    user = models.User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        is_admin=is_first_user,
        is_approved=is_first_user,  # first account (admin) is auto-approved
        daily_quota=cfg.default_daily_quota,
        cost_per_image=cfg.default_cost_per_image,
        relay_key=gen_relay_key(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if is_first_user:
        token = create_access_token(user.username)
        return schemas.RegisterOut(status="active", message="注册成功，已自动成为管理员", access_token=token)

    return schemas.RegisterOut(
        status="pending",
        message="注册成功，请等待管理员审核通过后再登录",
        access_token=None,
    )


@router.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_approved:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号正在等待管理员审核，请稍后再试")
    token = create_access_token(user.username)
    return schemas.TokenOut(access_token=token)


@router.get("/me", response_model=schemas.MeOut)
def me(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return schemas.MeOut(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        daily_quota=user.daily_quota,
        cost_per_image=user.cost_per_image,
        used_today=crud.used_today(db, user.id),
        relay_key=user.relay_key,
    )


@router.post("/relay-key/regenerate", response_model=schemas.MeOut)
def regenerate_relay_key(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.relay_key = gen_relay_key()
    db.commit()
    db.refresh(user)
    return schemas.MeOut(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        daily_quota=user.daily_quota,
        cost_per_image=user.cost_per_image,
        used_today=crud.used_today(db, user.id),
        relay_key=user.relay_key,
    )
