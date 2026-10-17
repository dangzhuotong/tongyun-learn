from datetime import datetime, timedelta, timezone

from fsrs import Card as FsrsCard
from fsrs import State

from tongyun_learn.models import Card, CardState, Deck, Point, Stage
from tongyun_learn.routers.learn import point_out, stage_out
from tongyun_learn.services.cards import deck_out
from tongyun_learn.services.queue import card_out
from tongyun_learn.services.review import card_state_out
from tongyun_learn.services.srs import apply_review, retrievability, to_fsrs

NOW = datetime(2026, 10, 14, 10, 0, 0)


def test_apply_review_backfills_missing_first_review_and_returns_same_row():
    cs = CardState(
        card_id=1,
        state=int(State.Review),
        step=1,
        reps=2,
        lapses=0,
        stability=5.0,
        difficulty=5.0,
        first_review=None,
        last_review=NOW - timedelta(days=1),
        due=NOW,
    )
    out = apply_review(cs, card_id=1, rating=3, reviewed_at=NOW)
    assert out is cs
    assert out.first_review == NOW
    assert out.last_review == NOW
    assert out.last_rating == 3
    assert out.reps == 3


def test_apply_review_relearning_again_keeps_lapses():
    cs = CardState(
        card_id=2,
        state=int(State.Relearning),
        step=1,
        reps=5,
        lapses=2,
        stability=2.0,
        difficulty=6.0,
        first_review=NOW - timedelta(days=20),
        last_review=NOW - timedelta(days=1),
        due=NOW,
    )
    out = apply_review(cs, card_id=2, rating=1, reviewed_at=NOW)
    assert out.lapses == 2
    assert out.state == int(State.Relearning)
    assert out.reps == 6


def test_apply_review_treats_none_reps_as_zero():
    cs = CardState(
        card_id=3,
        state=int(State.Learning),
        step=1,
        reps=None,
        lapses=None,
        stability=1.0,
        difficulty=5.0,
        first_review=NOW - timedelta(minutes=10),
        last_review=NOW - timedelta(minutes=10),
        due=NOW,
    )
    out = apply_review(cs, card_id=3, rating=3, reviewed_at=NOW)
    assert out.reps == 1
    assert out.lapses is None


def test_to_fsrs_preserves_learning_state_and_step():
    cs = CardState(
        card_id=4,
        state=int(State.Learning),
        step=1,
        stability=1.0,
        difficulty=5.0,
        due=NOW,
        last_review=NOW - timedelta(minutes=5),
    )
    f = to_fsrs(cs)
    assert f.state == State.Learning
    assert f.step == 1
    assert f.stability == 1.0
    assert f.difficulty == 5.0
    assert f.due == NOW.replace(tzinfo=timezone.utc)


def test_to_fsrs_treats_none_state_as_new_card():
    assert to_fsrs(CardState(card_id=5, state=None)).state == FsrsCard().state
    assert to_fsrs(CardState(card_id=6, state=0)).state == FsrsCard().state


def test_retrievability_returns_none_when_stability_missing():
    cs = CardState(card_id=7, state=int(State.Review), stability=None, last_review=NOW)
    assert retrievability(cs, NOW) is None


def test_retrievability_at_stability_is_ninety_percent():
    cs = CardState(
        card_id=8,
        state=int(State.Review),
        stability=10.0,
        difficulty=3.0,
        last_review=NOW,
        due=NOW + timedelta(days=10),
    )
    r = retrievability(cs, NOW + timedelta(days=10))
    assert r is not None
    assert abs(r - 0.9) < 1e-9


def test_card_out_row_without_due_has_no_overdue():
    card = Card(deck_id=1, front="x")
    card.id = 9
    cs = CardState(card_id=9, state=int(State.Review), due=None, stability=1.0)
    out = card_out(card, cs, NOW)
    assert out["state"] == int(State.Review)
    assert out["due"] is None
    assert out["overdue_days"] is None


def test_card_state_out_minimal_row_defaults_to_none():
    out = card_state_out(CardState(card_id=1, state=int(State.Learning), due=None))
    assert out == {
        "state": int(State.Learning),
        "due": None,
        "stability": None,
        "difficulty": None,
        "reps": None,
        "lapses": None,
    }


def test_deck_out_preserves_empty_meta():
    out = deck_out(Deck(id=1, source=None, meta={}))
    assert out["meta"] == {}
    assert out["subject_id"] is None


def test_point_out_preserves_empty_tags():
    out = point_out(Point(id="p", active=True, tags=[]))
    assert out["tags"] == []
    assert out["card_types"] is None


def test_stage_out_nulls():
    out = stage_out(Stage(id="s", ord=0))
    assert out["ord"] == 0
    assert out["title"] is None
    assert out["exit_criteria"] is None
