#!/usr/bin/env python3
"""ABSOLUTE ZERO multi-agent runtime. Stdlib only.

Eight role agents (planner, researcher, architect, implementer, reviewer,
tester, optimizer, coordinator). The coordinator composes a workflow DAG
dynamically per request (intent template per subtask, pruned/extended by
complexity), schedules it with dependency-aware parallel execution, gives
agents a versioned shared blackboard with conflict resolution, and a
message bus for agent-to-agent communication. Deterministic agents do real
work by driving the other engines; LLM-shaped steps come back as work
orders for Claude (the CPU). Run records in 90_META/runs/. Contract in
AGENTS.md.

  python scripts/agents.py compose "add wikilinks and fix the date crash"
  python scripts/agents.py run "add wikilinks and fix the date crash"
  python scripts/agents.py --selftest
"""
import argparse
import json
import queue
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from graphlib import TopologicalSorter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import classify, words_of
from orchestrator import VERIFY
from planner import ALTERNATIVES, LAWS, decompose, mine_risks

VAULT = Path(__file__).resolve().parent.parent
RUNS = VAULT / "90_META" / "runs"
MAX_WORKERS = 4
SUBPROC_TIMEOUT = 300

# Higher priority wins blackboard write conflicts.
PRIORITY = {"coordinator": 9, "reviewer": 8, "tester": 7, "architect": 6,
            "planner": 5, "optimizer": 4, "researcher": 3, "implementer": 2}

# Workflow templates per intent: (agent, depends_on other agents in the
# same subtask). Parallel siblings share dependencies.
WORKFLOWS = {
    "feature": [("planner", []), ("researcher", ["planner"]),
                ("architect", ["planner"]),
                ("implementer", ["researcher", "architect"]),
                ("reviewer", ["implementer"]), ("tester", ["implementer"])],
    "bug_fix": [("researcher", []), ("implementer", ["researcher"]),
                ("reviewer", ["implementer"]), ("tester", ["implementer"])],
    "quick_fix": [("implementer", []), ("tester", ["implementer"])],
    "research": [("researcher", [])],
    "architecture": [("planner", []), ("researcher", ["planner"]),
                     ("architect", ["planner", "researcher"]),
                     ("implementer", ["architect"]),
                     ("reviewer", ["implementer"]),
                     ("tester", ["implementer"])],
    "performance": [("researcher", []), ("optimizer", ["researcher"]),
                    ("implementer", ["optimizer"]),
                    ("tester", ["implementer"])],
    "security": [("researcher", []), ("reviewer", ["researcher"]),
                 ("implementer", ["reviewer"]), ("tester", ["implementer"])],
    "documentation": [("researcher", []), ("implementer", ["researcher"]),
                      ("reviewer", ["implementer"])],
    "deployment": [("planner", []), ("implementer", ["planner"]),
                   ("tester", ["implementer"]), ("reviewer", ["tester"])],
}
# Agents pruned from trivial subtasks (deps rewire transitively).
TRIVIAL_PRUNE = {"planner", "architect", "optimizer"}
# Agents guaranteed present on complex subtasks.
COMPLEX_EXTRA = ["planner", "architect", "optimizer"]


def now():
    return datetime.now().isoformat(timespec="seconds")


