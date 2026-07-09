#!/usr/bin/env python3
"""ABSOLUTE ZERO query. Stdlib only.

Filters 90_META/INDEX.json by tags/type/project/date and prints
title + summary + path per hit. Nothing else (retrieval is pull, not push).

  python scripts/query.py --tags ros2,navigation
  python scripts/query.py --tags ekf --type lesson
  python scripts/query.py --project ASUNAMA --since 2026-01-01
"""
import argparse
import json
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
INDEX = VAULT / "90_META" / "INDEX.json"


def load():
    if not INDEX.exists():
        raise SystemExit("no INDEX.json — run scripts/indexer.py first")
    return json.loads(INDEX.read_text(encoding="utf-8"))["notes"]


def matches(note, tags, ntype, project, since):
    if ntype and note["type"] != ntype:
        return False
    if project and note["project"].upper() != project.upper():
        return False
    if since and (note["date"] or "") < since:
        return False
    if tags:
        have = {t.lower() for t in note["tags"]}
        if not all(t.lower() in have for t in tags):
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description="Query the vault index.")
    ap.add_argument("--tags", default="", help="comma-separated, all must match")
    ap.add_argument("--type", dest="ntype", default="",
                    help="lesson|fault|knowledge|decision|session|...")
    ap.add_argument("--project", default="")
    ap.add_argument("--since", default="", help="YYYY-MM-DD, inclusive")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    hits = [n for n in load()
            if matches(n, tags, args.ntype, args.project, args.since)]
    hits.sort(key=lambda n: n["date"], reverse=True)

    if not hits:
        print("not in vault")
        return
    for n in hits[:args.limit]:
        print(f"{n['title']}  [{n['type']}/{n['project']}]")
        if n["summary"]:
            print(f"    {n['summary']}")
        print(f"    {n['path']}")
    extra = len(hits) - args.limit
    if extra > 0:
        print(f"... {extra} more, narrow tags")


if __name__ == "__main__":
    main()
