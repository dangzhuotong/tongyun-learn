"""知识点状态重算（定稿 §4）+ 点数据 PointStats。

所有写操作（review / evidence / session / 建卡停卡 / 地图导入）在同一事务里调用 recompute_points，
它会沿硬前置的下游连锁重算。阈值不随时间自动变，所以不需要定时任务。
"""

from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tongyun_learn.models import (
    Blocker,
    Card,
    CardState,
    Evidence,
    Point,
    PointPrereq,
    PointState,
    PointStateLog,
    ReviewLog,
    SessionPoint,
)
from tongyun_learn.services import srs
from tongyun_learn.timeutil import iso_local, utcnow

DONE_STATES = {"learned", "mastered", "rusty"}  # 作为硬前置视为“学过”
STABLE_DAYS = 21
MASTER_RATIO = 0.8
MASTER_ACC = 0.85
MASTER_MIN_CARDS = 3
VOCAB_MIN_CARDS = 50
VOCAB_AGE_DAYS = 30
VOCAB_LEARNED_CARDS = 100
RUSTY_RATIO = 0.6
RUSTY_ACC = 0.7
EVIDENCE_DAYS = 60
RECHECK_DAYS = 90
EVIDENCE_REVIEWERS = ("axue", "migrate")


def is_vocab(p: Point) -> bool:
    return "en_word" in (p.tags or [])


def needed_evidence(p: Point) -> list[str]:
    if list(p.card_types or []) == ["memory"]:
        return []
    return list(p.mastery_evidence or [])


def _stable(cs: CardState) -> bool:
    return (cs.stability or 0) >= STABLE_DAYS and (cs.last_rating or 0) >= 3


def _latest_passed(evs: list[Evidence], t: str) -> datetime | None:
    ats = [
        e.observed_at
        for e in evs
        if e.type == t and e.passed and e.reviewer in EVIDENCE_REVIEWERS and e.observed_at is not None
    ]
    return max(ats) if ats else None


def stale_evidence(p: Point, evs: list[Evidence], now: datetime) -> list[list]:
    """need 类证据里最近一次达标早于 90 天（或没有）的：[[type, at|None], ...]。"""
    out = []
    for t in needed_evidence(p):
        at = _latest_passed(evs, t)
        if at is None or at < now - timedelta(days=RECHECK_DAYS):
            out.append([t, iso_local(at)])
    return out


