"""P3b insights 读接口与人工改状态测试（/weak、/recall、/summary/week、PATCH /points/{id}/state）。"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.learn_helpers import AXUE, WEB, learn_env, map_texts  # noqa: F401
from tongyun_learn.models import Card, CardState, PointState, PointStateLog
from tongyun_learn.timeutil import today_local

pytestmark = pytest.mark.usefixtures("learn_env")


def _import_maps(client: TestClient) -> None:
    res = client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE)
    assert res.status_code == 200, res.text


# ───────────────────────── GET /v1/weak ─────────────────────────


def test_get_weak(client: TestClient, db_session):
    _import_maps(client)

    # 初始状态：无弱项点
    res0 = client.get("/v1/weak", headers=AXUE)
    assert res0.status_code == 200
    assert res0.json() == []

    # 1. 建一个自测证据让点变 learned（jf.git-secrets：mastery_evidence 为 [selftest]）
    # 给 score=2, max=5（未达标），使点进入 learned 但 fresh_ev 缺达标 selftest 证据
    ev_res = client.post(
        "/v1/evidence",
        json={"point_id": "jf.git-secrets", "type": "selftest", "score": 2, "max": 5},
        headers=AXUE,
    )
    assert ev_res.status_code == 200, ev_res.text

    weak1 = client.get("/v1/weak", headers=AXUE).json()
    assert len(weak1) == 1
    item_git = weak1[0]
    assert item_git["point_id"] == "jf.git-secrets"
    assert "missing_evidence" in item_git["reasons"]
    assert item_git["missing_evidence"] == ["selftest"]

    # 2. 给某点建 open 卡点 → reasons 含 open_blocker；卡点 resolved 后该原因消失
    blk_res = client.post(
        "/v1/blockers",
        json={"point_id": "jf.git-secrets", "title": "Git密钥拦截问题"},
        headers=AXUE,
    )
    assert blk_res.status_code == 200, blk_res.text
    blk_id = blk_res.json()["id"]

    weak2 = client.get("/v1/weak", headers=AXUE).json()
    assert len(weak2) == 1
    assert "open_blocker" in weak2[0]["reasons"]
    assert "missing_evidence" in weak2[0]["reasons"]
    assert weak2[0]["open_blockers"] == 1

    # resolve 卡点后 open_blocker 原因消失
    resolve_res = client.patch(
        f"/v1/blockers/{blk_id}",
        json={"status": "resolved", "resolution": "已修复配置"},
        headers=AXUE,
    )
    assert resolve_res.status_code == 200, resolve_res.text

    weak2_after = client.get("/v1/weak", headers=AXUE).json()
    assert len(weak2_after) == 1
    assert "open_blocker" not in weak2_after[0]["reasons"]
    assert "missing_evidence" in weak2_after[0]["reasons"]

    # 3. 用 db_session 直接把某点 point_state.state 改 rusty / needs_recheck=True、
    # 把卡的 card_state.lapses 改成 3 → 分别出现 rusty、needs_recheck、lapses_high
    ps_eq = db_session.get(PointState, "jf.equals-hashcode")
    assert ps_eq is not None
    ps_eq.state = "rusty"
    ps_eq.needs_recheck = True

    card_eq = db_session.scalar(
        select(Card).where(Card.point_id == "jf.equals-hashcode", Card.active.is_(True))
    )
    assert card_eq is not None
    cs_eq = db_session.get(CardState, card_eq.id)
    if cs_eq is None:
        cs_eq = CardState(card_id=card_eq.id, lapses=3, state="review")
        db_session.add(cs_eq)
    else:
        cs_eq.lapses = 3
    db_session.commit()

    weak3 = client.get("/v1/weak", headers=AXUE).json()
    item_eq = next((it for it in weak3 if it["point_id"] == "jf.equals-hashcode"), None)
    assert item_eq is not None
    assert "rusty" in item_eq["reasons"]
    assert "needs_recheck" in item_eq["reasons"]
    assert "lapses_high" in item_eq["reasons"]

    # 4. 原因多的排前面
    # item_eq 有 3 个原因（rusty, lapses_high, needs_recheck），item_git 有 1 个原因（missing_evidence）
    assert weak3[0]["point_id"] == "jf.equals-hashcode"
    assert len(weak3[0]["reasons"]) > len(weak3[1]["reasons"])

    # 5. ?subject= 过滤生效
    sub_res = client.get("/v1/weak?subject=java-fde", headers=AXUE)
    assert sub_res.status_code == 200
    assert len(sub_res.json()) == 2

    sub_other = client.get("/v1/weak?subject=english", headers=AXUE)
    assert sub_other.status_code == 200
    assert sub_other.json() == []

    # 6. 没有弱项的点不出现（库里其它几十个点均不出现在 weak 列表里）
    all_weak_pids = {it["point_id"] for it in weak3}
    assert all_weak_pids == {"jf.equals-hashcode", "jf.git-secrets"}

    # 7. web 令牌也能读（200）
    web_res = client.get("/v1/weak", headers=WEB)
    assert web_res.status_code == 200
    assert len(web_res.json()) == 2


# ───────────────────────── GET /v1/recall ─────────────────────────


def test_get_recall(client: TestClient):
    _import_maps(client)

    today = today_local()

    # 建不同日期的课（今天-1、今天-3、今天-8、今天）
    dates_to_create = [
        today - timedelta(days=1),
        today - timedelta(days=3),
        today - timedelta(days=8),
        today,
    ]
    for d in dates_to_create:
        res = client.post(
            "/v1/sessions",
            json={
                "date": d.isoformat(),
                "point_ids": ["jf.git-secrets"],
                "summary": f"课次 {d}",
            },
            headers=AXUE,
        )
        assert res.status_code == 200, res.text

    # 给 jf.git-secrets 建一个 open 卡点
    blk_res = client.post(
        "/v1/blockers",
        json={"point_id": "jf.git-secrets", "title": "回顾卡点"},
        headers=AXUE,
    )
    assert blk_res.status_code == 200, blk_res.text
    blk_id = blk_res.json()["id"]

    # GET /v1/recall 默认 days="1,3,7"
    recall_res = client.get("/v1/recall?days=1,3,7", headers=AXUE)
    assert recall_res.status_code == 200, recall_res.text
    groups = recall_res.json()

    # 断言：
    # 1. 第一组 label=last 是今天之前最近一次（今天-1）
    assert len(groups) >= 3
    assert groups[0]["label"] == "last"
    assert groups[0]["date"] == (today - timedelta(days=1)).isoformat()
    assert groups[0]["days_ago"] == 1

    # 2. days=1,3,7 时 3 天前那课 label=3d
    g_3d = next((g for g in groups if g["label"] == "3d"), None)
    assert g_3d is not None
    assert g_3d["date"] == (today - timedelta(days=3)).isoformat()
    assert g_3d["days_ago"] == 3

    # 3. 7 天目标 ±1 天取到 8 天前那课（label=7d）
    g_7d = next((g for g in groups if g["label"] == "7d"), None)
    assert g_7d is not None
    assert g_7d["date"] == (today - timedelta(days=8)).isoformat()
    assert g_7d["days_ago"] == 8

    # 4. 今天的课不出现
    for g in groups:
        assert g["date"] != today.isoformat()
        assert g["days_ago"] > 0

    # 5. 同一天不重复出现
    group_dates = [g["date"] for g in groups]
    assert len(group_dates) == len(set(group_dates))

    # 6. 该课关联点的 open 卡点出现在该组 open_blockers
    for g in groups:
        open_ids = [b["id"] for b in g["open_blockers"]]
        assert blk_id in open_ids

    # 7. days 参数校验：days=abc、days=0、days=400 → 422
    assert client.get("/v1/recall?days=abc", headers=AXUE).status_code == 422
    assert client.get("/v1/recall?days=0", headers=AXUE).status_code == 422
    assert client.get("/v1/recall?days=400", headers=AXUE).status_code == 422


# ───────────────────────── GET /v1/summary/week ─────────────────────────


def test_get_summary_week(client: TestClient, db_session):
    _import_maps(client)

    today = today_local()
    weekday = today.weekday()
    mon = today - timedelta(days=weekday)

    # 本周建课：如果在周一就只建今天；如果不是周一，建周一和今天 2 次课
    session_dates = [mon] if weekday == 0 else [mon, today]
    for d in session_dates:
        r = client.post(
            "/v1/sessions",
            json={
                "date": d.isoformat(),
                "point_ids": ["jf.git-secrets"],
                "minutes": 30,
                "summary": f"本周课 {d}",
            },
            headers=AXUE,
        )
        assert r.status_code == 200, r.text

    # 若干复习（POST /v1/review）
    card = db_session.scalar(select(Card).where(Card.active.is_(True)))
    assert card is not None
    rev1 = client.post("/v1/review", json={"card_id": card.id, "rating": 3}, headers=AXUE)
    assert rev1.status_code == 200, rev1.text
    rev2 = client.post("/v1/review", json={"card_id": card.id, "rating": 4}, headers=AXUE)
    assert rev2.status_code == 200, rev2.text

    # 一个卡点后 resolve
    b_res = client.post("/v1/blockers", json={"title": "本周卡点"}, headers=AXUE)
    assert b_res.status_code == 200, b_res.text
    b_id = b_res.json()["id"]

    b_res_res = client.patch(
        f"/v1/blockers/{b_id}",
        json={"status": "resolved", "resolution": "本周已解决"},
        headers=AXUE,
    )
    assert b_res_res.status_code == 200, b_res_res.text

    # 自测证据让点变学过（jf.git-secrets 初始 available → learned）
    ev_res = client.post(
        "/v1/evidence",
        json={"point_id": "jf.git-secrets", "type": "selftest", "score": 2, "max": 5},
        headers=AXUE,
    )
    assert ev_res.status_code == 200, ev_res.text

    # GET /v1/summary/week?ago=0
    summary = client.get("/v1/summary/week?ago=0", headers=AXUE).json()
    assert summary["study_days"] == len(session_dates)
    assert summary["reviews"] == 2
    assert summary["acc"] == 1.0
    assert summary["blockers"]["opened"] == 1
    assert summary["blockers"]["resolved"] == 1

    # transitions.learned 包含 jf.git-secrets
    learned_transitions = summary["transitions"]["learned"]
    assert any(t["point_id"] == "jf.git-secrets" for t in learned_transitions)

    # ago=1 时这些为 0/空
    summary_ago1 = client.get("/v1/summary/week?ago=1", headers=AXUE).json()
    assert summary_ago1["study_days"] == 0
    assert summary_ago1["reviews"] == 0
    assert summary_ago1["acc"] is None
    assert summary_ago1["blockers"]["opened"] == 0
    assert summary_ago1["blockers"]["resolved"] == 0
    assert summary_ago1["transitions"]["learned"] == []

    # ago=-1 → 422
    assert client.get("/v1/summary/week?ago=-1", headers=AXUE).status_code == 422


# ───────────────────────── PATCH /v1/points/{id}/state ─────────────────────────


def test_patch_point_state(client: TestClient, db_session):
    _import_maps(client)

    # 1. 缺 reason 或 reason 空 → 422；不存在的点 → 404；web 令牌 → 403
    r_empty_reason = client.patch(
        "/v1/points/jf.git-secrets/state",
        json={"state": "mastered", "reason": ""},
        headers=AXUE,
    )
    assert r_empty_reason.status_code == 422

    r_missing_reason = client.patch(
        "/v1/points/jf.git-secrets/state",
        json={"state": "mastered"},
        headers=AXUE,
    )
    assert r_missing_reason.status_code == 422

    r_not_found = client.patch(
        "/v1/points/non_existent_point/state",
        json={"state": "mastered", "reason": "测试"},
        headers=AXUE,
    )
    assert r_not_found.status_code == 404

    r_web_forbidden = client.patch(
        "/v1/points/jf.git-secrets/state",
        json={"state": "mastered", "reason": "web 令牌尝试改状态"},
        headers=WEB,
    )
    assert r_web_forbidden.status_code == 403

    # 2. 覆盖成 mastered：返回 state=mastered、override_state=mastered
    # point_state.ever_mastered 仍为 False，learned_at 也不因覆盖而被设上；
    # point_state_log 有一条 cause=manual、note 含理由
    ps_before = db_session.get(PointState, "jf.git-secrets")
    assert ps_before.state == "available"
    assert ps_before.ever_mastered is False
    assert ps_before.learned_at is None

    cov_res = client.patch(
        "/v1/points/jf.git-secrets/state",
        json={"state": "mastered", "reason": "人工认证已掌握"},
        headers=AXUE,
    )
    assert cov_res.status_code == 200, cov_res.text
    cov_data = cov_res.json()
    assert cov_data["state"] == "mastered"
    assert cov_data["override_state"] == "mastered"

    db_session.expire_all()
    ps_after_cov = db_session.get(PointState, "jf.git-secrets")
    assert ps_after_cov.state == "mastered"
    assert ps_after_cov.override_state == "mastered"
    assert ps_after_cov.ever_mastered is False
    assert ps_after_cov.learned_at is None

    cov_log = db_session.scalars(
        select(PointStateLog)
        .where(PointStateLog.point_id == "jf.git-secrets")
        .order_by(PointStateLog.id.desc())
    ).first()
    assert cov_log is not None
    assert cov_log.cause == "manual"
    assert "人工认证已掌握" in (cov_log.note or "")

    # 3. 再 {"state": null, "reason": "撤销"} → 回到真实推导状态（覆盖前是什么就回到什么，例如 available）
    # override_state 为 None，又多一条 manual log（即使状态没变也要记，force_log）
    revoke_res = client.patch(
        "/v1/points/jf.git-secrets/state",
        json={"state": None, "reason": "撤销覆盖测试"},
        headers=AXUE,
    )
    assert revoke_res.status_code == 200, revoke_res.text
    revoke_data = revoke_res.json()
    assert revoke_data["state"] == "available"
    assert revoke_data["override_state"] is None

    db_session.expire_all()
    ps_after_revoke = db_session.get(PointState, "jf.git-secrets")
    assert ps_after_revoke.state == "available"
    assert ps_after_revoke.override_state is None

    revoke_log = db_session.scalars(
        select(PointStateLog)
        .where(PointStateLog.point_id == "jf.git-secrets")
        .order_by(PointStateLog.id.desc())
    ).first()
    assert revoke_log is not None
    assert revoke_log.cause == "manual"
    assert "撤销覆盖测试" in (revoke_log.note or "")

    # 4. 强制解锁：对一个 locked 点覆盖 available → state=available；
    # 它有了真实进展（例如 POST /v1/sessions 关联它）后 state 跟随推导（learning），不被 available 卡住
    ps_locked = db_session.get(PointState, "jf.hashmap")
    assert ps_locked is not None
    assert ps_locked.state == "locked"

    unlock_res = client.patch(
        "/v1/points/jf.hashmap/state",
        json={"state": "available", "reason": "提前解锁学习"},
        headers=AXUE,
    )
    assert unlock_res.status_code == 200, unlock_res.text
    assert unlock_res.json()["state"] == "available"
    assert unlock_res.json()["override_state"] == "available"

    # 有了真实进展（POST /v1/sessions 关联它）
    sess_res = client.post(
        "/v1/sessions",
        json={"date": "2026-10-07", "point_ids": ["jf.hashmap"], "summary": "学习 HashMap"},
        headers=AXUE,
    )
    assert sess_res.status_code == 200, sess_res.text

    db_session.expire_all()
    ps_progress = db_session.get(PointState, "jf.hashmap")
    # 跟随真实推导变 learning，不被 override_state=available 卡住
    assert ps_progress.state == "learning"
    assert ps_progress.override_state == "available"

    # 5. 防抖：用 db_session 造一个真实 mastered 的点
    # （直接改 point_state.state='mastered'、stats 里 derived_state='mastered'），
    # 覆盖成 learning 再撤销，撤销后应按 mastered→rusty 的防抖分支推导
    # （无复习数据时会落到 rusty，而不是 learned/available）
    ps_test = db_session.get(PointState, "jf.thread-basics")
    assert ps_test is not None
    ps_test.state = "mastered"
    ps_test.stats = {**(ps_test.stats or {}), "derived_state": "mastered"}
    db_session.commit()

    # 覆盖成 learning
    client.patch(
        "/v1/points/jf.thread-basics/state",
        json={"state": "learning", "reason": "临时覆盖为学习中"},
        headers=AXUE,
    )

    # 再撤销
    rev_test = client.patch(
        "/v1/points/jf.thread-basics/state",
        json={"state": None, "reason": "撤销回到推导状态"},
        headers=AXUE,
    )
    assert rev_test.status_code == 200, rev_test.text
    # 断言撤销后落到 rusty
    assert rev_test.json()["state"] == "rusty"
    assert rev_test.json()["override_state"] is None
