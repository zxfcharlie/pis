"""
Turns a template's prompt fields + 1-2 uploaded product photos into generated
product photo-set image(s).

This calls out to an existing remote relay service (the user's own ai-relay
project, OpenAI-SDK compatible) at `{relay_base_url}/images/edits`, passing
size / quality / n / output_format / background exactly as OpenAI's Images
API expects. The relay is configured by the admin (base URL + rk-... key,
see /api/admin/config) -- this app never holds a raw OpenAI/Anthropic key.

If no relay is configured (or the call fails), a local placeholder image is
rendered instead (via Pillow) so the whole app stays runnable/demoable.
"""
import io
import logging
from typing import List, Optional

import requests
from PIL import Image, ImageDraw, ImageFont

from ..config import settings

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


def compose_prompt(fields: dict) -> str:
    blocks = []
    for key, label in FIELD_LABELS:
        value = (fields.get(key) or "").strip()
        if value:
            blocks.append(f"【{label}】{value}")
    return "\n\n".join(blocks)


def size_from_parameters(parameters: str) -> str:
    """Best-effort mapping from our template's `--ar x:y` convention to an
    OpenAI Images size string, used only when the caller doesn't pass an
    explicit `size`."""
    parameters = parameters or ""
    if "4:5" in parameters:
        return "1024x1536"
    if "16:9" in parameters:
        return "1536x1024"
    if "1:1" in parameters:
        return "1024x1024"
    return "auto"


def _call_relay_image_edit(
    relay_base_url: str,
    relay_api_key: str,
    input_images: List[bytes],
    prompt: str,
    size: str,
    quality: str,
    n: int,
    output_format: str,
    background: str,
) -> List[bytes]:
    url = f"{relay_base_url.rstrip('/')}/images/edits"
    headers = {"Authorization": f"Bearer {relay_api_key}"}
    files = [
        ("image[]", (f"ref_{i}.png", img, "image/png")) for i, img in enumerate(input_images)
    ]
    data = {
        "model": settings.IMAGE_GEN_MODEL,
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
    text = "[未配置中转服务，以下为占位图]\n\n" + prompt
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


def generate_images(
    input_images: List[bytes],
    prompt_fields: dict,
    n: int = 1,
    relay_base_url: str = "",
    relay_api_key: str = "",
    size: Optional[str] = None,
    quality: str = "auto",
    output_format: str = "png",
    background: str = "auto",
) -> List[bytes]:
    prompt = compose_prompt(prompt_fields)

    size = size if size in VALID_SIZES else size_from_parameters(prompt_fields.get("parameters", ""))
    quality = quality if quality in VALID_QUALITY else "auto"
    output_format = output_format if output_format in VALID_FORMAT else "png"
    background = background if background in VALID_BACKGROUND else "auto"

    if not relay_base_url or not relay_api_key:
        logger.warning("remote relay not configured - returning placeholder image(s)")
        return [_placeholder_image(prompt, size) for _ in range(n)]

    try:
        images = _call_relay_image_edit(
            relay_base_url, relay_api_key, input_images, prompt, size, quality, n, output_format, background
        )
        if not images:
            raise RuntimeError("上游未返回任何图片")
        return images
    except Exception:
        logger.exception("image generation via remote relay failed, falling back to placeholder")
        return [_placeholder_image(prompt + "\n\n[中转服务调用失败，已回退为占位图]", size) for _ in range(n)]
