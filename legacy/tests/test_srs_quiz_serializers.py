"""Pure-function tests for SRS helpers, quiz grading, and serializers.

Tiny offline fixtures; does not touch database or network.
"""

import json
from datetime import datetime, timezone

import pytest

from tongyun_learn.data.en_curriculum import DEFAULT_GRADUATE_RULE, DEFAULT_TARGET, EASIER_TARGET
from tongyun_learn.errors import ApiError
from tongyun_learn.services.en_coach import (
    _accept_model_queue,
    _canon,
    _target,
    rule_summary,
    unit_public,
)
from tongyun_learn.services.en_grade import classify_mismatch, grade_attempt
from tongyun_learn.services.en_progress import CardSnap, UnitProgress
from tongyun_learn.services.queue import (
    OpenCtx,
    _new_point_key,
    _round_robin_open,
    _sort_key_available,
)
from tongyun_learn.services.review import _reviewed_at

# ─────────────────────────────────────────────────────────────
# 1. SRS Helpers: _reviewed_at validation and timezone handling
# ─────────────────────────────────────────────────────────────


def test_reviewed_at_none_returns_now():
    now_utc = datetime(2026, 10, 20, 4, 0, 0)
    assert _reviewed_at(None, now_utc) == now_utc


def test_reviewed_at_naive_and_aware_in_past():
    # now is naive UTC
    now_utc = datetime(2026, 10, 20, 4, 0, 0)
    # Naive raw is treated as Asia/Shanghai (UTC+8): 11:30 local == 03:30 UTC
    past_local_naive = datetime(2026, 10, 20, 11, 30, 0)
    expected_utc = datetime(2026, 10, 20, 3, 30, 0)
    assert _reviewed_at(past_local_naive, now_utc) == expected_utc

    # Explicitly timezone-aware UTC raw is converted to naive UTC
    past_aware_utc = datetime(2026, 10, 20, 3, 30, 0, tzinfo=timezone.utc)
    assert _reviewed_at(past_aware_utc, now_utc) == expected_utc


def test_reviewed_at_boundary_future_slack():
    now_utc = datetime(2026, 10, 20, 4, 0, 0)
    # Exactly on boundary (now_utc + FUTURE_SLACK = 04:10:00 UTC)
    boundary_aware = datetime(2026, 10, 20, 4, 10, 0, tzinfo=timezone.utc)
    assert _reviewed_at(boundary_aware, now_utc) == datetime(2026, 10, 20, 4, 10, 0)

    # Local naive 12:10:00 converts to 04:10:00 UTC, exactly boundary
    boundary_local_naive = datetime(2026, 10, 20, 12, 10, 0)
    assert _reviewed_at(boundary_local_naive, now_utc) == datetime(2026, 10, 20, 4, 10, 0)


def test_reviewed_at_future_exceeds_slack_raises_apierror():
    now_utc = datetime(2026, 10, 20, 4, 0, 0)
    # Exceeds FUTURE_SLACK by 1 second (04:10:01 UTC)
    over_slack_aware = datetime(2026, 10, 20, 4, 10, 1, tzinfo=timezone.utc)
    with pytest.raises(ApiError) as exc_info:
        _reviewed_at(over_slack_aware, now_utc)
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "validation_error"


# ─────────────────────────────────────────────────────────────
# 2. SRS Queue Helpers: _round_robin_open and point sort keys
# ─────────────────────────────────────────────────────────────


def test_round_robin_open_alphabetical_order_and_global_cap():
    by_subject = {
        "chem": ["c.1", "c.2", "c.3"],
        "bio": ["b.1", "b.2", "b.3"],
    }
    ctx = OpenCtx(opened_today=set(), ever_opened=set(), by_subject={}, global_n=0)
    # Round-robin picks bio first (alphabetical), then chem, then bio (round 2).
    # Reaching GLOBAL_NEW_POINTS = 3, so stops without opening chem a second time.
    opened = _round_robin_open(by_subject, ctx, accept=lambda subj, pid: True)
    assert opened == ["b.1", "c.1", "b.2"]


def test_round_robin_open_per_subject_cap():
    by_subject = {
        "bio": ["b.1", "b.2", "b.3", "b.4"],
    }
    ctx = OpenCtx(opened_today=set(), ever_opened=set(), by_subject={}, global_n=0)
    # bio is constrained by PER_SUBJECT_NEW_POINTS = 2
    opened = _round_robin_open(by_subject, ctx, accept=lambda subj, pid: True)
    assert opened == ["b.1", "b.2"]


