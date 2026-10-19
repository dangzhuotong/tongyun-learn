"""云芽英语纯逻辑：判分细节、毕业/解锁、今日队列组装、课表快照。够小、离线、不碰库。"""

from datetime import datetime, timedelta

from tongyun_learn.data.en_curriculum import DEFAULT_GRADUATE_RULE
from tongyun_learn.models import TypeEvent
from tongyun_learn.services.en_curriculum import expected_text, study_streak_days, top_error_shape
from tongyun_learn.services.en_grade import _compact, _levenshtein, classify_mismatch
from tongyun_learn.services.en_progress import (
    CardSnap,
    UnitProgress,
    _is_due,
    _is_nail,
    _is_new,
    _phases,
    apply_unlocks,
    build_queue,
    cap_items,
    current_dev_unit,
    dev_all_graduated,
    is_graduated,
    life_slot_cap,
    life_unlocked,
    make_item,
    nail_items,
    recent_window_start,
    rule_of,
)

NOW = datetime(2026, 10, 14, 10, 0, 0)
DUE_AT = datetime(2026, 10, 14, 6, 0, 0)


def _snap(**kw) -> CardSnap:
    base = dict(
        card_id=1,
        unit_id=1,
        unit_ord=1,
        unit_title="U1",
        track="en",
        kind="dev",
        ord=1,
        lemma="read",
        phonetic="/riːd/",
        cn="阅读",
        pos="v.",
        sentences=[{"en": "Read this.", "zh": "读这个。"}],
        state=None,
        due=None,
        reps=0,
        lapses=0,
        streak_wrong=0,
        recent_correct=0,
        recent_total=0,
        unit_total=3,
        rule=dict(DEFAULT_GRADUATE_RULE),
    )
    base.update(kw)
    return CardSnap(**base)


def _unit(uid: int, kind: str, **kw) -> UnitProgress:
    base = dict(
        unit_id=uid,
        track="en" if kind == "dev" else "en-life",
        ord=uid,
        title=f"U{uid}",
        kind=kind,
        total=2,
        in_review=0,
        recent_correct=0,
        recent_total=0,
        nail_card_ids=[],
        rule=dict(DEFAULT_GRADUATE_RULE),
    )
    base.update(kw)
    return UnitProgress(**base)


# ───────────────────────── 判分细节 ─────────────────────────


def test_levenshtein_distance_and_limit():
    assert _levenshtein("read", "read") == 0
    assert _levenshtein("read", "red") == 1
    assert _levenshtein("read", "bread") == 1
    assert _levenshtein("abc", "xyz") == 3
    # 长度差超过 limit 直接返回 limit + 1，不再算完整矩阵
    assert _levenshtein("a", "abcdefg") == 5


def test_compact_drops_case_punct_and_spaces():
    assert _compact("Well-known, ok!") == "well-knownok"
    assert _compact("  DON'T  stop. ") == "don'tstop"


def test_classify_prefix_and_transposition_edge():
    # typed 是 expected 的后缀（少了开头），归为前缀问题
    assert classify_mismatch("return", "turn") == "prefix"
    # 相邻两个字母互换
    assert classify_mismatch("form", "from") == "transposition"


# ───────────────────────── 毕业规则 ─────────────────────────


def test_rule_of_fills_defaults_without_mutating_source():
    assert rule_of(None) == DEFAULT_GRADUATE_RULE
    merged = rule_of({"review_ratio": 0.5, "nail_streak": None})
    assert merged["review_ratio"] == 0.5
    assert merged["nail_streak"] == DEFAULT_GRADUATE_RULE["nail_streak"]
    assert DEFAULT_GRADUATE_RULE["review_ratio"] == 0.8


def test_is_graduated_uses_custom_rule():
    # 放宽到 50% 复习态、60% 正确率后，同一组数据可以毕业
    assert not is_graduated(total=10, in_review=6, recent_total=10, recent_correct=7, nail_count=0)
    assert is_graduated(
        total=10,
        in_review=6,
        recent_total=10,
        recent_correct=7,
        nail_count=0,
        rule={"review_ratio": 0.5, "recent_accuracy": 0.6},
    )


