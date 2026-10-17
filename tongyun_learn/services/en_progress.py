"""单元毕业、钉子词、今日队列。纯函数，不碰数据库。

毕业默认：本单元 ≥80% 的卡处于 FSRS 复习态，近 3 天正确率 ≥85%，且没有连续错 ≥3 的钉子词。
生活英语：开发英语第 3 单元毕业后，每日队列最多占 20%。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from fsrs import State

from tongyun_learn.data.en_curriculum import (
    DEFAULT_GRADUATE_RULE,
    DEFAULT_TARGET,
    LIFE_AFTER_DEV_ORD,
    LIFE_FRACTION,
)

REVIEW_STATE = int(State.Review)


@dataclass
class CardSnap:
    card_id: int
    unit_id: int
    unit_ord: int
    unit_title: str
    track: str
    kind: str
    ord: int
    lemma: str
    phonetic: str
    cn: str
    pos: str
    sentences: list[dict[str, str]]
    state: int | None
    due: datetime | None
    reps: int
    lapses: int
    streak_wrong: int
    recent_correct: int
    recent_total: int
    unit_total: int = 0
    rule: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_GRADUATE_RULE))


@dataclass
class UnitProgress:
    unit_id: int
    track: str
    ord: int
    title: str
    kind: str
    total: int
    in_review: int
    recent_correct: int
    recent_total: int
    nail_card_ids: list[int]
    rule: dict[str, Any]
    unlocked: bool = False
    graduated: bool = False

    @property
    def review_ratio(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.in_review / self.total

    @property
    def recent_accuracy(self) -> float | None:
        if self.recent_total <= 0:
            return None
        return self.recent_correct / self.recent_total


def rule_of(raw: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_GRADUATE_RULE)
    if not raw:
        return out
    for key in out:
        if key in raw and raw[key] is not None:
            out[key] = raw[key]
    return out


def is_graduated(
    *,
    total: int,
    in_review: int,
    recent_total: int,
    recent_correct: int,
    nail_count: int,
    rule: dict[str, Any] | None = None,
) -> bool:
    cfg = rule_of(rule)
    if total <= 0:
        return False
    if in_review / total < float(cfg["review_ratio"]):
        return False
    if recent_total <= 0:
        return False
    if recent_correct / recent_total < float(cfg["recent_accuracy"]):
        return False
    return nail_count <= 0


def life_slot_cap(main_count: int, fraction: float = LIFE_FRACTION) -> int:
    """生活词条数上限：life / (main + life) ≤ fraction。主线为空时不单开生活队列。"""
    if main_count <= 0 or fraction <= 0:
        return 0
    cap = 0
    while (cap + 1) / (main_count + cap + 1) <= fraction + 1e-12:
        cap += 1
        if cap > 1000:
            break
    return cap


def _recent_low(snap: CardSnap) -> bool:
    if snap.recent_total < 2:
        return False
    return (snap.recent_correct / snap.recent_total) < 0.85


def _phases(snap: CardSnap, reason: str, force_sentences: bool) -> list[str]:
    if reason == "life" or not snap.sentences:
        return ["A"]
    want_b = False
    if reason == "nail":
        want_b = True
    elif reason == "due":
        want_b = snap.streak_wrong > 0 or snap.lapses > 0 or _recent_low(snap)
    elif reason == "new":
        want_b = force_sentences or snap.ord > (snap.unit_total + 1) // 2
    if want_b:
        return ["A", "B"]
    return ["A"]


def make_item(snap: CardSnap, phase: str, reason: str) -> dict[str, Any]:
    sentence = snap.sentences[0] if snap.sentences else None
    prompt: dict[str, Any] = {
        "cn": snap.cn,
        "phonetic": snap.phonetic,
        "pos": snap.pos,
        "zh": sentence["zh"] if phase == "B" and sentence else None,
        "sentence_index": 0 if phase == "B" and sentence else None,
    }
    return {
        "card_id": snap.card_id,
        "unit_id": snap.unit_id,
        "unit_ord": snap.unit_ord,
        "unit_title": snap.unit_title,
        "track": snap.track,
        "kind": snap.kind,
        "ord": snap.ord,
        "lemma": snap.lemma,
        "phase": phase,
        "reason": reason,
        "prompt": prompt,
    }


def _expand(snaps: list[CardSnap], reason: str, force_sentences: bool) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for snap in snaps:
        for phase in _phases(snap, reason, force_sentences):
            items.append(make_item(snap, phase, reason))
    return items


def cap_items(items: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    nail_n = sum(1 for i in items if i["reason"] == "nail")
    keep_rest = max(0, target - nail_n)
    out: list[dict[str, Any]] = []
    rest_kept = 0
    for item in items:
        if item["reason"] == "nail":
            out.append(item)
        elif rest_kept < keep_rest:
            out.append(item)
            rest_kept += 1
    return out


def apply_unlocks(units: list[UnitProgress]) -> None:
    """按顺序解锁。上一开发单元毕业才开下一单元。生活旁路等第 3 单元毕业。"""
    dev = sorted((u for u in units if u.kind == "dev"), key=lambda u: u.ord)
    prev = True
    for unit in dev:
        unit.unlocked = prev
        unit.graduated = bool(unit.unlocked) and is_graduated(
            total=unit.total,
            in_review=unit.in_review,
            recent_total=unit.recent_total,
            recent_correct=unit.recent_correct,
            nail_count=len(unit.nail_card_ids),
            rule=unit.rule,
        )
        prev = unit.graduated
    gate = next((u for u in dev if u.ord == LIFE_AFTER_DEV_ORD and u.graduated), None)
    life_on = gate is not None
    for unit in units:
        if unit.kind == "life":
            unit.unlocked = life_on
            unit.graduated = False


def current_dev_unit(units: list[UnitProgress]) -> UnitProgress | None:
    dev = sorted((u for u in units if u.kind == "dev"), key=lambda u: u.ord)
    for unit in dev:
        if unit.unlocked and not unit.graduated:
            return unit
    return dev[-1] if dev else None


def dev_all_graduated(units: list[UnitProgress]) -> bool:
    dev = [u for u in units if u.kind == "dev"]
    return bool(dev) and all(u.graduated for u in dev)


def life_unlocked(units: list[UnitProgress]) -> bool:
    return any(u.kind == "life" and u.unlocked for u in units)


def _is_new(snap: CardSnap) -> bool:
    return snap.reps <= 0 or not snap.state


def _is_due(snap: CardSnap, now: datetime) -> bool:
    return snap.reps > 0 and bool(snap.state) and snap.due is not None and snap.due <= now


def _is_nail(snap: CardSnap) -> bool:
    return snap.streak_wrong >= int(snap.rule.get("nail_streak") or 3)


def build_queue(
    snaps: list[CardSnap],
    units: list[UnitProgress],
    *,
    now: datetime,
    target: int = DEFAULT_TARGET,
    force_sentences: bool = False,
    life_fraction: float = LIFE_FRACTION,
) -> dict[str, Any]:
    apply_unlocks(units)
    current = current_dev_unit(units)
    by_unit = {u.unit_id: u for u in units}
    main_snaps = [s for s in snaps if by_unit.get(s.unit_id) and by_unit[s.unit_id].unlocked and s.kind == "dev"]
    life_snaps = [s for s in snaps if by_unit.get(s.unit_id) and by_unit[s.unit_id].unlocked and s.kind == "life"]

    nails = [s for s in main_snaps if _is_nail(s)]
    nail_ids = {s.card_id for s in nails}
    dues = [s for s in main_snaps if s.card_id not in nail_ids and _is_due(s, now)]
    dues.sort(key=lambda s: (-s.lapses, s.due or now, s.unit_ord, s.ord))
    news: list[CardSnap] = []
    if current is not None and not current.graduated:
        news = [
            s
            for s in main_snaps
            if s.unit_id == current.unit_id and s.card_id not in nail_ids and _is_new(s) and not _is_due(s, now)
        ]
        news.sort(key=lambda s: s.ord)

    main_items = _expand(nails, "nail", force_sentences)
    main_items += _expand(dues, "due", force_sentences)
    main_items += _expand(news, "new", force_sentences)
    main_items = cap_items(main_items, max(1, target))

    life_nails = [s for s in life_snaps if _is_nail(s)]
    life_nail_ids = {s.card_id for s in life_nails}
    life_rest = [s for s in life_snaps if s.card_id not in life_nail_ids and (_is_due(s, now) or _is_new(s))]
    life_rest.sort(key=lambda s: (0 if _is_due(s, now) else 1, s.ord))
    life_items = _expand(life_nails, "life", False) + _expand(life_rest, "life", False)
    cap = life_slot_cap(len(main_items), life_fraction)
    life_items = life_items[:cap]

    items = main_items + life_items
    return {
        "items": items,
        "include_sentences": any(i["phase"] == "B" for i in items),
        "target_count": target,
        "current_unit_id": current.unit_id if current else None,
        "life_unlocked": life_unlocked(units),
        "all_dev_graduated": dev_all_graduated(units),
    }


def nail_items(
    snaps: list[CardSnap],
    units: list[UnitProgress],
    *,
    force_sentences: bool = False,
) -> list[dict[str, Any]]:
    """当前仍是钉子、且单元已解锁的主线词。用来把漏掉的钉子补进已保存的队列。"""
    apply_unlocks(units)
    by_unit = {u.unit_id: u for u in units}
    nails = [
        s
        for s in snaps
        if s.kind == "dev" and by_unit.get(s.unit_id) and by_unit[s.unit_id].unlocked and _is_nail(s)
    ]
    return _expand(nails, "nail", force_sentences)


def recent_window_start(today_start_utc: datetime, recent_days: int) -> datetime:
    return today_start_utc - timedelta(days=max(recent_days, 1) - 1)
