"""P3b 卡点服务（定稿 §1 / §2）。"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from tongyun_learn.db import utcnow
from tongyun_learn.errors import ApiError
from tongyun_learn.models import Blocker, Point, StudySession
from tongyun_learn.timeutil import iso_local


def blocker_out(db: Session, b: Blocker, point_title: str | None = None) -> dict:
    resolved_point_title: str | None = None
    if b.point_id:
        if point_title is not None:
            resolved_point_title = point_title
        else:
            p = db.get(Point, b.point_id)
            resolved_point_title = p.title if p else None

    return {
        "id": b.id,
        "point_id": b.point_id,
        "point_title": resolved_point_title,
        "session_id": b.session_id,
        "title": b.title,
        "detail": b.detail,
        "status": b.status,
        "resolution": b.resolution,
        "legacy_ref": b.legacy_ref,
        "created_at": iso_local(b.created_at),
        "resolved_at": iso_local(b.resolved_at) if b.resolved_at is not None else None,
    }


def create_blocker(db: Session, data: Mapping[str, Any] | Any) -> dict:
    if hasattr(data, "model_dump"):
        payload = data.model_dump()
    elif isinstance(data, Mapping):
        payload = dict(data)
    else:
        payload = dict(data)

    point_id = payload.get("point_id")
    if point_id is not None:
        if db.get(Point, point_id) is None:
            raise ApiError(404, "point_not_found", "知识点不存在")

    session_id = payload.get("session_id")
    if session_id is not None:
        sess = db.get(StudySession, session_id)
        if sess is None:
            raise ApiError(404, "session_not_found", "课次不存在")
        if sess.voided_at is not None:
            raise ApiError(409, "session_voided", "课次已作废，不能再挂卡点")

    raw_title = payload.get("title")
    title = (raw_title or "").strip()
    if not title:
        raise ApiError(422, "invalid_title", "标题不能为空")

    detail = payload.get("detail")

    b = Blocker(
        point_id=point_id,
        session_id=session_id,
        title=title,
        detail=detail,
        status="open",
        created_at=utcnow(),
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return blocker_out(db, b)


def update_blocker(db: Session, blocker_id: int, data: Mapping[str, Any] | Any) -> dict:
    b = db.get(Blocker, blocker_id)
    if b is None:
        raise ApiError(404, "not_found", "卡点不存在")

    if hasattr(data, "model_dump"):
        payload = data.model_dump(exclude_unset=True)
    elif isinstance(data, Mapping):
        payload = dict(data)
    else:
        payload = dict(data)

    has_status = "status" in payload and payload["status"] is not None
    has_resolution = "resolution" in payload and payload["resolution"] is not None

    if not has_status and not has_resolution:
        raise ApiError(422, "empty_patch", "至少需要提供 status 或 resolution")

    if has_status:
        st = payload["status"]
        if st not in ("open", "resolved", "dropped"):
            raise ApiError(422, "invalid_status", "状态非法")
        if st in ("resolved", "dropped"):
            if b.resolved_at is None:
                b.resolved_at = utcnow()
        elif st == "open":
            b.resolved_at = None
        b.status = st

    if has_resolution:
        b.resolution = payload["resolution"]

    db.commit()
    db.refresh(b)
    return blocker_out(db, b)


def list_blockers(
    db: Session,
    status: str | None = None,
    point: str | None = None,
    limit: int = 200,
) -> list[dict]:
    if status is not None and status != "":
        if status not in ("open", "resolved", "dropped"):
            raise ApiError(422, "invalid_status", "状态非法")

    stmt = select(Blocker)
    if status:
        stmt = stmt.where(Blocker.status == status)
    if point:
        stmt = stmt.where(Blocker.point_id == point)

    order_priority = case((Blocker.status == "open", 0), else_=1)
    stmt = stmt.order_by(order_priority.asc(), Blocker.created_at.asc(), Blocker.id.asc())

    if limit is not None:
        stmt = stmt.limit(limit)

    items = list(db.scalars(stmt))
    if not items:
        return []

    point_ids = {b.point_id for b in items if b.point_id}
    titles: dict[str, str] = {}
    if point_ids:
        titles = dict(db.execute(select(Point.id, Point.title).where(Point.id.in_(point_ids))).all())

    return [blocker_out(db, b, point_title=titles.get(b.point_id)) for b in items]
