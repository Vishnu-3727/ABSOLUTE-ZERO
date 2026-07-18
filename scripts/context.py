#!/usr/bin/env python3
"""ABSOLUTE ZERO context budget manager. Stdlib only.

Builds the Optimal Context Package for a request: what to load, at what
fidelity, within a token budget. Inputs: INDEX.json (knowledge), FAULT_LEDGER
(experience), similarity scoring, .claude/commands (skills), optional
conversation history file, the request itself. Output: ordered package with
fidelity tiers (full > section > summary > title), a pinned architecture
spine that survives budget pressure, one-hop dependency pulls, dedup, and an
OMITTED tail so the model knows what it did not load. Budget is a ceiling,
not a quota: low-relevance notes stay out even with room left.
Contract in CONTEXT.md.

  python scripts/context.py pack "why does odometry drift on takeoff" --project ASUNAMA
  python scripts/context.py pack "..." --budget 3000 --history chat.txt --json
  python scripts/context.py --selftest
"""
import argparse
import json
import re
import sys
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import STOP, classify, est_tokens, jaccard, words_of

VAULT = Path(__file__).resolve().parent.parent
BUDGET, HARD_CAP = 5000, 8000
FULL_CAP = 400        # tokens; bigger bodies get section-extracted
TITLE_COST = 8
MIN_SCORE = 0.5       # below this a note adds noise, not signal
HISTORY_SHARE = 0.15  # of budget
DEDUP_JACCARD = 0.6
# Wake set is already in context at session start - never double-load.
WAKE_SET = {"CLAUDE.md", "00_CORE/ACTIVE_GOALS.md", "90_META/INDEX_SUMMARY.md"}
TYPE_PRIOR = {"fault": 1.0, "lesson": 0.8, "knowledge": 0.6, "decision": 0.6,
              "research": 0.5, "overview": 0.4, "recent": 0.4, "goals": 0.3,
              "core": 0.3, "session": 0.2, "doc": 0.1}
INTENT_SKILLS = {"research": ["research", "recall"],
                 "architecture": ["recall", "review", "predict"],
                 "performance": ["recall", "predict"],
                 "security": ["recall", "review"],
                 "deployment": ["recall", "predict"]}
FM_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def recency(d, today):
    try:
        age = (today - date.fromisoformat(d)).days
    except (ValueError, TypeError):
        return 0.0
    return 0.3 if age <= 30 else 0.15 if age <= 180 else 0.0


def score(note, qwords, project, today):
    """2.0*tag_hits + 1.5*similarity + type_prior + 0.5*project + recency."""
    tag_hits = len(qwords & {t.lower() for t in note["tags"]})
    text = (note["title"] + " " + (note["summary"] or "")).lower()
    sim = max(jaccard(qwords, set(words_of(text))),
              SequenceMatcher(None, " ".join(sorted(qwords)), text).ratio())
    s = 2.0 * tag_hits + 1.5 * sim + TYPE_PRIOR.get(note["type"], 0.3)
    if project and note["project"].upper() == project.upper():
        s += 0.5
    return round(s + recency(note.get("date", ""), today), 2)


def read_body(vault, relpath):
    p = vault / relpath
    if not p.exists():
        return ""
    return FM_RE.sub("", p.read_text(encoding="utf-8"), count=1)


def compress(body, qwords, cap):
    """Fidelity ladder: full body if it fits, else only request-matching
    sections, else caller falls back to the frontmatter summary."""
    if est_tokens(body) <= cap:
        return body, "full"
    parts = re.split(r"(?m)^(?=#{1,3} )", body)
    keep = "".join(p for p in parts if qwords & set(words_of(p)))
    if keep and est_tokens(keep) <= cap:
        return keep, "section"
    return "", "summary"


def dedup(scored):
    """Near-duplicate summaries: keep the higher-scored note."""
    kept, dropped = [], []
    for s, n in scored:  # already sorted desc
        nw = set(words_of(n["title"] + " " + (n["summary"] or "")))
        if any(jaccard(nw, kw) > DEDUP_JACCARD for kw, _ in kept):
            dropped.append(n["path"])
        else:
            kept.append((nw, (s, n)))
    return [k for _, k in kept], dropped


