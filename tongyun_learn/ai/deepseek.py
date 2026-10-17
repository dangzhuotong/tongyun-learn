"""DeepSeek Chat Completions。云芽教练专用，不经过 KIE。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from tongyun_learn.config import Settings

logger = logging.getLogger("tongyun_learn.ai.deepseek")


class DeepSeekError(Exception):
    def __init__(self, code: str, message: str, *, api_key: str = "") -> None:
        if api_key and api_key in message:
            message = message.replace(api_key, "[REDACTED]")
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def _secret(settings: Settings) -> str:
    key = settings.deepseek_api_key
    raw = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
    return raw.strip()


def complete_chat(
    messages: list[dict[str, str]],
    settings: Settings,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """调用 DeepSeek，返回 text / tokens_in / tokens_out / model。失败抛 DeepSeekError，消息里不含密钥。"""
    api_key = _secret(settings)
    if not api_key:
        raise DeepSeekError("not_configured", "未配置 DEEPSEEK_API_KEY")

    url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=settings.ai_timeout_s, transport=transport) as client:
            resp = client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise DeepSeekError("timeout", "DeepSeek 超时", api_key=api_key) from exc
    except httpx.HTTPError as exc:
        raise DeepSeekError("network", "DeepSeek 网络错误", api_key=api_key) from exc

    if resp.status_code >= 400:
        snippet = resp.text[:300]
        logger.warning("deepseek http %s model=%s", resp.status_code, settings.deepseek_model)
        raise DeepSeekError("http", f"DeepSeek HTTP {resp.status_code}: {snippet}", api_key=api_key)

    try:
        body = resp.json()
        text = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("bad_output", "DeepSeek 返回里没有文本", api_key=api_key) from exc
    if not isinstance(text, str) or not text.strip():
        raise DeepSeekError("bad_output", "DeepSeek 返回空文本", api_key=api_key)
    if api_key in text:
        text = text.replace(api_key, "[REDACTED]")
    usage = body.get("usage") or {}
    return {
        "text": text,
        "tokens_in": usage.get("prompt_tokens"),
        "tokens_out": usage.get("completion_tokens"),
        "model": str(body.get("model") or settings.deepseek_model),
    }