def test_life_slot_cap_zero_and_custom_fraction():
    assert life_slot_cap(0) == 0
    assert life_slot_cap(5, fraction=0) == 0
    assert life_slot_cap(4, fraction=0.5) == 4


def test_unit_progress_ratios_handle_empty():
    unit = _unit(1, "dev", total=0, in_review=0, recent_correct=0, recent_total=0)
    assert unit.review_ratio == 0.0
    assert unit.recent_accuracy is None

    unit = _unit(1, "dev", total=4, in_review=1, recent_correct=3, recent_total=4)
    assert unit.review_ratio == 0.25
    assert unit.recent_accuracy == 0.75


# ───────────────────────── 卡片状态判定 ─────────────────────────


def test_card_state_predicates():
    assert _is_new(_snap(reps=0, state=None)) is True
    assert _is_new(_snap(reps=3, state=None)) is True
    assert _is_new(_snap(reps=1, state=2)) is False

    assert _is_due(_snap(reps=2, state=2, due=DUE_AT), NOW) is True
    assert _is_due(_snap(reps=2, state=2, due=NOW + timedelta(days=1)), NOW) is False
    assert _is_due(_snap(reps=0, state=None, due=DUE_AT), NOW) is False

    assert _is_nail(_snap(streak_wrong=3)) is True
    assert _is_nail(_snap(streak_wrong=2)) is False


# ───────────────────────── 阶段与条目 ─────────────────────────


def test_phases_reasons_and_force_sentences():
    snap = _snap()
    assert _phases(snap, "life", False) == ["A"]
    assert _phases(_snap(sentences=[]), "nail", False) == ["A"]
    assert _phases(snap, "nail", False) == ["A", "B"]
    # due 只有在有近期错误痕迹时才加句阶段
    assert _phases(_snap(streak_wrong=1), "due", False) == ["A", "B"]
    assert _phases(_snap(recent_total=4, recent_correct=1), "due", False) == ["A", "B"]
    assert _phases(_snap(recent_total=4, recent_correct=4), "due", False) == ["A"]
    # new：位于单元后半段或强制例句时加 B
    assert _phases(_snap(ord=3), "new", False) == ["A", "B"]
    assert _phases(_snap(ord=1), "new", False) == ["A"]
    assert _phases(_snap(ord=1), "new", True) == ["A", "B"]


def test_make_item_prompt_phase_a_and_b():
    snap = _snap()
    item_a = make_item(snap, "A", "new")
    assert item_a["prompt"] == {"cn": "阅读", "phonetic": "/riːd/", "pos": "v.", "zh": None, "sentence_index": None}
    item_b = make_item(snap, "B", "nail")
    assert item_b["prompt"]["zh"] == "读这个。"
    assert item_b["prompt"]["sentence_index"] == 0
    assert item_b["phase"] == "B"


def test_cap_items_keeps_all_nails_even_over_target():
    items = [
        {"reason": "nail", "ord": 1},
        {"reason": "due", "ord": 2},
        {"reason": "nail", "ord": 3},
        {"reason": "new", "ord": 4},
    ]
    assert cap_items(items, 1) == [{"reason": "nail", "ord": 1}, {"reason": "nail", "ord": 3}]
    assert cap_items(items, 3) == [
        {"reason": "nail", "ord": 1},
        {"reason": "due", "ord": 2},
        {"reason": "nail", "ord": 3},
    ]
    assert cap_items(items, 10) == items


# ───────────────────────── 解锁与当前单元 ─────────────────────────


