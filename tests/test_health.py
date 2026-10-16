from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tongyun_learn import __version__


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == __version__
    assert data["db"] == "ok"
    assert "+08:00" in data["time"]


def test_healthz_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_db_failure(client: TestClient) -> None:
    with patch("tongyun_learn.routers.health.get_engine") as mock_engine:
        mock_engine.return_value.connect.side_effect = Exception("DB connection timeout")
        resp = client.get("/v1/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["db"] == "error"
        assert "password" not in resp.text
        assert "timeout" not in resp.text


def test_health_time_uses_configured_timezone(client: TestClient) -> None:
    from tongyun_learn.config import Settings

    with patch("tongyun_learn.routers.health.get_settings", return_value=Settings(tz="UTC")):
        resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["time"].endswith("+00:00")


def test_unknown_path_404(client: TestClient) -> None:
    resp = client.get("/v1/non_existent_route")
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "not_found"


def test_root_path_setting(app: FastAPI) -> None:
    assert app.root_path == "/learn/api"
