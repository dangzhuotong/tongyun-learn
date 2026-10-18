"""routers/deps.py 的 dry-run 纯路径单测（离线，无外部网络）。

覆盖：
- mark_dry：仅对 dict 且 db.info["dry_run"] 为真时补 dry_run 标记，且原地返回。
- get_write_db：dry_run=true 时设置 db.info 标记、把 commit 换成 flush、回写 X-Dry-Run 头，
  生成器结束必须 rollback（不落库）；dry_run=false 时不加任何标记。
"""

from types import SimpleNamespace

from fastapi import Response

from tongyun_learn.db import SessionLocal
from tongyun_learn.models import Subject
from tongyun_learn.routers.deps import get_write_db, mark_dry


def test_mark_dry_adds_flag_to_dict_when_dry_run():
    db = SimpleNamespace(info={"dry_run": True})
    out = {"a": 1}
    assert mark_dry(db, out) is out
    assert out == {"a": 1, "dry_run": True}


def test_mark_dry_leaves_dict_untouched_without_flag():
    db = SimpleNamespace(info={})
    out = {"a": 1}
    assert mark_dry(db, out) is out
    assert "dry_run" not in out


def test_mark_dry_ignores_non_dict_payloads():
    db = SimpleNamespace(info={"dry_run": True})
    for value in (["x"], "text", 42, None):
        assert mark_dry(db, value) is value


def test_get_write_db_dry_run_flags_and_rolls_back():
    response = Response()
    gen = get_write_db(response=response, dry_run=True)
    db = next(gen)
    try:
        assert db.info.get("dry_run") is True
        assert db.commit == db.flush  # 事务永不提交，commit 退化为 flush
        assert response.headers["X-Dry-Run"] == "1"

        db.add(Subject(id="zz-dep-dry", prefix="zzdd", title="dry"))
        db.flush()
        assert db.get(Subject, "zz-dep-dry") is not None
    finally:
        gen.close()  # 触发 finally：rollback + close

    with SessionLocal() as check:
        assert check.get(Subject, "zz-dep-dry") is None


def test_get_write_db_without_dry_run_has_no_flags():
    response = Response()
    gen = get_write_db(response=response, dry_run=False)
    db = next(gen)
    try:
        assert db.info.get("dry_run") is None
        assert "X-Dry-Run" not in response.headers
        assert db.commit != db.flush
    finally:
        gen.close()