def _compute(db: Session, p: Point, ps: PointState | None, now: datetime) -> tuple[str, dict, bool | None]:
    """返回 (新状态, stats 快照, needs_recheck 置位建议：True=置 1 / None=不动)。"""
    rows = db.execute(
        select(Card.id, CardState)
        .outerjoin(CardState, CardState.card_id == Card.id)
        .where(Card.point_id == p.id, Card.active.is_(True))
    ).all()
    n_active = len(rows)
    C = [cs for _cid, cs in rows if cs is not None and cs.state]
    ratio = len([c for c in C if _stable(c)]) / len(C) if C else 0.0
    last10 = db.scalars(
        select(ReviewLog.rating)
        .where(ReviewLog.point_id == p.id, ReviewLog.applied.is_(True))
        .order_by(ReviewLog.reviewed_at.desc(), ReviewLog.id.desc())
        .limit(10)
    ).all()
    acc10 = len([r for r in last10 if r >= 3]) / len(last10) if last10 else 0.0
    fsrs_ok = len(C) >= MASTER_MIN_CARDS and ratio >= MASTER_RATIO and acc10 >= MASTER_ACC
    vocab = is_vocab(p)
    if vocab:
        cutoff = now - timedelta(days=VOCAB_AGE_DAYS)
        C30 = [c for c in C if c.first_review is not None and c.first_review <= cutoff]
        ratio = len([c for c in C30 if _stable(c)]) / len(C30) if C30 else 0.0
        fsrs_ok = len(C30) >= VOCAB_MIN_CARDS and ratio >= MASTER_RATIO and acc10 >= MASTER_ACC

    need = needed_evidence(p)
    evs = db.scalars(select(Evidence).where(Evidence.point_id == p.id)).all()

    def ev_ok(t: str, days: int) -> bool:
        at = _latest_passed(evs, t)
        return at is not None and at >= now - timedelta(days=days)

    has_selftest = any(e.type == "selftest" for e in evs)
    has_passed_selftest = any(e.type == "selftest" and e.passed for e in evs)
    if vocab:
        learned = len(C) >= VOCAB_LEARNED_CARDS or has_passed_selftest
    else:
        learned = has_selftest or (n_active > 0 and len(C) == n_active)

    hard = db.execute(
        select(PointPrereq.prereq_id, Point.active, PointState.state)
        .join(Point, Point.id == PointPrereq.prereq_id)
        .outerjoin(PointState, PointState.point_id == PointPrereq.prereq_id)
        .where(PointPrereq.point_id == p.id, PointPrereq.kind == "hard")
    ).all()
    hard_ok = all((not active) or (st in DONE_STATES) for _pid, active, st in hard)

    has_session = db.scalar(select(func.count()).select_from(SessionPoint).where(SessionPoint.point_id == p.id)) > 0

    prev = ps.state if ps else None
    recheck: bool | None = None
    if prev == "mastered":
        s = "rusty" if (ratio < RUSTY_RATIO or acc10 < RUSTY_ACC) else "mastered"
    elif prev == "rusty":
        s = "mastered" if fsrs_ok else "rusty"
        if s == "mastered" and stale_evidence(p, evs, now):
            recheck = True
    elif fsrs_ok and all(ev_ok(t, EVIDENCE_DAYS) for t in need):
        s = "mastered"
    elif learned or (ps is not None and ps.learned_at is not None):
        s = "learned"
    elif C or has_session:
        s = "learning"
    elif hard_ok:
        s = "available"
    else:
        s = "locked"
    if ps is not None and ps.override_state:
        o = ps.override_state
        s = o if (o != "available" or s == "locked") else s

    stats = {
        "stable_ratio": round(ratio, 4),
        "recent_acc": round(acc10, 4),
        "recent_n": len(last10),
        "reviewed_cards": len(C),
        "active_cards": n_active,
    }
    return s, stats, recheck


def _hard_dependents(db: Session, pid: str) -> list[str]:
    return list(
        db.scalars(select(PointPrereq.point_id).where(PointPrereq.prereq_id == pid, PointPrereq.kind == "hard")).all()
    )


def recompute_points(
    db: Session,
    point_ids: Iterable[str],
    cause: str,
    cause_ref: str | None = None,
    evidence_point_ids: Iterable[str] = (),
    now: datetime | None = None,
) -> list[dict]:
    """重算给定点并沿硬前置下游连锁。返回状态变化 [{point_id, from, to}]（调用方负责 commit）。"""
    now = now or utcnow()
    ev_set = set(evidence_point_ids)
    queue: deque[str] = deque(dict.fromkeys(point_ids))
    queued = set(queue)
    changes: list[dict] = []
    guard = 0
    while queue:
        guard += 1
        if guard > 20000:  # 防御：图无环时不会到这里
            break
        pid = queue.popleft()
        queued.discard(pid)
        p = db.get(Point, pid)
        if p is None:
            continue
        ps = db.get(PointState, pid)
        prev = ps.state if ps else None
        if not p.active:
            # 停用点不重算，但它“视为已满足”可能解锁下游
            for d in _hard_dependents(db, pid):
                if d not in queued:
                    queue.append(d)
                    queued.add(d)
            continue
        s, stats, recheck = _compute(db, p, ps, now)
        if ps is None:
            ps = PointState(point_id=pid, state=s, since=now, ever_mastered=False, needs_recheck=False)
            db.add(ps)
        if recheck:
            ps.needs_recheck = True
        if pid in ev_set:
            ps.needs_recheck = False
        if s == "mastered":
            ps.ever_mastered = True
        if s in ("learned", "mastered") and ps.learned_at is None:
            ps.learned_at = now
        ps.stats = stats
        ps.computed_at = now
        if s != prev:
            ps.state = s
            ps.since = now
            db.add(
                PointStateLog(
                    point_id=pid,
                    from_state=prev,
                    to_state=s,
                    cause=cause,
                    cause_ref=str(cause_ref)[:64] if cause_ref is not None else None,
                    created_at=now,
                )
            )
            changes.append({"point_id": pid, "from": prev, "to": s})
            if (prev in DONE_STATES) != (s in DONE_STATES) or prev is None:
                for d in _hard_dependents(db, pid):
                    if d not in queued:
                        queue.append(d)
                        queued.add(d)
        db.flush()
    return changes