def test_apply_unlocks_sequential_and_life_gate():
    units = [_unit(1, "dev"), _unit(2, "dev"), _unit(3, "dev"), _unit(9, "life")]
    units[0] = _unit(1, "dev", total=2, in_review=2, recent_total=4, recent_correct=4)
    apply_unlocks(units)
    assert [(u.unit_id, u.unlocked, u.graduated) for u in units] == [
        (1, True, True),
        (2, True, False),
        (3, False, False),
        (9, False, False),
    ]
    assert life_unlocked(units) is False
    assert current_dev_unit(units).unit_id == 2
    assert dev_all_graduated(units) is False

    all_done = [
        _unit(1, "dev", total=2, in_review=2, recent_total=4, recent_correct=4),
        _unit(2, "dev", total=2, in_review=2, recent_total=4, recent_correct=4),
        _unit(3, "dev", total=2, in_review=2, recent_total=4, recent_correct=4),
        _unit(9, "life"),
    ]
    apply_unlocks(all_done)
    assert all(u.unlocked for u in all_done if u.kind == "dev")
    assert all_done[3].unlocked is True
    assert life_unlocked(all_done) is True
    assert dev_all_graduated(all_done) is True


def test_recent_window_start_never_before_one_day():
    start = datetime(2026, 10, 14, 0, 0, 0)
    assert recent_window_start(start, 3) == datetime(2026, 10, 12, 0, 0, 0)
    assert recent_window_start(start, 0) == start


# ───────────────────────── 队列组装 ─────────────────────────


def test_build_queue_picks_nail_due_new_in_order():
    now = datetime(2026, 10, 14, 10, 0, 0)
    units = [_unit(1, "dev", total=3), _unit(9, "life")]
    snaps = [
        _snap(card_id=1, streak_wrong=3),
        _snap(card_id=2, ord=2, reps=4, state=2, due=datetime(2026, 10, 13)),
        _snap(card_id=3, ord=1),
    ]
    out = build_queue(snaps, units, now=now)
    assert out["current_unit_id"] == 1
    assert out["life_unlocked"] is False
    assert out["all_dev_graduated"] is False
    assert out["include_sentences"] is True
    assert [i["reason"] for i in out["items"]] == ["nail", "nail", "due", "new"]
    assert [i["phase"] for i in out["items"]] == ["A", "B", "A", "A"]


def test_nail_items_only_unlocked_dev_units():
    units = [_unit(1, "dev"), _unit(2, "dev")]
    snaps = [
        _snap(card_id=1, unit_id=1, streak_wrong=3),
        _snap(card_id=2, unit_id=2, streak_wrong=5),
        _snap(card_id=3, unit_id=1, streak_wrong=0),
    ]
    # 单元 1 未毕业 -> 单元 2 未解锁，其钉子词不进补队
    items = nail_items(snaps, units)
    assert [i["card_id"] for i in items] == [1, 1]
    assert all(i["reason"] == "nail" for i in items)


# ───────────────────────── 课表快照纯函数 ─────────────────────────


def test_expected_text_by_phase_and_index():
    snap = _snap()
    assert expected_text(snap, "A", None) == "read"
    assert expected_text(snap, "B", 0) == "Read this."
    assert expected_text(snap, "B", 5) is None
    assert expected_text(_snap(sentences=[]), "B", 0) is None


def test_top_error_shape_picks_most_frequent():
    events = [
        TypeEvent(card_id=1, user_name="web", phase="A", correct=False, typed="x", error_shape="case"),
        TypeEvent(card_id=2, user_name="web", phase="A", correct=False, typed="x", error_shape="case"),
        TypeEvent(card_id=3, user_name="web", phase="A", correct=False, typed="x", error_shape="suffix"),
        TypeEvent(card_id=4, user_name="web", phase="A", correct=True, typed="x", error_shape=None),
    ]
    assert top_error_shape(events) == "case"
    assert top_error_shape([]) is None


def test_study_streak_days_counts_back_from_today_or_yesterday():
    today = datetime(2026, 10, 14, 0, 0, 0)

    def event(day: int) -> TypeEvent:
        return TypeEvent(
            card_id=1,
            user_name="web",
            phase="A",
            correct=True,
            typed="read",
            created_at=datetime(2026, 10, day, 6, 0, 0),
        )

    assert study_streak_days({}, today) == 0
    assert study_streak_days({1: [event(14), event(13), event(12)]}, today) == 3
    # 今天还没学，从昨天往前数
    assert study_streak_days({1: [event(13), event(12)]}, today) == 2
    # 断档
    assert study_streak_days({1: [event(12)]}, today) == 0
