"""P3a 学习接口（定稿 §2）。web 令牌只读 + POST /review(/batch)；其余写接口仅 axue。"""

from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tongyun_learn.auth import Principal, get_principal, require
from tongyun_learn.db import get_db
from tongyun_learn.errors import ApiError
from tongyun_learn.models import (
    Blocker,
    Card,
    CardState,
    Deck,
    Evidence,
    Point,
    PointPrereq,
    PointState,
    Stage,
    Subject,
)
from tongyun_learn.routers.deps import WriteDb, mark_dry
from tongyun_learn.services import cards as card_svc
from tongyun_learn.services import queue as queue_svc
from tongyun_learn.services import review as review_svc
from tongyun_learn.services import tutor as tutor_svc
from tongyun_learn.services.importer import import_maps
from tongyun_learn.services.state import point_stats
from tongyun_learn.timeutil import iso_local

router = APIRouter(tags=["learn"])

Db = Annotated[Session, Depends(get_db)]
AnyP = Annotated[Principal, Depends(get_principal)]
Axue = Annotated[Principal, Depends(require("axue"))]

CardType = Literal["memory", "understand", "handson", "express"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ───────────────────────── 地图 ─────────────────────────


class ImportBody(Strict):
    files: list[Annotated[str, Field(min_length=1, max_length=2_000_000)]] = Field(min_length=1, max_length=20)


@router.post("/maps/import")
def maps_import(body: ImportBody, _p: Axue, db: Db, dry_run: bool = True) -> dict:
    return import_maps(db, body.files, dry_run)


def _points_by_state(db: Session, subject_id: str) -> dict[str, int]:
    rows = db.execute(
        select(PointState.state, func.count())
        .join(Point, Point.id == PointState.point_id)
        .where(Point.subject_id == subject_id, Point.active.is_(True))
        .group_by(PointState.state)
    ).all()
    return {s: int(n) for s, n in rows}


@router.get("/subjects")
def list_subjects(_p: AnyP, db: Db) -> list[dict]:
    out = []
    for s in db.scalars(select(Subject).where(Subject.active.is_(True)).order_by(Subject.id)):
        out.append(
            {
                "id": s.id,
                "title": s.title,
                "goal": s.goal,
                "map_version": s.map_version,
                "points_by_state": _points_by_state(db, s.id),
            }
        )
    return out


def point_out(p: Point) -> dict:
    return {
        "id": p.id,
        "subject_id": p.subject_id,
        "stage_id": p.stage_id,
        "ord": p.ord,
        "title": p.title,
        "description": p.description,
        "card_types": p.card_types,
        "effort_hours": float(p.effort_hours) if p.effort_hours is not None else None,
        "interview_weight": p.interview_weight,
        "mastery_evidence": p.mastery_evidence,
        "tags": p.tags,
        "active": p.active,
    }


def stage_out(st: Stage) -> dict:
    return {
        "id": st.id,
        "subject_id": st.subject_id,
        "ord": st.ord,
        "title": st.title,
        "weeks": st.weeks,
        "goal": st.goal,
        "deliverable": st.deliverable,
        "exit_criteria": st.exit_criteria,
    }


@router.get("/subjects/{subject_id}/map")
def subject_map(subject_id: str, _p: AnyP, db: Db) -> dict:
    s = db.get(Subject, subject_id)
    if s is None:
        raise ApiError(404, "not_found", "学科不存在")
    stages = list(
        db.scalars(select(Stage).where(Stage.subject_id == subject_id, Stage.active.is_(True)).order_by(Stage.ord))
    )
    points = list(
        db.scalars(select(Point).where(Point.subject_id == subject_id, Point.active.is_(True)).order_by(Point.ord))
    )
    ids = [p.id for p in points]
    prereqs: dict[str, list[dict]] = {pid: [] for pid in ids}
    for pp in db.scalars(select(PointPrereq).where(PointPrereq.point_id.in_(ids or [""]))):
        prereqs[pp.point_id].append({"id": pp.prereq_id, "kind": pp.kind})
    stats = point_stats(db, ids)
    out_stages = []
    for st in stages:
        status = queue_svc.stage_status(db, st)
        out_stages.append(
            {
                **stage_out(st),
                "passed": status["passed"],
                "weight2_learned": status["weight2_learned"],
                "exit_evidence": status["exit_evidence"],
                "points": [
                    {**point_out(p), "prereqs": prereqs[p.id], "stats": stats[p.id]}
                    for p in points
                    if p.stage_id == st.id
                ],
            }
        )
    return {
        "subject": {
            "id": s.id,
            "prefix": s.prefix,
            "title": s.title,
            "goal": s.goal,
            "description": s.description,
            "map_version": s.map_version,
        },
        "stages": out_stages,
    }


def card_row(c: Card, cs: CardState | None) -> dict:
    return {
        "card_id": c.id,
        "deck_id": c.deck_id,
        "card_type": c.card_type,
        "front": c.front,
        "back": c.back,
        "payload": c.payload,
        "tags": c.tags,
        "created_by": c.created_by,
        "active": c.active,
        "state": cs.state if cs else 0,
        "due": iso_local(cs.due) if cs else None,
        "stability": cs.stability if cs else None,
        "reps": cs.reps if cs else 0,
        "lapses": cs.lapses if cs else 0,
    }


@router.get("/points/{point_id}")
def get_point(point_id: str, p: AnyP, db: Db, include_inactive_cards: bool = False) -> dict:
    pt = db.get(Point, point_id)
    if pt is None:
        raise ApiError(404, "not_found", "知识点不存在")
    prereqs = [
        {"id": pp.prereq_id, "kind": pp.kind}
        for pp in db.scalars(select(PointPrereq).where(PointPrereq.point_id == point_id))
    ]
    dependents = [
        {"id": pp.point_id, "kind": pp.kind}
        for pp in db.scalars(select(PointPrereq).where(PointPrereq.prereq_id == point_id))
    ]
    cq = select(Card, CardState).outerjoin(CardState, CardState.card_id == Card.id).where(Card.point_id == point_id)
    if not include_inactive_cards:
        cq = cq.where(Card.active.is_(True))
    if p.name == "web":
        cq = cq.where(Card.card_type != "handson")
    cards = [card_row(c, cs) for c, cs in db.execute(cq.order_by(Card.id)).all()]
    evidence = [
        {
            "id": e.id,
            "type": e.type,
            "score": float(e.score) if e.score is not None else None,
            "max": float(e.max_score) if e.max_score is not None else None,
            "passed": bool(e.passed),
            "rubric": e.rubric,
            "notes": e.notes,
            "session_id": e.session_id,
            "card_id": e.card_id,
            "reviewer": e.reviewer,
            "observed_at": iso_local(e.observed_at),
        }
        for e in db.scalars(select(Evidence).where(Evidence.point_id == point_id).order_by(Evidence.observed_at.desc()))
    ]
    blockers = [
        {
            "id": b.id,
            "title": b.title,
            "detail": b.detail,
            "status": b.status,
            "resolution": b.resolution,
            "created_at": iso_local(b.created_at),
        }
        for b in db.scalars(select(Blocker).where(Blocker.point_id == point_id).order_by(Blocker.id.desc()))
    ]
    return {
        "point": point_out(pt),
        "prereqs": prereqs,
        "dependents": dependents,
        "stats": point_stats(db, [point_id])[point_id],
        "cards": cards,
        "evidence": evidence,
        "blockers": blockers,
        "sources": pt.sources or [],
    }


# ───────────────────────── 卡组 / 卡片 ─────────────────────────


class CardIn(Strict):
    card_type: CardType
    front: str = Field(min_length=1, max_length=4000)
    back: str | None = Field(default=None, max_length=100_000)
    payload: dict[str, Any] | None = None
    tags: list[str] | None = None


class DeckCardIn(CardIn):
    point_id: str | None = None


class PointCardsBody(Strict):
    cards: list[CardIn] = Field(min_length=1, max_length=100)


class DeckCardsBody(Strict):
    cards: list[DeckCardIn] = Field(min_length=1, max_length=100)


@router.post("/points/{point_id}/cards")
def add_point_cards(point_id: str, body: PointCardsBody, p: Axue, db: WriteDb) -> dict:
    pt = db.get(Point, point_id)
    if pt is None:
        raise ApiError(404, "not_found", "知识点不存在")
    deck = card_svc.deck_for_point(db, pt)
    out = card_svc.add_cards(db, deck, [c.model_dump() for c in body.cards], created_by=p.name, point_id=point_id)
    return mark_dry(db, out)


class CardPatch(Strict):
    front: str | None = Field(default=None, min_length=1, max_length=4000)
    back: str | None = Field(default=None, max_length=100_000)
    payload: dict[str, Any] | None = None
    card_type: CardType | None = None
    active: bool | None = None


@router.patch("/cards/{card_id}")
def patch_card(card_id: int, body: CardPatch, _p: Axue, db: WriteDb) -> dict:
    out = card_svc.patch_card(db, card_id, body.model_dump(exclude_unset=True))
    return mark_dry(db, out)


class Caps(Strict):
    review_cap: int = Field(default=60, ge=0, le=1000)
    new_cap: int = Field(default=8, ge=0, le=500)
    new_cap_deep: int | None = Field(default=None, ge=0, le=500)


class DeckIn(Strict):
    kind: str = Field(pattern=r"^[a-z][a-z0-9_]{1,15}$")
    name: str = Field(min_length=1, max_length=128)
    subject_id: str | None = None
    source: Literal["builtin", "ai", "agent"] | None = None
    caps: Caps | None = None
    meta: dict[str, Any] | None = None


@router.get("/decks")
def list_decks(_p: AnyP, db: Db, subject: str | None = None) -> list[dict]:
    q = select(Deck)
    if subject:
        q = q.where(Deck.subject_id == subject)
    return [card_svc.deck_out(d) for d in db.scalars(q.order_by(Deck.id))]


@router.post("/decks")
def create_deck(body: DeckIn, _p: Axue, db: WriteDb) -> dict:
    data = body.model_dump()
    if body.caps is not None:
        data["caps"] = body.caps.model_dump()
    deck, created = card_svc.create_deck(db, data)
    return mark_dry(db, {**deck, "created": created})


@router.post("/decks/{deck_id}/cards")
def add_deck_cards(deck_id: int, body: DeckCardsBody, p: Axue, db: WriteDb) -> dict:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise ApiError(404, "not_found", "卡组不存在")
    out = card_svc.add_cards(db, deck, [c.model_dump() for c in body.cards], created_by=p.name)
    return mark_dry(db, out)


# ───────────────────────── 复习 ─────────────────────────


@router.get("/review/due")
def review_due(
    p: AnyP,
    db: Db,
    subject: str | None = None,
    deck: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    return queue_svc.build_queue(db, subject=subject, deck_id=deck, limit=limit, principal=p.name)


class ReviewIn(Strict):
    kind: Literal["card", "en_word"] = "card"
    card_id: int | None = None
    word: str | None = Field(default=None, min_length=1, max_length=64)
    dict_id: str | None = Field(default=None, max_length=64)
    rating: int = Field(ge=1, le=4)
    errors: int | None = Field(default=None, ge=0, le=1000)
    answer_text: str | None = Field(default=None, max_length=20_000)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    reviewed_at: datetime | None = None
    client_review_id: str | None = Field(default=None, min_length=1, max_length=64)
    payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _shape(self) -> "ReviewIn":
        if self.kind == "en_word" and not (self.word and self.word.strip()):
            raise ValueError("en_word 复习必须带 word")
        if self.kind == "card" and self.card_id is None:
            raise ValueError("必须带 card_id（或 kind=en_word + word）")
        return self


class ReviewBatch(Strict):
    items: list[ReviewIn] = Field(min_length=1, max_length=200)


@router.post("/review")
def post_review(body: ReviewIn, p: AnyP, db: WriteDb) -> dict:
    out = review_svc.apply_one(db, body.model_dump(), p.name)
    db.commit()
    return mark_dry(db, out)


@router.post("/review/batch")
def post_review_batch(body: ReviewBatch, p: AnyP, db: WriteDb) -> dict:
    out = review_svc.apply_batch(db, [i.model_dump() for i in body.items], p.name)
    return mark_dry(db, out)


# ───────────────────────── 进度 / 课次 / 证据 / 推荐 ─────────────────────────


@router.get("/progress")
def get_progress(_p: AnyP, db: Db, subject: str | None = None, stage: str | None = None) -> dict:
    return queue_svc.progress(db, subject=subject, stage=stage)


class SessionIn(Strict):
    date: date
    minutes: int | None = Field(default=None, ge=0, le=1440)
    subject_id: str | None = None
    point_ids: list[str] = Field(default_factory=list, max_length=50)
    lesson_ref: str | None = Field(default=None, max_length=64)
    cues: list[str] = Field(default_factory=list, max_length=50)
    summary: str = Field(min_length=1, max_length=20_000)
    stuck: str | None = Field(default=None, max_length=20_000)
    notes: str | None = Field(default=None, max_length=50_000)


@router.post("/sessions")
def post_session(body: SessionIn, _p: Axue, db: WriteDb) -> dict:
    out = tutor_svc.create_session(db, body.model_dump())
    return mark_dry(db, out)


class EvidenceIn(Strict):
    point_id: str | None = None
    stage_id: str | None = None
    session_id: int | None = None
    type: Literal["selftest", "feynman", "express", "handson"]
    score: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, gt=0)
    passed: bool | None = None
    rubric: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=20_000)
    observed_at: datetime | None = None
    card_id: int | None = None
    rating: int | None = Field(default=None, ge=1, le=4)


@router.post("/evidence")
def post_evidence(body: EvidenceIn, _p: Axue, db: WriteDb) -> dict:
    out = tutor_svc.create_evidence(db, body.model_dump())
    return mark_dry(db, out)


@router.get("/next")
def get_next(
    _p: AnyP,
    db: Db,
    subject: str | None = None,
    limit: Annotated[int, Query(ge=0, le=100)] = 5,
) -> dict:
    return queue_svc.next_points(db, subject=subject, limit=limit)
