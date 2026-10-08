"""P3b 卡点接口：POST /blockers、PATCH /blockers/{id}、GET /blockers。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from tongyun_learn.auth import Principal, get_principal, require
from tongyun_learn.db import get_db
from tongyun_learn.errors import ApiError
from tongyun_learn.routers.deps import WriteDb, mark_dry
from tongyun_learn.services import blockers as blocker_svc

router = APIRouter(tags=["blockers"])

Db = Annotated[Session, Depends(get_db)]
AnyP = Annotated[Principal, Depends(get_principal)]
Axue = Annotated[Principal, Depends(require("axue"))]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateBlockerBody(Strict):
    point_id: str | None = None
    session_id: int | None = None
    title: str = Field(..., max_length=255)
    detail: str | None = Field(default=None, max_length=20000)


class UpdateBlockerBody(Strict):
    status: Literal["open", "resolved", "dropped"] | None = None
    resolution: str | None = Field(default=None, max_length=20000)


@router.post("/blockers")
def create_blocker(body: CreateBlockerBody, _p: Axue, db: WriteDb) -> dict:
    out = blocker_svc.create_blocker(db, body.model_dump())
    return mark_dry(db, out)


@router.patch("/blockers/{blocker_id}")
def update_blocker(blocker_id: int, body: UpdateBlockerBody, _p: Axue, db: WriteDb) -> dict:
    out = blocker_svc.update_blocker(db, blocker_id, body.model_dump(exclude_unset=True))
    return mark_dry(db, out)


@router.get("/blockers")
def list_blockers(
    _p: AnyP,
    db: Db,
    status: str | None = Query(default=None),
    point: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict]:
    filter_status = status if (status is not None and status != "") else None
    if filter_status and filter_status not in ("open", "resolved", "dropped"):
        raise ApiError(422, "invalid_status", "状态非法")
    filter_point = point if (point is not None and point != "") else None
    return blocker_svc.list_blockers(db, status=filter_status, point=filter_point, limit=limit)
