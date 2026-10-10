"""学习看板（TypeWords learn-board）与 tongyun-learn 6 个接口的契约回归测试。

契约锁定的 6 个只读接口（前端类型定义见 /workspace/tongyun-words/app/tongyun/learn-board-api.ts）：
1. GET /v1/subjects -> Subject[]
2. GET /v1/subjects/{id}/map -> SubjectMap
3. GET /v1/next?limit=5 -> NextResp
4. GET /v1/review/due?limit=5 -> ReviewDueResp
5. GET /v1/progress?subject= -> ProgressResp
6. GET /v1/blockers?status=open -> Blocker[]
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.learn_helpers import AXUE, WEB, learn_env, map_texts  # noqa: F401
from tongyun_learn.models import Card, CardState, PointState
from tongyun_learn.timeutil import utcnow

pytestmark = pytest.mark.usefixtures("learn_env")


# ───────────────────────── 契约类型断言辅助函数 ─────────────────────────


def assert_subject_contract(sub: dict) -> None:
    """断言符合 learn-board-api.ts 的 Subject 接口定义。"""
    assert isinstance(sub, dict)
    assert "id" in sub and isinstance(sub["id"], str) and sub["id"]
    assert "title" in sub and isinstance(sub["title"], str) and sub["title"]
    assert "points_by_state" in sub and isinstance(sub["points_by_state"], dict)
    for state_key, count in sub["points_by_state"].items():
        assert isinstance(state_key, str)
        assert isinstance(count, int) and not isinstance(count, bool)

    # 可选字段 goal?: string | null
    if "goal" in sub and sub["goal"] is not None:
        assert isinstance(sub["goal"], str)


def assert_subject_map_contract(map_data: dict) -> None:
    """断言符合 learn-board-api.ts 的 SubjectMap 接口定义。"""
    assert isinstance(map_data, dict)
    assert "subject" in map_data and isinstance(map_data["subject"], dict)
    assert "id" in map_data["subject"] and isinstance(map_data["subject"]["id"], str)
    assert "title" in map_data["subject"] and isinstance(map_data["subject"]["title"], str)

    assert "stages" in map_data and isinstance(map_data["stages"], list)
    assert len(map_data["stages"]) > 0

    for stage in map_data["stages"]:
        assert isinstance(stage, dict)
        assert "id" in stage and isinstance(stage["id"], str)
        assert "title" in stage and isinstance(stage["title"], str)
        assert "ord" in stage and isinstance(stage["ord"], int) and not isinstance(stage["ord"], bool)
        assert "passed" in stage and isinstance(stage["passed"], bool)
        assert "points" in stage and isinstance(stage["points"], list)

        for pt in stage["points"]:
            assert isinstance(pt, dict)
            assert "id" in pt and isinstance(pt["id"], str)
            assert "title" in pt and isinstance(pt["title"], str)

            # 可选字段 ord?: number | null
            if "ord" in pt and pt["ord"] is not None:
                assert isinstance(pt["ord"], int) and not isinstance(pt["ord"], bool)

            # prereqs: MapPrereq[]
            assert "prereqs" in pt and isinstance(pt["prereqs"], list)
            for pre in pt["prereqs"]:
                assert isinstance(pre, dict)
                assert "id" in pre and isinstance(pre["id"], str)
                assert "kind" in pre and isinstance(pre["kind"], str)

            # stats: { state: string | null; [k: string]: any }
            assert "stats" in pt and isinstance(pt["stats"], dict)
            assert "state" in pt["stats"]
            assert pt["stats"]["state"] is None or isinstance(pt["stats"]["state"], str)


def assert_next_resp_contract(next_data: dict) -> None:
    """断言符合 learn-board-api.ts 的 NextResp 接口定义。"""
    assert isinstance(next_data, dict)

    # recheck: RecheckItem[]
    assert "recheck" in next_data and isinstance(next_data["recheck"], list)
    for item in next_data["recheck"]:
        assert isinstance(item, dict)
        assert "point_id" in item and isinstance(item["point_id"], str)
        assert "title" in item and isinstance(item["title"], str)

    # next: NextItem[]
    assert "next" in next_data and isinstance(next_data["next"], list)
    for item in next_data["next"]:
        assert isinstance(item, dict)
        assert "point_id" in item and isinstance(item["point_id"], str)
        assert "title" in item and isinstance(item["title"], str)
        assert "state" in item and isinstance(item["state"], str)
        assert "reason" in item and isinstance(item["reason"], str)
        assert "opens_today" in item and isinstance(item["opens_today"], bool)

        # 可选字段
        if "subject_id" in item and item["subject_id"] is not None:
            assert isinstance(item["subject_id"], str)
        if "stage_title" in item and item["stage_title"] is not None:
            assert isinstance(item["stage_title"], str)
        if "opened_today" in item and item["opened_today"] is not None:
            assert isinstance(item["opened_today"], bool)
        if "open_blockers" in item and item["open_blockers"] is not None:
            assert isinstance(item["open_blockers"], int) and not isinstance(item["open_blockers"], bool)

    # new_point_quota: { global_left: number; by_subject_left: Record<string, number> }
    assert "new_point_quota" in next_data and isinstance(next_data["new_point_quota"], dict)
    quota = next_data["new_point_quota"]
    assert "global_left" in quota
    assert isinstance(quota["global_left"], int) and not isinstance(quota["global_left"], bool)
    assert "by_subject_left" in quota and isinstance(quota["by_subject_left"], dict)
    for sub_id, left in quota["by_subject_left"].items():
        assert isinstance(sub_id, str)
        assert isinstance(left, int) and not isinstance(left, bool)


def assert_review_due_resp_contract(due_data: dict) -> None:
    """断言符合 learn-board-api.ts 的 ReviewDueResp 接口定义。"""
    assert isinstance(due_data, dict)

    assert "review" in due_data and isinstance(due_data["review"], list)
    assert "new" in due_data and isinstance(due_data["new"], list)

    for card in due_data["review"] + due_data["new"]:
        assert isinstance(card, dict)
        assert "card_id" in card and isinstance(card["card_id"], int) and not isinstance(card["card_id"], bool)
        assert "front" in card and isinstance(card["front"], str)
        if "card_type" in card and card["card_type"] is not None:
            assert isinstance(card["card_type"], str)
        if "point_id" in card and card["point_id"] is not None:
            assert isinstance(card["point_id"], str)

    # counts: { due_total: number; [k: string]: any }
    assert "counts" in due_data and isinstance(due_data["counts"], dict)
    assert "due_total" in due_data["counts"]
    assert isinstance(due_data["counts"]["due_total"], int) and not isinstance(due_data["counts"]["due_total"], bool)


def assert_progress_resp_contract(prog_data: dict) -> None:
    """断言符合 learn-board-api.ts 的 ProgressResp 接口定义。"""
    assert isinstance(prog_data, dict)
    assert "retention_30d" in prog_data
    ret = prog_data["retention_30d"]
    assert ret is None or (isinstance(ret, (int, float)) and not isinstance(ret, bool))


def assert_blocker_contract(blocker: dict) -> None:
    """断言符合 learn-board-api.ts 的 Blocker 接口定义。"""
    assert isinstance(blocker, dict)
    assert "id" in blocker and isinstance(blocker["id"], int) and not isinstance(blocker["id"], bool)
    assert "title" in blocker and isinstance(blocker["title"], str)
    assert "status" in blocker and isinstance(blocker["status"], str)

    # 可选/可为 null 字段
    if "point_id" in blocker and blocker["point_id"] is not None:
        assert isinstance(blocker["point_id"], str)
    if "point_title" in blocker and blocker["point_title"] is not None:
        assert isinstance(blocker["point_title"], str)
    if "detail" in blocker and blocker["detail"] is not None:
        assert isinstance(blocker["detail"], str)
    if "created_at" in blocker and blocker["created_at"] is not None:
        assert isinstance(blocker["created_at"], str)


# ───────────────────────── 测试夹具 ─────────────────────────


@pytest.fixture
def board_fixture(client: TestClient) -> dict:
    """导入英语和 Java 两门学科，并预先生成一条 open 卡点。"""
    # 1. 导入两门科目（tech-english 与 java-fde）
    res_import = client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE)
    assert res_import.status_code == 200, res_import.text

    # 2. 造一条 open 卡点（关联知识点）
    res_blk = client.post(
        "/v1/blockers",
        json={
            "point_id": "jf.equals-hashcode",
            "title": "看板契约测试卡点：equals实现混淆",
            "detail": "对 equals 与 hashCode 契约关系存在疑惑",
        },
        headers=AXUE,
    )
    assert res_blk.status_code == 200, res_blk.text
    created_blocker = res_blk.json()
    return created_blocker


# ───────────────────────── 契约回归测试用例 ─────────────────────────


def test_board_endpoints_unauthorized(client: TestClient, board_fixture: dict):
    """未带令牌或携带无效令牌时，看板调用的 6 个接口均应返回 401。"""
    endpoints = [
        "/v1/subjects",
        "/v1/subjects/tech-english/map",
        "/v1/next?limit=5",
        "/v1/review/due?limit=5",
        "/v1/progress?subject=",
        "/v1/blockers?status=open",
    ]

    for ep in endpoints:
        # 完全不带令牌
        r_no_token = client.get(ep)
        assert r_no_token.status_code == 401, f"{ep} 没有令牌时未返回 401 (got {r_no_token.status_code})"
        assert r_no_token.json()["error"]["code"] == "unauthorized"

        # 携带错误令牌
        r_bad_token = client.get(ep, headers={"Authorization": "Bearer bad-token"})
        assert r_bad_token.status_code == 401, f"{ep} 携带无效令牌时未返回 401 (got {r_bad_token.status_code})"
        assert r_bad_token.json()["error"]["code"] == "unauthorized"


def test_contract_get_subjects(client: TestClient, board_fixture: dict):
    """测试 GET /v1/subjects 接口契约：

    - 状态码 200；
    - 返回数组，元素符合 Subject 接口定义；
    - 至少包含英语 (tech-english) 和 Java (java-fde) 两个科目（防止仅返回单一科目回归）。
    """
    res = client.get("/v1/subjects", headers=WEB)
    assert res.status_code == 200, res.text
    subjects = res.json()
    assert isinstance(subjects, list)
    assert len(subjects) >= 2

    # 字段契约检查
    for sub in subjects:
        assert_subject_contract(sub)

    subject_ids = {s["id"] for s in subjects}
    assert "tech-english" in subject_ids, "未包含英语学科 (tech-english)"
    assert "java-fde" in subject_ids, "未包含 Java 学科 (java-fde)"


def test_contract_get_subject_map(client: TestClient, board_fixture: dict):
    """测试 GET /v1/subjects/{id}/map 接口契约：

    - 对 tech-english 与 java-fde 分别请求；
    - 状态码 200；
    - 返回结构符合 SubjectMap 接口定义。
    """
    for sub_id in ["tech-english", "java-fde"]:
        res = client.get(f"/v1/subjects/{sub_id}/map", headers=WEB)
        assert res.status_code == 200, res.text
        data = res.json()
        assert_subject_map_contract(data)
        assert data["subject"]["id"] == sub_id


def test_contract_get_next(client: TestClient, board_fixture: dict, db_session):
    """测试 GET /v1/next?limit=5 接口契约：

    - 状态码 200；
    - 返回结构符合 NextResp 接口定义；
    - 测试包含待复查 (recheck) 与推荐下一步 (next) 元素时的类型契约。
    """
    # 构造一条待复查知识点，确保 recheck 列表有元素被校验
    ps = db_session.get(PointState, "jf.equals-hashcode")
    assert ps is not None
    ps.needs_recheck = True
    db_session.commit()

    res = client.get("/v1/next?limit=5", headers=WEB)
    assert res.status_code == 200, res.text
    data = res.json()
    assert_next_resp_contract(data)

    assert len(data["recheck"]) >= 1
    assert any(item["point_id"] == "jf.equals-hashcode" for item in data["recheck"])
    assert len(data["next"]) >= 1


def test_contract_get_review_due(client: TestClient, board_fixture: dict, db_session):
    """测试 GET /v1/review/due?limit=5 接口契约：

    - 状态码 200；
    - 返回结构符合 ReviewDueResp 接口定义；
    - 验证 review 与 new 队列中卡片的字段与类型。
    """
    # 构造一张已到期的复习卡片，确保 review 队列有元素被校验
    card = db_session.scalar(select(Card).where(Card.active.is_(True)))
    assert card is not None
    cs = db_session.get(CardState, card.id)
    if cs is None:
        cs = CardState(card_id=card.id, state=2, due=utcnow() - timedelta(days=1), reps=1)
        db_session.add(cs)
    else:
        cs.state = 2
        cs.due = utcnow() - timedelta(days=1)
    db_session.commit()

    res = client.get("/v1/review/due?limit=5", headers=WEB)
    assert res.status_code == 200, res.text
    data = res.json()
    assert_review_due_resp_contract(data)

    assert data["counts"]["due_total"] >= 1
    assert len(data["review"]) >= 1
    assert len(data["new"]) >= 1


def test_contract_get_progress(client: TestClient, board_fixture: dict):
    """测试 GET /v1/progress 接口契约：

    - 带 subject= 参数与不带参数均返回 200；
    - 带具体科目参数（tech-english、java-fde）返回 200；
    - 返回结构符合 ProgressResp 接口定义（保留 retention_30d 字段且可为 null 或数字）。
    """
    # 1. GET /v1/progress?subject=
    res_empty_subj = client.get("/v1/progress?subject=", headers=WEB)
    assert res_empty_subj.status_code == 200, res_empty_subj.text
    assert_progress_resp_contract(res_empty_subj.json())

    # 2. GET /v1/progress
    res_all = client.get("/v1/progress", headers=WEB)
    assert res_all.status_code == 200, res_all.text
    assert_progress_resp_contract(res_all.json())

    # 3. 各学科 progress
    for sub_id in ["tech-english", "java-fde"]:
        res_sub = client.get(f"/v1/progress?subject={sub_id}", headers=WEB)
        assert res_sub.status_code == 200, res_sub.text
        assert_progress_resp_contract(res_sub.json())


def test_contract_get_blockers_and_filter(client: TestClient, board_fixture: dict):
    """测试 GET /v1/blockers?status=open 接口契约：

    - 状态码 200；
    - 返回符合 Blocker 接口定义；
    - status=open 时能看到新造的 open 卡点；
    - 当卡点更新为 resolved 后，status=open 列表中看不到该卡点，status=resolved 列表中能看到。
    """
    blk_id = board_fixture["id"]

    # 1. status=open 能够查到新创建的卡点
    res_open = client.get("/v1/blockers?status=open", headers=WEB)
    assert res_open.status_code == 200, res_open.text
    blockers_open = res_open.json()
    assert isinstance(blockers_open, list)
    target = next((b for b in blockers_open if b["id"] == blk_id), None)
    assert target is not None, f"未在 status=open 列表中找到卡点 id={blk_id}"
    assert_blocker_contract(target)
    assert target["status"] == "open"
    assert target["title"] == board_fixture["title"]
    assert target["point_id"] == "jf.equals-hashcode"
    assert target["point_title"] == "equals / hashCode 与 String"

    # 2. 将卡点改为 resolved
    patch_res = client.patch(
        f"/v1/blockers/{blk_id}",
        json={"status": "resolved", "resolution": "测试解决卡点说明"},
        headers=AXUE,
    )
    assert patch_res.status_code == 200, patch_res.text

    # 3. 再次查询 status=open，看不到该卡点
    res_open_again = client.get("/v1/blockers?status=open", headers=WEB)
    assert res_open_again.status_code == 200, res_open_again.text
    open_ids_again = [b["id"] for b in res_open_again.json()]
    assert blk_id not in open_ids_again, f"已解决的卡点 id={blk_id} 仍出现在 status=open 列表中"

    # 4. 查询 status=resolved，能看到该卡点
    res_resolved = client.get("/v1/blockers?status=resolved", headers=WEB)
    assert res_resolved.status_code == 200, res_resolved.text
    resolved_ids = [b["id"] for b in res_resolved.json()]
    assert blk_id in resolved_ids, f"已解决的卡点 id={blk_id} 未出现在 status=resolved 列表中"
