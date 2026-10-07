"""P3b 卡点（blockers）接口测试：POST /v1/blockers、PATCH /v1/blockers/{id}、GET /v1/blockers。"""

from fastapi.testclient import TestClient

from tests.learn_helpers import AXUE, WEB, learn_env, map_texts  # noqa: F401


def _import_maps(client: TestClient) -> None:
    res = client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE)
    assert res.status_code == 200, res.text


def test_create_blockers_and_stats(client: TestClient, learn_env):  # noqa: F811
    _import_maps(client)

    # 1. 都不带
    r1 = client.post(
        "/v1/blockers",
        json={"title": "卡点1 都不带", "detail": "详细描述1"},
        headers=AXUE,
    )
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["id"] is not None
    assert d1["point_id"] is None
    assert d1["point_title"] is None
    assert d1["session_id"] is None
    assert d1["title"] == "卡点1 都不带"
    assert d1["detail"] == "详细描述1"
    assert d1["status"] == "open"
    assert d1["resolution"] is None
    assert d1["legacy_ref"] is None
    assert d1["created_at"] is not None
    assert d1["resolved_at"] is None

    # 2. 带 point_id，检查 GET /v1/points/{id} 的 stats.open_blockers +1
    p_before = client.get("/v1/points/jf.equals-hashcode", headers=AXUE).json()
    assert p_before["stats"]["open_blockers"] == 0

    r2 = client.post(
        "/v1/blockers",
        json={"point_id": "jf.equals-hashcode", "title": "卡点2 带point"},
        headers=AXUE,
    )
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["point_id"] == "jf.equals-hashcode"
    assert d2["point_title"] == "equals / hashCode 与 String"

    p_after = client.get("/v1/points/jf.equals-hashcode", headers=AXUE).json()
    assert p_after["stats"]["open_blockers"] == 1

    # 3. 带 session_id
    s_res = client.post("/v1/sessions", json={"date": "2026-10-07", "summary": "课次"}, headers=AXUE)
    assert s_res.status_code == 200, s_res.text
    sid = s_res.json()["session_id"]

    r3 = client.post(
        "/v1/blockers",
        json={"session_id": sid, "title": "卡点3 带session"},
        headers=AXUE,
    )
    assert r3.status_code == 200, r3.text
    d3 = r3.json()
    assert d3["session_id"] == sid
    assert d3["title"] == "卡点3 带session"


def test_create_blocker_validation(client: TestClient, learn_env):  # noqa: F811
    _import_maps(client)

    # 不存在的 point → 404
    r_pt = client.post("/v1/blockers", json={"point_id": "non-existent-point", "title": "标题"}, headers=AXUE)
    assert r_pt.status_code == 404
    assert r_pt.json()["error"]["code"] == "point_not_found"

    # 不存在的 session → 404
    r_sess = client.post("/v1/blockers", json={"session_id": 999999, "title": "标题"}, headers=AXUE)
    assert r_sess.status_code == 404
    assert r_sess.json()["error"]["code"] == "session_not_found"

    # 空 title → 422
    r_empty_title = client.post("/v1/blockers", json={"title": ""}, headers=AXUE)
    assert r_empty_title.status_code == 422
    assert r_empty_title.json()["error"]["code"] == "invalid_title"

    r_blank_title = client.post("/v1/blockers", json={"title": "   "}, headers=AXUE)
    assert r_blank_title.status_code == 422
    assert r_blank_title.json()["error"]["code"] == "invalid_title"

    # 多余字段 → 422
    r_extra = client.post("/v1/blockers", json={"title": "合规标题", "extra_prop": 123}, headers=AXUE)
    assert r_extra.status_code == 422


