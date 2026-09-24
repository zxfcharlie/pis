import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.get("/templates", response_model=List[schemas.AdminTemplateOut])
def all_templates(
    season: Optional[List[str]] = Query(None),
    product: Optional[List[str]] = Query(None),
    owner: Optional[str] = Query(None),  # "system" | "<username>" | None (=all)
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from .templates import _to_out  # avoid circular import at module load time

    q = db.query(models.Template)
    if season:
        q = q.filter(models.Template.season.in_(season))
    if product:
        q = q.filter(models.Template.product.in_(product))
    templates = q.order_by(models.Template.owner_id.is_(None).desc(), models.Template.season, models.Template.product, models.Template.id).all()

    if owner:
        if owner == "system":
            templates = [t for t in templates if t.is_system]
        else:
            templates = [t for t in templates if not t.is_system and t.owner and t.owner.username == owner]

    since_7d = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    since_30d = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    usage_7d = crud.template_usage_counts(db, since_7d)
    usage_30d = crud.template_usage_counts(db, since_30d)

    out = []
    for t in templates:
        base = _to_out(t, admin)
        out.append(
            schemas.AdminTemplateOut(
                **base.dict(),
                owner_username=(t.owner.username if t.owner else None),
                usage_7d=usage_7d.get(t.id, 0),
                usage_30d=usage_30d.get(t.id, 0),
            )
        )
    return out


@router.get("/remix-templates", response_model=List[schemas.RemixTemplateOut])
def all_remix_templates(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    from .remix_templates import _to_out as _remix_to_out

    templates = (
        db.query(models.RemixTemplate)
        .order_by(models.RemixTemplate.owner_id.is_(None).desc(), models.RemixTemplate.product, models.RemixTemplate.id)
        .all()
    )
    return [_remix_to_out(t, admin) for t in templates]


# ---------- Product-based permissions ----------

@router.get("/products")
def list_all_products(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """All distinct product values across both template kinds, for building
    the permission-assignment checkbox list in the admin panel."""
    a = {p for (p,) in db.query(models.Template.product).all() if p}
    b = {p for (p,) in db.query(models.RemixTemplate.product).all() if p}
    return {"products": sorted(a | b)}


@router.get("/users/{user_id}/product-access", response_model=schemas.UserProductAccessOut)
def get_user_product_access(user_id: int, admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    rows = db.query(models.UserProductAccess.product).filter(models.UserProductAccess.user_id == user_id).all()
    return schemas.UserProductAccessOut(user_id=user_id, products=sorted(p for (p,) in rows))


@router.put("/users/{user_id}/product-access", response_model=schemas.UserProductAccessOut)
def set_user_product_access(
    user_id: int,
    payload: schemas.UserProductAccessSetIn,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    crud.set_user_product_access(db, user_id, payload.products)
    return schemas.UserProductAccessOut(user_id=user_id, products=sorted(set(payload.products)))


@router.get("/config", response_model=schemas.AdminConfigOut)
def get_config(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    cfg = crud.get_or_create_global_config(db)
    return schemas.AdminConfigOut(
        default_cost_per_image=cfg.default_cost_per_image,
        default_daily_quota=cfg.default_daily_quota,
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
    )


# ---------- Relay providers: add/edit/switch which upstream API is active ----------

@router.get("/providers", response_model=List[schemas.RelayProviderOut])
def list_providers(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(models.RelayProvider).order_by(models.RelayProvider.id).all()


@router.post("/providers", response_model=schemas.RelayProviderOut)
def create_provider(
    payload: schemas.RelayProviderCreateIn,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if payload.kind not in ("sync_edit", "toapis_async"):
        raise HTTPException(status_code=400, detail="未知的供应商类型")
    p = models.RelayProvider(**payload.dict())
    if db.query(models.RelayProvider).count() == 0:
        p.is_active = True  # first provider ever added is activated automatically
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.put("/providers/{provider_id}", response_model=schemas.RelayProviderOut)
def update_provider(
    provider_id: int,
    payload: schemas.RelayProviderUpdateIn,
    admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    p = db.query(models.RelayProvider).filter(models.RelayProvider.id == provider_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="供应商不存在")
    data = payload.dict(exclude_unset=True)
    if data.get("kind") and data["kind"] not in ("sync_edit", "toapis_async"):
        raise HTTPException(status_code=400, detail="未知的供应商类型")
    for k, v in data.items():
        if v is not None:
            setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.post("/providers/{provider_id}/activate", response_model=schemas.RelayProviderOut)
def activate_provider(
    provider_id: int, admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    p = db.query(models.RelayProvider).filter(models.RelayProvider.id == provider_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="供应商不存在")
    db.query(models.RelayProvider).update({models.RelayProvider.is_active: False}, synchronize_session=False)
    p.is_active = True
    db.commit()
    db.refresh(p)
    return p


@router.delete("/providers/{provider_id}")
def delete_provider(
    provider_id: int, admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    p = db.query(models.RelayProvider).filter(models.RelayProvider.id == provider_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="供应商不存在")
    was_active = p.is_active
    db.delete(p)
    db.commit()
    if was_active:
        fallback = db.query(models.RelayProvider).first()
        if fallback:
            fallback.is_active = True
            db.commit()
    return {"ok": True}


@router.get("/providers/{provider_id}/models")
def list_provider_models(
    provider_id: int, admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    """Live GET {base_url}/models on this provider (not necessarily the
    active one) so the admin can pick a real model id for image_model
    instead of guessing."""
    from ..services import relay_client

    p = db.query(models.RelayProvider).filter(models.RelayProvider.id == provider_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="供应商不存在")
    try:
        return relay_client.proxy_get(p.base_url, p.api_key, "/models")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取模型列表失败: {e}")


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