def test_round_robin_open_skips_unacceptable_and_exhausts_candidates():
    by_subject = {
        "math": ["m.1", "m.2", "m.3"],
    }
    ctx = OpenCtx(opened_today=set(), ever_opened=set(), by_subject={}, global_n=0)

    # Accept only m.2 and m.3, skipping m.1
    def accept_fn(_subj: str, pid: str) -> bool:
        return pid in ("m.2", "m.3")

    opened = _round_robin_open(by_subject, ctx, accept=accept_fn)
    assert opened == ["m.2", "m.3"]


def test_sort_key_available_and_new_point_key():
    meta_learning = {
        "stage_ord": 1,
        "weight": 2,
        "unmet_soft": [],
        "ord": 10,
        "state": "learning",
    }
    meta_available = {
        "stage_ord": 1,
        "weight": 2,
        "unmet_soft": [],
        "ord": 10,
        "state": "available",
    }
    meta_high_stage = {
        "stage_ord": 2,
        "weight": 5,
        "unmet_soft": [],
        "ord": 1,
        "state": "learning",
    }

    # _sort_key_available: (stage_ord, -weight, len(unmet_soft), ord)
    assert _sort_key_available(meta_learning) == (1, -2, 0, 10)
    assert _sort_key_available(meta_high_stage) == (2, -5, 0, 1)

    # _new_point_key puts "learning" state first (0) before "available" (1)
    key_learn = _new_point_key(meta_learning)
    key_avail = _new_point_key(meta_available)
    assert key_learn[0] == 0
    assert key_avail[0] == 1
    assert key_learn < key_avail


# ─────────────────────────────────────────────────────────────
# 3. Quiz Grading & Mismatch Classifier
# ─────────────────────────────────────────────────────────────


def test_classify_mismatch_shared_stem_suffix_branch():
    # "connection" vs "connective":
    # They do NOT start with each other;
    # Levenshtein distance is 3 (exceeds <= 2 for near_word);
    # Shared prefix is "connect" (length 7 >= 10 // 2);
    # Length difference is 0 (<= 3);
    # This specifically exercises the shared-prefix fallback branch -> "suffix".
    assert classify_mismatch("connection", "connective") == "suffix"


def test_grade_attempt_case_strict_in_sentence_phase():
    # In sentence phase (B), loose punctuation applies, but when ignore_case=False,
    # case mismatches are caught and diagnosed as "case".
    passed, error = grade_attempt("The cat sat.", "the cat sat", "B", ignore_case=False)
    assert passed is False
    assert error == "case"


# ─────────────────────────────────────────────────────────────
# 4. Serializers & Coach Plan Formatting
# ─────────────────────────────────────────────────────────────


def test_unit_public_formatting_and_rounding():
    unit = UnitProgress(
        unit_id=10,
        track="en",
        ord=1,
        title="Unit 1 Basics",
        kind="dev",
        total=8,
        in_review=5,
        recent_correct=7,
        recent_total=9,
        nail_card_ids=[101, 102],
        rule=dict(DEFAULT_GRADUATE_RULE),
        unlocked=True,
        graduated=False,
    )
    data = unit_public(unit)
    assert data["id"] == 10
    assert data["ord"] == 1
    assert data["title"] == "Unit 1 Basics"
    assert data["unlocked"] is True
    assert data["graduated"] is False

    prog = data["progress"]
    assert prog["total"] == 8
    assert prog["in_review"] == 5
    assert prog["review_ratio"] == round(5 / 8, 4)
    assert prog["recent_correct"] == 7
    assert prog["recent_total"] == 9
    assert prog["recent_accuracy"] == round(7 / 9, 4)
    assert prog["nails"] == 2
    assert prog["recent_days"] == int(DEFAULT_GRADUATE_RULE["recent_days"])


