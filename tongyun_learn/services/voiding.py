"""课次与证据的软作废、恢复与课次列表（定稿 P3b、§4）。"""

from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from tongyun_learn.errors import ApiError
from tongyun_learn.models import Blocker, Card, CardState, Evidence, ReviewLog, SessionPoint, StudySession
from tongyun_learn.services import srs
from tongyun_learn.services.review import card_state_out
from tongyun_learn.services.state import recompute_points
from tongyun_learn.timeutil import iso_local, utcnow


def _reason(reason: str | None) -> str:
    r = (reason or "").strip()
    if not r:
        raise ApiError(422, "validation_error", "作废要写原因")
    return r


def _clip(text: str) -> str:
    return text if len(text) <= 500 else text[:500]


def _void_linked_review(db: Session, ev: Evidence, reason: str, now: datetime) -> tuple[ReviewLog | None, bool]:
    """作废这条证据写出来的复习。已经作废的不动（保留原原因）。返回 (复习, 是否要重放 FSRS)。"""
    if ev.review_id is None:
        return None, False
    rev = db.get(ReviewLog, ev.review_id)
    if rev is None or rev.voided_at is not None:
        return None, False
    rev.voided_at = now
    rev.void_reason = _clip(f"[证据#{ev.id}] {reason}")
    return rev, bool(rev.applied)


def _restore_linked_review(db: Session, ev: Evidence) -> tuple[ReviewLog | None, bool]:
    """只恢复「随这条证据作废」的复习。单独作废的复习保持作废。返回 (复习, 恢复前是否 applied)。"""
    if ev.review_id is None:
        return None, False
    rev = db.get(ReviewLog, ev.review_id)
    prefix = f"[证据#{ev.id}]"
    if rev is None or rev.voided_at is None or not (rev.void_reason or "").startswith(prefix):
        return None, False
    was_applied = bool(rev.applied)
    rev.voided_at = None
    rev.void_reason = None
    return rev, was_applied


