"""云芽英语：今日队列、手敲、教练。web 和 axue 令牌都能用。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from tongyun_learn.auth import Principal, get_principal
from tongyun_learn.config import Settings, get_settings
from tongyun_learn.db import get_db
from tongyun_learn.services import en_coach

router = APIRouter(tags=["yun-ya"])

Db = Annotated[Session, Depends(get_db)]
AnyP = Annotated[Principal, Depends(get_principal)]
Cfg = Annotated[Settings, Depends(get_settings)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TypeBody(Strict):
    card_id: int = Field(gt=0)
    phase: Literal["A", "B"]
    typed: str = Field(min_length=1, max_length=2000)
    duration_ms: int | None = Field(default=None, ge=0, le=600_000)
    sentence_index: int | None = Field(default=None, ge=0, le=20)
    attempts: int = Field(default=1, ge=1, le=5)
    client_event_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]{1,64}$")


class CoachBody(Strict):
    feedback: Literal["easier", "harder"] | None = None


@router.get("/today")
def today(p: AnyP, db: Db) -> dict:
    """今日队列。没有计划时用规则生成并写入 coach_plans。"""
    return en_coach.today_payload(db, p.name)


@router.post("/type")
def submit_type(body: TypeBody, p: AnyP, db: Db, settings: Cfg) -> dict:
    """提交一次敲词（A）或敲句（B），写入 type_events 并更新 FSRS。"""
    return en_coach.submit_type(
        db,
        p.name,
        card_id=body.card_id,
        phase=body.phase,
        typed=body.typed,
        duration_ms=body.duration_ms,
        sentence_index=body.sentence_index,
        attempts=body.attempts,
        client_event_id=body.client_event_id,
        settings=settings,
    )


@router.get("/coach")
def get_coach(p: AnyP, db: Db) -> dict:
    """薄弱点（实时）和最近一份已入库的教练计划。"""
    return en_coach.coach_payload(db, p.name)


@router.post("/coach")
def post_coach(p: AnyP, db: Db, settings: Cfg, body: CoachBody | None = None) -> dict:
    """生成一份教练计划并入库。有 DEEPSEEK_API_KEY 时用模型，否则规则降级。"""
    feedback = body.feedback if body else None
    en_coach.create_plan(db, p.name, feedback=feedback, settings=settings)
    return en_coach.coach_payload(db, p.name)
