"""P3b 读接口与人工改状态（定稿 §2 P3b 行）。

- weak：弱项 = 生疏 / 遗忘多 / 有未解决卡点 / 缺证据 / 待复查。
- recall：上次 + 约 N 天前的课次（康奈尔线索问题）及相关未解决卡点，替代 `axue review`。
- week_summary：周报，按北京时间周一~周日，状态变化读 point_state_log。
- set_override：PATCH /points/{id}/state，写 override + log，同事务重算并连锁。
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tongyun_learn.errors import ApiError
from tongyun_learn.models import (
    POINT_STATES,
    Blocker,
    Card,
    CardState,
    Evidence,
    Point,
    PointState,
    PointStateLog,
    ReviewLog,
    SessionPoint,
    Stage,
    StudySession,
)
from tongyun_learn.services.state import (
    EVIDENCE_DAYS,
    EVIDENCE_REVIEWERS,
    needed_evidence,
    point_stats,
    recompute_points,
)
from tongyun_learn.timeutil import day_bounds_utc, iso_local, local_date, today_local, utcnow

# 遗忘多：任一 active 卡 lapses ≥ 3，或该点 active 卡 lapses 合计 ≥ 5
LAPSES_CARD = 3
LAPSES_POINT = 5
REASON_ORDER = ("rusty", "open_blocker", "lapses_high", "needs_recheck", "missing_evidence")


# ───────────────────────── weak ─────────────────────────


def weak_points(db: Session, subject: str | None = None, now: datetime | None = None) -> list[dict]:
    now = now or utcnow()
    q = (
        select(Point, Stage.ord, PointState)
        .join(Stage, Stage.id == Point.stage_id)
        .outerjoin(PointState, PointState.point_id == Point.id)
        .where(Point.active.is_(True))
    )
    if subject:
        q = q.where(Point.subject_id == subject)
    rows = db.execute(q).all()
    if not rows:
        return []
    ids = [p.id for p, _o, _ps in rows]

    lapses: dict[str, list[int]] = defaultdict(list)
    for pid, lp in db.execute(
        select(Card.point_id, CardState.lapses)
        .join(CardState, CardState.card_id == Card.id)
        .where(Card.point_id.in_(ids), Card.active.is_(True))
    ):
        lapses[pid].append(int(lp or 0))
    open_bl = dict(
        db.execute(
            select(Blocker.point_id, func.count())
            .where(Blocker.point_id.in_(ids), Blocker.status == "open")
            .group_by(Blocker.point_id)
        ).all()
    )
    cutoff = now - timedelta(days=EVIDENCE_DAYS)
    fresh_ev: dict[str, set[str]] = defaultdict(set)
    for pid, t in db.execute(
        select(Evidence.point_id, Evidence.type).where(
            Evidence.point_id.in_(ids),
            Evidence.passed.is_(True),
            Evidence.reviewer.in_(EVIDENCE_REVIEWERS),
            Evidence.observed_at >= cutoff,
            Evidence.voided_at.is_(None),
        )
    ):
        fresh_ev[pid].add(t)

    found: list[tuple[tuple, dict]] = []
    for p, stage_ord, ps in rows:
        state = ps.state if ps else None
        reasons: list[str] = []
        missing: list[str] = []
        if state == "rusty":
            reasons.append("rusty")
        if open_bl.get(p.id):
            reasons.append("open_blocker")
        lp = lapses.get(p.id, [])
        if lp and (max(lp) >= LAPSES_CARD or sum(lp) >= LAPSES_POINT):
            reasons.append("lapses_high")
        if ps is not None and ps.needs_recheck:
            reasons.append("needs_recheck")
        if state == "learned":
            missing = [t for t in needed_evidence(p) if t not in fresh_ev.get(p.id, set())]
            if missing:
                reasons.append("missing_evidence")
        if not reasons:
            continue
        reasons.sort(key=REASON_ORDER.index)
        item = {
            "point_id": p.id,
            "title": p.title,
            "subject_id": p.subject_id,
            "state": state,
            "reasons": reasons,
            "missing_evidence": missing,
            "lapses": {"max": max(lp) if lp else 0, "total": sum(lp)},
            "open_blockers": int(open_bl.get(p.id, 0)),
        }
        key = (-len(reasons), REASON_ORDER.index(reasons[0]), stage_ord, p.ord, p.id)
        found.append((key, item))
    found.sort(key=lambda x: x[0])
    stats = point_stats(db, [it["point_id"] for _k, it in found], now)
    out = []
    for _k, it in found:
        it["stats"] = stats[it["point_id"]]
        out.append(it)
    return out


# ───────────────────────── recall ─────────────────────────


def parse_days(days: str) -> list[int]:
    try:
        vals = sorted({int(x) for x in days.split(",") if x.strip()})
    except ValueError as e:
        raise ApiError(422, "invalid_days", "days 格式如 1,3,7") from e
    if not vals or any(v < 1 or v > 365 for v in vals) or len(vals) > 10:
        raise ApiError(422, "invalid_days", "days 取 1–365 的整数，最多 10 个")
    return vals


def _session_items(db: Session, sessions: list[StudySession]) -> list[dict]:
    if not sessions:
        return []
    sp: dict[int, list[str]] = defaultdict(list)
    for sid, pid in db.execute(
        select(SessionPoint.session_id, SessionPoint.point_id)
        .where(SessionPoint.session_id.in_([s.id for s in sessions]))
        .order_by(SessionPoint.point_id)
    ):
        sp[sid].append(pid)
    return [
        {
            "session_id": s.id,
            "date": s.date.isoformat(),
            "point_ids": sp.get(s.id, []),
            "lesson_ref": s.lesson_ref,
            "minutes": s.minutes,
            "cues": list(s.cues or []),
            "summary": s.summary,
            "stuck": s.stuck,
            "notes": s.notes,
            "source": s.source,
        }
        for s in sessions
    ]


def blocker_brief(b: Blocker) -> dict:
    return {
        "id": b.id,
        "point_id": b.point_id,
        "session_id": b.session_id,
        "title": b.title,
        "detail": b.detail,
        "status": b.status,
        "created_at": iso_local(b.created_at),
    }


def recall(db: Session, days: str = "1,3,7", now: datetime | None = None) -> list[dict]:
    """[{label, days_ago, date, sessions[], open_blockers[]}]：先“上次”（今天之前最近一次课），
    再每个目标天数 n（n≤1 精确匹配，否则 ±1 天就近，较近的优先），同一天只出现一次。"""
    targets = parse_days(days)
    today = today_local(now)
    last = db.scalar(
        select(func.max(StudySession.date)).where(StudySession.date < today, StudySession.voided_at.is_(None))
    )
    window_start = today - timedelta(days=max(targets) + 1)
    dates = set(
        db.scalars(
            select(StudySession.date)
            .where(
                StudySession.date >= window_start,
                StudySession.date < today,
                StudySession.voided_at.is_(None),
            )
            .distinct()
        ).all()
    )
    picked: list[tuple[str, date]] = []
    used: set[date] = set()
    if last is not None:
        picked.append(("last", last))
        used.add(last)
    for n in targets:
        tol = 0 if n <= 1 else 1
        cands = [d for d in dates if abs((today - d).days - n) <= tol and d not in used]
        if cands:
            d = min(cands, key=lambda d: (abs((today - d).days - n), -d.toordinal()))
            picked.append((f"{n}d", d))
            used.add(d)

    open_blockers = list(db.scalars(select(Blocker).where(Blocker.status == "open").order_by(Blocker.created_at)))
    out = []
    for label, d in picked:
        sess = list(
            db.scalars(
                select(StudySession)
                .where(StudySession.date == d, StudySession.voided_at.is_(None))
                .order_by(StudySession.id)
            )
        )
        items = _session_items(db, sess)
        sids = {it["session_id"] for it in items}
        pids = {pid for it in items for pid in it["point_ids"]}
        related = [b for b in open_blockers if b.session_id in sids or (b.point_id and b.point_id in pids)]
        out.append(
            {
                "label": label,
                "days_ago": (today - d).days,
                "date": d.isoformat(),
                "sessions": items,
                "open_blockers": [blocker_brief(b) for b in related],
            }
        )
    return out


# ───────────────────────── 周报 ─────────────────────────


def week_summary(db: Session, ago: int = 0, now: datetime | None = None) -> dict:
    if ago < 0 or ago > 520:
        raise ApiError(422, "invalid_ago", "ago 取 0–520")
    now = now or utcnow()
    t = today_local(now) - timedelta(weeks=ago)
    mon = t - timedelta(days=t.weekday())
    sun = mon + timedelta(days=6)
    start, _ = day_bounds_utc(mon)
    _, end = day_bounds_utc(sun)

    sessions = list(
        db.scalars(
            select(StudySession)
            .where(StudySession.date >= mon, StudySession.date <= sun, StudySession.voided_at.is_(None))
            .order_by(StudySession.date, StudySession.id)
        )
    )
    session_items = _session_items(db, sessions)

    logs = db.execute(
        select(ReviewLog.reviewed_at, ReviewLog.rating, ReviewLog.reviewer).where(
            ReviewLog.applied.is_(True),
            ReviewLog.voided_at.is_(None),
            ReviewLog.reviewed_at >= start,
            ReviewLog.reviewed_at < end,
        )
    ).all()
    n_rev = len(logs)
    acc = round(len([r for _a, r, _w in logs if r >= 3]) / n_rev, 4) if n_rev else None
    by_reviewer: dict[str, int] = defaultdict(int)
    for _a, _r, w in logs:
        by_reviewer[w or "self"] += 1

    days = {s.date for s in sessions} | {local_date(a) for a, _r, _w in logs}
    days = {d for d in days if mon <= d <= sun}

    trans: dict[str, list[dict]] = {"learned": [], "mastered": [], "rusty": []}
    seen: set[tuple[str, str]] = set()
    for lg, title in db.execute(
        select(PointStateLog, Point.title)
        .join(Point, Point.id == PointStateLog.point_id)
        .where(
            PointStateLog.created_at >= start,
            PointStateLog.created_at < end,
            PointStateLog.to_state.in_(tuple(trans)),
        )
        .order_by(PointStateLog.created_at.desc(), PointStateLog.id.desc())
    ):
        key = (lg.point_id, lg.to_state)
        if key in seen or lg.from_state == lg.to_state:
            continue
        seen.add(key)
        trans[lg.to_state].append(
            {
                "point_id": lg.point_id,
                "title": title,
                "from": lg.from_state,
                "at": iso_local(lg.created_at),
                "cause": lg.cause,
            }
        )
    for v in trans.values():
        v.reverse()  # 时间正序

    opened = list(
        db.scalars(select(Blocker).where(Blocker.created_at >= start, Blocker.created_at < end).order_by(Blocker.id))
    )
    resolved = list(
        db.scalars(
            select(Blocker)
            .where(Blocker.status == "resolved", Blocker.resolved_at >= start, Blocker.resolved_at < end)
            .order_by(Blocker.id)
        )
    )
    open_now = db.scalar(select(func.count()).select_from(Blocker).where(Blocker.status == "open")) or 0

    ev_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for t_, passed in db.execute(
        select(Evidence.type, Evidence.passed).where(
            Evidence.observed_at >= start,
            Evidence.observed_at < end,
            Evidence.voided_at.is_(None),
        )
    ):
        ev_counts[t_]["total"] += 1
        ev_counts[t_]["passed"] += 1 if passed else 0

    return {
        "range": {"start": mon.isoformat(), "end": sun.isoformat()},
        "study_days": len(days),
        "study_dates": sorted(d.isoformat() for d in days),
        "reviews": n_rev,
        "acc": acc,
        "reviews_by_reviewer": dict(by_reviewer),
        "minutes": sum(s.minutes or 0 for s in sessions),
        "sessions": session_items,
        "evidence": dict(ev_counts),
        "transitions": trans,
        "blockers": {
            "opened": len(opened),
            "resolved": len(resolved),
            "open_now": int(open_now),
            "opened_items": [blocker_brief(b) for b in opened],
            "resolved_items": [blocker_brief(b) | {"resolved_at": iso_local(b.resolved_at)} for b in resolved],
        },
    }


# ───────────────────────── 人工改状态 ─────────────────────────


def set_override(db: Session, point_id: str, state: str | None, reason: str) -> dict:
    reason = (reason or "").strip()
    if not reason:
        raise ApiError(422, "reason_required", "人工改状态必须写理由")
    if state is not None and state not in POINT_STATES:
        raise ApiError(422, "invalid_state", f"state 只能是 {'/'.join(POINT_STATES)} 或 null")
    p = db.get(Point, point_id)
    if p is None:
        raise ApiError(404, "not_found", "知识点不存在")
    if not p.active:
        raise ApiError(409, "point_inactive", "知识点已停用")
    now = utcnow()
    ps = db.get(PointState, point_id)
    if ps is None:  # 理论上导入时都建好了；兜底先算一次
        recompute_points(db, [point_id], cause="manual", now=now)
        ps = db.get(PointState, point_id)
    prev_override = ps.override_state
    if prev_override is None and "derived_state" not in (ps.stats or {}):
        # 老快照没有 derived_state：此刻没覆盖，ps.state 就是真实状态，先记下来给防抖分支用
        ps.stats = {**(ps.stats or {}), "derived_state": ps.state}
    ps.override_state = state
    ps.override_reason = reason[:500] if state is not None else None
    note = f"覆盖为 {state}：{reason}" if state is not None else f"撤销覆盖（原 {prev_override}）：{reason}"
    changes = recompute_points(
        db,
        [point_id],
        cause="manual",
        now=now,
        note=note,
        force_log=[point_id],
        fresh=[point_id] if state is None else (),
    )
    db.commit()
    ps = db.get(PointState, point_id)
    return {
        "point_id": point_id,
        "override_state": ps.override_state,
        "override_reason": ps.override_reason,
        "state": ps.state,
        "point_changes": changes,
        "stats": point_stats(db, [point_id])[point_id],
    }
