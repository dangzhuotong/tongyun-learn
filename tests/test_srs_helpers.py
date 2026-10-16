from datetime import datetime, timedelta, timezone

import pytest
from fsrs import State

from tongyun_learn.models import CardState
from tongyun_learn.services.srs import _aware, _naive, apply_review, retrievability, to_fsrs

TZ8 = timezone(timedelta(hours=8))


def test_aware_none():
    assert _aware(None) is None


def test_aware_naive_becomes_utc():
    dt = datetime(2026, 10, 14, 12, 0, 0)
    out = _aware(dt)
    assert out.tzinfo == timezone.utc
    assert out.hour == 12


def test_aware_aware_is_converted_to_utc():
    dt = datetime(2026, 10, 14, 12, 0, 0, tzinfo=TZ8)
    out = _aware(dt)
    assert out == datetime(2026, 10, 14, 4, 0, 0, tzinfo=timezone.utc)


def test_naive_none():
    assert _naive(None) is None


@pytest.mark.parametrize(
    ("dt", "expected"),
    [
        (datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc), datetime(2026, 10, 14, 12, 0, 0)),
        (datetime(2026, 10, 14, 12, 0, 0, tzinfo=TZ8), datetime(2026, 10, 14, 4, 0, 0)),
    ],
)
def test_naive_strips_tzinfo(dt, expected):
    out = _naive(dt)
    assert out == expected
    assert out.tzinfo is None


def test_to_fsrs_aware_due_keeps_instant():
    due = datetime(2026, 10, 14, 20, 0, 0, tzinfo=TZ8)
    cs = CardState(card_id=1, state=int(State.Review), due=due, stability=5.0, difficulty=3.0)
    assert to_fsrs(cs).due == datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("rating", [1, 2, 3, 4])
def test_apply_review_new_card_all_ratings(rating):
    now = datetime(2026, 10, 14, 10, 0, 0)
    cs = apply_review(None, card_id=rating, rating=rating, reviewed_at=now)
    assert cs.reps == 1
    assert cs.lapses == 0
    assert cs.last_rating == rating
    assert cs.first_review == now
    assert cs.last_review == now
    assert cs.stability > 0
    assert cs.difficulty > 0
    assert cs.due is not None and cs.due.tzinfo is None


def test_apply_review_easy_schedules_further_than_hard():
    now = datetime(2026, 10, 14, 10, 0, 0)
    hard = apply_review(None, card_id=1, rating=2, reviewed_at=now)
    easy = apply_review(None, card_id=2, rating=4, reviewed_at=now)
    assert easy.stability > hard.stability
    assert easy.due > hard.due


def test_apply_review_keeps_existing_first_review():
    now = datetime(2026, 10, 14, 10, 0, 0)
    first = now - timedelta(days=30)
    cs = CardState(
        card_id=9,
        state=int(State.Review),
        reps=2,
        lapses=0,
        stability=4.0,
        difficulty=5.0,
        first_review=first,
        last_review=first,
        due=now,
    )
    updated = apply_review(cs, card_id=9, rating=3, reviewed_at=now)
    assert updated.first_review == first
    assert updated.reps == 3


def test_retrievability_aware_and_naive_now_agree():
    rev = datetime(2026, 10, 14, 10, 0, 0)
    cs = CardState(card_id=3, state=int(State.Review), stability=10.0, difficulty=3.0, last_review=rev)
    naive_now = rev + timedelta(days=3)
    aware_now = naive_now.replace(tzinfo=timezone.utc)
    assert retrievability(cs, aware_now) == retrievability(cs, naive_now)


def test_retrievability_new_card_has_none():
    now = datetime(2026, 10, 14, 10, 0, 0)
    assert retrievability(CardState(card_id=4, state=0, stability=1.0, last_review=now), now) is None
