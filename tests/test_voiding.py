"""Task E3a: 课次与证据软作废、GET /sessions 测试。"""

import os
import tempfile

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.learn_helpers import AXUE, WEB, learn_env, map_texts  # noqa: F401
from tongyun_learn.config import get_settings
from tongyun_learn.migrate_axue import migrate
from tongyun_learn.models import Card, Evidence, PointState, ReviewLog, StudySession
from tongyun_learn.timeutil import utcnow

pytestmark = pytest.mark.usefixtures("learn_env")


def _import_maps(client: TestClient) -> None:
    res = client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE)
    assert res.status_code == 200, res.text


def test_session_void_and_restore_flow(client: TestClient, db_session) -> None:
    _import_maps(client)

    # 挑两个开局 available 的点
    nxt = client.get("/v1/next?subject=java-fde&limit=5", headers=AXUE).json()
    avail = [n["point_id"] for n in nxt["next"] if n["state"] == "available"]
    assert len(avail) >= 2
    pt1, pt2 = avail[0], avail[1]

    # 1. pt1: 建课次（关联 pt1 -> learning）+ 一条自测证据（-> learned）
    r_sess1 = client.post(
        "/v1/sessions",
        json={"date": "2026-10-06", "point_ids": [pt1], "summary": "课次1"},
        headers=AXUE,
    ).json()
    sid1 = r_sess1["session_id"]
    assert db_session.get(PointState, pt1).state == "learning"

    r_ev1 = client.post(
        "/v1/evidence",
        json={"point_id": pt1, "session_id": sid1, "type": "selftest", "score": 5, "max": 5},
        headers=AXUE,
    ).json()
    ev_id1 = r_ev1["evidence_id"]
    assert db_session.get(PointState, pt1).state == "learned"

    # 2. pt2: 只建课次、不建证据（available -> learning）
    r_sess2 = client.post(
        "/v1/sessions",
        json={"date": "2026-10-06", "point_ids": [pt2], "summary": "课次2"},
        headers=AXUE,
    ).json()
    sid2 = r_sess2["session_id"]
    assert db_session.get(PointState, pt2).state == "learning"

    # 3. dry_run 作废 sid2：返回 dry_run: true 且库里没变
    r_dry = client.post(
        f"/v1/sessions/{sid2}/void?dry_run=true",
        json={"reason": "预演作废"},
        headers=AXUE,
    )
    assert r_dry.status_code == 200
    assert r_dry.json().get("dry_run") is True
    db_session.expire_all()
    assert db_session.get(StudySession, sid2).voided_at is None
    assert db_session.get(PointState, pt2).state == "learning"

    # 4. 真实作废 sid2：验证作废后 learning -> available
    r_void2 = client.post(
        f"/v1/sessions/{sid2}/void",
        json={"reason": "真正作废课次2"},
        headers=AXUE,
    )
    assert r_void2.status_code == 200
    db_session.expire_all()
    assert db_session.get(StudySession, sid2).voided_at is not None
    assert db_session.get(PointState, pt2).state == "available"

    # 5. 作废 sid1：级联作废其证据
    r_void1 = client.post(
        f"/v1/sessions/{sid1}/void",
        json={"reason": "课次1录入有误"},
        headers=AXUE,
    )
    assert r_void1.status_code == 200
    body_void1 = r_void1.json()
    assert body_void1["session_id"] == sid1
    assert body_void1["void_reason"] == "课次1录入有误"
    assert ev_id1 in body_void1["cascaded_evidence"]

    db_session.expire_all()
    ev1_row = db_session.get(Evidence, ev_id1)
    assert ev1_row.voided_at is not None
    assert ev1_row.void_reason == f"[课次#{sid1}] 课次1录入有误"
    # 作废按剩余数据重推：课次和自测都作废了，「学过」不再粘着，learned_at 一并撤掉
    ps1 = db_session.get(PointState, pt1)
    assert ps1.state == "available"
    assert ps1.learned_at is None
    assert {"point_id": pt1, "from": "learned", "to": "available"} in body_void1["point_changes"]

    # 6. GET /sessions 默认看不到已作废课次
    list_active = client.get("/v1/sessions", headers=AXUE).json()
    sids_active = [s["session_id"] for s in list_active]
    assert sid1 not in sids_active
    assert sid2 not in sids_active

    # GET /sessions?include_voided=true 能看到且带 voided_at
    list_all = client.get("/v1/sessions?include_voided=true", headers=AXUE).json()
    s1_item = next((s for s in list_all if s["session_id"] == sid1), None)
    assert s1_item is not None
    assert s1_item["voided_at"] is not None
    assert s1_item["void_reason"] == "课次1录入有误"
    assert len(s1_item["evidence"]) == 1
    assert s1_item["evidence"][0]["voided_at"] is not None

    # 7. GET /recall 和 GET /summary/week 不再统计作废课次
    recall_res = client.get("/v1/recall?days=1", headers=AXUE).json()
    recall_sids = [s["session_id"] for item in recall_res for s in item["sessions"]]
    assert sid1 not in recall_sids
    assert sid2 not in recall_sids

    week_res = client.get("/v1/summary/week?ago=0", headers=AXUE).json()
    week_sids = [s["session_id"] for s in week_res["sessions"]]
    assert sid1 not in week_sids
    assert sid2 not in week_sids
    assert week_res["evidence"].get("selftest", {}).get("total", 0) == 0

    # 8. restore 课次1：课次与级联证据恢复
    r_restore1 = client.post(f"/v1/sessions/{sid1}/restore", headers=AXUE)
    assert r_restore1.status_code == 200
    body_restore1 = r_restore1.json()
    assert body_restore1["session_id"] == sid1
    assert ev_id1 in body_restore1["restored_evidence"]

    db_session.expire_all()
    s1_db = db_session.get(StudySession, sid1)
    assert s1_db.voided_at is None
    assert s1_db.void_reason is None
    ev1_db = db_session.get(Evidence, ev_id1)
    assert ev1_db.voided_at is None
    assert ev1_db.void_reason is None
    # 恢复后回到学过；sid2 仍作废，pt2 仍是可学
    assert db_session.get(PointState, pt1).state == "learned"
    assert db_session.get(PointState, pt2).state == "available"

    # 9. 异常情况
    # 重复 void 已恢复后的课次或重复 void
    # sid2 当前处于作废状态，重复 void -> 409 already_voided
    res_dup_void = client.post(f"/v1/sessions/{sid2}/void", json={"reason": "dup"}, headers=AXUE)
    assert res_dup_void.status_code == 409
    assert res_dup_void.json()["error"]["code"] == "already_voided"

    # restore 未作废课次 -> 409 not_voided
    res_not_void = client.post(f"/v1/sessions/{sid1}/restore", headers=AXUE)
    assert res_not_void.status_code == 409
    assert res_not_void.json()["error"]["code"] == "not_voided"

    # 不存在的课次 -> 404 not_found
    res_not_found_v = client.post("/v1/sessions/999999/void", json={"reason": "none"}, headers=AXUE)
    assert res_not_found_v.status_code == 404
    assert res_not_found_v.json()["error"]["code"] == "not_found"

    res_not_found_r = client.post("/v1/sessions/999999/restore", headers=AXUE)
    assert res_not_found_r.status_code == 404
    assert res_not_found_r.json()["error"]["code"] == "not_found"

    # web 令牌无权写 -> 403
    res_web_v = client.post(f"/v1/sessions/{sid1}/void", json={"reason": "web"}, headers=WEB)
    assert res_web_v.status_code == 403
    res_web_r = client.post(f"/v1/sessions/{sid2}/restore", headers=WEB)
    assert res_web_r.status_code == 403


