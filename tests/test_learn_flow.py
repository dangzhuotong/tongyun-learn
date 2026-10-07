"""P3a 端到端冒烟：导入真实知识地图 → 队列 → 复习 → 课次/证据 → next/progress。"""

from fastapi.testclient import TestClient

from tests.learn_helpers import AXUE, WEB, learn_env, map_texts  # noqa: F401


def _import(client: TestClient, dry_run: bool) -> dict:
    r = client.post(f"/v1/maps/import?dry_run={str(dry_run).lower()}", json={"files": map_texts()}, headers=AXUE)
    assert r.status_code == 200, r.text
    return r.json()


def test_import_idempotent_and_counts(client: TestClient, learn_env):  # noqa: F811
    d = _import(client, True)
    assert d["errors"] == []
    assert client.get("/v1/subjects", headers=AXUE).json() == []  # dry run 不写库
    d = _import(client, False)
    res = {r["subject"]: r for r in d["results"]}
    assert res["tech-english"]["points"]["added"] == 28 and res["java-fde"]["points"]["added"] == 47
    total_cards = sum(r["example_cards"]["created"] for r in d["results"])
    assert total_cards == 133
    assert sum(r["prereqs"]["added"] for r in d["results"]) == 94
    d2 = _import(client, False)
    for r in d2["results"]:
        for group in ("stages", "points", "prereqs", "example_cards"):
            assert all(v == 0 for v in r[group].values()), (r["subject"], group, r[group])
    subs = {s["id"]: s for s in client.get("/v1/subjects", headers=WEB).json()}
    assert sum(sum(s["points_by_state"].values()) for s in subs.values()) == 75
    assert sum(s["points_by_state"].get("available", 0) for s in subs.values()) == 31


def test_web_cannot_write(client: TestClient, learn_env):  # noqa: F811
    r = client.post("/v1/maps/import?dry_run=true", json={"files": map_texts()}, headers=WEB)
    assert r.status_code == 403
    _import(client, False)
    assert client.post("/v1/sessions", json={"date": "2026-10-07", "summary": "x"}, headers=WEB).status_code == 403
    assert client.post("/v1/evidence", json={"point_id": "jf.java-basics", "type": "feynman", "passed": True},
                       headers=WEB).status_code == 403


def test_queue_review_session_evidence(client: TestClient, learn_env):  # noqa: F811
    _import(client, False)
    q = client.get("/v1/review/due?subject=java-fde&limit=50", headers=AXUE).json()
    assert q["review"] == []
    assert 0 < len(q["new"]) <= 8
    deep = [c for c in q["new"] if c["card_type"] in ("understand", "express")]
    assert len(deep) <= 3
    pts = {c["point_id"] for c in q["new"]}
    assert len(pts) <= 2  # 每学科每天最多开 2 个新点
    # 全局最多开 3 个新点
    qa = client.get("/v1/review/due?limit=200", headers=AXUE).json()
    word_decks = {d["id"] for d in client.get("/v1/decks", headers=AXUE).json() if d["kind"] == "en_word"}
    # 单词卡组的点（tags 含 en_word）不占新开点名额
    assert len({c["point_id"] for c in qa["new"] if c["point_id"] and c["deck_id"] not in word_decks}) <= 3
    assert any(c["deck_id"] in word_decks for c in qa["new"])
    # web 看不到动手卡
    qw = client.get("/v1/review/due?limit=200", headers=WEB).json()
    assert all(c["card_type"] != "handson" for c in qw["new"])

    card = q["new"][0]
    r = client.post("/v1/review", json={"card_id": card["card_id"], "rating": 3, "client_review_id": "r-1"},
                    headers=AXUE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is True
    assert {"point_id": card["point_id"], "from": "available", "to": "learning"} in body["point_changes"]
    r2 = client.post("/v1/review", json={"card_id": card["card_id"], "rating": 3, "client_review_id": "r-1"},
                     headers=AXUE)
    assert r2.json()["duplicate"] is True and r2.json()["applied"] is False

    # 课次：可学→学习中
    nxt = client.get("/v1/next?subject=java-fde&limit=5", headers=AXUE).json()
    assert nxt["recheck"] == []
    target = next(n for n in nxt["next"] if n["state"] == "available")["point_id"]
    s = client.post("/v1/sessions", json={"date": "2026-10-07", "point_ids": [target], "cues": ["为什么?"],
                                          "summary": "讲了一课"}, headers=AXUE)
    assert s.status_code == 200, s.text
    assert {"point_id": target, "from": "available", "to": "learning"} in s.json()["point_changes"]
    # 自测（分数不限）→ 学过
    e = client.post("/v1/evidence", json={"point_id": target, "type": "selftest", "score": 2, "max": 5,
                                          "session_id": s.json()["session_id"]}, headers=AXUE)
    assert e.status_code == 200, e.text
    assert e.json()["passed"] is False
    assert {"point_id": target, "from": "learning", "to": "learned"} in e.json()["point_changes"]
    # 阶段出口证据
    st = client.post("/v1/evidence", json={"stage_id": "jf.s1-core", "type": "selftest", "score": 4, "max": 5},
                     headers=AXUE)
    assert st.status_code == 200 and st.json()["passed"] is True
    p = client.get(f"/v1/points/{target}", headers=WEB).json()
    assert p["stats"]["state"] == "learned"
    assert p["stats"]["evidence"]["selftest"]["passed"] is False
    prog = client.get("/v1/progress?subject=java-fde", headers=WEB).json()
    assert prog["points_by_state"]["learned"] == 1
    assert len(prog["last7"]) == 7 and prog["last7"][-1]["reviews"] == 1
    m = client.get("/v1/subjects/java-fde/map", headers=WEB).json()
    assert len(m["stages"]) == 5 and sum(len(s["points"]) for s in m["stages"]) == 47


def test_en_word_batch(client: TestClient, learn_env):  # noqa: F811
    _import(client, False)
    items = [
        {"kind": "en_word", "word": "Concurrency", "dict_id": "cet4", "rating": 3, "errors": 1,
         "reviewed_at": "2026-10-07T09:00:00+08:00", "client_review_id": "w-1"},
        {"kind": "en_word", "word": "idempotent", "dict_id": "cet4", "rating": 4, "errors": 0,
         "reviewed_at": "2026-10-07T09:01:00+08:00", "client_review_id": "w-2"},
        {"kind": "en_word", "word": "concurrency", "dict_id": "cet4", "rating": 2,
         "reviewed_at": "2026-10-07T08:00:00+08:00", "client_review_id": "w-3"},  # 早于上次：只记日志
        {"kind": "en_word", "word": "idempotent", "rating": 4, "client_review_id": "w-2"},  # 重复
    ]
    r = client.post("/v1/review/batch", json={"items": items}, headers=WEB)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["duplicates"] == 1
    res = d["results"]
    assert res[0]["applied"] is True and res[1]["applied"] is True
    assert res[2]["card_id"] == res[0]["card_id"]
    # 按 reviewed_at 排序处理：08:00 那条最先处理，所以它是 applied；09:00 那条在后面也 applied
    assert res[2]["applied"] is True
    # idempotent 命中示例卡（同一卡组同一单词）
    p = client.get("/v1/points/en.vocab-general", headers=AXUE).json()
    fronts = {c["front"] for c in p["cards"]}
    assert "idempotent" in fronts and "concurrency" in fronts
    # 再发一条更早的：applied=0
    r = client.post("/v1/review", json={"kind": "en_word", "word": "concurrency", "rating": 1,
                                        "reviewed_at": "2026-10-07T07:00:00+08:00"}, headers=WEB)
    assert r.json()["applied"] is False
