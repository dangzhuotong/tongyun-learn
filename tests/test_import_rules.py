"""地图导入规则与边界测试（PRD §2 + 决定 4）。

覆盖：
1. 校验失败原子回滚（schema 错误、指向不存在前置、前置成环，库里不写任何数据）
2. 停用与恢复（YAML 删点再导入 active=0 示例卡停用；再加回 reactivated=1 示例卡恢复）
3. 阿学修改/替换过的示例卡不被覆盖（created_by=axue，重导入计 kept_edited，不恢复成 example）
4. 修改 YAML 里示例卡 back → example_cards.updated=1
5. 单独导入 english.yaml（跨学科软前置使用库里已有的 java-fde 知识点）
"""

import pytest  # noqa: F401
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.learn_helpers import AXUE, MAPS, learn_env, map_texts  # noqa: F401
from tongyun_learn.models import Card, Point, PointPrereq, Subject
from tongyun_learn.services.importer import import_maps


def _load_yaml_docs() -> list[dict]:
    return [
        yaml.safe_load((MAPS / "english.yaml").read_text(encoding="utf-8")),
        yaml.safe_load((MAPS / "java-fde.yaml").read_text(encoding="utf-8")),
    ]


def test_import_errors_cause_atomic_rollback(client: TestClient, db_session: Session, learn_env):  # noqa: F811
    """导入错误原子回滚：
    - Schema 不合法
    - 前置指向不存在的 id
    - 前置成环
    有 error 时返回 errors，库里不写任何记录（dry_run=false 亦然）。
    """
    db = db_session

    # 1) Schema 不合法
    bad_schema_yaml = "subject:\n  id: test-bad\nstages: 123"  # stages 必须是 array
    res1 = client.post("/v1/maps/import?dry_run=false", json={"files": [bad_schema_yaml]}, headers=AXUE).json()
    assert len(res1["errors"]) > 0
    assert db.scalars(select(Subject)).all() == []

    # 2) 前置指向不存在的 id
    docs2 = _load_yaml_docs()
    # 给 java-fde 的第一个点添加一个不存在的前置
    docs2[1]["stages"][0]["points"][0]["prerequisites"].append({"id": "jf.non-existent-prereq", "kind": "hard"})
    files2 = [yaml.dump(d, allow_unicode=True) for d in docs2]
    res2 = client.post("/v1/maps/import?dry_run=false", json={"files": files2}, headers=AXUE).json()
    assert len(res2["errors"]) > 0
    assert any("不存在" in e for e in res2["errors"])
    assert db.scalars(select(Subject)).all() == []

    # 3) 前置成环：Point A -> Point B -> Point A
    docs3 = _load_yaml_docs()
    p0 = docs3[1]["stages"][0]["points"][0]
    p1 = docs3[1]["stages"][0]["points"][1]
    p0["prerequisites"].append({"id": p1["id"], "kind": "hard"})
    p1["prerequisites"].append({"id": p0["id"], "kind": "hard"})
    files3 = [yaml.dump(d, allow_unicode=True) for d in docs3]
    res3 = client.post("/v1/maps/import?dry_run=false", json={"files": files3}, headers=AXUE).json()
    assert len(res3["errors"]) > 0
    assert any("成环" in e for e in res3["errors"])
    assert db.scalars(select(Subject)).all() == []


def test_import_deactivate_and_reactivate_point(client: TestClient, db_session: Session, learn_env):  # noqa: F811
    """知识点停用与重新启用：
    - YAML 删掉一个知识点再导入 → 该点 active=0（不物理删除），其示例卡停用
    - 再加回来 → reactivated=1，示例卡恢复
    """
    db = db_session

    # 首次完整导入
    r_init = client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE).json()
    assert r_init["errors"] == []

    # 选取叶子点 jf.git-secrets（无下游依赖），检查其初始状态
    target_pid = "jf.git-secrets"
    pt = db.get(Point, target_pid)
    assert pt is not None and pt.active is True
    ex_cards = db.scalars(select(Card).where(Card.point_id == target_pid)).all()
    assert len(ex_cards) > 0
    assert all(c.active is True for c in ex_cards)

    # 从 YAML 中删去该知识点并重新导入
    docs = _load_yaml_docs()
    jf_stages = docs[1]["stages"]
    removed_point = None
    for s in jf_stages:
        for idx, p in enumerate(s["points"]):
            if p["id"] == target_pid:
                removed_point = s["points"].pop(idx)
                break
        if removed_point:
            break
    assert removed_point is not None

    files_removed = [yaml.dump(d, allow_unicode=True) for d in docs]
    r_del = client.post("/v1/maps/import?dry_run=false", json={"files": files_removed}, headers=AXUE).json()
    assert r_del["errors"] == []

    # 校验 diff 计数
    jf_res = next(r for r in r_del["results"] if r["subject"] == "java-fde")
    assert jf_res["points"]["deactivated"] == 1
    assert jf_res["example_cards"]["deactivated"] >= 1

    # 校验库里行未物理删除，但 active 变为 False，示例卡亦停用
    db.expire_all()
    pt_after = db.get(Point, target_pid)
    assert pt_after is not None
    assert pt_after.active is False
    assert pt_after.deactivated_at is not None
    ex_cards_after = db.scalars(select(Card).where(Card.point_id == target_pid)).all()
    assert all(c.active is False for c in ex_cards_after)

    # 恢复：将原始文件重新导入
    r_restore = client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE).json()
    assert r_restore["errors"] == []

    jf_restore = next(r for r in r_restore["results"] if r["subject"] == "java-fde")
    assert jf_restore["points"]["reactivated"] == 1

    # 校验库中该点及示例卡均已恢复
    db.expire_all()
    pt_restored = db.get(Point, target_pid)
    assert pt_restored.active is True
    assert pt_restored.deactivated_at is None
    ex_cards_restored = db.scalars(select(Card).where(Card.point_id == target_pid)).all()
    assert all(c.active is True for c in ex_cards_restored)