class Blackboard:
    """Shared memory: versioned keys, compare-and-swap writes, priority
    conflict resolution (lists merge instead of losing)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}
        self.conflicts = []

    def read(self, key):
        with self._lock:
            e = self._data.get(key)
            return dict(e) if e else None

    def write(self, key, value, writer, expected=None):
        """Returns True if the value landed. expected = version the writer
        read (CAS); None = unconditional append-style write."""
        with self._lock:
            cur = self._data.get(key)
            if cur and expected is not None and cur["version"] != expected:
                if isinstance(cur["value"], list) and isinstance(value, list):
                    merged = cur["value"] + [v for v in value
                                             if v not in cur["value"]]
                    self.conflicts.append(
                        {"t": now(), "key": key, "loser": None,
                         "writers": [cur["writer"], writer],
                         "resolution": "merged lists"})
                    self._data[key] = {"value": merged,
                                       "version": cur["version"] + 1,
                                       "writer": writer, "t": now()}
                    return True
                # ties keep the committed value: stale writer must re-read
                keep_cur = PRIORITY.get(cur["writer"], 0) >= \
                    PRIORITY.get(writer, 0)
                loser = writer if keep_cur else cur["writer"]
                self.conflicts.append(
                    {"t": now(), "key": key, "loser": loser,
                     "writers": [cur["writer"], writer],
                     "resolution": "priority: "
                                   + (cur["writer"] if keep_cur else writer)
                                   + " wins"})
                if keep_cur:
                    return False
            version = cur["version"] + 1 if cur else 1
            self._data[key] = {"value": value, "version": version,
                               "writer": writer, "t": now()}
            return True

    def snapshot(self):
        with self._lock:
            return {k: dict(v) for k, v in self._data.items()}


class Bus:
    """Agent communication: per-agent inbox queues + full message log."""

    def __init__(self):
        self._lock = threading.Lock()
        self._inboxes = {}
        self.log = []

    def _inbox(self, agent):
        with self._lock:
            return self._inboxes.setdefault(agent, queue.Queue())

    def send(self, sender, to, subject, body=""):
        msg = {"t": now(), "from": sender, "to": to,
               "subject": subject, "body": body}
        with self._lock:
            self.log.append(msg)
        self._inbox(to).put(msg)

    def broadcast(self, sender, subject, body=""):
        for a in PRIORITY:
            if a != sender:
                self.send(sender, a, subject, body)

    def drain(self, agent):
        box, out = self._inbox(agent), []
        while True:
            try:
                out.append(box.get_nowait())
            except queue.Empty:
                return out


# ---------------------------------------------------------------- agents
def planner_agent(ctx):
    from planner import build
    plan = build(ctx["subtask"], vault=ctx["vault"],
                 plans_dir=ctx["vault"] / "90_META" / "plans")
    fails = [n for s, n in plan["validation"] if s == "fail"]
    ctx["memory"].write(f"plan.{ctx['tid']}",
                        {"path": plan["path"],
                         "steps": plan["execution_order"],
                         "points": plan["complexity"]["points"]},
                        "planner")
    if fails:
        ctx["bus"].broadcast("planner", "plan gate FAIL", "; ".join(fails))
    return {"plan": plan["path"], "points": plan["complexity"]["points"],
            "gate_fails": fails}


def researcher_agent(ctx):
    vault, sub = ctx["vault"], ctx["subtask"]
    qw = set(words_of(sub))
    hits = []
    index = vault / "90_META" / "INDEX.json"
    if index.exists():
        notes = json.loads(index.read_text(encoding="utf-8"))["notes"]
        scored = []
        for n in notes:
            nw = set(words_of(n["title"] + " " + (n["summary"] or ""))) \
                | {t.lower() for t in n["tags"]}
            jac = len(qw & nw) / len(qw | nw) if qw | nw else 0
            scored.append((jac, n))
        scored.sort(key=lambda s: s[0], reverse=True)
        hits = [{"title": n["title"], "path": n["path"], "score": round(s, 2)}
                for s, n in scored[:5] if s >= 0.1]
    risks = mine_risks(sub, vault)
    ctx["memory"].write(f"findings.{ctx['tid']}",
                        {"notes": hits, "risks": risks}, "researcher")
    if risks:
        ctx["bus"].broadcast("researcher", "fault-ledger warning",
                             risks[0])
    return {"notes": hits, "risks": risks,
            "note": "vault empty" if not (hits or risks) else ""}


def architect_agent(ctx):
    import re as _re
    text = ctx["request"].lower()
    violations = [law for pat, law in LAWS if _re.search(pat, text)]
    alts = ALTERNATIVES.get(ctx["intent"], [])
    design = {"approach": alts[0] if alts else "direct",
              "alternatives": alts[1:], "law_warnings": violations}
    ctx["memory"].write(f"design.{ctx['tid']}", design, "architect")
    if violations:
        ctx["bus"].send("architect", "implementer", "law warning",
                        "; ".join(violations))
    return design


def implementer_agent(ctx):
    vault, sub = ctx["vault"], ctx["subtask"]
    try:
        from plugins import route
        chain = route(sub, vault=vault,
                      registry=vault / "90_META" / "PLUGINS.json",
                      quiet=True)["chain"]
    except SystemExit:
        chain = []
    touched = sorted(w + ".py" for w in set(words_of(sub))
                     if (vault / "scripts" / (w + ".py")).exists())
    ctx["memory"].write(f"touched.{ctx['tid']}", touched, "implementer")
    plan = ctx["memory"].read(f"plan.{ctx['tid']}")
    order = {"kind": "work-order", "subtask": sub, "intent": ctx["intent"],
             "steps": plan["value"]["steps"] if plan else [],
             "tools": [c["name"] for c in chain], "touched": touched}
    ctx["memory"].write(f"work_order.{ctx['tid']}", order, "implementer")
    ctx["bus"].send("implementer", "coordinator", "work order ready", sub)
    return order


def reviewer_agent(ctx):
    vault = ctx["vault"]
    verifier = vault / "scripts" / "verifier.py"
    dirty = ""
    if (vault / ".git").exists():
        r = subprocess.run(["git", "status", "--porcelain"], cwd=vault,
                           capture_output=True, text=True)
        dirty = r.stdout.strip()
    if dirty and verifier.exists():
        r = subprocess.run([sys.executable, str(verifier), "check"],
                           cwd=vault, capture_output=True, text=True,
                           timeout=SUBPROC_TIMEOUT)
        verdict = "PASS" if r.returncode == 0 else "FAIL"
        out = {"mode": "verifier", "verdict": verdict,
               "tail": r.stdout.strip().splitlines()[-3:]}
    else:
        out = {"mode": "checklist", "verdict": "PENDING",
               "checklist": VERIFY.get(ctx["intent"], [])}
    ctx["memory"].write(f"review.{ctx['tid']}", out, "reviewer")
    if out["verdict"] == "FAIL":
        ctx["bus"].send("reviewer", "coordinator", "verifier FAIL",
                        "retry EXECUTE per FLOW step 5")
        raise RuntimeError("verifier FAIL")
    return out


def tester_agent(ctx):
    vault = ctx["vault"]
    touched = ctx["memory"].read(f"touched.{ctx['tid']}")
    targets = (touched["value"] if touched else []) or []
    results = {}
    for name in targets:
        script = vault / "scripts" / name
        if not script.exists():
            continue
        r = subprocess.run([sys.executable, str(script), "--selftest"],
                           cwd=vault, capture_output=True, text=True,
                           timeout=SUBPROC_TIMEOUT)
        results[name] = "pass" if r.returncode == 0 else "FAIL"
    out = {"targets": results,
           "note": "" if results else "no runnable selftest targets"}
    ctx["memory"].write(f"tests.{ctx['tid']}", out, "tester")
    if "FAIL" in results.values():
        ctx["bus"].send("tester", "coordinator", "selftest FAIL",
                        ", ".join(k for k, v in results.items()
                                  if v == "FAIL"))
        raise RuntimeError("selftest FAIL: " + json.dumps(results))
    return out


def optimizer_agent(ctx):
    wf = ctx["vault"] / "90_META" / "experience" / "workflows.json"
    stats = json.loads(wf.read_text(encoding="utf-8")) if wf.exists() else {}
    mine = stats.get(ctx["intent"], {})
    advice = []
    runs, passed = mine.get("runs", 0), mine.get("pass", 0)
    if runs and passed < runs:
        advice.append(f"{ctx['intent']} pass rate {passed}/{runs} - "
                      "check FAULT_LEDGER before EXECUTE")
    if mine.get("retries", 0) > runs:
        advice.append("retry-heavy intent: verify earlier, smaller steps")
    out = {"stats": mine, "advice": advice or ["no history - proceed"]}
    ctx["memory"].write(f"optimization.{ctx['tid']}", out, "optimizer")
    return out


def coordinator_agent(ctx):
    mem = ctx["memory"].snapshot()
    orders = [v["value"] for k, v in mem.items()
              if k.startswith("work_order.")]
    summary = {"work_orders": orders,
               "conflicts": len(ctx["memory"].conflicts),
               "messages": ctx["bus"].drain("coordinator"),
               "keys": sorted(mem)}
    ctx["memory"].write("summary", summary, "coordinator")
    return summary


HANDLERS = {"planner": planner_agent, "researcher": researcher_agent,
            "architect": architect_agent, "implementer": implementer_agent,
            "reviewer": reviewer_agent, "tester": tester_agent,
            "optimizer": optimizer_agent, "coordinator": coordinator_agent}


# ---------------------------------------------------- dynamic composition
def compose(request):
    """Coordinator's planning act: intent template per subtask, pruned for
    trivial / extended for complex, joined by a final coordinator node."""
    subtasks = decompose(request)
    nodes = []
    for ti, sub in enumerate(subtasks, 1):
        c = classify(sub)
        template = list(WORKFLOWS[c["intent"]])
        if c["complexity"] == "trivial":
            keep = {a for a, _ in template} - TRIVIAL_PRUNE
            deps = {a: set(d) for a, d in template}
            for gone in {a for a, _ in template} - keep:
                for a in deps:
                    if gone in deps[a]:
                        deps[a] = (deps[a] - {gone}) | (deps[gone] & keep)
            template = [(a, sorted(deps[a] & keep))
                        for a, _ in template if a in keep]
        elif c["complexity"] == "complex":
            have = {a for a, _ in template}
            sinks = sorted(have - {d for _, ds in template for d in ds})
            for extra in COMPLEX_EXTRA:
                if extra not in have:
                    template.append((extra, sinks))
        for agent, deps in template:
            nodes.append({"id": f"t{ti}.{agent}", "agent": agent,
                          "subtask": sub, "intent": c["intent"],
                          "complexity": c["complexity"], "tid": f"t{ti}",
                          "depends_on": [f"t{ti}.{d}" for d in deps]})
    all_ids = {n["id"] for n in nodes}
    sinks = sorted(all_ids - {d for n in nodes for d in n["depends_on"]})
    nodes.append({"id": "coordinator", "agent": "coordinator",
                  "subtask": request, "intent": "-", "complexity": "-",
                  "tid": "run", "depends_on": sinks})
    return {"request": request, "subtasks": subtasks, "nodes": nodes}


# ---------------------------------------------------------------- runtime
def execute(workflow, vault=VAULT, handlers=None, max_workers=MAX_WORKERS,
            runs_dir=None):
    handlers = handlers or HANDLERS
    memory, bus = Blackboard(), Bus()
    by_id = {n["id"]: n for n in workflow["nodes"]}
    ts = TopologicalSorter({n["id"]: set(n["depends_on"])
                            for n in workflow["nodes"]})
    ts.prepare()
    results, failed, intervals = {}, set(), {}
    t0 = time.perf_counter()  # monotonic() ticks ~15ms on Windows

    def run_node(node):
        ctx = {"request": workflow["request"], "subtask": node["subtask"],
               "intent": node["intent"], "complexity": node["complexity"],
               "node": node["id"], "agent": node["agent"],
               "tid": node["tid"], "memory": memory, "bus": bus,
               "vault": vault, "inbox": bus.drain(node["agent"])}
        return handlers[node["agent"]](ctx)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        while ts.is_active():
            for nid in ts.get_ready():
                node = by_id[nid]
                if any(d in failed for d in node["depends_on"]):
                    failed.add(nid)
                    results[nid] = {"status": "skipped",
                                    "error": "dependency failed"}
                    ts.done(nid)
                    continue
                start = time.perf_counter() - t0
                fut = pool.submit(run_node, node)
                futures[fut] = (nid, start)
            if not futures:
                continue
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for fut in done:
                nid, start = futures.pop(fut)
                end = time.perf_counter() - t0
                intervals[nid] = (start, end)
                try:
                    results[nid] = {"status": "done", "output": fut.result(),
                                    "ms": int((end - start) * 1000)}
                    for n in workflow["nodes"]:
                        if nid in n["depends_on"]:
                            bus.send(by_id[nid]["agent"], n["agent"],
                                     f"{nid} done", "input ready")
                except Exception as e:  # agent failure is data, not a crash
                    failed.add(nid)
                    results[nid] = {"status": "fail", "error": str(e),
                                    "ms": int((end - start) * 1000)}
                ts.done(nid)

    # starts sort before ends at equal timestamps or zero-length
    # intervals never count as overlapping
    events = sorted([(s, 1) for s, _ in intervals.values()]
                    + [(e, -1) for _, e in intervals.values()],
                    key=lambda ev: (ev[0], -ev[1]))
    peak = cur = 0
    for _, d in events:
        cur += d
        peak = max(peak, cur)
    record = {
        "id": f"{datetime.now():%Y-%m-%d}-"
              + ("-".join(words_of(workflow["request"])[:5]) or "run"),
        "request": workflow["request"], "subtasks": workflow["subtasks"],
        "workflow": workflow["nodes"], "results": results,
        "messages": bus.log, "conflicts": memory.conflicts,
        "memory": memory.snapshot(), "max_parallel": peak,
        "verdict": "fail" if failed else "pass",
    }
    d = runs_dir if runs_dir is not None else RUNS
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{record['id']}.json"
    n = 2
    while path.exists():
        path = d / f"{record['id']}-{n}.json"
        n += 1
    path.write_text(json.dumps(record, indent=1, default=str) + "\n",
                    encoding="utf-8")
    record["path"] = str(path)
    return record


def show(record):
    print(f"run         {record['path']}")
    print(f"verdict     {record['verdict']}   "
          f"max parallel {record['max_parallel']}   "
          f"conflicts {len(record['conflicts'])}   "
          f"messages {len(record['messages'])}")
    for n in record["workflow"]:
        r = record["results"].get(n["id"], {})
        mark = {"done": "ok  ", "fail": "FAIL", "skipped": "skip"}.get(
            r.get("status"), "?   ")
        print(f"  {mark} {n['id']:<18} deps: "
              f"{', '.join(n['depends_on']) or '-'}"
              + (f"  ({r['ms']} ms)" if "ms" in r else ""))
        if r.get("error"):
            print(f"       error: {r['error']}")
    summary = record["memory"].get("summary", {}).get("value", {})
    for o in summary.get("work_orders", []):
        print(f"  WORK ORDER [{o['intent']}] {o['subtask']}")
        print(f"       tools: {', '.join(o['tools']) or '-'}   "
              f"touched: {', '.join(o['touched']) or '-'}")


def show_workflow(wf):
    print(f"subtasks    {len(wf['subtasks'])}")
    for n in wf["nodes"]:
        print(f"  {n['id']:<18} [{n['intent']}/{n['complexity']}] deps: "
              f"{', '.join(n['depends_on']) or '-'}")


# --------------------------------------------------------------- selftest
def selftest():
    import tempfile

    # dynamic composition: complex gets architect+optimizer, trivial prunes
    wf = compose("redesign the entire retrieval architecture")
    agents = {n["agent"] for n in wf["nodes"]}
    assert {"planner", "architect", "optimizer", "coordinator"} <= agents, agents
    wf = compose("fix typo in readme")
    agents = {n["agent"] for n in wf["nodes"]}
    assert "planner" not in agents and "architect" not in agents, agents
    assert "implementer" in agents and "tester" in agents
    t = {n["agent"]: n for n in wf["nodes"]}
    assert t["tester"]["depends_on"] == ["t1.implementer"], "deps not rewired"

    # two subtasks = parallel branches, coordinator joins the sinks
    wf = compose("add wikilinks to query output and fix the indexer "
                 "crash on startup")
    tids = {n["tid"] for n in wf["nodes"]}
    assert {"t1", "t2", "run"} == tids, tids
    cross = [n for n in wf["nodes"] if n["tid"] == "t1"
             and any(d.startswith("t2.") for d in n["depends_on"])]
    assert not cross, "branches must be independent"
    assert wf["nodes"][-1]["agent"] == "coordinator"

    # blackboard: versions, CAS conflict, priority, list merge
    bb = Blackboard()
    assert bb.write("k", "a", "implementer")
    assert not bb.write("k", "b", "implementer", expected=0), "stale CAS won"
    assert bb.read("k")["value"] == "a" and bb.conflicts, "conflict unlogged"
    assert bb.write("k", "c", "reviewer", expected=0), "priority lost"
    assert bb.read("k")["value"] == "c" and bb.read("k")["version"] == 2
    bb.write("l", [1, 2], "researcher")
    bb.write("l", [2, 3], "planner", expected=0)
    assert bb.read("l")["value"] == [1, 2, 3], "lists not merged"

    # bus: send, drain, broadcast
    bus = Bus()
    bus.send("planner", "tester", "hi")
    assert bus.drain("tester")[0]["subject"] == "hi"
    assert bus.drain("tester") == []
    bus.broadcast("coordinator", "all hands")
    assert len(bus.log) == len(PRIORITY)  # 1 send + 7 broadcast
    assert bus.drain("planner")[0]["subject"] == "all hands"

    # scheduler: true parallelism (barrier passes only if concurrent),
    # dependency order, failure skips descendants
    barrier = threading.Barrier(2, timeout=10)
    order = []
    lock = threading.Lock()

    def par(ctx):
        barrier.wait()  # deadlocks (then breaks) if scheduler is serial
        with lock:
            order.append(ctx["node"])
        return {}

    def rec(ctx):
        with lock:
            order.append(ctx["node"])
        return {}

    def boom(ctx):
        raise RuntimeError("boom")

    wf = {"request": "parallel proof", "subtasks": ["x"], "nodes": [
        {"id": "a", "agent": "researcher", "subtask": "x", "intent": "-",
         "complexity": "-", "tid": "t1", "depends_on": []},
        {"id": "b", "agent": "architect", "subtask": "x", "intent": "-",
         "complexity": "-", "tid": "t1", "depends_on": []},
        {"id": "c", "agent": "implementer", "subtask": "x", "intent": "-",
         "complexity": "-", "tid": "t1", "depends_on": ["a", "b"]},
        {"id": "d", "agent": "tester", "subtask": "x", "intent": "-",
         "complexity": "-", "tid": "t1", "depends_on": ["c"]},
    ]}
    with tempfile.TemporaryDirectory() as td:
        h = {"researcher": par, "architect": par, "implementer": rec,
             "tester": boom}
        r = execute(wf, vault=Path(td), handlers=h, runs_dir=Path(td))
        assert r["max_parallel"] >= 2, "never ran two agents at once"
        assert order.index("c") > max(order.index("a"), order.index("b"))
        assert r["results"]["d"]["status"] == "fail"
        assert r["verdict"] == "fail"
        h["tester"] = rec
        wf["nodes"].append({"id": "e", "agent": "optimizer", "subtask": "x",
                            "intent": "-", "complexity": "-", "tid": "t1",
                            "depends_on": ["d"]})
        h["optimizer"] = rec
        h["implementer"] = boom
        barrier = threading.Barrier(2, timeout=10)
        order = []
        r = execute(wf, vault=Path(td), handlers=h, runs_dir=Path(td))
        assert r["results"]["d"]["status"] == "skipped", "descendant ran"
        assert r["results"]["e"]["status"] == "skipped", "transitive ran"

    # full run with real agents on a temp vault (no index, no registry)
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        (v / "90_META").mkdir(parents=True)
        (v / "90_META" / "FAULT_LEDGER.md").write_text(
            "- [X][query] query crash on empty tags -> guard\n",
            encoding="utf-8")
        wf = compose("add a summary flag to the query script")
        r = execute(wf, vault=v, runs_dir=v / "runs")
        assert r["verdict"] == "pass", json.dumps(r["results"], default=str)
        assert Path(r["path"]).exists(), "record not persisted"
        summary = r["memory"]["summary"]["value"]
        assert summary["work_orders"], "no work order for the CPU"
        assert any(m["subject"] == "fault-ledger warning"
                   for m in r["messages"]), "researcher never warned"
        assert any(k.startswith("plan.") for k in r["memory"]), "no plan"
    print("selftest OK")


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Multi-agent runtime.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    co = sub.add_parser("compose")
    co.add_argument("request")
    co.add_argument("--json", action="store_true", dest="as_json")
    ru = sub.add_parser("run")
    ru.add_argument("request")
    ru.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    if args.selftest:
        selftest()
    elif args.cmd == "compose":
        wf = compose(args.request)
        print(json.dumps(wf, indent=1)) if args.as_json else show_workflow(wf)
    elif args.cmd == "run":
        record = execute(compose(args.request))
        print(json.dumps(record, indent=1, default=str)) if args.as_json \
            else show(record)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
