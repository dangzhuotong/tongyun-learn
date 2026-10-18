"""知识地图导入（定稿 §2 POST /maps/import）：校验（复用 validate.py 逻辑）→ 按 id 增量 upsert → diff。

- 有任何 error 一律不写库；dry_run 也完整跑一遍再回滚，diff 与真导入一致。
- 永不物理删除：YAML 里删掉 = active=0；同 id 再出现 = 恢复启用。
- 示例卡建成真卡（created_by=example，payload.example_src="<point_id>|<front_key>"）；
  未改过的 example 卡跟 YAML 同步，YAML 删掉的停用；阿学改过的（created_by 已变 axue）不动。
- 幂等：同一份 YAML 重复导入，diff 全为 0。
- 每次导入（含预演）都在 map_imports 记一行审计（dry_run=1 表示预演，库里其它表不变）；
  预演时还没建学科行的新学科不记（外键）。
- 结果里带 open_at_start（文件里无硬前置的点数，即「开局可学」）和 points_by_state（导入后的状态分布）。
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from importlib import resources
from typing import Any

import jsonschema
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tongyun_learn.models import Card, Deck, MapImport, Point, PointPrereq, PointState, Stage, Subject
from tongyun_learn.services.cardkeys import front_key
from tongyun_learn.services.state import recompute_points
from tongyun_learn.timeutil import utcnow

CARD_TYPE_MAP = {"记忆卡": "memory", "理解卡": "understand", "动手卡": "handson", "表达卡": "express"}
EVIDENCE_MAP = {"自测": "selftest", "费曼": "feynman", "表达": "express", "动手": "handson"}

# 默认卡组配额（定稿 §1 decks 注释 + 决定 6）
DEFAULT_CAPS = {
    ("java-fde", "qa"): (60, 8, 3),
    ("tech-english", "en_word"): (150, 20, None),
    ("tech-english", "qa"): (30, 5, None),
}
FALLBACK_QA_CAPS = (60, 8, 3)
FALLBACK_WORD_CAPS = (150, 20, None)
DEFAULT_DICT_POINT_MAP = {"cet4": "en.vocab-general"}


def deck_name(subject_id: str, kind: str) -> str:
    return f"{subject_id}:{kind}"


def _schema() -> dict:
    text = resources.files("tongyun_learn.data").joinpath("knowledge-map.schema.json").read_text(encoding="utf-8")
    return json.loads(text)


@dataclass
class Parsed:
    idx: int
    doc: dict
    sha: str
    subject_id: str = ""
    prefix: str = ""


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _empty_result(subject_id: str, map_version: str | None) -> dict:
    return {
        "subject": subject_id,
        "map_version": map_version,
        "stages": {"added": 0, "updated": 0, "deactivated": 0},
        "points": {"added": 0, "updated": 0, "deactivated": 0, "reactivated": 0},
        "prereqs": {"added": 0, "removed": 0},
        "example_cards": {"created": 0, "updated": 0, "deactivated": 0, "kept_edited": 0},
        "open_at_start": 0,  # 文件里没有硬前置的知识点数（= validate.py 的「开局即可学」）
        "points_by_state": {},  # 导入（或预演）后该学科启用知识点的状态分布
    }


# ───────────────────────── 校验 ─────────────────────────


def parse_and_validate(db: Session, files: list[str]) -> tuple[list[Parsed], Report]:
    rep = Report()
    validator = jsonschema.Draft202012Validator(_schema())
    parsed: list[Parsed] = []
    for i, text in enumerate(files):
        name = f"files[{i}]"
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as e:
            rep.errors.append(f"{name}: YAML 解析失败：{e}")
            continue
        if not isinstance(doc, dict):
            rep.errors.append(f"{name}: 顶层必须是对象")
            continue
        errs = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
        for e in errs:
            loc = "/".join(str(p) for p in e.path) or "<root>"
            rep.errors.append(f"{name}: Schema @ {loc}: {e.message}")
        if errs:
            continue
        subj = doc["subject"]
        parsed.append(Parsed(i, doc, hashlib.sha256(text.encode("utf-8")).hexdigest(), subj["id"], subj["prefix"]))
    if rep.errors:
        return parsed, rep

    seen_subjects: dict[str, int] = {}
    nodes: dict[str, tuple[str, str]] = {}  # id -> (subject_id, kind)
    points: dict[str, dict] = {}
    point_stage: dict[str, tuple[str, int]] = {}
    for f in parsed:
        name = f"files[{f.idx}]({f.subject_id})"
        if f.subject_id in seen_subjects:
            rep.errors.append(f"{name}: 学科 {f.subject_id} 在本次请求里重复出现")
        seen_subjects[f.subject_id] = f.idx
        stages = f.doc["stages"]
        orders = [s["order"] for s in stages]
        if sorted(orders) != list(range(1, len(stages) + 1)):
            rep.errors.append(f"{name}: stage.order 应为 1..{len(stages)} 且不重复，实际 {orders}")
        for s in stages:
            for nid, kind in [(s["id"], "stage")] + [(p["id"], "point") for p in s["points"]]:
                if not nid.startswith(f.prefix + "."):
                    rep.errors.append(f"{name}: {kind} id {nid} 前缀应为 {f.prefix}.")
                if nid in nodes:
                    rep.errors.append(f"{name}: id {nid} 重复")
                nodes[nid] = (f.subject_id, kind)
            for p in s["points"]:
                points[p["id"]] = p
                point_stage[p["id"]] = (f.subject_id, s["order"])
                ctypes = set(p["card_types"])
                for j, c in enumerate(p["example_cards"]):
                    if c["type"] not in ctypes:
                        rep.errors.append(f"{name}: {p['id']} 示例卡 #{j + 1} 类型 {c['type']} 不在 card_types 中")

    # 与库里已有数据的冲突：id 永不复用、前缀唯一
    file_subjects = set(seen_subjects)
    for f in parsed:
        other = db.scalar(select(Subject).where(Subject.prefix == f.prefix, Subject.id != f.subject_id))
        if other is not None:
            rep.errors.append(f"学科 {f.subject_id}: 前缀 {f.prefix} 已被学科 {other.id} 使用")
        existing = db.get(Subject, f.subject_id)
        if existing is not None and existing.prefix != f.prefix:
            rep.errors.append(f"学科 {f.subject_id}: 前缀不能从 {existing.prefix} 改成 {f.prefix}")
    if nodes:
        ids = list(nodes)
        for st in db.scalars(select(Stage).where(Stage.id.in_(ids))):
            subj, kind = nodes[st.id]
            if kind != "stage":
                rep.errors.append(f"id {st.id} 在库里是阶段，不能改成知识点")
            elif st.subject_id != subj:
                rep.errors.append(f"阶段 {st.id} 已属于学科 {st.subject_id}")
        for pt in db.scalars(select(Point).where(Point.id.in_(ids))):
            subj, kind = nodes[pt.id]
            if kind != "point":
                rep.errors.append(f"id {pt.id} 在库里是知识点，不能改成阶段")
            elif pt.subject_id != subj:
                rep.errors.append(f"知识点 {pt.id} 已属于学科 {pt.subject_id}")

    # 前置：本次文件里的点，或库里其他学科的点（跨学科前置）
    db_points = {pt.id: pt for pt in db.scalars(select(Point).where(Point.subject_id.not_in(file_subjects or {""})))}
    db_stage_ids = set(db.scalars(select(Stage.id)).all())
    graph: dict[str, list[str]] = {}
    for pid, p in points.items():
        graph[pid] = []
        seen: set[str] = set()
        for pr in p["prerequisites"]:
            rid = pr["id"]
            if rid in seen:
                rep.errors.append(f"{pid}: 前置 {rid} 重复")
            seen.add(rid)
            if rid == pid:
                rep.errors.append(f"{pid}: 不能以自己为前置")
                continue
            if rid in points:
                graph[pid].append(rid)
                if pr["kind"] == "hard":
                    a, b = point_stage[pid], point_stage[rid]
                    if a[0] == b[0] and b[1] > a[1]:
                        rep.warnings.append(f"{pid}: 硬前置 {rid} 在更靠后的阶段（阶段 {b[1]} > {a[1]}）")
            elif rid in db_points:
                graph[pid].append(rid)
                if not db_points[rid].active:
                    rep.warnings.append(f"{pid}: 前置 {rid} 已停用（视为已满足）")
                else:
                    rep.warnings.append(f"{pid}: 前置 {rid} 不在本次文件里，使用库里已有的知识点")
            else:
                where = "是阶段 id，前置只能指向知识点" if (rid in nodes or rid in db_stage_ids) else "不存在"
                rep.errors.append(f"{pid}: 前置 {rid} {where}")
    # 库里其他学科的边也要参与环检测
    for pp in db.scalars(select(PointPrereq).where(PointPrereq.point_id.in_(list(db_points) or [""]))):
        graph.setdefault(pp.point_id, []).append(pp.prereq_id)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    for start in list(graph):
        if color.get(start, WHITE) != WHITE:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        path: list[str] = []
        while stack:
            u, i = stack.pop()
            if i == 0:
                color[u] = GRAY
                path.append(u)
            nbrs = graph.get(u, [])
            if i < len(nbrs):
                stack.append((u, i + 1))
                v = nbrs[i]
                c = color.get(v, WHITE)
                if c == GRAY:
                    cyc = path[path.index(v) :] + [v]
                    rep.errors.append("前置成环：" + " -> ".join(cyc))
                elif c == WHITE:
                    stack.append((v, 0))
            else:
                color[u] = BLACK
                path.pop()
    return parsed, rep


# ───────────────────────── 写库 ─────────────────────────


def _set(obj: Any, attrs: dict[str, Any]) -> bool:
    changed = False
    for k, v in attrs.items():
        cur = getattr(obj, k)
        if isinstance(v, Decimal) and cur is not None:
            same = Decimal(str(cur)) == v
        else:
            same = cur == v
        if not same:
            setattr(obj, k, v)
            changed = True
    return changed


def ensure_decks(db: Session, subject_id: str, has_vocab: bool) -> dict[str, Deck]:
    out: dict[str, Deck] = {}
    kinds = ["qa"] + (["en_word"] if has_vocab else [])
    for kind in kinds:
        name = deck_name(subject_id, kind)
        d = db.scalar(select(Deck).where(Deck.subject_id == subject_id, Deck.kind == kind, Deck.name == name))
        if d is None:
            fallback = FALLBACK_WORD_CAPS if kind == "en_word" else FALLBACK_QA_CAPS
            rc, nc, nd = DEFAULT_CAPS.get((subject_id, kind), fallback)
            meta = {"dict_point_map": dict(DEFAULT_DICT_POINT_MAP), "default_point": "en.vocab-general"}
            d = Deck(
                subject_id=subject_id,
                kind=kind,
                name=name,
                source="map",
                review_cap=rc,
                new_cap=nc,
                new_cap_deep=nd,
                meta=meta if kind == "en_word" else None,
            )
            db.add(d)
            db.flush()
        out[kind] = d
    return out


def _apply(db: Session, parsed: list[Parsed], rep: Report, now: datetime) -> list[dict]:
    results = {f.subject_id: _empty_result(f.subject_id, f.doc["map_version"]) for f in parsed}
    yaml_points: dict[str, tuple[Parsed, dict]] = {}

    # 1) 学科、阶段、知识点（先全部 upsert，跨学科前置的 FK 才不会挂）
    for f in parsed:
        res = results[f.subject_id]
        sd = f.doc["subject"]
        subj = db.get(Subject, f.subject_id)
        attrs = {
            "prefix": f.prefix,
            "title": sd["title"],
            "goal": sd["goal"],
            "description": sd.get("description"),
            "axue_area": sd.get("axue_area"),
            "map_version": f.doc["map_version"],
            "active": True,
        }
        if subj is None:
            subj = Subject(id=f.subject_id, **attrs)
            db.add(subj)
        else:
            _set(subj, attrs)
        db.flush()

        stage_ids = set()
        for s in f.doc["stages"]:
            stage_ids.add(s["id"])
            attrs = {
                "subject_id": f.subject_id,
                "ord": s["order"],
                "title": s["title"],
                "weeks": s.get("weeks"),
                "goal": s.get("goal"),
                "deliverable": s.get("deliverable"),
                "exit_criteria": s.get("exit_criteria"),
                "active": True,
            }
            st = db.get(Stage, s["id"])
            if st is None:
                db.add(Stage(id=s["id"], **attrs))
                res["stages"]["added"] += 1
            elif _set(st, attrs):
                res["stages"]["updated"] += 1
        db.flush()
        for st in db.scalars(select(Stage).where(Stage.subject_id == f.subject_id, Stage.active.is_(True))):
            if st.id not in stage_ids:
                st.active = False
                res["stages"]["deactivated"] += 1

        ord_ = 0
        file_point_ids = set()
        for s in f.doc["stages"]:
            for p in s["points"]:
                ord_ += 1
                file_point_ids.add(p["id"])
                yaml_points[p["id"]] = (f, p)
                attrs = {
                    "subject_id": f.subject_id,
                    "stage_id": s["id"],
                    "ord": ord_,
                    "title": p["title"],
                    "description": p["description"],
                    "card_types": [CARD_TYPE_MAP[t] for t in p["card_types"]],
                    "effort_hours": Decimal(str(p["effort_hours"])).quantize(Decimal("0.1")),
                    "interview_weight": p["interview_weight"],
                    "mastery_evidence": [EVIDENCE_MAP[t] for t in p["mastery_evidence"]],
                    "tags": list(p.get("tags") or []),
                    "sources": list(p.get("sources") or []),
                    "example_cards": [
                        {"type": CARD_TYPE_MAP[c["type"]], "front": c["front"], "back": c["back"]}
                        for c in p["example_cards"]
                    ],
                }
                pt = db.get(Point, p["id"])
                if pt is None:
                    db.add(Point(id=p["id"], active=True, **attrs))
                    res["points"]["added"] += 1
                else:
                    reactivated = not pt.active
                    if reactivated:
                        pt.active = True
                        pt.deactivated_at = None
                        res["points"]["reactivated"] += 1
                    if _set(pt, attrs) and not reactivated:
                        res["points"]["updated"] += 1
        db.flush()
        for pt in db.scalars(select(Point).where(Point.subject_id == f.subject_id, Point.active.is_(True))):
            if pt.id not in file_point_ids:
                pt.active = False
                pt.deactivated_at = now
                res["points"]["deactivated"] += 1
        db.flush()

    # 2) 前置边
    for pid, (f, p) in yaml_points.items():
        res = results[f.subject_id]
        want = {pr["id"]: pr["kind"] for pr in p["prerequisites"]}
        have = {pp.prereq_id: pp for pp in db.scalars(select(PointPrereq).where(PointPrereq.point_id == pid))}
        for rid, pp in have.items():
            if rid not in want:
                db.delete(pp)
                res["prereqs"]["removed"] += 1
            elif pp.kind != want[rid]:
                pp.kind = want[rid]
                res["prereqs"]["removed"] += 1
                res["prereqs"]["added"] += 1
        for rid, kind in want.items():
            if rid not in have:
                db.add(PointPrereq(point_id=pid, prereq_id=rid, kind=kind))
                res["prereqs"]["added"] += 1
    db.flush()

    # 3) 卡组 + 示例卡
    for f in parsed:
        res = results[f.subject_id]
        subj_points = [(pid, p) for pid, (ff, p) in yaml_points.items() if ff is f]
        has_vocab = any("en_word" in (p.get("tags") or []) for _pid, p in subj_points)
        decks = ensure_decks(db, f.subject_id, has_vocab)
        deck_ids = [d.id for d in db.scalars(select(Deck).where(Deck.subject_id == f.subject_id))]
        by_src: dict[str, Card] = {}
        example_cards: list[Card] = []
        for c in db.scalars(select(Card).where(Card.deck_id.in_(deck_ids), Card.created_by.in_(("example", "axue")))):
            src = (c.payload or {}).get("example_src") if isinstance(c.payload, dict) else None
            if src:
                by_src[src] = c
            if c.created_by == "example":
                example_cards.append(c)
        wanted: set[str] = set()
        for pid, p in subj_points:
            deck = decks["en_word"] if "en_word" in (p.get("tags") or []) else decks["qa"]
            for c in p["example_cards"]:
                fk = front_key(c["front"])
                src = f"{pid}|{fk}"
                if src in wanted:
                    rep.warnings.append(f"{pid}: 示例卡「{c['front'][:30]}」重复，只建一张")
                    continue
                wanted.add(src)
                ctype = CARD_TYPE_MAP[c["type"]]
                card = by_src.get(src)
                if card is None:
                    clash = db.scalar(select(Card).where(Card.deck_id == deck.id, Card.front_key == fk))
                    if clash is not None:
                        rep.warnings.append(
                            f"{pid}: 示例卡「{c['front'][:30]}」与卡组里已有的卡 {clash.id} 同名，保留已有卡"
                        )
                        res["example_cards"]["kept_edited"] += 1
                        continue
                    db.add(
                        Card(
                            deck_id=deck.id,
                            point_id=pid,
                            card_type=ctype,
                            front=c["front"],
                            front_key=fk,
                            back=c["back"],
                            payload={"example_src": src},
                            created_by="example",
                            active=True,
                        )
                    )
                    db.flush()
                    res["example_cards"]["created"] += 1
                elif card.created_by != "example":
                    res["example_cards"]["kept_edited"] += 1
                else:
                    if _set(
                        card,
                        {
                            "deck_id": deck.id,
                            "point_id": pid,
                            "card_type": ctype,
                            "front": c["front"],
                            "back": c["back"],
                            "active": True,
                        },
                    ):
                        res["example_cards"]["updated"] += 1
        for c in example_cards:
            src = (c.payload or {}).get("example_src")
            if c.active and src not in wanted:
                c.active = False
                res["example_cards"]["deactivated"] += 1
    db.flush()

    # 4) 重算受影响学科的全部点（含停用点，用来连锁解锁下游），按硬前置拓扑序
    subject_ids = [f.subject_id for f in parsed]
    all_ids = list(db.scalars(select(Point.id).where(Point.subject_id.in_(subject_ids)).order_by(Point.ord)).all())
    recompute_points(db, _topo(db, all_ids), cause="import", now=now)
    db.flush()

    # 5) 「开局可学」数 + 导入后状态分布（预演时也是导入后的样子，回滚前算好）
    for f in parsed:
        res = results[f.subject_id]
        subj_points = [p for _pid, (ff, p) in yaml_points.items() if ff is f]
        res["open_at_start"] = sum(
            1 for p in subj_points if not any(pr["kind"] == "hard" for pr in p["prerequisites"])
        )
        rows = db.execute(
            select(PointState.state, func.count())
            .join(Point, Point.id == PointState.point_id)
            .where(Point.subject_id == f.subject_id, Point.active.is_(True))
            .group_by(PointState.state)
        ).all()
        res["points_by_state"] = {st: int(n) for st, n in sorted(rows)}
    return [results[f.subject_id] for f in parsed]


def _topo(db: Session, ids: list[str]) -> list[str]:
    idset = set(ids)
    deps: dict[str, set[str]] = {i: set() for i in ids}
    for pp in db.scalars(select(PointPrereq).where(PointPrereq.point_id.in_(ids), PointPrereq.kind == "hard")):
        if pp.prereq_id in idset:
            deps[pp.point_id].add(pp.prereq_id)
    out: list[str] = []
    done: set[str] = set()
    remaining = list(ids)
    while remaining:
        progress = [i for i in remaining if deps[i] <= done]
        if not progress:  # 有环时兜底（校验已拦）
            progress = remaining
        for i in progress:
            out.append(i)
            done.add(i)
        remaining = [i for i in remaining if i not in done]
    return out


def import_maps(db: Session, files: list[str], dry_run: bool) -> dict:
    now = utcnow()
    parsed, rep = parse_and_validate(db, files)
    if rep.errors:
        db.rollback()
        return {"dry_run": dry_run, "results": [], "errors": rep.errors, "warnings": rep.warnings}
    results = _apply(db, parsed, rep, now)
    if dry_run:
        db.rollback()
    for f, res in zip(parsed, results, strict=True):
        if db.get(Subject, f.subject_id) is not None:  # dry_run 的新学科没有学科行，不记
            db.add(
                MapImport(
                    subject_id=f.subject_id,
                    map_version=f.doc["map_version"],
                    file_sha256=f.sha,
                    dry_run=dry_run,
                    diff=res,
                    created_at=now,
                )
            )
    db.commit()
    return {"dry_run": dry_run, "results": results, "errors": [], "warnings": rep.warnings}
