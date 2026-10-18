"""薄弱点、今日队列、教练计划。有 DeepSeek 密钥就用模型，否则规则降级，两种结果都入库。"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import date as date_cls
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tongyun_learn.ai.deepseek import DeepSeekError, complete_chat
from tongyun_learn.ai.kie import parse_json_text
from tongyun_learn.config import Settings, get_settings
from tongyun_learn.data.en_curriculum import DEFAULT_TARGET, EASIER_TARGET
from tongyun_learn.db import utcnow
from tongyun_learn.errors import ApiError
from tongyun_learn.limits import bump_ai_calls, check_ai_cap
from tongyun_learn.models import AiCache, CardState, CoachPlan, ReviewLog, TypeEvent
from tongyun_learn.services import review as review_svc
from tongyun_learn.services.en_curriculum import (
    expected_text,
    find_card_unit,
    load_context,
    study_streak_days,
    top_error_shape,
)
from tongyun_learn.services.en_grade import grade_attempt, rating_for
from tongyun_learn.services.en_progress import (
    apply_unlocks,
    build_queue,
    cap_items,
    current_dev_unit,
    life_slot_cap,
    life_unlocked,
    make_item,
    nail_items,
    recent_window_start,
)
from tongyun_learn.timeutil import day_bounds_utc, iso_local

logger = logging.getLogger("tongyun_learn.en_coach")

PROMPT_VER = "c1"
CACHE_KIND = "coach_plan"


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def unit_public(unit: Any) -> dict[str, Any]:
    return {
        "id": unit.unit_id,
        "ord": unit.ord,
        "title": unit.title,
        "track": unit.track,
        "kind": unit.kind,
        "unlocked": unit.unlocked,
        "graduated": unit.graduated,
        "progress": {
            "total": unit.total,
            "in_review": unit.in_review,
            "review_ratio": _round(unit.review_ratio),
            "recent_correct": unit.recent_correct,
            "recent_total": unit.recent_total,
            "recent_accuracy": _round(unit.recent_accuracy),
            "recent_days": int(unit.rule["recent_days"]),
            "nails": len(unit.nail_card_ids),
            "rule": unit.rule,
        },
    }


def weak_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    apply_unlocks(ctx["units"])
    snaps = {s.card_id: s for s in ctx["snaps"]}
    nails = []
    for unit in ctx["units"]:
        if unit.kind != "dev" or not unit.unlocked:
            continue
        for cid in unit.nail_card_ids:
            snap = snaps.get(cid)
            if snap is None:
                continue
            nails.append(
                {
                    "card_id": cid,
                    "lemma": snap.lemma,
                    "cn": snap.cn,
                    "streak": snap.streak_wrong,
                    "top_error": top_error_shape(ctx["events"].get(cid, [])),
                    "unit_ord": unit.ord,
                }
            )
    nails.sort(key=lambda n: (-n["streak"], n["unit_ord"], n["lemma"]))

    local_day = date_cls.fromisoformat(ctx["today"])
    start, _end = day_bounds_utc(local_day)
    week_start = recent_window_start(start, 7)
    wrongs: dict[int, int] = defaultdict(int)
    recent_correct = 0
    recent_total = 0
    dev_ids = {u.unit_id for u in ctx["units"] if u.kind == "dev" and u.unlocked}
    window_start = recent_window_start(start, 3)
    for cid, evs in ctx["events"].items():
        snap = snaps.get(cid)
        if snap is None or snap.unit_id not in dev_ids:
            continue
        for ev in evs:
            if ev.created_at >= week_start and not ev.correct:
                wrongs[cid] += 1
            if ev.created_at >= window_start:
                recent_total += 1
                if ev.correct:
                    recent_correct += 1
    top = []
    for cid, n in sorted(wrongs.items(), key=lambda kv: (-kv[1], kv[0]))[:5]:
        snap = snaps[cid]
        top.append(
            {
                "card_id": cid,
                "lemma": snap.lemma,
                "cn": snap.cn,
                "wrongs": n,
                "top_error": top_error_shape(ctx["events"].get(cid, [])),
                "unit_ord": snap.unit_ord,
            }
        )
    current = current_dev_unit(ctx["units"])
    acc = None if recent_total == 0 else recent_correct / recent_total
    return {
        "nails": nails,
        "top_misses": top,
        "recent_accuracy": _round(acc),
        "recent_correct": recent_correct,
        "recent_total": recent_total,
        "recent_days": 3,
        "streak_days": study_streak_days(ctx["events"], ctx["now"]),
        "current_unit": unit_public(current) if current else None,
        "life_unlocked": life_unlocked(ctx["units"]),
        "units": [unit_public(u) for u in sorted(ctx["units"], key=lambda u: (u.kind != "dev", u.ord))],
    }


def rule_summary(weak: dict[str, Any]) -> str:
    current = weak.get("current_unit") or {}
    title = current.get("title") or "当前单元"
    nails = weak.get("nails") or []
    if nails:
        words = "、".join(n["lemma"] for n in nails[:3])
        return f"钉子词 {words} 先清掉，再继续「{title}」。"
    acc = weak.get("recent_accuracy")
    if acc is None:
        return f"从「{title}」开始敲新词。后半单元和错得多的词会加上例句。"
    pct = round(float(acc) * 100)
    return f"近 {weak.get('recent_days', 3)} 天正确率 {pct}%。继续「{title}」，到期的先复习。"


def _target(feedback: str | None) -> int:
    if feedback == "easier":
        return EASIER_TARGET
    return DEFAULT_TARGET


def rule_queue(ctx: dict[str, Any], feedback: str | None) -> dict[str, Any]:
    built = build_queue(
        ctx["snaps"],
        ctx["units"],
        now=ctx["now"],
        target=_target(feedback),
        force_sentences=feedback == "harder",
    )
    built["date"] = ctx["today"]
    built["feedback"] = feedback
    built["generator"] = "rules-v1"
    built["degraded"] = None
    return built


def _save_plan(
    db: Session,
    user_name: str,
    summary: str,
    queue: dict[str, Any],
    weak: dict[str, Any],
    source: str,
    until: Any,
) -> CoachPlan:
    row = CoachPlan(
        user_name=user_name,
        created_at=utcnow(),
        summary=summary,
        queue_json=queue,
        until=until,
        source=source,
        weak_json=weak,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _canon(weak: dict[str, Any], feedback: str | None, model: str, day: str) -> str:
    payload = {
        "day": day,
        "feedback": feedback,
        "model": model,
        "current": (weak.get("current_unit") or {}).get("id"),
        "acc": weak.get("recent_accuracy"),
        "nails": [n["card_id"] for n in weak.get("nails") or []],
        "misses": [m["card_id"] for m in weak.get("top_misses") or []],
        "life": weak.get("life_unlocked"),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _messages(weak: dict[str, Any], ctx: dict[str, Any], feedback: str | None) -> list[dict[str, str]]:
    apply_unlocks(ctx["units"])
    unlocked = {u.unit_id for u in ctx["units"] if u.unlocked}
    cards = []
    for snap in ctx["snaps"]:
        if snap.unit_id not in unlocked:
            continue
        cards.append(
            {
                "card_id": snap.card_id,
                "lemma": snap.lemma,
                "cn": snap.cn,
                "unit_ord": snap.unit_ord,
                "kind": snap.kind,
                "has_sentence": bool(snap.sentences),
                "reps": snap.reps,
                "streak_wrong": snap.streak_wrong,
                "lapses": snap.lapses,
                "state": snap.state or 0,
            }
        )
    hint = "按你的判断决定今天练几条、哪些要敲例句。"
    if feedback == "easier":
        hint = "用户觉得太难。今天大约 10 条，例句少一点。"
    elif feedback == "harder":
        hint = "用户觉得太简单。保持大约 20 条，并给这些词加上例句阶段。"
    system = (
        "你是云芽英语的敲击教练。只输出一个 JSON 对象，不要写别的文字。"
        "你只能使用给定的 card_id。不要发明单词。"
        "生活英语（kind=life）只有在 life_unlocked 时才能出现，并且不能超过队列的 20%。"
        "未解锁单元的词不要排进去。钉子词必须排上，阶段用 A 再 B。"
        "新词至少有阶段 A。阶段 B 表示敲整句。"
    )
    user = {
        "hint": hint,
        "weak": {
            "nails": weak.get("nails"),
            "top_misses": weak.get("top_misses"),
            "recent_accuracy": weak.get("recent_accuracy"),
            "current_unit": weak.get("current_unit"),
            "life_unlocked": weak.get("life_unlocked"),
        },
        "cards": cards,
        "schema": {
            "summary": "一句中文，指出薄弱点和今天怎么练",
            "include_sentences": True,
            "target_count": 20,
            "defer_next_unit": False,
            "queue": [{"card_id": 1, "phase": "A", "reason": "nail"}],
        },
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def _accept_model_queue(raw: dict[str, Any], ctx: dict[str, Any], feedback: str | None) -> dict[str, Any] | None:
    summary = str(raw.get("summary") or "").strip()
    if not summary or len(summary) > 800:
        return None
    try:
        target = int(raw.get("target_count") or DEFAULT_TARGET)
    except (TypeError, ValueError):
        return None
    target = max(1, min(40, target))
    if feedback == "easier":
        target = min(target, EASIER_TARGET)
    defer = bool(raw.get("defer_next_unit"))
    snaps = {s.card_id: s for s in ctx["snaps"]}
    apply_unlocks(ctx["units"])
    unlocked = {u.unit_id for u in ctx["units"] if u.unlocked}
    items: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    queue = raw.get("queue")
    if not isinstance(queue, list):
        return None
    for row in queue:
        if not isinstance(row, dict):
            continue
        try:
            cid = int(row.get("card_id"))
        except (TypeError, ValueError):
            continue
        snap = snaps.get(cid)
        if snap is None or snap.unit_id not in unlocked:
            continue
        phase = row.get("phase")
        if phase not in ("A", "B"):
            continue
        if phase == "B" and not snap.sentences:
            continue
        if defer and snap.reps <= 0:
            continue
        if (cid, phase) in seen:
            continue
        seen.add((cid, phase))
        reason = row.get("reason")
        if reason not in ("nail", "due", "new", "life", "focus"):
            reason = "focus"
        if snap.kind == "life":
            reason = "life"
        elif reason == "life":
            reason = "focus"
        items.append(make_item(snap, phase, reason))
    main = [i for i in items if i["reason"] != "life"]
    life = [i for i in items if i["reason"] == "life"]
    life = life[: life_slot_cap(len(main))]
    items = cap_items(main, target) + life
    if not items:
        return None
    return {
        "date": ctx["today"],
        "items": items,
        "include_sentences": any(i["phase"] == "B" for i in items),
        "target_count": target,
        "current_unit_id": (current_dev_unit(ctx["units"]).unit_id if current_dev_unit(ctx["units"]) else None),
        "life_unlocked": life_unlocked(ctx["units"]),
        "all_dev_graduated": all(u.graduated for u in ctx["units"] if u.kind == "dev"),
        "feedback": feedback,
        "generator": "deepseek",
        "degraded": None,
        "summary": summary,
        "defer_next_unit": defer,
    }


def _store_cache(
    db: Session,
    key: str,
    model: str,
    content: dict[str, Any],
    tokens_in: int | None,
    tokens_out: int | None,
) -> None:
    db.add(
        AiCache(
            cache_key=key,
            kind=CACHE_KIND,
            model=model,
            prompt_ver=PROMPT_VER,
            content=content,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def _deepseek_queue(
    db: Session,
    user_name: str,
    ctx: dict[str, Any],
    weak: dict[str, Any],
    feedback: str | None,
    settings: Settings,
) -> tuple[dict[str, Any] | None, str | None]:
    """成功返回 (queue, None)。失败返回 (None, degraded 原因)。无密钥返回 (None, None)，交给规则。"""
    key = settings.deepseek_api_key
    raw_key = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
    if not raw_key.strip():
        return None, None
    canon = _canon(weak, feedback, settings.deepseek_model, ctx["today"])
    ckey = hashlib.sha256(f"{CACHE_KIND}|{settings.deepseek_model}|{PROMPT_VER}|{canon}".encode()).hexdigest()
    cached = db.get(AiCache, ckey)
    if cached and isinstance(cached.content, dict):
        accepted = _accept_model_queue(cached.content, ctx, feedback)
        if accepted is not None:
            return accepted, None
    try:
        check_ai_cap(db, user_name, settings)
    except ApiError as exc:
        if exc.code == "ai_daily_cap":
            return None, "ai_daily_cap"
        raise
    try:
        result = complete_chat(_messages(weak, ctx, feedback), settings)
        parsed = parse_json_text(result["text"])
    except DeepSeekError as exc:
        logger.warning("coach deepseek failed code=%s", exc.code)
        reason = "ai_bad_output" if exc.code == "bad_output" else "ai_unavailable"
        return None, reason
    except ValueError:
        logger.warning("coach deepseek returned non-json")
        return None, "ai_bad_output"
    accepted = _accept_model_queue(parsed, ctx, feedback)
    if accepted is None:
        return None, "ai_bad_output"
    bump_ai_calls(db, user_name, settings)
    _store_cache(db, ckey, result["model"], parsed, result.get("tokens_in"), result.get("tokens_out"))
    return accepted, None


def create_plan(
    db: Session,
    user_name: str,
    *,
    feedback: str | None = None,
    settings: Settings | None = None,
) -> CoachPlan:
    settings = settings or get_settings()
    ctx = load_context(db, user_name)
    weak = weak_summary(ctx)
    queue, degraded = _deepseek_queue(db, user_name, ctx, weak, feedback, settings)
    if queue is None:
        queue = rule_queue(ctx, feedback)
        queue["degraded"] = degraded
        summary = rule_summary(weak)
        source = "rules"
    else:
        summary = str(queue.pop("summary"))
        source = "deepseek"
    return _save_plan(db, user_name, summary, queue, weak, source, ctx["today_end"])


def latest_plan(db: Session, user_name: str) -> CoachPlan | None:
    return db.scalar(
        select(CoachPlan)
        .where(CoachPlan.user_name == user_name)
        .order_by(CoachPlan.created_at.desc(), CoachPlan.id.desc())
        .limit(1)
    )


def active_today_plan(db: Session, user_name: str, ctx: dict[str, Any]) -> CoachPlan | None:
    row = latest_plan(db, user_name)
    if row is None:
        return None
    queue = row.queue_json or {}
    if queue.get("date") != ctx["today"]:
        return None
    if row.until <= ctx["now"]:
        return None
    return row


def serve_items(ctx: dict[str, Any], queue: dict[str, Any]) -> list[dict[str, Any]]:
    """按今天的对错收掉已完成项，并把仍存在的钉子词提到前面。"""
    apply_unlocks(ctx["units"])
    unlocked = {u.unit_id for u in ctx["units"] if u.unlocked}
    snaps = {s.card_id: s for s in ctx["snaps"]}
    done = ctx["done_today"]
    rest: list[dict[str, Any]] = []
    for item in queue.get("items") or []:
        if not isinstance(item, dict):
            continue
        cid = item.get("card_id")
        phase = item.get("phase")
        snap = snaps.get(cid)
        if snap is None or snap.unit_id not in unlocked or phase not in ("A", "B"):
            continue
        if (cid, phase) in done:
            continue
        fresh = make_item(snap, phase, item.get("reason") or "focus")
        if snap.kind == "life":
            fresh["reason"] = "life"
        rest.append(fresh)
    nail_card_ids = {item["card_id"] for item in nail_items(ctx["snaps"], ctx["units"])}
    rest = [item for item in rest if item["card_id"] not in nail_card_ids or item["kind"] == "life"]
    forced = [
        item
        for item in nail_items(ctx["snaps"], ctx["units"], force_sentences=False)
        if (item["card_id"], item["phase"]) not in done
    ]
    merged: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for item in forced + rest:
        key = (item["card_id"], item["phase"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def today_payload(db: Session, user_name: str) -> dict[str, Any]:
    ctx = load_context(db, user_name)
    plan = active_today_plan(db, user_name, ctx)
    if plan is None:
        weak = weak_summary(ctx)
        queue = rule_queue(ctx, None)
        plan = _save_plan(db, user_name, rule_summary(weak), queue, weak, "rules", ctx["today_end"])
        ctx = load_context(db, user_name)
    queue = plan.queue_json or {}
    items = serve_items(ctx, queue)
    apply_unlocks(ctx["units"])
    current = current_dev_unit(ctx["units"])
    return {
        "date": ctx["today"],
        "source": plan.source,
        "plan_id": plan.id,
        "summary": plan.summary,
        "degraded": queue.get("degraded"),
        "include_sentences": any(i["phase"] == "B" for i in items),
        "target_count": queue.get("target_count"),
        "current_unit": unit_public(current) if current else None,
        "life_unlocked": life_unlocked(ctx["units"]),
        "units": [unit_public(u) for u in sorted(ctx["units"], key=lambda u: (u.kind != "dev", u.ord))],
        "items": items,
    }


def coach_payload(db: Session, user_name: str) -> dict[str, Any]:
    ctx = load_context(db, user_name)
    plan = latest_plan(db, user_name)
    return {"weak": weak_summary(ctx), "plan": _plan_public(plan, ctx) if plan else None}


def _plan_public(plan: CoachPlan, ctx: dict[str, Any]) -> dict[str, Any]:
    queue = plan.queue_json or {}
    active = queue.get("date") == ctx["today"] and plan.until > ctx["now"]
    return {
        "id": plan.id,
        "source": plan.source,
        "summary": plan.summary,
        "created_at": iso_local(plan.created_at),
        "until": iso_local(plan.until),
        "active": active,
        "degraded": queue.get("degraded"),
        "include_sentences": queue.get("include_sentences"),
        "target_count": queue.get("target_count"),
        "feedback": queue.get("feedback"),
        "current_unit_id": queue.get("current_unit_id"),
        "life_unlocked": queue.get("life_unlocked"),
        "queue": queue.get("items") or [],
    }


def _event_public(ev: TypeEvent, cs: CardState | None, rating: int | None, duplicate: bool) -> dict[str, Any]:
    return {
        "duplicate": duplicate,
        "event_id": ev.id,
        "card_id": ev.card_id,
        "unit_id": ev.unit_id,
        "phase": ev.phase,
        "correct": ev.correct,
        "typed": ev.typed,
        "expected": ev.expected,
        "error_shape": ev.error_shape,
        "duration_ms": ev.duration_ms,
        "sentence_index": ev.sentence_index,
        "rating": rating,
        "review_id": ev.review_id,
        "card_state": review_svc.card_state_out(cs),
    }


def submit_type(
    db: Session,
    user_name: str,
    *,
    card_id: int,
    phase: str,
    typed: str,
    duration_ms: int | None,
    sentence_index: int | None,
    attempts: int,
    client_event_id: str | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if client_event_id:
        existing = db.scalar(select(TypeEvent).where(TypeEvent.client_event_id == client_event_id))
        if existing is not None:
            review = db.get(ReviewLog, existing.review_id) if existing.review_id else None
            cs = db.get(CardState, existing.card_id)
            return _event_public(existing, cs, review.rating if review else None, True)

    ctx = load_context(db, user_name)
    found = find_card_unit(ctx, card_id)
    if found is None:
        raise ApiError(404, "not_found", "这张卡不在云芽英语课表里")
    _card, unit, snap = found
    apply_unlocks(ctx["units"])
    if not unit.unlocked:
        raise ApiError(409, "unit_locked", "这个单元还没解锁")
    expected = expected_text(snap, phase, sentence_index)
    if expected is None:
        raise ApiError(409, "no_sentence", "这张卡没有可敲的例句")
    correct, shape = grade_attempt(expected, typed, phase, ignore_case=settings.type_ignore_case)
    rating = rating_for(correct, attempts)
    applied = review_svc.apply_one(
        db,
        {
            "card_id": card_id,
            "rating": rating,
            "duration_ms": duration_ms,
            "answer_text": typed,
            "errors": 0 if correct and attempts <= 1 else max(attempts, 1),
            "client": "yun-ya",
            "client_review_id": (
                hashlib.sha256(f"type:{client_event_id}".encode()).hexdigest() if client_event_id else None
            ),
        },
        user_name,
        ctx["now"],
    )
    ev = TypeEvent(
        card_id=card_id,
        unit_id=unit.unit_id,
        user_name=user_name,
        phase=phase,
        correct=correct,
        typed=typed,
        expected=expected,
        duration_ms=duration_ms,
        error_shape=None if correct else shape,
        sentence_index=sentence_index if phase == "B" else None,
        client_event_id=client_event_id,
        review_id=applied["review_id"],
        created_at=ctx["now"],
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    cs = db.get(CardState, card_id)
    return _event_public(ev, cs, rating, False)
