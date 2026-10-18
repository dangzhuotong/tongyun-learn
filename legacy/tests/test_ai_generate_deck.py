import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from tongyun_learn.ai.kie import KieClient
from tongyun_learn.ai.schemas import validate
from tongyun_learn.ai.service import get_kie_client
from tongyun_learn.config import get_settings
from tongyun_learn.db import SessionLocal
from tongyun_learn.limits import reset_rate_limiter
from tongyun_learn.main import create_app
from tongyun_learn.models import AiCache, ApiUsage, Card, Deck

WEB_TOKEN = "web-test-token"
WEB_SHA256 = hashlib.sha256(WEB_TOKEN.encode()).hexdigest()

SAMPLE_WORDS = [
    {
        "word": "concurrency",
        "phonetic": "/kənˈkɜːrənsi/",
        "cn": "并发",
        "example": "Concurrency is a property of systems.",
        "example_cn": "并发是系统的特性。",
    },
    {
        "word": "throughput",
        "phonetic": "/ˈθruːpʊt/",
        "cn": "吞吐量",
        "example": "High throughput is desirable.",
        "example_cn": "高吞吐量是理想的。",
    },
]

SAMPLE_GENERATE_DECK_JSON = {"words": SAMPLE_WORDS}


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_TOKEN_WEB_SHA256", WEB_SHA256)
    monkeypatch.setenv("KIE_API_KEY", "test-key")
    monkeypatch.setenv("LEARN_AI_MODEL", "gemini-3-8-flash-openai")
    monkeypatch.setenv("LEARN_AI_FALLBACK_MODEL", "deepseek-v4-1-flash")
    get_settings.cache_clear()
    reset_rate_limiter()

    with SessionLocal() as db:
        db.query(Card).delete()
        db.query(Deck).delete()
        db.query(AiCache).delete()
        db.query(ApiUsage).delete()
        db.commit()

    yield

    with SessionLocal() as db:
        db.query(Card).delete()
        db.query(Deck).delete()
        db.query(AiCache).delete()
        db.query(ApiUsage).delete()
        db.commit()
    get_settings.cache_clear()
    reset_rate_limiter()