def test_rule_summary_branches():
    # Branch 1: Has nail words -> clear nails first
    weak_with_nails = {
        "current_unit": {"title": "单元一"},
        "nails": [{"lemma": "abandon"}, {"lemma": "abstract"}],
    }
    s1 = rule_summary(weak_with_nails)
    assert "钉子词 abandon、abstract 先清掉" in s1
    assert "「单元一」" in s1

    # Branch 2: No nails, no recent accuracy -> start new words
    weak_no_history = {
        "current_unit": {"title": "单元二"},
        "nails": [],
        "recent_accuracy": None,
    }
    s2 = rule_summary(weak_no_history)
    assert "从「单元二」开始敲新词" in s2
    assert "后半单元和错得多的词会加上例句" in s2

    # Branch 3: No nails, has recent accuracy -> review due first
    weak_with_acc = {
        "current_unit": {"title": "单元三"},
        "nails": [],
        "recent_accuracy": 0.857,
        "recent_days": 3,
    }
    s3 = rule_summary(weak_with_acc)
    assert "近 3 天正确率 86%" in s3
    assert "继续「单元三」，到期的先复习" in s3


def test_target_and_canon_serializers():
    # _target feedback mapping
    assert _target("easier") == EASIER_TARGET
    assert _target("harder") == DEFAULT_TARGET
    assert _target(None) == DEFAULT_TARGET
    assert _target("other") == DEFAULT_TARGET

    # _canon serialization
    weak = {
        "current_unit": {"id": 1},
        "recent_accuracy": 0.9,
        "nails": [{"card_id": 5}],
        "top_misses": [{"card_id": 9}],
        "life_unlocked": True,
    }
    canon_str = _canon(weak, "easier", "deepseek-v3", "2026-10-20")
    assert isinstance(canon_str, str)
    decoded = json.loads(canon_str)
    assert decoded["current"] == 1
    assert decoded["day"] == "2026-10-20"
    assert decoded["feedback"] == "easier"
    assert decoded["model"] == "deepseek-v3"
    assert decoded["nails"] == [5]
    assert decoded["misses"] == [9]
    assert decoded["life"] is True


def test_accept_model_queue_sanitization_and_validation():
    # Invalid summary or non-list queue rejected
    ctx = {
        "today": "2026-10-20",
        "units": [
            UnitProgress(
                unit_id=1,
                track="en",
                ord=1,
                title="U1",
                kind="dev",
                total=2,
                in_review=2,
                recent_correct=4,
                recent_total=4,
                nail_card_ids=[],
                rule=dict(DEFAULT_GRADUATE_RULE),
                unlocked=True,
            )
        ],
        "snaps": [
            CardSnap(
                card_id=10,
                unit_id=1,
                unit_ord=1,
                unit_title="U1",
                track="en",
                kind="dev",
                ord=1,
                lemma="abandon",
                phonetic="/əˈbændən/",
                cn="放弃",
                pos="v.",
                sentences=[{"en": "Never abandon hope.", "zh": "永不放弃希望。"}],
                state=2,
                due=datetime(2026, 10, 20),
                reps=3,
                lapses=0,
                streak_wrong=0,
                recent_correct=3,
                recent_total=3,
            ),
            CardSnap(
                card_id=11,
                unit_id=1,
                unit_ord=1,
                unit_title="U1",
                track="en",
                kind="dev",
                ord=2,
                lemma="ability",
                phonetic="/əˈbɪləti/",
                cn="能力",
                pos="n.",
                sentences=[],  # No sentences!
                state=2,
                due=datetime(2026, 10, 20),
                reps=2,
                lapses=0,
                streak_wrong=0,
                recent_correct=2,
                recent_total=2,
            ),
        ],
    }

    assert _accept_model_queue({"summary": "", "queue": []}, ctx, None) is None
    assert _accept_model_queue({"summary": "ok", "queue": "not-a-list"}, ctx, None) is None

    # Valid raw queue with filtering:
    # - card 10 phase A accepted
    # - card 10 phase A duplicate skipped
    # - card 11 phase B skipped because no sentences
    # - card 999 non-existent skipped
    raw_model_output = {
        "summary": "今日重点突破",
        "target_count": 10,
        "defer_next_unit": False,
        "queue": [
            {"card_id": 10, "phase": "A", "reason": "due"},
            {"card_id": 10, "phase": "A", "reason": "due"},
            {"card_id": 11, "phase": "B", "reason": "due"},
            {"card_id": 999, "phase": "A", "reason": "new"},
        ],
    }
    accepted = _accept_model_queue(raw_model_output, ctx, feedback=None)
    assert accepted is not None
    assert accepted["summary"] == "今日重点突破"
    assert accepted["generator"] == "deepseek"
    assert len(accepted["items"]) == 1
    assert accepted["items"][0]["card_id"] == 10
    assert accepted["items"][0]["phase"] == "A"
    assert accepted["items"][0]["reason"] == "due"