def test_patch_blocker(client: TestClient, learn_env):  # noqa: F811
    _import_maps(client)

    # 不存在的 id → 404
    r_404 = client.patch("/v1/blockers/999999", json={"status": "resolved"}, headers=AXUE)
    assert r_404.status_code == 404
    assert r_404.json()["error"]["code"] == "not_found"

    # 创建一个关联 jf.equals-hashcode 的卡点
    cb = client.post(
        "/v1/blockers",
        json={"point_id": "jf.equals-hashcode", "title": "卡点用于patch"},
        headers=AXUE,
    ).json()
    bid = cb["id"]

    # 此时 open_blockers 为 1
    assert client.get("/v1/points/jf.equals-hashcode", headers=AXUE).json()["stats"]["open_blockers"] == 1

    # 空 body → 422
    r_empty = client.patch(f"/v1/blockers/{bid}", json={}, headers=AXUE)
    assert r_empty.status_code == 422
    assert r_empty.json()["error"]["code"] == "empty_patch"

    r_nulls = client.patch(f"/v1/blockers/{bid}", json={"status": None, "resolution": None}, headers=AXUE)
    assert r_nulls.status_code == 422
    assert r_nulls.json()["error"]["code"] == "empty_patch"

    # 多余字段 → 422
    r_extra = client.patch(f"/v1/blockers/{bid}", json={"status": "resolved", "extra": 1}, headers=AXUE)
    assert r_extra.status_code == 422

    # PATCH 成 resolved → resolved_at 有值、open_blockers -1
    r_res = client.patch(
        f"/v1/blockers/{bid}",
        json={"status": "resolved", "resolution": "解决说明"},
        headers=AXUE,
    )
    assert r_res.status_code == 200
    d_res = r_res.json()
    assert d_res["status"] == "resolved"
    assert d_res["resolution"] == "解决说明"
    assert d_res["resolved_at"] is not None

    # open_blockers 减 1
    assert client.get("/v1/points/jf.equals-hashcode", headers=AXUE).json()["stats"]["open_blockers"] == 0

    # 再 PATCH 回 open → resolved_at 为 None
    r_open = client.patch(f"/v1/blockers/{bid}", json={"status": "open"}, headers=AXUE)
    assert r_open.status_code == 200
    d_open = r_open.json()
    assert d_open["status"] == "open"
    assert d_open["resolved_at"] is None
    # resolution 保持原值
    assert d_open["resolution"] == "解决说明"

    # open_blockers 恢复为 1
    assert client.get("/v1/points/jf.equals-hashcode", headers=AXUE).json()["stats"]["open_blockers"] == 1

    # dropped 也有 resolved_at
    r_drop = client.patch(f"/v1/blockers/{bid}", json={"status": "dropped"}, headers=AXUE)
    assert r_drop.status_code == 200
    d_drop = r_drop.json()
    assert d_drop["status"] == "dropped"
    assert d_drop["resolved_at"] is not None

    # resolution 可单独改，且已有 resolved_at 时不覆盖
    r_only_res = client.patch(f"/v1/blockers/{bid}", json={"resolution": "更新方案"}, headers=AXUE)
    assert r_only_res.status_code == 200
    d_only_res = r_only_res.json()
    assert d_only_res["resolution"] == "更新方案"
    assert d_only_res["status"] == "dropped"
    assert d_only_res["resolved_at"] == d_drop["resolved_at"]


def test_list_blockers_filter_and_sort(client: TestClient, learn_env):  # noqa: F811
    _import_maps(client)

    b1 = client.post("/v1/blockers", json={"point_id": "jf.equals-hashcode", "title": "b1"}, headers=AXUE).json()
    b2 = client.post("/v1/blockers", json={"point_id": "jf.equals-hashcode", "title": "b2"}, headers=AXUE).json()
    b3 = client.post("/v1/blockers", json={"point_id": "en.vocab-general", "title": "b3"}, headers=AXUE).json()
    b4 = client.post("/v1/blockers", json={"point_id": "en.vocab-general", "title": "b4"}, headers=AXUE).json()

    # 将 b1 改为 resolved，b4 改为 dropped
    client.patch(f"/v1/blockers/{b1['id']}", json={"status": "resolved"}, headers=AXUE)
    client.patch(f"/v1/blockers/{b4['id']}", json={"status": "dropped"}, headers=AXUE)

    # 1. 过滤 status
    res_open = client.get("/v1/blockers?status=open", headers=AXUE).json()
    assert [x["id"] for x in res_open] == [b2["id"], b3["id"]]

    res_resolved = client.get("/v1/blockers?status=resolved", headers=AXUE).json()
    assert [x["id"] for x in res_resolved] == [b1["id"]]

    res_dropped = client.get("/v1/blockers?status=dropped", headers=AXUE).json()
    assert [x["id"] for x in res_dropped] == [b4["id"]]

    # status 非法值 → 422
    r_inv = client.get("/v1/blockers?status=invalid_status", headers=AXUE)
    assert r_inv.status_code == 422

    # 2. 过滤 point
    res_pt = client.get("/v1/blockers?point=jf.equals-hashcode", headers=AXUE).json()
    # open 在前：b2 (open) 排在 b1 (resolved) 前
    assert [x["id"] for x in res_pt] == [b2["id"], b1["id"]]

    # 3. 全量排序：open 在前，然后 created_at 升序、id 升序
    res_all = client.get("/v1/blockers", headers=AXUE).json()
    statuses = [x["status"] for x in res_all]
    assert statuses == ["open", "open", "resolved", "dropped"]
    assert [x["id"] for x in res_all] == [b2["id"], b3["id"], b1["id"], b4["id"]]

    # 4. limit 参数
    res_limit = client.get("/v1/blockers?limit=2", headers=AXUE).json()
    assert len(res_limit) == 2
    assert [x["id"] for x in res_limit] == [b2["id"], b3["id"]]

    assert client.get("/v1/blockers?limit=0", headers=AXUE).status_code == 422
    assert client.get("/v1/blockers?limit=501", headers=AXUE).status_code == 422


def test_auth_permissions(client: TestClient, learn_env):  # noqa: F811
    _import_maps(client)

    # axue 可以读写
    r_create = client.post("/v1/blockers", json={"title": "axue卡点"}, headers=AXUE)
    assert r_create.status_code == 200
    bid = r_create.json()["id"]

    # web 令牌：GET 200
    r_get = client.get("/v1/blockers", headers=WEB)
    assert r_get.status_code == 200
    assert len(r_get.json()) >= 1

    # web 令牌：POST 403
    r_post_web = client.post("/v1/blockers", json={"title": "web卡点"}, headers=WEB)
    assert r_post_web.status_code == 403

    # web 令牌：PATCH 403
    r_patch_web = client.patch(f"/v1/blockers/{bid}", json={"status": "resolved"}, headers=WEB)
    assert r_patch_web.status_code == 403
