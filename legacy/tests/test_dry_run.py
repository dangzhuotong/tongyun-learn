"""Task E2: 测试所有写接口的 ?dry_run=true 预演功能。"""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.learn_helpers import AXUE, WEB, learn_env, map_texts  # noqa: F401
from tongyun_learn.models import (
    Blocker,
    Card,
    CardState,
    Deck,
    Evidence,
    PointState,
    PointStateLog,
    ReviewLog,
    SessionPoint,
    StudySession,
)


def _import_maps(client: TestClient) -> None:
    res = client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE)
    assert res.status_code == 200, res.text


def _db_snapshot(db: Session) -> dict:
    db.expire_all()
    return {
        "sessions": db.scalar(select(func.count()).select_from(StudySession)),
        "session_points": db.scalar(select(func.count()).select_from(SessionPoint)),
        "evidence": db.scalar(select(func.count()).select_from(Evidence)),
        "blockers": db.scalar(select(func.count()).select_from(Blocker)),
        "review_log": db.scalar(select(func.count()).select_from(ReviewLog)),
        "card_state": db.scalar(select(func.count()).select_from(CardState)),
        "cards": db.scalar(select(func.count()).select_from(Card)),
        "decks": db.scalar(select(func.count()).select_from(Deck)),
        "point_state_log": db.scalar(select(func.count()).select_from(PointStateLog)),
        "point_states": {
            ps.point_id: (ps.state, ps.override_state, ps.override_reason)
            for ps in db.scalars(select(PointState).order_by(PointState.point_id))
        },
    }


