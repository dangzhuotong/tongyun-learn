from datetime import datetime, timedelta, timezone

import pytest
from fsrs import Card as FsrsCard
from fsrs import State

from tongyun_learn.errors import ApiError
from tongyun_learn.models import CardState
from tongyun_learn.services.review import _reviewed_at
from tongyun_learn.services.srs import (
    _aware,
    _naive,
    apply_review,
    retrievability,
    to_fsrs,
)
from tongyun_learn.services.state import _stable


def test_aware_helper_timezone_conversions():
    # 1. None
    assert _aware(None) is None

    # 2. Naive datetime -> assumed UTC and gets timezone.utc
    naive_dt = datetime(2026, 10, 15, 10, 0, 0)
    aware_dt = _aware(naive_dt)
    assert aware_dt is not None
    assert aware_dt.tzinfo == timezone.utc
    assert aware_dt.year == 2026 and aware_dt.hour == 10

    # 3. Already UTC aware
    utc_dt = datetime(2026, 10, 15, 10, 0, 0, tzinfo=timezone.utc)
    res_utc = _aware(utc_dt)
    assert res_utc == utc_dt
    assert res_utc.tzinfo == timezone.utc

    # 4. Aware in another timezone (e.g. UTC+8 Asia/Shanghai)
    tz_shanghai = timezone(timedelta(hours=8))
    shanghai_dt = datetime(2026, 10, 15, 18, 0, 0, tzinfo=tz_shanghai)
    res_shanghai = _aware(shanghai_dt)
    assert res_shanghai.tzinfo == timezone.utc
    # 18:00 UTC+8 -> 10:00 UTC
    assert res_shanghai.hour == 10


def test_naive_helper_timezone_conversions():
    # 1. None
    assert _naive(None) is None

    # 2. Aware UTC datetime -> stripped tzinfo
    utc_dt = datetime(2026, 10, 15, 12, 30, 0, tzinfo=timezone.utc)
    res_utc = _naive(utc_dt)
    assert res_utc == datetime(2026, 10, 15, 12, 30, 0)
    assert res_utc.tzinfo is None

    # 3. Aware in another timezone (e.g. UTC+9 Tokyo)
    tz_tokyo = timezone(timedelta(hours=9))
    tokyo_dt = datetime(2026, 10, 15, 21, 0, 0, tzinfo=tz_tokyo)
    res_tokyo = _naive(tokyo_dt)
    # 21:00 UTC+9 -> 12:00 UTC naive
    assert res_tokyo == datetime(2026, 10, 15, 12, 0, 0)
    assert res_tokyo.tzinfo is None


def test_to_fsrs_all_states():
    # Default / None card
    c_none = to_fsrs(None)
    assert isinstance(c_none, FsrsCard)

    c_zero = to_fsrs(CardState(state=0))
    assert isinstance(c_zero, FsrsCard)

    # Learning state (1)
    cs_learn = CardState(
        card_id=1,
        state=int(State.Learning),
        step=0,
        stability=1.2,
        difficulty=5.0,
        due=datetime(2026, 10, 15, 12, 0, 0),
        last_review=datetime(2026, 10, 15, 11, 50, 0),
    )
    f_learn = to_fsrs(cs_learn)
    assert f_learn.state == State.Learning
    assert f_learn.step == 0
    assert f_learn.stability == 1.2

    # Review state (2)
    cs_rev = CardState(
        card_id=2,
        state=int(State.Review),
        step=1,
        stability=15.0,
        difficulty=3.0,
        due=datetime(2026, 10, 25, 10, 0, 0),
        last_review=datetime(2026, 10, 15, 10, 0, 0),
    )
    f_rev = to_fsrs(cs_rev)
    assert f_rev.state == State.Review
    assert f_rev.stability == 15.0

    # Relearning state (3)
    cs_relearn = CardState(
        card_id=3,
        state=int(State.Relearning),
        step=0,
        stability=2.5,
        difficulty=6.0,
    )
    f_relearn = to_fsrs(cs_relearn)
    assert f_relearn.state == State.Relearning


