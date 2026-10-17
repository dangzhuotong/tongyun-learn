"""云芽英语课表：种子入库，并装成队列用的快照。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tongyun_learn.data.en_curriculum import (
    DECK_NAME,
    DEFAULT_GRADUATE_RULE,
    SEED_VERSION,
    UNITS,
)
from tongyun_learn.db import utcnow
from tongyun_learn.models import Card, CardState, Deck, TypeEvent, Unit, UnitWord
from tongyun_learn.services.cardkeys import front_key
from tongyun_learn.services.en_progress import (
    REVIEW_STATE,
    CardSnap,
    UnitProgress,
    recent_window_start,
    rule_of,
)
from tongyun_learn.timeutil import day_bounds_utc, local_date, today_local


def seed_english(db: Session) -> dict[str, int]:
    """幂等写入单元、词卡和 unit_words。内容版本没变就直接返回。"""
    deck = db.scalar(select(Deck).where(Deck.kind == "en_word", Deck.name == DECK_NAME))
    if deck is not None and (deck.meta or {}).get("seed_version") == SEED_VERSION:
        n_units = db.scalar(select(Unit.id).where(Unit.track == "en", Unit.ord == 1).limit(1))
        if n_units is not None:
            return {"units": len(UNITS), "cards": 0, "created": 0, "skipped": 1}

    if deck is None:
        deck = Deck(
            subject_id=None,
            kind="en_word",
            name=DECK_NAME,
            source="builtin",
            review_cap=150,
            new_cap=20,
            meta={"track": "yun-ya-en", "seed_version": SEED_VERSION},
            created_at=utcnow(),
        )
        db.add(deck)
        db.flush()

    created = 0
    cards = 0
    for spec in UNITS:
        unit = db.scalar(select(Unit).where(Unit.track == spec["track"], Unit.ord == spec["ord"]))
        rule = None if spec["kind"] == "life" else dict(DEFAULT_GRADUATE_RULE)
        if unit is None:
            unit = Unit(
                track=spec["track"],
                ord=spec["ord"],
                title=spec["title"],
                kind=spec["kind"],
                graduate_rule_json=rule,
                active=True,
                created_at=utcnow(),
            )
            db.add(unit)
            db.flush()
        else:
            unit.title = spec["title"]
            unit.kind = spec["kind"]
            unit.graduate_rule_json = rule
            unit.active = True

        for i, word in enumerate(spec["words"], start=1):
            lemma = word["lemma"].strip()
            fk = front_key(lemma)
            card = db.scalar(select(Card).where(Card.deck_id == deck.id, Card.front_key == fk))
            payload = {
                "kind": "en_word",
                "word": lemma,
                "phonetic": word["phonetic"],
                "pos": word["pos"],
                "cn": word["cn"],
                "sentences": word["sentences"],
                "track": spec["kind"],
            }
            if card is None:
                card = Card(
                    deck_id=deck.id,
                    point_id=None,
                    card_type="memory",
                    front=lemma,
                    front_key=fk,
                    back=word["cn"],
                    payload=payload,
                    tags=["yun-ya", f"unit:{spec['ord']}", spec["kind"]],
                    created_by="example",
                    active=True,
                )
                db.add(card)
                db.flush()
                created += 1
            else:
                card.front = lemma
                card.back = word["cn"]
                card.payload = payload
                card.active = True
            cards += 1
            link = db.get(UnitWord, {"unit_id": unit.id, "card_id": card.id})
            if link is None:
                db.add(UnitWord(unit_id=unit.id, card_id=card.id, ord=i))
            else:
                link.ord = i

    deck.meta = {**(deck.meta or {}), "track": "yun-ya-en", "seed_version": SEED_VERSION}
    db.commit()
    return {"units": len(UNITS), "cards": cards, "created": created, "skipped": 0}


def _events_by_card(db: Session, user_name: str) -> dict[int, list[TypeEvent]]:
    rows = db.scalars(
        select(TypeEvent)
        .where(TypeEvent.user_name == user_name)
        .order_by(TypeEvent.created_at.asc(), TypeEvent.id.asc())
    ).all()
    grouped: dict[int, list[TypeEvent]] = defaultdict(list)
    for ev in rows:
        grouped[ev.card_id].append(ev)
    return grouped


def _streak(events: list[TypeEvent]) -> int:
    n = 0
    for ev in reversed(events):
        if ev.correct:
            break
        n += 1
    return n


def load_context(db: Session, user_name: str, now: datetime | None = None) -> dict[str, Any]:
    """种子 + 单元进度 + 词条快照。调用方可以接着组队列。"""
    seed_english(db)
    now = now or utcnow()
    day = today_local(now)
    today_start, today_end = day_bounds_utc(day)

    units = list(db.scalars(select(Unit).where(Unit.active.is_(True)).order_by(Unit.kind, Unit.ord)))
    links = list(db.scalars(select(UnitWord)))
    link_by_card = {ln.card_id: ln for ln in links}
    card_ids = [ln.card_id for ln in links]
    cards = {
        c.id: c
        for c in db.scalars(select(Card).where(Card.id.in_(card_ids or [-1]), Card.active.is_(True)))
    }
    states = {
        cs.card_id: cs
        for cs in db.scalars(select(CardState).where(CardState.card_id.in_(card_ids or [-1])))
    }
    events = _events_by_card(db, user_name)

    # 近 N 天窗口按各单元规则里最大的天数取，默认 3。
    max_days = 3
    for unit in units:
        max_days = max(max_days, int(rule_of(unit.graduate_rule_json)["recent_days"]))
    window_start = recent_window_start(today_start, max_days)

    snaps: list[CardSnap] = []
    per_unit_cards: dict[int, list[CardSnap]] = defaultdict(list)
    for unit in units:
        for ln in sorted((x for x in links if x.unit_id == unit.id), key=lambda x: x.ord):
            card = cards.get(ln.card_id)
            if card is None:
                continue
            payload = card.payload or {}
            sentences = payload.get("sentences") or []
            cs = states.get(card.id)
            evs = events.get(card.id, [])
            recent = [e for e in evs if e.created_at >= window_start]
            snap = CardSnap(
                card_id=card.id,
                unit_id=unit.id,
                unit_ord=unit.ord,
                unit_title=unit.title,
                track=unit.track,
                kind=unit.kind,
                ord=ln.ord,
                lemma=str(payload.get("word") or card.front or ""),
                phonetic=str(payload.get("phonetic") or ""),
                cn=str(payload.get("cn") or card.back or ""),
                pos=str(payload.get("pos") or ""),
                sentences=[
                    {"en": s.get("en") or "", "zh": s.get("zh") or ""} for s in sentences if isinstance(s, dict)
                ],
                state=cs.state if cs else None,
                due=cs.due if cs else None,
                reps=int(cs.reps or 0) if cs else 0,
                lapses=int(cs.lapses or 0) if cs else 0,
                streak_wrong=_streak(evs),
                recent_correct=sum(1 for e in recent if e.correct),
                recent_total=len(recent),
                rule=rule_of(unit.graduate_rule_json),
            )
            snaps.append(snap)
            per_unit_cards[unit.id].append(snap)

    progresses: list[UnitProgress] = []
    for unit in units:
        group = per_unit_cards.get(unit.id, [])
        rule = rule_of(unit.graduate_rule_json)
        days = int(rule["recent_days"])
        unit_window = recent_window_start(today_start, days)
        recent_events = [
            e
            for snap in group
            for e in events.get(snap.card_id, [])
            if e.created_at >= unit_window
        ]
        nail_ids = [s.card_id for s in group if s.streak_wrong >= int(rule["nail_streak"])]
        total = len(group)
        for snap in group:
            snap.unit_total = total
        progresses.append(
            UnitProgress(
                unit_id=unit.id,
                track=unit.track,
                ord=unit.ord,
                title=unit.title,
                kind=unit.kind,
                total=total,
                in_review=sum(1 for s in group if s.state == REVIEW_STATE),
                recent_correct=sum(1 for e in recent_events if e.correct),
                recent_total=len(recent_events),
                nail_card_ids=nail_ids,
                rule=rule,
            )
        )

    done_today = {
        (e.card_id, e.phase)
        for evs in events.values()
        for e in evs
        if e.correct and e.created_at >= today_start
    }
    return {
        "now": now,
        "today": day.isoformat(),
        "today_end": today_end,
        "snaps": snaps,
        "units": progresses,
        "cards": cards,
        "link_by_card": link_by_card,
        "done_today": done_today,
        "events": events,
    }


def find_card_unit(ctx: dict[str, Any], card_id: int) -> tuple[Card, UnitProgress, CardSnap] | None:
    card = ctx["cards"].get(card_id)
    if card is None:
        return None
    snap = next((s for s in ctx["snaps"] if s.card_id == card_id), None)
    unit = next((u for u in ctx["units"] if snap and u.unit_id == snap.unit_id), None)
    if snap is None or unit is None:
        return None
    return card, unit, snap


def expected_text(snap: CardSnap, phase: str, sentence_index: int | None) -> str | None:
    if phase == "A":
        return snap.lemma
    if not snap.sentences:
        return None
    idx = sentence_index or 0
    if idx < 0 or idx >= len(snap.sentences):
        return None
    return snap.sentences[idx]["en"]


def top_error_shape(events: list[TypeEvent]) -> str | None:
    counts: dict[str, int] = defaultdict(int)
    for ev in events:
        if not ev.correct and ev.error_shape:
            counts[ev.error_shape] += 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def study_streak_days(events: dict[int, list[TypeEvent]], today: datetime) -> int:
    """连续学习日：从今天或昨天往前数有敲击的本地日。today 是 naive UTC 的当前时刻。"""
    days = {local_date(ev.created_at) for evs in events.values() for ev in evs}
    if not days:
        return 0
    cursor = local_date(today)
    if cursor not in days:
        cursor = cursor - timedelta(days=1)
        if cursor not in days:
            return 0
    n = 0
    while cursor in days:
        n += 1
        cursor = cursor - timedelta(days=1)
    return n
