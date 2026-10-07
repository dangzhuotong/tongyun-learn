"""状态机规则与阈值测试（PRD §4 + 决定 1/2）。

覆盖：
1. 掌握 ①② 阈值与边界（卡数 ≥3、ratio ≥0.8、acc10 ≥0.85）
2. ③ 证据有效性（60 天窗口、reviewer 必须 axue/migrate）
3. 纯记忆卡点不看 ③ 证据
4. mastered → rusty 防抖阈值（ratio < 0.6 或 acc10 < 0.7 退化；0.6 / 0.7 恰好不退）
5. rusty → mastered 与 needs_recheck（>90 天证据置位，新证据清零）
6. learned 判定（自测不限分、全卡复习过）与粘性
7. 词汇点特化规则（学过 100 张卡 / passed 自测；掌握 30 天卡 ≥50 张）
8. 硬前置解锁、停用前置、软前置不阻碍、连锁解锁
9. point_state_log 状态变更审计日志
"""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.learn_helpers import AXUE, learn_env  # noqa: F401
from tongyun_learn.models import (
    Card,
    CardState,
    Deck,
    Evidence,
    Point,
    PointPrereq,
    PointState,
    PointStateLog,
    ReviewLog,
    Stage,
    Subject,
)
from tongyun_learn.services.cardkeys import front_key
from tongyun_learn.services.state import recompute_points
from tongyun_learn.timeutil import utcnow


def _get_or_create_subject(db: Session, subject_id: str = "subj-test") -> Subject:
    s = db.get(Subject, subject_id)
    if not s:
        s = Subject(id=subject_id, prefix=subject_id[:10], title=subject_id, active=True)
        db.add(s)
        db.flush()
    return s


def _get_or_create_stage(
    db: Session, stage_id: str = "stage-test", subject_id: str = "subj-test", ord: int = 1
) -> Stage:
    _get_or_create_subject(db, subject_id)
    st = db.get(Stage, stage_id)
    if not st:
        st = Stage(id=stage_id, subject_id=subject_id, ord=ord, title=stage_id, active=True)
        db.add(st)
        db.flush()
    return st


def _get_or_create_deck(db: Session, subject_id: str = "subj-test", kind: str = "qa") -> Deck:
    _get_or_create_subject(db, subject_id)
    d = db.scalar(select(Deck).where(Deck.subject_id == subject_id, Deck.kind == kind))
    if not d:
        d = Deck(subject_id=subject_id, kind=kind, name=f"{subject_id}:{kind}", review_cap=60, new_cap=8)
        db.add(d)
        db.flush()
    return d


def _create_point(
    db: Session,
    point_id: str,
    subject_id: str = "subj-test",
    stage_id: str = "stage-test",
    card_types: list[str] | None = None,
    mastery_evidence: list[str] | None = None,
    tags: list[str] | None = None,
    active: bool = True,
    ord: int = 1,
) -> Point:
    _get_or_create_stage(db, stage_id, subject_id, ord)
    p = db.get(Point, point_id)
    if not p:
        p = Point(
            id=point_id,
            subject_id=subject_id,
            stage_id=stage_id,
            ord=ord,
            title=point_id,
            card_types=card_types or ["understand"],
            mastery_evidence=mastery_evidence or [],
            tags=tags or [],
            active=active,
        )
        db.add(p)
        db.flush()
    return p


def _create_card(
    db: Session,
    point: Point,
    card_type: str = "understand",
    front: str = "f",
    active: bool = True,
    reviewed: bool = True,
    stability: float = 30.0,
    last_rating: int = 3,
    first_review: datetime | None = None,
    last_review: datetime | None = None,
) -> tuple[Card, CardState | None]:
    deck = _get_or_create_deck(db, point.subject_id, "en_word" if "en_word" in (point.tags or []) else "qa")
    fk = front_key(front)
    c = Card(
        deck_id=deck.id,
        point_id=point.id,
        card_type=card_type,
        front=front,
        front_key=fk,
        back="b",
        created_by="example",
        active=active,
    )
    db.add(c)
    db.flush()
    cs = None
    if reviewed:
        fr = first_review or utcnow() - timedelta(days=5)
        lr = last_review or utcnow() - timedelta(days=1)
        cs = CardState(
            card_id=c.id,
            state=1,  # learning / reviewed
            stability=stability,
            difficulty=0.3,
            reps=2,
            lapses=0,
            first_review=fr,
            last_review=lr,
            last_rating=last_rating,
        )
        db.add(cs)
        db.flush()
    return c, cs


