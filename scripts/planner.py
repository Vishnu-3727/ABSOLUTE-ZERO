#!/usr/bin/env python3
"""ABSOLUTE ZERO planning engine. Stdlib only.

Plans before implementation: decomposes a request into subtasks, expands
each into intent-specific steps bound to discovered plugins, orders the
whole graph topologically, attaches risks mined from the FAULT_LEDGER,
alternatives, complexity points, a git rollback baseline, a test per step,
and architecture-validation gates. Output is an executable plan the /task
EXECUTE stage can walk step by step. Contract in PLANNER.md.

  python scripts/planner.py plan "add wikilinks to query output and fix the date crash"
  python scripts/planner.py validate 90_META/plans/<id>.json
  python scripts/planner.py --selftest
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from graphlib import TopologicalSorter, CycleError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import STOP, classify, words_of

VAULT = Path(__file__).resolve().parent.parent
PLANS = VAULT / "90_META" / "plans"
POINTS = {"trivial": 1, "standard": 3, "complex": 8}
MAX_SUBTASKS = 5

# Step templates per intent: (action, needed_caps, risk, test, rollback).
# Steps run in listed order (each depends on the previous) unless noted.
STEPS = {
    "quick_fix": [
        ("recall", ["retrieval"], "past fault repeats", "ledger scanned", "-"),
        ("apply", [], "collateral edits", "diff shows only the target",
         "git checkout -- <files>"),
        ("check", ["audit"], "-", "selftest / targeted run passes",
         "git checkout -- <files>"),
    ],
    "bug_fix": [
        ("recall", ["retrieval"], "fixing symptom seen before", "ledger + pack cited", "-"),
        ("reproduce", [], "unreproducible = wrong diagnosis",
         "failing case demonstrated", "-"),
        ("root-cause", [], "patching a caller instead of the shared cause",
         "cause named in one sentence", "-"),
        ("fix", ["codegen"], "regression elsewhere", "repro now passes",
         "git checkout -- <files>"),
        ("record", ["persistence"], "lesson lost",
         "FAULTS.md entry links a topic note", "git revert <commit>"),
    ],
    "feature": [
        ("recall", ["retrieval"], "rebuilding what exists", "pack cited", "-"),
        ("design", [], "over-engineering",
         "approach chosen from alternatives, one line why", "-"),
        ("implement", ["codegen"], "scope creep",
         "works end to end", "git checkout -- <files>"),
        ("test", ["audit"], "untested branch", "selftest + e2e pass",
         "git checkout -- <files>"),
        ("document", ["indexing"], "docs drift", "docs updated + reindexed",
         "git revert <commit>"),
    ],
    "architecture": [
        ("recall", ["retrieval", "similarity"], "ignoring prior decisions",
         "pack + similarity cited", "-"),
        ("design", [], "big-bang rewrite",
         "written plan approved before edits", "-"),
        ("validate", [], "invariant broken",
         "architecture checks all ok", "-"),
        ("implement", ["codegen"], "cross-module breakage",
         "all selftests pass", "git reset --hard <baseline>"),
        ("review", ["audit"], "orphan modules", "review.py clean",
         "git revert <commit>"),
    ],
    "research": [
        ("recall", ["retrieval"], "researching what vault knows", "pack cited", "-"),
        ("search", ["web", "research"], "unsourced claims",
         "every claim has a URL", "-"),
        ("write", ["persistence"], "summary in context not in note",
         "note in 40_RESEARCH with frontmatter", "git checkout -- <files>"),
        ("digest", [], "-", "5-line digest reported", "-"),
    ],
    "documentation": [
        ("recall", ["retrieval"], "documenting stale behavior", "pack cited", "-"),
        ("write", ["indexing"], "drift from code",
         "checked against current code", "git checkout -- <files>"),
        ("index", ["indexing"], "orphan doc", "reindex + review.py clean",
         "git checkout -- <files>"),
    ],
    "performance": [
        ("recall", ["retrieval"], "optimizing the wrong hotspot", "pack cited", "-"),
        ("baseline", [], "no before-number", "baseline measured", "-"),
        ("optimize", ["codegen"], "correctness regression",
         "selftests still pass", "git checkout -- <files>"),
        ("measure", [], "placebo optimization",
         "after-number beats baseline", "git revert <commit>"),
    ],
    "security": [
        ("recall", ["retrieval", "audit"], "known vuln class repeats",
         "ledger + pack cited", "-"),
        ("threat-model", [], "fixing the wrong threat", "threat named", "-"),
        ("fix", ["codegen"], "incomplete fix", "exploit path closed",
         "git checkout -- <files>"),
        ("audit", ["audit"], "secrets committed",
         "no secrets in diff, review clean", "git revert <commit>"),
    ],
    "deployment": [
        ("recall", ["retrieval"], "past deploy faults repeat", "ledger cited", "-"),
        ("stage", [], "no dry run", "dry-run or staged first", "-"),
        ("deploy", ["persistence"], "no rollback path",
         "rollback command stated before deploy", "documented rollback path"),
        ("verify", ["audit"], "silent partial failure",
         "post-deploy check passes", "execute rollback path"),
    ],
}
ALTERNATIVES = {
    "quick_fix": ["edit in place", "revert the offending commit instead"],
    "bug_fix": ["fix in the shared function (root cause)",
                "guard at the caller (symptom - only with a ponytail note)"],
    "feature": ["extend an existing script (preferred - ladder rung 2)",
                "new stdlib script", "markdown flow only, no code"],
    "architecture": ["incremental refactor behind existing interfaces",
                     "new module + deprecate old", "do nothing (YAGNI check)"],
    "research": ["web research to 40_RESEARCH note",
                 "answer from vault only if pack already covers it"],
    "documentation": ["update existing doc", "new root doc (register in "
                      "indexer ROOT_DOCS)", "one-line ledger/principle entry"],
    "performance": ["algorithmic fix", "cache", "accept and document ceiling"],
    "security": ["remove the risky surface", "validate at trust boundary",
                 "document as accepted risk"],
    "deployment": ["staged rollout", "all-at-once with tested rollback"],
}
# Architecture invariants of this OS, checked against request + plan.
LAWS = [
    (r"\bpip\b|\bconda\b|package|dependency|install\b",
     "stdlib-only law: vault scripts take zero dependencies (CLAUDE.md)"),
    (r"rewrite.*claude\.md|claude\.md.*rewrite",
     "CLAUDE.md is never rewritten without asking"),
    (r"\bnew root doc|[A-Z]+\.md at (vault )?root",
     "new root docs must be added to indexer ROOT_DOCS"),
]


def decompose(request):
    parts = re.split(r"\band then\b|\bthen\b|\band also\b|;|\band\b",
                     request, flags=re.IGNORECASE)
    parts = [p.strip(" ,.") for p in parts if len(words_of(p)) >= 2]
    return (parts or [request])[:MAX_SUBTASKS]


def mine_risks(text, vault):
    """Experience-engine pass: fault-ledger lines sharing words with the task."""
    qw = set(words_of(text)) - STOP
    out = []
    ledger = vault / "90_META" / "FAULT_LEDGER.md"
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.startswith("-") and qw & (set(words_of(line)) - STOP):
                out.append(line.lstrip("- ").strip())
    return out


def bind_plugins(caps, vault):
    """Best plugin + fallbacks for a step's capabilities, from the registry."""
    try:
        from plugins import load_registry, load_stats, score
        plugs = [p for p in load_registry() if p["name"] != "plugins"]
        stats = load_stats()
    except SystemExit:
        return None, []
    need = set(caps)
    ranked = sorted(plugs, key=lambda p: score(p, need, stats), reverse=True)
    ranked = [p["name"] for p in ranked if set(p["capabilities"]) & need]
    return (ranked[0] if ranked else None), ranked[1:3]