def test_import_preserves_axue_edited_and_replaced_cards(client: TestClient, db_session: Session, learn_env):  # noqa: F811
    """阿学改动卡片保护：
    - 阿学 PATCH /v1/cards/{id} 改过的示例卡（created_by 变 axue）→ 重导入计 kept_edited，内容不被覆盖
    - 替换示例卡（停用旧卡 + POST /points/{id}/cards 建新卡）后重导入也不会把旧卡恢复成 example
    """
    db = db_session
    client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE)

    target_pid = "jf.equals-hashcode"
    cards = db.scalars(select(Card).where(Card.point_id == target_pid).order_by(Card.id)).all()
    assert len(cards) >= 2

    # 1) 阿学修改第一张示例卡：修改 back
    c_edit = cards[0]
    new_back = "阿学定制解析：JVM 是 Java 跨平台的核心"
    r_patch = client.patch(f"/v1/cards/{c_edit.id}", json={"back": new_back}, headers=AXUE)
    assert r_patch.status_code == 200, r_patch.text
    assert r_patch.json()["created_by"] == "axue"

    # 2) 替换第二张示例卡：停用旧卡，并 POST 建新卡
    c_replace = cards[1]
    r_deact = client.patch(f"/v1/cards/{c_replace.id}", json={"active": False}, headers=AXUE)
    assert r_deact.status_code == 200
    assert r_deact.json()["created_by"] == "axue"
    assert r_deact.json()["active"] is False

    r_new_card = client.post(
        f"/v1/points/{target_pid}/cards",
        json={"cards": [{"card_type": "understand", "front": "新替换卡片", "back": "新卡背面"}]},
        headers=AXUE,
    )
    assert r_new_card.status_code == 200

    # 3) 重新导入原始 YAML
    r_reimport = client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE).json()
    assert r_reimport["errors"] == []

    jf_res = next(r for r in r_reimport["results"] if r["subject"] == "java-fde")
    # 至少包含改过和停用的示例卡计入 kept_edited
    assert jf_res["example_cards"]["kept_edited"] >= 2

    # 校验第一张卡内容未被覆盖，created_by 仍为 axue
    db.expire_all()
    c_edit_db = db.get(Card, c_edit.id)
    assert c_edit_db.back == new_back
    assert c_edit_db.created_by == "axue"

    # 校验被替换的旧卡未被重置为 active=True 或 created_by=example
    c_replace_db = db.get(Card, c_replace.id)
    assert c_replace_db.active is False
    assert c_replace_db.created_by == "axue"


def test_import_updates_example_card_back(client: TestClient, db_session: Session, learn_env):  # noqa: F811
    """修改 YAML 里某张示例卡的 back → 重导入 example_cards.updated=1。"""
    client.post("/v1/maps/import?dry_run=false", json={"files": map_texts()}, headers=AXUE)

    docs = _load_yaml_docs()
    target_card = docs[1]["stages"][0]["points"][0]["example_cards"][0]
    updated_back = target_card["back"] + " —— 更新后的补充内容"
    target_card["back"] = updated_back

    files_modified = [yaml.dump(d, allow_unicode=True) for d in docs]
    res = client.post("/v1/maps/import?dry_run=false", json={"files": files_modified}, headers=AXUE).json()
    assert res["errors"] == []

    jf_res = next(r for r in res["results"] if r["subject"] == "java-fde")
    assert jf_res["example_cards"]["updated"] >= 1


def test_import_single_english_yaml_with_java_in_db(client: TestClient, db_session: Session, learn_env):  # noqa: F811
    """单独只导入 english.yaml（java-fde 已在库里）也能通过（跨学科软前置走库里已有点）。"""
    db = db_session

    # 1) 先只导入 java-fde.yaml
    java_text = (MAPS / "java-fde.yaml").read_text(encoding="utf-8")
    r_jf = import_maps(db, [java_text], dry_run=False)
    assert r_jf["errors"] == []

    # 2) 再单独只导入 english.yaml
    # english.yaml 包含指向 jf.* 的跨学科软前置，应通过库里已有的 java-fde 点通过校验
    english_text = (MAPS / "english.yaml").read_text(encoding="utf-8")
    r_en = import_maps(db, [english_text], dry_run=False)
    assert r_en["errors"] == []
    assert len(r_en["warnings"]) > 0  # 含有跨学科使用库里已有点的提示警告
    assert any("库里已有的知识点" in w for w in r_en["warnings"])

    # 校验跨学科前置边在 point_prereqs 表中存在
    cross_prereq = db.scalar(
        select(PointPrereq).where(
            PointPrereq.point_id == "en.read-ai-docs",
            PointPrereq.prereq_id == "jf.llm-basics",
            PointPrereq.kind == "soft",
        )
    )
    assert cross_prereq is not None
