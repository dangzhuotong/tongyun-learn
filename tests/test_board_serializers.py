from datetime import datetime
from decimal import Decimal

import pytest

from tongyun_learn.models import Card, CardState, Deck, Point, Stage
from tongyun_learn.routers.learn import card_row, point_out, stage_out
from tongyun_learn.services.cards import deck_out
from tongyun_learn.services.queue import card_out
from tongyun_learn.services.review import card_state_out
from tongyun_learn.timeutil import iso_local


def test_point_out_full_fields():
    p = Point(
        id="tech-english.async-io",
        subject_id="tech-english",
        stage_id="stage-core",
        ord=10,
        title="Async I/O Concepts",
        description="Event loops and non-blocking sockets",
        card_types=["memory", "understand"],
        effort_hours=Decimal("3.5"),
        interview_weight=2,
        mastery_evidence=["selftest", "express"],
        tags=["python", "network"],
        active=True,
    )
    res = point_out(p)
    assert res == {
        "id": "tech-english.async-io",
        "subject_id": "tech-english",
        "stage_id": "stage-core",
        "ord": 10,
        "title": "Async I/O Concepts",
        "description": "Event loops and non-blocking sockets",
        "card_types": ["memory", "understand"],
        "effort_hours": 3.5,
        "interview_weight": 2,
        "mastery_evidence": ["selftest", "express"],
        "tags": ["python", "network"],
        "active": True,
    }
    assert isinstance(res["effort_hours"], float)


def test_point_out_nullable_fields():
    p = Point(
        id="java.nullability",
        subject_id="java-fde",
        stage_id=None,
        ord=None,
        title="Optional & Nulls",
        description=None,
        card_types=None,
        effort_hours=None,
        interview_weight=None,
        mastery_evidence=None,
        tags=None,
        active=False,
    )
    res = point_out(p)
    assert res["id"] == "java.nullability"
    assert res["effort_hours"] is None
    assert res["stage_id"] is None
    assert res["description"] is None
    assert res["card_types"] is None
    assert res["active"] is False


def test_stage_out_serialization():
    st = Stage(
        id="stage-01",
        subject_id="tech-english",
        ord=1,
        title="Foundation",
        weeks="Week 1-2",
        goal="Master technical vocabulary",
        deliverable="Complete 100 cards",
        exit_criteria="Pass selftest with >= 80%",
    )
    res = stage_out(st)
    assert res == {
        "id": "stage-01",
        "subject_id": "tech-english",
        "ord": 1,
        "title": "Foundation",
        "weeks": "Week 1-2",
        "goal": "Master technical vocabulary",
        "deliverable": "Complete 100 cards",
        "exit_criteria": "Pass selftest with >= 80%",
    }


def test_card_row_without_state():
    card = Card(
        id=101,
        deck_id=5,
        card_type="memory",
        front="latency",
        back="延迟",
        payload={"note": "network"},
        tags=["vocab", "easy"],
        created_by="axue",
        active=True,
    )
    res = card_row(card, None)
    assert res == {
        "card_id": 101,
        "deck_id": 5,
        "card_type": "memory",
        "front": "latency",
        "back": "延迟",
        "payload": {"note": "network"},
        "tags": ["vocab", "easy"],
        "created_by": "axue",
        "active": True,
        "state": 0,
        "due": None,
        "stability": None,
        "reps": 0,
        "lapses": 0,
    }


def test_card_row_with_state():
    due_dt = datetime(2026, 10, 20, 14, 0, 0)
    card = Card(
        id=102,
        deck_id=5,
        card_type="understand",
        front="What is idempotency?",
        back="Same effect on multiple executions",
        payload=None,
        tags=["design"],
        created_by="example",
        active=True,
    )
    cs = CardState(
        card_id=102,
        state=2,
        due=due_dt,
        stability=18.5,
        reps=4,
        lapses=1,
    )
    res = card_row(card, cs)
    assert res["card_id"] == 102
    assert res["state"] == 2
    assert res["due"] == iso_local(due_dt)
    assert res["stability"] == 18.5
    assert res["reps"] == 4
    assert res["lapses"] == 1


def test_deck_out_serialization():
    d = Deck(
        id=42,
        subject_id="tech-english",
        kind="en_word",
        name="tech-english:en_word",
        source="builtin",
        review_cap=100,
        new_cap=15,
        new_cap_deep=5,
        meta={"level": "CET-6", "tags": ["cs"]},
    )
    res = deck_out(d)
    assert res == {
        "id": 42,
        "subject_id": "tech-english",
        "kind": "en_word",
        "name": "tech-english:en_word",
        "source": "builtin",
        "review_cap": 100,
        "new_cap": 15,
        "new_cap_deep": 5,
        "meta": {"level": "CET-6", "tags": ["cs"]},
    }


def test_card_out_queue_serialization():
    now = datetime(2026, 10, 15, 10, 0, 0)
    card = Card(
        id=200,
        deck_id=10,
        point_id="p.net",
        card_type="memory",
        front="throughput",
        back="吞吐量",
        payload={"unit": "req/s"},
    )

    # 1. cs is None
    res_none = card_out(card, None, now)
    assert res_none["card_id"] == 200
    assert res_none["state"] == 0
    assert res_none["due"] is None
    assert res_none["overdue_days"] is None

    # 2. cs has overdue due date (2.5 days ago)
    past_due = now - datetime.resolution * 0 - (now - datetime(2026, 10, 12, 22, 0, 0))
    cs_overdue = CardState(
        card_id=200,
        state=2,
        due=datetime(2026, 10, 12, 22, 0, 0),  # 2.5 days prior to 2026-10-15 10:00:00
    )
    res_overdue = card_out(card, cs_overdue, now)
    assert res_overdue["state"] == 2
    assert res_overdue["due"] == iso_local(cs_overdue.due)
    assert res_overdue["overdue_days"] == 2.5

    # 3. cs has future due date
    cs_future = CardState(
        card_id=200,
        state=2,
        due=datetime(2026, 10, 18, 10, 0, 0),
    )
    res_future = card_out(card, cs_future, now)
    assert res_future["overdue_days"] == 0.0

    # 4. cs has None due
    cs_no_due = CardState(card_id=200, state=1, due=None)
    res_no_due = card_out(card, cs_no_due, now)
    assert res_no_due["overdue_days"] is None
    assert res_no_due["due"] is None


def test_card_state_out_serialization():
    # cs is None
    assert card_state_out(None) is None

    # cs has values
    due_dt = datetime(2026, 10, 19, 8, 30, 0)
    cs = CardState(
        state=2,
        due=due_dt,
        stability=12.34,
        difficulty=4.56,
        reps=7,
        lapses=2,
    )
    res = card_state_out(cs)
    assert res == {
        "state": 2,
        "due": iso_local(due_dt),
        "stability": 12.34,
        "difficulty": 4.56,
        "reps": 7,
        "lapses": 2,
    }
