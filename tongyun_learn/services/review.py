"""复习写入（定稿 §2 POST /review(/batch) + §5 en_word 契约）。"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from tongyun_learn.errors import ApiError
from tongyun_learn.models import Card, CardState, Deck, Point, ReviewLog
from tongyun_learn.services import srs
from tongyun_learn.services.cardkeys import front_key
from tongyun_learn.services.importer import deck_name
from tongyun_learn.services.state import recompute_points
from tongyun_learn.timeutil import iso_local, to_utc_naive, utcnow

FUTURE_SLACK = timedelta(minutes=10)
EN_SUBJECT = "tech-english"


def card_state_out(cs: CardState | None) -> dict | None:
    if cs is None:
        return None
    return {
        "state": cs.state,
        "due": iso_local(cs.due),
        "stability": cs.stability,
        "difficulty": cs.difficulty,
        "reps": cs.reps,
        "lapses": cs.lapses,
    }


def _reviewed_at(raw: datetime | None, now: datetime) -> datetime:
    if raw is None:
        return now
    at = to_utc_naive(raw)
    if at > now + FUTURE_SLACK:
        raise ApiError(422, "validation_error", "reviewed_at 不能晚于当前时间")
    return at


def resolve_en_word_card(db: Session, item: dict, principal: str) -> Card:
    """en_word：在 tech-english 的 en_word 卡组里按 sha256(小写单词) upsert 记忆卡。"""
    deck = db.scalar(
        select(Deck).where(
            Deck.subject_id == EN_SUBJECT, Deck.kind == "en_word", Deck.name == deck_name(EN_SUBJECT, "en_word")
        )
    )
    if deck is None:
        raise ApiError(409, "deck_missing", "还没有 en_word 卡组，请先导入 tech-english 知识地图")
    word = item["word"].strip()
    fk = front_key(word)
    card = db.scalar(select(Card).where(Card.deck_id == deck.id, Card.front_key == fk))
    if card is not None:
        if card.payload is None and item.get("payload") is not None:
            card.payload = item["payload"]
        return card
    meta = deck.meta or {}
    pid = (meta.get("dict_point_map") or {}).get(item.get("dict_id") or "") or meta.get("default_point")
    if pid is None or db.get(Point, pid) is None:
        pid = None
    card = Card(
        deck_id=deck.id,
        point_id=pid,
        card_type="memory",
        front=word.lower(),
        front_key=fk,
        back=None,
        payload=item.get("payload"),
        tags=[f"dict:{item['dict_id']}"] if item.get("dict_id") else None,
        created_by="web" if principal == "web" else "axue",
        active=True,
    )
    db.add(card)
    db.flush()
    return card


def apply_one(db: Session, item: dict, principal: str, now: datetime | None = None) -> dict:
    """处理一条复习（不 commit）。item 已经过 pydantic 校验并转成 dict。"""
    now = now or utcnow()
    crid = item.get("client_review_id")
    if crid:
        dup = db.scalar(select(ReviewLog).where(ReviewLog.client_review_id == crid))
        if dup is not None:
            res = {
                "card_id": dup.card_id,
                "card_state": card_state_out(db.get(CardState, dup.card_id)),
                "applied": False,
                "duplicate": True,
                "point_changes": [],
            }
            if dup.voided_at is not None:
                res["voided"] = True
            return res
    at = _reviewed_at(item.get("reviewed_at"), now)
    if item.get("kind") == "en_word":
        card = resolve_en_word_card(db, item, principal)
    else:
        card = db.get(Card, item["card_id"])
        if card is None:
            raise ApiError(404, "not_found", "卡片不存在")
        if principal == "web" and card.card_type == "handson":
            raise ApiError(403, "forbidden", "动手卡只能由阿学验收")
    if not card.active:
        raise ApiError(409, "card_inactive", "卡片已停用")
    cs = db.get(CardState, card.id)
    applied = cs is None or cs.last_review is None or at >= cs.last_review
    if applied:
        is_new = cs is None
        cs = srs.apply_review(cs, card.id, item["rating"], at)
        if is_new:
            db.add(cs)
    log = ReviewLog(
        card_id=card.id,
        point_id=card.point_id,
        rating=item["rating"],
        reviewer="axue" if principal == "axue" else "self",
        client=item.get("client") or ("typewords" if item.get("kind") == "en_word" else principal),
        answer_text=item.get("answer_text"),
        duration_ms=item.get("duration_ms"),
        errors=item.get("errors"),
        reviewed_at=at,
        applied=applied,
        stability_after=cs.stability if (applied and cs) else None,
        due_after=cs.due if (applied and cs) else None,
        client_review_id=crid,
        created_at=now,
    )
    db.add(log)
    db.flush()
    changes: list[dict] = []
    if applied and card.point_id:
        changes = recompute_points(db, [card.point_id], cause="review", cause_ref=str(log.id), now=now)
    return {
        "card_id": card.id,
        "card_state": card_state_out(cs),
        "applied": applied,
        "duplicate": False,
        "point_changes": changes,
    }


def apply_batch(db: Session, items: list[dict], principal: str) -> dict:
    now = utcnow()
    order = sorted(
        range(len(items)),
        key=lambda i: to_utc_naive(items[i]["reviewed_at"]) if items[i].get("reviewed_at") else now,
    )
    results: list[dict | None] = [None] * len(items)
    duplicates = 0
    for i in order:
        try:
            # apply_one 的 ApiError 都在写库之前抛出，所以单条失败不影响同批其他条目
            r = apply_one(db, items[i], principal, now)
        except ApiError as e:
            r = {"error": {"code": e.code, "message": e.message}}
        if r.get("duplicate"):
            duplicates += 1
        r["index"] = i
        results[i] = r
    db.commit()
    return {"results": results, "duplicates": duplicates}
