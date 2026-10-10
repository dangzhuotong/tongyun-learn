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
from tongyun_learn.limits import ai_calls_today, reset_rate_limiter
from tongyun_learn.main import create_app
from tongyun_learn.models import AiCache, ApiUsage

WEB_TOKEN = "web-test-token"
WEB_SHA256 = hashlib.sha256(WEB_TOKEN.encode()).hexdigest()

SAMPLE_QUIZ_JSON = {
    "questions": [
        {
            "type": "cloze",
            "word": "abandon",
            "stem": "The crew had to ___ the sinking ship.",
            "options": [],
            "answer": "abandon",
            "explain": "根据语境，船员不得不弃船，填 abandon。",
        },
        {
            "type": "choice",
            "word": "ability",
            "stem": "He has demonstrated a great ___ to solve complex problems.",
            "options": ["ability", "abandon", "absence", "abroad"],
            "answer": "ability",
            "explain": "ability 表示能力，符合语境。",
        },
    ]
}

SAMPLE_SINGLE_WORD_QUIZ_JSON = {
    "questions": [
        {
            "type": "cloze",
            "word": "abandon",
            "stem": "They had to ___ their car in the heavy snow.",
            "options": [],
            "answer": "abandon",
            "explain": "abandon 表示在暴雪中弃车离开。",
        },
        {
            "type": "choice",
            "word": "abandon",
            "stem": "Which word is closest in meaning to 'abandon'?",
            "options": ["give up", "continue", "maintain", "protect"],
            "answer": "give up",
            "explain": "abandon 意为放弃，同义短语为 give up。",
        },
    ]
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


def test_quiz_happy_path_200():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {
            "choices": [{"message": {"content": json.dumps(SAMPLE_SINGLE_WORD_QUIZ_JSON)}}],
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
        res = test_client.post(
            "/v1/ai/quiz",
            headers=headers,
            json={"words": [{"word": "abandon", "cn": "放弃"}]},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["kind"] == "word_quiz"
        assert data["cached"] is False
        assert data["model"] == "gemini-3-8-flash-openai"
        assert data["prompt_ver"] == "q1"
        assert len(data["content"]["questions"]) == 2
        assert len(calls) == 1


def test_quiz_caching_and_order_insensitivity():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {
            "choices": [{"message": {"content": json.dumps(SAMPLE_QUIZ_JSON)}}],
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

        # 1. First call with [abandon, ability]
        r1 = test_client.post(
            "/v1/ai/quiz",
            headers=headers,
            json={"words": [{"word": "abandon", "cn": "放弃"}, {"word": "ability", "cn": "能力"}]},
        )
        assert r1.status_code == 200
        assert r1.json()["cached"] is False
        assert len(calls) == 1

        # 2. Second call with reverse order [ability, abandon]
        r2 = test_client.post(
            "/v1/ai/quiz",
            headers=headers,
            json={"words": [{"word": "ability", "cn": "能力"}, {"word": "abandon", "cn": "放弃"}]},
        )
        assert r2.status_code == 200
        assert r2.json()["cached"] is True
        assert len(calls) == 1


def test_quiz_retry_on_bad_json_then_success():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "not valid json"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 5},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(SAMPLE_SINGLE_WORD_QUIZ_JSON)}}],
                "usage": {"prompt_tokens": 15, "completion_tokens": 30},
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
            "/v1/ai/quiz",
            headers=headers,
            json={"words": [{"word": "abandon"}]},
        )
        assert res.status_code == 200
        assert res.json()["cached"] is False
        assert len(calls) == 2

        # Verify cached afterwards
        res_cached = test_client.post(
            "/v1/ai/quiz",
            headers=headers,
            json={"words": [{"word": "abandon"}]},
        )
        assert res_cached.status_code == 200
        assert res_cached.json()["cached"] is True
        assert len(calls) == 2


def test_quiz_bad_json_twice_returns_502_not_cached():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "/gemini-3-8-flash-openai/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "still bad json"}}],
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
                            "content": [{"type": "output_text", "text": "still bad json fallback"}],
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
            "/v1/ai/quiz",
            headers=headers,
            json={"words": [{"word": "abandon"}]},
        )
        assert res.status_code == 502
        data = res.json()
        assert data["error"]["code"] == "ai_bad_output"

        with SessionLocal() as db:
            assert db.query(AiCache).count() == 0


def test_quiz_validation_errors(client: TestClient):
    headers = {"Authorization": f"Bearer {WEB_TOKEN}"}

    # 1. 0 words -> 422
    r_empty = client.post("/v1/ai/quiz", headers=headers, json={"words": []})
    assert r_empty.status_code == 422
    assert r_empty.json()["error"]["code"] == "validation_error"

    # 2. 21 words -> 422
    twenty_one = [{"word": f"word{i}"} for i in range(21)]
    r_21 = client.post("/v1/ai/quiz", headers=headers, json={"words": twenty_one})
    assert r_21.status_code == 422
    assert r_21.json()["error"]["code"] == "validation_error"

    # 3. word without English letter -> 422
    r_no_letter = client.post("/v1/ai/quiz", headers=headers, json={"words": [{"word": "12345"}]})
    assert r_no_letter.status_code == 422
    assert r_no_letter.json()["error"]["code"] == "validation_error"

    # 4. word empty string -> 422
    r_blank = client.post("/v1/ai/quiz", headers=headers, json={"words": [{"word": ""}]})
    assert r_blank.status_code == 422
    assert r_blank.json()["error"]["code"] == "validation_error"

    # 5. word too long (> 64 chars) -> 422
    r_long_word = client.post("/v1/ai/quiz", headers=headers, json={"words": [{"word": "a" * 65}]})
    assert r_long_word.status_code == 422
    assert r_long_word.json()["error"]["code"] == "validation_error"

    # 6. cn too long (> 100 chars) -> 422
    r_long_cn = client.post(
        "/v1/ai/quiz",
        headers=headers,
        json={"words": [{"word": "abandon", "cn": "放弃" * 51}]},
    )
    assert r_long_cn.status_code == 422
    assert r_long_cn.json()["error"]["code"] == "validation_error"


