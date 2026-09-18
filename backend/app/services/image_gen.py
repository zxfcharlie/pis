"""
Turns a template's prompt fields + 1-2 uploaded product photos into generated
product photo-set image(s), via whichever RelayProvider the admin currently
has marked active (admin panel -> API 供应商, switchable at any time without
a redeploy). Two calling conventions are supported today:

- kind == "sync_edit": OpenAI-style synchronous POST {base_url}/images/edits
  (multipart `image[]` fields, `size`/`quality`/`n`/`output_format`/
  `background`, immediate b64_json/url back). This is what the user's own
  ai-relay project speaks.

- kind == "toapis_async": ToAPIs-style. Reference photos must be uploaded
  first (POST {base_url}/uploads/images, multipart `file`) to get public
  URLs -- ToAPIs no longer accepts inline base64. Then POST
  {base_url}/images/generations (JSON body, `reference_images` as URLs,
  `size` as an aspect ratio like "1:1"/"4:5"/"16:9", `resolution` as
  "1k"/"2k"/"4k") returns a task id, which is polled via
  GET {base_url}/images/generations/{task_id} until status is
  completed/failed (docs recommend an initial 5s wait, then >=5-10s between
  polls with jitter; we cap total wait at ~110s).

If no provider is active (or the call fails for any reason), a local
placeholder image is rendered instead (via Pillow) so the whole app stays
runnable/demoable.
"""
import io
import logging
import random
import re
import time
from typing import List, Optional

import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("image_gen")

FIELD_LABELS = [
    ("subject", "主体"),
    ("style", "风格"),
    ("photography", "摄影"),
    ("atmosphere", "氛围"),
    ("background", "背景"),
    ("light", "光线"),
    ("negative", "负面"),
    ("parameters", "参数"),
]

VALID_SIZES = {"auto", "1024x1024", "1024x1536", "1536x1024"}
VALID_QUALITY = {"auto", "low", "medium", "high"}
VALID_FORMAT = {"png", "jpeg", "webp"}
VALID_BACKGROUND = {"auto", "transparent", "opaque"}

TOAPIS_POLL_INITIAL_WAIT = 5
TOAPIS_POLL_MAX_WAIT = 110
TOAPIS_POLL_MIN_INTERVAL = 5


def compose_prompt(fields: dict) -> str:
    blocks = []
    for key, label in FIELD_LABELS:
        value = (fields.get(key) or "").strip()
        if value:
            blocks.append(f"【{label}】{value}")
    return "\n\n".join(blocks)


def size_from_parameters(parameters: str) -> str:
    """Best-effort mapping from our template's `--ar x:y` convention to an
    OpenAI Images pixel-size string, used by the sync_edit provider when the
    caller doesn't pass an explicit `size`."""
    parameters = parameters or ""
    if "4:5" in parameters:
        return "1024x1536"
    if "16:9" in parameters:
        return "1536x1024"
    if "1:1" in parameters:
        return "1024x1024"
    return "auto"


def aspect_ratio_from_parameters(parameters: str) -> str:
    """Our templates already encode `--ar W:H` (see convert_seed.py) which is
    exactly the aspect-ratio string ToAPIs' `size` field wants -- no lossy
    pixel-size round trip needed for that provider."""
    m = re.search(r"--ar\s+(\d+:\d+)", parameters or "")
    return m.group(1) if m else "1:1"


def _resolution_from_quality(quality: str) -> str:
    return {"high": "2k", "medium": "1k", "low": "1k", "auto": "1k"}.get(quality, "1k")


# ---------------- provider: sync_edit (this user's own ai-relay project) ----------------

def _call_sync_edit(
    base_url: str, api_key: str, input_images: List[bytes], prompt: str,
    size: str, quality: str, n: int, output_format: str, background: str, model: str,
) -> List[bytes]:
    url = f"{base_url.rstrip('/')}/images/edits"
    headers = {"Authorization": f"Bearer {api_key}"}
    files = [("image[]", (f"ref_{i}.png", img, "image/png")) for i, img in enumerate(input_images)]
    data = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": str(n),
        "output_format": output_format,
        "background": background,
    }
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=180)
    resp.raise_for_status()
    payload = resp.json()
    results = []
    for item in payload.get("data", []):
        b64 = item.get("b64_json")
        if b64:
            import base64
            results.append(base64.b64decode(b64))
        elif item.get("url"):
            img_resp = requests.get(item["url"], timeout=60)
            img_resp.raise_for_status()
            results.append(img_resp.content)
    return results


# ---------------- provider: toapis_async ----------------

