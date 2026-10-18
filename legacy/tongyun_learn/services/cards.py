"""建卡 / 改卡 / 建卡组（定稿 §2 POST /points/{id}/cards、PATCH /cards/{id}、POST /decks(/cards)）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from tongyun_learn.errors import ApiError
from tongyun_learn.models import Card, Deck, Point, Subject
from tongyun_learn.services.cardkeys import front_key
from tongyun_learn.services.importer import deck_name
from tongyun_learn.services.state import is_vocab, recompute_points
from tongyun_learn.timeutil import utcnow


def deck_for_point(db: Session, p: Point) -> Deck:
    """知识点的卡进本学科 qa 卡组；词汇点（tags 含 en_word）进 en_word 卡组，和 TypeWords 的单词卡按单词去重。"""
    kind = "en_word" if is_vocab(p) else "qa"
    d = db.scalar(
        select(Deck).where(
            Deck.subject_id == p.subject_id, Deck.kind == kind, Deck.name == deck_name(p.subject_id, kind)
        )
    )
    if d is None:
        raise ApiError(409, "deck_missing", f"学科 {p.subject_id} 还没有 {kind} 卡组，请先导入知识地图")
    return d


def add_cards(db: Session, deck: Deck, cards: list[dict], created_by: str, point_id: str | None = None) -> dict:
    now = utcnow()
    created, skipped = [], []
    touched: set[str] = set()
    seen: set[str] = set()
    for c in cards:
        pid = c.get("point_id") or point_id
        if pid is not None:
            p = db.get(Point, pid)
            if p is None:
                raise ApiError(404, "not_found", f"知识点 {pid} 不存在")
        fk = front_key(c["front"])
        if fk in seen or db.scalar(select(Card.id).where(Card.deck_id == deck.id, Card.front_key == fk)):
            skipped.append(c["front"])
            continue
        seen.add(fk)
        card = Card(
            deck_id=deck.id,
            point_id=pid,
            card_type=c["card_type"],
            front=c["front"],
            front_key=fk,
            back=c.get("back"),
            payload=c.get("payload"),
            tags=c.get("tags"),
            created_by=created_by,
            active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(card)
        db.flush()
        created.append({"card_id": card.id, "front": card.front})
        if pid:
            touched.add(pid)
    changes = recompute_points(db, sorted(touched), cause="card", now=now) if touched else []
    db.commit()
    return {"created": created, "skipped": skipped, "point_changes": changes}


def patch_card(db: Session, card_id: int, patch: dict) -> dict:
    now = utcnow()
    card = db.get(Card, card_id)
    if card is None:
        raise ApiError(404, "not_found", "卡片不存在")
    changed = False
    if "front" in patch and patch["front"] is not None and patch["front"] != card.front:
        fk = front_key(patch["front"])
        clash = db.scalar(select(Card.id).where(Card.deck_id == card.deck_id, Card.front_key == fk, Card.id != card.id))
        if clash:
            raise ApiError(409, "duplicate_front", "同卡组已有同名卡片", details={"card_id": clash})
        card.front, card.front_key = patch["front"], fk
        changed = True
    for k in ("back", "card_type", "active"):
        if k in patch and patch[k] is not None and getattr(card, k) != patch[k]:
            setattr(card, k, patch[k])
            changed = True
    if "payload" in patch:
        new_payload = dict(patch["payload"]) if isinstance(patch["payload"], dict) else patch["payload"]
        old_src = (card.payload or {}).get("example_src") if isinstance(card.payload, dict) else None
        if old_src:  # 保留示例卡来源标记，重导入时据此认出“阿学改过”的卡
            new_payload = dict(new_payload or {})
            new_payload["example_src"] = old_src
        if new_payload != card.payload:
            card.payload = new_payload
            changed = True
    changes: list[dict] = []
    if changed:
        if card.created_by == "example":
            card.created_by = "axue"
        card.updated_at = now
        db.flush()
        if card.point_id:
            changes = recompute_points(db, [card.point_id], cause="card", cause_ref=str(card.id), now=now)
    db.commit()
    return {
        "card_id": card.id,
        "deck_id": card.deck_id,
        "point_id": card.point_id,
        "card_type": card.card_type,
        "front": card.front,
        "back": card.back,
        "payload": card.payload,
        "active": card.active,
        "created_by": card.created_by,
        "point_changes": changes,
    }


def deck_out(d: Deck) -> dict:
    return {
        "id": d.id,
        "subject_id": d.subject_id,
        "kind": d.kind,
        "name": d.name,
        "source": d.source,
        "review_cap": d.review_cap,
        "new_cap": d.new_cap,
        "new_cap_deep": d.new_cap_deep,
        "meta": d.meta,
    }


def create_deck(db: Session, body: dict) -> tuple[dict, bool]:
    if body.get("subject_id") and db.get(Subject, body["subject_id"]) is None:
        raise ApiError(404, "not_found", "学科不存在")
    existing = db.scalar(
        select(Deck).where(
            Deck.subject_id.is_(None) if not body.get("subject_id") else Deck.subject_id == body["subject_id"],
            Deck.kind == body["kind"],
            Deck.name == body["name"],
        )
    )
    if existing is not None:
        return deck_out(existing), False
    caps = body.get("caps") or {}
    d = Deck(
        subject_id=body.get("subject_id"),
        kind=body["kind"],
        name=body["name"],
        source=body.get("source") or "agent",
        review_cap=caps.get("review_cap", 60),
        new_cap=caps.get("new_cap", 8),
        new_cap_deep=caps.get("new_cap_deep"),
        meta=body.get("meta"),
        created_at=utcnow(),
    )
    db.add(d)
    db.commit()
    return deck_out(d), True
