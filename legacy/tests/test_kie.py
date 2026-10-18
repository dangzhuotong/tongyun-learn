import asyncio

import httpx
import pytest

from tongyun_learn.ai.kie import KieClient, KieError, parse_json_text


def test_parse_json_text_fenced():
    raw = """Here is the result:
```json
{
  "word": "abandon",
  "phonetic": "/əˈbændən/"
}
```
Hope this is helpful!"""
    parsed = parse_json_text(raw)
    assert parsed["word"] == "abandon"
    assert parsed["phonetic"] == "/əˈbændən/"


def test_parse_json_text_no_fences():
    raw = '{"word": "abandon", "nested": {"a": 1}}'
    parsed = parse_json_text(raw)
    assert parsed["word"] == "abandon"
    assert parsed["nested"]["a"] == 1


def test_parse_json_text_invalid():
    with pytest.raises(ValueError):
        parse_json_text("Not a json string at all")

    with pytest.raises(ValueError):
        parse_json_text("[1, 2, 3]")


def test_responses_api_text_extraction():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/openai/v1/responses"
        assert request.headers["Authorization"] == "Bearer secret-api-key"
        body = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": '{"result": '},
                        {"type": "output_text", "text": '"ok"}'},
                    ],
                }
            ],
            "usage": {"input_tokens": 15, "output_tokens": 25},
            "credits_consumed": 0.05,
        }
        return httpx.Response(200, json=body)

    client = KieClient(
        base_url="https://api.kie.ai",
        api_key="secret-api-key",
        timeout_s=10.0,
        transport=httpx.MockTransport(mock_handler),
    )

    result = asyncio.run(
        client.complete(
            model="deepseek-v4-1-flash",
            messages=[{"role": "user", "content": "hello"}],
        )
    )
    assert result.text == '{"result": "ok"}'
    assert result.tokens_in == 15
    assert result.tokens_out == 25
    assert result.credits == 0.05
    assert result.model == "deepseek-v4-1-flash"


def test_chat_completions_extraction():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/gemini-3-8-flash-openai/v1/chat/completions"
        body = {
            "choices": [
                {
                    "message": {
                        "content": '{"chat": "success"}',
                    }
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 10},
            "credits_consumed": 0.01,
        }
        return httpx.Response(200, json=body)

    client = KieClient(
        base_url="https://api.kie.ai",
        api_key="secret-api-key",
        timeout_s=10.0,
        transport=httpx.MockTransport(mock_handler),
    )

    result = asyncio.run(
        client.complete(
            model="gemini-3-8-flash-openai",
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result.text == '{"chat": "success"}'
    assert result.tokens_in == 5
    assert result.tokens_out == 10


def test_api_key_not_in_kie_error_str():
    secret_key = "super-secret-api-key-987"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"code": "invalid_api_key", "message": f"Invalid key {secret_key}"}},
        )

    client = KieClient(
        base_url="https://api.kie.ai",
        api_key=secret_key,
        timeout_s=5.0,
        transport=httpx.MockTransport(mock_handler),
    )

    with pytest.raises(KieError) as exc_info:
        asyncio.run(
            client.complete(
                model="gemini-3-8-flash-openai",
                messages=[{"role": "user", "content": "test"}],
            )
        )

    err_str = str(exc_info.value)
    assert secret_key not in err_str
    assert "[REDACTED]" in err_str
