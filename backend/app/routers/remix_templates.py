from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user, get_current_user_for_image
from ..database import get_db
from ..services import storage

router = APIRouter(prefix="/api/remix-templates", tags=["remix-templates"])


def _to_out(t: models.RemixTemplate, user: models.User) -> schemas.RemixTemplateOut:
    return schemas.RemixTemplateOut(
        id=t.id,
        owner_id=t.owner_id,
        is_system=t.is_system,
        editable=crud.remix_editable_by(user, t),
        name=t.name,
        product=t.product,
        prompt=t.prompt,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _visible_query(db: Session, user: models.User, mine_only: bool):
    q = db.query(models.RemixTemplate)
    if mine_only:
        q = q.filter(models.RemixTemplate.owner_id == user.id)
    else:
        q = q.filter(or_(models.RemixTemplate.is_system == True, models.RemixTemplate.owner_id == user.id))  # noqa: E712
    allowed = crud.get_allowed_products(db, user)
    if allowed is not None:
        q = q.filter(models.RemixTemplate.product.in_(allowed))
    return q


def _usable(db: Session, user: models.User, t: models.RemixTemplate) -> bool:
    if not crud.remix_visible_to(user, t):
        return False
    allowed = crud.get_allowed_products(db, user)
    return allowed is None or t.product in allowed


@router.get("/filters")
def filter_options(mine_only: bool = False, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = _visible_query(db, user, mine_only)
    products = sorted({p for (p,) in q.with_entities(models.RemixTemplate.product).all() if p})
    return {"products": products}


@router.get("", response_model=List[schemas.RemixTemplateOut])
def list_remix_templates(
    product: Optional[List[str]] = Query(None),
    mine_only: bool = False,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = _visible_query(db, user, mine_only)
    if product:
        q = q.filter(models.RemixTemplate.product.in_(product))
    templates = q.order_by(models.RemixTemplate.product, models.RemixTemplate.is_system.desc(), models.RemixTemplate.id).all()
    return [_to_out(t, user) for t in templates]


@router.get("/{template_id}", response_model=schemas.RemixTemplateOut)
def get_remix_template(template_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(models.RemixTemplate).filter(models.RemixTemplate.id == template_id).first()
    if not t or not _usable(db, user, t):
        raise HTTPException(status_code=404, detail="二创套图模板不存在")
    return _to_out(t, user)


@router.get("/{template_id}/background-image")
def get_background_image(
    template_id: int,
    thumb: bool = False,
    user: models.User = Depends(get_current_user_for_image),
    db: Session = Depends(get_db),
):
    t = db.query(models.RemixTemplate).filter(models.RemixTemplate.id == template_id).first()
    if not t or not _usable(db, user, t):
        raise HTTPException(status_code=404, detail="二创套图模板不存在")
    if not t.background_image_path:
        raise HTTPException(status_code=404, detail="该模板还没有设置图1")
    p = storage.abs_remix_background_path(t.background_image_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="背景图文件不存在")

    # a template's 图1 changes rarely (only via explicit re-upload on edit),
    # so cache hard too -- browsers will keep re-requesting it on every grid
    # render otherwise, which was a big chunk of "二创模板加载慢".
    cache_headers = {"Cache-Control": "private, max-age=86400"}

    if thumb:
        thumb_bytes = storage.make_thumbnail(p.read_bytes())
        return Response(content=thumb_bytes, media_type="image/jpeg", headers=cache_headers)

    ext = p.suffix.lower().lstrip(".")
    media_type = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
    return Response(content=p.read_bytes(), media_type=media_type, headers=cache_headers)


@router.post("", response_model=schemas.RemixTemplateOut)
def create_remix_template(
    name: str = Form(...),
    product: str = Form(""),
    prompt: str = Form("把上传的产品（图2）放到图1中"),
    as_system: bool = Form(False),
    background_image: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if as_system and not user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可创建系统模板")

    content = background_image.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="图1不能为空")
    ext = (background_image.filename or "bg.png").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "webp"):
        ext = "png"
    rel_path = storage.save_remix_background(content, ext=ext)

    t = models.RemixTemplate(
        owner_id=None if as_system else user.id,
        is_system=as_system,
        name=name,
        product=product,
        prompt=prompt,
        background_image_path=rel_path,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _to_out(t, user)


@router.put("/{template_id}", response_model=schemas.RemixTemplateOut)
def update_remix_template(
    template_id: int,
    name: Optional[str] = Form(None),
    product: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    background_image: Optional[UploadFile] = File(None),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.query(models.RemixTemplate).filter(models.RemixTemplate.id == template_id).first()
    if not t or not crud.remix_visible_to(user, t):
        raise HTTPException(status_code=404, detail="二创套图模板不存在")
    if not crud.remix_editable_by(user, t):
        raise HTTPException(status_code=403, detail="该模板不可编辑")

    if name is not None:
        t.name = name
    if product is not None:
        t.product = product
    if prompt is not None:
        t.prompt = prompt
    if background_image is not None:
        content = background_image.file.read()
        if content:
            ext = (background_image.filename or "bg.png").rsplit(".", 1)[-1].lower()
            if ext not in ("png", "jpg", "jpeg", "webp"):
                ext = "png"
            new_rel_path = storage.save_remix_background(content, ext=ext)
            old_path = t.background_image_path
            t.background_image_path = new_rel_path
            if old_path:
                storage.delete_remix_background(old_path)

    db.commit()
    db.refresh(t)
    return _to_out(t, user)


@router.delete("/{template_id}")
def delete_remix_template(template_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(models.RemixTemplate).filter(models.RemixTemplate.id == template_id).first()
    if not t or not crud.remix_visible_to(user, t):
        raise HTTPException(status_code=404, detail="二创套图模板不存在")
    if not crud.remix_editable_by(user, t):
        raise HTTPException(status_code=403, detail="该模板不可删除")
    bg_path = t.background_image_path
    db.delete(t)
    db.commit()
    if bg_path:
        storage.delete_remix_background(bg_path)
    return {"ok": True}
