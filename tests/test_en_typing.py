"""云芽英语：判分、毕业、今日队列、敲击入库、教练降级。"""

import json
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from fsrs import State
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.learn_helpers import WEB, learn_env  # noqa: F401
from tongyun_learn.ai.deepseek import DeepSeekError, complete_chat
from tongyun_learn.config import Settings, get_settings
from tongyun_learn.db import utcnow
from tongyun_learn.models import AiCache, Card, CardState, CoachPlan, ReviewLog, TypeEvent, Unit, UnitWord
from tongyun_learn.services.en_grade import grade_attempt, rating_for
from tongyun_learn.services.en_progress import is_graduated, life_slot_cap

REVIEW = int(State.Review)
LEARNING = int(State.Learning)


def test_grade_word_and_sentence():
    ok, shape = grade_attempt("read", "READ", "A", ignore_case=True)
    assert ok and shape is None
    ok, shape = grade_attempt("read", "Read", "A", ignore_case=False)
    assert not ok and shape == "case"
    ok, shape = grade_attempt("read", "red", "A")
    assert not ok and shape == "missing_letter"
    ok, shape = grade_attempt("require", "required", "A")
    assert not ok and shape == "suffix"
    ok, shape = grade_attempt("read", "read.", "A")
    assert not ok and shape == "punctuation"
    sentence = "Please read the error message before you retry."
    ok, shape = grade_attempt(sentence, "please read the error message before you retry", "B")
    assert ok and shape is None
    assert rating_for(True, 1) == 3
    assert rating_for(True, 2) == 2
    assert rating_for(False, 2) == 1


def test_graduation_threshold_and_life_cap():
    assert not is_graduated(total=8, in_review=6, recent_total=20, recent_correct=20, nail_count=0)
    assert is_graduated(total=8, in_review=7, recent_total=20, recent_correct=17, nail_count=0)
    assert not is_graduated(total=8, in_review=7, recent_total=20, recent_correct=16, nail_count=0)
    assert not is_graduated(total=8, in_review=8, recent_total=0, recent_correct=0, nail_count=0)
    assert not is_graduated(total=8, in_review=8, recent_total=20, recent_correct=20, nail_count=1)
    assert life_slot_cap(0) == 0
    assert life_slot_cap(1) == 0
    assert life_slot_cap(4) == 1
    assert life_slot_cap(8) == 2
    assert life_slot_cap(20) == 5
    for n in range(0, 40):
        cap = life_slot_cap(n)
        if n + cap:
            assert cap / (n + cap) <= 0.2 + 1e-9


def test_deepseek_error_redacts_key():
    secret = "sk-test-secret-value"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {secret}"
        return httpx.Response(500, text=f"boom {secret}")

    settings = Settings(deepseek_api_key=SecretStr(secret), deepseek_base_url="https://api.deepseek.com")
    with pytest.raises(DeepSeekError) as caught:
        complete_chat([{"role": "user", "content": "hi"}], settings, transport=httpx.MockTransport(handler))
    assert secret not in str(caught.value)
    assert "sk-test" not in caught.value.message


def _unit_cards(db: Session, track: str, ord_: int) -> tuple[Unit, list[tuple[UnitWord, Card]]]:
    db.rollback()
    unit = db.scalar(select(Unit).where(Unit.track == track, Unit.ord == ord_))
    assert unit is not None
    links = list(db.scalars(select(UnitWord).where(UnitWord.unit_id == unit.id).order_by(UnitWord.ord)))
    rows = []
    for link in links:
        card = db.get(Card, link.card_id)
        assert card is not None
        rows.append((link, card))
    return unit, rows


def _mark_review(db: Session, card_id: int, *, due_delta_days: float) -> None:
    now = utcnow()
    cs = db.get(CardState, card_id)
    if cs is None:
        cs = CardState(card_id=card_id, reps=0, lapses=0)
        db.add(cs)
    cs.state = REVIEW
    cs.step = None
    cs.stability = 8.0
    cs.difficulty = 5.0
    cs.reps = 4
    cs.lapses = 0
    cs.due = now + timedelta(days=due_delta_days)
    cs.first_review = now - timedelta(days=3)
    cs.last_review = now - timedelta(days=1)
    cs.last_rating = 3


def _event(
    db: Session,
    card: Card,
    unit: Unit,
    *,
    correct: bool,
    typed: str | None = None,
    days_ago: int = 0,
) -> None:
    db.add(
        TypeEvent(
            card_id=card.id,
            unit_id=unit.id,
            user_name="web",
            phase="A",
            correct=correct,
            typed=typed if typed is not None else (card.front or ""),
            expected=card.front,
            duration_ms=800,
            error_shape=None if correct else "other",
            created_at=utcnow() - timedelta(days=days_ago),
        )
    )