def _add_review_log(
    db: Session,
    card: Card,
    rating: int = 3,
    reviewer: str = "axue",
    reviewed_at: datetime | None = None,
    applied: bool = True,
) -> ReviewLog:
    rl = ReviewLog(
        card_id=card.id,
        point_id=card.point_id,
        rating=rating,
        reviewer=reviewer,
        reviewed_at=reviewed_at or utcnow(),
        applied=applied,
    )
    db.add(rl)
    db.flush()
    return rl


def test_mastery_fsrs_thresholds(db_session: Session, learn_env):  # noqa: F811
    """掌握 ①②：
    - 已复习卡 = 3 且 ratio=0.8、acc10=0.85 达标 → mastered（mastery_evidence 为空或只有记忆卡的点）
    - 边界两侧：2 张卡（不达标）、ratio 0.79（不达标）、acc 0.84（不达标）
    """
    now = utcnow()
    db = db_session

    # Case 1: 边界达标：5 张卡（≥3），4 张稳定（ratio = 4/5 = 0.80 ≥ 0.8）；
    # 10 条 review_log 中 9 条 ≥3（acc10 = 0.90 ≥ 0.85）
    p1 = _create_point(db, "pt.m-ok", mastery_evidence=[])
    cards1 = []
    for i in range(5):
        # 前 4 张稳定（stability=25 >= 21, last_rating=3 >= 3），第 5 张不稳定（stability=10）
        stab = 25.0 if i < 4 else 10.0
        c, _ = _create_card(db, p1, front=f"c1_{i}", stability=stab, last_rating=3)
        cards1.append(c)
    # 10 条 review: 9 条 rating 3, 1 条 rating 2 (acc10 = 0.90)
    for i in range(10):
        _add_review_log(db, cards1[0], rating=3 if i < 9 else 2, reviewed_at=now - timedelta(minutes=10 - i))
    db.commit()

    recompute_points(db, [p1.id], cause="test", now=now)
    db.commit()
    assert db.get(PointState, p1.id).state == "mastered"

    # Case 2: 卡数边界不达标：仅 2 张已复习卡（< 3），哪怕 ratio=1.0、acc10=1.0
    p2 = _create_point(db, "pt.m-fail-cards", mastery_evidence=[])
    cards2 = []
    for i in range(2):
        c, _ = _create_card(db, p2, front=f"c2_{i}", stability=25.0, last_rating=3)
        cards2.append(c)
    for _ in range(10):
        _add_review_log(db, cards2[0], rating=4)
    db.commit()

    recompute_points(db, [p2.id], cause="test", now=now)
    db.commit()
    assert db.get(PointState, p2.id).state == "learned"  # 未达掌握门槛，停留在 learned

    # Case 3: ratio 边界不达标：100 张卡，79 张稳定（ratio = 0.79 < 0.80），acc10=1.0
    p3 = _create_point(db, "pt.m-fail-ratio", mastery_evidence=[])
    cards3 = []
    for i in range(100):
        stab = 25.0 if i < 79 else 10.0
        c, _ = _create_card(db, p3, front=f"c3_{i}", stability=stab, last_rating=3)
        cards3.append(c)
    for _ in range(10):
        _add_review_log(db, cards3[0], rating=4)
    db.commit()

    recompute_points(db, [p3.id], cause="test", now=now)
    db.commit()
    assert db.get(PointState, p3.id).state == "learned"

    # Case 4: acc10 边界不达标：5 张卡均稳定（ratio=1.0），最近 10 次 review 中 8 次 ≥3（acc10 = 0.80 < 0.85）
    p4 = _create_point(db, "pt.m-fail-acc", mastery_evidence=[])
    cards4 = []
    for i in range(5):
        c, _ = _create_card(db, p4, front=f"c4_{i}", stability=25.0, last_rating=3)
        cards4.append(c)
    for i in range(10):
        # 8 次 rating 3，2 次 rating 2 -> acc10 = 0.80
        _add_review_log(db, cards4[0], rating=3 if i < 8 else 2, reviewed_at=now - timedelta(minutes=10 - i))
    db.commit()

    recompute_points(db, [p4.id], cause="test", now=now)
    db.commit()
    assert db.get(PointState, p4.id).state == "learned"


