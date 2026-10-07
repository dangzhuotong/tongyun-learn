import hashlib
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from tongyun_learn.ai.kie import KieClient
from tongyun_learn.ai.service import get_kie_client
from tongyun_learn.config import get_settings
from tongyun_learn.db import SessionLocal
from tongyun_learn.limits import reset_rate_limiter
from tongyun_learn.main import create_app
from tongyun_learn.models import AiCache, ApiUsage

WEB_TOKEN = "web-test-token"
WEB_SHA256 = hashlib.sha256(WEB_TOKEN.encode()).hexdigest()

SAMPLE_WORD_JSON = {
    "word": "abandon",
    "phonetic": "/əˈbændən/",
    "meanings": [{"pos": "v.", "cn": "放弃"}],
    "examples": [
        {"en": "They had to abandon the burning car.", "zh": "他们不得不弃车离开。"},
        {"en": "He abandoned the project due to lack of time.", "zh": "由于缺乏时间，他放弃了该项目。"},
    ],
    "roots": [{"part": "a-", "type": "prefix", "meaning": "加强"}],
    "etymology": "古法语",
    "mnemonic": "一个胖墩放弃了",
    "related": [{"word": "ban", "cn": "禁止"}],
}

SAMPLE_SENTENCE_JSON = {
    "sentence": "The database optimizes queries that execute frequently.",
    "translation": "数据库优化频繁执行的查询。",
    "structure": [
        {"text": "The database", "role": "主语", "explain": "主语"},
        {"text": "optimizes", "role": "谓语", "explain": "谓语动词"},
    ],
    "grammar_points": [{"name": "定语从句", "explain": "that引导"}],
    "key_words": [{"word": "optimize", "pos": "v.", "cn": "优化", "note": ""}],
    "difficulty": "medium",
}


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_TOKEN_WEB_SHA256", WEB_SHA256)
    monkeypatch.setenv("KIE_API_KEY", "test-key")
    monkeypatch.setenv("LEARN_AI_MODEL", "gemini-3-8-flash-openai")
    monkeypatch.setenv("LEARN_AI_FALLBACK_MODEL", "deepseek-v4-1-flash")
    get_settings.cache_clear()
    reset_rate_limiter()

    with SessionLocal() as db:
        db.query(AiCache).delete()
        db.query(ApiUsage).delete()
        db.commit()

    yield

    with SessionLocal() as db:
        db.query(AiCache).delete()
        db.query(ApiUsage).delete()
        db.commit()
    get_settings.cache_clear()
    reset_rate_limiter()


def test_validation_errors(client: TestClient):
    headers = {"Authorization": f"Bearer {WEB_TOKEN}"}

    # 1. Unknown kind -> 422
    r1 = client.post(
        "/v1/ai/explain",
        headers=headers,
        json={"kind": "unknown_kind", "input": {"word": "test"}},
    )
    assert r1.status_code == 422
    assert r1.json()["error"]["code"] == "validation_error"

    # 2. word "" -> 422
    r2 = client.post(
        "/v1/ai/explain",
        headers=headers,
        json={"kind": "word_mnemonic", "input": {"word": ""}},
    )
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "validation_error"

    # 3. sentence too long -> 422
    r3 = client.post(
        "/v1/ai/explain",
        headers=headers,
        json={"kind": "sentence_grammar", "input": {"sentence": "a" * 1001}},
    )
    assert r3.status_code == 422
    assert r3.json()["error"]["code"] == "validation_error"


def test_explain_happy_path_both_kinds_and_caching():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        req_data = json.loads(request.content)
        messages = req_data.get("messages", [])
        user_content = messages[-1]["content"] if messages else ""
        if "单词：" in user_content:
            body = {
                "choices": [{"message": {"content": json.dumps(SAMPLE_WORD_JSON)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            }
        else:
            body = {
                "choices": [{"message": {"content": json.dumps(SAMPLE_SENTENCE_JSON)}}],
                "usage": {"prompt_tokens": 15, "completion_tokens": 30},
            }
        return httpx.Response(200, json=body)

    mock_client = KieClient(
        base_url="https://api.kie.ai",
        api_key="test-key",
        timeout_s=30.0,
        transport=httpx.MockTransport(mock_handler),
    )

    app = create_app()
    app.dependency_overrides[get_kie_client] = lambda: mock_client

    with TestClient(app) as test_client:
        headers = {"Authorization": f"Bearer {WEB_TOKEN}"}

        # 1. word_mnemonic happy path
        res_w = test_client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "abandon", "context": "放弃"}},
        )
        assert res_w.status_code == 200
        w_data = res_w.json()
        assert w_data["cached"] is False
        assert w_data["model"] == "gemini-3-8-flash-openai"
        assert w_data["content"]["word"] == "abandon"
        assert len(calls) == 1

        # Second identical call -> cached: True, call count unchanged
        res_w2 = test_client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "abandon", "context": "放弃"}},
        )
        assert res_w2.status_code == 200
        assert res_w2.json()["cached"] is True
        assert len(calls) == 1

        # 2. sentence_grammar happy path
        res_s = test_client.post(
            "/v1/ai/explain",
            headers=headers,
            json={
                "kind": "sentence_grammar",
                "input": {"sentence": "The database optimizes queries that execute frequently."},
            },
        )
        assert res_s.status_code == 200
        s_data = res_s.json()
        assert s_data["cached"] is False
        assert s_data["content"]["sentence"] == "The database optimizes queries that execute frequently."
        assert len(calls) == 2

        # Second identical sentence call -> cached: True
        res_s2 = test_client.post(
            "/v1/ai/explain",
            headers=headers,
            json={
                "kind": "sentence_grammar",
                "input": {"sentence": "The database optimizes queries that execute frequently."},
            },
        )
        assert res_s2.status_code == 200
        assert res_s2.json()["cached"] is True
        assert len(calls) == 2