def _graduate(db: Session, track: str, ord_: int, *, review_count: int | None = None, due_past: int = 0) -> None:
    unit, rows = _unit_cards(db, track, ord_)
    n_review = len(rows) if review_count is None else review_count
    for i, (_link, card) in enumerate(rows):
        if i < n_review:
            due_days = -0.01 if i < due_past else 5
            _mark_review(db, card.id, due_delta_days=due_days)
        else:
            cs = db.get(CardState, card.id)
            if cs is None:
                cs = CardState(card_id=card.id, reps=1, lapses=0)
                db.add(cs)
            cs.state = LEARNING
            cs.reps = 1
            cs.due = utcnow() + timedelta(days=2)
            cs.stability = 1.0
            cs.difficulty = 5.0
            cs.last_review = utcnow()
            cs.first_review = utcnow()
        _event(db, card, unit, correct=True, days_ago=1)
    db.commit()


def test_health_today_type_coach_without_key(learn_env, client: TestClient, db_session: Session):  # noqa: F811
    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    denied = client.get("/v1/today")
    assert denied.status_code == 401

    today = client.get("/v1/today", headers=WEB)
    assert today.status_code == 200
    body = today.json()
    assert body["source"] == "rules"
    assert body["current_unit"]["ord"] == 1
    assert body["current_unit"]["graduated"] is False
    assert body["life_unlocked"] is False
    assert body["include_sentences"] is True
    lemmas = {item["lemma"] for item in body["items"]}
    assert "read" in lemmas
    assert "latency" not in lemmas
    assert "meeting" not in lemmas
    read_phases = [item["phase"] for item in body["items"] if item["lemma"] == "read"]
    assert read_phases == ["A"]
    assert any(item["phase"] == "B" and item["lemma"] == "ensure" for item in body["items"])
    assert db_session.scalar(select(func.count()).select_from(CoachPlan)) == 1

    read = next(item for item in body["items"] if item["lemma"] == "read" and item["phase"] == "A")
    typed = client.post(
        "/v1/type",
        headers=WEB,
        json={"card_id": read["card_id"], "phase": "A", "typed": "read", "duration_ms": 1500, "client_event_id": "e1"},
    )
    assert typed.status_code == 200, typed.text
    typed_body = typed.json()
    assert typed_body["correct"] is True
    assert typed_body["duplicate"] is False
    assert typed_body["card_state"]["reps"] == 1
    assert typed_body["rating"] == 3

    again = client.post(
        "/v1/type",
        headers=WEB,
        json={"card_id": read["card_id"], "phase": "A", "typed": "READ", "duration_ms": 10, "client_event_id": "e1"},
    )
    assert again.status_code == 200
    assert again.json()["duplicate"] is True
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(TypeEvent)) == 1
    assert db_session.scalar(select(func.count()).select_from(ReviewLog)) == 1

    wrong = client.post(
        "/v1/type",
        headers=WEB,
        json={"card_id": read["card_id"], "phase": "A", "typed": "red", "duration_ms": 900},
    )
    assert wrong.status_code == 200
    assert wrong.json()["correct"] is False
    assert wrong.json()["error_shape"] == "missing_letter"

    _unit, rows = _unit_cards(db_session, "en", 2)
    locked = client.post(
        "/v1/type",
        headers=WEB,
        json={"card_id": rows[0][1].id, "phase": "A", "typed": "latency", "duration_ms": 100},
    )
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "unit_locked"

    sentence = (db_session.get(Card, read["card_id"]).payload or {})["sentences"][0]["en"]
    loose = sentence.rstrip(".")
    phrase = client.post(
        "/v1/type",
        headers=WEB,
        json={"card_id": read["card_id"], "phase": "B", "typed": loose, "duration_ms": 4000, "sentence_index": 0},
    )
    assert phrase.status_code == 200, phrase.text
    assert phrase.json()["correct"] is True

    coach = client.get("/v1/coach", headers=WEB)
    assert coach.status_code == 200
    assert coach.json()["weak"]["current_unit"]["ord"] == 1
    made = client.post("/v1/coach", headers=WEB, json={})
    assert made.status_code == 200
    plan = made.json()["plan"]
    assert plan["source"] == "rules"
    assert plan["degraded"] is None
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(CoachPlan)) >= 2
    assert db_session.scalar(select(func.count()).select_from(AiCache).where(AiCache.kind == "coach_plan")) == 0


