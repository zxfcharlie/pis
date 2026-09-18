"""
Generic reverse-proxy helpers for forwarding /v1/* requests to the existing
remote relay service (admin-configured base URL + rk-... key, see
/api/admin/config). The remote relay already does OpenAI<->Claude provider
routing and format normalization, so this layer stays a thin passthrough:
our own users authenticate with their own per-user rk- key (issued by this
app), and we re-sign the request upstream with the admin's relay key.
"""
import logging
from typing import Generator, Optional

import requests

logger = logging.getLogger("relay_client")


def proxy_json(
    relay_base_url: str,
    relay_api_key: str,
    path: str,
    payload: dict,
    stream: bool = False,
    timeout: int = 300,
):
    """POST JSON to {relay_base_url}{path}. Returns parsed dict for non-streaming
    calls, or the raw `requests.Response` (stream=True) for the caller to relay."""
    url = f"{relay_base_url.rstrip('/')}{path}"
    headers = {
        "Authorization": f"Bearer {relay_api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=payload, stream=stream, timeout=timeout)
    resp.raise_for_status()
    if stream:
        return resp
    return resp.json()


def proxy_multipart(
    relay_base_url: str,
    relay_api_key: str,
    path: str,
    data: dict,
    files: list,
    timeout: int = 180,
) -> dict:
    url = f"{relay_base_url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {relay_api_key}"}
    resp = requests.post(url, headers=headers, data=data, files=files, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def proxy_get(relay_base_url: str, relay_api_key: str, path: str, timeout: int = 30) -> dict:
    url = f"{relay_base_url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {relay_api_key}"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def sse_passthrough(resp) -> Generator[str, None, None]:
    """The remote relay already returns OpenAI-format SSE for every provider
    (it does the Claude<->OpenAI stream conversion itself), so we just
    forward its bytes line by line."""
    for raw_line in resp.iter_lines():
        if raw_line:
            yield raw_line.decode("utf-8", errors="ignore") + "\n\n"
        else:
            yield "\n"