def test_evidence_void_and_restore_flow(client: TestClient, db_session) -> None:
    _import_maps(client)
    nxt = client.get("/v1/next?subject=java-fde&limit=5", headers=AXUE).json()
    pt = next(n["point_id"] for n in nxt["next"] if n["state"] == "available")

    # 创建一条 feynman 证据
    r_ev = client.post(
        "/v1/evidence",
        json={"point_id": pt, "type": "feynman", "passed": True, "notes": "讲通了"},
        headers=AXUE,
    ).json()
    ev_id = r_ev["evidence_id"]

    # GET /points/{id} 默认包含它，且带 voided_at=None, void_reason=None
    p_info = client.get(f"/v1/points/{pt}", headers=AXUE).json()
    assert any(e["id"] == ev_id for e in p_info["evidence"])
    assert p_info["stats"]["evidence"].get("feynman") is not None

    # 作废该证据
    r_void = client.post(f"/v1/evidence/{ev_id}/void", json={"reason": "误点达标"}, headers=AXUE)
    assert r_void.status_code == 200
    v_body = r_void.json()
    assert v_body["evidence_id"] == ev_id
    assert v_body["void_reason"] == "误点达标"
    assert v_body["voided_at"] is not None

    # GET /points/{id} 默认不再包含它，stats.evidence 也不再含该类型
    p_info2 = client.get(f"/v1/points/{pt}", headers=AXUE).json()
    assert not any(e["id"] == ev_id for e in p_info2["evidence"])
    assert p_info2["stats"]["evidence"].get("feynman") is None

    # GET /points/{id}?include_voided=true 包含它且有 voided_at
    p_info_all = client.get(f"/v1/points/{pt}?include_voided=true", headers=AXUE).json()
    target_e = next(e for e in p_info_all["evidence"] if e["id"] == ev_id)
    assert target_e["voided_at"] is not None
    assert target_e["void_reason"] == "误点达标"

    # 重复 void -> 409
    res_dup = client.post(f"/v1/evidence/{ev_id}/void", json={"reason": "dup"}, headers=AXUE)
    assert res_dup.status_code == 409
    assert res_dup.json()["error"]["code"] == "already_voided"

    # 恢复证据
    r_res = client.post(f"/v1/evidence/{ev_id}/restore", headers=AXUE)
    assert r_res.status_code == 200
    assert r_res.json()["voided_at"] is None
    assert r_res.json()["void_reason"] is None

    # 再次 GET /points/{id} 恢复出来
    p_info3 = client.get(f"/v1/points/{pt}", headers=AXUE).json()
    assert any(e["id"] == ev_id for e in p_info3["evidence"])
    assert p_info3["stats"]["evidence"].get("feynman") is not None

    # 测试所属课次作废中时不能单独恢复该证据：409 session_voided
    sess = client.post(
        "/v1/sessions",
        json={"date": "2026-10-06", "point_ids": [pt], "summary": "课次"},
        headers=AXUE,
    ).json()
    sid = sess["session_id"]
    ev_casc = client.post(
        "/v1/evidence",
        json={"point_id": pt, "session_id": sid, "type": "handson", "passed": True},
        headers=AXUE,
    ).json()
    ev_casc_id = ev_casc["evidence_id"]

    # 作废课次
    client.post(f"/v1/sessions/{sid}/void", json={"reason": "课次作废"}, headers=AXUE)
    # 单独恢复级联证据 -> 409 session_voided
    r_conflict = client.post(f"/v1/evidence/{ev_casc_id}/restore", headers=AXUE)
    assert r_conflict.status_code == 409
    assert r_conflict.json()["error"]["code"] == "session_voided"


