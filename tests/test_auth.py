import hashlib
from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from tongyun_learn.auth import Principal, get_principal, require
from tongyun_learn.config import get_settings
from tongyun_learn.db import SessionLocal
from tongyun_learn.errors import ApiError
from tongyun_learn.limits import reset_rate_limiter
from tongyun_learn.main import create_app
from tongyun_learn.models import ApiUsage

WEB_TOKEN = "web-test-token"
AXUE_TOKEN = "axue-test-token"
WEB_SHA256 = hashlib.sha256(WEB_TOKEN.encode()).hexdigest()
AXUE_SHA256 = hashlib.sha256(AXUE_TOKEN.encode()).hexdigest()


@pytest.fixture(autouse=True)
def setup_auth_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_TOKEN_WEB_SHA256", WEB_SHA256)
    monkeypatch.setenv("LEARN_TOKEN_AXUE_SHA256", AXUE_SHA256)
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


def test_auth_no_header(client: TestClient):
    resp = client.post("/v1/ai/explain", json={"kind": "word_mnemonic", "input": {"word": "test"}})
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "unauthorized"
    assert "缺少或无效的令牌" in data["error"]["message"]


def test_auth_malformed_header(client: TestClient):
    resp = client.post(
        "/v1/ai/explain",
        headers={"Authorization": "Basic 12345"},
        json={"kind": "word_mnemonic", "input": {"word": "test"}},
    )
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"
    data = resp.json()
    assert data["error"]["code"] == "unauthorized"


def test_auth_wrong_token(client: TestClient):
    resp = client.post(
        "/v1/ai/explain",
        headers={"Authorization": "Bearer wrong-token"},
        json={"kind": "word_mnemonic", "input": {"word": "test"}},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "unauthorized"


def test_auth_web_token_and_axue_token():
    app = create_app()

    @app.get("/test/principal")
    def read_principal(p: Annotated[Principal, Depends(get_principal)]):
        return {"principal": p.name}

    @app.get("/test/axue-only")
    def axue_only(p: Annotated[Principal, Depends(require("axue"))]):
        return {"principal": p.name}

    with TestClient(app) as test_client:
        # Web token
        resp_web = test_client.get(
            "/test/principal",
            headers={"Authorization": f"Bearer {WEB_TOKEN}"},
        )
        assert resp_web.status_code == 200
        assert resp_web.json() == {"principal": "web"}

        # Axue token
        resp_axue = test_client.get(
            "/test/principal",
            headers={"Authorization": f"Bearer {AXUE_TOKEN}"},
        )
        assert resp_axue.status_code == 200
        assert resp_axue.json() == {"principal": "axue"}

        # Axue only with web token -> 403 forbidden
        resp_forbidden = test_client.get(
            "/test/axue-only",
            headers={"Authorization": f"Bearer {WEB_TOKEN}"},
        )
        assert resp_forbidden.status_code == 403
        data = resp_forbidden.json()
        assert data["error"]["code"] == "forbidden"
        assert data["error"]["message"] == "无权限"

        # Axue only with axue token -> 200 ok
        resp_axue_allowed = test_client.get(
            "/test/axue-only",
            headers={"Authorization": f"Bearer {AXUE_TOKEN}"},
        )
        assert resp_axue_allowed.status_code == 200
        assert resp_axue_allowed.json() == {"principal": "axue"}


def _fake_request(auth: str | None):
    """get_principal 只读取 request.headers.get("Authorization")，用极简替身即可离线直测。"""

    class _Req:
        headers = {"Authorization": auth} if auth is not None else {}

    return _Req()


def test_get_principal_rejects_missing_empty_and_whitespace_tokens():
    settings = get_settings()
    cases = [
        None,  # 无 Authorization
        "",  # 空头
        "Bearer",  # 缺少空格
        "Bearer ",  # 只有前缀
        "Bearer     ",  # 前缀后全是空白
        "bearer web-test-token",  # 大小写不匹配
        "Token web-test-token",  # 方案不对
    ]
    with SessionLocal() as db:
        for value in cases:
            with pytest.raises(ApiError) as exc:
                get_principal(_fake_request(value), db, settings)
            assert exc.value.status_code == 401
            assert exc.value.code == "unauthorized"
            assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


def test_get_principal_strips_surrounding_whitespace():
    settings = get_settings()
    with SessionLocal() as db:
        principal = get_principal(_fake_request(f"Bearer   {WEB_TOKEN}  "), db, settings)
    assert principal == Principal(name="web")


def test_principal_is_frozen():
    principal = Principal(name="web")
    with pytest.raises(FrozenInstanceError):
        principal.name = "axue"  # type: ignore[misc]


def test_require_without_roles_forbids_every_token():
    app = create_app()

    @app.get("/test/no-roles")
    def no_roles(p: Annotated[Principal, Depends(require())]):
        return {"principal": p.name}

    with TestClient(app) as test_client:
        for token in (WEB_TOKEN, AXUE_TOKEN):
            resp = test_client.get("/test/no-roles", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 403
            assert resp.json()["error"]["code"] == "forbidden"


def test_require_multiple_roles_allows_each_listed_role():
    app = create_app()

    @app.get("/test/both")
    def both(p: Annotated[Principal, Depends(require("web", "axue"))]):
        return {"principal": p.name}

    with TestClient(app) as test_client:
        resp_web = test_client.get("/test/both", headers={"Authorization": f"Bearer {WEB_TOKEN}"})
        assert resp_web.status_code == 200
        assert resp_web.json() == {"principal": "web"}

        resp_axue = test_client.get("/test/both", headers={"Authorization": f"Bearer {AXUE_TOKEN}"})
        assert resp_axue.status_code == 200
        assert resp_axue.json() == {"principal": "axue"}


def test_only_web_token_configured_rejects_axue_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEARN_TOKEN_AXUE_SHA256", "")
    get_settings.cache_clear()
    reset_rate_limiter()

    app = create_app()

    @app.get("/test/principal")
    def read_principal(p: Annotated[Principal, Depends(get_principal)]):
        return {"principal": p.name}

    with TestClient(app) as test_client:
        resp_web = test_client.get("/test/principal", headers={"Authorization": f"Bearer {WEB_TOKEN}"})
        assert resp_web.status_code == 200
        assert resp_web.json() == {"principal": "web"}

        # 未配置 axue 哈希：即便请求带上 axue 令牌也必须 401，而不是误判为 axue
        resp_axue = test_client.get("/test/principal", headers={"Authorization": f"Bearer {AXUE_TOKEN}"})
        assert resp_axue.status_code == 401
        assert resp_axue.json()["error"]["code"] == "unauthorized"
