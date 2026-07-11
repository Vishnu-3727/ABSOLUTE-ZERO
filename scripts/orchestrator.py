#!/usr/bin/env python3
"""ABSOLUTE ZERO workflow orchestrator. Stdlib only.

Central runtime of the OS: every user request is classified (intent,
complexity), mapped to a strategy + engine set, and tracked as a
state-machine trace in 90_META/traces/. Claude executes the pipeline;
this script is the deterministic plumbing: classify, plan, enforce legal
transitions, log, close. Full contract in ORCHESTRATOR.md.

  python scripts/orchestrator.py plan "fix the stale-date crash in review.py"
  python scripts/orchestrator.py log --trace <file> --state EXECUTE --note "patched"
  python scripts/orchestrator.py close --trace <file> --result pass --summary "done"
  python scripts/orchestrator.py similarity "gps denied navigation drift"
  python scripts/orchestrator.py --selftest
"""
import argparse
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
TRACES = VAULT / "90_META" / "traces"
INDEX = VAULT / "90_META" / "INDEX.json"
MAX_RETRIES = 2

# Dict order is tie-break priority: first listed wins on equal score.
INTENT_KEYWORDS = {
    "security": ["security", "vulnerability", "vuln", "auth", "injection",
                 "secret", "cve", "exploit", "permission", "harden"],
    "deployment": ["deploy", "release", "ship", "ci", "docker", "systemd",
                   "publish", "install", "flash", "provision"],
    "quick_fix": ["typo", "rename", "tweak", "bump", "quick", "trivial"],
    "performance": ["slow", "performance", "optimize", "optimise", "latency",
                    "memory", "profile", "speed", "throughput"],
    "architecture": ["architecture", "redesign", "restructure", "refactor",
                     "decouple", "orchestrator", "state machine"],
    "research": ["research", "investigate", "compare", "evaluate", "survey",
                 "which", "options", "feasibility"],
    "documentation": ["document", "documentation", "docs", "readme",
                      "comment", "explain", "guide", "writeup"],
    "bug_fix": ["bug", "fix", "crash", "error", "broken", "fails", "failing",
                "exception", "traceback", "regression", "wrong", "debug"],
    "feature": ["add", "implement", "feature", "build", "create", "support",
                "new", "extend"],
}
COMPLEX_WORDS = ["entire", "redesign", "architecture", "migrate", "overhaul",
                 "across", "system-wide", "production-ready", "framework"]
TRIVIAL_WORDS = ["typo", "rename", "bump", "one line", "one-line", "quick"]

STRATEGY = {"trivial": "direct", "standard": "recall-execute-verify",
            "complex": "deep"}
PIPELINE = {
    "direct": ["RECALL", "EXECUTE", "VERIFY", "SUMMARIZE"],
    "recall-execute-verify": ["RECALL", "PLAN", "EXECUTE", "VERIFY",
                              "SUMMARIZE"],
    "deep": ["RECALL", "SIMILARITY", "PLAN", "EXECUTE", "VERIFY", "REVIEW",
             "SUMMARIZE"],
}
# Engines: knowledge, experience, similarity, skills, audit, dashboard.
# Context management (token budgets) is always on and not listed.
ENGINES = {
    "quick_fix": ["experience"],
    "bug_fix": ["experience", "knowledge", "audit"],
    "feature": ["knowledge", "experience", "skills"],
    "architecture": ["knowledge", "experience", "similarity"],
    "research": ["knowledge", "similarity"],
    "documentation": ["knowledge", "dashboard"],
    "performance": ["experience", "knowledge"],
    "security": ["experience", "knowledge", "audit"],
    "deployment": ["experience", "audit"],
}
VERIFY = {
    "quick_fix": ["change applied", "nothing else touched"],
    "bug_fix": ["root cause named, not symptom",
                "fix exercised (test or run)",
                "FAULTS.md entry with topic wikilink"],
    "feature": ["works end to end", "one runnable check left behind",
                "docs/notes updated if behavior changed"],
    "architecture": ["written plan agreed before edits",
                     "boundaries documented",
                     "review.py clean (no new orphans)"],
    "research": ["sources cited with URLs",
                 "note in 40_RESEARCH with frontmatter",
                 "5-line digest reported"],
    "documentation": ["accurate against current code",
                      "frontmatter + reindexed"],
    "performance": ["baseline measured before", "improvement measured after",
                    "no correctness regression"],
    "security": ["threat named", "fix verified", "no secrets committed"],
    "deployment": ["dry-run or staged first", "rollback path stated",
                   "post-deploy check passes"],
}


