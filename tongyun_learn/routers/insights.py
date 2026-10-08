"""P3b 读接口：/weak、/recall、/summary/week，以及人工改状态 PATCH /points/{id}/state。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from tongyun_learn.auth import Principal, get_principal, require
from tongyun_learn.db import get_db
from tongyun_learn.routers.deps import WriteDb, mark_dry
from tongyun_learn.services import insights as svc

router = APIRouter(tags=["insights"])

Db = Annotated[Session, Depends(get_db)]
AnyP = Annotated[Principal, Depends(get_principal)]
Axue = Annotated[Principal, Depends(require("axue"))]


class StateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["locked", "available", "learning", "learned", "mastered", "rusty"] | None
    reason: str = Field(min_length=1, max_length=500)


@router.get("/weak")
def get_weak(_p: AnyP, db: Db, subject: str | None = None) -> list[dict]:
    return svc.weak_points(db, subject=subject)


@router.get("/recall")
def get_recall(_p: AnyP, db: Db, days: Annotated[str, Query(max_length=64)] = "1,3,7") -> list[dict]:
    return svc.recall(db, days=days)


@router.get("/summary/week")
def get_week(_p: AnyP, db: Db, ago: Annotated[int, Query(ge=0, le=520)] = 0) -> dict:
    return svc.week_summary(db, ago=ago)


@router.patch("/points/{point_id}/state")
def patch_state(point_id: str, body: StateIn, _p: Axue, db: WriteDb) -> dict:
    out = svc.set_override(db, point_id, body.state, body.reason)
    return mark_dry(db, out)