def test_mastery_evidence_window_and_reviewer(db_session: Session, learn_env):  # noqa: F811
    """③ 证据：需要 selftest 的点：
    - 60 天内 passed 的 selftest 才算；61 天前的不算
    - reviewer 必须 axue/migrate（self 或其他不算）
    - passed 为 False 的不算
    """
    now = utcnow()
    db = db_session

    # 准备基础达标卡片（①② 均满足）
    def _setup_point_with_cards(pid: str) -> Point:
        p = _create_point(db, pid, card_types=["understand"], mastery_evidence=["selftest"])
        cards = []
        for i in range(3):
            c, _ = _create_card(db, p, front=f"{pid}_c_{i}", stability=25.0, last_rating=3)
            cards.append(c)
        for _ in range(10):
            _add_review_log(db, cards[0], rating=4)
        return p

    # 1) 证据在 60 天整 (恰好达标)
    p_60 = _setup_point_with_cards("pt.ev-60d")
    ev60 = Evidence(
        point_id=p_60.id,
        type="selftest",
        passed=True,
        reviewer="axue",
        observed_at=now - timedelta(days=60),
    )
    db.add(ev60)
    db.commit()
    recompute_points(db, [p_60.id], cause="evidence", now=now)
    db.commit()
    assert db.get(PointState, p_60.id).state == "mastered"

    # 2) 证据在 61 天前 (超期不达标)
    p_61 = _setup_point_with_cards("pt.ev-61d")
    ev61 = Evidence(
        point_id=p_61.id,
        type="selftest",
        passed=True,
        reviewer="axue",
        observed_at=now - timedelta(days=61),
    )
    db.add(ev61)
    db.commit()
    recompute_points(db, [p_61.id], cause="evidence", now=now)
    db.commit()
    assert db.get(PointState, p_61.id).state == "learned"

    # 3) reviewer 为 migrate (达标)
    p_mig = _setup_point_with_cards("pt.ev-mig")
    ev_mig = Evidence(
        point_id=p_mig.id,
        type="selftest",
        passed=True,
        reviewer="migrate",
        observed_at=now - timedelta(days=10),
    )
    db.add(ev_mig)
    db.commit()
    recompute_points(db, [p_mig.id], cause="evidence", now=now)
    db.commit()
    assert db.get(PointState, p_mig.id).state == "mastered"

    # 4) reviewer 不在 axue/migrate (如 None，不达标)
    p_none = _setup_point_with_cards("pt.ev-none")
    ev_none = Evidence(
        point_id=p_none.id,
        type="selftest",
        passed=True,
        reviewer=None,
        observed_at=now - timedelta(days=10),
    )
    db.add(ev_none)
    db.commit()
    recompute_points(db, [p_none.id], cause="evidence", now=now)
    db.commit()
    assert db.get(PointState, p_none.id).state == "learned"

    # 5) passed 为 False (不达标)
    p_fail = _setup_point_with_cards("pt.ev-fail")
    ev_fail = Evidence(
        point_id=p_fail.id,
        type="selftest",
        passed=False,
        reviewer="axue",
        observed_at=now - timedelta(days=10),
    )
    db.add(ev_fail)
    db.commit()
    recompute_points(db, [p_fail.id], cause="evidence", now=now)
    db.commit()
    assert db.get(PointState, p_fail.id).state == "learned"


