import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_user_by_relay_key
from ..database import get_db
from ..services import relay_client

router = APIRouter(prefix="/v1", tags=["relay"])


def get_relay_user(
    authorization: str = Header(None), db: Session = Depends(get_db)
) -> models.User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少Authorization: Bearer <中转密钥>")
    key = authorization.split(" ", 1)[1].strip()
    user = get_user_by_relay_key(db, key)
    if not user:
        raise HTTPException(status_code=401, detail="中转密钥无效")
    return user


@router.get("/models")
def list_models(user: models.User = Depends(get_relay_user)):
    now = int(time.time())
    models_list = [
        "gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3", "o3-mini",
        "claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001",
    ]
    return {
        "object": "list",
        "data": [{"id": m, "object": "model", "created": now, "owned_by": "relay"} for m in models_list],
    }


@router.post("/chat/completions")
def chat_completions(
    request: Request,
    payload: dict,
    user: models.User = Depends(get_relay_user),
):
    model = payload.get("model", "")
    is_claude = relay_client.is_claude_model(model)
    stream = bool(payload.get("stream", False))

    try:
        if is_claude:
            result = relay_client.call_claude_chat(payload)
        else:
            result = relay_client.call_openai_chat(payload)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"上游调用失败: {e}")

    if not stream:
        return result  # already a plain dict in OpenAI format

    # result is a raw streaming `requests.Response`
    if is_claude:
        generator = relay_client.anthropic_stream_to_openai_sse(result, model)
    else:
        generator = relay_client.openai_stream_passthrough(result)

    return StreamingResponse(generator, media_type="text/event-stream")
