"""services/importer.py 地图加载器的纯逻辑面单测。

覆盖不需要完整导入流程的部分：
- _empty_result：diff 结果模板结构与每次调用互相独立。
- _schema：内置 knowledge-map.schema.json 能加载，且仓库 maps/*.yaml 全部通过 Draft 2020-12 校验。
- CARD_TYPE_MAP / EVIDENCE_MAP：YAML 中文类型到内部代码的映射完整。
- _set：字段比较与「是否有变更」判定（含 Decimal 数值等价）。
- _topo：按硬前置给出拓扑序，忽略软前置，有环时兜底不丢点。
"""

from decimal import Decimal
from types import SimpleNamespace

import jsonschema
import pytest  # noqa: F401
import yaml
from sqlalchemy import delete, or_

from tests.learn_helpers import MAPS, learn_env  # noqa: F401
from tongyun_learn.db import SessionLocal
from tongyun_learn.models import Point, PointPrereq, Stage, Subject
from tongyun_learn.services.importer import (
    CARD_TYPE_MAP,
    EVIDENCE_MAP,
    _empty_result,
    _schema,
    _set,
    _topo,
)


def test_empty_result_shape_and_isolation():
    res = _empty_result("java-fde", "2026-10-07.1")
    assert res["subject"] == "java-fde"
    assert res["map_version"] == "2026-10-07.1"
    assert res["stages"] == {"added": 0, "updated": 0, "deactivated": 0}
    assert res["points"] == {"added": 0, "updated": 0, "deactivated": 0, "reactivated": 0}
    assert res["prereqs"] == {"added": 0, "removed": 0}
    assert res["example_cards"] == {"created": 0, "updated": 0, "deactivated": 0, "kept_edited": 0}
    assert res["open_at_start"] == 0
    assert res["points_by_state"] == {}

    res["points"]["added"] = 7
    assert _empty_result("other", None)["points"]["added"] == 0


def test_bundled_schema_validates_all_maps():
    validator = jsonschema.Draft202012Validator(_schema())
    for name in ("english.yaml", "java-fde.yaml"):
        doc = yaml.safe_load((MAPS / name).read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
        assert errors == [], f"{name}: {[e.message for e in errors]}"


def test_card_type_and_evidence_maps_are_complete():
    assert CARD_TYPE_MAP == {
        "记忆卡": "memory",
        "理解卡": "understand",
        "动手卡": "handson",
        "表达卡": "express",
    }
    assert EVIDENCE_MAP == {
        "自测": "selftest",
        "费曼": "feynman",
        "表达": "express",
        "动手": "handson",
    }


def test_set_detects_scalar_changes():
    obj = SimpleNamespace(a=1, b="x")
    assert _set(obj, {"a": 1, "b": "x"}) is False
    assert _set(obj, {"a": 2}) is True
    assert obj.a == 2


def test_set_treats_equal_decimals_as_unchanged():
    obj = SimpleNamespace(effort=1.0)
    assert _set(obj, {"effort": Decimal("1.0")}) is False
    assert _set(obj, {"effort": Decimal("2.5")}) is True
    assert obj.effort == Decimal("2.5")


def test_set_updates_none_valued_field():
    obj = SimpleNamespace(deactivated_at=None)
    assert _set(obj, {"deactivated_at": "2026-10-07"}) is True
    assert obj.deactivated_at == "2026-10-07"


_TOPO_SUBJECT = "zz-topo"
_TOPO_STAGE = "zzt.s1"
_TOPO_POINTS = ("A", "B", "C")


def _seed_topo_graph(db, edges: list[tuple[str, str, str]]) -> None:
    # 模型没有 relationship()，一次 flush 按类名排序，Point 会排在 Stage/Subject 前面。
    # SQLite 默认不查外键；MySQL 的 fk_points_stage_id_stages 会拒绝尚未存在的阶段。
    # 所以先把学科、阶段落库，再插知识点。
    db.add(Subject(id=_TOPO_SUBJECT, prefix="zzt", title="topo"))
    db.flush()
    db.add(Stage(id=_TOPO_STAGE, subject_id=_TOPO_SUBJECT, ord=1, title="s1"))
    db.flush()
    for pid in _TOPO_POINTS:
        db.add(Point(id=pid, subject_id=_TOPO_SUBJECT, stage_id=_TOPO_STAGE, title=pid))
    db.flush()
    for point_id, prereq_id, kind in edges:
        db.add(PointPrereq(point_id=point_id, prereq_id=prereq_id, kind=kind))
    db.commit()


def _cleanup_topo_graph(db) -> None:
    db.rollback()
    db.expunge_all()
    db.execute(
        delete(PointPrereq).where(or_(PointPrereq.point_id.in_(_TOPO_POINTS), PointPrereq.prereq_id.in_(_TOPO_POINTS)))
    )
    db.execute(delete(Point).where(Point.id.in_(_TOPO_POINTS)))
    db.execute(delete(Stage).where(Stage.id == _TOPO_STAGE))
    db.execute(delete(Subject).where(Subject.id == _TOPO_SUBJECT))
    db.commit()


@pytest.fixture
def topo_db(learn_env):  # noqa: F811
    db = SessionLocal()
    try:
        yield db
    finally:
        _cleanup_topo_graph(db)
        db.close()


def test_topo_respects_hard_prerequisites(topo_db):
    # 列表顺序故意把依赖方 B 放在前面；拓扑序必须把 A 排到 B 之前
    _seed_topo_graph(topo_db, [("B", "A", "hard")])
    assert _topo(topo_db, ["B", "A"]) == ["A", "B"]


def test_topo_ignores_soft_prerequisites(topo_db):
    # 若把软前置误当硬依赖，A 会被排到 B 之后
    _seed_topo_graph(topo_db, [("A", "B", "soft")])
    assert _topo(topo_db, ["A", "B"]) == ["A", "B"]


def test_topo_cycle_fallback_keeps_every_point(topo_db):
    _seed_topo_graph(topo_db, [("A", "B", "hard"), ("B", "A", "hard")])
    assert sorted(_topo(topo_db, ["A", "B", "C"])) == ["A", "B", "C"]
