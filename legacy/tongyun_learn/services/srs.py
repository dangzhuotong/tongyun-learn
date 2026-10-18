"""py-fsrs 封装：card_state 行 <-> fsrs.Card，复习、可提取率。

- 关掉 fuzz，保证同样输入得到同样排程（便于测试和复算）。
- card_state.state：0 新卡（没行即新卡）、1 learning、2 review、3 relearning，与 fsrs.State 数值一致。
- reps / lapses 由我们自己累计：每次 applied 复习 reps+1；review 态评 Again 记一次 lapse。
"""

from datetime import datetime, timezone

from fsrs import Card as FsrsCard
from fsrs import Rating, Scheduler, State

from tongyun_learn.models import CardState

_scheduler = Scheduler(enable_fuzzing=False)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def to_fsrs(cs: CardState | None) -> FsrsCard:
    if cs is None or not cs.state:
        return FsrsCard()
    return FsrsCard(
        card_id=cs.card_id,
        state=State(cs.state),
        step=cs.step,
        stability=cs.stability,
        difficulty=cs.difficulty,
        due=_aware(cs.due),
        last_review=_aware(cs.last_review),
    )


def apply_review(cs: CardState | None, card_id: int, rating: int, reviewed_at: datetime) -> CardState:
    """在 reviewed_at（naive UTC）做一次复习，返回更新后的 CardState（新卡则新建，未 add 到 session）。"""
    prev_state = cs.state if cs is not None else 0
    card = to_fsrs(cs)
    new_card, _log = _scheduler.review_card(card, Rating(rating), review_datetime=_aware(reviewed_at))
    if cs is None:
        cs = CardState(card_id=card_id, reps=0, lapses=0, first_review=reviewed_at)
    if cs.first_review is None:
        cs.first_review = reviewed_at
    cs.state = int(new_card.state)
    cs.step = new_card.step
    cs.stability = new_card.stability
    cs.difficulty = new_card.difficulty
    cs.due = _naive(new_card.due)
    cs.last_review = reviewed_at
    cs.last_rating = rating
    cs.reps = (cs.reps or 0) + 1
    if rating == 1 and prev_state == int(State.Review):
        cs.lapses = (cs.lapses or 0) + 1
    return cs


def retrievability(cs: CardState, now: datetime) -> float | None:
    if cs is None or not cs.state or cs.last_review is None or not cs.stability:
        return None
    return float(_scheduler.get_card_retrievability(to_fsrs(cs), current_datetime=_aware(now)))
