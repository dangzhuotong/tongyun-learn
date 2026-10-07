"""axue_learning → tongyun_learn 一次性迁移（定稿 P3b、决定 5；design-notes §6）。按 legacy_ref upsert，可重复跑。

    # 预演（默认）：完整跑一遍再回滚，打印报告；--report 另存 JSON
    python -m tongyun_learn.migrate_axue --source-url 'mysql+pymysql://...' [--report out.json]
    # 真迁移
    python -m tongyun_learn.migrate_axue --source-url 'mysql+pymysql://...' --commit --report out.json
    # 也可以先导出快照、再从快照迁（快照里没有密钥，可留档）
    python -m tongyun_learn.migrate_axue --source-url '...' --snapshot axue-snapshot.json
    python -m tongyun_learn.migrate_axue --source-json axue-snapshot.json [--commit]

源库只读（MySQL 上 SET SESSION TRANSACTION READ ONLY，只 SELECT 四张表）。目标库读 LEARN_DATABASE_URL。
--source-url 也可用环境变量 AXUE_SOURCE_URL 给，避免密码出现在命令行历史里。

映射：
- lessons：10 课映射到 jf.*（tongyun_learn/data/axue_lessons.json）；其余课有学习记录或卡点的建成
  misc.<code 小写>（学科 misc、阶段 misc.legacy），没记录的不迁。
- study_sessions → sessions（legacy_ref=axue:study_sessions:<id>，source=migrate），notes 里的康奈尔卡
  「线索/总结/卡点」拆进 cues/summary/stuck，原文留在 notes。
- self_test_score → selftest 证据（…:<id>:selftest）；notes 里「费曼:讲通/未讲通」→ feynman（…:feynman），
  「表达 6/8（结2原2例1坑1）」→ express（…:express，rubric 拆四维）。reviewer=migrate，达标按 §4 服务端规则。
- blockers → blockers（legacy_ref=axue:blockers:<id>），lesson_id 换成 point_id，未解决→open、已解决→resolved。
- skill_mastery、lessons.status 不迁，原值写进报告（迁移日志）备查；状态全部由新库数据重新推导。
- 已作废的行重跑不恢复。
源库 DATETIME 默认按北京时间理解（axue 命令行写库时 time_zone=+08:00），可用 --source-tz 改。
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import Decimal
from importlib.resources import files
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from tongyun_learn.models import Blocker, Evidence, Point, SessionPoint, Stage, StudySession, Subject
from tongyun_learn.services.importer import _topo
from tongyun_learn.services.state import recompute_points
from tongyun_learn.timeutil import iso_local, utcnow

MISC_SUBJECT = "misc"
MISC_STAGE = "misc.legacy"
STATUS_MAP = {"未解决": "open", "已解决": "resolved"}
CARD_KEYS = ("线索", "总结", "卡点")
FEYNMAN_RE = re.compile(r"费曼\s*[:：]\s*(讲通|未讲通|没讲通)")
EXPRESS_RE = re.compile(r"表达\s*[:：]?\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)")
_N = r"\s*(\d(?:\.\d)?)\s*"
# 「结2原2例1坑1」或「结论先行2 原理2 举例1 踩坑1」
RUBRIC_SHORT_RE = re.compile("结" + _N + "原" + _N + "例" + _N + "坑" + _N)
RUBRIC_LONG_RE = re.compile("结论先行" + _N + "原理" + _N + "举例" + _N + "踩坑" + _N)


def load_lesson_map() -> dict[str, dict]:
    doc = json.loads(files("tongyun_learn.data").joinpath("axue_lessons.json").read_text(encoding="utf-8"))
    return {row["code"]: row for row in doc["lessons"]}


def misc_point_id(code: str) -> str:
    return f"misc.{code.lower()}"


# ───────────────────────── notes 解析 ─────────────────────────


def parse_card(notes: str | None) -> dict[str, Any]:
    """康奈尔卡：「线索: a；b」「总结: …」「卡点: …」（全角/半角冒号都认）。"""
    card: dict[str, Any] = {}
    for line in (notes or "").splitlines():
        line = line.strip()
        for k in CARD_KEYS:
            if line.startswith((k + ":", k + "：")):
                card[k] = line[len(k) + 1 :].strip()
    if "线索" in card:
        card["cues"] = [x.strip() for x in card["线索"].replace(";", "；").split("；") if x.strip()]
    return card


def parse_feynman(notes: str | None) -> bool | None:
    m = FEYNMAN_RE.search(notes or "")
    return None if m is None else m.group(1) == "讲通"


def parse_express(notes: str | None) -> tuple[Decimal, Decimal, dict | None] | None:
    m = EXPRESS_RE.search(notes or "")
    if m is None:
        return None
    score, mx = Decimal(m.group(1)), Decimal(m.group(2))
    if mx <= 0 or score > mx:
        return None
    rest = (notes or "")[m.end() : m.end() + 80]
    r = RUBRIC_LONG_RE.search(rest) or RUBRIC_SHORT_RE.search(rest)
    rubric = None
    if r:
        rubric = dict(zip(("结论先行", "原理", "举例", "踩坑"), (float(x) for x in r.groups()), strict=True))
    return score, mx, rubric


# ───────────────────────── 源数据 ─────────────────────────


@dataclass
class Source:
    lessons: list[dict]
    sessions: list[dict]
    blockers: list[dict]
    skill_mastery: list[dict]


def _as_date(v: Any) -> date | None:
    if v is None or isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def _as_dt(v: Any) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v))


def read_source_db(url: str) -> Source:
    eng = create_engine(url, pool_pre_ping=True)
    try:
        with eng.connect() as c:
            if eng.dialect.name == "mysql":
                c.execute(text("SET SESSION TRANSACTION READ ONLY"))

            def rows(sql: str) -> list[dict]:
                return [dict(r._mapping) for r in c.execute(text(sql))]

            return Source(
                lessons=rows(
                    "SELECT id, code, week, day, area, title, file_path, status, sort_order, active FROM lessons"
                ),
                sessions=rows(
                    "SELECT id, lesson_id, study_date, minutes, self_test_score, self_test_total, notes, created_at "
                    "FROM study_sessions ORDER BY id"
                ),
                blockers=rows(
                    "SELECT id, lesson_id, session_id, area, description, status, created_at, resolved_at "
                    "FROM blockers ORDER BY id"
                ),
                skill_mastery=rows("SELECT area, level, note, updated_at FROM skill_mastery ORDER BY area"),
            )
    finally:
        eng.dispose()


def read_source_json(path: str) -> Source:
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return Source(
        lessons=doc.get("lessons", []),
        sessions=doc.get("study_sessions", []),
        blockers=doc.get("blockers", []),
        skill_mastery=doc.get("skill_mastery", []),
    )


def _jsonable(o: Any) -> Any:
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError(type(o).__name__)


def _as_text(v: Any) -> Any:
    """报告用：datetime/Decimal 转成 JSON 友好的值；快照 JSON 里读回来的已是字符串，原样返回。"""
    if v is None or isinstance(v, (str, int, float)):
        return v
    return _jsonable(v)


def write_snapshot(src: Source, path: str) -> None:
    doc = {
        "lessons": src.lessons,
        "study_sessions": src.sessions,
        "blockers": src.blockers,
        "skill_mastery": src.skill_mastery,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1, default=_jsonable)


# ───────────────────────── 迁移 ─────────────────────────


@dataclass
class Report:
    dry_run: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    point_changes: list[dict] = field(default_factory=list)
    skill_mastery: list[dict] = field(default_factory=list)
    lessons: list[dict] = field(default_factory=list)

    def bump(self, kind: str, what: str) -> None:
        self.counts.setdefault(kind, {"created": 0, "updated": 0, "unchanged": 0})
        self.counts[kind][what] = self.counts[kind].get(what, 0) + 1

    def as_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "errors": self.errors,
            "warnings": self.warnings,
            "counts": self.counts,
            "point_changes": self.point_changes,
            "skill_mastery": self.skill_mastery,
            "lessons": self.lessons,
        }


def _set(obj: Any, attrs: dict) -> bool:
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


def _upsert(db: Session, rep: Report, kind: str, model: type, legacy_ref: str, attrs: dict) -> Any:
    row = db.scalar(select(model).where(model.legacy_ref == legacy_ref))
    if row is None:
        row = model(legacy_ref=legacy_ref, **attrs)
        db.add(row)
        db.flush()
        rep.bump(kind, "created")
    elif _set(row, attrs):
        db.flush()
        rep.bump(kind, "updated")
    else:
        rep.bump(kind, "unchanged")
    return row


class Migrator:
    def __init__(self, db: Session, src: Source, source_tz: str = "Asia/Shanghai", now: datetime | None = None):
        self.db = db
        self.src = src
        self.tz = ZoneInfo(source_tz)
        self.now = now or utcnow()
        self.lesson_map = load_lesson_map()
        self.lessons_by_id = {int(r["id"]): r for r in src.lessons}
        self.point_for_lesson: dict[int, str] = {}
        self.touched: set[str] = set()

    def utc(self, v: Any) -> datetime | None:
        dt = _as_dt(v)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.tz)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)

    def observed_at(self, s: dict) -> datetime:
        """证据时间：源记录的 created_at（若与 study_date 同一天），否则 study_date 当天 21:00（北京时间）。"""
        d = _as_date(s["study_date"])
        created = _as_dt(s.get("created_at"))
        if created is not None:
            local = created if created.tzinfo is None else created.astimezone(self.tz).replace(tzinfo=None)
            if local.date() == d:
                return self.utc(local)
        return self.utc(datetime.combine(d, time(21, 0)))

    # 1) 课程 → 知识点
    def map_lessons(self, rep: Report) -> None:
        used_lessons = {int(s["lesson_id"]) for s in self.src.sessions if s.get("lesson_id") is not None}
        used_lessons |= {int(b["lesson_id"]) for b in self.src.blockers if b.get("lesson_id") is not None}
        missing_main = []
        need_misc: list[dict] = []
        for lid, row in sorted(self.lessons_by_id.items(), key=lambda kv: (kv[1].get("sort_order") or 0, kv[0])):
            code = str(row["code"]).upper()
            mapped = (self.lesson_map.get(code) or {}).get("point")
            has_records = lid in used_lessons
            if mapped:
                if self.db.get(Point, mapped) is None:
                    missing_main.append(mapped)
                    continue
                self.point_for_lesson[lid] = mapped
            elif has_records:
                need_misc.append(row)
                self.point_for_lesson[lid] = misc_point_id(code)
            rep.lessons.append(
                {
                    "code": code,
                    "title": row.get("title"),
                    "old_status": row.get("status"),
                    "active": bool(row.get("active", 1)),
                    "point_id": self.point_for_lesson.get(lid),
                    "has_records": has_records,
                }
            )
        for lid in used_lessons - set(self.lessons_by_id):
            rep.warnings.append(f"源库有记录引用了不存在的 lesson_id={lid}，这些记录不关联知识点")
        if missing_main:
            rep.errors.append(
                f"目标库缺少映射用的知识点 {sorted(set(missing_main))}，请先按部署说明 4.1 导入 java-fde.yaml 再迁移"
            )
            return
        if need_misc:
            self._ensure_misc(rep, need_misc)

    def _ensure_misc(self, rep: Report, rows: list[dict]) -> None:
        db = self.db
        subj = db.get(Subject, MISC_SUBJECT)
        attrs = {
            "prefix": "misc",
            "title": "主线外课程（迁移）",
            "goal": "保留 axue_learning 旧课程表里主线外课程的学习历史",
            "description": "由 migrate_axue 从 axue_learning 迁入，不参与推荐；不在任何 YAML 里，导入地图不会动它。",
            "map_version": "legacy-1",
            "active": True,
        }
        if subj is None:
            db.add(Subject(id=MISC_SUBJECT, **attrs))
            rep.bump("subjects", "created")
        elif _set(subj, attrs):
            rep.bump("subjects", "updated")
        else:
            rep.bump("subjects", "unchanged")
        db.flush()
        st_attrs = {"subject_id": MISC_SUBJECT, "ord": 1, "title": "旧课程表（W1–W4）", "active": True}
        st = db.get(Stage, MISC_STAGE)
        if st is None:
            db.add(Stage(id=MISC_STAGE, **st_attrs))
        else:
            _set(st, st_attrs)
        db.flush()
        for row in rows:
            code = str(row["code"]).upper()
            meta = self.lesson_map.get(code) or {}
            pid = misc_point_id(code)
            area = row.get("area") or meta.get("area") or "-"
            sources = [{"type": "lesson", "ref": code, "title": row.get("title") or meta.get("title")}]
            fp = row.get("file_path") or meta.get("file_path")
            if fp:
                sources.append({"type": "path", "ref": fp})
            p_attrs = {
                "subject_id": MISC_SUBJECT,
                "stage_id": MISC_STAGE,
                "ord": int(row.get("sort_order") or meta.get("sort_order") or 0),
                "title": row.get("title") or meta.get("title") or code,
                "description": f"axue_learning 旧课 {code}（{area}），迁移保留历史",
                "card_types": ["understand"],
                "effort_hours": Decimal("1.0"),
                "interview_weight": 0,
                "mastery_evidence": [],
                "tags": ["legacy"],
                "sources": sources,
                "example_cards": [],
            }
            pt = db.get(Point, pid)
            if pt is None:
                db.add(Point(id=pid, active=True, **p_attrs))
                rep.bump("misc_points", "created")
            elif _set(pt, p_attrs):
                rep.bump("misc_points", "updated")
            else:
                rep.bump("misc_points", "unchanged")
            db.flush()
            self.touched.add(pid)

    # 2) 课次 + 证据
    def migrate_sessions(self, rep: Report) -> dict[int, int]:
        db = self.db
        sid_map: dict[int, int] = {}
        for s in self.src.sessions:
            old_id = int(s["id"])
            lid = s.get("lesson_id")
            pid = self.point_for_lesson.get(int(lid)) if lid is not None else None
            lesson = self.lessons_by_id.get(int(lid)) if lid is not None else None
            notes = s.get("notes")
            card = parse_card(notes)
            subject_id = db.get(Point, pid).subject_id if pid else None
            attrs = {
                "subject_id": subject_id,
                "date": _as_date(s["study_date"]),
                "minutes": int(s["minutes"]) if s.get("minutes") is not None else None,
                "lesson_ref": str(lesson["code"]).upper() if lesson else None,
                "cues": card.get("cues") or [],
                "summary": card.get("总结"),
                "stuck": card.get("卡点"),
                "notes": notes,
                "source": "migrate",
            }
            created = self.utc(s.get("created_at"))
            row = db.scalar(select(StudySession).where(StudySession.legacy_ref == f"axue:study_sessions:{old_id}"))
            if row is None and created is not None:
                attrs_new = attrs | {"created_at": created}
            else:
                attrs_new = attrs
            row = _upsert(db, rep, "sessions", StudySession, f"axue:study_sessions:{old_id}", attrs_new)
            sid_map[old_id] = row.id
            have = set(db.scalars(select(SessionPoint.point_id).where(SessionPoint.session_id == row.id)).all())
            want = {pid} if pid else set()
            for extra in have - want:
                db.delete(db.get(SessionPoint, (row.id, extra)))
            for p in want - have:
                db.add(SessionPoint(session_id=row.id, point_id=p))
            if pid:
                self.touched.add(pid)
            else:
                rep.warnings.append(f"study_sessions#{old_id} 没有对应知识点，只迁课次、不建证据")
                continue
            db.flush()
            self._evidence(rep, s, row.id, pid)
        return sid_map

    def _evidence(self, rep: Report, s: dict, session_id: int, pid: str) -> None:
        old_id = int(s["id"])
        notes = s.get("notes")
        at = self.observed_at(s)
        base = {"point_id": pid, "session_id": session_id, "reviewer": "migrate", "observed_at": at}
        if s.get("self_test_score") is not None:
            score = Decimal(str(s["self_test_score"]))
            mx = Decimal(str(s.get("self_test_total") or 5))
            _upsert(
                self.db,
                rep,
                "evidence_selftest",
                Evidence,
                f"axue:study_sessions:{old_id}:selftest",
                base | {"type": "selftest", "score": score, "max_score": mx, "passed": score / mx >= Decimal("0.8")},
            )
        fe = parse_feynman(notes)
        if fe is not None:
            _upsert(
                self.db,
                rep,
                "evidence_feynman",
                Evidence,
                f"axue:study_sessions:{old_id}:feynman",
                base | {"type": "feynman", "passed": fe, "notes": "迁移自 notes「费曼」"},
            )
        ex = parse_express(notes)
        if ex is not None:
            score, mx, rubric = ex
            _upsert(
                self.db,
                rep,
                "evidence_express",
                Evidence,
                f"axue:study_sessions:{old_id}:express",
                base
                | {
                    "type": "express",
                    "score": score,
                    "max_score": mx,
                    "passed": score / mx >= Decimal("0.75"),
                    "rubric": rubric,
                    "notes": "迁移自 notes「表达」",
                },
            )

    # 3) 卡点
    def migrate_blockers(self, rep: Report, sid_map: dict[int, int]) -> None:
        for b in self.src.blockers:
            old_id = int(b["id"])
            lid = b.get("lesson_id")
            pid = self.point_for_lesson.get(int(lid)) if lid is not None else None
            desc = (b.get("description") or "").strip() or "(空)"
            first = desc.splitlines()[0].strip()
            title = first if len(first) <= 255 else first[:254] + "…"
            detail = desc if desc != title else None
            if pid is None and b.get("area"):
                detail = (detail or desc) + f"\n[axue_learning 领域：{b['area']}]"
            old_sid = b.get("session_id")
            status = STATUS_MAP.get(b.get("status") or "未解决", "open")
            attrs = {
                "point_id": pid,
                "session_id": sid_map.get(int(old_sid)) if old_sid is not None else None,
                "title": title,
                "detail": detail,
                "status": status,
                "created_at": self.utc(b.get("created_at")) or self.now,
                "resolved_at": self.utc(b.get("resolved_at")) if status == "resolved" else None,
            }
            if status == "resolved" and attrs["resolved_at"] is None:
                attrs["resolved_at"] = attrs["created_at"]
            if old_sid is not None and int(old_sid) not in sid_map:
                rep.warnings.append(f"blockers#{old_id} 引用的 session#{old_sid} 不存在，session_id 置空")
            _upsert(self.db, rep, "blockers", Blocker, f"axue:blockers:{old_id}", attrs)

    def run(self, rep: Report) -> None:
        self.map_lessons(rep)
        if rep.errors:
            return
        sid_map = self.migrate_sessions(rep)
        self.migrate_blockers(rep, sid_map)
        self.db.flush()
        if self.touched:
            ids = list(self.touched)
            rep.point_changes = recompute_points(self.db, _topo(self.db, ids), cause="migrate", now=self.now)
        rep.skill_mastery = [
            {
                "area": m.get("area"),
                "level": m.get("level"),
                "note": m.get("note"),
                "updated_at": _as_text(m.get("updated_at")),
            }
            for m in self.src.skill_mastery
        ]
        from tongyun_learn.models import PointState  # noqa: PLC0415  报告里附上迁移后状态

        for item in rep.lessons:
            if item["point_id"]:
                ps = self.db.get(PointState, item["point_id"])
                item["new_state"] = ps.state if ps else None


def migrate(db: Session, src: Source, dry_run: bool = True, source_tz: str = "Asia/Shanghai") -> dict:
    rep = Report(dry_run=dry_run)
    try:
        Migrator(db, src, source_tz=source_tz).run(rep)
    except Exception:
        db.rollback()
        raise
    if rep.errors or dry_run:
        db.rollback()
    else:
        db.commit()
    out = rep.as_dict()
    out["finished_at"] = iso_local(utcnow())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tongyun_learn.migrate_axue", description="axue_learning → tongyun_learn 迁移")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--source-url", help="源库 SQLAlchemy URL（也可用环境变量 AXUE_SOURCE_URL）")
    g.add_argument("--source-json", help="从快照 JSON 读源数据")
    ap.add_argument("--snapshot", help="只把源库四张表导出成 JSON 快照（不写目标库）")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="预演（默认）：跑完回滚")
    mode.add_argument("--commit", action="store_true", help="真写目标库")
    ap.add_argument("--source-tz", default="Asia/Shanghai", help="源库 DATETIME 的时区，默认 Asia/Shanghai")
    ap.add_argument("--report", help="报告另存为 JSON 文件")
    args = ap.parse_args(argv)

    if args.source_json:
        src = read_source_json(args.source_json)
    else:
        url = args.source_url or os.environ.get("AXUE_SOURCE_URL")
        if not url:
            ap.error("需要 --source-url / AXUE_SOURCE_URL 或 --source-json")
        src = read_source_db(url)
    if args.snapshot:
        write_snapshot(src, args.snapshot)
        print(
            f"快照已写入 {args.snapshot}：lessons {len(src.lessons)}，study_sessions {len(src.sessions)}，"
            f"blockers {len(src.blockers)}，skill_mastery {len(src.skill_mastery)}"
        )
        return 0

    from tongyun_learn.db import SessionLocal  # noqa: PLC0415  只有真要写目标库时才连

    with SessionLocal() as db:
        res = migrate(db, src, dry_run=not args.commit, source_tz=args.source_tz)
    text_out = json.dumps(res, ensure_ascii=False, indent=2, default=_jsonable)
    print(text_out)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(text_out)
    mode_s = "已提交" if args.commit and not res["errors"] else "预演，已回滚"
    print(f"[{mode_s}] counts={json.dumps(res['counts'], ensure_ascii=False)}", file=sys.stderr)
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