def test_dry_run_all_write_endpoints_and_verify_no_change_then_real_write(
    client: TestClient, db_session: Session, learn_env  # noqa: F811
):
    _import_maps(client)

    nxt = client.get("/v1/next?subject=java-fde&limit=5", headers=AXUE).json()
    target_pt = next(n for n in nxt["next"] if n["state"] == "available")["point_id"]

    # 1. POST /v1/sessions
    snap_before = _db_snapshot(db_session)
    r_sess_dry = client.post(
        "/v1/sessions?dry_run=true",
        json={"date": "2026-10-07", "point_ids": [target_pt], "summary": "预演课次"},
        headers=AXUE,
    )
    assert r_sess_dry.status_code == 200, r_sess_dry.text
    assert r_sess_dry.headers.get("X-Dry-Run") == "1"
    d_sess_dry = r_sess_dry.json()
    assert d_sess_dry.get("dry_run") is True
    assert d_sess_dry.get("session_id") is not None
    assert {"point_id": target_pt, "from": "available", "to": "learning"} in d_sess_dry.get("point_changes", [])
    assert _db_snapshot(db_session) == snap_before
    assert client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["stats"]["state"] == "available"

    # 真写 POST /v1/sessions
    r_sess_real = client.post(
        "/v1/sessions?dry_run=false",
        json={"date": "2026-10-07", "point_ids": [target_pt], "summary": "真写课次"},
        headers=AXUE,
    )
    assert r_sess_real.status_code == 200, r_sess_real.text
    assert "X-Dry-Run" not in r_sess_real.headers
    d_sess_real = r_sess_real.json()
    assert "dry_run" not in d_sess_real
    assert d_sess_real.get("session_id") is not None
    real_session_id = d_sess_real["session_id"]
    assert client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["stats"]["state"] == "learning"

    # 2. POST /v1/evidence
    snap_before = _db_snapshot(db_session)
    r_ev_dry = client.post(
        "/v1/evidence?dry_run=true",
        json={"point_id": target_pt, "type": "selftest", "score": 2, "max": 5, "session_id": real_session_id},
        headers=AXUE,
    )
    assert r_ev_dry.status_code == 200, r_ev_dry.text
    assert r_ev_dry.headers.get("X-Dry-Run") == "1"
    d_ev_dry = r_ev_dry.json()
    assert d_ev_dry.get("dry_run") is True
    assert d_ev_dry.get("evidence_id") is not None
    assert d_ev_dry.get("passed") is False
    assert {"point_id": target_pt, "from": "learning", "to": "learned"} in d_ev_dry.get("point_changes", [])
    assert _db_snapshot(db_session) == snap_before
    assert client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["stats"]["state"] == "learning"

    # 真写 POST /v1/evidence
    r_ev_real = client.post(
        "/v1/evidence",
        json={"point_id": target_pt, "type": "selftest", "score": 2, "max": 5, "session_id": real_session_id},
        headers=AXUE,
    )
    assert r_ev_real.status_code == 200, r_ev_real.text
    assert "X-Dry-Run" not in r_ev_real.headers
    assert "dry_run" not in r_ev_real.json()
    assert client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["stats"]["state"] == "learned"

    # 3. POST /v1/blockers
    snap_before = _db_snapshot(db_session)
    r_b_dry = client.post(
        "/v1/blockers?dry_run=true",
        json={"point_id": target_pt, "title": "dry blocker", "detail": "detail"},
        headers=AXUE,
    )
    assert r_b_dry.status_code == 200, r_b_dry.text
    assert r_b_dry.headers.get("X-Dry-Run") == "1"
    d_b_dry = r_b_dry.json()
    assert d_b_dry.get("dry_run") is True
    assert d_b_dry.get("id") is not None
    assert d_b_dry["title"] == "dry blocker"
    assert d_b_dry["status"] == "open"
    assert _db_snapshot(db_session) == snap_before
    assert client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["stats"]["open_blockers"] == 0
    assert not any(b["title"] == "dry blocker" for b in client.get("/v1/blockers", headers=AXUE).json())

    # 真写 POST /v1/blockers
    r_b_real = client.post(
        "/v1/blockers",
        json={"point_id": target_pt, "title": "real blocker", "detail": "detail"},
        headers=AXUE,
    )
    assert r_b_real.status_code == 200, r_b_real.text
    assert "X-Dry-Run" not in r_b_real.headers
    assert "dry_run" not in r_b_real.json()
    real_blocker_id = r_b_real.json()["id"]
    assert client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["stats"]["open_blockers"] == 1

    # 4. PATCH /v1/blockers/{id}
    snap_before = _db_snapshot(db_session)
    r_pb_dry = client.patch(
        f"/v1/blockers/{real_blocker_id}?dry_run=true",
        json={"status": "resolved", "resolution": "dry res"},
        headers=AXUE,
    )
    assert r_pb_dry.status_code == 200, r_pb_dry.text
    assert r_pb_dry.headers.get("X-Dry-Run") == "1"
    d_pb_dry = r_pb_dry.json()
    assert d_pb_dry.get("dry_run") is True
    assert d_pb_dry["status"] == "resolved"
    assert d_pb_dry["resolution"] == "dry res"
    assert _db_snapshot(db_session) == snap_before
    assert client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["stats"]["open_blockers"] == 1
    assert client.get("/v1/blockers?status=resolved", headers=AXUE).json() == []

    # 真写 PATCH /v1/blockers/{id}
    r_pb_real = client.patch(
        f"/v1/blockers/{real_blocker_id}",
        json={"status": "resolved", "resolution": "real res"},
        headers=AXUE,
    )
    assert r_pb_real.status_code == 200, r_pb_real.text
    assert "X-Dry-Run" not in r_pb_real.headers
    assert "dry_run" not in r_pb_real.json()
    assert client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["stats"]["open_blockers"] == 0

    # 5. POST /v1/points/{id}/cards
    snap_before = _db_snapshot(db_session)
    r_pc_dry = client.post(
        f"/v1/points/{target_pt}/cards?dry_run=true",
        json={"cards": [{"card_type": "memory", "front": "dry point card front", "back": "back"}]},
        headers=AXUE,
    )
    assert r_pc_dry.status_code == 200, r_pc_dry.text
    assert r_pc_dry.headers.get("X-Dry-Run") == "1"
    d_pc_dry = r_pc_dry.json()
    assert d_pc_dry.get("dry_run") is True
    assert len(d_pc_dry["created"]) == 1
    assert d_pc_dry["created"][0]["front"] == "dry point card front"
    assert _db_snapshot(db_session) == snap_before
    assert not any(
        c["front"] == "dry point card front"
        for c in client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["cards"]
    )

    # 真写 POST /v1/points/{id}/cards
    r_pc_real = client.post(
        f"/v1/points/{target_pt}/cards",
        json={"cards": [{"card_type": "memory", "front": "real point card front", "back": "back"}]},
        headers=AXUE,
    )
    assert r_pc_real.status_code == 200, r_pc_real.text
    assert "X-Dry-Run" not in r_pc_real.headers
    assert "dry_run" not in r_pc_real.json()
    real_card_id = r_pc_real.json()["created"][0]["card_id"]
    assert any(
        c["front"] == "real point card front"
        for c in client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["cards"]
    )

    # 6. PATCH /v1/cards/{id}
    snap_before = _db_snapshot(db_session)
    r_patchc_dry = client.patch(
        f"/v1/cards/{real_card_id}?dry_run=true",
        json={"front": "patched dry front"},
        headers=AXUE,
    )
    assert r_patchc_dry.status_code == 200, r_patchc_dry.text
    assert r_patchc_dry.headers.get("X-Dry-Run") == "1"
    d_patchc_dry = r_patchc_dry.json()
    assert d_patchc_dry.get("dry_run") is True
    assert d_patchc_dry["front"] == "patched dry front"
    assert _db_snapshot(db_session) == snap_before
    cards_now = client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["cards"]
    assert any(c["card_id"] == real_card_id and c["front"] == "real point card front" for c in cards_now)

    # 真写 PATCH /v1/cards/{id}
    r_patchc_real = client.patch(
        f"/v1/cards/{real_card_id}",
        json={"front": "patched real front"},
        headers=AXUE,
    )
    assert r_patchc_real.status_code == 200, r_patchc_real.text
    assert "X-Dry-Run" not in r_patchc_real.headers
    assert "dry_run" not in r_patchc_real.json()
    cards_now = client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["cards"]
    assert any(c["card_id"] == real_card_id and c["front"] == "patched real front" for c in cards_now)

    # 7. POST /v1/decks
    snap_before = _db_snapshot(db_session)
    r_d_dry = client.post(
        "/v1/decks?dry_run=true",
        json={"kind": "custom", "name": "dry_deck"},
        headers=AXUE,
    )
    assert r_d_dry.status_code == 200, r_d_dry.text
    assert r_d_dry.headers.get("X-Dry-Run") == "1"
    d_d_dry = r_d_dry.json()
    assert d_d_dry.get("dry_run") is True
    assert d_d_dry["name"] == "dry_deck"
    assert d_d_dry["created"] is True
    assert _db_snapshot(db_session) == snap_before
    assert not any(d["name"] == "dry_deck" for d in client.get("/v1/decks", headers=AXUE).json())

    # 真写 POST /v1/decks
    r_d_real = client.post(
        "/v1/decks",
        json={"kind": "custom", "name": "real_deck"},
        headers=AXUE,
    )
    assert r_d_real.status_code == 200, r_d_real.text
    assert "X-Dry-Run" not in r_d_real.headers
    assert "dry_run" not in r_d_real.json()
    real_deck_id = r_d_real.json()["id"]
    real_decks = client.get("/v1/decks", headers=AXUE).json()
    assert any(d["id"] == real_deck_id and d["name"] == "real_deck" for d in real_decks)

    # 8. POST /v1/decks/{id}/cards
    snap_before = _db_snapshot(db_session)
    r_dc_dry = client.post(
        f"/v1/decks/{real_deck_id}/cards?dry_run=true",
        json={"cards": [{"card_type": "memory", "front": "deck dry card front"}]},
        headers=AXUE,
    )
    assert r_dc_dry.status_code == 200, r_dc_dry.text
    assert r_dc_dry.headers.get("X-Dry-Run") == "1"
    d_dc_dry = r_dc_dry.json()
    assert d_dc_dry.get("dry_run") is True
    assert len(d_dc_dry["created"]) == 1
    assert d_dc_dry["created"][0]["front"] == "deck dry card front"
    assert _db_snapshot(db_session) == snap_before

    # 真写 POST /v1/decks/{id}/cards
    r_dc_real = client.post(
        f"/v1/decks/{real_deck_id}/cards",
        json={"cards": [{"card_type": "memory", "front": "deck real card front"}]},
        headers=AXUE,
    )
    assert r_dc_real.status_code == 200, r_dc_real.text
    assert "X-Dry-Run" not in r_dc_real.headers
    assert "dry_run" not in r_dc_real.json()
    assert len(r_dc_real.json()["created"]) == 1

    # 9. POST /v1/review
    q = client.get("/v1/review/due?subject=java-fde&limit=50", headers=AXUE).json()
    rev_card = q["new"][0]
    snap_before = _db_snapshot(db_session)
    r_rev_dry = client.post(
        "/v1/review?dry_run=true",
        json={"card_id": rev_card["card_id"], "rating": 3, "client_review_id": "dry-rev-crid-1"},
        headers=AXUE,
    )
    assert r_rev_dry.status_code == 200, r_rev_dry.text
    assert r_rev_dry.headers.get("X-Dry-Run") == "1"
    d_rev_dry = r_rev_dry.json()
    assert d_rev_dry.get("dry_run") is True
    assert d_rev_dry["applied"] is True
    assert d_rev_dry["duplicate"] is False
    assert d_rev_dry["card_state"] is not None
    assert _db_snapshot(db_session) == snap_before
    q_after = client.get("/v1/review/due?subject=java-fde&limit=50", headers=AXUE).json()
    assert any(c["card_id"] == rev_card["card_id"] for c in q_after["new"])

    # 真写 POST /v1/review
    r_rev_real = client.post(
        "/v1/review",
        json={"card_id": rev_card["card_id"], "rating": 3, "client_review_id": "real-rev-crid-1"},
        headers=AXUE,
    )
    assert r_rev_real.status_code == 200, r_rev_real.text
    assert "X-Dry-Run" not in r_rev_real.headers
    assert "dry_run" not in r_rev_real.json()
    assert r_rev_real.json()["applied"] is True

    # 10. POST /v1/review/batch
    snap_before = _db_snapshot(db_session)
    r_batch_dry = client.post(
        "/v1/review/batch?dry_run=true",
        json={"items": [{"kind": "en_word", "word": "dryrunword", "rating": 3}]},
        headers=AXUE,
    )
    assert r_batch_dry.status_code == 200, r_batch_dry.text
    assert r_batch_dry.headers.get("X-Dry-Run") == "1"
    d_batch_dry = r_batch_dry.json()
    assert d_batch_dry.get("dry_run") is True
    assert len(d_batch_dry["results"]) == 1
    assert d_batch_dry["results"][0]["applied"] is True
    assert _db_snapshot(db_session) == snap_before

    # 真写 POST /v1/review/batch
    r_batch_real = client.post(
        "/v1/review/batch",
        json={"items": [{"kind": "en_word", "word": "realword", "rating": 3}]},
        headers=AXUE,
    )
    assert r_batch_real.status_code == 200, r_batch_real.text
    assert "X-Dry-Run" not in r_batch_real.headers
    assert "dry_run" not in r_batch_real.json()
    assert len(r_batch_real.json()["results"]) == 1
    assert r_batch_real.json()["results"][0]["applied"] is True

    # 11. PATCH /v1/points/{id}/state
    snap_before = _db_snapshot(db_session)
    r_state_dry = client.patch(
        f"/v1/points/{target_pt}/state?dry_run=true",
        json={"state": "mastered", "reason": "预演人工改状态"},
        headers=AXUE,
    )
    assert r_state_dry.status_code == 200, r_state_dry.text
    assert r_state_dry.headers.get("X-Dry-Run") == "1"
    d_state_dry = r_state_dry.json()
    assert d_state_dry.get("dry_run") is True
    assert d_state_dry["override_state"] == "mastered"
    assert d_state_dry["state"] == "mastered"
    assert _db_snapshot(db_session) == snap_before
    assert client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["stats"]["override_state"] is None

    # 真写 PATCH /v1/points/{id}/state
    r_state_real = client.patch(
        f"/v1/points/{target_pt}/state",
        json={"state": "mastered", "reason": "真写人工改状态"},
        headers=AXUE,
    )
    assert r_state_real.status_code == 200, r_state_real.text
    assert "X-Dry-Run" not in r_state_real.headers
    assert "dry_run" not in r_state_real.json()
    assert client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["stats"]["override_state"] == "mastered"


