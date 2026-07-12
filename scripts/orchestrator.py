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
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# classify re-exported: five engines still import it from here.
from core import words_of, retrieve, stale, classify  # noqa: F401

VAULT = Path(__file__).resolve().parent.parent
TRACES = VAULT / "90_META" / "traces"
INDEX = VAULT / "90_META" / "INDEX.json"
MAX_RETRIES = 2

STRATEGY = {"trivial": "direct", "standard": "recall-execute-verify",
            "complex": "deep"}
PIPELINE = {
    "direct": ["RECALL", "EXECUTE", "VERIFY", "SUMMARIZE"],
    "recall-execute-verify": ["RECALL", "PLAN", "EXECUTE", "VERIFY",
                              "SUMMARIZE"],
    "deep": ["RECALL", "SIMILARITY", "PLAN", "EXECUTE", "VERIFY", "REVIEW",
             "SUMMARIZE"],
    # V3: gate said no LLM needed - deterministic tool chain does the work.
    "tool-direct": ["ROUTE", "EXECUTE", "VERIFY", "SUMMARIZE"],
}
# V3 token budgets (TOKEN.md): every request gets one before any engine
# runs. Downstream (context/promptc) clamps to its own 8k hard cap.
BUDGETS = {"trivial": 600, "standard": 3000, "complex": 12000}
RESEARCH_BUDGET = 20000
CACHE_HIT = 0.6  # vault note this similar = read it before spending tokens
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


def budget_for(intent, complexity):
    return RESEARCH_BUDGET if intent == "research" else BUDGETS[complexity]


def vault_hits(query, limit=5):
    """Shared vault retrieval (core.retrieve over the index)."""
    if not INDEX.exists():
        return []
    notes = json.loads(INDEX.read_text(encoding="utf-8"))["notes"]
    return retrieve(query, notes, limit=limit,
                    key=lambda n: f"{n['title']} {n['summary'] or ''} "
                                  f"{' '.join(n['tags'])}")


def gate(request, c):
    """V3 capability gate: is the LLM needed at all?
    Answer order = cheapest first: cached vault note, then a fully
    deterministic plugin chain (trivial only), then the model."""
    hits = vault_hits(request, limit=1)
    if hits and hits[0][0] >= CACHE_HIT:
        return {"llm": "cache-first",
                "reason": f"vault hit {hits[0][0]:.2f}: {hits[0][1]['path']}"}
    if c["complexity"] == "trivial":
        try:
            from plugins import route
            p = route(request, quiet=True)
            if p["chain"] and not p["uncovered"] and \
                    all(l["kind"] == "script" for l in p["chain"]):
                return {"llm": "none",
                        "reason": "deterministic chain: "
                                  + " -> ".join(l["name"] for l in p["chain"])}
        except SystemExit:
            pass  # no PLUGINS.json yet - gate stays conservative
    return {"llm": "required", "reason": ""}


def freshness():
    """V3 context cache: warn when a cached artifact is older than its
    sources instead of silently serving stale intelligence."""
    meta = VAULT / "90_META"
    scripts = list((VAULT / "scripts").glob("*.py"))
    warns = []
    if stale(meta / "PLUGINS.json", scripts):
        warns.append("PLUGINS.json stale - python scripts/plugins.py scan")
    if stale(meta / "GRAPH.json", scripts + [INDEX]):
        warns.append("GRAPH.json stale - python scripts/graph.py build")
    return warns


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
    g = gate(request, c)
    budget = budget_for(c["intent"], c["complexity"])
    strategy = ("tool-direct" if g["llm"] == "none"
                else STRATEGY[c["complexity"]])
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
        "budget": budget, "llm": g["llm"], "gate_reason": g["reason"],
        "transitions": [{"t": now(), "state": "CLASSIFY",
                         "note": f"{c['intent']}/{c['complexity']}"}],
        "retries": 0, "result": None,
    }
    save_trace(path, trace)
    print(f"intent      {c['intent']}"
          + ("  (AMBIGUOUS - confirm with user)" if c["ambiguous"] else ""))
    print(f"complexity  {c['complexity']}")
    print(f"strategy    {strategy}")
    print(f"budget      {budget} tokens")
    print(f"llm         {g['llm']}"
          + (f" ({g['reason']})" if g["reason"] else ""))
    print(f"engines     {', '.join(trace['engines'])}")
    print(f"pipeline    {' -> '.join(trace['pipeline'])}")
    for v in trace["verify"]:
        print(f"verify      - {v}")
    for w in freshness():
        print(f"STALE       {w}")
    if g["llm"] == "none":
        print(f'route       python scripts/plugins.py route "{request}"')
    else:
        q = f'python scripts/context.py pack "{request}" --budget {budget}'
        if project:
            q += f" --project {project}"
        print(f"recall      {q}")
        print(f'skills      python scripts/skills.py discover "{request}"')
        if c["complexity"] != "trivial":
            print(f'plan        python scripts/planner.py plan "{request}"')
        if c["complexity"] == "complex":
            print(f'agents      python scripts/agents.py run "{request}"')
        print(f'profile     python scripts/profiler.py report  (after close)')
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
    hits = vault_hits(query, limit)
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
    assert budget_for("bug_fix", "trivial") == 600
    assert budget_for("feature", "standard") == 3000
    assert budget_for("architecture", "complex") == 12000
    assert budget_for("research", "standard") == RESEARCH_BUDGET
    g = gate("redesign the entire retrieval architecture",
             {"intent": "architecture", "complexity": "complex"})
    assert g["llm"] in {"required", "cache-first"}  # complex never gates out
    with tempfile.TemporaryDirectory() as td:
        p = plan("fix the stale-date crash in review.py", traces_dir=Path(td))
        tr = load_trace(p)
        assert tr["budget"] == 3000 and tr["llm"] in {"required",
                                                      "cache-first", "none"}
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
