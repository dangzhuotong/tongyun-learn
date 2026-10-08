import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.learn_helpers import AXUE, WEB, learn_env, map_texts  # noqa: F401
from tongyun_learn.models import Card, CardState, PointState, PointStateLog, ReviewLog

pytestmark = pytest.mark.usefixtures("learn_env")


def _import_maps(client: TestClient) -> None:
    res = client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE)
    assert res.status_code == 200, res.text


def test_review_void_and_fsrs_replay_flow(client: TestClient, db_session) -> None:
    """测试复习作废 + FSRS 重放 + 恢复 + 全作废删 card_state + GET /reviews。"""
    _import_maps(client)

    # 找一张有 point_id 的卡
    card = db_session.scalar(select(Card).where(Card.active.is_(True), Card.point_id.is_not(None)))
    assert card is not None
    card_id = card.id
    point_id = card.point_id

    # 1. POST /review 返回带 review_id；连续复习 3 次（时间递增，评分 3, 3, 1）
    r1 = client.post(
        "/v1/review",
        json={
            "card_id": card_id,
            "rating": 3,
            "reviewed_at": "2026-10-06T10:00:00Z",
            "client_review_id": "cr-replay-1",
        },
        headers=AXUE,
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert "review_id" in b1 and b1["review_id"] is not None
    rev_id1 = b1["review_id"]

    r2 = client.post(
        "/v1/review",
        json={
            "card_id": card_id,
            "rating": 3,
            "reviewed_at": "2026-10-06T11:00:00Z",
            "client_review_id": "cr-replay-2",
        },
        headers=AXUE,
    )
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert "review_id" in b2
    rev_id2 = b2["review_id"]
    cs2_snapshot = b2["card_state"]
    assert cs2_snapshot["reps"] == 2

    db_session.expire_all()
    cs_row_after_2 = db_session.get(CardState, card_id)
    last_rating_after_2 = cs_row_after_2.last_rating
    assert last_rating_after_2 == 3

    r3 = client.post(
        "/v1/review",
        json={
            "card_id": card_id,
            "rating": 1,
            "reviewed_at": "2026-10-06T12:00:00Z",
            "client_review_id": "cr-replay-3",
        },
        headers=AXUE,
    )
    assert r3.status_code == 200, r3.text
    b3 = r3.json()
    rev_id3 = b3["review_id"]
    cs3_snapshot = b3["card_state"]
    assert cs3_snapshot["reps"] == 3

    # 2. 作废第 3 次：card_state 的 stability/due/reps/lapses/last_rating 等于第 2 次之后的值（reps=2）
    r_void3 = client.post(
        f"/v1/reviews/{rev_id3}/void",
        json={"reason": "误点 Again"},
        headers=AXUE,
    )
    assert r_void3.status_code == 200, r_void3.text
    v3_body = r_void3.json()
    assert v3_body["review_id"] == rev_id3
    assert v3_body["card_id"] == card_id
    cs_after_v3 = v3_body["card_state"]
    assert cs_after_v3["reps"] == 2
    assert cs_after_v3["reps"] == cs2_snapshot["reps"]
    assert cs_after_v3["stability"] == cs2_snapshot["stability"]
    assert cs_after_v3["due"] == cs2_snapshot["due"]
    assert cs_after_v3["lapses"] == cs2_snapshot["lapses"]

    db_session.expire_all()
    cs_row_v3 = db_session.get(CardState, card_id)
    assert cs_row_v3.reps == 2
    assert cs_row_v3.last_rating == 3

    # 3. 再恢复第 3 次：等于 3 次都算的结果
    r_res3 = client.post(
        f"/v1/reviews/{rev_id3}/restore",
        json={"reason": "没误点，确实记错了"},
        headers=AXUE,
    )
    assert r_res3.status_code == 200, r_res3.text
    res3_body = r_res3.json()
    cs_after_res3 = res3_body["card_state"]
    assert cs_after_res3["reps"] == 3
    assert cs_after_res3["reps"] == cs3_snapshot["reps"]
    assert cs_after_res3["stability"] == cs3_snapshot["stability"]
    assert cs_after_res3["due"] == cs3_snapshot["due"]
    assert cs_after_res3["lapses"] == cs3_snapshot["lapses"]

    db_session.expire_all()
    cs_row_res3 = db_session.get(CardState, card_id)
    assert cs_row_res3.reps == 3
    assert cs_row_res3.last_rating == 1

    # 4. 三条全作废 → card_state 行被删（GET /points/{id} 里该卡 state=0），点状态随之重算
    r_v3 = client.post(f"/v1/reviews/{rev_id3}/void", json={"reason": "作废3"}, headers=AXUE)
    assert r_v3.status_code == 200
    r_v2 = client.post(f"/v1/reviews/{rev_id2}/void", json={"reason": "作废2"}, headers=AXUE)
    assert r_v2.status_code == 200
    r_v1 = client.post(f"/v1/reviews/{rev_id1}/void", json={"reason": "作废1"}, headers=AXUE)
    assert r_v1.status_code == 200
    assert r_v1.json()["card_state"] is None

    db_session.expire_all()
    assert db_session.get(CardState, card_id) is None

    # GET /points/{id} 里该卡 state=0
    pt_info = client.get(f"/v1/points/{point_id}", headers=AXUE).json()
    c_item = next(c for c in pt_info["cards"] if c["card_id"] == card_id)
    assert c_item["state"] == 0

    # 点状态随之重算：点没有课次/证据/复习，重算后回到 available
    ps = db_session.get(PointState, point_id)
    assert ps.state == "available"

    # 5. GET /reviews?card= 默认不列作废的
    revs_active = client.get(f"/v1/reviews?card={card_id}", headers=AXUE).json()
    assert len(revs_active) == 0

    # include_voided=true 能查到 3 条已作废复习
    revs_all = client.get(f"/v1/reviews?card={card_id}&include_voided=true", headers=AXUE).json()
    assert len(revs_all) == 3
    for r in revs_all:
        assert r["voided_at"] is not None
        assert r["void_reason"] is not None
        assert r["card_id"] == card_id
        assert r["point_id"] == point_id

    # 6. 同一 client_review_id 的复习被作废后重发 → duplicate=true、voided=true
    r_dup = client.post(
        "/v1/review",
        json={
            "card_id": card_id,
            "rating": 3,
            "reviewed_at": "2026-10-06T10:00:00Z",
            "client_review_id": "cr-replay-1",
        },
        headers=AXUE,
    )
    assert r_dup.status_code == 200
    dup_body = r_dup.json()
    assert dup_body["duplicate"] is True
    assert dup_body["voided"] is True
    assert dup_body["applied"] is False
    assert dup_body["review_id"] == rev_id1


def test_review_void_guards_and_edge_cases(client: TestClient, db_session) -> None:
    """测试复习作废异常场景、权限、dry_run、applied=False 作废、batch 与 evidence 带 review_id。"""
    _import_maps(client)
    card = db_session.scalar(select(Card).where(Card.active.is_(True), Card.point_id.is_not(None)))
    assert card is not None

    # 建一条复习
    r = client.post("/v1/review", json={"card_id": card.id, "rating": 3}, headers=AXUE).json()
    rev_id = r["review_id"]

    # 1. 422: 空白原因
    assert client.post(f"/v1/reviews/{rev_id}/void", json={"reason": "   "}, headers=AXUE).status_code == 422
    assert client.post(f"/v1/reviews/{rev_id}/void", json={"reason": ""}, headers=AXUE).status_code == 422

    # 2. 403: web 令牌禁止作废 / 恢复
    assert client.post(f"/v1/reviews/{rev_id}/void", json={"reason": "web作废"}, headers=WEB).status_code == 403
    assert client.post(f"/v1/reviews/{rev_id}/restore", json={"reason": "web恢复"}, headers=WEB).status_code == 403

    # 3. 404: 不存在的复习
    r_404_v = client.post("/v1/reviews/999999/void", json={"reason": "none"}, headers=AXUE)
    assert r_404_v.status_code == 404 and r_404_v.json()["error"]["code"] == "not_found"

    r_404_r = client.post("/v1/reviews/999999/restore", json={"reason": "none"}, headers=AXUE)
    assert r_404_r.status_code == 404 and r_404_r.json()["error"]["code"] == "not_found"

    # 4. 409 not_voided: 未作废时调 restore
    r_nv = client.post(f"/v1/reviews/{rev_id}/restore", json={"reason": "not voided"}, headers=AXUE)
    assert r_nv.status_code == 409 and r_nv.json()["error"]["code"] == "not_voided"

    # 5. dry_run 作废：库里不变，返回 dry_run: true
    r_dry = client.post(f"/v1/reviews/{rev_id}/void?dry_run=true", json={"reason": "预演作废"}, headers=AXUE)
    assert r_dry.status_code == 200
    assert r_dry.json().get("dry_run") is True
    db_session.expire_all()
    assert db_session.get(ReviewLog, rev_id).voided_at is None

    # 6. 正常作废
    r_void = client.post(f"/v1/reviews/{rev_id}/void", json={"reason": "正式作废"}, headers=AXUE)
    assert r_void.status_code == 200

    # 7. 409 already_voided: 重复作废
    r_av = client.post(f"/v1/reviews/{rev_id}/void", json={"reason": "再次作废"}, headers=AXUE)
    assert r_av.status_code == 409 and r_av.json()["error"]["code"] == "already_voided"

    # 8. restore 带 reason 写进 point_state_log
    r_res = client.post(f"/v1/reviews/{rev_id}/restore", json={"reason": "恢复复习"}, headers=AXUE)
    assert r_res.status_code == 200
    db_session.expire_all()
    assert db_session.get(ReviewLog, rev_id).voided_at is None
    ps_logs = list(
        db_session.scalars(
            select(PointStateLog).where(PointStateLog.point_id == card.point_id).order_by(PointStateLog.id)
        )
    )
    recent_causes = [(lg.cause, lg.cause_ref, lg.note) for lg in ps_logs[-2:]]
    assert ("void", f"review:{rev_id}", "正式作废") in recent_causes
    assert ("restore", f"review:{rev_id}", "恢复复习") in recent_causes

    # 9. GET /reviews 读接口测试
    # AnyP：web 也可以读
    r_list_web = client.get("/v1/reviews?limit=10", headers=WEB)
    assert r_list_web.status_code == 200
    assert isinstance(r_list_web.json(), list)

    # 验证 card 与 point 过滤
    r_card = client.get(f"/v1/reviews?card={card.id}", headers=AXUE).json()
    assert all(item["card_id"] == card.id for item in r_card)

    r_pt = client.get(f"/v1/reviews?point={card.point_id}", headers=AXUE).json()
    assert all(item["point_id"] == card.point_id for item in r_pt)

    # ?card= 空串不报错
    r_empty_card = client.get("/v1/reviews?card=", headers=AXUE)
    assert r_empty_card.status_code == 200

    # ?card=非数字 报 422
    r_bad_card = client.get("/v1/reviews?card=notanint", headers=AXUE)
    assert r_bad_card.status_code == 422

    # 10. POST /review/batch 的每条结果带 review_id
    batch_res = client.post(
        "/v1/review/batch",
        json={"items": [{"kind": "en_word", "word": "algorithm", "rating": 3}]},
        headers=AXUE,
    )
    assert batch_res.status_code == 200
    b_item = batch_res.json()["results"][0]
    assert "review_id" in b_item and b_item["review_id"] is not None

    # 11. POST /evidence 里的 review 带 review_id
    ev_res = client.post(
        "/v1/evidence",
        json={
            "point_id": card.point_id,
            "card_id": card.id,
            "type": "selftest",
            "score": 5,
            "max": 5,
        },
        headers=AXUE,
    )
    assert ev_res.status_code == 200
    ev_body = ev_res.json()
    assert "review" in ev_body
    assert "review_id" in ev_body["review"] and ev_body["review"]["review_id"] is not None

    # 12. applied=False 的复习（reviewed_at 早于已有的 last_review）：只改标记、不重放
    r_unapplied = client.post(
        "/v1/review",
        json={
            "card_id": card.id,
            "rating": 4,
            "reviewed_at": "2020-01-01T00:00:00Z",
            "client_review_id": "cr-unapplied-1",
        },
        headers=AXUE,
    )
    assert r_unapplied.status_code == 200
    b_unapp = r_unapplied.json()
    assert b_unapp["applied"] is False
    unapp_rev_id = b_unapp["review_id"]

    db_session.expire_all()
    cs_before_void_unapp = db_session.get(CardState, card.id)
    reps_before = cs_before_void_unapp.reps
    stab_before = cs_before_void_unapp.stability

    # 作废该 applied=False 复习：只改标记、不重放
    r_v_unapp = client.post(f"/v1/reviews/{unapp_rev_id}/void", json={"reason": "作废补录"}, headers=AXUE)
    assert r_v_unapp.status_code == 200
    assert r_v_unapp.json()["point_changes"] == []
    assert r_v_unapp.json()["card_state"]["reps"] == reps_before
    assert r_v_unapp.json()["card_state"]["stability"] == stab_before

    db_session.expire_all()
    unapp_row = db_session.get(ReviewLog, unapp_rev_id)
    assert unapp_row.voided_at is not None

    # 恢复该 applied=False 复习：只改标记、不重放
    r_r_unapp = client.post(f"/v1/reviews/{unapp_rev_id}/restore", json={"reason": "恢复补录"}, headers=AXUE)
    assert r_r_unapp.status_code == 200
    assert r_r_unapp.json()["point_changes"] == []
    assert r_r_unapp.json()["card_state"]["reps"] == reps_before

    db_session.expire_all()
    unapp_row2 = db_session.get(ReviewLog, unapp_rev_id)
    assert unapp_row2.voided_at is None
