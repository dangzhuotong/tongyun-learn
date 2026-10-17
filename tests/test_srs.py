from datetime import datetime, timedelta, timezone

from fsrs import Card as FsrsCard
from fsrs import State

from tongyun_learn.models import CardState
from tongyun_learn.services.srs import apply_review, retrievability, to_fsrs


def test_to_fsrs_none_and_zero_state():
    card_none = to_fsrs(None)
    assert isinstance(card_none, FsrsCard)
    assert card_none.state == FsrsCard().state

    cs_zero = CardState(card_id=1, state=0)
    card_zero = to_fsrs(cs_zero)
    assert isinstance(card_zero, FsrsCard)
    assert card_zero.state == FsrsCard().state


def test_to_fsrs_with_active_state():
    dt_naive = datetime(2026, 10, 14, 12, 0, 0)
    cs = CardState(
        card_id=42,
        state=int(State.Review),
        step=1,
        stability=8.5,
        difficulty=4.2,
        due=dt_naive,
        last_review=dt_naive - timedelta(days=2),
    )
    fsrs_c = to_fsrs(cs)
    assert fsrs_c.card_id == 42
    assert fsrs_c.state == State.Review
    assert fsrs_c.step == 1
    assert fsrs_c.stability == 8.5
    assert fsrs_c.difficulty == 4.2
    assert fsrs_c.due == dt_naive.replace(tzinfo=timezone.utc)
    assert fsrs_c.last_review == (dt_naive - timedelta(days=2)).replace(tzinfo=timezone.utc)


def test_apply_review_new_card():
    now = datetime(2026, 10, 14, 10, 0, 0)
    cs = apply_review(None, card_id=101, rating=3, reviewed_at=now)

    assert cs.card_id == 101
    assert cs.first_review == now
    assert cs.last_review == now
    assert cs.last_rating == 3
    assert cs.reps == 1
    assert cs.lapses == 0
    assert cs.due is not None
    assert cs.due.tzinfo is None
    assert cs.due >= now
    assert cs.stability > 0
    assert cs.difficulty > 0


def test_apply_review_review_state_again_increments_lapses():
    # 处于 Review 状态的卡片评 Again (1)，lapses 必须 +1
    now = datetime(2026, 10, 14, 10, 0, 0)
    first = now - timedelta(days=20)
    prev = now - timedelta(days=5)

    cs = CardState(
        card_id=202,
        state=int(State.Review),
        reps=4,
        lapses=1,
        stability=10.0,
        difficulty=3.0,
        first_review=first,
        last_review=prev,
        due=now,
    )

    updated = apply_review(cs, card_id=202, rating=1, reviewed_at=now)
    assert updated.reps == 5
    assert updated.lapses == 2
    assert updated.last_rating == 1
    assert updated.last_review == now
    assert updated.state == int(State.Relearning)


def test_apply_review_review_state_good_does_not_increment_lapses():
    # 处于 Review 状态的卡片评 Good (3)，lapses 不增加
    now = datetime(2026, 10, 14, 10, 0, 0)
    prev = now - timedelta(days=5)

    cs = CardState(
        card_id=203,
        state=int(State.Review),
        reps=3,
        lapses=1,
        stability=8.0,
        difficulty=3.5,
        first_review=prev - timedelta(days=10),
        last_review=prev,
        due=now,
    )

    updated = apply_review(cs, card_id=203, rating=3, reviewed_at=now)
    assert updated.reps == 4
    assert updated.lapses == 1
    assert updated.last_rating == 3
    assert updated.stability > 8.0


def test_apply_review_learning_state_again_does_not_increment_lapses():
    # 处于 Learning 状态（还未进入 Review）评 Again，不计入 lapses
    now = datetime(2026, 10, 14, 10, 0, 0)
    cs = CardState(
        card_id=204,
        state=int(State.Learning),
        reps=1,
        lapses=0,
        stability=1.0,
        difficulty=5.0,
        first_review=now - timedelta(minutes=10),
        last_review=now - timedelta(minutes=10),
        due=now,
    )

    updated = apply_review(cs, card_id=204, rating=1, reviewed_at=now)
    assert updated.reps == 2
    assert updated.lapses == 0


def test_apply_review_determinism():
    # 关闭 fuzzing 下，相同输入的调度结果完全一致
    t = datetime(2026, 10, 14, 8, 0, 0)
    cs1 = apply_review(None, card_id=999, rating=3, reviewed_at=t)
    cs2 = apply_review(None, card_id=999, rating=3, reviewed_at=t)

    assert cs1.due == cs2.due
    assert cs1.stability == cs2.stability
    assert cs1.difficulty == cs2.difficulty
    assert cs1.state == cs2.state


def test_retrievability_none_cases():
    now = datetime(2026, 10, 14, 12, 0, 0)
    # cs is None
    assert retrievability(None, now) is None

    # cs.state is 0
    assert retrievability(CardState(state=0), now) is None

    # last_review is None
    assert retrievability(CardState(state=2, stability=5.0, last_review=None), now) is None

    # stability is None or 0
    assert retrievability(CardState(state=2, stability=0.0, last_review=now), now) is None


def test_retrievability_value_and_decay():
    rev_time = datetime(2026, 10, 14, 10, 0, 0)
    cs = CardState(
        card_id=500,
        state=int(State.Review),
        stability=10.0,
        difficulty=3.0,
        last_review=rev_time,
        due=rev_time + timedelta(days=10),
    )

    # 刚复习完时，可提取率接近 1.0
    r0 = retrievability(cs, rev_time)
    assert r0 is not None
    assert 0.99 <= r0 <= 1.0

    # 5 天后
    r5 = retrievability(cs, rev_time + timedelta(days=5))
    assert r5 is not None

    # 20 天后
    r20 = retrievability(cs, rev_time + timedelta(days=20))
    assert r20 is not None

    # 随时间衰减
    assert r0 > r5 > r20
    assert 0.0 < r20 < 1.0
