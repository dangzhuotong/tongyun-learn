"""axue_learning → tongyun_learn 迁移测试（定稿 P3b、决定 5；design-notes §6）。"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.learn_helpers import AXUE, learn_env, map_texts  # noqa: F401
from tongyun_learn.migrate_axue import (
    Source,
    migrate,
    parse_card,
    parse_express,
    parse_feynman,
)
from tongyun_learn.models import Blocker, Evidence, Point, PointState, SessionPoint, StudySession
from tongyun_learn.services.importer import import_maps

pytestmark = pytest.mark.usefixtures("learn_env")


# ───────────────────────── 纯函数参数化用例 ─────────────────────────


@pytest.mark.parametrize(
    ("notes", "expected_cues", "expected_summary", "expected_stuck"),
    [
        (
            "线索: 问题1；问题2\n总结: 总结内容\n卡点: 卡点内容",
            ["问题1", "问题2"],
            "总结内容",
            "卡点内容",
        ),
        (
            "线索：问题A; 问题B ；问题C\n总结：全角冒号总结\n卡点：全角冒号卡点",
            ["问题A", "问题B", "问题C"],
            "全角冒号总结",
            "全角冒号卡点",
        ),
        (
            "一些杂乱的文本，没有任何康奈尔格式",
            None,
            None,
            None,
        ),
        (
            None,
            None,
            None,
            None,
        ),
    ],
)
def test_parse_card(notes, expected_cues, expected_summary, expected_stuck):
    card = parse_card(notes)
    assert card.get("cues") == expected_cues
    assert card.get("总结") == expected_summary
    assert card.get("卡点") == expected_stuck


@pytest.mark.parametrize(
    ("notes", "expected"),
    [
        ("费曼:讲通", True),
        ("费曼：讲通", True),
        ("费曼 : 讲通", True),
        ("费曼:未讲通", False),
        ("费曼：未讲通", False),
        ("费曼:没讲通", False),
        ("费曼：没讲通", False),
        ("今天没有费曼测试", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_feynman(notes, expected):
    assert parse_feynman(notes) == expected


@pytest.mark.parametrize(
    ("notes", "expected_score", "expected_mx", "has_rubric", "expected_rubric"),
    [
        (
            "表达 6/8（结2原2例1坑1）",
            Decimal("6"),
            Decimal("8"),
            True,
            {"结论先行": 2.0, "原理": 2.0, "举例": 1.0, "踩坑": 1.0},
        ),
        (
            "表达：7/8",
            Decimal("7"),
            Decimal("8"),
            False,
            None,
        ),
        (
            "表达: 8/8",
            Decimal("8"),
            Decimal("8"),
            False,
            None,
        ),
        (
            "表达 6/8 结论先行2 原理2 举例1 踩坑1",
            Decimal("6"),
            Decimal("8"),
            True,
            {"结论先行": 2.0, "原理": 2.0, "举例": 1.0, "踩坑": 1.0},
        ),
        ("表达 9/8", None, None, False, None),  # 超分返回 None
        ("表达 5/0", None, None, False, None),  # mx <= 0 返回 None
        ("无表达内容", None, None, False, None),
        (None, None, None, False, None),
    ],
)
def test_parse_express(notes, expected_score, expected_mx, has_rubric, expected_rubric):
    res = parse_express(notes)
    if expected_score is None:
        assert res is None
    else:
        assert res is not None
        score, mx, rubric = res
        assert score == expected_score
        assert mx == expected_mx
        if has_rubric:
            assert rubric == expected_rubric
        else:
            assert rubric is None


# ───────────────────────── 迁移集成测试 ─────────────────────────


def _build_test_source() -> Source:
    return Source(
        lessons=[
            {
                "id": 1,
                "code": "W1D1",
                "week": 1,
                "day": 1,
                "area": "开发编程",
                "title": "Git与密钥安全",
                "file_path": "/workspace/personal/axue/lessons/week1/W1D1-Git与密钥安全.md",
                "status": "done",
                "sort_order": 11,
                "active": 1,
            },
            {
                "id": 2,
                "code": "W1D2",
                "week": 1,
                "day": 2,
                "area": "Web",
                "title": "HTTP一次请求全过程",
                "file_path": "/workspace/personal/axue/lessons/week1/W1D2-HTTP一次请求全过程.md",
                "status": "doing",
                "sort_order": 12,
                "active": 1,
            },
            {
                "id": 6,
                "code": "W2D1",
                "week": 2,
                "day": 1,
                "area": "开发编程",
                "title": "TypeScript 类型",
                "file_path": "/workspace/personal/axue/lessons/week2/W2D1-TypeScript类型.md",
                "status": "todo",
                "sort_order": 21,
                "active": 1,
            },
        ],
        sessions=[
            {
                "id": 4,
                "lesson_id": 1,
                "study_date": "2026-10-03",
                "minutes": None,
                "self_test_score": None,
                "self_test_total": None,
                "notes": "线索: 问题1；问题2\n总结: 总结内容\n卡点: 卡点内容",
                "created_at": "2026-10-03 21:00:00",
            },
            {
                "id": 5,
                "lesson_id": 2,
                "study_date": "2026-10-04",
                "minutes": 45,
                "self_test_score": 4,
                "self_test_total": 5,
                "notes": "线索: HTTP线索\n总结: HTTP总结\n卡点: HTTP卡点\n费曼:讲通\n表达 6/8（结2原2例1坑1）",
                "created_at": "2026-10-04 21:00:00",
            },
        ],
        blockers=[
            {
                "id": 2,
                "lesson_id": 1,
                "session_id": 4,
                "area": "开发编程",
                "description": "卡点2描述",
                "status": "未解决",
                "created_at": "2026-10-03 21:30:00",
                "resolved_at": None,
            },
            {
                "id": 3,
                "lesson_id": 1,
                "session_id": 4,
                "area": "开发编程",
                "description": "卡点3描述",
                "status": "未解决",
                "created_at": "2026-10-03 21:35:00",
                "resolved_at": None,
            },
            {
                "id": 1,
                "lesson_id": None,
                "session_id": None,
                "area": "Web",
                "description": "卡点1描述",
                "status": "已解决",
                "created_at": "2026-10-02 10:00:00",
                "resolved_at": "2026-10-02 11:00:00",
            },
        ],
        skill_mastery=[
            {"area": "开发编程", "level": "L2", "note": "熟悉", "updated_at": datetime(2026, 10, 1, 10, 0, 0)},
            {"area": "Web", "level": "L1", "note": "入门", "updated_at": datetime(2026, 10, 1, 10, 0, 0)},
            {"area": "AI", "level": "L2", "note": "熟练", "updated_at": datetime(2026, 10, 1, 10, 0, 0)},
            {"area": "英语", "level": "L3", "note": "流利", "updated_at": datetime(2026, 10, 1, 10, 0, 0)},
        ],
    )


def test_migrate_target_db_no_maps_error(db_session):
    """目标库没导地图时 → errors 非空、不写库。"""
    src = _build_test_source()
    res = migrate(db_session, src, dry_run=False)

    assert len(res["errors"]) > 0
    assert "目标库缺少映射用的知识点" in res["errors"][0]

    # 验证未写库
    assert db_session.scalar(select(func.count()).select_from(StudySession)) == 0
    assert db_session.scalar(select(func.count()).select_from(Blocker)) == 0
    assert db_session.scalar(select(func.count()).select_from(Evidence)) == 0


def test_migrate_dry_run_no_writes(db_session):
    """dry_run=True：跑完库里没有 sessions/blockers/evidence 行（报告 counts 照样有 created）。"""
    import_maps(db_session, map_texts(), dry_run=False)
    db_session.commit()

    src = _build_test_source()
    res = migrate(db_session, src, dry_run=True)

    assert res["errors"] == []
    assert res["counts"]["sessions"]["created"] == 2
    assert res["counts"]["blockers"]["created"] == 3

    # dry_run 回滚，库里应无新增 sessions/blockers/evidence 行
    assert db_session.scalar(select(func.count()).select_from(StudySession)) == 0
    assert db_session.scalar(select(func.count()).select_from(Blocker)) == 0
    assert db_session.scalar(select(func.count()).select_from(Evidence)) == 0


def test_migrate_commit_and_idempotence(client: TestClient, db_session):
    """完整 commit 迁移断言与幂等性验证。"""
    # 导入地图
    res_import = client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE)
    assert res_import.status_code == 200, res_import.text

    src = _build_test_source()
    res = migrate(db_session, src, dry_run=False)

    assert res["errors"] == []

    # 1. sessions 表 legacy_ref=axue:study_sessions:4 的课次
    s4 = db_session.scalar(select(StudySession).where(StudySession.legacy_ref == "axue:study_sessions:4"))
    assert s4 is not None
    assert s4.legacy_ref == "axue:study_sessions:4"
    assert s4.date == date(2026, 10, 3)
    assert s4.cues == ["问题1", "问题2"]
    assert s4.summary == "总结内容"
    assert s4.stuck == "卡点内容"
    assert s4.source == "migrate"

    # session_points 只挂 jf.git-secrets
    s4_pts = list(
        db_session.scalars(select(SessionPoint.point_id).where(SessionPoint.session_id == s4.id)).all()
    )
    assert s4_pts == ["jf.git-secrets"]

    # 2. blockers legacy_ref=axue:blockers:2 和 :3
    b2 = db_session.scalar(select(Blocker).where(Blocker.legacy_ref == "axue:blockers:2"))
    b3 = db_session.scalar(select(Blocker).where(Blocker.legacy_ref == "axue:blockers:3"))
    assert b2 is not None and b3 is not None
    assert b2.legacy_ref == "axue:blockers:2"
    assert b3.legacy_ref == "axue:blockers:3"
    assert b2.point_id == "jf.git-secrets"
    assert b3.point_id == "jf.git-secrets"
    assert b2.session_id == s4.id
    assert b3.session_id == s4.id
    assert b2.status == "open"
    assert b3.status == "open"
    assert b2.resolved_at is None
    assert b3.resolved_at is None

    # #1 → resolved、point_id 为空、detail 带领域
    b1 = db_session.scalar(select(Blocker).where(Blocker.legacy_ref == "axue:blockers:1"))
    assert b1 is not None
    assert b1.status == "resolved"
    assert b1.point_id is None
    assert "[axue_learning 领域：Web]" in (b1.detail or "")

    # 3. W1D2 建成 misc.w1d2（subject misc、tags 含 legacy），W2D1 不建点；
    #    GET /v1/next 里不出现任何 misc.* 点
    pt_w1d2 = db_session.get(Point, "misc.w1d2")
    assert pt_w1d2 is not None
    assert pt_w1d2.subject_id == "misc"
    assert "legacy" in (pt_w1d2.tags or [])

    pt_w2d1 = db_session.get(Point, "misc.w2d1")
    assert pt_w2d1 is None

    next_res = client.get("/v1/next", headers=AXUE)
    assert next_res.status_code == 200, next_res.text
    next_data = next_res.json()
    for item in next_data.get("next", []):
        assert not item["point_id"].startswith("misc.")
    for item in next_data.get("recheck", []):
        assert not item["point_id"].startswith("misc.")

    # 4. #5 生成 selftest(4/5 passed)、feynman(passed)、express(6/8 passed，rubric 四维 2/2/1/1) 三条证据
    #    reviewer=migrate，legacy_ref 分别以 :selftest/:feynman/:express 结尾；#4 不生成任何证据
    ev_selftest = db_session.scalar(
        select(Evidence).where(Evidence.legacy_ref == "axue:study_sessions:5:selftest")
    )
    assert ev_selftest is not None
    assert ev_selftest.type == "selftest"
    assert ev_selftest.score == Decimal("4")
    assert ev_selftest.max_score == Decimal("5")
    assert ev_selftest.passed is True
    assert ev_selftest.reviewer == "migrate"

    ev_feynman = db_session.scalar(
        select(Evidence).where(Evidence.legacy_ref == "axue:study_sessions:5:feynman")
    )
    assert ev_feynman is not None
    assert ev_feynman.type == "feynman"
    assert ev_feynman.passed is True
    assert ev_feynman.reviewer == "migrate"

    ev_express = db_session.scalar(
        select(Evidence).where(Evidence.legacy_ref == "axue:study_sessions:5:express")
    )
    assert ev_express is not None
    assert ev_express.type == "express"
    assert ev_express.score == Decimal("6")
    assert ev_express.max_score == Decimal("8")
    assert ev_express.passed is True
    assert ev_express.reviewer == "migrate"
    assert ev_express.rubric == {"结论先行": 2.0, "原理": 2.0, "举例": 1.0, "踩坑": 1.0}

    s4_evs = list(db_session.scalars(select(Evidence).where(Evidence.session_id == s4.id)).all())
    assert len(s4_evs) == 0

    # 5. jf.git-secrets 状态为 learning（有课次、无自测）
    ps_git = db_session.get(PointState, "jf.git-secrets")
    assert ps_git is not None
    assert ps_git.state == "learning"

    # 6. 报告 skill_mastery 原样带出 4 行，lessons 里有 W1D1 的 old_status 和 new_state
    assert len(res["skill_mastery"]) == 4
    assert [m["area"] for m in res["skill_mastery"]] == ["开发编程", "Web", "AI", "英语"]

    w1d1_rep = next(item for item in res["lessons"] if item["code"] == "W1D1")
    assert w1d1_rep["old_status"] == "done"
    assert w1d1_rep["new_state"] == "learning"

    # 7. 幂等：同一个 Source 再跑一次 commit，counts 里全部是 unchanged，表行数不变
    n_sessions_before = db_session.scalar(select(func.count()).select_from(StudySession))
    n_sp_before = db_session.scalar(select(func.count()).select_from(SessionPoint))
    n_blockers_before = db_session.scalar(select(func.count()).select_from(Blocker))
    n_ev_before = db_session.scalar(select(func.count()).select_from(Evidence))
    n_points_before = db_session.scalar(select(func.count()).select_from(Point))

    res2 = migrate(db_session, src, dry_run=False)
    assert res2["errors"] == []

    for kind, stats in res2["counts"].items():
        assert stats.get("created", 0) == 0, f"{kind} had created items on 2nd run"
        assert stats.get("updated", 0) == 0, f"{kind} had updated items on 2nd run"
        assert stats.get("unchanged", 0) > 0, f"{kind} had no unchanged items on 2nd run"

    assert db_session.scalar(select(func.count()).select_from(StudySession)) == n_sessions_before
    assert db_session.scalar(select(func.count()).select_from(SessionPoint)) == n_sp_before
    assert db_session.scalar(select(func.count()).select_from(Blocker)) == n_blockers_before
    assert db_session.scalar(select(func.count()).select_from(Evidence)) == n_ev_before
    assert db_session.scalar(select(func.count()).select_from(Point)) == n_points_before


def test_migrate_from_json_snapshot_skill_mastery_str_updated_at(db_session):
    """从 JSON 快照读入（updated_at 为 str）时能正常迁移（T2 发现：原先 _jsonable 遇 str 抛 TypeError）。"""
    import_maps(db_session, map_texts(), dry_run=False)
    db_session.commit()

    src = _build_test_source()
    src.skill_mastery = [
        {"area": "开发编程", "level": "L2", "note": "熟悉", "updated_at": "2026-10-01T10:00:00"},
    ]
    res = migrate(db_session, src, dry_run=True)
    assert res["errors"] == []
    assert res["skill_mastery"][0]["updated_at"] == "2026-10-01T10:00:00"


def test_snapshot_roundtrip_matches_direct(db_session, tmp_path):
    """源库读出来是 date/datetime/Decimal；导出快照再读回（变成字符串）迁移结果一致。"""
    from tongyun_learn.migrate_axue import read_source_json, write_snapshot

    import_maps(db_session, map_texts(), dry_run=False)
    db_session.commit()
    src = _build_test_source()
    for s in src.sessions:
        s["study_date"] = date.fromisoformat(s["study_date"])
        s["created_at"] = datetime.fromisoformat(s["created_at"])
    src.skill_mastery = [{"area": "AI", "level": 1, "note": "初始", "updated_at": datetime(2026, 10, 3, 9, 0)}]
    direct = migrate(db_session, src, dry_run=True)
    snap = tmp_path / "snap.json"
    write_snapshot(src, str(snap))
    via_json = migrate(db_session, read_source_json(str(snap)), dry_run=True)
    assert direct["errors"] == via_json["errors"] == []
    assert direct["counts"] == via_json["counts"]
    assert direct["point_changes"] == via_json["point_changes"]
    assert via_json["skill_mastery"][0]["updated_at"] == "2026-10-03T09:00:00"


def test_migrate_session_4_and_blockers_git_secrets_idempotence(db_session) -> None:
    """证明 axue session #4（2026-10-03 的课，没有分数）和卡点 #2、#3 会挂到知识点 jf.git-secrets 上，

    且重复跑迁移不会重复写入（按 legacy_ref 去重）。
    """
    # 1. 目标库导入知识地图（包含 jf.git-secrets）
    import_maps(db_session, map_texts(), dry_run=False)
    db_session.commit()

    # 2. 构造假造的 axue 旧数据
    # - session #4 指向 W1D1 那课（映射到 jf.git-secrets）、2026-10-03、没有分数
    # - 卡点 #2、#3 关联到这节课与 session #4，状态为未解决
    source = Source(
        lessons=[
            {
                "id": 1,
                "code": "W1D1",
                "week": 1,
                "day": 1,
                "area": "开发编程",
                "title": "Git与密钥安全",
                "file_path": "/workspace/personal/axue/lessons/week1/W1D1-Git与密钥安全.md",
                "status": "done",
                "sort_order": 11,
                "active": 1,
            },
        ],
        sessions=[
            {
                "id": 4,
                "lesson_id": 1,
                "study_date": "2026-10-03",
                "minutes": 50,
                "self_test_score": None,
                "self_test_total": None,
                "notes": "线索: Git与密钥安全；.gitignore\n总结: 掌握了git-secrets扫描\n卡点: pre-commit hook配置异常",
                "created_at": "2026-10-03 21:00:00",
            },
        ],
        blockers=[
            {
                "id": 2,
                "lesson_id": 1,
                "session_id": 4,
                "area": "开发编程",
                "description": "卡点2：pre-commit hook 误拦截合规密钥模板",
                "status": "未解决",
                "created_at": "2026-10-03 21:30:00",
                "resolved_at": None,
            },
            {
                "id": 3,
                "lesson_id": 1,
                "session_id": 4,
                "area": "开发编程",
                "description": "卡点3：清理历史 commit 敏感内容时重写历史失败",
                "status": "未解决",
                "created_at": "2026-10-03 21:35:00",
                "resolved_at": None,
            },
        ],
        skill_mastery=[],
    )

    # 3. 执行迁移（真写库）
    res1 = migrate(db_session, source, dry_run=False)
    assert res1["errors"] == []
    assert res1["counts"]["sessions"]["created"] == 1
    assert res1["counts"]["blockers"]["created"] == 2

    # 断言 1：这条课次挂在 jf.git-secrets 上，legacy_ref 能看出来源是 session 4，分数为空、不算成通过的证据
    s4 = db_session.scalar(select(StudySession).where(StudySession.legacy_ref == "axue:study_sessions:4"))
    assert s4 is not None
    assert s4.legacy_ref == "axue:study_sessions:4"
    assert s4.legacy_ref.endswith(":4")
    assert s4.date == date(2026, 10, 3)
    assert s4.source == "migrate"
    assert s4.lesson_ref == "W1D1"
    assert s4.summary == "掌握了git-secrets扫描"
    assert s4.stuck == "pre-commit hook配置异常"

    s4_pts = list(
        db_session.scalars(select(SessionPoint.point_id).where(SessionPoint.session_id == s4.id)).all()
    )
    assert s4_pts == ["jf.git-secrets"]

    # 分数为空：不生成任何 Evidence，不计入达标/通过证据
    s4_evs = list(db_session.scalars(select(Evidence).where(Evidence.session_id == s4.id)).all())
    assert len(s4_evs) == 0
    git_evs = list(db_session.scalars(select(Evidence).where(Evidence.point_id == "jf.git-secrets")).all())
    assert len(git_evs) == 0
    assert not any(e.passed for e in git_evs)

    # 知识点状态：有课次因此进入 learning，但无自测等通过证据，绝不计入 learned 或 mastered
    ps_git = db_session.get(PointState, "jf.git-secrets")
    assert ps_git is not None
    assert ps_git.state == "learning"
    assert ps_git.state not in ("learned", "mastered")
    assert ps_git.learned_at is None

    # 断言 2：卡点 #2、#3 挂在 jf.git-secrets 上，状态是未解决（open）
    b2 = db_session.scalar(select(Blocker).where(Blocker.legacy_ref == "axue:blockers:2"))
    b3 = db_session.scalar(select(Blocker).where(Blocker.legacy_ref == "axue:blockers:3"))
    assert b2 is not None and b3 is not None
    assert b2.legacy_ref == "axue:blockers:2"
    assert b3.legacy_ref == "axue:blockers:3"
    assert b2.point_id == "jf.git-secrets"
    assert b3.point_id == "jf.git-secrets"
    assert b2.session_id == s4.id
    assert b3.session_id == s4.id
    assert b2.status == "open"
    assert b3.status == "open"
    assert b2.resolved_at is None
    assert b3.resolved_at is None

    # 4. 记录数量基准
    n_sessions_before = db_session.scalar(select(func.count()).select_from(StudySession))
    n_blockers_before = db_session.scalar(select(func.count()).select_from(Blocker))
    n_sp_before = db_session.scalar(select(func.count()).select_from(SessionPoint))
    n_ev_before = db_session.scalar(select(func.count()).select_from(Evidence))

    # 断言 3：再跑一次迁移，课次和卡点的数量不变（按 legacy_ref 幂等去重）
    res2 = migrate(db_session, source, dry_run=False)
    assert res2["errors"] == []
    assert res2["counts"]["sessions"].get("created", 0) == 0
    assert res2["counts"]["sessions"].get("updated", 0) == 0
    assert res2["counts"]["sessions"].get("unchanged", 0) == 1
    assert res2["counts"]["blockers"].get("created", 0) == 0
    assert res2["counts"]["blockers"].get("updated", 0) == 0
    assert res2["counts"]["blockers"].get("unchanged", 0) == 2

    assert db_session.scalar(select(func.count()).select_from(StudySession)) == n_sessions_before
    assert db_session.scalar(select(func.count()).select_from(Blocker)) == n_blockers_before
    assert db_session.scalar(select(func.count()).select_from(SessionPoint)) == n_sp_before
    assert db_session.scalar(select(func.count()).select_from(Evidence)) == n_ev_before

    # 确认记录的数据库主键未变（没有删了重插）
    s4_after = db_session.scalar(select(StudySession).where(StudySession.legacy_ref == "axue:study_sessions:4"))
    b2_after = db_session.scalar(select(Blocker).where(Blocker.legacy_ref == "axue:blockers:2"))
    b3_after = db_session.scalar(select(Blocker).where(Blocker.legacy_ref == "axue:blockers:3"))
    assert s4_after.id == s4.id
    assert b2_after.id == b2.id
    assert b3_after.id == b3.id


def test_migrate_blocker_associated_by_session_fallback(db_session) -> None:
    """卡点未显式填写 lesson_id 但关联了 session_id 时，能从 session 继承知识点。"""
    import_maps(db_session, map_texts(), dry_run=False)
    db_session.commit()

    source = Source(
        lessons=[
            {
                "id": 1,
                "code": "W1D1",
                "title": "Git与密钥安全",
                "active": 1,
            },
        ],
        sessions=[
            {
                "id": 4,
                "lesson_id": 1,
                "study_date": "2026-10-03",
                "notes": "线索: 密钥安全",
                "created_at": "2026-10-03 21:00:00",
            },
        ],
        blockers=[
            {
                "id": 2,
                "lesson_id": None,  # lesson_id 为空
                "session_id": 4,     # 关联到 session #4
                "area": "开发编程",
                "description": "通过 session 关联到 jf.git-secrets 的卡点",
                "status": "未解决",
                "created_at": "2026-10-03 21:30:00",
            },
        ],
        skill_mastery=[],
    )

    res = migrate(db_session, source, dry_run=False)
    assert res["errors"] == []

    b2 = db_session.scalar(select(Blocker).where(Blocker.legacy_ref == "axue:blockers:2"))
    assert b2 is not None
    assert b2.point_id == "jf.git-secrets"
    assert b2.status == "open"

