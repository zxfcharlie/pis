import datetime
import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..services import image_gen, storage

router = APIRouter(tags=["generate"])

OVERRIDE_KEYS = [
    "subject",
    "style",
    "photography",
    "atmosphere",
    "background",
    "light",
    "negative",
    "parameters",
]


def _job_to_out(job: models.GenerationJob) -> schemas.GenerationOut:
    return schemas.GenerationOut(
        id=job.id,
        template_id=job.template_id,
        prompt_snapshot=json.loads(job.prompt_snapshot_json or "{}"),
        input_images=json.loads(job.input_images_json or "[]"),
        output_images=json.loads(job.output_images_json or "[]"),
        image_count=job.image_count,
        cost=job.cost,
        status=job.status,
        error_message=job.error_message or "",
        created_at=job.created_at,
        expire_at=job.expire_at,
    )


@router.post("/api/generate", response_model=schemas.GenerationOut)
def generate(
    images: List[UploadFile] = File(...),
    template_id: Optional[int] = Form(None),
    use_template_as_is: bool = Form(True),
    n: int = Form(1),
    save_as_template: bool = Form(False),
    template_name: Optional[str] = Form(None),
    # OpenAI Images API params, forwarded to the remote relay as-is
    img_size: Optional[str] = Form("auto"),
    img_quality: Optional[str] = Form("auto"),
    img_output_format: Optional[str] = Form("png"),
    img_background: Optional[str] = Form("auto"),
    # override fields - only applied when use_template_as_is is False
    subject: Optional[str] = Form(None),
    style: Optional[str] = Form(None),
    photography: Optional[str] = Form(None),
    atmosphere: Optional[str] = Form(None),
    background: Optional[str] = Form(None),
    light: Optional[str] = Form(None),
    negative: Optional[str] = Form(None),
    parameters: Optional[str] = Form(None),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not (1 <= len(images) <= 2):
        raise HTTPException(status_code=400, detail="请上传1-2张产品图")
    if not (1 <= n <= 4):
        raise HTTPException(status_code=400, detail="单次生成数量需在1-4之间")

    base_fields = {k: "" for k in OVERRIDE_KEYS}
    template = None
    if template_id is not None:
        template = db.query(models.Template).filter(models.Template.id == template_id).first()
        if not template or not crud.template_visible_to(user, template):
            raise HTTPException(status_code=404, detail="模板不存在")
        base_fields = template.prompt_fields()

    overrides = {
        "subject": subject,
        "style": style,
        "photography": photography,
        "atmosphere": atmosphere,
        "background": background,
        "light": light,
        "negative": negative,
        "parameters": parameters,
    }

    if use_template_as_is or template_id is None and not any(v for v in overrides.values()):
        final_fields = base_fields
    else:
        final_fields = dict(base_fields)
        for k, v in overrides.items():
            if v is not None:
                final_fields[k] = v

    cfg = crud.get_or_create_global_config(db)
    cost_per_image = user.cost_per_image or cfg.default_cost_per_image
    projected_cost = cost_per_image * n
    if crud.used_today(db, user.id) + projected_cost > user.daily_quota:
        raise HTTPException(status_code=403, detail="今日生成额度已用完，请明天再试或联系管理员调整额度")

    # read + persist input images
    input_rel_paths = []
    input_bytes_list = []
    for img in images:
        content = img.file.read()
        input_bytes_list.append(content)
        input_rel_paths.append(storage.save_upload_bytes(user.id, img.filename or "upload.png", content))

    job_token = uuid.uuid4().hex

    try:
        output_images_bytes = image_gen.generate_images(
            input_bytes_list,
            final_fields,
            n=n,
            relay_base_url=cfg.remote_relay_base_url or "",
            relay_api_key=cfg.remote_relay_api_key or "",
            size=img_size,
            quality=img_quality,
            output_format=img_output_format,
            background=img_background,
        )
        status_str = "success"
        error_message = ""
    except Exception as e:  # pragma: no cover - defensive
        output_images_bytes = []
        status_str = "failed"
        error_message = str(e)

    ext = img_output_format if img_output_format in ("png", "jpeg", "webp") else "png"
    output_rel_paths = (
        storage.save_generated_images(user.id, job_token, output_images_bytes, ext=ext)
        if output_images_bytes
        else []
    )
    actual_cost = cost_per_image * len(output_rel_paths)

    job = models.GenerationJob(
        user_id=user.id,
        template_id=template.id if template else None,
        prompt_snapshot_json=json.dumps(final_fields, ensure_ascii=False),
        input_images_json=json.dumps(input_rel_paths, ensure_ascii=False),
        output_images_json=json.dumps(output_rel_paths, ensure_ascii=False),
        image_count=len(output_rel_paths),
        cost=actual_cost,
        status=status_str,
        error_message=error_message,
        created_at=datetime.datetime.utcnow(),
        expire_at=datetime.datetime.utcnow() + datetime.timedelta(days=settings.IMAGE_EXPIRE_DAYS),
    )
    db.add(job)

    if save_as_template and status_str == "success":
        name = template_name or (template.name + " (自定义)" if template else f"自定义模板-{job_token[:6]}")
        new_tpl = models.Template(
            owner_id=user.id,
            is_system=False,
            name=name,
            season=template.season if template else "",
            scene=template.scene if template else "",
            product=template.product if template else "",
            region=template.region if template else "",
            **final_fields,
        )
        db.add(new_tpl)

    db.commit()
    db.refresh(job)
    return _job_to_out(job)


@router.get("/api/generations", response_model=List[schemas.GenerationOut])
def list_generations(
    page: int = 1,
    page_size: int = 20,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    jobs = (
        db.query(models.GenerationJob)
        .filter(models.GenerationJob.user_id == user.id)
        .order_by(models.GenerationJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_job_to_out(j) for j in jobs]


@router.get("/api/generations/{job_id}", response_model=schemas.GenerationOut)
def get_generation(job_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(models.GenerationJob).filter(models.GenerationJob.id == job_id).first()
    if not job or (job.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="记录不存在")
    return _job_to_out(job)


@router.get("/api/generations/{job_id}/image/{index}")
def get_generation_image(job_id: int, index: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(models.GenerationJob).filter(models.GenerationJob.id == job_id).first()
    if not job or (job.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="记录不存在")
    paths = json.loads(job.output_images_json or "[]")
    if index < 0 or index >= len(paths):
        raise HTTPException(status_code=404, detail="图片不存在")
    p = storage.abs_generated_path(paths[index])
    if not p.exists():
        raise HTTPException(status_code=404, detail="图片已过期或不存在")
    ext = p.suffix.lower().lstrip(".")
    media_type = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
    return Response(content=p.read_bytes(), media_type=media_type)


@router.post("/api/generations/batch-download")
def batch_download(payload: schemas.BatchDownloadIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs = (
        db.query(models.GenerationJob)
        .filter(models.GenerationJob.id.in_(payload.ids))
        .all()
    )
    jobs = [j for j in jobs if j.user_id == user.id or user.is_admin]
    if not jobs:
        raise HTTPException(status_code=404, detail="没有可下载的记录")

    job_ids = [j.id for j in jobs]
    job_paths = [json.loads(j.output_images_json or "[]") for j in jobs]
    zip_bytes = storage.build_zip(job_paths, job_ids)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=generations.zip"},
    )
