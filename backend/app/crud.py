import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models


def get_or_create_global_config(db: Session) -> models.GlobalConfig:
    cfg = db.query(models.GlobalConfig).filter(models.GlobalConfig.id == 1).first()
    if not cfg:
        from .config import settings

        cfg = models.GlobalConfig(
            id=1,
            default_cost_per_image=settings.DEFAULT_COST_PER_IMAGE,
            default_daily_quota=settings.DEFAULT_DAILY_QUOTA,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def used_today(db: Session, user_id: int) -> float:
    """Sum of cost for this user's successful generations created since local midnight (UTC)."""
    start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    total = (
        db.query(func.coalesce(func.sum(models.GenerationJob.cost), 0.0))
        .filter(
            models.GenerationJob.user_id == user_id,
            models.GenerationJob.created_at >= start,
            models.GenerationJob.status == "success",
        )
        .scalar()
    )
    return float(total or 0.0)


def total_generated_and_cost(db: Session, user_id: int):
    row = (
        db.query(
            func.count(models.GenerationJob.id),
            func.coalesce(func.sum(models.GenerationJob.cost), 0.0),
        )
        .filter(models.GenerationJob.user_id == user_id, models.GenerationJob.status == "success")
        .first()
    )
    return int(row[0] or 0), float(row[1] or 0.0)


def template_visible_to(user: models.User, template: models.Template) -> bool:
    return template.is_system or template.owner_id == user.id or user.is_admin


def template_editable_by(user: models.User, template: models.Template) -> bool:
    """Admin-created (system) templates are read-only for everyone except the admin
    who owns editing rights over the whole system template set."""
    if template.is_system:
        return user.is_admin
    return template.owner_id == user.id or user.is_admin


def get_active_provider(db: Session):
    return db.query(models.RelayProvider).filter(models.RelayProvider.is_active == True).first()  # noqa: E712


# ---------- 二创套图模板 (RemixTemplate) permission helpers -- shared shape with Template ----------

def remix_visible_to(user: models.User, tpl: models.RemixTemplate) -> bool:
    return tpl.is_system or tpl.owner_id == user.id or user.is_admin


def remix_editable_by(user: models.User, tpl: models.RemixTemplate) -> bool:
    if tpl.is_system:
        return user.is_admin
    return tpl.owner_id == user.id or user.is_admin


# ---------- Product-based access control ----------

def get_allowed_products(db: Session, user: models.User) -> "set[str] | None":
    """None = unrestricted (sees every product). A non-empty set restricts the
    user to exactly those products. Admins are always unrestricted."""
    if user.is_admin:
        return None
    rows = db.query(models.UserProductAccess.product).filter(models.UserProductAccess.user_id == user.id).all()
    products = {p for (p,) in rows}
    return products or None


def set_user_product_access(db: Session, user_id: int, products: list):
    db.query(models.UserProductAccess).filter(models.UserProductAccess.user_id == user_id).delete()
    for p in {p.strip() for p in products if p and p.strip()}:
        db.add(models.UserProductAccess(user_id=user_id, product=p))
    db.commit()


# ---------- Template usage stats (for the admin template table) ----------

def template_usage_counts(db: Session, since: datetime.datetime) -> dict:
    """Returns {template_id: count} of successful GenerationJob rows created
    on/after `since`."""
    rows = (
        db.query(models.GenerationJob.template_id, func.count(models.GenerationJob.id))
        .filter(
            models.GenerationJob.template_id.isnot(None),
            models.GenerationJob.created_at >= since,
            models.GenerationJob.status == "success",
        )
        .group_by(models.GenerationJob.template_id)
        .all()
    )
    return {tid: count for tid, count in rows}
