import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from tongyun_learn.ai.kie import KieClient
from tongyun_learn.ai.service import explain, get_kie_client
from tongyun_learn.auth import Principal, get_principal
from tongyun_learn.config import Settings, get_settings
from tongyun_learn.db import get_db
from tongyun_learn.errors import ApiError

router = APIRouter(prefix="/ai", tags=["ai"])


class WordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    word: str
    context: str | None = Field(default=None, max_length=500)

    @field_validator("word")
    @classmethod
    def validate_word(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 64):
            raise ValueError("word 长度必须在 1 到 64 之间")
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("word 必须包含英文字母")
        return v


class SentenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence: str
    context: str | None = Field(default=None, max_length=2000)

    @field_validator("sentence")
    @classmethod
    def validate_sentence(cls, v: str) -> str:
        v = " ".join(v.split())
        if not (3 <= len(v) <= 1000):
            raise ValueError("sentence 长度必须在 3 到 1000 之间")
        return v


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["word_mnemonic", "sentence_grammar"]
    input: dict[str, Any]


@router.post("/explain")
async def explain_endpoint(
    body: ExplainRequest,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
    kie_client: Annotated[KieClient, Depends(get_kie_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    if body.kind == "word_mnemonic":
        try:
            validated_input = WordInput.model_validate(body.input).model_dump(exclude_unset=False)
        except ValidationError as exc:
            raise ApiError(
                422,
                "validation_error",
                "请求参数不合法",
                details=jsonable_encoder(exc.errors()),
            ) from exc
    elif body.kind == "sentence_grammar":
        try:
            validated_input = SentenceInput.model_validate(body.input).model_dump(exclude_unset=False)
        except ValidationError as exc:
            raise ApiError(
                422,
                "validation_error",
                "请求参数不合法",
                details=jsonable_encoder(exc.errors()),
            ) from exc
    else:
        raise ApiError(422, "validation_error", "未知的 kind 类型")

    return await explain(
        db=db,
        principal=principal,
        kind=body.kind,
        input_data=validated_input,
        client=kie_client,
        settings=settings,
    )


class QuizWordItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    word: str
    cn: str | None = Field(default=None, max_length=100)

    @field_validator("word")
    @classmethod
    def validate_word(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 64):
            raise ValueError("word 长度必须在 1 到 64 之间")
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("word 必须包含英文字母")
        return v


class QuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    words: list[QuizWordItem] = Field(min_length=1, max_length=20)


@router.post("/quiz")
async def quiz_endpoint(
    body: QuizRequest,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
    kie_client: Annotated[KieClient, Depends(get_kie_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    seen: set[str] = set()
    unique_words: list[dict[str, Any]] = []
    for item in body.words:
        key = item.word.lower()
        if key not in seen:
            seen.add(key)
            unique_words.append(item.model_dump())

    return await explain(
        db=db,
        principal=principal,
        kind="word_quiz",
        input_data={"words": unique_words},
        client=kie_client,
        settings=settings,
    )