def test_card_types_memory_only_skips_evidence(db_session: Session, learn_env):  # noqa: F811
    """card_types 只有 memory 的点不看 ③ 证据。"""
    now = utcnow()
    db = db_session

    # 仅记忆卡，但声明了 mastery_evidence=["selftest"]
    p_mem = _create_point(db, "pt.mem-only", card_types=["memory"], mastery_evidence=["selftest"])
    cards = []
    for i in range(3):
        c, _ = _create_card(db, p_mem, card_type="memory", front=f"m_{i}", stability=25.0, last_rating=3)
        cards.append(c)
    for _ in range(10):
        _add_review_log(db, cards[0], rating=4)
    db.commit()

    recompute_points(db, [p_mem.id], cause="test", now=now)
    db.commit()
    # 无需 selftest 证据直接达到 mastered
    assert db.get(PointState, p_mem.id).state == "mastered"

    # 对照组：多卡型含 understand，未给证据不能达到 mastered
    p_mix = _create_point(db, "pt.mix-cards", card_types=["memory", "understand"], mastery_evidence=["selftest"])
    cards_mix = []
    for i in range(3):
        c, _ = _create_card(db, p_mix, card_type="memory", front=f"mix_{i}", stability=25.0, last_rating=3)
        cards_mix.append(c)
    for _ in range(10):
        _add_review_log(db, cards_mix[0], rating=4)
    db.commit()

    recompute_points(db, [p_mix.id], cause="test", now=now)
    db.commit()
    assert db.get(PointState, p_mix.id).state == "learned"


def test_mastered_to_rusty_thresholds(db_session: Session, learn_env):  # noqa: F811
    """mastered → rusty：ratio < 0.6 或 acc10 < 0.7；0.6 / 0.7 恰好不退。"""
    now = utcnow()
    db = db_session

    # 1) 边界恰好不退：ratio = 0.60, acc10 = 0.70
    p_exact = _create_point(db, "pt.exact-no-rust", card_types=["memory"])
    cards = []
    for i in range(10):
        # 6 张稳定（ratio = 6/10 = 0.60），4 张不稳定
        stab = 25.0 if i < 6 else 10.0
        c, _ = _create_card(db, p_exact, card_type="memory", front=f"ex_{i}", stability=stab, last_rating=3)
        cards.append(c)
    for i in range(10):
        # 7 次 rating 3，3 次 rating 2 -> acc10 = 7/10 = 0.70
        _add_review_log(db, cards[0], rating=3 if i < 7 else 2, reviewed_at=now - timedelta(minutes=10 - i))
    # 手动先置为 mastered
    ps_exact = PointState(point_id=p_exact.id, state="mastered", since=now, ever_mastered=True)
    db.add(ps_exact)
    db.commit()

    recompute_points(db, [p_exact.id], cause="review", now=now)
    db.commit()
    assert db.get(PointState, p_exact.id).state == "mastered"

    # 2) ratio < 0.6 退到 rusty：100 张卡中 59 张稳定（ratio = 0.59 < 0.60），acc10 = 1.0
    p_ratio_drop = _create_point(db, "pt.drop-ratio", card_types=["memory"])
    cards_r = []
    for i in range(100):
        stab = 25.0 if i < 59 else 10.0
        c, _ = _create_card(db, p_ratio_drop, card_type="memory", front=f"dr_{i}", stability=stab, last_rating=3)
        cards_r.append(c)
    for _ in range(10):
        _add_review_log(db, cards_r[0], rating=4)
    ps_r = PointState(point_id=p_ratio_drop.id, state="mastered", since=now, ever_mastered=True)
    db.add(ps_r)
    db.commit()

    recompute_points(db, [p_ratio_drop.id], cause="review", now=now)
    db.commit()
    assert db.get(PointState, p_ratio_drop.id).state == "rusty"

    # 3) acc10 < 0.7 退到 rusty：10 张卡均稳定（ratio = 1.0），10 次 review 中 6 次 ≥3（acc10 = 0.60 < 0.70）
    p_acc_drop = _create_point(db, "pt.drop-acc", card_types=["memory"])
    cards_a = []
    for i in range(10):
        c, _ = _create_card(db, p_acc_drop, card_type="memory", front=f"da_{i}", stability=25.0, last_rating=3)
        cards_a.append(c)
    for i in range(10):
        _add_review_log(db, cards_a[0], rating=3 if i < 6 else 2, reviewed_at=now - timedelta(minutes=10 - i))
    ps_a = PointState(point_id=p_acc_drop.id, state="mastered", since=now, ever_mastered=True)
    db.add(ps_a)
    db.commit()

    recompute_points(db, [p_acc_drop.id], cause="review", now=now)
    db.commit()
    assert db.get(PointState, p_acc_drop.id).state == "rusty"