def test_apply_review_all_ratings_on_new_card():
    now = datetime(2026, 10, 15, 10, 0, 0)

    # Rating 1: Again
    cs1 = apply_review(None, card_id=10, rating=1, reviewed_at=now)
    assert cs1.reps == 1
    assert cs1.lapses == 0
    assert cs1.last_rating == 1
    assert cs1.state == int(State.Learning)
    assert cs1.first_review == now

    # Rating 2: Hard
    cs2 = apply_review(None, card_id=11, rating=2, reviewed_at=now)
    assert cs2.reps == 1
    assert cs2.lapses == 0
    assert cs2.last_rating == 2
    assert cs2.state == int(State.Learning)

    # Rating 3: Good
    cs3 = apply_review(None, card_id=12, rating=3, reviewed_at=now)
    assert cs3.reps == 1
    assert cs3.lapses == 0
    assert cs3.last_rating == 3
    assert cs3.state == int(State.Learning)

    # Rating 4: Easy (directly graduates to Review)
    cs4 = apply_review(None, card_id=13, rating=4, reviewed_at=now)
    assert cs4.reps == 1
    assert cs4.lapses == 0
    assert cs4.last_rating == 4
    assert cs4.state == int(State.Review)
    assert cs4.stability > cs3.stability


def test_apply_review_multi_step_progression():
    t0 = datetime(2026, 10, 15, 10, 0, 0)

    # Step 1: Initial learning with Good
    cs = apply_review(None, card_id=99, rating=3, reviewed_at=t0)
    assert cs.reps == 1
    assert cs.first_review == t0
    assert cs.state == int(State.Learning)

    # Step 2: Next review after interval with Good
    t1 = t0 + timedelta(minutes=15)
    cs = apply_review(cs, card_id=99, rating=3, reviewed_at=t1)
    assert cs.reps == 2
    assert cs.first_review == t0  # Preserved!
    assert cs.last_review == t1
    assert cs.state == int(State.Review)

    # Step 3: In Review state, rate Again (1) -> should lapse
    t2 = t1 + timedelta(days=3)
    cs = apply_review(cs, card_id=99, rating=1, reviewed_at=t2)
    assert cs.reps == 3
    assert cs.lapses == 1
    assert cs.state == int(State.Relearning)

    # Step 4: In Relearning state, rate Again (1) -> lapses does NOT increment again
    t3 = t2 + timedelta(minutes=10)
    cs = apply_review(cs, card_id=99, rating=1, reviewed_at=t3)
    assert cs.reps == 4
    assert cs.lapses == 1  # Still 1!


def test_retrievability_monotonic_decay():
    rev_time = datetime(2026, 10, 15, 10, 0, 0)
    cs = CardState(
        card_id=888,
        state=int(State.Review),
        stability=10.0,
        difficulty=3.0,
        last_review=rev_time,
        due=rev_time + timedelta(days=10),
    )

    r_at_rev = retrievability(cs, rev_time)
    assert r_at_rev is not None
    assert 0.999 <= r_at_rev <= 1.0

    r_1d = retrievability(cs, rev_time + timedelta(days=1))
    r_5d = retrievability(cs, rev_time + timedelta(days=5))
    r_10d = retrievability(cs, rev_time + timedelta(days=10))
    r_30d = retrievability(cs, rev_time + timedelta(days=30))

    assert r_at_rev > r_1d > r_5d > r_10d > r_30d > 0.0


def test_stable_helper_boundary_conditions():
    # Exact threshold: stability == 21.0 and last_rating == 3
    assert _stable(CardState(stability=21.0, last_rating=3)) is True
    assert _stable(CardState(stability=21.0, last_rating=4)) is True

    # Just below stability threshold: 20.99
    assert _stable(CardState(stability=20.99, last_rating=3)) is False

    # Below rating threshold: last_rating == 2
    assert _stable(CardState(stability=30.0, last_rating=2)) is False
    assert _stable(CardState(stability=30.0, last_rating=1)) is False

    # Missing / None values
    assert _stable(CardState(stability=None, last_rating=3)) is False
    assert _stable(CardState(stability=25.0, last_rating=None)) is False
    assert _stable(CardState(stability=0.0, last_rating=0)) is False


def test_reviewed_at_future_slack_check():
    now = datetime(2026, 10, 15, 12, 0, 0)

    # None defaults to now
    assert _reviewed_at(None, now) == now

    # Past time is valid
    past = datetime(2026, 10, 14, 12, 0, 0)
    assert _reviewed_at(past, now) == past

    # Within 10 minutes slack is allowed
    future_allowed = now + timedelta(minutes=9)
    assert _reviewed_at(future_allowed, now) == future_allowed

    # Exceeding 10 minutes slack raises ApiError 422
    future_forbidden = now + timedelta(minutes=11)
    with pytest.raises(ApiError) as exc:
        _reviewed_at(future_forbidden, now)
    assert exc.value.status_code == 422
    assert exc.value.code == "validation_error"