def test_generate_deck_success_200():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {
            "choices": [{"message": {"content": json.dumps(SAMPLE_GENERATE_DECK_JSON)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 40},
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
        res = test_client.post(
            "/v1/ai/generate-deck",
            headers=headers,
            json={"scenario": "后端技术面试", "n": 2},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["cached"] is False
        assert data["added"] == 2
        assert data["skipped"] == 0
        assert data["model"] == "gemini-3-8-flash-openai"
        assert len(data["words"]) == 2

        deck = data["deck"]
        assert deck["kind"] == "en_word"
        assert deck["source"] == "ai"
        assert deck["subject_id"] is None
        assert deck["name"] == "AI·后端技术面试"

        with SessionLocal() as db:
            cards = db.query(Card).filter(Card.deck_id == deck["id"]).all()
            assert len(cards) == 2
            fronts = {c.front for c in cards}
            assert fronts == {"concurrency", "throughput"}
            for c in cards:
                assert c.card_type == "memory"
                assert c.created_by == "ai"
                assert c.payload.get("scenario") == "后端技术面试"
                assert "phonetic" in c.payload


def test_generate_deck_caching_and_no_duplicate_cards():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {
            "choices": [{"message": {"content": json.dumps(SAMPLE_GENERATE_DECK_JSON)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 40},
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

        # 1. First call -> generates, adds 2 cards, cached=False
        r1 = test_client.post(
            "/v1/ai/generate-deck",
            headers=headers,
            json={"scenario": "后端技术面试", "n": 2},
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["cached"] is False
        assert d1["added"] == 2
        assert d1["skipped"] == 0
        assert len(calls) == 1

        # 2. Second call with extra whitespaces -> hits cache, adds 0 cards, skips 2
        r2 = test_client.post(
            "/v1/ai/generate-deck",
            headers=headers,
            json={"scenario": "  后端技术面试  ", "n": 2},
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["cached"] is True
        assert d2["added"] == 0
        assert d2["skipped"] == 2
        assert len(calls) == 1

        # Verify DB card count is still exactly 2
        with SessionLocal() as db:
            assert db.query(Card).count() == 2


def test_generate_deck_n_bounds_422(client: TestClient):
    headers = {"Authorization": f"Bearer {WEB_TOKEN}"}

    # n < 1
    r_zero = client.post(
        "/v1/ai/generate-deck",
        headers=headers,
        json={"scenario": "后端面试", "n": 0},
    )
    assert r_zero.status_code == 422
    assert r_zero.json()["error"]["code"] == "validation_error"

    # n > 50
    r_51 = client.post(
        "/v1/ai/generate-deck",
        headers=headers,
        json={"scenario": "后端面试", "n": 51},
    )
    assert r_51.status_code == 422
    assert r_51.json()["error"]["code"] == "validation_error"


def test_generate_deck_scenario_length_422(client: TestClient):
    headers = {"Authorization": f"Bearer {WEB_TOKEN}"}

    # scenario empty
    r_empty = client.post(
        "/v1/ai/generate-deck",
        headers=headers,
        json={"scenario": ""},
    )
    assert r_empty.status_code == 422
    assert r_empty.json()["error"]["code"] == "validation_error"

    # scenario 1 char
    r_one = client.post(
        "/v1/ai/generate-deck",
        headers=headers,
        json={"scenario": "a"},
    )
    assert r_one.status_code == 422
    assert r_one.json()["error"]["code"] == "validation_error"

    # scenario whitespace only
    r_spaces = client.post(
        "/v1/ai/generate-deck",
        headers=headers,
        json={"scenario": "    "},
    )
    assert r_spaces.status_code == 422
    assert r_spaces.json()["error"]["code"] == "validation_error"

    # scenario whitespace around 1 char
    r_space_one = client.post(
        "/v1/ai/generate-deck",
        headers=headers,
        json={"scenario": "  a  "},
    )
    assert r_space_one.status_code == 422
    assert r_space_one.json()["error"]["code"] == "validation_error"

    # scenario too long (> 200 chars)
    r_too_long = client.post(
        "/v1/ai/generate-deck",
        headers=headers,
        json={"scenario": "字" * 201},
    )
    assert r_too_long.status_code == 422
    assert r_too_long.json()["error"]["code"] == "validation_error"


def test_generate_deck_repair_retry_success():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            # First attempt returns invalid output (e.g. invalid json or missing word letter)
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": '{"words":[{"word":"123","cn":"数字"}]}'}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10},
                },
            )
        # Second attempt returns repaired valid json
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(SAMPLE_GENERATE_DECK_JSON)}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 30},
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
            "/v1/ai/generate-deck",
            headers=headers,
            json={"scenario": "系统设计", "n": 2},
        )
        assert res.status_code == 200
        assert res.json()["cached"] is False
        assert res.json()["added"] == 2
        assert len(calls) == 2


def test_generate_deck_unconfigured_kie_503(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    monkeypatch.setenv("KIE_API_KEY", "")
    get_settings.cache_clear()

    headers = {"Authorization": f"Bearer {WEB_TOKEN}"}
    res = client.post(
        "/v1/ai/generate-deck",
        headers=headers,
        json={"scenario": "外企技术面试", "n": 10},
    )
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "ai_not_configured"


def test_generate_deck_daily_cap_429(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_AI_DAILY_WEB", "1")
    get_settings.cache_clear()

    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {
            "choices": [{"message": {"content": json.dumps(SAMPLE_GENERATE_DECK_JSON)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
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

        # 1. First call -> 200, consumes cap
        r1 = test_client.post(
            "/v1/ai/generate-deck",
            headers=headers,
            json={"scenario": "场景一", "n": 2},
        )
        assert r1.status_code == 200
        assert r1.json()["cached"] is False

        # 2. Second call with different scenario -> 429 ai_daily_cap
        r2 = test_client.post(
            "/v1/ai/generate-deck",
            headers=headers,
            json={"scenario": "场景二", "n": 2},
        )
        assert r2.status_code == 429
        assert r2.json()["error"]["code"] == "ai_daily_cap"
        assert "Retry-After" in r2.headers

        # 3. Third call with scenario one -> hits cache -> 200
        r3 = test_client.post(
            "/v1/ai/generate-deck",
            headers=headers,
            json={"scenario": "场景一", "n": 2},
        )
        assert r3.status_code == 200
        assert r3.json()["cached"] is True


def test_generate_deck_unauthorized_401(client: TestClient):
    # Missing token -> 401
    r_no_token = client.post("/v1/ai/generate-deck", json={"scenario": "技术面试"})
    assert r_no_token.status_code == 401
    assert r_no_token.json()["error"]["code"] == "unauthorized"

    # Wrong token -> 401
    r_bad_token = client.post(
        "/v1/ai/generate-deck",
        headers={"Authorization": "Bearer wrong-token"},
        json={"scenario": "技术面试"},
    )
    assert r_bad_token.status_code == 401
    assert r_bad_token.json()["error"]["code"] == "unauthorized"


def test_generate_deck_custom_name_and_truncation():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {
            "choices": [{"message": {"content": json.dumps(SAMPLE_GENERATE_DECK_JSON)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
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

        # 1. Custom deck_name
        r1 = test_client.post(
            "/v1/ai/generate-deck",
            headers=headers,
            json={"scenario": "技术面试", "n": 2, "deck_name": "自定义单词本"},
        )
        assert r1.status_code == 200
        assert r1.json()["deck"]["name"] == "自定义单词本"

        # 2. Long scenario default truncated to 64 chars
        long_scenario = "长场景" * 40
        r2 = test_client.post(
            "/v1/ai/generate-deck",
            headers=headers,
            json={"scenario": long_scenario, "n": 2},
        )
        assert r2.status_code == 200
        assert r2.json()["deck"]["name"] == f"AI·{long_scenario}"[:64]
        assert len(r2.json()["deck"]["name"]) == 64


def test_word_deck_schema_validation_rules():
    # Valid
    assert validate("word_deck", SAMPLE_GENERATE_DECK_JSON, {"scenario": "test", "n": 2}) == []

    # Exceeding n
    assert any("数量必须在" in e for e in validate("word_deck", SAMPLE_GENERATE_DECK_JSON, {"n": 1}))

    # Word without letters
    bad_word = {"words": [{"word": "12345", "cn": "数字"}]}
    assert any("必须包含英文字母" in e for e in validate("word_deck", bad_word, {"n": 2}))

    # Empty cn
    bad_cn = {"words": [{"word": "word", "cn": "  "}]}
    assert any("cn 释义不能为空" in e for e in validate("word_deck", bad_cn, {"n": 2}))

    # Word too long
    bad_len = {"words": [{"word": "a" * 65, "cn": "很长"}]}
    assert any("长度必须在" in e for e in validate("word_deck", bad_len, {"n": 2}))