def test_rusty_to_mastered_and_needs_recheck(client: TestClient, db_session: Session, learn_env):  # noqa: F811
    """rusty → mastered 只需 ①②；
    need 类证据最近一次 >90 天时 needs_recheck=1；
    随后对该点 POST 任意证据（哪怕没通过）needs_recheck 清 0。
    """
    now = utcnow()
    db = db_session

    p = _create_point(db, "pt.rusty-recheck", card_types=["understand"], mastery_evidence=["selftest"])
    # 建立一条 95 天前通过的 selftest 证据（> 90 天）
    ev = Evidence(
        point_id=p.id,
        type="selftest",
        passed=True,
        reviewer="axue",
        observed_at=now - timedelta(days=95),
    )
    db.add(ev)

    # 3 张卡满足 ①②
    cards = []
    for i in range(3):
        c, _ = _create_card(db, p, front=f"rr_{i}", stability=25.0, last_rating=3)
        cards.append(c)
    for _ in range(10):
        _add_review_log(db, cards[0], rating=4)

    # 初始状态为 rusty
    ps = PointState(point_id=p.id, state="rusty", since=now - timedelta(days=10), ever_mastered=True)
    db.add(ps)
    db.commit()

    # 重算：满足 ①② 即可重回 mastered，但因证据 >90 天，needs_recheck 应被置为 1
    recompute_points(db, [p.id], cause="review", now=now)
    db.commit()

    ps_updated = db.get(PointState, p.id)
    assert ps_updated.state == "mastered"
    assert ps_updated.needs_recheck is True

    # 随后通过 API POST 任意新证据（哪怕 passed 为 False / 分数不足）
    r = client.post(
        "/v1/evidence",
        json={"point_id": p.id, "type": "selftest", "score": 1, "max": 10},
        headers=AXUE,
    )
    assert r.status_code == 200, r.text
    assert r.json()["passed"] is False

    # 校验 needs_recheck 已被清 0
    db.rollback()  # 结束当前事务（MySQL 可重复读快照）
    db.expire_all()  # 没开事务时 rollback 是空操作，仍要清身份映射
    ps_after = db.get(PointState, p.id)
    assert ps_after.needs_recheck is False


def test_learned_selftest_or_all_cards_reviewed_and_sticky(db_session: Session, learn_env):  # noqa: F811
    """学过判定：
    - 一次 selftest（分数不限，哪怕 passed=False）即学过
    - 或该点 active 卡全部复习过即学过
    - 学过是粘性的（之后加新卡不回退到 learning）
    """
    now = utcnow()
    db = db_session

    # Case 1: 一次 selftest（分数不限、未通过）即学过
    p1 = _create_point(db, "pt.learn-selftest", card_types=["understand"])
    _create_card(db, p1, front="c_unrev", reviewed=False)  # 有未复习卡
    ev_fail = Evidence(point_id=p1.id, type="selftest", passed=False, reviewer="axue", observed_at=now)
    db.add(ev_fail)
    db.commit()

    recompute_points(db, [p1.id], cause="evidence", now=now)
    db.commit()
    assert db.get(PointState, p1.id).state == "learned"

    # Case 2: 该点 active 卡全部复习过（卡片不稳定，未达到 mastered）→ learned
    p2 = _create_point(db, "pt.learn-all-reviewed", card_types=["understand"])
    for i in range(3):
        # stability=5 < 21，未稳固
        _create_card(db, p2, front=f"rev_{i}", reviewed=True, stability=5.0, last_rating=3)
    db.commit()

    recompute_points(db, [p2.id], cause="review", now=now)
    db.commit()
    assert db.get(PointState, p2.id).state == "learned"

    # Case 3: 粘性测试（之后加新卡，active 卡未全部复习，且无 selftest，仍保持 learned，不回退到 learning）
    p3 = _create_point(db, "pt.learn-sticky", card_types=["understand"])
    _create_card(db, p3, front="stk_1", reviewed=True, stability=5.0)
    db.commit()
    recompute_points(db, [p3.id], cause="review", now=now)
    db.commit()
    assert db.get(PointState, p3.id).state == "learned"
    assert db.get(PointState, p3.id).learned_at is not None

    # 新增 2 张未复习卡
    _create_card(db, p3, front="stk_new_1", reviewed=False)
    _create_card(db, p3, front="stk_new_2", reviewed=False)
    db.commit()

    recompute_points(db, [p3.id], cause="card", now=now)
    db.commit()
    assert db.get(PointState, p3.id).state == "learned"  # 保持粘性，不回退


