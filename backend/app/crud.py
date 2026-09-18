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
            remote_relay_base_url=settings.REMOTE_RELAY_BASE_URL,
            remote_relay_api_key=settings.REMOTE_RELAY_API_KEY,
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
