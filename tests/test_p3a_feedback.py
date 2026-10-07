"""阿衡 / 阿学 对 bac1b86 的反馈修正（10-07 联调口径）。"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.learn_helpers import AXUE, WEB, learn_env, map_texts  # noqa: F401
from tongyun_learn.models import Card, CardState, MapImport, ReviewLog
from tongyun_learn.services.queue import progress
from tongyun_learn.services.tutor import express_to_rating
from tongyun_learn.timeutil import utcnow


def _import(client: TestClient, dry_run: bool) -> dict:
    r = client.post(f"/v1/maps/import?dry_run={str(dry_run).lower()}", json={"files": map_texts()}, headers=AXUE)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize(
    ("score", "mx", "rating"),
    [(0, 8, 1), (3.9, 8, 1), (4, 8, 2), (5, 8, 2), (7, 10, 2), (7.4, 10, 2), (6, 8, 3), (7.5, 10, 3), (7, 8, 3),
     (9.9, 10, 3), (8, 8, 4), (10, 10, 4), (4.9, 10, 1), (5, 10, 2)],
)
def test_express_rating_by_ratio(score, mx, rating):
    assert express_to_rating(score, mx) == rating
    # 和 passed（≥0.75）永远一致：通过 ⇔ rating ≥ 3
    assert (score / mx >= 0.75) == (rating >= 3)


def test_import_open_at_start_and_points_by_state(client: TestClient, db_session: Session, learn_env):  # noqa: F811
    d = _import(client, True)
    res = {r["subject"]: r for r in d["results"]}
    assert all(r["open_at_start"] > 0 for r in res.values())
    assert sum(r["points_by_state"].get("available", 0) for r in res.values()) == 31  # 预演显示导入后的样子
    d = _import(client, False)
    res2 = {r["subject"]: r for r in d["results"]}
    assert {k: v["open_at_start"] for k, v in res2.items()} == {k: v["open_at_start"] for k, v in res.items()}
    assert sum(sum(r["points_by_state"].values()) for r in res2.values()) == 75
    # 预演和真导入都在 map_imports 留一行审计（预演 dry_run=1；预演时还没有学科行的新学科不记）
    db_session.rollback()
    rows = list(db_session.scalars(select(MapImport)))
    assert sorted(bool(r.dry_run) for r in rows) == [False, False]
    _import(client, True)
    db_session.rollback()
    rows = list(db_session.scalars(select(MapImport)))
    assert sorted(bool(r.dry_run) for r in rows) == [False, False, True, True]


def test_stats_null_without_reviews_and_last_passed_at(client: TestClient, learn_env):  # noqa: F811
    _import(client, False)
    st = client.get("/v1/points/jf.git-secrets", headers=AXUE).json()["stats"]
    assert st["stable_ratio"] is None and st["recent_acc"] is None
    assert st["recent_n"] == 0 and st["reviewed_cards"] == 0
    ok = {"point_id": "jf.git-secrets", "type": "selftest", "score": 5, "max": 5}
    ok["observed_at"] = "2026-09-01T10:00:00+08:00"
    assert client.post("/v1/evidence", json=ok, headers=AXUE).status_code == 200
    bad = {"point_id": "jf.git-secrets", "type": "selftest", "score": 1, "max": 5}
    assert client.post("/v1/evidence", json=bad, headers=AXUE).status_code == 200
    ev = client.get("/v1/points/jf.git-secrets", headers=AXUE).json()["stats"]["evidence"]["selftest"]
    assert ev["passed"] is False  # 最近一次没过
    assert ev["last_passed_at"] == "2026-09-01T10:00:00+08:00"  # 但最近一次通过的时间还在


def test_retention_excludes_first_review(client: TestClient, db_session: Session, learn_env):  # noqa: F811
    _import(client, False)
    db = db_session
    db.rollback()
    card = db.scalar(select(Card).where(Card.point_id == "jf.git-secrets").order_by(Card.id))
    now = utcnow()
    first = now - timedelta(days=3)
    db.add(CardState(card_id=card.id, state=2, step=None, stability=5.0, difficulty=5.0, due=now + timedelta(days=3),
                     last_review=now - timedelta(days=1), first_review=first, last_rating=3, reps=2, lapses=0))
    db.add(ReviewLog(card_id=card.id, point_id=card.point_id, rating=1, reviewer="axue", reviewed_at=first,
                     applied=True))
    db.add(ReviewLog(card_id=card.id, point_id=card.point_id, rating=3, reviewer="axue",
                     reviewed_at=now - timedelta(days=1), applied=True))
    db.commit()
    # 第一次（Again）是新卡学习，不算；只剩一次 Good → 1.0
    assert progress(db, subject="java-fde")["retention_30d"] == 1.0


def test_docs_disabled_by_default(client: TestClient):
    assert client.get("/v1/docs").status_code == 404
    assert client.get("/v1/openapi.json").status_code == 404


def test_docs_can_be_enabled(monkeypatch: pytest.MonkeyPatch):
    from tongyun_learn.config import get_settings
    from tongyun_learn.main import create_app

    monkeypatch.setenv("LEARN_DOCS_ENABLED", "true")
    get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        assert c.get("/v1/openapi.json").status_code == 200
    finally:
        get_settings.cache_clear()
