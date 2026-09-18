import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_admin
from ..database import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _user_to_admin_out(db: Session, u: models.User) -> schemas.AdminUserOut:
    total_generated, total_cost = crud.total_generated_and_cost(db, u.id)
    return schemas.AdminUserOut(
        id=u.id,
        username=u.username,
        is_admin=u.is_admin,
        is_approved=u.is_approved,
        daily_quota=u.daily_quota,
        cost_per_image=u.cost_per_image,
        used_today=crud.used_today(db, u.id),
        total_generated=total_generated,
        total_cost=total_cost,
        created_at=u.created_at,
    )


@router.get("/users", response_model=List[schemas.AdminUserOut])
def list_users(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.id).all()
    return [_user_to_admin_out(db, u) for u in users]


@router.put("/users/{user_id}", response_model=schemas.AdminUserOut)
def update_user(
    user_id: int,
    payload: schemas.AdminUserUpdateIn,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    for k, v in payload.dict(exclude_unset=True).items():
        if v is not None:
            setattr(u, k, v)
    db.commit()
    db.refresh(u)
    return _user_to_admin_out(db, u)


@router.post("/users/{user_id}/approve", response_model=schemas.AdminUserOut)
def approve_user(user_id: int, admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    u.is_approved = True
    db.commit()
    db.refresh(u)
    return _user_to_admin_out(db, u)


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录的账号")
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(u)
    db.commit()
    return {"ok": True}


@router.get("/templates", response_model=List[schemas.TemplateOut])
def all_templates(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    from .templates import _to_out  # avoid circular import at module load time

    templates = db.query(models.Template).order_by(models.Template.owner_id.is_(None).desc(), models.Template.id).all()
    return [_to_out(t, admin) for t in templates]


@router.get("/config", response_model=schemas.AdminConfigOut)
def get_config(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    cfg = crud.get_or_create_global_config(db)
    return schemas.AdminConfigOut(
        default_cost_per_image=cfg.default_cost_per_image,
        default_daily_quota=cfg.default_daily_quota,
        remote_relay_base_url=cfg.remote_relay_base_url or "",
        remote_relay_api_key=cfg.remote_relay_api_key or "",
    )


@router.put("/config", response_model=schemas.AdminConfigOut)
def update_config(
    payload: schemas.AdminConfigUpdateIn,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    cfg = crud.get_or_create_global_config(db)
    for k, v in payload.dict(exclude_unset=True).items():
        if v is not None:
            setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    return schemas.AdminConfigOut(
        default_cost_per_image=cfg.default_cost_per_image,
        default_daily_quota=cfg.default_daily_quota,
        remote_relay_base_url=cfg.remote_relay_base_url or "",
        remote_relay_api_key=cfg.remote_relay_api_key or "",
    )


@router.get("/stats", response_model=schemas.AdminStatsOut)
def stats(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    per_user = [_user_to_admin_out(db, u) for u in users]

    total_generations = sum(u.total_generated for u in per_user)
    total_cost = sum(u.total_cost for u in per_user)

    start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_row = (
        db.query(func.count(models.GenerationJob.id), func.coalesce(func.sum(models.GenerationJob.cost), 0.0))
        .filter(models.GenerationJob.created_at >= start, models.GenerationJob.status == "success")
        .first()
    )

    return schemas.AdminStatsOut(
        total_users=len(users),
        total_generations=total_generations,
        total_cost=total_cost,
        today_generations=int(today_row[0] or 0),
        today_cost=float(today_row[1] or 0.0),
        per_user=per_user,
    )
