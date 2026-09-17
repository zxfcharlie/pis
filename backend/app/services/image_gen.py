"""
Turns a template's prompt fields + 1-2 uploaded product photos into generated
product photo-set image(s).

By default this calls OpenAI's image-edit endpoint (`IMAGE_GEN_MODEL`, e.g.
gpt-image-1) with the uploaded product photos as reference images. Swap
`_call_openai_image_edit` for whichever image model you actually have access
to (Midjourney via a bridge, a Claude/Gemini image tool, an internal diffusion
service, etc.) -- the rest of the app only depends on `generate_images()`'s
signature.

If OPENAI_API_KEY is not configured, a local placeholder image is rendered
instead (via Pillow) so the whole app is runnable and demoable without any
upstream key.
"""
import io
import logging
from typing import List

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


def compose_prompt(fields: dict) -> str:
    blocks = []
    for key, label in FIELD_LABELS:
        value = (fields.get(key) or "").strip()
        if value:
            blocks.append(f"【{label}】{value}")
    return "\n\n".join(blocks)


def _size_from_parameters(parameters: str) -> str:
    parameters = parameters or ""
    if "4:5" in parameters:
        return "1024x1536"
    if "16:9" in parameters:
        return "1536x1024"
    return "1024x1024"


def _call_openai_image_edit(input_images: List[bytes], prompt: str, size: str, n: int) -> List[bytes]:
    url = f"{settings.OPENAI_BASE_URL}/images/edits"
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
    files = [
        ("image[]", (f"ref_{i}.png", img, "image/png")) for i, img in enumerate(input_images)
    ]
    data = {
        "model": settings.IMAGE_GEN_MODEL,
        "prompt": prompt,
        "size": size,
        "n": str(n),
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
    w, h = (int(x) for x in size.split("x"))
    img = Image.new("RGB", (w, h), color=(30, 34, 45))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    margin = 24
    text = (
        "[未配置 OPENAI_API_KEY，以下为占位图]\n\n" + prompt
    )
    # naive manual word-wrap
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


def generate_images(input_images: List[bytes], prompt_fields: dict, n: int = 1) -> List[bytes]:
    prompt = compose_prompt(prompt_fields)
    size = _size_from_parameters(prompt_fields.get("parameters", ""))

    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set - returning placeholder image(s)")
        return [_placeholder_image(prompt, size) for _ in range(n)]

    try:
        images = _call_openai_image_edit(input_images, prompt, size, n)
        if not images:
            raise RuntimeError("upstream returned no images")
        return images
    except Exception:
        logger.exception("image generation upstream call failed, falling back to placeholder")
        return [_placeholder_image(prompt + "\n\n[上游生成失败，已回退为占位图]", size) for _ in range(n)]