def compress_history(path, qwords, cap):
    """Extractive: lines matching the request + the last 10 lines, newest
    kept when over cap. Real summarization is the model's job at runtime."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    tail = lines[-10:]
    hits = [l for l in lines[:-10] if qwords & set(words_of(l))]
    picked = hits + tail
    while picked and est_tokens("\n".join(picked)) > cap:
        picked.pop(0)  # oldest goes first
    return "\n".join(picked)


def build(request, project="", budget=BUDGET, history=None,
          vault=VAULT, notes=None):
    budget = min(budget, HARD_CAP)
    qwords = set(words_of(request)) - STOP
    intent = classify(request)["intent"]
    today = date.today()
    if notes is None:
        idx = vault / "90_META" / "INDEX.json"
        if not idx.exists():
            raise SystemExit("no INDEX.json - run scripts/indexer.py first")
        notes = json.loads(idx.read_text(encoding="utf-8"))["notes"]
    by_stem = {Path(n["path"]).stem: n for n in notes}
    used = 0
    pkg = {"request": request, "intent": intent, "budget": budget,
           "pinned": [], "items": [], "history": None,
           "skills": INTENT_SKILLS.get(intent, ["recall"]),
           "dropped_dups": [], "omitted": []}

    # 1. Pinned architecture spine: project OVERVIEW/RECENT + matching
    #    fault-ledger lines. Survives any budget pressure (loud if it alone
    #    blows the budget - that is the 8k escalation case).
    spine = []
    if project:
        for name in ("OVERVIEW.md", "RECENT.md"):
            rel = f"10_PROJECTS/{project.upper()}/{name}"
            if (vault / rel).exists():
                spine.append((rel, read_body(vault, rel), "project spine"))
    ledger = vault / "90_META" / "FAULT_LEDGER.md"
    if ledger.exists():
        hits = [l for l in ledger.read_text(encoding="utf-8").splitlines()
                if qwords & set(words_of(l))]
        if hits:
            spine.append(("90_META/FAULT_LEDGER.md", "\n".join(hits),
                          f"{len(hits)} matching fault line(s)"))
    for rel, text, why in spine:
        cost = est_tokens(text)
        pkg["pinned"].append({"path": rel, "tier": "full", "tokens": cost,
                              "reason": why, "text": text})
        used += cost
    if used > budget:
        print(f"WARNING: pinned spine alone is {used} tokens > budget "
              f"{budget} - narrow the request or raise the budget",
              file=sys.stderr)

    # 2. History: extractive compression, capped share of budget.
    if history:
        text = compress_history(history, qwords, int(budget * HISTORY_SHARE))
        pkg["history"] = {"path": str(history), "tokens": est_tokens(text),
                          "text": text}
        used += pkg["history"]["tokens"]

    # 3. Score, dedup, greedy-select with fidelity degradation.
    pinned_paths = {p["path"] for p in pkg["pinned"]}
    cands = [n for n in notes
             if n["path"] not in WAKE_SET and n["path"] not in pinned_paths]
    scored = sorted(((score(n, qwords, project, today), n) for n in cands),
                    key=lambda x: x[0], reverse=True)
    scored = [(s, n) for s, n in scored if s >= MIN_SCORE]
    scored, pkg["dropped_dups"] = dedup(scored)
    selected = {}
    for s, n in scored:
        room = budget - used
        if room < TITLE_COST:
            break
        text, tier = compress(read_body(vault, n["path"]), qwords,
                              min(FULL_CAP, room))
        if tier == "summary":
            text = n["summary"] or n["title"]
            if est_tokens(text) > room:
                tier, text = "title", n["title"]
        cost = est_tokens(text)
        if cost > room:
            continue
        item = {"path": n["path"], "tier": tier, "tokens": cost, "score": s,
                "reason": "ranked", "text": text}
        pkg["items"].append(item)
        selected[Path(n["path"]).stem] = item
        used += cost

    # 4. One-hop dependency pull: links of selected notes come along at
    #    summary tier (fault -> topic note rule rides on this).
    #    ponytail: one hop only; transitive closure if link chains deepen.
    for item in list(pkg["items"]) + pkg["pinned"]:
        src = by_stem.get(Path(item["path"]).stem)
        for link in (src or {}).get("links", []):
            stem = Path(link.split("|")[0]).stem
            dep = by_stem.get(stem)
            if (not dep or stem in selected or dep["path"] in pinned_paths
                    or dep["path"] in WAKE_SET):
                continue
            text = dep["summary"] or dep["title"]
            cost = est_tokens(text)
            if used + cost > budget:
                continue
            entry = {"path": dep["path"], "tier": "summary", "tokens": cost,
                     "score": 0.0, "reason": f"dep of {Path(item['path']).stem}",
                     "text": text}
            pkg["items"].append(entry)
            selected[stem] = entry
            used += cost

    pkg["omitted"] = [f"{n['title']} ({n['path']})" for s, n in scored
                      if Path(n["path"]).stem not in selected]
    pkg["used"] = used
    return pkg


def show(pkg):
    print(f"intent      {pkg['intent']}")
    print(f"budget      {pkg['used']} / {pkg['budget']} tokens used")
    print("PINNED (architecture spine)")
    for p in pkg["pinned"]:
        print(f"  {p['tokens']:>5}  {p['path']}  ({p['reason']})")
    if not pkg["pinned"]:
        print("  none")
    print("RANKED")
    for i in pkg["items"]:
        print(f"  {i['score']:>5}  {i['tier']:<7} {i['tokens']:>5}  "
              f"{i['path']}  ({i['reason']})")
    if not pkg["items"]:
        print("  not in vault")
    if pkg["history"]:
        print(f"HISTORY     {pkg['history']['tokens']} tokens extracted "
              f"from {pkg['history']['path']}")
    print(f"SKILLS      {', '.join('/' + s for s in pkg['skills'])}")
    if pkg["dropped_dups"]:
        print(f"DEDUPED     {', '.join(pkg['dropped_dups'])}")
    if pkg["omitted"]:
        print(f"OMITTED     {len(pkg['omitted'])} known, not loaded:")
        for t in pkg["omitted"]:
            print(f"  {t}")


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        def note(rel, title, ntype, tags, summary, links=(), body="",
                 proj="ASUNAMA", d="2026-07-01"):
            p = v / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body or f"# {title}\ncontent\n", encoding="utf-8")
            return {"path": rel, "title": title, "type": ntype, "tags": tags,
                    "summary": summary, "links": list(links), "project": proj,
                    "date": d}
        big = ("# Drift\n\n## odometry drift cause\n" + "detail " * 30 +
               "\n\n## unrelated appendix\n" + "filler " * 200)
        notes = [
            note("CLAUDE.md", "Master", "doc", [], "rules"),
            note("30_LESSONS/drift.md", "Odometry drift fix", "lesson",
                 ["odometry", "drift"], "Anchor odometry drift absolutely.",
                 links=["nav-topic"], body=big),
            note("30_LESSONS/drift2.md", "Odometry drift fix again", "lesson",
                 ["odometry", "drift"], "Anchor odometry drift absolutely!"),
            note("20_KNOWLEDGE/nav-topic.md", "GPS-denied navigation",
                 "knowledge", ["navigation"], "How to localize without GPS."),
            note("10_PROJECTS/ASUNAMA/SESSIONS/x.md", "Session", "session",
                 ["odometry"], "A day of work."),
        ]
        (v / "90_META").mkdir()
        (v / "90_META" / "FAULT_LEDGER.md").write_text(
            "[ASUNAMA][odometry] drift on takeoff -> anchor to origin\n"
            "[ASUNAMA][coverage] footprint bug -> mark full footprint\n",
            encoding="utf-8")
        pkg = build("fix odometry drift on takeoff", project="ASUNAMA",
                    budget=300, vault=v, notes=notes)
        paths = [i["path"] for i in pkg["items"]]
        assert pkg["used"] <= 300, "budget ceiling violated"
        assert "CLAUDE.md" not in paths, "wake set double-loaded"
        assert "30_LESSONS/drift2.md" in pkg["dropped_dups"], "dedup missed"
        assert any("drift on takeoff" in p["text"]
                   for p in pkg["pinned"]), "fault ledger line not pinned"
        assert not any("coverage" in p["text"].splitlines()[-1]
                       and len(p["text"].splitlines()) > 1
                       for p in pkg["pinned"] if "LEDGER" in p["path"]), \
            "non-matching ledger line pinned"
        assert "20_KNOWLEDGE/nav-topic.md" in paths, "dependency not pulled"
        top = pkg["items"][0]
        assert top["path"] == "30_LESSONS/drift.md" and top["tier"] == "section"
        assert "unrelated appendix" not in top["text"], "compression kept junk"
        lesson_i = paths.index("30_LESSONS/drift.md")
        sess_i = paths.index("10_PROJECTS/ASUNAMA/SESSIONS/x.md") \
            if "10_PROJECTS/ASUNAMA/SESSIONS/x.md" in paths else 99
        assert lesson_i < sess_i, "type prior failed: session above lesson"
        h = v / "chat.txt"
        h.write_text("\n".join(["noise line"] * 40
                               + ["user decided odometry anchor approach"]
                               + ["closing line %d" % i for i in range(10)]),
                     encoding="utf-8")
        pkg2 = build("fix odometry drift", budget=1000, history=h,
                     vault=v, notes=notes)
        assert "odometry anchor approach" in pkg2["history"]["text"]
        assert "noise line" not in pkg2["history"]["text"]
        assert pkg2["history"]["tokens"] <= 150
        tiny = build("fix odometry drift", budget=80, vault=v, notes=notes)
        assert tiny["used"] <= 80, "tiny budget violated"
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Context budget manager.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    pk = sub.add_parser("pack")
    pk.add_argument("request")
    pk.add_argument("--project", default="")
    pk.add_argument("--budget", type=int, default=BUDGET)
    pk.add_argument("--history", default=None)
    pk.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    if args.selftest:
        selftest()
    elif args.cmd == "pack":
        pkg = build(args.request, args.project, args.budget, args.history)
        if args.as_json:
            print(json.dumps(pkg, indent=1))
        else:
            show(pkg)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
