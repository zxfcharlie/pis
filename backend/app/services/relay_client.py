"""
Implements the OpenAI-compatible `/v1/chat/completions` relay described in
the project spec: any client that supports a custom `base_url` can point at
this service using a `rk-...` relay key instead of a real OpenAI/Anthropic
key. Requests are routed to the real upstream based on the `model` field and
always answered in OpenAI's response format (including streaming).
"""
import json
import time
import uuid
from typing import Generator

import requests

from ..config import settings

CLAUDE_PREFIXES = ("claude",)


def is_claude_model(model: str) -> bool:
    return (model or "").lower().startswith(CLAUDE_PREFIXES)


# ---------------- OpenAI passthrough ----------------

def call_openai_chat(payload: dict):
    url = f"{settings.OPENAI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    if payload.get("stream"):
        resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=300)
        resp.raise_for_status()
        return resp  # caller streams resp.iter_lines() straight through, already OpenAI SSE format
    resp = requests.post(url, headers=headers, json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()


# ---------------- Claude conversion ----------------

def _openai_messages_to_anthropic(messages: list):
    system_parts = []
    converted = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(content if isinstance(content, str) else json.dumps(content))
            continue
        if role not in ("user", "assistant"):
            continue
        converted.append({"role": role, "content": content})
    return "\n".join(system_parts), converted


def call_claude_chat(payload: dict):
    system, messages = _openai_messages_to_anthropic(payload.get("messages", []))
    anthropic_payload = {
        "model": payload.get("model"),
        "max_tokens": payload.get("max_tokens", 1024),
        "messages": messages,
        "temperature": payload.get("temperature", 1.0),
        "stream": bool(payload.get("stream", False)),
    }
    if system:
        anthropic_payload["system"] = system

    url = f"{settings.ANTHROPIC_BASE_URL}/messages"
    headers = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    if payload.get("stream"):
        resp = requests.post(url, headers=headers, json=anthropic_payload, stream=True, timeout=300)
        resp.raise_for_status()
        return resp  # raw anthropic SSE stream; caller converts via anthropic_stream_to_openai_sse
    resp = requests.post(url, headers=headers, json=anthropic_payload, timeout=300)
    resp.raise_for_status()
    return _anthropic_response_to_openai(resp.json(), payload.get("model"))


def _anthropic_response_to_openai(data: dict, model: str) -> dict:
    text_parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    text = "".join(text_parts)
    usage = data.get("usage", {})
    finish_map = {"end_turn": "stop", "max_tokens": "length", "stop_sequence": "stop"}
    return {
        "id": data.get("id", f"chatcmpl-{uuid.uuid4().hex}"),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish_map.get(data.get("stop_reason"), "stop"),
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }


def anthropic_stream_to_openai_sse(resp, model: str) -> Generator[str, None, None]:
    """Converts Anthropic's SSE event stream into OpenAI chat.completion.chunk SSE lines."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    def make_chunk(delta: dict, finish_reason=None):
        return {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }

    # initial role chunk, matching OpenAI's streaming convention
    yield f"data: {json.dumps(make_chunk({'role': 'assistant'}))}\n\n"

    for raw_line in resp.iter_lines():
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="ignore")
        if not line.startswith("data:"):
            continue
        data_str = line[len("data:"):].strip()
        if data_str == "[DONE]":
            break
        try:
            event = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")
        if etype == "content_block_delta":
            delta_text = event.get("delta", {}).get("text", "")
            if delta_text:
                yield f"data: {json.dumps(make_chunk({'content': delta_text}))}\n\n"
        elif etype == "message_delta":
            stop_reason = event.get("delta", {}).get("stop_reason")
            if stop_reason:
                finish = {"end_turn": "stop", "max_tokens": "length"}.get(stop_reason, "stop")
                yield f"data: {json.dumps(make_chunk({}, finish_reason=finish))}\n\n"
        elif etype == "message_stop":
            break

    yield "data: [DONE]\n\n"


def openai_stream_passthrough(resp) -> Generator[str, None, None]:
    for raw_line in resp.iter_lines():
        if raw_line:
            yield raw_line.decode("utf-8", errors="ignore") + "\n\n"
