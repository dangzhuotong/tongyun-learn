from datetime import datetime, timedelta
from decimal import Decimal

from tongyun_learn.models import Blocker, Card, CardState, Deck, Point, Stage
from tongyun_learn.routers.learn import point_out, stage_out
from tongyun_learn.services.blockers import blocker_out
from tongyun_learn.services.cards import deck_out
from tongyun_learn.services.insights import blocker_brief
from tongyun_learn.services.queue import card_out
from tongyun_learn.services.review import card_state_out
from tongyun_learn.timeutil import iso_local

NOW = datetime(2026, 10, 14, 12, 0, 0)


def test_card_state_out_none():
    assert card_state_out(None) is None


def test_card_state_out_full():
    due = datetime(2026, 10, 13, 20, 0, 0)
    cs = CardState(card_id=1, state=2, step=1, due=due, stability=8.5, difficulty=4.2, reps=5, lapses=2)
    out = card_state_out(cs)
    assert out == {
        "state": 2,
        "due": iso_local(due),
        "stability": 8.5,
        "difficulty": 4.2,
        "reps": 5,
        "lapses": 2,
    }


def test_card_out_new_card():
    card = Card(deck_id=3, point_id="p.1", card_type="memory", front="abandon", back="放弃")
    card.id = 11
    out = card_out(card, None, NOW)
    assert out["card_id"] == 11
    assert out["deck_id"] == 3
    assert out["point_id"] == "p.1"
    assert out["state"] == 0
    assert out["due"] is None
    assert out["overdue_days"] is None


def test_card_out_overdue_rounding():
    card = Card(deck_id=3, front="abandon")
    card.id = 12
    cs = CardState(card_id=12, state=2, due=NOW - timedelta(days=2, hours=12), stability=5.0)
    out = card_out(card, cs, NOW)
    assert out["state"] == 2
    assert out["due"] == iso_local(cs.due)
    assert out["overdue_days"] == 2.5


def test_card_out_not_yet_due_is_zero_overdue():
    card = Card(deck_id=3, front="abandon")
    card.id = 13
    cs = CardState(card_id=13, state=2, due=NOW + timedelta(hours=6), stability=5.0)
    assert card_out(card, cs, NOW)["overdue_days"] == 0.0


def test_blocker_out_without_point():
    b = Blocker(id=5, point_id=None, title="卡点", detail="d", status="open", created_at=NOW)
    out = blocker_out(None, b)
    assert out["id"] == 5
    assert out["point_id"] is None
    assert out["point_title"] is None
    assert out["status"] == "open"
    assert out["created_at"] == iso_local(NOW)
    assert out["resolved_at"] is None
    assert out["resolution"] is None
    assert out["legacy_ref"] is None


def test_blocker_out_with_point_title_skips_db():
    resolved = NOW + timedelta(hours=1)
    b = Blocker(
        id=6,
        point_id="p.1",
        title="卡点",
        status="resolved",
        created_at=NOW,
        resolved_at=resolved,
        resolution="已解决",
    )
    out = blocker_out(None, b, point_title="知识点")
    assert out["point_title"] == "知识点"
    assert out["status"] == "resolved"
    assert out["resolved_at"] == iso_local(resolved)
    assert out["resolution"] == "已解决"


def test_blocker_brief():
    created = datetime(2026, 10, 14, 3, 30, 0)
    b = Blocker(id=7, point_id="p.2", session_id=9, title="t", detail="d", status="open", created_at=created)
    out = blocker_brief(b)
    assert out == {
        "id": 7,
        "point_id": "p.2",
        "session_id": 9,
        "title": "t",
        "detail": "d",
        "status": "open",
        "created_at": iso_local(created),
    }


def test_deck_out():
    d = Deck(
        id=2,
        subject_id="tech-english",
        kind="en_word",
        name="tech-english:en_word",
        source="map",
        review_cap=60,
        new_cap=8,
        new_cap_deep=3,
        meta={"default_point": "p.1"},
    )
    assert deck_out(d) == {
        "id": 2,
        "subject_id": "tech-english",
        "kind": "en_word",
        "name": "tech-english:en_word",
        "source": "map",
        "review_cap": 60,
        "new_cap": 8,
        "new_cap_deep": 3,
        "meta": {"default_point": "p.1"},
    }


def test_deck_out_nulls():
    d = Deck(id=4, subject_id=None, kind=None, name=None, source=None)
    out = deck_out(d)
    assert out["subject_id"] is None
    assert out["meta"] is None
    assert out["review_cap"] is None


def test_point_out_with_decimal_effort():
    p = Point(
        id="p.1",
        subject_id="java-fde",
        stage_id="s.1",
        ord=2,
        title="标题",
        description="描述",
        card_types=["memory", "understand"],
        effort_hours=Decimal("1.5"),
        interview_weight=3,
        mastery_evidence=["selftest"],
        tags=["git"],
        active=True,
    )
    out = point_out(p)
    assert out["id"] == "p.1"
    assert out["effort_hours"] == 1.5
    assert isinstance(out["effort_hours"], float)
    assert out["card_types"] == ["memory", "understand"]
    assert out["interview_weight"] == 3
    assert out["mastery_evidence"] == ["selftest"]
    assert out["active"] is True


def test_point_out_without_effort():
    p = Point(id="p.2", subject_id="s", stage_id="st", effort_hours=None, active=False)
    out = point_out(p)
    assert out["effort_hours"] is None
    assert out["active"] is False


def test_stage_out():
    st = Stage(
        id="s.1",
        subject_id="java-fde",
        ord=1,
        title="阶段",
        weeks="W1-W2",
        goal="目标",
        deliverable="交付",
        exit_criteria="完成",
    )
    assert stage_out(st) == {
        "id": "s.1",
        "subject_id": "java-fde",
        "ord": 1,
        "title": "阶段",
        "weeks": "W1-W2",
        "goal": "目标",
        "deliverable": "交付",
        "exit_criteria": "完成",
    }