def test_quiz_unauthorized_401(client: TestClient):
    # Missing token -> 401
    r_no_token = client.post("/v1/ai/quiz", json={"words": [{"word": "abandon"}]})
    assert r_no_token.status_code == 401
    assert r_no_token.json()["error"]["code"] == "unauthorized"

    # Invalid token -> 401
    r_bad_token = client.post(
        "/v1/ai/quiz",
        headers={"Authorization": "Bearer wrong-token"},
        json={"words": [{"word": "abandon"}]},
    )
    assert r_bad_token.status_code == 401
    assert r_bad_token.json()["error"]["code"] == "unauthorized"


def test_quiz_api_usage_and_daily_cap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_AI_DAILY_WEB", "1")
    get_settings.cache_clear()

    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {
            "choices": [{"message": {"content": json.dumps(SAMPLE_SINGLE_WORD_QUIZ_JSON)}}],
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

        # 1. First call -> 200, cached=False, calls=1
        r1 = test_client.post(
            "/v1/ai/quiz",
            headers=headers,
            json={"words": [{"word": "abandon"}]},
        )
        assert r1.status_code == 200
        assert r1.json()["cached"] is False
        assert len(calls) == 1

        with SessionLocal() as db:
            assert ai_calls_today(db, "web") == 1

        # 2. Second call with different word -> 429 ai_daily_cap
        r2 = test_client.post(
            "/v1/ai/quiz",
            headers=headers,
            json={"words": [{"word": "ability"}]},
        )
        assert r2.status_code == 429
        assert r2.json()["error"]["code"] == "ai_daily_cap"
        assert "Retry-After" in r2.headers
        assert len(calls) == 1

        # 3. Third call repeats first words (cache hit) -> 200, cached=True
        r3 = test_client.post(
            "/v1/ai/quiz",
            headers=headers,
            json={"words": [{"word": "abandon"}]},
        )
        assert r3.status_code == 200
        assert r3.json()["cached"] is True
        assert len(calls) == 1

        with SessionLocal() as db:
            assert ai_calls_today(db, "web") == 1


def test_quiz_deduplication():
    calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {
            "choices": [{"message": {"content": json.dumps(SAMPLE_SINGLE_WORD_QUIZ_JSON)}}],
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

        # Send duplicates
        r1 = test_client.post(
            "/v1/ai/quiz",
            headers=headers,
            json={"words": [{"word": "abandon", "cn": "放弃"}, {"word": "abandon", "cn": "抛弃"}]},
        )
        assert r1.status_code == 200
        assert r1.json()["cached"] is False
        assert len(calls) == 1

        # Calling with single word hits the exact same cache
        r2 = test_client.post(
            "/v1/ai/quiz",
            headers=headers,
            json={"words": [{"word": "abandon", "cn": "放弃"}]},
        )
        assert r2.status_code == 200
        assert r2.json()["cached"] is True
        assert len(calls) == 1


def test_word_quiz_schema_validation_rules():
    # 1. Valid quiz
    errs = validate("word_quiz", SAMPLE_QUIZ_JSON, {"words": [{"word": "abandon"}, {"word": "ability"}]})
    assert errs == []

    # 2. Choice with != 4 options
    bad_options_quiz = {
        "questions": [
            {
                "type": "choice",
                "word": "abandon",
                "stem": "Stem",
                "options": ["A", "B", "C"],
                "answer": "A",
                "explain": "Exp",
            }
        ]
    }
    errs_opt = validate("word_quiz", bad_options_quiz, {"words": [{"word": "abandon"}]})
    assert any("4 个选项" in e for e in errs_opt)

    # 3. Choice where answer not in options
    bad_answer_quiz = {
        "questions": [
            {
                "type": "choice",
                "word": "abandon",
                "stem": "Stem",
                "options": ["A", "B", "C", "D"],
                "answer": "E",
                "explain": "Exp",
            }
        ]
    }
    errs_ans = validate("word_quiz", bad_answer_quiz, {"words": [{"word": "abandon"}]})
    assert any("answer" in e for e in errs_ans)

    # 4. Missing an input word
    errs_missing = validate(
        "word_quiz",
        SAMPLE_SINGLE_WORD_QUIZ_JSON,
        {"words": [{"word": "abandon"}, {"word": "missing_word"}]},
    )
    assert any("missing_word" in e for e in errs_missing)


def _q(stem: str) -> dict:
    return {
        "type": "cloze",
        "word": "abandon",
        "stem": stem,
        "options": [],
        "answer": "abandon",
        "explain": "放弃",
    }


def test_word_quiz_validate_cloze_leak_and_too_many():
    from tongyun_learn.ai.schemas import validate

    inp = {"words": [{"word": "abandon"}]}
    leak = {"questions": [_q("They abandon the car.")]}
    assert any("cloze" in e for e in validate("word_quiz", leak, inp))
    ok = {"questions": [_q("They ___ the car.")]}
    assert validate("word_quiz", ok, inp) == []
    many = {"questions": [_q("They ___ the car.")] * 3}
    assert any("2 倍" in e for e in validate("word_quiz", many, inp))