def words_of(text):
    return re.findall(r"[a-z0-9][a-z0-9_-]*", text.lower())


def classify(request):
    text = request.lower()
    have = set(words_of(text))
    best, best_score = "feature", 0
    for intent, keys in INTENT_KEYWORDS.items():
        # prefix match so secrets/secret, failing/fails etc. all hit
        score = sum(1 for k in keys
                    if (any(w.startswith(k) for w in have)
                        if " " not in k else k in text))
        if score > best_score:
            best, best_score = intent, score
    ambiguous = best_score == 0
    high = (best == "architecture" or len(have) > 60
            or any(w in text for w in COMPLEX_WORDS))
    low = best == "quick_fix" or any(w in text for w in TRIVIAL_WORDS)
    complexity = "complex" if high else ("trivial" if low else "standard")
    return {"intent": best, "complexity": complexity, "ambiguous": ambiguous}


def known_tags():
    if not INDEX.exists():
        return set()
    notes = json.loads(INDEX.read_text(encoding="utf-8"))["notes"]
    return {t.lower() for n in notes for t in n["tags"]}


def now():
    return datetime.now().isoformat(timespec="seconds")


def load_trace(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_trace(path, trace):
    Path(path).write_text(json.dumps(trace, indent=1) + "\n", encoding="utf-8")


def plan(request, project="", traces_dir=TRACES):
    c = classify(request)
    strategy = STRATEGY[c["complexity"]]
    tags = sorted(known_tags() & set(words_of(request)))
    slug = "-".join(words_of(request)[:5]) or "task"
    tid = f"{datetime.now():%Y-%m-%d}-{slug}"
    traces_dir.mkdir(parents=True, exist_ok=True)
    path = traces_dir / f"{tid}.json"
    n = 2
    while path.exists():
        path = traces_dir / f"{tid}-{n}.json"
        n += 1
    trace = {
        "id": path.stem, "request": request, "project": project,
        "intent": c["intent"], "complexity": c["complexity"],
        "strategy": strategy, "engines": ENGINES[c["intent"]],
        "pipeline": PIPELINE[strategy], "verify": VERIFY[c["intent"]],
        "recall_tags": tags, "ambiguous": c["ambiguous"],
        "transitions": [{"t": now(), "state": "CLASSIFY",
                         "note": f"{c['intent']}/{c['complexity']}"}],
        "retries": 0, "result": None,
    }
    save_trace(path, trace)
    print(f"intent      {c['intent']}"
          + ("  (AMBIGUOUS - confirm with user)" if c["ambiguous"] else ""))
    print(f"complexity  {c['complexity']}")
    print(f"strategy    {strategy}")
    print(f"engines     {', '.join(trace['engines'])}")
    print(f"pipeline    {' -> '.join(trace['pipeline'])}")
    for v in trace["verify"]:
        print(f"verify      - {v}")
    q = f'python scripts/context.py pack "{request}"'
    if project:
        q += f" --project {project}"
    print(f"recall      {q}")
    print(f'skills      python scripts/skills.py discover "{request}"')
    if c["complexity"] != "trivial":
        print(f'plan        python scripts/planner.py plan "{request}"')
    print(f"trace       {path.relative_to(VAULT) if path.is_relative_to(VAULT) else path}")
    return path


def allowed_states(trace):
    pipe = trace["pipeline"]
    visited = [t["state"] for t in trace["transitions"] if t["state"] in pipe]
    if not visited:
        return {pipe[0]}
    i = pipe.index(visited[-1])
    out = {pipe[i + 1]} if i + 1 < len(pipe) else set()
    if visited[-1] == "VERIFY" and trace["retries"] < MAX_RETRIES:
        out.add("EXECUTE")  # retry loop
    return out


def log(path, state, note=""):
    trace = load_trace(path)
    if trace["result"] is not None:
        raise SystemExit(f"trace already closed ({trace['result']})")
    ok = allowed_states(trace)
    if state not in ok:
        raise SystemExit(f"illegal transition to {state}; "
                         f"allowed: {', '.join(sorted(ok)) or 'none (close it)'}")
    visited = [t["state"] for t in trace["transitions"]]
    if state == "EXECUTE" and "VERIFY" in visited:
        trace["retries"] += 1
    trace["transitions"].append({"t": now(), "state": state, "note": note})
    save_trace(path, trace)
    print(f"{trace['id']}: -> {state}"
          + (f" (retry {trace['retries']}/{MAX_RETRIES})"
             if state == "EXECUTE" and trace["retries"] else ""))


def close(path, result, summary=""):
    trace = load_trace(path)
    if trace["result"] is not None:
        raise SystemExit(f"trace already closed ({trace['result']})")
    visited = [t["state"] for t in trace["transitions"]]
    if result == "pass" and "SUMMARIZE" not in visited:
        raise SystemExit("close pass requires SUMMARIZE logged first")
    final = "DONE" if result == "pass" else "ESCALATED"
    trace["result"] = result
    trace["transitions"].append({"t": now(), "state": final, "note": summary})
    save_trace(path, trace)
    print(f"{trace['id']}: {final}")


def similarity(query, limit=5):
    if not INDEX.exists():
        raise SystemExit("no INDEX.json - run scripts/indexer.py first")
    notes = json.loads(INDEX.read_text(encoding="utf-8"))["notes"]
    q = query.lower()
    qw = set(words_of(q))
    scored = []
    for n in notes:
        title, summary = n["title"].lower(), (n["summary"] or "").lower()
        nw = set(words_of(title + " " + summary)) | {t.lower() for t in n["tags"]}
        jac = len(qw & nw) / len(qw | nw) if qw | nw else 0
        ratio = max(SequenceMatcher(None, q, title).ratio(),
                    SequenceMatcher(None, q, summary).ratio())
        scored.append((max(jac, ratio), n))
    scored.sort(key=lambda s: s[0], reverse=True)
    hits = [(s, n) for s, n in scored[:limit] if s >= 0.15]
    if not hits:
        print("not in vault")
        return
    for s, n in hits:
        print(f"{s:.2f}  {n['title']}  [{n['type']}/{n['project']}]")
        print(f"      {n['path']}")


def selftest():
    import tempfile
    cases = {
        "fix typo in readme": ("quick_fix", "trivial"),
        "debug the crash when indexer hits empty frontmatter": ("bug_fix", "standard"),
        "add wikilink support to query output": ("feature", "standard"),
        "redesign the entire retrieval architecture": ("architecture", "complex"),
        "research vision-based landing options": ("research", "standard"),
        "write a readme guide for the scripts": ("documentation", "standard"),
        "the indexer is slow, optimize the frontmatter parse": ("performance", "standard"),
        "audit for hardcoded secrets before pushing": ("security", "standard"),
        "deploy the nightly systemd timer": ("deployment", "standard"),
    }
    for req, (intent, cx) in cases.items():
        c = classify(req)
        assert (c["intent"], c["complexity"]) == (intent, cx), \
            f"{req!r} -> {c['intent']}/{c['complexity']}, want {intent}/{cx}"
    assert classify("hello there")["ambiguous"]
    with tempfile.TemporaryDirectory() as td:
        p = plan("fix the stale-date crash in review.py", traces_dir=Path(td))
        for bad in ("EXECUTE", "SUMMARIZE"):  # must start at RECALL
            try:
                log(p, bad)
                raise AssertionError("illegal transition accepted")
            except SystemExit:
                pass
        for st in ("RECALL", "PLAN", "EXECUTE", "VERIFY"):
            log(p, st)
        log(p, "EXECUTE", "retry after verify fail")
        log(p, "VERIFY")
        try:
            close(p, "pass")
            raise AssertionError("closed pass before SUMMARIZE")
        except SystemExit:
            pass
        log(p, "SUMMARIZE")
        close(p, "pass", "selftest lifecycle")
        assert load_trace(p)["retries"] == 1
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Workflow orchestrator.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("plan")
    p.add_argument("request")
    p.add_argument("--project", default="")
    lg = sub.add_parser("log")
    lg.add_argument("--trace", required=True)
    lg.add_argument("--state", required=True)
    lg.add_argument("--note", default="")
    cl = sub.add_parser("close")
    cl.add_argument("--trace", required=True)
    cl.add_argument("--result", required=True, choices=["pass", "fail"])
    cl.add_argument("--summary", default="")
    sm = sub.add_parser("similarity")
    sm.add_argument("query")
    sm.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    if args.selftest:
        selftest()
    elif args.cmd == "plan":
        plan(args.request, args.project)
    elif args.cmd == "log":
        log(args.trace, args.state, args.note)
    elif args.cmd == "close":
        close(args.trace, args.result, args.summary)
    elif args.cmd == "similarity":
        similarity(args.query, args.limit)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
