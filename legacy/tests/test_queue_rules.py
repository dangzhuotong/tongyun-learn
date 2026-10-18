"""每日队列配额与排序测试（PRD §4 + 决定 4/6）。

覆盖：
1. 默认配额（java-fde/qa 60/8/3，tech-english/en_word 150/20，tech-english/qa 30/5）
2. 新卡配额（new_cap、new_cap_deep）、未解锁点卡不进队列、停用卡不进
3. 新开点限额（每学科每天 ≤2，所有学科合计 ≤3，今天已开点占名额）
4. 到期总数阻断（> 2*review_cap 阻断新卡）、已复习截断与逾期程度降序
5. web 令牌看不到 handson 动手卡
6. GET /v1/next 规则（recheck 列出全部不受 limit 限制，next 按 learning/available 优先级及四元组排序）
"""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.learn_helpers import AXUE, WEB, learn_env, map_texts  # noqa: F401, F811
from tongyun_learn.models import (
    Card,
    CardState,
    Deck,
    Point,
    PointPrereq,
    PointState,
    Stage,
    Subject,
)
from tongyun_learn.services.cardkeys import front_key
from tongyun_learn.services.importer import import_maps
from tongyun_learn.services.queue import build_queue, next_points
from tongyun_learn.timeutil import utcnow


def _get_or_create_subject(db: Session, subject_id: str = "subj-q") -> Subject:
    s = db.get(Subject, subject_id)
    if not s:
        s = Subject(id=subject_id, prefix=subject_id[:10], title=subject_id, active=True)
        db.add(s)
        db.flush()
    return s


def _get_or_create_stage(
    db: Session, stage_id: str = "st-q", subject_id: str = "subj-q", ord: int = 1
) -> Stage:
    _get_or_create_subject(db, subject_id)
    st = db.get(Stage, stage_id)
    if not st:
        st = Stage(id=stage_id, subject_id=subject_id, ord=ord, title=stage_id, active=True)
        db.add(st)
        db.flush()
    return st


def _create_deck(
    db: Session,
    subject_id: str,
    kind: str,
    review_cap: int = 60,
    new_cap: int = 8,
    new_cap_deep: int | None = 3,
) -> Deck:
    _get_or_create_subject(db, subject_id)
    name = f"{subject_id}:{kind}"
    d = db.scalar(select(Deck).where(Deck.subject_id == subject_id, Deck.kind == kind, Deck.name == name))
    if not d:
        d = Deck(
            subject_id=subject_id,
            kind=kind,
            name=name,
            review_cap=review_cap,
            new_cap=new_cap,
            new_cap_deep=new_cap_deep,
        )
        db.add(d)
        db.flush()
    return d


def _create_point_with_state(
    db: Session,
    point_id: str,
    subject_id: str = "subj-q",
    stage_id: str = "st-q",
    state: str = "available",
    interview_weight: int = 1,
    ord: int = 1,
    needs_recheck: bool = False,
) -> Point:
    _get_or_create_stage(db, stage_id, subject_id)
    p = db.get(Point, point_id)
    if not p:
        p = Point(
            id=point_id,
            subject_id=subject_id,
            stage_id=stage_id,
            ord=ord,
            title=point_id,
            interview_weight=interview_weight,
            active=True,
        )
        db.add(p)
        db.flush()
    ps = db.get(PointState, point_id)
    if not ps:
        ps = PointState(
            point_id=point_id,
            state=state,
            since=utcnow(),
            ever_mastered=False,
            needs_recheck=needs_recheck,
        )
        db.add(ps)
        db.flush()
    else:
        ps.state = state
        ps.needs_recheck = needs_recheck
        db.flush()
    return p


