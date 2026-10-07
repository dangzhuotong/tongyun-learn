"""阿学写课和证据（定稿 §2 POST /sessions、POST /evidence，§4 证据 passed 规则）。"""

from datetime import date, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from tongyun_learn.errors import ApiError
from tongyun_learn.models import Card, Evidence, Point, SessionPoint, Stage, StudySession, Subject
from tongyun_learn.services.review import apply_one
from tongyun_learn.services.state import recompute_points
from tongyun_learn.timeutil import to_utc_naive, utcnow

SELFTEST_PASS = 0.8
EXPRESS_PASS = 0.75


def express_to_rating(score: float, max_score: float) -> int:
    """表达分→FSRS，直接按比例（与 passed ≥0.75 永远一致）：<0.5 Again，<0.75 Hard，<1 Good，=1 Easy。"""
    r = score / max_score if max_score else 0.0
    if r < 0.5:
        return 1
    if r < EXPRESS_PASS:
        return 2
    if r < 1:
        return 3
    return 4


def judge_passed(type_: str, score: float | None, max_score: float | None, passed: bool | None) -> bool:
    if type_ in ("selftest", "express"):
        if score is None or not max_score:
            raise ApiError(422, "validation_error", f"{type_} 证据必须给 score 和 max（max>0）")
        if score < 0 or score > max_score:
            raise ApiError(422, "validation_error", "score 必须在 0..max 之间")
        return score / max_score >= (SELFTEST_PASS if type_ == "selftest" else EXPRESS_PASS)
    if passed is None:
        raise ApiError(422, "validation_error", f"{type_} 证据必须给 passed")
    return bool(passed)


def create_session(db: Session, body: dict) -> dict:
    now = utcnow()
    if body.get("subject_id") and db.get(Subject, body["subject_id"]) is None:
        raise ApiError(404, "not_found", "学科不存在")
    pids = list(dict.fromkeys(body.get("point_ids") or []))
    missing = [pid for pid in pids if db.get(Point, pid) is None]
    if missing:
        raise ApiError(404, "not_found", "知识点不存在", details={"point_ids": missing})
    s = StudySession(
        subject_id=body.get("subject_id"),
        date=body["date"] if isinstance(body["date"], date) else date.fromisoformat(body["date"]),
        minutes=body.get("minutes"),
        lesson_ref=body.get("lesson_ref"),
        cues=body.get("cues") or [],
        summary=body.get("summary"),
        stuck=body.get("stuck"),
        notes=body.get("notes"),
        source="axue",
        created_at=now,
    )
    db.add(s)
    db.flush()
    for pid in pids:
        db.add(SessionPoint(session_id=s.id, point_id=pid))
    db.flush()
    changes = recompute_points(db, pids, cause="session", cause_ref=str(s.id), now=now)
    db.commit()
    return {"session_id": s.id, "point_changes": changes}


def create_evidence(db: Session, body: dict) -> dict:
    now = utcnow()
    pid, sid = body.get("point_id"), body.get("stage_id")
    if not pid and not sid:
        raise ApiError(422, "validation_error", "point_id 和 stage_id 至少给一个")
    if pid and db.get(Point, pid) is None:
        raise ApiError(404, "not_found", "知识点不存在")
    if sid and db.get(Stage, sid) is None:
        raise ApiError(404, "not_found", "阶段不存在")
    if body.get("session_id") and db.get(StudySession, body["session_id"]) is None:
        raise ApiError(404, "not_found", "课次不存在")
    card = None
    if body.get("card_id"):
        card = db.get(Card, body["card_id"])
        if card is None:
            raise ApiError(404, "not_found", "卡片不存在")
        if pid and card.point_id and card.point_id != pid:
            raise ApiError(422, "validation_error", "card_id 不属于该知识点")
        pid = pid or card.point_id
    t = body["type"]
    score, max_score = body.get("score"), body.get("max")
    passed = judge_passed(t, score, max_score, body.get("passed"))
    observed = to_utc_naive(body["observed_at"]) if body.get("observed_at") else now
    if observed > now:
        observed = now
    ev = Evidence(
        point_id=pid,
        stage_id=sid,
        session_id=body.get("session_id"),
        card_id=card.id if card else None,
        type=t,
        score=Decimal(str(score)) if score is not None else None,
        max_score=Decimal(str(max_score)) if max_score is not None else None,
        passed=passed,
        rubric=body.get("rubric"),
        notes=body.get("notes"),
        reviewer="axue",
        observed_at=observed,
        created_at=now,
    )
    db.add(ev)
    db.flush()
    review = None
    if card is not None:
        rating = body.get("rating")
        if rating is None:
            if score is not None and max_score:
                rating = express_to_rating(float(score), float(max_score))
            else:
                rating = 3 if passed else 1
        review = apply_one(
            db,
            {
                "card_id": card.id,
                "rating": rating,
                "reviewed_at": observed.replace(tzinfo=timezone.utc),
                "client": "axue",
                "answer_text": body.get("notes"),
            },
            "axue",
            now,
        )
    changes = []
    if pid:
        # 只有通过的证据才清「待复查」（没通过的不算复查完成）
        changes = recompute_points(
            db, [pid], cause="evidence", cause_ref=str(ev.id), evidence_point_ids=[pid] if passed else [], now=now
        )
    if review is not None:
        changes = review["point_changes"] + changes
    db.commit()
    out = {"evidence_id": ev.id, "passed": passed, "point_changes": changes}
    if review is not None:
        out["review"] = review
    return out
