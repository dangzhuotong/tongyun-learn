from collections.abc import Generator
from typing import Annotated, Any

from fastapi import Depends, Query, Response
from sqlalchemy.orm import Session

from tongyun_learn.db import SessionLocal


def get_write_db(
    response: Response,
    dry_run: bool = Query(False, description="预演：执行后整体回滚"),
) -> Generator[Session, None, None]:
    db = SessionLocal()
    if dry_run:
        db.info["dry_run"] = True
        db.commit = db.flush  # 服务层的 commit 变成 flush，事务一直不提交
        response.headers["X-Dry-Run"] = "1"
    try:
        yield db
    finally:
        if dry_run:
            db.rollback()
        db.close()


WriteDb = Annotated[Session, Depends(get_write_db)]


def mark_dry(db: Session, out: Any) -> Any:
    """dict 响应加 "dry_run": True；非 dry_run 原样返回"""
    if db.info.get("dry_run") and isinstance(out, dict):
        out["dry_run"] = True
    return out


__all__ = ["WriteDb", "get_write_db", "mark_dry"]