def test_review_deduplication_voided(client: TestClient, db_session) -> None:
    _import_maps(client)
    # 找一张卡片
    card = db_session.scalar(select(Card).where(Card.active.is_(True)))
    assert card is not None

    crid = "crid-test-void-dedup-1"
    # 写入一条复习
    r1 = client.post(
        "/v1/review",
        json={"card_id": card.id, "rating": 3, "client_review_id": crid},
        headers=AXUE,
    ).json()
    assert r1.get("duplicate") is None or r1.get("duplicate") is False

    # 将该 review_log 置为 voided
    rev_log = db_session.scalar(select(ReviewLog).where(ReviewLog.client_review_id == crid))
    assert rev_log is not None
    rev_log.voided_at = utcnow()
    rev_log.void_reason = "测试作废"
    db_session.commit()

    # 重新发送同一 client_review_id
    r2 = client.post(
        "/v1/review",
        json={"card_id": card.id, "rating": 3, "client_review_id": crid},
        headers=AXUE,
    ).json()
    assert r2["duplicate"] is True
    assert r2["applied"] is False
    assert r2.get("voided") is True


def test_migrate_axue_preserves_voided_state(db_session) -> None:
    """迁移重跑不恢复已作废的课次 / 证据（作废列不在迁移的 upsert 字段里）。"""
    from tests.test_migrate_axue import _build_test_source
    from tongyun_learn.services.importer import import_maps

    import_maps(db_session, map_texts(), dry_run=False)
    db_session.commit()
    src = _build_test_source()
    rep = migrate(db_session, src, dry_run=False)
    assert rep["errors"] == []

    sess = db_session.scalar(select(StudySession).where(StudySession.legacy_ref == "axue:study_sessions:5"))
    ev = db_session.scalar(select(Evidence).where(Evidence.legacy_ref == "axue:study_sessions:5:selftest"))
    assert sess is not None and ev is not None
    now = utcnow()
    sess.voided_at, sess.void_reason = now, "人工作废旧课次"
    ev.voided_at, ev.void_reason = now, "人工作废旧证据"
    db_session.commit()

    rep2 = migrate(db_session, src, dry_run=False)
    assert rep2["errors"] == []
    assert rep2["counts"]["sessions"].get("created", 0) == 0
    assert rep2["counts"]["sessions"].get("updated", 0) == 0

    db_session.expire_all()
    sess_after = db_session.get(StudySession, sess.id)
    ev_after = db_session.get(Evidence, ev.id)
    assert sess_after.voided_at is not None and sess_after.void_reason == "人工作废旧课次"
    assert ev_after.voided_at is not None and ev_after.void_reason == "人工作废旧证据"