def _create_card_for_deck(
    db: Session,
    deck: Deck,
    point_id: str | None = None,
    card_type: str = "understand",
    front: str = "front",
    active: bool = True,
    due_delta_days: float | None = None,
    stability: float = 10.0,
    reviewed_today: bool = False,
    first_review_today: bool = False,
) -> tuple[Card, CardState | None]:
    fk = front_key(front)
    c = Card(
        deck_id=deck.id,
        point_id=point_id,
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
    now = utcnow()
    if due_delta_days is not None or reviewed_today or first_review_today:
        fr = now if first_review_today else now - timedelta(days=10)
        lr = now if reviewed_today else now - timedelta(days=5)
        due_time = now + timedelta(days=due_delta_days) if due_delta_days is not None else now - timedelta(days=1)
        cs = CardState(
            card_id=c.id,
            state=2,  # review state
            stability=stability,
            difficulty=0.3,
            reps=2,
            lapses=0,
            first_review=fr,
            last_review=lr,
            last_rating=3,
            due=due_time,
        )
        db.add(cs)
        db.flush()
    return c, cs


def test_default_deck_caps_from_import(db_session: Session, learn_env):  # noqa: F811
    """默认配额：
    - java-fde/qa 60/8/3
    - tech-english/en_word 150/20 (deep=None)
    - tech-english/qa 30/5 (deep=None)
    """
    db = db_session
    res = import_maps(db, map_texts(), dry_run=False)
    assert res["errors"] == []

    decks = db.scalars(select(Deck)).all()
    deck_map = {(d.subject_id, d.kind): d for d in decks}

    # 1) java-fde qa 卡组
    d_jf_qa = deck_map.get(("java-fde", "qa"))
    assert d_jf_qa is not None
    assert (d_jf_qa.review_cap, d_jf_qa.new_cap, d_jf_qa.new_cap_deep) == (60, 8, 3)

    # 2) tech-english en_word 卡组
    d_te_word = deck_map.get(("tech-english", "en_word"))
    assert d_te_word is not None
    assert (d_te_word.review_cap, d_te_word.new_cap, d_te_word.new_cap_deep) == (150, 20, None)

    # 3) tech-english qa 卡组
    d_te_qa = deck_map.get(("tech-english", "qa"))
    assert d_te_qa is not None
    assert (d_te_qa.review_cap, d_te_qa.new_cap, d_te_qa.new_cap_deep) == (30, 5, None)


def test_new_cards_caps_and_filtering(db_session: Session, learn_env):  # noqa: F811
    """新卡过滤与配额：
    - 每卡组 ≤ new_cap，其中 understand+express ≤ new_cap_deep
    - locked 点的卡（含 example 示例卡）不进队列
    - 停用卡（active=False）不进队列
    """
    now = utcnow()
    db = db_session

    deck = _create_deck(db, "s-cap", "qa", review_cap=50, new_cap=5, new_cap_deep=2)

    # 1) 可学点上的卡
    p_open = _create_point_with_state(db, "pt.open", subject_id="s-cap", state="available")
    # 4 张深度卡（3 张 understand，1 张 express）
    for i in range(3):
        _create_card_for_deck(db, deck, point_id=p_open.id, card_type="understand", front=f"und_{i}")
    _create_card_for_deck(db, deck, point_id=p_open.id, card_type="express", front="exp_0")
    # 5 张记忆卡
    for i in range(5):
        _create_card_for_deck(db, deck, point_id=p_open.id, card_type="memory", front=f"mem_{i}")
    # 2 张停用卡（不应出现）
    for i in range(2):
        _create_card_for_deck(db, deck, point_id=p_open.id, card_type="memory", front=f"deact_{i}", active=False)

    # 2) 未解锁点上的卡（不应出现）
    p_locked = _create_point_with_state(db, "pt.locked", subject_id="s-cap", state="locked")
    for i in range(3):
        _create_card_for_deck(db, deck, point_id=p_locked.id, card_type="understand", front=f"lock_{i}")

    db.commit()

    q = build_queue(db, deck_id=deck.id, limit=50, principal="axue", now=now)
    new_cards = q["new"]

    # 校验卡片总量不超过 new_cap=5
    assert len(new_cards) <= 5
    # 校验深度卡（understand + express）不超过 new_cap_deep=2
    deep_cards = [c for c in new_cards if c["card_type"] in ("understand", "express")]
    assert len(deep_cards) <= 2

    # 校验未解锁点的卡和停用卡均未进入
    point_ids_in_queue = {c["point_id"] for c in new_cards}
    assert p_locked.id not in point_ids_in_queue
    fronts_in_queue = {c["front"] for c in new_cards}
    assert "deact_0" not in fronts_in_queue and "deact_1" not in fronts_in_queue


def test_points_opening_daily_limits(db_session: Session, learn_env):  # noqa: F811
    """新开点限额：
    - 每学科每天 ≤ 2，所有学科合计 ≤ 3
    - 今天已经开过（first_review 在今天）的点要占名额
    """
    now = utcnow()
    db = db_session

    deck1 = _create_deck(db, "subj-1", "qa", review_cap=50, new_cap=20, new_cap_deep=10)
    deck2 = _create_deck(db, "subj-2", "qa", review_cap=50, new_cap=20, new_cap_deep=10)

    # subj-1: 3 个可学新点，各有一批新卡
    p1 = _create_point_with_state(db, "s1.p1", subject_id="subj-1", state="available", ord=1)
    p2 = _create_point_with_state(db, "s1.p2", subject_id="subj-1", state="available", ord=2)
    p3 = _create_point_with_state(db, "s1.p3", subject_id="subj-1", state="available", ord=3)
    _create_card_for_deck(db, deck1, point_id=p1.id, front="c_s1_p1")
    _create_card_for_deck(db, deck1, point_id=p2.id, front="c_s1_p2")
    _create_card_for_deck(db, deck1, point_id=p3.id, front="c_s1_p3")

    # subj-2: 3 个可学新点，各有一批新卡
    p4 = _create_point_with_state(db, "s2.p4", subject_id="subj-2", state="available", ord=1)
    p5 = _create_point_with_state(db, "s2.p5", subject_id="subj-2", state="available", ord=2)
    p6 = _create_point_with_state(db, "s2.p6", subject_id="subj-2", state="available", ord=3)
    _create_card_for_deck(db, deck2, point_id=p4.id, front="c_s2_p4")
    _create_card_for_deck(db, deck2, point_id=p5.id, front="c_s2_p5")
    _create_card_for_deck(db, deck2, point_id=p6.id, front="c_s2_p6")

    db.commit()

    # 1) 全局限额测试：两个学科共 6 个点，由于每学科 ≤2 且全局 ≤3，全局开出新点数必须 ≤ 3
    q = build_queue(db, limit=50, principal="axue", now=now)
    opening = q["counts"]["points_opening"]
    # 按学科轮流取、先到先占：subj-1 → subj-2 → subj-1，正好 3 个
    assert opening == ["s1.p1", "s2.p4", "s1.p2"]
    assert {c["point_id"] for c in q["new"]} == set(opening)

    # 2) 今天已开过点占名额：给 subj-1 的一个点 p_today 插一张 today first_review 卡
    p_today = _create_point_with_state(db, "s1.today", subject_id="subj-1", state="learning", ord=0)
    _create_card_for_deck(
        db, deck1, point_id=p_today.id, front="c_s1_today", first_review_today=True, stability=10.0
    )
    db.commit()

    q2 = build_queue(db, subject="subj-1", limit=50, principal="axue", now=now)
    # 今天已开点占 1 个名额，因此今日 subj-1 新开放的新点至多还剩 2 - 1 = 1 个
    assert q2["counts"]["points_opened_today"] == 1
    assert q2["counts"]["points_opening"] == ["s1.p1"]


def test_overdue_blocking_and_review_truncation_sorting(db_session: Session, learn_env):  # noqa: F811
    """到期阻断与复习截断/排序：
    - 到期总数 > 2*review_cap → 该卡组今天不出新卡（counts.new_blocked 计数）
    - 边界：<= 2*review_cap 不阻断
    - 复习数截到 review_cap − 今天已复习数
    - 按逾期程度 (now−due)/stability 降序
    """
    now = utcnow()
    db = db_session

    deck = _create_deck(db, "s-block", "qa", review_cap=5, new_cap=4, new_cap_deep=2)
    p_avail = _create_point_with_state(db, "pt.block-open", subject_id="s-block", state="available")

    # 1) 边界阻断：review_cap=5，2*review_cap=10。造 11 张到期卡 (> 10)
    cards_overdue = []
    for i in range(11):
        # stability 差异化以便测试排序：
        # c0: 逾期 1 天 / 稳定度 10 = 0.1
        # c1: 逾期 5 天 / 稳定度 2 = 2.5
        # c2: 逾期 2 天 / 稳定度 1 = 2.0
        # 其他：逾期 1 天 / 稳定度 5 = 0.2
        if i == 0:
            stab, delta = 10.0, -1.0
        elif i == 1:
            stab, delta = 2.0, -5.0
        elif i == 2:
            stab, delta = 1.0, -2.0
        else:
            stab, delta = 5.0, -1.0
        c, _ = _create_card_for_deck(
            db, deck, point_id=p_avail.id, front=f"od_{i}", due_delta_days=delta, stability=stab
        )
        cards_overdue.append(c)

    # 准备 2 张新卡
    _create_card_for_deck(db, deck, point_id=p_avail.id, front="new_1")
    _create_card_for_deck(db, deck, point_id=p_avail.id, front="new_2")
    db.commit()

    q_blocked = build_queue(db, deck_id=deck.id, limit=50, principal="axue", now=now)
    assert q_blocked["counts"]["due_total"] == 11
    assert q_blocked["counts"]["new_blocked"] == 1
    # 阻断时不出新卡
    assert len(q_blocked["new"]) == 0
    # 截取到 review_cap = 5
    assert len(q_blocked["review"]) == 5

    # 检查逾期程度降序：
    # 第一应为 c1 (2.5)，第二应为 c2 (2.0)
    assert q_blocked["review"][0]["front"] == "od_1"
    assert q_blocked["review"][1]["front"] == "od_2"

    # 2) 边界未阻断：删掉 1 张到期卡，使得到期数 = 10 (恰好等于 2*review_cap)
    card_to_drop = cards_overdue.pop()
    card_to_drop.active = False  # 停卡（服务从不物理删卡；停用卡不进队列）
    db.commit()

    q_unblocked = build_queue(db, deck_id=deck.id, limit=50, principal="axue", now=now)
    assert q_unblocked["counts"]["due_total"] == 10
    assert q_unblocked["counts"]["new_blocked"] == 0
    # 不阻断，能正常出新卡
    assert len(q_unblocked["new"]) > 0

    # 3) 复习数截断：review_cap=5，今天已复习 2 张，复习队列应只出 5 - 2 = 3 张
    _create_card_for_deck(db, deck, point_id=p_avail.id, front="rev_today_1", reviewed_today=True)
    _create_card_for_deck(db, deck, point_id=p_avail.id, front="rev_today_2", reviewed_today=True)
    db.commit()

    q_trunc = build_queue(db, deck_id=deck.id, limit=50, principal="axue", now=now)
    assert len(q_trunc["review"]) == 3


def test_web_token_hides_handson_cards(client: TestClient, db_session: Session, learn_env):  # noqa: F811
    """web 令牌看不到 handson 动手卡（GET /v1/review/due 用 WEB 头）。"""
    db = db_session

    deck = _create_deck(db, "s-hand", "qa", review_cap=50, new_cap=10)
    p = _create_point_with_state(db, "pt.hand", subject_id="s-hand", state="available")

    # 1 张普通理解新卡，1 张动手新卡
    _create_card_for_deck(db, deck, point_id=p.id, card_type="understand", front="c_und")
    _create_card_for_deck(db, deck, point_id=p.id, card_type="handson", front="c_hand_new")

    # 1 张普通复习卡，1 张动手复习卡
    _create_card_for_deck(db, deck, point_id=p.id, card_type="understand", front="c_und_rev", due_delta_days=-1.0)
    _create_card_for_deck(db, deck, point_id=p.id, card_type="handson", front="c_hand_rev", due_delta_days=-1.0)
    db.commit()

    # 1) WEB 请求：看不到任何 handson 卡
    r_web = client.get(f"/v1/review/due?deck={deck.id}&limit=50", headers=WEB)
    assert r_web.status_code == 200
    data_web = r_web.json()
    all_web_cards = data_web["review"] + data_web["new"]
    assert all(c["card_type"] != "handson" for c in all_web_cards)

    # 2) AXUE 请求：可以看到 handson 卡
    r_axue = client.get(f"/v1/review/due?deck={deck.id}&limit=50", headers=AXUE)
    assert r_axue.status_code == 200
    data_axue = r_axue.json()
    all_axue_cards = data_axue["review"] + data_axue["new"]
    assert any(c["card_type"] == "handson" for c in all_axue_cards)


def test_get_next_points_recheck_and_ordering(client: TestClient, db_session: Session, learn_env):  # noqa: F811
    """GET /v1/next：
    - recheck 列出全部 needs_recheck 点（不受 limit 限制）
    - next 先学习中、再可学
    - 可学按（阶段 ord↑、interview_weight↓、未满足软前置数↑、文件 ord↑）
    """
    now = utcnow()
    db = db_session

    st1 = _get_or_create_stage(db, "st-1", "subj-next", ord=1)
    st2 = _get_or_create_stage(db, "st-2", "subj-next", ord=2)

    # 1) 4 个待复查点（needs_recheck=True）
    for i in range(4):
        _create_point_with_state(
            db, f"pt.recheck_{i}", subject_id="subj-next", stage_id=st1.id, state="mastered", needs_recheck=True
        )

    # 2) 候选点集合：
    # p_learning: 学习中（优先级最高）
    p_learning = _create_point_with_state(
        db, "pt.learning", subject_id="subj-next", stage_id=st1.id, state="learning", ord=10
    )

    # p_s1_w3: 阶段 1，权重 3
    p_s1_w3 = _create_point_with_state(
        db, "pt.s1_w3", subject_id="subj-next", stage_id=st1.id, state="available", interview_weight=3, ord=1
    )

    # p_s1_w1_nosoft: 阶段 1，权重 1，未满足软前置 0
    p_s1_w1_nosoft = _create_point_with_state(
        db, "pt.s1_w1_nosoft", subject_id="subj-next", stage_id=st1.id, state="available", interview_weight=1, ord=2
    )

    # p_s1_w1_soft: 阶段 1，权重 1，未满足软前置 1
    p_soft_pre = _create_point_with_state(
        db, "pt.soft_pre", subject_id="subj-next", stage_id=st1.id, state="locked", ord=99
    )
    p_s1_w1_soft = _create_point_with_state(
        db, "pt.s1_w1_soft", subject_id="subj-next", stage_id=st1.id, state="available", interview_weight=1, ord=1
    )
    db.add(PointPrereq(point_id=p_s1_w1_soft.id, prereq_id=p_soft_pre.id, kind="soft"))

    # p_s2_w3: 阶段 2，权重 3
    p_s2_w3 = _create_point_with_state(
        db, "pt.s2_w3", subject_id="subj-next", stage_id=st2.id, state="available", interview_weight=3, ord=1
    )

    db.commit()

    # 请求 limit=2：recheck 应全部返回 4 个（不受 limit 限制），next 返回前 2 个
    res = client.get("/v1/next?subject=subj-next&limit=2", headers=AXUE).json()
    assert len(res["recheck"]) == 4

    # 期望的学科内顺序（_new_point_key）：
    # 1. p_learning (学习中排在可学之前)
    # 2. p_s1_w3 (阶段 1，权重 3 最高)
    # 3. p_s1_w1_nosoft (阶段 1，权重 1，未满足软前置为 0 < 1)
    # 4. p_s1_w1_soft (阶段 1，权重 1，未满足软前置为 1)
    # 5. p_s2_w3 (阶段 2)
    expected_order = [
        p_learning.id,
        p_s1_w3.id,
        p_s1_w1_nosoft.id,
        p_s1_w1_soft.id,
        p_s2_w3.id,
    ]
    from tongyun_learn.services import queue as queue_mod

    meta = queue_mod._point_meta(db)
    cand = [pid for pid in expected_order]
    assert sorted(cand, key=lambda pid: queue_mod._new_point_key(meta[pid])) == expected_order

    # /next 遵守新开点上限（每学科 ≤2）：这些点都还没出过卡，学习中的点也占名额（与 /review/due 一致）
    res_full = next_points(db, subject="subj-next", limit=10, now=now)
    next_list = res_full["next"]
    pids = [n["point_id"] for n in next_list]
    assert pids == expected_order[:2]
    assert all(n["opens_today"] for n in next_list)
    assert res_full["new_point_quota"]["by_subject_left"]["subj-next"] == 2
    assert {"stage_title", "effort_hours", "sources", "stage_id"} <= set(next_list[0])
