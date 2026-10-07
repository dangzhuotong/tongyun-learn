"""课次与证据的软作废、恢复与课次列表（定稿 P3b、§4）。"""

from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tongyun_learn.errors import ApiError
from tongyun_learn.models import Blocker, Evidence, SessionPoint, StudySession
from tongyun_learn.services.state import recompute_points
from tongyun_learn.timeutil import iso_local, utcnow


def _reason(reason: str | None) -> str:
    r = (reason or "").strip()
    if not r:
        raise ApiError(422, "validation_error", "作废要写原因")
    return r


def void_session(db: Session, session_id: int, reason: str, now: datetime | None = None) -> dict:
    now = now or utcnow()
    session = db.get(StudySession, session_id)
    if session is None:
        raise ApiError(404, "not_found", "课次不存在")
    if session.voided_at is not None:
        raise ApiError(409, "already_voided", "课次已作废")

    reason = _reason(reason)
    session.voided_at = now
    session.void_reason = reason

    cascaded_evs = list(
        db.scalars(
            select(Evidence)
            .where(
                Evidence.session_id == session.id,
                Evidence.voided_at.is_(None),
            )
            .order_by(Evidence.id)
        )
    )
    for ev in cascaded_evs:
        ev.voided_at = now
        ev.void_reason = f"[课次#{session.id}] {reason}"

    session_pids = list(db.scalars(select(SessionPoint.point_id).where(SessionPoint.session_id == session.id)))
    ev_pids = [ev.point_id for ev in cascaded_evs if ev.point_id]
    affected_pids = sorted(set(session_pids) | set(ev_pids))

    db.flush()  # autoflush 关着，先把作废标记写下去，重算才看得到
    changes = recompute_points(
        db,
        affected_pids,
        rebase=affected_pids,
        cause="void",
        cause_ref=f"session:{session.id}",
        now=now,
        note=reason,
    )
    db.commit()

    return {
        "session_id": session.id,
        "voided_at": iso_local(session.voided_at),
        "void_reason": session.void_reason,
        "cascaded_evidence": [ev.id for ev in cascaded_evs],
        "point_changes": changes,
    }


def restore_session(db: Session, session_id: int, reason: str | None = None, now: datetime | None = None) -> dict:
    now = now or utcnow()
    session = db.get(StudySession, session_id)
    if session is None:
        raise ApiError(404, "not_found", "课次不存在")
    if session.voided_at is None:
        raise ApiError(409, "not_voided", "课次未作废")

    session.voided_at = None
    session.void_reason = None

    prefix = f"[课次#{session.id}]"
    restored_evs = []
    evs = list(
        db.scalars(
            select(Evidence)
            .where(
                Evidence.session_id == session.id,
                Evidence.voided_at.is_not(None),
            )
            .order_by(Evidence.id)
        )
    )
    for ev in evs:
        if ev.void_reason and ev.void_reason.startswith(prefix):
            ev.voided_at = None
            ev.void_reason = None
            restored_evs.append(ev)

    session_pids = list(db.scalars(select(SessionPoint.point_id).where(SessionPoint.session_id == session.id)))
    ev_pids = [ev.point_id for ev in restored_evs if ev.point_id]
    affected_pids = sorted(set(session_pids) | set(ev_pids))

    db.flush()
    changes = recompute_points(
        db,
        affected_pids,
        cause="restore",
        cause_ref=f"session:{session.id}",
        now=now,
        note=(reason or "").strip() or None,
    )
    db.commit()

    return {
        "session_id": session.id,
        "restored_evidence": [ev.id for ev in restored_evs],
        "point_changes": changes,
    }


def void_evidence(db: Session, evidence_id: int, reason: str, now: datetime | None = None) -> dict:
    now = now or utcnow()
    ev = db.get(Evidence, evidence_id)
    if ev is None:
        raise ApiError(404, "not_found", "证据不存在")
    if ev.voided_at is not None:
        raise ApiError(409, "already_voided", "证据已作废")

    reason = _reason(reason)
    ev.voided_at = now
    ev.void_reason = reason

    changes = []
    if ev.point_id:
        db.flush()
        changes = recompute_points(
            db,
            [ev.point_id],
            rebase=[ev.point_id],
            cause="void",
            cause_ref=f"evidence:{ev.id}",
            now=now,
            note=reason,
        )
    db.commit()

    return {
        "evidence_id": ev.id,
        "voided_at": iso_local(ev.voided_at),
        "void_reason": ev.void_reason,
        "point_changes": changes,
    }