def git_baseline(vault):
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, cwd=vault)
        return r.stdout.strip() or None
    except OSError:
        return None


def validate(plan):
    """Architecture validation gates. ok / warn / fail (fail = not executable)."""
    checks = []
    graph = {s["id"]: set(s["depends_on"]) for s in plan["steps"]}
    try:
        list(TopologicalSorter(graph).static_order())  # generator: consume
        checks.append(("ok", "dependency graph is acyclic"))
    except CycleError as e:
        checks.append(("fail", f"dependency cycle: {e.args[1]}"))
    incomplete = [s["id"] for s in plan["steps"]
                  if not s["test"] or not s["rollback"]]
    checks.append(("ok", "every step has a test and a rollback") if not
                  incomplete else ("fail", f"steps missing test/rollback: "
                                           f"{', '.join(incomplete)}"))
    text = plan["request"].lower()
    for pat, law in LAWS:
        if re.search(pat, text):
            checks.append(("warn", law))
    if plan["complexity"]["label"] == "complex":
        checks.append(("warn", "complex plan: 8k escalation rule - state "
                               "cost, get approval before EXECUTE"))
    if plan["rollback"]["baseline"] is None:
        checks.append(("warn", "no git baseline - rollback is manual"))
    checks.append(("ok", "plan is executable") if not any(
        s == "fail" for s, _ in checks) else ("fail", "plan is NOT executable"))
    return checks


