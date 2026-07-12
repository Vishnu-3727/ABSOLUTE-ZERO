#!/usr/bin/env python3
"""ABSOLUTE ZERO review helper. Stdlib only.

The computable part of /review (FLOW.md): flag ORPHAN notes (no inbound
wikilinks) and STALE notes (older than --days). Pattern-hunting across the
FAULT_LEDGER and lesson summaries stays the reviewer's job — this just does the
tedious link-graph + date math so nothing rots unnoticed.

  python scripts/review.py            # orphans + notes older than 180d
  python scripts/review.py --days 90
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import load_index

VAULT = Path(__file__).resolve().parent.parent

# Entry points / logs are not expected to have inbound links.
NEVER_ORPHAN = {"doc", "core", "meta", "overview", "recent", "session"}


def stem(path):
    return Path(path).stem


def orphans(notes):
    linked = set()
    for n in notes:
        linked.update(n["links"])
    out = []
    for n in notes:
        if n["type"] in NEVER_ORPHAN:
            continue
        if stem(n["path"]) not in linked:
            out.append(n)
    return out


def stale(notes, days):
    today = date.today()
    out = []
    for n in notes:
        d = n.get("date", "")
        try:
            age = (today - date.fromisoformat(d)).days
        except ValueError:
            continue
        if age > days:
            out.append((age, n))
    out.sort(reverse=True)
    return out


def selftest():
    notes = [
        {"type": "lesson", "path": "30_LESSONS/a.md", "links": ["b"],
         "date": "2020-01-01"},
        {"type": "knowledge", "path": "20_KNOWLEDGE/b.md", "links": [],
         "date": str(date.today())},
        {"type": "doc", "path": "CLAUDE.md", "links": [], "date": ""},
    ]
    orph = {stem(n["path"]) for n in orphans(notes)}
    assert orph == {"a"}, orph  # b is linked, doc types never orphan
    st = stale(notes, 180)
    assert [stem(n["path"]) for _, n in st] == ["a"]  # bad date skipped
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Flag orphan and stale notes.")
    ap.add_argument("--days", type=int, default=180, help="stale threshold")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    notes = load_index(VAULT)

    orph = orphans(notes)
    print(f"ORPHANS (no inbound links): {len(orph)}")
    for n in orph:
        print(f"  [{n['type']}] {n['path']}")

    st = stale(notes, args.days)
    print(f"\nSTALE (> {args.days}d): {len(st)}")
    for age, n in st:
        print(f"  {age}d  {n['path']}")

    if not orph and not st:
        print("\nclean — nothing to prune.")


if __name__ == "__main__":
    main()
