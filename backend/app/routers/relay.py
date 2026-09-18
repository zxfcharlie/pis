from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import crud, models
from ..auth import get_user_by_relay_key
from ..database import get_db
from ..services import relay_client

router = APIRouter(prefix="/v1", tags=["relay"])


def get_relay_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> models.User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少Authorization: Bearer <中转密钥>")
    key = authorization.split(" ", 1)[1].strip()
    user = get_user_by_relay_key(db, key)
    if not user:
        raise HTTPException(status_code=401, detail="中转密钥无效")
    return user


def _relay_config(db: Session):
    cfg = crud.get_or_create_global_config(db)
    if not cfg.remote_relay_base_url or not cfg.remote_relay_api_key:
        raise HTTPException(status_code=503, detail="管理员尚未配置中转服务地址/密钥（设置 -> 中转访问）")
    return cfg.remote_relay_base_url, cfg.remote_relay_api_key


@router.get("/models")
def list_models(user: models.User = Depends(get_relay_user), db: Session = Depends(get_db)):
    base_url, api_key = _relay_config(db)
    try:
        return relay_client.proxy_get(base_url, api_key, "/models")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"上游调用失败: {e}")


@router.post("/chat/completions")
def chat_completions(request: Request, payload: dict, user: models.User = Depends(get_relay_user), db: Session = Depends(get_db)):
    base_url, api_key = _relay_config(db)
    stream = bool(payload.get("stream", False))
    try:
        result = relay_client.proxy_json(base_url, api_key, "/chat/completions", payload, stream=stream)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"上游调用失败: {e}")

    if not stream:
        return result
    return StreamingResponse(relay_client.sse_passthrough(result), media_type="text/event-stream")


@router.post("/images/generations")
def images_generations(payload: dict, user: models.User = Depends(get_relay_user), db: Session = Depends(get_db)):
    base_url, api_key = _relay_config(db)
    try:
        return relay_client.proxy_json(base_url, api_key, "/images/generations", payload)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"上游调用失败: {e}")


@router.post("/images/edits")
def images_edits(
    model: str = Form(...),
    prompt: str = Form(...),
    size: Optional[str] = Form("auto"),
    quality: Optional[str] = Form("auto"),
    n: Optional[int] = Form(1),
    output_format: Optional[str] = Form("png"),
    background: Optional[str] = Form("auto"),
    image: List[UploadFile] = File(...),
    user: models.User = Depends(get_relay_user),
    db: Session = Depends(get_db),
):
    base_url, api_key = _relay_config(db)
    files = [("image[]", (f.filename or f"image_{i}.png", f.file.read(), f.content_type or "image/png")) for i, f in enumerate(image)]
    data = {
        "model": model, "prompt": prompt, "size": size, "quality": quality,
        "n": str(n), "output_format": output_format, "background": background,
    }
    try:
        return relay_client.proxy_multipart(base_url, api_key, "/images/edits", data, files)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"上游调用失败: {e}")