def test_fallback_on_code_402():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "/gemini-3-8-flash-openai/" in request.url.path:
            return httpx.Response(200, json={"code": 402, "msg": "insufficient credits"})
        else:
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": json.dumps(SAMPLE_WORD_JSON)}],
                        }
                    ],
                    "usage": {"input_tokens": 12, "output_tokens": 24},
                },
            )

    mock_client = KieClient(
        base_url="https://api.kie.ai",
        api_key="test-key",
        timeout_s=30.0,
        transport=httpx.MockTransport(mock_handler),
    )

    app = create_app()
    app.dependency_overrides[get_kie_client] = lambda: mock_client

    with TestClient(app) as test_client:
        headers = {"Authorization": f"Bearer {WEB_TOKEN}"}
        res = test_client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "abandon"}},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["model"] == "deepseek-v4-1-flash"
        assert len(calls) == 2


def test_retry_on_invalid_json():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "not valid json here"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 5},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(SAMPLE_WORD_JSON)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )

    mock_client = KieClient(
        base_url="https://api.kie.ai",
        api_key="test-key",
        timeout_s=30.0,
        transport=httpx.MockTransport(mock_handler),
    )

    app = create_app()
    app.dependency_overrides[get_kie_client] = lambda: mock_client

    with TestClient(app) as test_client:
        headers = {"Authorization": f"Bearer {WEB_TOKEN}"}
        res = test_client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "abandon"}},
        )
        assert res.status_code == 200
        assert len(calls) == 2


def test_invalid_twice_primary_and_fallback_returns_502_ai_bad_output():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "/gemini-3-8-flash-openai/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "bad json"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 5},
                },
            )
        else:
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "bad json fallback"}],
                        }
                    ],
                    "usage": {"input_tokens": 5, "output_tokens": 5},
                },
            )

    mock_client = KieClient(
        base_url="https://api.kie.ai",
        api_key="test-key",
        timeout_s=30.0,
        transport=httpx.MockTransport(mock_handler),
    )

    app = create_app()
    app.dependency_overrides[get_kie_client] = lambda: mock_client

    with TestClient(app) as test_client:
        headers = {"Authorization": f"Bearer {WEB_TOKEN}"}
        res = test_client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "abandon"}},
        )
        assert res.status_code == 502
        data = res.json()
        assert data["error"]["code"] == "ai_bad_output"
        assert len(calls) == 4


def test_timeout_on_both_returns_502_ai_unavailable():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("timed out")

    mock_client = KieClient(
        base_url="https://api.kie.ai",
        api_key="test-key",
        timeout_s=30.0,
        transport=httpx.MockTransport(mock_handler),
    )

    app = create_app()
    app.dependency_overrides[get_kie_client] = lambda: mock_client

    with TestClient(app) as test_client:
        headers = {"Authorization": f"Bearer {WEB_TOKEN}"}
        res = test_client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "abandon"}},
        )
        assert res.status_code == 502
        assert res.json()["error"]["code"] == "ai_unavailable"
        assert len(calls) == 2


def test_kie_api_key_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KIE_API_KEY", "")
    get_settings.cache_clear()

    app = create_app()

    with TestClient(app) as test_client:
        headers = {"Authorization": f"Bearer {WEB_TOKEN}"}

        # 1. No cache -> 503 ai_not_configured
        res = test_client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "abandon"}},
        )
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "ai_not_configured"

        # 2. Populate cache in DB
        from tongyun_learn.ai.service import cache_key, canonical_input

        ckey = cache_key(
            "word_mnemonic",
            "gemini-3-8-flash-openai",
            "w1",
            canonical_input("word_mnemonic", {"word": "abandon"}),
        )
        with SessionLocal() as db:
            db.add(
                AiCache(
                    cache_key=ckey,
                    kind="word_mnemonic",
                    model="gemini-3-8-flash-openai",
                    prompt_ver="w1",
                    content=SAMPLE_WORD_JSON,
                )
            )
            db.commit()

        # 3. With cache present -> 200 cached
        res2 = test_client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "abandon"}},
        )
        assert res2.status_code == 200
        assert res2.json()["cached"] is True


def test_tiny_budget_fails_quickly(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_AI_TOTAL_BUDGET_S", "0.01")
    get_settings.cache_clear()

    def slow_handler(request: httpx.Request) -> httpx.Response:
        time.sleep(0.05)
        return httpx.Response(200, json={})

    mock_client = KieClient(
        base_url="https://api.kie.ai",
        api_key="test-key",
        timeout_s=30.0,
        transport=httpx.MockTransport(slow_handler),
    )

    app = create_app()
    app.dependency_overrides[get_kie_client] = lambda: mock_client

    with TestClient(app) as test_client:
        headers = {"Authorization": f"Bearer {WEB_TOKEN}"}
        res = test_client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "abandon"}},
        )
        assert res.status_code == 502
        assert res.json()["error"]["code"] == "ai_unavailable"
