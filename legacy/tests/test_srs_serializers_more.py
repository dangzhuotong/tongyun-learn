"""SRS 助手与序列化器的补充纯函数用例（不碰库、不联网）。"""

from datetime import datetime, timezone

from tongyun_learn.models import Card, CardState
from tongyun_learn.services.queue import card_out
from tongyun_learn.services.review import card_state_out
from tongyun_learn.services.srs import _aware, _naive, apply_review
from tongyun_learn.timeutil import iso_local

NOW = datetime(2026, 10, 14, 10, 0, 0)


def test_aware_leaves_utc_instant_unchanged():
    dt = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
    assert _aware(dt) == dt


def test_naive_utc_strips_tzinfo():
    out = _naive(datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc))
    assert out == datetime(2026, 10, 14, 12, 0, 0)
    assert out.tzinfo is None


def test_apply_review_again_schedules_sooner_than_good():
    again = apply_review(None, card_id=1, rating=1, reviewed_at=NOW)
    good = apply_review(None, card_id=2, rating=3, reviewed_at=NOW)
    assert again.due <= good.due
    assert again.stability <= good.stability


def test_apply_review_new_card_due_is_naive_utc():
    cs = apply_review(None, card_id=3, rating=2, reviewed_at=NOW)
    assert cs.due.tzinfo is None
    assert cs.due >= NOW
    assert cs.state in (1, 2, 3)


def test_card_out_keeps_payload_and_display_fields():
    card = Card(
        deck_id=7,
        point_id="en.vocab-general",
        card_type="memory",
        front="abandon",
        back="放弃",
        payload={"example_src": "en.vocab-general|abc"},
    )
    card.id = 21
    out = card_out(card, None, NOW)
    assert out["back"] == "放弃"
    assert out["card_type"] == "memory"
    assert out["point_id"] == "en.vocab-general"
    assert out["payload"] == {"example_src": "en.vocab-general|abc"}
    assert out["state"] == 0


def test_card_state_out_localizes_due():
    due = datetime(2026, 10, 13, 20, 0, 0)
    cs = CardState(card_id=1, state=2, due=due, stability=9.0, difficulty=4.0, reps=4, lapses=1)
    out = card_state_out(cs)
    assert out["due"] == iso_local(due)
    assert out["due"].endswith("+08:00")
