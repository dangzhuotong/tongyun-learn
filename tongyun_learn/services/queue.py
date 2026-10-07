"""每日队列 GET /review/due 与推荐 GET /next（定稿 §4、决定 4/6）。

队列是对当前数据的纯计算（不写库）：同一时刻重复请求得到同样结果，复习后再请求会前移。
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tongyun_learn.models import Blocker, Card, CardState, Deck, Evidence, Point, PointPrereq, PointState, Stage
from tongyun_learn.services.state import DONE_STATES, point_stats, stale_evidence
from tongyun_learn.timeutil import day_bounds_utc, iso_local, today_local, utcnow

PER_SUBJECT_NEW_POINTS = 2
GLOBAL_NEW_POINTS = 3
DEEP_TYPES = ("understand", "express")


@dataclass
class DeckPlan:
    deck: Deck
    review: list[tuple[float, Card, CardState]] = field(default_factory=list)
    due_total: int = 0
    new_allowed: bool = True
    new_left: int = 0
    deep_left: int | None = None
    new: list[Card] = field(default_factory=list)
    pool: list[Card] = field(default_factory=list)


def card_out(card: Card, cs: CardState | None, now: datetime) -> dict:
    overdue = None
    if cs is not None and cs.due is not None:
        overdue = round(max(0.0, (now - cs.due).total_seconds() / 86400), 2)
    return {
        "card_id": card.id,
        "deck_id": card.deck_id,
        "point_id": card.point_id,
        "card_type": card.card_type,
        "front": card.front,
        "back": card.back,
        "payload": card.payload,
        "state": cs.state if cs is not None else 0,
        "due": iso_local(cs.due) if cs is not None else None,
        "overdue_days": overdue,
    }


def _point_meta(db: Session) -> dict[str, dict]:
    """启用点的排序信息：subject, stage_ord, ord, weight, state, unmet_soft。"""
    rows = db.execute(
        select(Point, Stage.ord, PointState.state)
        .join(Stage, Stage.id == Point.stage_id)
        .outerjoin(PointState, PointState.point_id == Point.id)
        .where(Point.active.is_(True))
    ).all()
    meta = {
        p.id: {
            "point": p,
            "subject": p.subject_id,
            "stage_ord": sord or 0,
            "ord": p.ord or 0,
            "weight": p.interview_weight or 0,
            "state": st,
            "unmet_soft": [],
        }
        for p, sord, st in rows
    }
    states = {pid: m["state"] for pid, m in meta.items()}
    inactive = set(db.scalars(select(Point.id).where(Point.active.is_(False))).all())
    for pp in db.scalars(select(PointPrereq).where(PointPrereq.kind == "soft")):
        if pp.point_id in meta and pp.prereq_id not in inactive and states.get(pp.prereq_id) not in DONE_STATES:
            meta[pp.point_id]["unmet_soft"].append(pp.prereq_id)
    return meta


def _sort_key_available(m: dict) -> tuple:
    return (m["stage_ord"], -m["weight"], len(m["unmet_soft"]), m["ord"])


def build_queue(
    db: Session,
    subject: str | None = None,
    deck_id: int | None = None,
    limit: int = 50,
    principal: str = "axue",
    now: datetime | None = None,
) -> dict:
    now = now or utcnow()
    day = today_local(now)
    start, end = day_bounds_utc(day)
    q = select(Deck)
    if subject:
        q = q.where(Deck.subject_id == subject)
    if deck_id:
        q = q.where(Deck.id == deck_id)
    decks = list(db.scalars(q.order_by(Deck.id)))
    meta = _point_meta(db)
    open_ok = {pid for pid, m in meta.items() if m["state"] not in (None, "locked")}

    def eligible(card: Card) -> bool:
        if principal == "web" and card.card_type == "handson":
            return False
        return card.point_id is None or card.point_id in open_ok

    # 今天已开的点（该点今天第一次出卡 = 其卡片最早 first_review 落在今天）
    first_rev = db.execute(
        select(Card.point_id, func.min(CardState.first_review))
        .join(CardState, CardState.card_id == Card.id)
        .where(Card.point_id.is_not(None))
        .group_by(Card.point_id)
    ).all()
    opened_today = {pid for pid, fr in first_rev if fr is not None and start <= fr < end}
    ever_opened = {pid for pid, fr in first_rev if fr is not None}
    opened_by_subject: dict[str, int] = defaultdict(int)
    for pid in opened_today:
        if pid in meta:
            opened_by_subject[meta[pid]["subject"]] += 1
    opened_global = len(opened_today)

    plans: list[DeckPlan] = []
    for d in decks:
        plan = DeckPlan(deck=d)
        rows = db.execute(
            select(Card, CardState)
            .outerjoin(CardState, CardState.card_id == Card.id)
            .where(Card.deck_id == d.id, Card.active.is_(True))
            .order_by(Card.id)
        ).all()
        reviewed_today = 0
        new_today = 0
        deep_today = 0
        new_cards: list[Card] = []
        due_items: list[tuple[float, Card, CardState]] = []
        for card, cs in rows:
            if cs is not None and cs.state:
                if cs.first_review is not None and start <= cs.first_review < end:
                    new_today += 1
                    if card.card_type in DEEP_TYPES:
                        deep_today += 1
                elif cs.last_review is not None and start <= cs.last_review < end:
                    reviewed_today += 1
                if not eligible(card):
                    continue
                if cs.due is not None and cs.due < end:
                    stab = max(cs.stability or 0.0, 0.1)
                    due_items.append(((now - cs.due).total_seconds() / 86400 / stab, card, cs))
            elif eligible(card):
                new_cards.append(card)
        due_items.sort(key=lambda t: (-t[0], t[1].id))
        plan.due_total = len(due_items)
        cap_left = max(0, (d.review_cap or 0) - reviewed_today)
        plan.review = due_items[:cap_left]
        plan.new_allowed = plan.due_total <= 2 * (d.review_cap or 0)
        plan.new_left = max(0, (d.new_cap or 0) - new_today) if plan.new_allowed else 0
        if d.new_cap_deep is not None:
            plan.deep_left = max(0, d.new_cap_deep - deep_today)
        plan.pool = new_cards
        plans.append(plan)

    def take(plan: DeckPlan, cards: list[Card]) -> int:
        n = 0
        for c in cards:
            if plan.new_left <= 0:
                break
            if c.card_type in DEEP_TYPES and plan.deep_left is not None:
                if plan.deep_left <= 0:
                    continue
                plan.deep_left -= 1
            plan.new.append(c)
            plan.new_left -= 1
            n += 1
        return n

    # 1) 不占“新开点”名额的：已开过的点（学习中等）和不挂点的卡
    for plan in plans:
        pool: list[Card] = plan.pool
        cont = [c for c in pool if c.point_id is None or c.point_id in ever_opened]
        cont.sort(
            key=lambda c: (
                0 if c.point_id else 1,
                meta[c.point_id]["stage_ord"] if c.point_id else 0,
                meta[c.point_id]["ord"] if c.point_id else 0,
                c.id,
            )
        )
        take(plan, cont)

    # 2) 新开点：每学科 ≤2、全局 ≤3，按学科轮流取，先到先占
    by_subject: dict[str, list[str]] = defaultdict(list)
    plans_by_subject: dict[str, list[DeckPlan]] = defaultdict(list)
    for plan in plans:
        if plan.deck.subject_id:
            plans_by_subject[plan.deck.subject_id].append(plan)
    for plan in plans:
        for c in plan.pool:
            pid = c.point_id
            if pid and pid not in ever_opened and pid in meta and pid not in by_subject[meta[pid]["subject"]]:
                by_subject[meta[pid]["subject"]].append(pid)
    for subj in by_subject:
        # 学习中（只开过课、还没出过卡）的点优先，其次可学点按 §4 排序
        by_subject[subj].sort(
            key=lambda pid: (0 if meta[pid]["state"] == "learning" else 1, *_sort_key_available(meta[pid]))
        )
    opening: list[str] = []
    progressed = True
    while progressed and opened_global < GLOBAL_NEW_POINTS:
        progressed = False
        for subj in sorted(by_subject):
            if opened_global >= GLOBAL_NEW_POINTS:
                break
            if opened_by_subject[subj] >= PER_SUBJECT_NEW_POINTS:
                continue
            while by_subject[subj]:
                pid = by_subject[subj].pop(0)
                got = 0
                for plan in plans_by_subject[subj]:
                    cards = [c for c in plan.pool if c.point_id == pid]
                    got += take(plan, cards)
                if got:
                    opening.append(pid)
                    opened_by_subject[subj] += 1
                    opened_global += 1
                    progressed = True
                    break

    reviews = sorted((t for p in plans for t in p.review), key=lambda t: (-t[0], t[1].id))
    review_out = [card_out(c, cs, now) for _o, c, cs in reviews][:limit]
    new_out = [card_out(c, None, now) for p in plans for c in p.new][: max(0, limit - len(review_out))]
    return {
        "date": day.isoformat(),
        "review": review_out,
        "new": new_out,
        "counts": {
            "due_total": sum(p.due_total for p in plans),
            "backlog": sum(max(0, p.due_total - len(p.review)) for p in plans),
            "new_blocked": sum(1 for p in plans if not p.new_allowed),
            "points_opened_today": len(opened_today),
            "points_opening": opening,
        },
    }


def next_points(db: Session, subject: str | None = None, limit: int = 5, now: datetime | None = None) -> dict:
    now = now or utcnow()
    q = (
        select(Point, PointState)
        .join(PointState, PointState.point_id == Point.id)
        .where(Point.active.is_(True), PointState.needs_recheck.is_(True))
    )
    if subject:
        q = q.where(Point.subject_id == subject)
    recheck = []
    for p, _ps in db.execute(q.order_by(Point.subject_id, Point.ord)).all():
        evs = list(db.scalars(select(Evidence).where(Evidence.point_id == p.id)))
        recheck.append({"point_id": p.id, "title": p.title, "stale_evidence": stale_evidence(p, evs, now)})

    meta = _point_meta(db)
    cands = [
        m for m in meta.values() if m["state"] in ("learning", "available") and (not subject or m["subject"] == subject)
    ]
    cands.sort(key=lambda m: (0 if m["state"] == "learning" else 1, *_sort_key_available(m)))
    cands = cands[: max(0, limit)]
    ids = [m["point"].id for m in cands]
    blockers = dict(
        db.execute(
            select(Blocker.point_id, func.count())
            .where(Blocker.point_id.in_(ids or [""]), Blocker.status == "open")
            .group_by(Blocker.point_id)
        ).all()
    )
    new_cards = dict(
        db.execute(
            select(Card.point_id, func.count())
            .outerjoin(CardState, CardState.card_id == Card.id)
            .where(Card.point_id.in_(ids or [""]), Card.active.is_(True), CardState.card_id.is_(None))
            .group_by(Card.point_id)
        ).all()
    )
    nxt = []
    for m in cands:
        p = m["point"]
        n_new = int(new_cards.get(p.id, 0))
        if m["state"] == "learning":
            reason = f"学习中，还有 {n_new} 张新卡" if n_new else "学习中，卡片都已开始复习，可做自测把它推到学过"
        else:
            reason = f"可学：第 {m['stage_ord']} 阶段，面试权重 {m['weight']}"
            if m["unmet_soft"]:
                reason += f"，建议先看 {len(m['unmet_soft'])} 个软前置"
        nxt.append(
            {
                "point_id": p.id,
                "title": p.title,
                "state": m["state"],
                "reason": reason,
                "unmet_soft": m["unmet_soft"],
                "open_blockers": int(blockers.get(p.id, 0)),
                "new_cards": n_new,
            }
        )
    return {"recheck": recheck, "next": nxt}


def progress(db: Session, subject: str | None = None, stage: str | None = None, now: datetime | None = None) -> dict:
    from tongyun_learn.models import ReviewLog  # 局部导入避免循环

    now = now or utcnow()
    pq = select(Point.id).where(Point.active.is_(True))
    if subject:
        pq = pq.where(Point.subject_id == subject)
    if stage:
        pq = pq.where(Point.stage_id == stage)
    pids = list(db.scalars(pq).all())
    by_state: dict[str, int] = defaultdict(int)
    for st in db.scalars(select(PointState.state).where(PointState.point_id.in_(pids or [""]))):
        by_state[st] += 1

    deck_q = select(Deck.id)
    if subject:
        deck_q = deck_q.where(Deck.subject_id == subject)
    deck_ids = list(db.scalars(deck_q).all())
    card_filter = [Card.active.is_(True), Card.deck_id.in_(deck_ids or [-1])]
    if stage:
        card_filter.append(Card.point_id.in_(pids or [""]))
    _, end = day_bounds_utc(today_local(now))
    due_today = db.scalar(
        select(func.count())
        .select_from(Card)
        .join(CardState, CardState.card_id == Card.id)
        .where(*card_filter, CardState.due < end)
    )
    log_filter = [ReviewLog.applied.is_(True)]
    card_ids_q = select(Card.id).where(*card_filter)
    log_filter.append(ReviewLog.card_id.in_(card_ids_q))
    since30 = now - timedelta(days=30)
    r30 = db.execute(select(ReviewLog.rating).where(*log_filter, ReviewLog.reviewed_at >= since30)).scalars().all()
    retention = round(len([r for r in r30 if r >= 2]) / len(r30), 4) if r30 else None

    last7 = []
    today = today_local(now)
    first7_start, _ = day_bounds_utc(today - timedelta(days=6))
    logs = db.execute(
        select(ReviewLog.reviewed_at, ReviewLog.rating).where(*log_filter, ReviewLog.reviewed_at >= first7_start)
    ).all()
    firsts = db.scalars(
        select(CardState.first_review)
        .join(Card, Card.id == CardState.card_id)
        .where(*card_filter, CardState.first_review >= first7_start)
    ).all()
    from tongyun_learn.timeutil import local_date

    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        rs = [r for at, r in logs if local_date(at) == d]
        last7.append(
            {
                "date": d.isoformat(),
                "reviews": len(rs),
                "acc": round(len([r for r in rs if r >= 3]) / len(rs), 4) if rs else None,
                "new_cards": len([f for f in firsts if local_date(f) == d]),
            }
        )

    sq = select(Stage).where(Stage.active.is_(True))
    if subject:
        sq = sq.where(Stage.subject_id == subject)
    if stage:
        sq = sq.where(Stage.id == stage)
    stages_out = [stage_status(db, st) for st in db.scalars(sq.order_by(Stage.subject_id, Stage.ord))]
    return {
        "points_by_state": dict(by_state),
        "due_today": int(due_today or 0),
        "retention_30d": retention,
        "last7": last7,
        "stages": stages_out,
    }


def stage_status(db: Session, st: Stage) -> dict:
    rows = db.execute(
        select(Point.id, PointState.state)
        .outerjoin(PointState, PointState.point_id == Point.id)
        .where(Point.stage_id == st.id, Point.active.is_(True), Point.interview_weight >= 2)
    ).all()
    learned = len([1 for _pid, s in rows if s in DONE_STATES])
    exit_ev = (
        db.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.stage_id == st.id, Evidence.passed.is_(True))
        )
        > 0
    )
    return {
        "id": st.id,
        "weight2_learned": f"{learned}/{len(rows)}",
        "exit_evidence": exit_ev,
        "passed": learned == len(rows) and exit_ev,
    }


__all__ = ["build_queue", "next_points", "progress", "stage_status", "point_stats", "card_out"]
