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
from tongyun_learn.models import Deck
from tongyun_learn.services import cards as card_svc

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


class GenerateDeckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str
    n: int = Field(default=20, ge=1, le=50)
    deck_name: str | None = Field(default=None, max_length=64)

    @field_validator("scenario")
    @classmethod
    def validate_scenario(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 200):
            raise ValueError("scenario 长度必须在 2 到 200 之间")
        return v

    @field_validator("deck_name")
    @classmethod
    def validate_deck_name(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if len(v) > 64:
                raise ValueError("deck_name 长度不能超过 64")
        return v


@router.post("/generate-deck")
async def generate_deck_endpoint(
    body: GenerateDeckRequest,
    principal: Annotated[Principal, Depends(get_principal)],
    db: Annotated[Session, Depends(get_db)],
    kie_client: Annotated[KieClient, Depends(get_kie_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    # 1. 调用 AI 生成词单（复用 explain 的缓存、日上限、KIE 与校验重试机制）
    ai_res = await explain(
        db=db,
        principal=principal,
        kind="word_deck",
        input_data={"scenario": body.scenario, "n": body.n},
        client=kie_client,
        settings=settings,
    )

    words_data = ai_res.get("content", {}).get("words", [])

    # 2. 确定卡组名称：缺省用 "AI·"+scenario 截断至 64 字符
    resolved_deck_name = body.deck_name or f"AI·{body.scenario}"[:64]

    # 3. 建/取卡组：kind='en_word', source='ai'
    # Deck 的 subject_id 选 None：create_deck 支持 subject_id 为 None（独立卡组），
    # 且不依赖特定学科预先存在，最符合场景词书独立建卡组的预期。
    # 鉴权取舍说明：鉴权采用 get_principal（与 quiz 一致，任意有效 token 均可调用，适配 Web 客户端直接生成卡组）；
    # 服务层 create_deck 与 add_cards 为纯业务函数不强制要求 axue 权限，创建卡片记录 created_by 标记为 'ai'。
    deck_dict, _ = card_svc.create_deck(
        db,
        {
            "kind": "en_word",
            "name": resolved_deck_name,
            "subject_id": None,
            "source": "ai",
            "meta": {"scenario": body.scenario},
        },
    )

    deck_obj = db.get(Deck, deck_dict["id"])
    if deck_obj is None:
        raise ApiError(500, "internal", "卡组创建或查询失败")

    # 4. 组装卡片列表并入库（按 front 去重）
    cards_to_add = [
        {
            "card_type": "memory",
            "front": item["word"],
            "back": item["cn"],
            "payload": {
                "phonetic": item.get("phonetic"),
                "example": item.get("example"),
                "example_cn": item.get("example_cn"),
                "scenario": body.scenario,
            },
        }
        for item in words_data
    ]

    add_res = card_svc.add_cards(
        db=db,
        deck=deck_obj,
        cards=cards_to_add,
        created_by="ai",
    )

    return {
        "deck": deck_dict,
        "added": len(add_res.get("created", [])),
        "skipped": len(add_res.get("skipped", [])),
        "cached": ai_res.get("cached", False),
        "model": ai_res.get("model", ""),
        "words": words_data,
    }