def test_nails_block_queue_and_graduation(learn_env, client: TestClient, db_session: Session):  # noqa: F811
    first = client.get("/v1/today", headers=WEB)
    read = next(item for item in first.json()["items"] if item["lemma"] == "read")
    for i in range(3):
        resp = client.post(
            "/v1/type",
            headers=WEB,
            json={
                "card_id": read["card_id"],
                "phase": "A",
                "typed": "red",
                "duration_ms": 100,
                "client_event_id": f"n{i}",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["correct"] is False
    today = client.get("/v1/today", headers=WEB).json()
    nail = [item for item in today["items"] if item["card_id"] == read["card_id"]]
    assert nail
    assert all(item["reason"] == "nail" for item in nail)
    weak = client.get("/v1/coach", headers=WEB).json()["weak"]
    assert any(n["lemma"] == "read" and n["streak"] >= 3 for n in weak["nails"])

    # 复习态和正确率都够，但 read 末尾仍是三连错，不能毕业。
    unit, rows = _unit_cards(db_session, "en", 1)
    for i, (_link, card) in enumerate(rows):
        if i < 7:
            _mark_review(db_session, card.id, due_delta_days=5)
        if card.id != read["card_id"]:
            for _ in range(3):
                _event(db_session, card, unit, correct=True)
    db_session.commit()
    refreshed = client.post("/v1/coach", headers=WEB, json={}).json()
    assert refreshed["weak"]["current_unit"]["ord"] == 1
    assert refreshed["weak"]["current_unit"]["graduated"] is False


def test_unit_graduation_unlocks_next_and_life_cap(learn_env, client: TestClient, db_session: Session):  # noqa: F811
    client.get("/v1/today", headers=WEB)
    _graduate(db_session, "en", 1, review_count=6)
    early = client.post("/v1/coach", headers=WEB, json={}).json()
    assert early["weak"]["current_unit"]["ord"] == 1

    _graduate(db_session, "en", 1, review_count=7)
    opened = client.post("/v1/coach", headers=WEB, json={}).json()
    assert opened["plan"]["source"] == "rules"
    assert opened["weak"]["current_unit"]["ord"] == 2
    today = client.get("/v1/today", headers=WEB).json()
    assert today["current_unit"]["ord"] == 2
    assert "latency" in {item["lemma"] for item in today["items"]}
    assert today["life_unlocked"] is False
    assert all(item["kind"] != "life" for item in today["items"])

    _graduate(db_session, "en", 2)
    _graduate(db_session, "en", 3, due_past=4)
    client.post("/v1/coach", headers=WEB, json={})
    mixed = client.get("/v1/today", headers=WEB).json()
    assert mixed["life_unlocked"] is True
    assert mixed["current_unit"]["ord"] == 3
    assert mixed["current_unit"]["graduated"] is True
    life = [item for item in mixed["items"] if item["kind"] == "life"]
    main = [item for item in mixed["items"] if item["kind"] != "life"]
    assert main
    assert life
    assert len(life) / len(mixed["items"]) <= 0.2 + 1e-9


def test_easier_shorter_and_harder_adds_sentences(learn_env, client: TestClient):  # noqa: F811
    client.get("/v1/today", headers=WEB)
    easier = client.post("/v1/coach", headers=WEB, json={"feedback": "easier"})
    assert easier.status_code == 200
    assert easier.json()["plan"]["target_count"] == 10
    today = client.get("/v1/today", headers=WEB).json()
    assert len(today["items"]) <= 10

    harder = client.post("/v1/coach", headers=WEB, json={"feedback": "harder"})
    assert harder.status_code == 200
    queued = client.get("/v1/today", headers=WEB).json()
    read_phases = [item["phase"] for item in queued["items"] if item["lemma"] == "read"]
    assert "B" in read_phases


def test_coach_uses_deepseek_when_configured(learn_env, client: TestClient, db_session: Session, monkeypatch):  # noqa: F811
    seeded = client.get("/v1/today", headers=WEB).json()
    card_id = seeded["items"][0]["card_id"]
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-unit-test")
    get_settings.cache_clear()

    def fake(messages, settings, transport=None):
        assert "sk-unit-test" not in json.dumps(messages)
        return {
            "text": json.dumps(
                {
                    "summary": "先把这个词敲熟。",
                    "include_sentences": False,
                    "target_count": 4,
                    "defer_next_unit": False,
                    "queue": [
                        {"card_id": card_id, "phase": "A", "reason": "focus"},
                        {"card_id": 999999, "phase": "A", "reason": "new"},
                    ],
                }
            ),
            "tokens_in": 11,
            "tokens_out": 7,
            "model": "deepseek-chat",
        }

    monkeypatch.setattr("tongyun_learn.services.en_coach.complete_chat", fake)
    made = client.post("/v1/coach", headers=WEB, json={})
    assert made.status_code == 200, made.text
    plan = made.json()["plan"]
    assert plan["source"] == "deepseek"
    assert plan["summary"] == "先把这个词敲熟。"
    ids = {item["card_id"] for item in plan["queue"]}
    assert card_id in ids
    assert 999999 not in ids
    db_session.rollback()
    cached = db_session.scalar(select(AiCache).where(AiCache.kind == "coach_plan"))
    assert cached is not None
    assert "sk-unit-test" not in json.dumps(cached.content, ensure_ascii=False)


def test_coach_falls_back_when_deepseek_returns_garbage(
    learn_env, client: TestClient, monkeypatch  # noqa: F811
):
    client.get("/v1/today", headers=WEB)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-unit-test")
    get_settings.cache_clear()

    def fake(messages, settings, transport=None):
        return {"text": "not-json", "tokens_in": 1, "tokens_out": 1, "model": "deepseek-chat"}

    monkeypatch.setattr("tongyun_learn.services.en_coach.complete_chat", fake)
    made = client.post("/v1/coach", headers=WEB, json={})
    assert made.status_code == 200
    plan = made.json()["plan"]
    assert plan["source"] == "rules"
    assert plan["degraded"] == "ai_bad_output"
    assert plan["queue"]
