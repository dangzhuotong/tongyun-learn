"""课次、证据与复习的作废、恢复及查询列表路由（定稿 P3b）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from tongyun_learn.auth import Principal, require
from tongyun_learn.db import get_db
from tongyun_learn.errors import ApiError
from tongyun_learn.routers.deps import WriteDb, mark_dry
from tongyun_learn.services import voiding as voiding_svc

router = APIRouter(tags=["voiding"])

Axue = Annotated[Principal, Depends(require("axue"))]
AnyP = Annotated[Principal, Depends(require("web", "axue"))]
Db = Annotated[Session, Depends(get_db)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VoidIn(Strict):
    reason: str = Field(..., min_length=1, max_length=500)


class RestoreIn(Strict):
    reason: str | None = Field(default=None, min_length=1, max_length=500)


@router.post("/sessions/{session_id}/void")
def void_session(session_id: int, body: VoidIn, _p: Axue, db: WriteDb) -> dict:
    out = voiding_svc.void_session(db, session_id, body.reason)
    return mark_dry(db, out)


@router.post("/sessions/{session_id}/restore")
def restore_session(session_id: int, _p: Axue, db: WriteDb, body: RestoreIn | None = None) -> dict:
    out = voiding_svc.restore_session(db, session_id, body.reason if body else None)
    return mark_dry(db, out)


@router.post("/evidence/{evidence_id}/void")
def void_evidence(evidence_id: int, body: VoidIn, _p: Axue, db: WriteDb) -> dict:
    out = voiding_svc.void_evidence(db, evidence_id, body.reason)
    return mark_dry(db, out)


@router.post("/evidence/{evidence_id}/restore")
def restore_evidence(evidence_id: int, _p: Axue, db: WriteDb, body: RestoreIn | None = None) -> dict:
    out = voiding_svc.restore_evidence(db, evidence_id, body.reason if body else None)
    return mark_dry(db, out)


@router.get("/sessions")
def list_sessions(
    _p: AnyP,
    db: Db,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    point: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    include_voided: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    return voiding_svc.list_sessions(
        db=db,
        date_from=date_from,
        date_to=date_to,
        point=point,
        subject=subject,
        include_voided=include_voided,
        limit=limit,
    )


@router.post("/reviews/{review_id}/void")
def void_review(review_id: int, body: VoidIn, _p: Axue, db: WriteDb) -> dict:
    out = voiding_svc.void_review(db, review_id, body.reason)
    return mark_dry(db, out)


@router.post("/reviews/{review_id}/restore")
def restore_review(review_id: int, _p: Axue, db: WriteDb, body: RestoreIn | None = None) -> dict:
    out = voiding_svc.restore_review(db, review_id, body.reason if body else None)
    return mark_dry(db, out)


@router.get("/reviews")
def list_reviews(
    _p: AnyP,
    db: Db,
    card: int | str | None = Query(default=None),
    point: str | None = Query(default=None),
    include_voided: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[dict]:
    card_id: int | None = None
    if card is not None and str(card).strip():
        try:
            card_id = int(str(card).strip())
        except ValueError as e:
            raise ApiError(422, "validation_error", "card 必须是整数") from e
    return voiding_svc.list_reviews(
        db=db,
        card=card_id,
        point=point,
        limit=limit,
        include_voided=include_voided,
    )