def test_dry_run_consecutive_sessions_idempotent(client: TestClient, db_session: Session, learn_env):  # noqa: F811
    _import_maps(client)
    nxt = client.get("/v1/next?subject=java-fde&limit=5", headers=AXUE).json()
    target_pt = next(n for n in nxt["next"] if n["state"] == "available")["point_id"]

    # 第一次 dry_run POST /sessions
    r1 = client.post(
        "/v1/sessions?dry_run=true",
        json={"date": "2026-10-07", "point_ids": [target_pt], "summary": "第1次预演"},
        headers=AXUE,
    )
    assert r1.status_code == 200, r1.text
    assert r1.headers.get("X-Dry-Run") == "1"
    assert r1.json()["dry_run"] is True
    assert {"point_id": target_pt, "from": "available", "to": "learning"} in r1.json()["point_changes"]

    # 第二次 dry_run POST /sessions：不互相影响，第二次 point_changes 仍是 available→learning
    r2 = client.post(
        "/v1/sessions?dry_run=true",
        json={"date": "2026-10-07", "point_ids": [target_pt], "summary": "第2次预演"},
        headers=AXUE,
    )
    assert r2.status_code == 200, r2.text
    assert r2.headers.get("X-Dry-Run") == "1"
    assert r2.json()["dry_run"] is True
    assert {"point_id": target_pt, "from": "available", "to": "learning"} in r2.json()["point_changes"]

    # 查表确认完全没变
    assert client.get(f"/v1/points/{target_pt}", headers=AXUE).json()["stats"]["state"] == "available"


