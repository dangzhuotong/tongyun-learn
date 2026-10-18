import hashlib
import json
from typing import Annotated

import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tongyun_learn.ai.kie import KieClient
from tongyun_learn.ai.service import get_kie_client
from tongyun_learn.auth import Principal, get_principal
from tongyun_learn.config import get_settings
from tongyun_learn.db import SessionLocal
from tongyun_learn.errors import ApiError
from tongyun_learn.limits import (
    ai_calls_today,
    bump_ai_calls,
    bump_requests,
    check_ai_cap,
    reset_rate_limiter,
)
from tongyun_learn.main import create_app
from tongyun_learn.models import ApiUsage

WEB_TOKEN = "web-test-token"
WEB_SHA256 = hashlib.sha256(WEB_TOKEN.encode()).hexdigest()


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_TOKEN_WEB_SHA256", WEB_SHA256)
    monkeypatch.setenv("KIE_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_rate_limiter()
    with SessionLocal() as db:
        db.query(ApiUsage).delete()
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(ApiUsage).delete()
        db.commit()
    get_settings.cache_clear()
    reset_rate_limiter()


def test_rate_limiting_429(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_RATE_WEB_PER_MIN", "3")
    get_settings.cache_clear()
    reset_rate_limiter()

    app = create_app()

    @app.get("/test/ping")
    def ping(p: Annotated[Principal, Depends(get_principal)]):
        return {"pong": True}

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {WEB_TOKEN}"}
        # 3 requests within limit
        r1 = client.get("/test/ping", headers=headers)
        assert r1.status_code == 200
        r2 = client.get("/test/ping", headers=headers)
        assert r2.status_code == 200
        r3 = client.get("/test/ping", headers=headers)
        assert r3.status_code == 200

        # 4th request -> 429
        r4 = client.get("/test/ping", headers=headers)
        assert r4.status_code == 429
        assert "Retry-After" in r4.headers
        assert int(r4.headers["Retry-After"]) >= 1
        data = r4.json()
        assert data["error"]["code"] == "rate_limited"
        assert "请求太频繁" in data["error"]["message"]


def test_bump_and_check_daily_cap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_AI_DAILY_WEB", "2")
    get_settings.cache_clear()

    db: Session = SessionLocal()
    try:
        # Initial calls
        assert ai_calls_today(db, "web") == 0
        bump_requests(db, "web")
        bump_requests(db, "web")
        bump_ai_calls(db, "web")
        assert ai_calls_today(db, "web") == 1

        check_ai_cap(db, "web")

        bump_ai_calls(db, "web")
        assert ai_calls_today(db, "web") == 2

        with pytest.raises(ApiError) as exc_info:
            check_ai_cap(db, "web")
        assert exc_info.value.status_code == 429
        assert exc_info.value.code == "ai_daily_cap"
        assert exc_info.value.headers is not None
        assert "Retry-After" in exc_info.value.headers
    finally:
        db.close()


def test_daily_cap_integration(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_AI_DAILY_WEB", "1")
    get_settings.cache_clear()
    reset_rate_limiter()

    with SessionLocal() as db:
        db.query(ApiUsage).filter(ApiUsage.token_name == "web").delete()
        db.commit()

    content_dict = {
        "word": "abandon",
        "phonetic": "/əˈbændən/",
        "meanings": [{"pos": "v.", "cn": "放弃"}],
        "examples": [
            {"en": "They abandoned the plan.", "zh": "他们放弃了计划。"},
            {"en": "Do not abandon hope.", "zh": "不要放弃希望。"},
        ],
        "roots": [],
        "etymology": "古法语",
        "mnemonic": "放弃口诀",
        "related": [],
    }
    valid_response = {
        "choices": [{"message": {"content": json.dumps(content_dict)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }

    call_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=valid_response)

    mock_client = KieClient(
        base_url="https://api.kie.ai",
        api_key="test-key",
        timeout_s=30.0,
        transport=httpx.MockTransport(mock_handler),
    )

    app = create_app()
    app.dependency_overrides[get_kie_client] = lambda: mock_client

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {WEB_TOKEN}"}

        # 1. First explain call -> 200, cached=False
        r1 = client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "abandon"}},
        )
        assert r1.status_code == 200
        assert r1.json()["cached"] is False
        assert call_count == 1

        # 2. Second call with DIFFERENT input -> 429 ai_daily_cap
        r2 = client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "ability"}},
        )
        assert r2.status_code == 429
        assert r2.json()["error"]["code"] == "ai_daily_cap"
        assert "Retry-After" in r2.headers
        assert call_count == 1

        # 3. Repeat FIRST input (cache hit) -> 200, cached=True, transport unchanged
        r3 = client.post(
            "/v1/ai/explain",
            headers=headers,
            json={"kind": "word_mnemonic", "input": {"word": "abandon"}},
        )
        assert r3.status_code == 200
        assert r3.json()["cached"] is True
        assert call_count == 1

        with SessionLocal() as db:
            calls = ai_calls_today(db, "web")
            assert calls == 1
