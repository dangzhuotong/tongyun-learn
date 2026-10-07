"""命令行：种子数据导入（幂等）。

    python -m tongyun_learn.cli import-maps maps/*.yaml            # 只预演（dry run），打印 diff
    python -m tongyun_learn.cli import-maps --commit maps/*.yaml   # 真导入
跨学科前置要把相关文件一起传。重复执行同一份 YAML，diff 全为 0。数据库连接读 LEARN_DATABASE_URL。
"""

import argparse
import json
import sys
from pathlib import Path

from tongyun_learn.db import SessionLocal
from tongyun_learn.services.importer import import_maps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tongyun_learn.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    im = sub.add_parser("import-maps", help="导入知识地图 YAML")
    im.add_argument("files", nargs="+", type=Path)
    im.add_argument("--commit", action="store_true", help="真写库；不带时只预演")
    args = ap.parse_args(argv)

    texts = [f.read_text(encoding="utf-8") for f in args.files]
    with SessionLocal() as db:
        res = import_maps(db, texts, dry_run=not args.commit)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res["results"]:
        parts = [f"{r['subject']} {r['open_at_start']}" for r in res["results"]]
        avail = sum(r["points_by_state"].get("available", 0) for r in res["results"])
        total = sum(r["open_at_start"] for r in res["results"])
        mode = "预演" if res["dry_run"] else "已导入"
        msg = f"[{mode}] 开局可学（无硬前置）{total} 个：{'，'.join(parts)}；导入后可学状态 {avail} 个"
        print(msg, file=sys.stderr)
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