# ───────────────────────── 读：PointStats ─────────────────────────


def _num(v: Decimal | float | None) -> float | None:
    return float(v) if v is not None else None


def point_stats(db: Session, point_ids: list[str], now: datetime | None = None) -> dict[str, dict]:
    """批量算 PointStats：{state, since, cards, stable_ratio, recent_acc, avg_retrievability, next_due,
    evidence, open_blockers, needs_recheck}。稳固比例/最近正确率取重算时的快照，其余现算。"""
    now = now or utcnow()
    if not point_ids:
        return {}
    out: dict[str, dict] = {}
    states = {ps.point_id: ps for ps in db.scalars(select(PointState).where(PointState.point_id.in_(point_ids)))}
    cards: dict[str, dict] = defaultdict(lambda: {"new": 0, "learning": 0, "review": 0})
    rsum: dict[str, list[float]] = defaultdict(list)
    next_due: dict[str, datetime] = {}
    rows = db.execute(
        select(Card.point_id, CardState)
        .outerjoin(CardState, CardState.card_id == Card.id)
        .where(Card.point_id.in_(point_ids), Card.active.is_(True))
    ).all()
    for pid, cs in rows:
        if cs is None or not cs.state:
            cards[pid]["new"] += 1
            continue
        cards[pid]["review" if cs.state == 2 else "learning"] += 1
        r = srs.retrievability(cs, now)
        if r is not None:
            rsum[pid].append(r)
        if cs.due is not None and (pid not in next_due or cs.due < next_due[pid]):
            next_due[pid] = cs.due
    evidence: dict[str, dict] = defaultdict(dict)
    for e in db.scalars(
        select(Evidence).where(Evidence.point_id.in_(point_ids)).order_by(Evidence.observed_at, Evidence.id)
    ):
        evidence[e.point_id][e.type] = {
            "passed": bool(e.passed),
            "score": _num(e.score),
            "max": _num(e.max_score),
            "at": iso_local(e.observed_at),
        }
    blockers = dict(
        db.execute(
            select(Blocker.point_id, func.count())
            .where(Blocker.point_id.in_(point_ids), Blocker.status == "open")
            .group_by(Blocker.point_id)
        ).all()
    )
    for pid in point_ids:
        ps = states.get(pid)
        snap = (ps.stats or {}) if ps else {}
        rs = rsum.get(pid)
        out[pid] = {
            "state": ps.state if ps else None,
            "since": iso_local(ps.since) if ps else None,
            "cards": dict(cards[pid]),
            "stable_ratio": snap.get("stable_ratio", 0.0),
            "recent_acc": snap.get("recent_acc", 0.0),
            "avg_retrievability": round(sum(rs) / len(rs), 4) if rs else None,
            "next_due": iso_local(next_due.get(pid)),
            "evidence": evidence.get(pid, {}),
            "open_blockers": int(blockers.get(pid, 0)),
            "needs_recheck": bool(ps.needs_recheck) if ps else False,
        }
    return out