def test_alembic_downgrade_0001_and_upgrade_head() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = tmp.name
    tmp.close()

    old_url = os.environ.get("LEARN_DATABASE_URL")
    try:
        os.environ["LEARN_DATABASE_URL"] = f"sqlite:///{tmp_path}"
        get_settings.cache_clear()

        cfg = Config("alembic.ini")
        # 跑 upgrade head
        command.upgrade(cfg, "head")
        # downgrade 回 0001
        command.downgrade(cfg, "0001")
        # 再 upgrade head
        command.upgrade(cfg, "head")
    finally:
        if old_url is not None:
            os.environ["LEARN_DATABASE_URL"] = old_url
        else:
            os.environ.pop("LEARN_DATABASE_URL", None)
        get_settings.cache_clear()
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def test_void_guards(client: TestClient, db_session) -> None:
    """作废原因不能是空白；作废中的课次不能再挂证据 / 卡点；restore 的 reason 进状态日志。"""
    from tongyun_learn.models import PointStateLog

    _import_maps(client)
    nxt = client.get("/v1/next?subject=java-fde&limit=5", headers=AXUE).json()
    pt = next(n["point_id"] for n in nxt["next"] if n["state"] == "available")
    sid = client.post(
        "/v1/sessions", json={"date": "2026-10-06", "point_ids": [pt], "summary": "s"}, headers=AXUE
    ).json()["session_id"]

    r = client.post(f"/v1/sessions/{sid}/void", json={"reason": "   "}, headers=AXUE)
    assert r.status_code == 422
    assert client.post(f"/v1/sessions/{sid}/void", json={"reason": "录错日期"}, headers=AXUE).status_code == 200

    r = client.post(
        "/v1/evidence", json={"point_id": pt, "session_id": sid, "type": "feynman", "passed": True}, headers=AXUE
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "session_voided"
    r = client.post("/v1/blockers", json={"point_id": pt, "session_id": sid, "title": "卡住了"}, headers=AXUE)
    assert r.status_code == 409 and r.json()["error"]["code"] == "session_voided"

    r = client.post(f"/v1/sessions/{sid}/restore", json={"reason": "日期其实没错"}, headers=AXUE)
    assert r.status_code == 200
    assert r.json()["point_changes"] == [{"point_id": pt, "from": "available", "to": "learning"}]
    db_session.expire_all()
    logs = list(
        db_session.scalars(select(PointStateLog).where(PointStateLog.point_id == pt).order_by(PointStateLog.id))
    )
    assert [(lg.cause, lg.note) for lg in logs[-2:]] == [("void", "录错日期"), ("restore", "日期其实没错")]
