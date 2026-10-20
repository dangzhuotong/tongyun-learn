"""Practice-flow smoke suite on tongyun-learn: health, board, practice review, typing & voiding."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.learn_helpers import AXUE, WEB, learn_env, map_texts  # noqa: F401
from tongyun_learn import __version__
from tongyun_learn.models import Card

pytestmark = pytest.mark.usefixtures("learn_env")


def _import_maps(client: TestClient) -> dict:
    """Helper to import standard maps for offline smoke tests."""
    res = client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE)
    assert res.status_code == 200, res.text
    return res.json()


def test_smoke_health_and_auth_paths(client: TestClient) -> None:
    """Smoke test: health checks, liveness probe, DB failure degradation, and auth boundaries."""
    # 1. Liveness endpoint /healthz
    r_healthz = client.get("/healthz")
    assert r_healthz.status_code == 200
    assert r_healthz.json() == {"status": "ok"}

    # 2. Main health check /v1/health
    r_health = client.get("/v1/health")
    assert r_health.status_code == 200
    data = r_health.json()
    assert data["status"] == "ok"
    assert data["version"] == __version__
    assert data["db"] == "ok"
    assert "+08:00" in data["time"]

    # 3. Degraded health when DB connection fails
    with patch("tongyun_learn.routers.health.get_engine") as mock_engine:
        mock_engine.return_value.connect.side_effect = Exception("DB offline")
        r_fail = client.get("/v1/health")
        assert r_fail.status_code == 503
        fail_data = r_fail.json()
        assert fail_data["status"] == "degraded"
        assert fail_data["db"] == "error"

    # 4. Auth enforcement: protected routes require tokens
    protected_endpoints = [
        "/v1/subjects",
        "/v1/today",
        "/v1/review/due?limit=10",
        "/v1/next?limit=5",
        "/v1/progress",
        "/v1/blockers?status=open",
    ]
    for ep in protected_endpoints:
        r_anon = client.get(ep)
        assert r_anon.status_code == 401, f"{ep} allowed anonymous access"
        assert r_anon.json()["error"]["code"] == "unauthorized"

        r_bad = client.get(ep, headers={"Authorization": "Bearer invalid-token"})
        assert r_bad.status_code == 401, f"{ep} allowed invalid token"
        assert r_bad.json()["error"]["code"] == "unauthorized"

    # 5. Role permissions: web token cannot write teacher-only endpoints
    r_web_import = client.post("/v1/maps/import?dry_run=true", json={"files": map_texts()}, headers=WEB)
    assert r_web_import.status_code == 403

    r_web_session = client.post("/v1/sessions", json={"date": "2026-10-20", "summary": "test"}, headers=WEB)
    assert r_web_session.status_code == 403

    r_web_evidence = client.post(
        "/v1/evidence", json={"point_id": "jf.java-basics", "type": "selftest", "passed": True}, headers=WEB
    )
    assert r_web_evidence.status_code == 403


def test_smoke_board_navigation_and_blockers(client: TestClient) -> None:
    """Smoke test: board subjects, maps, recommendations, progress, and blocker lifecycle."""
    _import_maps(client)

    # 1. Subjects list
    res_sub = client.get("/v1/subjects", headers=WEB)
    assert res_sub.status_code == 200
    subjects = res_sub.json()
    assert isinstance(subjects, list)
    sub_ids = {s["id"] for s in subjects}
    assert "tech-english" in sub_ids
    assert "java-fde" in sub_ids

    for sub in subjects:
        assert "points_by_state" in sub
        assert isinstance(sub["points_by_state"], dict)

    # 2. Subject map inspection
    res_map = client.get("/v1/subjects/java-fde/map", headers=WEB)
    assert res_map.status_code == 200
    map_data = res_map.json()
    assert map_data["subject"]["id"] == "java-fde"
    assert len(map_data["stages"]) > 0
    first_stage = map_data["stages"][0]
    assert "points" in first_stage
    assert len(first_stage["points"]) > 0
    assert "prereqs" in first_stage["points"][0]
    assert "stats" in first_stage["points"][0]

    # 3. Next learning recommendations
    res_next = client.get("/v1/next?limit=5", headers=WEB)
    assert res_next.status_code == 200
    next_data = res_next.json()
    assert "next" in next_data and isinstance(next_data["next"], list)
    assert "recheck" in next_data and isinstance(next_data["recheck"], list)
    assert "new_point_quota" in next_data
    assert "global_left" in next_data["new_point_quota"]

    # 4. Progress overview
    res_prog = client.get("/v1/progress?subject=java-fde", headers=WEB)
    assert res_prog.status_code == 200
    prog_data = res_prog.json()
    assert "points_by_state" in prog_data
    assert "retention_30d" in prog_data

    # 5. Blocker lifecycle (create -> list open -> resolve -> list resolved)
    res_blk = client.post(
        "/v1/blockers",
        json={
            "point_id": "jf.equals-hashcode",
            "title": "Smoke test blocker: contract confusion",
            "detail": "Clarification needed on equals & hashCode",
        },
        headers=AXUE,
    )
    assert res_blk.status_code == 200, res_blk.text
    blk_id = res_blk.json()["id"]

    res_open = client.get("/v1/blockers?status=open", headers=WEB)
    assert res_open.status_code == 200
    assert any(b["id"] == blk_id for b in res_open.json())

    res_patch = client.patch(
        f"/v1/blockers/{blk_id}",
        json={"status": "resolved", "resolution": "Resolved via mentor review"},
        headers=AXUE,
    )
    assert res_patch.status_code == 200

    res_open_after = client.get("/v1/blockers?status=open", headers=WEB)
    assert all(b["id"] != blk_id for b in res_open_after.json())

    res_resolved = client.get("/v1/blockers?status=resolved", headers=WEB)
    assert any(b["id"] == blk_id for b in res_resolved.json())


def test_smoke_practice_review_and_evidence_flow(client: TestClient) -> None:
    """Smoke test: due card queue, single review, batch review, tutor sessions, and evidence."""
    _import_maps(client)

    # 1. Inspect due queue
    q_res = client.get("/v1/review/due?subject=java-fde&limit=10", headers=WEB)
    assert q_res.status_code == 200
    queue_data = q_res.json()
    assert "review" in queue_data
    assert "new" in queue_data
    assert len(queue_data["new"]) > 0

    target_card = queue_data["new"][0]
    card_id = target_card["card_id"]
    point_id = target_card["point_id"]

    # 2. Practice review card (single)
    r1 = client.post(
        "/v1/review",
        json={"card_id": card_id, "rating": 3, "client_review_id": "smoke-flow-cr-1"},
        headers=WEB,
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["applied"] is True
    assert b1["duplicate"] is False
    assert b1["card_state"]["reps"] == 1
    assert {"point_id": point_id, "from": "available", "to": "learning"} in b1["point_changes"]

    # Idempotent re-submission
    r1_dup = client.post(
        "/v1/review",
        json={"card_id": card_id, "rating": 3, "client_review_id": "smoke-flow-cr-1"},
        headers=WEB,
    )
    assert r1_dup.status_code == 200
    assert r1_dup.json()["duplicate"] is True
    assert r1_dup.json()["applied"] is False

    # 3. Practice batch review (words)
    batch_items = [
        {
            "kind": "en_word",
            "word": "Concurrent",
            "dict_id": "cet4",
            "rating": 3,
            "errors": 0,
            "reviewed_at": "2026-10-20T10:00:00+08:00",
            "client_review_id": "smoke-word-1",
        },
        {
            "kind": "en_word",
            "word": "Parallel",
            "dict_id": "cet4",
            "rating": 4,
            "errors": 0,
            "reviewed_at": "2026-10-20T10:01:00+08:00",
            "client_review_id": "smoke-word-2",
        },
        {
            "kind": "en_word",
            "word": "Concurrent",
            "dict_id": "cet4",
            "rating": 3,
            "client_review_id": "smoke-word-1",
        },
    ]
    r_batch = client.post("/v1/review/batch", json={"items": batch_items}, headers=WEB)
    assert r_batch.status_code == 200, r_batch.text
    batch_data = r_batch.json()
    assert batch_data["duplicates"] == 1
    assert len(batch_data["results"]) == 3
    assert batch_data["results"][0]["applied"] is True
    assert batch_data["results"][1]["applied"] is True

    # 4. Session & Evidence progression
    nxt = client.get("/v1/next?subject=java-fde&limit=5", headers=AXUE).json()
    avail_point = next(p["point_id"] for p in nxt["next"] if p["state"] == "available")

    sess_res = client.post(
        "/v1/sessions",
        json={
            "date": "2026-10-20",
            "point_ids": [avail_point],
            "cues": ["Explain how it works"],
            "summary": "Smoke test practice session",
        },
        headers=AXUE,
    )
    assert sess_res.status_code == 200, sess_res.text
    sess_id = sess_res.json()["session_id"]
    assert {"point_id": avail_point, "from": "available", "to": "learning"} in sess_res.json()["point_changes"]

    # Submit evidence -> state moves to learned
    ev_res = client.post(
        "/v1/evidence",
        json={
            "point_id": avail_point,
            "type": "selftest",
            "score": 4,
            "max": 5,
            "passed": True,
            "session_id": sess_id,
        },
        headers=AXUE,
    )
    assert ev_res.status_code == 200, ev_res.text
    assert ev_res.json()["passed"] is True
    assert {"point_id": avail_point, "from": "learning", "to": "learned"} in ev_res.json()["point_changes"]

    # Point detail check
    pt_detail = client.get(f"/v1/points/{avail_point}", headers=WEB).json()
    assert pt_detail["stats"]["state"] == "learned"
    assert len(pt_detail["evidence"]) >= 1


def test_smoke_yun_ya_typing_practice_flow(client: TestClient, db_session: Session) -> None:
    """Smoke test: yun-ya English daily queue, phase A word typing, phase B sentence typing, and coach."""
    # 1. GET /v1/today queue
    res_today = client.get("/v1/today", headers=WEB)
    assert res_today.status_code == 200, res_today.text
    today_data = res_today.json()
    assert "source" in today_data
    assert "current_unit" in today_data
    assert "items" in today_data
    assert len(today_data["items"]) > 0

    read_item = next((item for item in today_data["items"] if item["phase"] == "A"), today_data["items"][0])
    card_id = read_item["card_id"]
    expected_word = read_item["lemma"]

    # 2. Phase A word typing (correct)
    t_res1 = client.post(
        "/v1/type",
        json={
            "card_id": card_id,
            "phase": "A",
            "typed": expected_word,
            "duration_ms": 1200,
            "client_event_id": "smoke-type-ev-1",
        },
        headers=WEB,
    )
    assert t_res1.status_code == 200, t_res1.text
    t_body1 = t_res1.json()
    assert t_body1["correct"] is True
    assert t_body1["duplicate"] is False
    assert t_body1["rating"] == 3
    assert t_body1["card_state"]["reps"] >= 1

    # Duplicate submission
    t_res_dup = client.post(
        "/v1/type",
        json={
            "card_id": card_id,
            "phase": "A",
            "typed": expected_word,
            "duration_ms": 50,
            "client_event_id": "smoke-type-ev-1",
        },
        headers=WEB,
    )
    assert t_res_dup.status_code == 200
    assert t_res_dup.json()["duplicate"] is True

    # Typo submission (wrong)
    t_res_typo = client.post(
        "/v1/type",
        json={
            "card_id": card_id,
            "phase": "A",
            "typed": expected_word + "xyz",
            "duration_ms": 800,
        },
        headers=WEB,
    )
    assert t_res_typo.status_code == 200
    assert t_res_typo.json()["correct"] is False
    assert t_res_typo.json()["error_shape"] is not None

    # 3. Phase B sentence typing
    card_row = db_session.get(Card, card_id)
    assert card_row is not None
    sentences = (card_row.payload or {}).get("sentences", [])
    if sentences:
        en_sentence = sentences[0]["en"]
        stripped = en_sentence.rstrip(".!?")
        t_phase_b = client.post(
            "/v1/type",
            json={
                "card_id": card_id,
                "phase": "B",
                "typed": stripped,
                "sentence_index": 0,
                "duration_ms": 3000,
            },
            headers=WEB,
        )
        assert t_phase_b.status_code == 200, t_phase_b.text
        assert t_phase_b.json()["correct"] is True

    # 4. Coach inspection and plan generation
    c_get = client.get("/v1/coach", headers=WEB)
    assert c_get.status_code == 200
    assert "weak" in c_get.json()

    c_post = client.post("/v1/coach", json={}, headers=WEB)
    assert c_post.status_code == 200
    assert "plan" in c_post.json()


def test_smoke_review_voiding_and_recovery(client: TestClient, db_session: Session) -> None:
    """Smoke test: review voiding, FSRS rollback replay, and review restoration."""
    _import_maps(client)

    card = db_session.scalar(select(Card).where(Card.active.is_(True), Card.point_id.is_not(None)))
    assert card is not None
    card_id = card.id

    # Review 1
    r1 = client.post(
        "/v1/review",
        json={
            "card_id": card_id,
            "rating": 3,
            "reviewed_at": "2026-10-20T08:00:00Z",
            "client_review_id": "smoke-void-r1",
        },
        headers=AXUE,
    )
    assert r1.status_code == 200
    cs1 = r1.json()["card_state"]
    assert cs1["reps"] == 1

    # Review 2
    r2 = client.post(
        "/v1/review",
        json={
            "card_id": card_id,
            "rating": 1,
            "reviewed_at": "2026-10-20T09:00:00Z",
            "client_review_id": "smoke-void-r2",
        },
        headers=AXUE,
    )
    assert r2.status_code == 200
    rev2_id = r2.json()["review_id"]
    cs2 = r2.json()["card_state"]
    assert cs2["reps"] == 2

    # Void review 2
    v_res = client.post(f"/v1/reviews/{rev2_id}/void", json={"reason": "Mistaken rating input"}, headers=AXUE)
    assert v_res.status_code == 200, v_res.text
    cs_voided = v_res.json()["card_state"]
    assert cs_voided["reps"] == 1
    assert cs_voided["reps"] == cs1["reps"]

    # Restore review 2
    rest_res = client.post(
        f"/v1/reviews/{rev2_id}/restore", json={"reason": "Undo void operation"}, headers=AXUE
    )
    assert rest_res.status_code == 200, rest_res.text
    cs_restored = rest_res.json()["card_state"]
    assert cs_restored["reps"] == 2

    # Query reviews listing
    rev_list = client.get(f"/v1/reviews?card={card_id}", headers=AXUE)
    assert rev_list.status_code == 200
    assert len(rev_list.json()) >= 2


def test_smoke_insights_and_state_override(client: TestClient) -> None:
    """Smoke test: weak points inspection, weekly study summary, and manual state overrides."""
    _import_maps(client)

    # 1. Weekly summary smoke
    res_week = client.get("/v1/summary/week?ago=0", headers=WEB)
    assert res_week.status_code == 200
    w_data = res_week.json()
    assert "range" in w_data
    assert "start" in w_data["range"]
    assert "end" in w_data["range"]
    assert "reviews" in w_data
    assert "study_days" in w_data

    # 2. Weak points inspection
    client.post(
        "/v1/blockers",
        json={
            "point_id": "jf.equals-hashcode",
            "title": "Smoke blocker for weak check",
            "detail": "Test details",
        },
        headers=AXUE,
    )
    weak_res = client.get("/v1/weak?subject=java-fde", headers=WEB)
    assert weak_res.status_code == 200
    weak_items = weak_res.json()
    assert any(item["point_id"] == "jf.equals-hashcode" for item in weak_items)

    # 3. Manual state override & revoke
    patch_res = client.patch(
        "/v1/points/jf.equals-hashcode/state",
        json={"state": "mastered", "reason": "Smoke test fast-track"},
        headers=AXUE,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["state"] == "mastered"
    assert patch_res.json()["override_state"] == "mastered"

    # Revoke override
    revoke_res = client.patch(
        "/v1/points/jf.equals-hashcode/state",
        json={"state": None, "reason": "Smoke test revoke"},
        headers=AXUE,
    )
    assert revoke_res.status_code == 200
    assert revoke_res.json()["override_state"] is None