def _replay_cards(db: Session, card_ids: list[int]) -> None:
    for card_id in dict.fromkeys(card_ids):
        _replay_fsrs(db, card_id)


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
    cascaded_reviews: list[int] = []
    replay_card_ids: list[int] = []
    review_pids: list[str] = []
    for ev in cascaded_evs:
        ev.voided_at = now
        ev.void_reason = _clip(f"[课次#{session.id}] {reason}")
        rev, replay = _void_linked_review(db, ev, ev.void_reason, now)
        if rev is None:
            continue
        cascaded_reviews.append(rev.id)
        if rev.point_id:
            review_pids.append(rev.point_id)
        if replay:
            replay_card_ids.append(rev.card_id)

    session_pids = list(db.scalars(select(SessionPoint.point_id).where(SessionPoint.session_id == session.id)))
    ev_pids = [ev.point_id for ev in cascaded_evs if ev.point_id]
    affected_pids = sorted(set(session_pids) | set(ev_pids) | set(review_pids))

    db.flush()  # autoflush 关着，先把作废标记写下去，重放和重算才看得到
    _replay_cards(db, replay_card_ids)
    db.flush()
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
        "cascaded_reviews": cascaded_reviews,
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
    restored_reviews: list[int] = []
    replay_card_ids: list[int] = []
    review_pids: list[str] = []
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
            rev, was_applied = _restore_linked_review(db, ev)
            if rev is None:
                continue
            restored_reviews.append(rev.id)
            if rev.point_id:
                review_pids.append(rev.point_id)
            if was_applied:
                replay_card_ids.append(rev.card_id)

    session_pids = list(db.scalars(select(SessionPoint.point_id).where(SessionPoint.session_id == session.id)))
    ev_pids = [ev.point_id for ev in restored_evs if ev.point_id]
    affected_pids = sorted(set(session_pids) | set(ev_pids) | set(review_pids))

    db.flush()
    _replay_cards(db, replay_card_ids)
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
        "restored_reviews": restored_reviews,
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
    rev, replay = _void_linked_review(db, ev, reason, now)

    pids = [ev.point_id] if ev.point_id else []
    if rev is not None and rev.point_id and rev.point_id not in pids:
        pids.append(rev.point_id)

    db.flush()
    if replay and rev is not None:
        _replay_fsrs(db, rev.card_id)
        db.flush()
    changes = []
    if pids:
        changes = recompute_points(
            db,
            pids,
            rebase=pids,
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
        "cascaded_review_id": rev.id if rev is not None else None,
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
    rev, was_applied = _restore_linked_review(db, ev)

    pids = [ev.point_id] if ev.point_id else []
    if rev is not None and rev.point_id and rev.point_id not in pids:
        pids.append(rev.point_id)

    db.flush()
    if was_applied and rev is not None:
        _replay_fsrs(db, rev.card_id)
        db.flush()
    changes = []
    if pids:
        changes = recompute_points(
            db,
            pids,
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
        "restored_review_id": rev.id if rev is not None else None,
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


def _replay_fsrs(db: Session, card_id: int) -> CardState | None:
    remaining_reviews = list(
        db.scalars(
            select(ReviewLog)
            .where(
                ReviewLog.card_id == card_id,
                ReviewLog.applied.is_(True),
                ReviewLog.voided_at.is_(None),
            )
            .order_by(ReviewLog.reviewed_at.asc(), ReviewLog.id.asc())
        )
    )
    if not remaining_reviews:
        cs_row = db.get(CardState, card_id)
        if cs_row is not None:
            db.delete(cs_row)
        return None

    temp_cs: CardState | None = None
    for r in remaining_reviews:
        temp_cs = srs.apply_review(temp_cs, card_id, r.rating, r.reviewed_at)
        r.stability_after = temp_cs.stability
        r.due_after = temp_cs.due

    cs_row = db.get(CardState, card_id)
    if cs_row is None:
        cs_row = CardState(card_id=card_id)
        db.add(cs_row)
    for field in (
        "state",
        "step",
        "stability",
        "difficulty",
        "due",
        "first_review",
        "last_review",
        "last_rating",
        "reps",
        "lapses",
    ):
        setattr(cs_row, field, getattr(temp_cs, field))
    return cs_row


def void_review(db: Session, review_id: int, reason: str, now: datetime | None = None) -> dict:
    now = now or utcnow()
    rev = db.get(ReviewLog, review_id)
    if rev is None:
        raise ApiError(404, "not_found", "复习记录不存在")
    if rev.voided_at is not None:
        raise ApiError(409, "already_voided", "复习记录已作废")

    reason = _reason(reason)
    rev.voided_at = now
    rev.void_reason = reason
    db.flush()

    if not rev.applied:
        cs_row = db.get(CardState, rev.card_id)
        db.commit()
        return {
            "review_id": rev.id,
            "card_id": rev.card_id,
            "card_state": card_state_out(cs_row),
            "point_changes": [],
        }

    cs_row = _replay_fsrs(db, rev.card_id)

    card = db.get(Card, rev.card_id)
    pid = rev.point_id or (card.point_id if card else None)
    pids = [pid] if pid else []

    db.flush()
    changes = []
    if pids:
        changes = recompute_points(
            db,
            pids,
            rebase=pids,
            cause="void",
            cause_ref=f"review:{rev.id}",
            now=now,
            note=reason,
        )
    db.commit()

    return {
        "review_id": rev.id,
        "card_id": rev.card_id,
        "card_state": card_state_out(cs_row),
        "point_changes": changes,
    }


def restore_review(db: Session, review_id: int, reason: str | None = None, now: datetime | None = None) -> dict:
    now = now or utcnow()
    rev = db.get(ReviewLog, review_id)
    if rev is None:
        raise ApiError(404, "not_found", "复习记录不存在")
    if rev.voided_at is None:
        raise ApiError(409, "not_voided", "复习记录未作废")

    blocking = db.scalar(
        select(Evidence.id).where(Evidence.review_id == rev.id, Evidence.voided_at.is_not(None)).limit(1)
    )
    if blocking is not None:
        raise ApiError(409, "evidence_voided", "所属证据尚在作废状态，不能单独恢复该复习")

    rev.voided_at = None
    rev.void_reason = None
    db.flush()

    if not rev.applied:
        cs_row = db.get(CardState, rev.card_id)
        db.commit()
        return {
            "review_id": rev.id,
            "card_id": rev.card_id,
            "card_state": card_state_out(cs_row),
            "point_changes": [],
        }

    cs_row = _replay_fsrs(db, rev.card_id)

    card = db.get(Card, rev.card_id)
    pid = rev.point_id or (card.point_id if card else None)
    pids = [pid] if pid else []

    db.flush()
    changes = []
    if pids:
        changes = recompute_points(
            db,
            pids,
            cause="restore",
            cause_ref=f"review:{rev.id}",
            now=now,
            note=(reason or "").strip() or None,
        )
    db.commit()

    return {
        "review_id": rev.id,
        "card_id": rev.card_id,
        "card_state": card_state_out(cs_row),
        "point_changes": changes,
    }


def list_reviews(
    db: Session,
    card: int | None = None,
    point: str | None = None,
    limit: int = 20,
    include_voided: bool = False,
    principal: str | None = None,
) -> list[dict]:
    q = select(ReviewLog)
    if principal == "web":
        # 与 GET /points 一样：web 看不到动手卡，列表里也不露出它的复习
        q = q.join(Card, Card.id == ReviewLog.card_id).where(
            or_(Card.card_type.is_(None), Card.card_type != "handson")
        )
    if not include_voided:
        q = q.where(ReviewLog.voided_at.is_(None))
    if card is not None:
        q = q.where(ReviewLog.card_id == card)
    if point and point.strip():
        q = q.where(ReviewLog.point_id == point.strip())
    q = q.order_by(ReviewLog.reviewed_at.desc(), ReviewLog.id.desc()).limit(limit)
    rows = list(db.scalars(q))
    return [
        {
            "review_id": r.id,
            "card_id": r.card_id,
            "point_id": r.point_id,
            "rating": r.rating,
            "reviewer": r.reviewer,
            "client": r.client,
            "reviewed_at": iso_local(r.reviewed_at),
            "applied": bool(r.applied),
            "client_review_id": r.client_review_id,
            "voided_at": iso_local(r.voided_at),
            "void_reason": r.void_reason,
        }
        for r in rows
    ]
