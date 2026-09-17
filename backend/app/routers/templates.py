from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_admin, get_current_user
from ..database import get_db

router = APIRouter(prefix="/api/templates", tags=["templates"])


def _to_out(t: models.Template, user: models.User) -> schemas.TemplateOut:
    return schemas.TemplateOut(
        id=t.id,
        owner_id=t.owner_id,
        is_system=t.is_system,
        editable=crud.template_editable_by(user, t),
        name=t.name,
        season=t.season,
        scene=t.scene,
        product=t.product,
        region=t.region,
        subject=t.subject,
        style=t.style,
        photography=t.photography,
        atmosphere=t.atmosphere,
        background=t.background,
        light=t.light,
        negative=t.negative,
        parameters=t.parameters,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("/filters", response_model=schemas.TemplateFilterOptions)
def filter_options(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(models.Template).filter(
        or_(models.Template.is_system == True, models.Template.owner_id == user.id)  # noqa: E712
    )
    templates = q.all()
    def uniq(vals):
        return sorted({v for v in vals if v})

    return schemas.TemplateFilterOptions(
        seasons=uniq(t.season for t in templates),
        scenes=uniq(t.scene for t in templates),
        products=uniq(t.product for t in templates),
        regions=uniq(t.region for t in templates),
    )


@router.get("", response_model=List[schemas.TemplateOut])
def list_templates(
    season: Optional[List[str]] = Query(None),
    scene: Optional[List[str]] = Query(None),
    product: Optional[List[str]] = Query(None),
    region: Optional[List[str]] = Query(None),
    mine_only: bool = False,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(models.Template)
    if mine_only:
        q = q.filter(models.Template.owner_id == user.id)
    else:
        q = q.filter(or_(models.Template.is_system == True, models.Template.owner_id == user.id))  # noqa: E712

    if season:
        q = q.filter(models.Template.season.in_(season))
    if scene:
        q = q.filter(models.Template.scene.in_(scene))
    if product:
        q = q.filter(models.Template.product.in_(product))
    if region:
        q = q.filter(models.Template.region.in_(region))

    templates = q.order_by(models.Template.is_system.desc(), models.Template.id).all()
    return [_to_out(t, user) for t in templates]


@router.get("/{template_id}", response_model=schemas.TemplateOut)
def get_template(template_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(models.Template).filter(models.Template.id == template_id).first()
    if not t or not crud.template_visible_to(user, t):
        raise HTTPException(status_code=404, detail="模板不存在")
    return _to_out(t, user)


@router.post("", response_model=schemas.TemplateOut)
def create_template(
    payload: schemas.TemplateCreateIn,
    as_system: bool = False,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if as_system and not user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可创建系统模板")

    t = models.Template(
        owner_id=None if as_system else user.id,
        is_system=as_system,
        **payload.dict(),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _to_out(t, user)


@router.put("/{template_id}", response_model=schemas.TemplateOut)
def update_template(
    template_id: int,
    payload: schemas.TemplateUpdateIn,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.query(models.Template).filter(models.Template.id == template_id).first()
    if not t or not crud.template_visible_to(user, t):
        raise HTTPException(status_code=404, detail="模板不存在")
    if not crud.template_editable_by(user, t):
        raise HTTPException(status_code=403, detail="该模板不可编辑")

    for k, v in payload.dict(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return _to_out(t, user)


@router.delete("/{template_id}")
def delete_template(template_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(models.Template).filter(models.Template.id == template_id).first()
    if not t or not crud.template_visible_to(user, t):
        raise HTTPException(status_code=404, detail="模板不存在")
    if not crud.template_editable_by(user, t):
        raise HTTPException(status_code=403, detail="该模板不可删除")
    db.delete(t)
    db.commit()
    return {"ok": True}