def test_vocab_point_rules(db_session: Session, learn_env):  # noqa: F811
    """词汇点（tags 含 en_word）：
    - 学过 = 复习过 ≥100 张或 passed selftest（99 张不算、未通过的 selftest 不算）
    - 掌握只算 first_review 满 30 天的卡且这批 ≥50 张（49 张不行）
    """
    now = utcnow()
    db = db_session

    # 1) 学过规则：99 张卡不算学过
    p_v99 = _create_point(db, "pt.v-99", tags=["en_word"])
    for i in range(99):
        _create_card(db, p_v99, front=f"w99_{i}", reviewed=True, stability=5.0)
    db.commit()
    recompute_points(db, [p_v99.id], cause="review", now=now)
    db.commit()
    assert db.get(PointState, p_v99.id).state == "learning"  # 99 张未达标，停留在 learning

    # 2) 学过规则：达到 100 张卡算学过
    _create_card(db, p_v99, front="w99_100", reviewed=True, stability=5.0)
    db.commit()
    recompute_points(db, [p_v99.id], cause="review", now=now)
    db.commit()
    assert db.get(PointState, p_v99.id).state == "learned"

    # 3) 词汇点未通过的 selftest 不算学过
    p_v_fail_ev = _create_point(db, "pt.v-fail-ev", tags=["en_word"])
    _create_card(db, p_v_fail_ev, front="w_fail_1", reviewed=True, stability=5.0)
    ev_fail = Evidence(point_id=p_v_fail_ev.id, type="selftest", passed=False, reviewer="axue", observed_at=now)
    db.add(ev_fail)
    db.commit()
    recompute_points(db, [p_v_fail_ev.id], cause="evidence", now=now)
    db.commit()
    assert db.get(PointState, p_v_fail_ev.id).state == "learning"  # 词汇点未通过 selftest 不能学过

    # 4) 词汇点通过的 selftest 可以学过
    ev_pass = Evidence(point_id=p_v_fail_ev.id, type="selftest", passed=True, reviewer="axue", observed_at=now)
    db.add(ev_pass)
    db.commit()
    recompute_points(db, [p_v_fail_ev.id], cause="evidence", now=now)
    db.commit()
    assert db.get(PointState, p_v_fail_ev.id).state == "learned"

    # 5) 掌握规则：只算 first_review 满 30 天的卡且这批 ≥50 张（49 张不行）
    p_vm = _create_point(db, "pt.v-master", tags=["en_word"])
    cards = []
    # 49 张满足 30 天（first_review = now - 35d），均稳固
    for i in range(49):
        c, _ = _create_card(
            db,
            p_vm,
            front=f"vm_old_{i}",
            reviewed=True,
            stability=25.0,
            last_rating=3,
            first_review=now - timedelta(days=35),
        )
        cards.append(c)
    # 另外 60 张新卡（first_review = now - 5d，未满 30 天，总卡数 49 + 60 = 109 >= 100 满足已学过门槛），均稳固
    for i in range(60):
        c, _ = _create_card(
            db,
            p_vm,
            front=f"vm_new_{i}",
            reviewed=True,
            stability=25.0,
            last_rating=3,
            first_review=now - timedelta(days=5),
        )
        cards.append(c)
    for _ in range(10):
        _add_review_log(db, cards[0], rating=4)
    db.commit()

    # 此时满 30 天的只有 49 张 (< 50)，哪怕总稳固卡数近百张，仍不能 mastered
    recompute_points(db, [p_vm.id], cause="review", now=now)
    db.commit()
    assert db.get(PointState, p_vm.id).state == "learned"

    # 将其中 1 张新卡的 first_review 改为满 30 天（达标 50 张）
    c_turn = cards[49]
    cs_turn = db.get(CardState, c_turn.id)
    assert cs_turn is not None
    cs_turn.first_review = now - timedelta(days=32)
    db.commit()

    recompute_points(db, [p_vm.id], cause="review", now=now)
    db.commit()
    assert db.get(PointState, p_vm.id).state == "mastered"


