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
from datetime import date
from pathlib import Path
import json

VAULT = Path(__file__).resolve().parent.parent
INDEX = VAULT / "90_META" / "INDEX.json"

# Entry points / logs are not expected to have inbound links.
NEVER_ORPHAN = {"doc", "core", "meta", "overview", "recent", "session"}


def load():
    if not INDEX.exists():
        raise SystemExit("no INDEX.json — run scripts/indexer.py first")
    return json.loads(INDEX.read_text(encoding="utf-8"))["notes"]


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


def main():
    ap = argparse.ArgumentParser(description="Flag orphan and stale notes.")
    ap.add_argument("--days", type=int, default=180, help="stale threshold")
    args = ap.parse_args()
    notes = load()

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
