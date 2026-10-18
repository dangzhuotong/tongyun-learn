from datetime import datetime, timedelta

from tongyun_learn.models import CardState, Evidence, Point
from tongyun_learn.services.importer import deck_name
from tongyun_learn.services.state import (
    _latest_passed,
    _stable,
    is_vocab,
    needed_evidence,
    stale_evidence,
)


def test_is_vocab():
    p1 = Point(id="en.word-1", tags=["en_word", "cet4"])
    assert is_vocab(p1) is True

    p2 = Point(id="jf.git-secrets", tags=["git", "security"])
    assert is_vocab(p2) is False

    p3 = Point(id="empty-tags", tags=None)
    assert is_vocab(p3) is False


def test_needed_evidence():
    # 纯记忆卡（memory）不需要进阶证据
    p_mem = Point(id="p1", card_types=["memory"], mastery_evidence=["selftest", "feynman"])
    assert needed_evidence(p_mem) == []

    # 包含其他卡类型时，返回 mastery_evidence
    p_multi = Point(id="p2", card_types=["memory", "understand"], mastery_evidence=["selftest", "feynman"])
    assert needed_evidence(p_multi) == ["selftest", "feynman"]

    p_none = Point(id="p3", card_types=["understand"], mastery_evidence=None)
    assert needed_evidence(p_none) == []


def test_stable_card_state():
    # stability >= 21 且 last_rating >= 3
    cs_stable = CardState(stability=21.0, last_rating=3)
    assert _stable(cs_stable) is True

    cs_high_rating = CardState(stability=25.0, last_rating=4)
    assert _stable(cs_high_rating) is True

    # 稳定性不足
    cs_low_stab = CardState(stability=20.9, last_rating=3)
    assert _stable(cs_low_stab) is False

    # 最近评级不足（如评了 Again 1 或 Hard 2）
    cs_low_rating = CardState(stability=30.0, last_rating=2)
    assert _stable(cs_low_rating) is False

    # 空值
    cs_none = CardState(stability=None, last_rating=None)
    assert _stable(cs_none) is False


def test_latest_passed_and_stale_evidence():
    now = datetime(2026, 10, 14, 10, 0, 0)
    p = Point(id="p_test", card_types=["understand"], mastery_evidence=["selftest", "feynman"])

    ev1 = Evidence(
        type="selftest",
        passed=True,
        reviewer="axue",
        observed_at=now - timedelta(days=30),
    )
    ev2 = Evidence(
        type="selftest",
        passed=True,
        reviewer="axue",
        observed_at=now - timedelta(days=10),
    )
    # 未通过的证据不计入 latest_passed
    ev3_failed = Evidence(
        type="feynman",
        passed=False,
        reviewer="axue",
        observed_at=now - timedelta(days=5),
    )
    # 非法 reviewer 不计入
    ev4_other_reviewer = Evidence(
        type="feynman",
        passed=True,
        reviewer="other",
        observed_at=now - timedelta(days=5),
    )

    evs = [ev1, ev2, ev3_failed, ev4_other_reviewer]

    assert _latest_passed(evs, "selftest") == now - timedelta(days=10)
    assert _latest_passed(evs, "feynman") is None

    # selftest 在 10 天前达标（< 90 天），不算过期；feynman 从未达标，算作过期
    stale = stale_evidence(p, evs, now)
    assert len(stale) == 1
    assert stale[0] == ["feynman", None]

    # 若 selftest 达标时间在 91 天前，则也过期
    ev_old = Evidence(
        type="selftest",
        passed=True,
        reviewer="axue",
        observed_at=now - timedelta(days=91),
    )
    stale_both = stale_evidence(p, [ev_old], now)
    stale_types = [s[0] for s in stale_both]
    assert "selftest" in stale_types
    assert "feynman" in stale_types


def test_deck_name():
    assert deck_name("tech-english", "en_word") == "tech-english:en_word"
    assert deck_name("java-fde", "qa") == "java-fde:qa"