def restore_evidence(db: Session, evidence_id: int, reason: str | None = None, now: datetime | None = None) -> dict:
    now = now or utcnow()
    ev = db.get(Evidence, evidence_id)
    if ev is None:
        raise ApiError(404, "not_found", "证据不存在")
    if ev.voided_at is None:
        raise ApiError(409, "not_voided", "证据未作废")

    if ev.session_id is not None:
        sess = db.get(StudySession, ev.session_id)
        if sess is not None and sess.voided_at is not None:
            raise ApiError(409, "session_voided", "所属课次尚在作废状态，不能单独恢复该证据")

    ev.voided_at = None
    ev.void_reason = None

    changes = []
    if ev.point_id:
        db.flush()
        changes = recompute_points(
            db,
            [ev.point_id],
            cause="restore",
            cause_ref=f"evidence:{ev.id}",
            now=now,
            note=(reason or "").strip() or None,
        )
    db.commit()

    return {
        "evidence_id": ev.id,
        "voided_at": None,
        "void_reason": None,
        "point_changes": changes,
    }


def list_sessions(
    db: Session,
    date_from: str | None = None,
    date_to: str | None = None,
    point: str | None = None,
    subject: str | None = None,
    include_voided: bool = False,
    limit: int = 50,
) -> list[dict]:
    d_from: date | None = None
    if date_from and date_from.strip():
        try:
            d_from = date.fromisoformat(date_from.strip())
        except ValueError as e:
            raise ApiError(422, "invalid_date", "date_from 格式应为 YYYY-MM-DD") from e

    d_to: date | None = None
    if date_to and date_to.strip():
        try:
            d_to = date.fromisoformat(date_to.strip())
        except ValueError as e:
            raise ApiError(422, "invalid_date", "date_to 格式应为 YYYY-MM-DD") from e

    q = select(StudySession)
    if not include_voided:
        q = q.where(StudySession.voided_at.is_(None))
    if d_from:
        q = q.where(StudySession.date >= d_from)
    if d_to:
        q = q.where(StudySession.date <= d_to)
    if subject and subject.strip():
        q = q.where(StudySession.subject_id == subject.strip())
    if point and point.strip():
        subq = select(SessionPoint.session_id).where(SessionPoint.point_id == point.strip())
        q = q.where(StudySession.id.in_(subq))

    q = q.order_by(StudySession.date.desc(), StudySession.id.desc()).limit(limit)
    sessions = list(db.scalars(q))
    if not sessions:
        return []

    sids = [s.id for s in sessions]

    sp_rows = db.execute(
        select(SessionPoint.session_id, SessionPoint.point_id)
        .where(SessionPoint.session_id.in_(sids))
        .order_by(SessionPoint.point_id)
    ).all()
    points_by_session: dict[int, list[str]] = defaultdict(list)
    for sid, pid in sp_rows:
        points_by_session[sid].append(pid)

    ev_q = select(Evidence).where(Evidence.session_id.in_(sids))
    if not include_voided:
        ev_q = ev_q.where(Evidence.voided_at.is_(None))
    ev_rows = list(db.scalars(ev_q.order_by(Evidence.id)))
    ev_by_session: dict[int, list[dict]] = defaultdict(list)
    for e in ev_rows:
        ev_by_session[e.session_id].append(
            {
                "id": e.id,
                "type": e.type,
                "passed": bool(e.passed),
                "score": float(e.score) if e.score is not None else None,
                "max": float(e.max_score) if e.max_score is not None else None,
                "voided_at": iso_local(e.voided_at),
            }
        )

    bl_rows = list(db.scalars(select(Blocker).where(Blocker.session_id.in_(sids)).order_by(Blocker.id)))
    bl_by_session: dict[int, list[dict]] = defaultdict(list)
    for b in bl_rows:
        bl_by_session[b.session_id].append(
            {
                "id": b.id,
                "title": b.title,
                "status": b.status,
            }
        )

    out = []
    for s in sessions:
        out.append(
            {
                "session_id": s.id,
                "date": s.date.isoformat(),
                "subject_id": s.subject_id,
                "minutes": s.minutes,
                "lesson_ref": s.lesson_ref,
                "point_ids": points_by_session.get(s.id, []),
                "cues": list(s.cues or []),
                "summary": s.summary,
                "stuck": s.stuck,
                "notes": s.notes,
                "source": s.source,
                "legacy_ref": s.legacy_ref,
                "created_at": iso_local(s.created_at),
                "voided_at": iso_local(s.voided_at),
                "void_reason": s.void_reason,
                "evidence": ev_by_session.get(s.id, []),
                "blockers": bl_by_session.get(s.id, []),
            }
        )
    return out