def test_prereq_unlock_and_cascading(db_session: Session, learn_env):  # noqa: F811
    """解锁规则：
    - 硬前置全部 ≥学过才 available
    - 停用的硬前置视为已满足
    - 软前置不影响解锁
    - 前置学过后下游自动从 locked 变 available（连锁重算）
    """
    now = utcnow()
    db = db_session

    p_up = _create_point(db, "pt.up")
    p_down = _create_point(db, "pt.down")
    # p_down 硬依赖 p_up
    db.add(PointPrereq(point_id=p_down.id, prereq_id=p_up.id, kind="hard"))
    db.commit()

    # 1) p_up 尚未学过（默认 available），p_down 应为 locked
    recompute_points(db, [p_up.id, p_down.id], cause="import", now=now)
    db.commit()
    assert db.get(PointState, p_up.id).state == "available"
    assert db.get(PointState, p_down.id).state == "locked"

    # 2) 连锁解锁：对 p_up 录入自测使其成为 learned，下游 p_down 应自动级联变为 available
    ev_up = Evidence(point_id=p_up.id, type="selftest", passed=True, reviewer="axue", observed_at=now)
    db.add(ev_up)
    db.commit()

    changes = recompute_points(db, [p_up.id], cause="evidence", now=now)
    db.commit()
    pids_changed = {c["point_id"] for c in changes}
    assert p_up.id in pids_changed
    assert p_down.id in pids_changed
    assert db.get(PointState, p_up.id).state == "learned"
    assert db.get(PointState, p_down.id).state == "available"

    # 3) 停用的硬前置视为已满足
    p_ghost = _create_point(db, "pt.ghost", active=False)
    p_down2 = _create_point(db, "pt.down2")
    db.add(PointPrereq(point_id=p_down2.id, prereq_id=p_ghost.id, kind="hard"))
    db.commit()

    recompute_points(db, [p_down2.id], cause="import", now=now)
    db.commit()
    assert db.get(PointState, p_down2.id).state == "available"

    # 4) 软前置不影响解锁
    p_soft_prereq = _create_point(db, "pt.soft-pre")
    p_soft_down = _create_point(db, "pt.soft-down")
    # p_soft_down 软依赖 p_soft_prereq；且 p_soft_prereq 处于 locked
    p_blocker = _create_point(db, "pt.blocker")
    db.add(PointPrereq(point_id=p_soft_prereq.id, prereq_id=p_blocker.id, kind="hard"))
    db.add(PointPrereq(point_id=p_soft_down.id, prereq_id=p_soft_prereq.id, kind="soft"))
    db.commit()

    recompute_points(db, [p_soft_prereq.id, p_soft_down.id], cause="import", now=now)
    db.commit()
    assert db.get(PointState, p_soft_prereq.id).state == "locked"
    # p_soft_down 无硬依赖，即使软前置未解锁，自身也应为 available
    assert db.get(PointState, p_soft_down.id).state == "available"


def test_point_state_log_records_cause(db_session: Session, learn_env):  # noqa: F811
    """每次状态变化写 point_state_log，cause 正确记录。"""
    now = utcnow()
    db = db_session

    p = _create_point(db, "pt.log-audit")
    # 首次计算：None -> available
    recompute_points(db, [p.id], cause="import", cause_ref="v1.0", now=now)
    db.commit()

    log1 = db.scalar(select(PointStateLog).where(PointStateLog.point_id == p.id).order_by(PointStateLog.id.desc()))
    assert log1 is not None
    assert log1.from_state is None
    assert log1.to_state == "available"
    assert log1.cause == "import"
    assert log1.cause_ref == "v1.0"

    # 录入证据触发状态变化：available -> learned
    ev = Evidence(point_id=p.id, type="selftest", passed=True, reviewer="axue", observed_at=now)
    db.add(ev)
    db.commit()

    recompute_points(db, [p.id], cause="evidence", cause_ref=str(ev.id), now=now)
    db.commit()

    log2 = db.scalar(select(PointStateLog).where(PointStateLog.point_id == p.id).order_by(PointStateLog.id.desc()))
    assert log2 is not None
    assert log2.from_state == "available"
    assert log2.to_state == "learned"
    assert log2.cause == "evidence"
    assert log2.cause_ref == str(ev.id)