def _toapis_upload_image(base_url: str, api_key: str, img_bytes: bytes, idx: int) -> str:
    url = f"{base_url.rstrip('/')}/uploads/images"
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": (f"ref_{idx}.png", img_bytes, "image/png")}
    resp = requests.post(url, headers=headers, files=files, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(payload.get("message") or "参考图上传失败")
    return payload["data"]["url"]


def _call_toapis_async(
    base_url: str, api_key: str, input_images: List[bytes], prompt: str,
    aspect_ratio: str, quality: str, n: int, background: str, model: str,
) -> List[bytes]:
    base_url = base_url.rstrip("/")
    reference_urls = [
        _toapis_upload_image(base_url, api_key, img, i) for i, img in enumerate(input_images)
    ]

    body = {
        "model": model,
        "prompt": prompt,
        "size": aspect_ratio,
        "resolution": _resolution_from_quality(quality),
        "n": n,
        "response_format": "url",
        "reference_images": reference_urls,
    }
    if background == "transparent":
        body["background"] = "transparent"  # ToAPIs: omit entirely for normal/opaque generations

    headers_json = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(f"{base_url}/images/generations", headers=headers_json, json=body, timeout=30)
    resp.raise_for_status()
    task = resp.json()
    task_id = task.get("id")
    if not task_id:
        raise RuntimeError(f"未获取到任务ID: {task}")

    time.sleep(TOAPIS_POLL_INITIAL_WAIT)
    deadline = time.time() + TOAPIS_POLL_MAX_WAIT
    interval = TOAPIS_POLL_MIN_INTERVAL
    status_url = f"{base_url}/images/generations/{task_id}"
    result = None
    while time.time() < deadline:
        r = requests.get(status_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", interval))
            time.sleep(retry_after + random.uniform(0, 1))
            interval = min(interval * 1.5, 15)
            continue
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        if status == "completed":
            result = data
            break
        if status == "failed":
            err = (data.get("error") or {}).get("message", "生成失败")
            raise RuntimeError(err)
        time.sleep(interval + random.uniform(0, 1))
        interval = min(interval * 1.5, 15)

    if not result:
        raise RuntimeError("ToAPIs 任务超时（超过110秒未完成）")

    urls = [item["url"] for item in (result.get("result") or {}).get("data", []) if item.get("url")]
    images = []
    for u in urls[:n]:
        img_resp = requests.get(u, timeout=60)
        img_resp.raise_for_status()
        images.append(img_resp.content)
    return images


# ---------------- placeholder fallback ----------------

def _placeholder_image(prompt: str, size: str) -> bytes:
    if size == "auto" or "x" not in size:
        size = "1024x1024"
    w, h = (int(x) for x in size.split("x"))
    img = Image.new("RGB", (w, h), color=(30, 34, 45))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    margin = 24
    text = "[未配置可用的中转供应商，以下为占位图]\n\n" + prompt
    max_chars = max(10, (w - 2 * margin) // 7)
    lines = []
    for raw_line in text.split("\n"):
        while len(raw_line) > max_chars:
            lines.append(raw_line[:max_chars])
            raw_line = raw_line[max_chars:]
        lines.append(raw_line)

    y = margin
    for line in lines:
        draw.text((margin, y), line, fill=(230, 230, 235), font=font)
        y += 14
        if y > h - margin:
            break
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------- entry point ----------------

def generate_images(
    input_images: List[bytes],
    prompt_fields: Optional[dict] = None,
    n: int = 1,
    provider=None,  # models.RelayProvider | None
    size: Optional[str] = None,
    quality: str = "auto",
    output_format: str = "png",
    background: str = "auto",
    model: Optional[str] = None,
    raw_prompt: Optional[str] = None,
) -> List[bytes]:
    prompt_fields = prompt_fields or {}
    prompt = raw_prompt if raw_prompt is not None else compose_prompt(prompt_fields)
    model = model or (getattr(provider, "image_model", None) or "gpt-image-2")

    pixel_size = size if size in VALID_SIZES else size_from_parameters(prompt_fields.get("parameters", ""))
    quality = quality if quality in VALID_QUALITY else "auto"
    output_format = output_format if output_format in VALID_FORMAT else "png"
    background = background if background in VALID_BACKGROUND else "auto"

    if not provider or not provider.base_url or not provider.api_key:
        logger.warning("no active relay provider configured - returning placeholder image(s)")
        return [_placeholder_image(prompt, pixel_size) for _ in range(n)]

    try:
        if provider.kind == "toapis_async":
            aspect_ratio = aspect_ratio_from_parameters(prompt_fields.get("parameters", "")) if not raw_prompt else "1:1"
            images = _call_toapis_async(
                provider.base_url, provider.api_key, input_images, prompt, aspect_ratio, quality, n, background, model
            )
        else:
            images = _call_sync_edit(
                provider.base_url, provider.api_key, input_images, prompt,
                pixel_size, quality, n, output_format, background, model,
            )
        if not images:
            raise RuntimeError("上游未返回任何图片")
        return images
    except Exception:
        logger.exception("image generation via provider '%s' (%s) failed, falling back to placeholder",
                          getattr(provider, "name", "?"), getattr(provider, "kind", "?"))
        return [_placeholder_image(prompt + "\n\n[中转服务调用失败，已回退为占位图]", pixel_size) for _ in range(n)]
