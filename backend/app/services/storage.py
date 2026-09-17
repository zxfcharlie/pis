import datetime
import io
import json
import logging
import shutil
import zipfile
from pathlib import Path
from typing import List

from sqlalchemy.orm import Session

from .. import models
from ..config import settings

logger = logging.getLogger("storage")


def user_upload_dir(user_id: int) -> Path:
    d = settings.UPLOAD_DIR / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def job_output_dir(user_id: int, job_token: str) -> Path:
    d = settings.GENERATED_DIR / str(user_id) / job_token
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_upload_bytes(user_id: int, filename: str, content: bytes) -> str:
    """Returns path relative to UPLOAD_DIR."""
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    safe_name = f"{ts}_{Path(filename).name}"
    dest = user_upload_dir(user_id) / safe_name
    dest.write_bytes(content)
    return str(dest.relative_to(settings.UPLOAD_DIR))


def save_generated_images(user_id: int, job_token: str, images: List[bytes]) -> List[str]:
    """Returns paths relative to GENERATED_DIR."""
    out_dir = job_output_dir(user_id, job_token)
    rel_paths = []
    for idx, img_bytes in enumerate(images):
        fname = f"image_{idx + 1}.png"
        (out_dir / fname).write_bytes(img_bytes)
        rel_paths.append(str((out_dir / fname).relative_to(settings.GENERATED_DIR)))
    return rel_paths


def abs_generated_path(rel_path: str) -> Path:
    return settings.GENERATED_DIR / rel_path


def abs_upload_path(rel_path: str) -> Path:
    return settings.UPLOAD_DIR / rel_path


def cleanup_expired(db: Session) -> int:
    """Delete generated files (and DB rows) whose expire_at has passed.
    Returns number of jobs cleaned up."""
    now = datetime.datetime.utcnow()
    expired = db.query(models.GenerationJob).filter(models.GenerationJob.expire_at < now).all()
    count = 0
    for job in expired:
        try:
            out_paths = json.loads(job.output_images_json or "[]")
            for rel in out_paths:
                p = abs_generated_path(rel)
                if p.exists():
                    p.unlink()
            # remove now-empty job directory
            if out_paths:
                job_dir = abs_generated_path(out_paths[0]).parent
                if job_dir.exists() and not any(job_dir.iterdir()):
                    job_dir.rmdir()
        except Exception:
            logger.exception("failed to remove files for expired job %s", job.id)
        db.delete(job)
        count += 1
    if count:
        db.commit()
        logger.info("cleanup_expired removed %d job(s)", count)
    return count


def build_zip(job_paths: List[List[str]], job_ids: List[int]) -> bytes:
    """job_paths[i] is the list of relative output-image paths for job_ids[i]."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for job_id, rel_paths in zip(job_ids, job_paths):
            for rel in rel_paths:
                p = abs_generated_path(rel)
                if p.exists():
                    arcname = f"job_{job_id}/{p.name}"
                    zf.write(p, arcname)
    buf.seek(0)
    return buf.read()