def test_dry_run_errors_unchanged(client: TestClient, learn_env):  # noqa: F811
    _import_maps(client)

    # 1. 不存在的点 → 404
    r_pt = client.post(
        "/v1/points/nonexistent-point/cards?dry_run=true",
        json={"cards": [{"card_type": "memory", "front": "foo"}]},
        headers=AXUE,
    )
    assert r_pt.status_code == 404

    r_sess = client.post(
        "/v1/sessions?dry_run=true",
        json={"date": "2026-10-07", "point_ids": ["nonexistent-point"], "summary": "x"},
        headers=AXUE,
    )
    assert r_sess.status_code == 404

    r_ev = client.post(
        "/v1/evidence?dry_run=true",
        json={"point_id": "nonexistent-point", "type": "selftest", "score": 1, "max": 2},
        headers=AXUE,
    )
    assert r_ev.status_code == 404

    r_b = client.post(
        "/v1/blockers?dry_run=true",
        json={"point_id": "nonexistent-point", "title": "t"},
        headers=AXUE,
    )
    assert r_b.status_code == 404

    r_st = client.patch(
        "/v1/points/nonexistent-point/state?dry_run=true",
        json={"state": "mastered", "reason": "r"},
        headers=AXUE,
    )
    assert r_st.status_code == 404

    # 不存在的卡片/卡组 → 404
    assert client.patch("/v1/cards/999999?dry_run=true", json={"front": "x"}, headers=AXUE).status_code == 404
    assert (
        client.post(
            "/v1/decks/999999/cards?dry_run=true",
            json={"cards": [{"card_type": "memory", "front": "x"}]},
            headers=AXUE,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            "/v1/blockers/999999?dry_run=true",
            json={"status": "resolved"},
            headers=AXUE,
        ).status_code
        == 404
    )

    # 2. web 令牌对 axue 专用写接口 → 403
    assert (
        client.post(
            "/v1/sessions?dry_run=true",
            json={"date": "2026-10-07", "summary": "x"},
            headers=WEB,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/evidence?dry_run=true",
            json={"point_id": "jf.equals-hashcode", "type": "selftest", "score": 1, "max": 2},
            headers=WEB,
        ).status_code
        == 403
    )
    assert client.post("/v1/blockers?dry_run=true", json={"title": "t"}, headers=WEB).status_code == 403
    assert client.patch("/v1/blockers/1?dry_run=true", json={"status": "resolved"}, headers=WEB).status_code == 403
    assert (
        client.post(
            "/v1/points/jf.equals-hashcode/cards?dry_run=true",
            json={"cards": [{"card_type": "memory", "front": "x"}]},
            headers=WEB,
        ).status_code
        == 403
    )
    assert client.patch("/v1/cards/1?dry_run=true", json={"front": "x"}, headers=WEB).status_code == 403
    assert client.post("/v1/decks?dry_run=true", json={"kind": "custom", "name": "d"}, headers=WEB).status_code == 403
    assert (
        client.post(
            "/v1/decks/1/cards?dry_run=true",
            json={"cards": [{"card_type": "memory", "front": "x"}]},
            headers=WEB,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            "/v1/points/jf.equals-hashcode/state?dry_run=true",
            json={"state": "mastered", "reason": "r"},
            headers=WEB,
        ).status_code
        == 403
    )

    # 3. 校验错误 → 422
    assert client.post("/v1/blockers?dry_run=true", json={"title": ""}, headers=AXUE).status_code == 422
    assert (
        client.patch(
            "/v1/points/jf.equals-hashcode/state?dry_run=true",
            json={"state": "invalid_state", "reason": "r"},
            headers=AXUE,
        ).status_code
        == 422
    )