def build(request, project="", vault=VAULT, plans_dir=None):
    subtasks = decompose(request)
    steps, points, labels = [], 0, []
    for ti, sub in enumerate(subtasks, 1):
        c = classify(sub)
        points += POINTS[c["complexity"]]
        labels.append(c["complexity"])
        prev = None
        for si, (action, caps, risk, test, rollback) in \
                enumerate(STEPS[c["intent"]], 1):
            sid = f"t{ti}.s{si}"
            plugin, alts = bind_plugins(caps, vault) if caps else (None, [])
            steps.append({
                "id": sid, "subtask": sub, "intent": c["intent"],
                "action": action, "plugin": plugin, "alternatives": alts,
                "depends_on": [prev] if prev else [], "risk": risk,
                "test": test, "rollback": rollback,
            })
            prev = sid
    # single commit step closes the whole plan (vault sleep protocol)
    steps.append({"id": "commit", "subtask": request, "intent": "-",
                  "action": "commit + reindex", "plugin": "indexer",
                  "alternatives": [], "risk": "unindexed notes",
                  "depends_on": [s["id"] for s in steps
                                 if not any(s["id"] in t["depends_on"]
                                            for t in steps)],
                  "test": "git log shows commit; INDEX_SUMMARY fresh",
                  "rollback": "git revert HEAD"})
    label = ("complex" if "complex" in labels else
             "standard" if "standard" in labels else "trivial")
    plan = {
        "id": f"{datetime.now():%Y-%m-%d}-"
              + ("-".join(words_of(request)[:5]) or "plan"),
        "request": request, "project": project, "subtasks": subtasks,
        "complexity": {"points": points, "label": label,
                       "per_subtask": labels},
        "risks_known": mine_risks(request, vault),
        "approaches": sorted({a for s in steps if s["intent"] in ALTERNATIVES
                              for a in ALTERNATIVES[s["intent"]]}),
        "rollback": {"baseline": git_baseline(vault),
                     "strategy": "git reset --hard <baseline> abandons all; "
                                 "per-step rollbacks are surgical"},
        "steps": steps,
    }
    order = list(TopologicalSorter(
        {s["id"]: set(s["depends_on"]) for s in steps}).static_order())
    plan["execution_order"] = order
    plan["validation"] = [list(c) for c in validate(plan)]
    d = plans_dir if plans_dir is not None else PLANS
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{plan['id']}.json"
    n = 2
    while path.exists():
        path = d / f"{plan['id']}-{n}.json"
        n += 1
    path.write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
    plan["path"] = str(path)
    return plan


def show(plan):
    c = plan["complexity"]
    print(f"plan        {plan['path']}")
    print(f"subtasks    {len(plan['subtasks'])} · complexity {c['points']} "
          f"pts ({c['label']})")
    print(f"baseline    git {plan['rollback']['baseline'] or 'NONE'}")
    print("STEPS (topological order)")
    by_id = {s["id"]: s for s in plan["steps"]}
    for sid in plan["execution_order"]:
        s = by_id[sid]
        plug = f"[{s['plugin']}]" if s["plugin"] else ""
        print(f"  {sid:<8} {s['action']:<16} {plug:<14} test: {s['test']}")
        if s["risk"] != "-":
            print(f"           risk: {s['risk']}  rollback: {s['rollback']}")
    if plan["risks_known"]:
        print("KNOWN RISKS (fault ledger)")
        for r in plan["risks_known"]:
            print(f"  - {r}")
    print("APPROACHES")
    for a in plan["approaches"]:
        print(f"  - {a}")
    print("VALIDATION")
    for status, note in plan["validation"]:
        print(f"  {status:<5} {note}")


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        (v / "90_META").mkdir(parents=True)
        (v / "90_META" / "FAULT_LEDGER.md").write_text(
            "- [X][tags] indexer crash on empty frontmatter -> guard\n",
            encoding="utf-8")
        subs = decompose("add wikilinks to query output and fix the "
                         "indexer crash on startup")
        assert len(subs) == 2, subs
        plan = build("add wikilinks to query output and fix the indexer "
                     "crash on startup", vault=v, plans_dir=v / "plans")
        assert plan["complexity"]["points"] >= 4
        intents = {s["intent"] for s in plan["steps"]}
        assert "feature" in intents and "bug_fix" in intents, intents
        order = plan["execution_order"]
        assert order.index("t1.s1") < order.index("t1.s3"), "recall after impl"
        assert order[-1] == "commit", "commit not last"
        assert any("indexer crash" in r for r in plan["risks_known"]), \
            "ledger risk not mined"
        assert all(s["test"] and s["rollback"] for s in plan["steps"])
        assert ("ok", "plan is executable") in [tuple(c) for c in
                                                plan["validation"]]
        assert Path(plan["path"]).exists(), "plan not persisted"
        # law check fires on dependency talk
        p2 = build("install a pip package for parsing", vault=v,
                   plans_dir=v / "plans")
        assert any("stdlib-only" in n for _, n in p2["validation"])
        # cycle detection fails loud
        bad = {"request": "x", "steps": [
            {"id": "a", "depends_on": ["b"], "test": "t", "rollback": "r"},
            {"id": "b", "depends_on": ["a"], "test": "t", "rollback": "r"}],
            "complexity": {"label": "trivial"}, "rollback": {"baseline": "x"}}
        assert any(s == "fail" for s, _ in validate(bad)), "cycle not caught"
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Planning engine.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    pl = sub.add_parser("plan")
    pl.add_argument("request")
    pl.add_argument("--project", default="")
    pl.add_argument("--json", action="store_true", dest="as_json")
    va = sub.add_parser("validate")
    va.add_argument("path")
    args = ap.parse_args()

    if args.selftest:
        selftest()
    elif args.cmd == "plan":
        plan = build(args.request, args.project)
        print(json.dumps(plan, indent=1) if args.as_json else "", end="")
        if not args.as_json:
            show(plan)
    elif args.cmd == "validate":
        plan = json.loads(Path(args.path).read_text(encoding="utf-8"))
        for status, note in validate(plan):
            print(f"{status:<5} {note}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
