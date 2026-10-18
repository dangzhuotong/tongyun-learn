import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("tongyun_learn.ai.kie")


class KieError(Exception):
    def __init__(
        self,
        code: Any = None,
        message: str = "",
        retryable: bool = False,
        api_key: str = "",
    ) -> None:
        if isinstance(code, str) and not message and not retryable:
            message = code
            code = "error"
        if api_key and api_key in message:
            message = message.replace(api_key, "[REDACTED]")
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(f"[{code}] {message}" if code is not None else message)


@dataclass(frozen=True)
class KieResult:
    text: str
    tokens_in: int | None
    tokens_out: int | None
    credits: float | None
    model: str


def parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if m:
        cleaned = m.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in text")
    obj = json.loads(cleaned[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError(f"Parsed JSON is not an object, got {type(obj).__name__}")
    return obj


class KieClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.transport = transport

    def _sanitize(self, text: str) -> str:
        if self.api_key and self.api_key in text:
            return text.replace(self.api_key, "[REDACTED]")
        return text

    def _is_retryable_code(self, code: Any) -> bool:
        if code in ("timeout", "network", 429, "429", 500, "500", 502, "502", 503, "503", 504, "504"):
            return True
        try:
            ic = int(code)
            return ic == 429 or ic >= 500
        except (ValueError, TypeError):
            return False

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        timeout: float | None = None,
    ) -> KieResult:
        actual_timeout = self.timeout_s if timeout is None else timeout
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        is_openai_chat = model.endswith("-openai")
        if is_openai_chat:
            url = f"{self.base_url}/{model}/v1/chat/completions"
            body: dict[str, Any] = {
                "messages": messages,
                "stream": False,
                "reasoning_effort": "low",
                "include_thoughts": False,
            }
        else:
            url = f"{self.base_url}/openai/v1/responses"
            sys_parts = [m["content"] for m in messages if m.get("role") == "system"]
            instructions = "\n\n".join(sys_parts)
            non_sys = [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in messages
                if m.get("role") != "system"
            ]
            body = {
                "model": model,
                "stream": False,
                "instructions": instructions,
                "input": non_sys,
                "reasoning": {"effort": "none"},
                "text": {"format": {"type": "json_object"}},
            }

        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(actual_timeout),
            ) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise KieError(
                code="timeout",
                message=self._sanitize(f"Request timed out: {exc}"),
                retryable=True,
                api_key=self.api_key,
            ) from exc
        except httpx.TransportError as exc:
            raise KieError(
                code="network",
                message=self._sanitize(f"Network transport error: {exc}"),
                retryable=True,
                api_key=self.api_key,
            ) from exc

        if resp.status_code < 200 or resp.status_code >= 300:
            retryable = resp.status_code >= 500 or resp.status_code == 429
            raise KieError(
                code=resp.status_code,
                message=self._sanitize(f"HTTP {resp.status_code}: {resp.text}"),
                retryable=retryable,
                api_key=self.api_key,
            )

        try:
            data = resp.json()
        except Exception as exc:
            raise KieError(
                code="invalid_json",
                message=self._sanitize(f"Response is not valid JSON: {exc}"),
                retryable=True,
                api_key=self.api_key,
            ) from exc

        if not isinstance(data, dict):
            raise KieError(
                code="invalid_json",
                message="Response JSON is not an object",
                retryable=True,
                api_key=self.api_key,
            )

        if "code" in data and data["code"] not in (200, "200", 0, None):
            code_val = data["code"]
            msg_val = data.get("msg") or data.get("message") or str(data)
            retryable = self._is_retryable_code(code_val)
            raise KieError(
                code=code_val,
                message=self._sanitize(str(msg_val)),
                retryable=retryable,
                api_key=self.api_key,
            )

        if "error" in data and data["error"]:
            err_obj = data["error"]
            if isinstance(err_obj, dict):
                err_code = err_obj.get("code", "error")
                err_msg = err_obj.get("message", str(err_obj))
            else:
                err_code = "error"
                err_msg = str(err_obj)
            retryable = self._is_retryable_code(err_code)
            raise KieError(
                code=err_code,
                message=self._sanitize(str(err_msg)),
                retryable=retryable,
                api_key=self.api_key,
            )

        credits_raw = data.get("credits_consumed")
        credits_val = float(credits_raw) if credits_raw is not None else None

        usage = data.get("usage") or {}

        if is_openai_chat:
            choices = data.get("choices") or []
            if not choices or not isinstance(choices, list):
                raise KieError(
                    code="empty_response",
                    message="No choices in chat completions response",
                    retryable=True,
                    api_key=self.api_key,
                )
            msg_obj = choices[0].get("message") or {}
            content = msg_obj.get("content")
            if isinstance(content, list):
                text = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            elif content is not None:
                text = str(content)
            else:
                text = ""

            tokens_in = usage.get("prompt_tokens")
            tokens_out = usage.get("completion_tokens")
        else:
            output_list = data.get("output") or []
            text_parts = []
            if isinstance(output_list, list):
                for item in output_list:
                    if isinstance(item, dict) and item.get("type") == "message":
                        contents = item.get("content") or []
                        if isinstance(contents, list):
                            for c in contents:
                                if isinstance(c, dict) and c.get("type") == "output_text":
                                    text_parts.append(c.get("text", ""))
                                elif isinstance(c, str):
                                    text_parts.append(c)
            text = "".join(text_parts)
            tokens_in = usage.get("input_tokens")
            tokens_out = usage.get("output_tokens")

        if not text.strip():
            raise KieError(
                code="empty_response",
                message="Empty response text from KIE",
                retryable=True,
                api_key=self.api_key,
            )

        return KieResult(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            credits=credits_val,
            model=model,
        )
