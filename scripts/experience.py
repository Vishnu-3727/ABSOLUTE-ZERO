#!/usr/bin/env python3
"""ABSOLUTE ZERO experience learning engine. Stdlib only.

Learns from every completed task. Raw material the OS already produces:
closed traces (a VERIFY-fail note + its retry note is a symptom->fix pair;
transition timestamps are durations), FAULTS ledgers, and the scripts/
corpus itself. Harvest extracts: lessons (drafted into 30_LESSONS/, deduped
against existing ones), failures (appended to the project FAULTS.md),
successful workflows (per-intent stats: runs, pass rate, retries, seconds),
reusable code (near-duplicate functions across scripts, ast+difflib), and
architectural patterns (motif counts across the corpus). Store:
90_META/experience/ + real lesson notes. Retrieval: `recall` ranks lessons,
workflows and patterns semantically (stemmed jaccard + difflib). Harvest is
idempotent: traces are marked harvested. Contract in EXPERIENCE.md.

  python scripts/experience.py harvest            all unharvested traces
  python scripts/experience.py harvest --trace 90_META/traces/x.json
  python scripts/experience.py recall "state machine retry"
  python scripts/experience.py --selftest
"""
import argparse
import ast
import json
import re
import sys
from datetime import datetime, date
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchestrator import words_of
from context import STOP, jaccard
from promptc import stem

VAULT = Path(__file__).resolve().parent.parent
EXP = VAULT / "90_META" / "experience"
LESSON_DEDUP = 0.5
CODE_DUP = 0.75
MOTIF_MIN = 3  # scripts sharing a motif before it counts as a pattern
MOTIFS = [
    ("selftest-guard", r"--selftest",
     "every script carries a runnable self-check"),
    ("docstring-contract", r'^#!/usr/bin/env python3\n"""',
     "shebang + docstring states the contract and usage up top"),
    ("data-table-config", r"^[A-Z_]{3,} = [\{\[]",
     "behavior encoded in module-level data tables, not branches"),
    ("artifact-dir", r"90_META",
     "runtime artifacts live under 90_META, committed, never indexed"),
    ("argparse-subcommands", r"add_parser\(",
     "CLI verbs via argparse subcommands"),
    ("fail-loud", r"SystemExit",
     "errors raise loudly instead of returning silently (P1)"),
    ("shared-kernel", r"^from (orchestrator|context|plugins|promptc) import",
     "engines import each other's primitives instead of duplicating"),
]


def nwords(text):
    return {stem(w) for w in words_of(text)} - STOP


def sim(a, b):
    return max(jaccard(nwords(a), nwords(b)),
               SequenceMatcher(None, a.lower()[:200], b.lower()[:200]).ratio())


def load_json(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def dump_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")


def secs(a, b):
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)) \
            .total_seconds()
    except ValueError:
        return 0


# -- extraction ------------------------------------------------------------
def lesson_pairs(trace):
    """VERIFY-fail note followed by a retry EXECUTE note = symptom -> fix."""
    out, tr = [], trace["transitions"]
    for i, t in enumerate(tr[:-1]):
        if t["state"] == "VERIFY" and tr[i + 1]["state"] == "EXECUTE":
            symptom = t.get("note") or "verify failed"
            fix = tr[i + 1].get("note") or "retried"
            out.append((symptom, fix))
    return out


def existing_lessons(vault):
    out = []
    d = vault / "30_LESSONS"
    if d.is_dir():
        for p in d.glob("*.md"):
            m = re.search(r"^summary:\s*(.+)$",
                          p.read_text(encoding="utf-8"), re.MULTILINE)
            out.append(m.group(1) if m else p.stem)
    return out


def draft_lesson(trace, symptom, fix, vault):
    summary = f"{symptom.split(' - ')[0][:80]} -> {fix[:60]}"
    if any(sim(summary, e) > LESSON_DEDUP for e in existing_lessons(vault)):
        return None
    slug = "-".join(words_of(fix)[:4]) or trace["id"][-20:]
    p = vault / "30_LESSONS" / f"{slug}.md"
    if p.exists():
        return None
    tags = sorted(set(trace.get("recall_tags", []))
                  | {trace["intent"].replace("_", "-")})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\ntags: [{', '.join(tags)}]\n"
        f"project: {trace.get('project') or 'ABSOLUTE_ZERO'}\n"
        f"status: draft\nconfidence: low\ndate: {date.today()}\n"
        f"summary: {summary}\n---\n\n# {fix[:70]}\n\n"
        f"- **Symptom:** {symptom}\n- **Fix:** {fix}\n"
        f"- **Evidence:** trace `90_META/traces/{trace['id']}.json` "
        f"(auto-harvested; promote via /review)\n", encoding="utf-8")
    return p


def record_failure(trace, vault):
    proj = trace.get("project") or "ABSOLUTE_ZERO"
    p = vault / "10_PROJECTS" / proj / "FAULTS.md"
    if not p.exists():
        return None
    last = trace["transitions"][-1].get("note", "")
    entry = (f"\n## {date.today()} — task escalated: {trace['id']}\n"
             f"- **Symptom:** {trace['request'][:120]}\n"
             f"- **Outcome:** closed fail after {trace.get('retries', 0)} "
             f"retries; {last[:150]} ([[debugging-silent-failures]])\n")
    p.write_text(p.read_text(encoding="utf-8") + entry, encoding="utf-8")
    return p


def update_workflows(trace, wf):
    tr = trace["transitions"]
    e = wf.setdefault(trace["intent"],
                      {"runs": 0, "pass": 0, "retries": 0, "seconds": 0,
                       "pipeline": trace.get("pipeline", []), "examples": []})
    e["runs"] += 1
    e["pass"] += trace.get("result") == "pass"
    e["retries"] += trace.get("retries", 0)
    e["seconds"] += round(secs(tr[0]["t"], tr[-1]["t"]))
    e["examples"] = (e["examples"] + [trace["id"]])[-5:]


def reusable_code(vault):
    """Near-duplicate functions across scripts: extract-to-shared candidates."""
    funcs = []
    for p in sorted((vault / "scripts").glob("*.py")):
        src = p.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for n in tree.body:
            if isinstance(n, ast.FunctionDef):
                funcs.append((p.name, n.name,
                              ast.get_source_segment(src, n) or ""))
    # main/selftest are the OS convention (every script has them by law) -
    # same name there is a pattern, not duplication. Bodies must match.
    convention = {"main", "selftest"}
    groups = {}
    for i, (f1, n1, s1) in enumerate(funcs):
        if n1 in convention:
            continue
        for f2, n2, s2 in funcs[i + 1:]:
            if f1 == f2 or n2 in convention:
                continue
            if SequenceMatcher(None, s1, s2).ratio() > CODE_DUP:
                key = n1 if n1 == n2 else f"{n1}/{n2}"
                groups.setdefault(key, set()).update((f1, f2))
    return [{"function": k, "files": sorted(v),
             "advice": "extract to a shared module or import one from "
                       "the other"} for k, v in sorted(groups.items())]


def architectural_patterns(vault):
    counts = {}
    for name, pat, desc in MOTIFS:
        hits = [p.name for p in sorted((vault / "scripts").glob("*.py"))
                if re.search(pat, p.read_text(encoding="utf-8"),
                             re.MULTILINE)]
        if len(hits) >= MOTIF_MIN:
            counts[name] = {"description": desc, "scripts": hits,
                            "count": len(hits)}
    return counts


# -- driver ------------------------------------------------------------
def harvest(vault=VAULT, only=None):
    traces_dir = vault / "90_META" / "traces"
    exp = vault / "90_META" / "experience"
    wf = load_json(exp / "workflows.json", {})
    report = {"lessons": [], "failures": [], "workflows": 0,
              "reusable_code": [], "patterns": {}}
    targets = [Path(only)] if only else sorted(traces_dir.glob("*.json")) \
        if traces_dir.is_dir() else []
    for tp in targets:
        trace = load_json(tp if tp.is_absolute() else vault / tp, None)
        if not trace or trace.get("result") is None \
                or trace.get("harvested"):
            continue
        for symptom, fix in lesson_pairs(trace):
            p = draft_lesson(trace, symptom, fix, vault)
            if p:
                report["lessons"].append(str(p.relative_to(vault)))
        if trace["result"] == "fail":
            p = record_failure(trace, vault)
            if p:
                report["failures"].append(trace["id"])
        update_workflows(trace, wf)
        report["workflows"] += 1
        trace["harvested"] = True
        dump_json(tp if tp.is_absolute() else vault / tp, trace)
    dump_json(exp / "workflows.json", wf)
    report["reusable_code"] = reusable_code(vault)
    report["patterns"] = architectural_patterns(vault)
    dump_json(exp / "patterns.json", report["patterns"])
    return report


def recall(query, vault=VAULT, limit=8):
    """Semantic retrieval over everything harvested."""
    exp = vault / "90_META" / "experience"
    hits = []
    lessons = vault / "30_LESSONS"
    if lessons.is_dir():  # direct scan: drafts exist before any reindex
        for p in lessons.glob("*.md"):
            text = p.read_text(encoding="utf-8")
            m = re.search(r"^summary:\s*(.+)$", text, re.MULTILINE)
            t = re.search(r"^tags:\s*\[(.*)\]$", text, re.MULTILINE)
            blob = f"{p.stem} {m.group(1) if m else ''} " \
                   f"{t.group(1) if t else ''}"
            s = sim(query, blob)
            if s > 0.1:
                hits.append((round(s, 2), "lesson",
                             f"30_LESSONS/{p.name}",
                             m.group(1) if m else p.stem))
    for intent, e in load_json(exp / "workflows.json", {}).items():
        s = sim(query, intent + " " + " ".join(e.get("pipeline", [])))
        if s > 0.1:
            rate = f"{e['pass']}/{e['runs']} pass"
            hits.append((round(s, 2), "workflow",
                         f"experience/workflows.json#{intent}",
                         f"{intent}: {rate}, {e['retries']} retries, "
                         f"~{e['seconds'] // max(1, e['runs'])}s/run"))
    for name, pat in load_json(exp / "patterns.json", {}).items():
        s = sim(query, name + " " + pat["description"])
        if s > 0.1:
            hits.append((round(s, 2), "pattern", name,
                         f"{pat['description']} ({pat['count']} scripts)"))
    hits.sort(key=lambda h: h[0], reverse=True)
    return hits[:limit]


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        (v / "90_META" / "traces").mkdir(parents=True)
        (v / "30_LESSONS").mkdir()
        (v / "10_PROJECTS" / "ABSOLUTE_ZERO").mkdir(parents=True)
        (v / "10_PROJECTS" / "ABSOLUTE_ZERO" / "FAULTS.md").write_text(
            "# faults\n", encoding="utf-8")
        (v / "scripts").mkdir()
        common = ('def load(p):\n    import json\n'
                  '    return json.loads(p.read_text(encoding="utf-8"))\n')
        (v / "scripts" / "a.py").write_text(
            '#!/usr/bin/env python3\n"""A."""\n# 90_META\n' + common +
            "raise SystemExit\n# --selftest\nX_TAB = {}\n", encoding="utf-8")
        (v / "scripts" / "b.py").write_text(
            '#!/usr/bin/env python3\n"""B."""\n# 90_META\n' + common +
            "raise SystemExit\n# --selftest\nY_TAB = {}\n", encoding="utf-8")
        (v / "scripts" / "c.py").write_text(
            '#!/usr/bin/env python3\n"""C."""\n# 90_META\n'
            "raise SystemExit\n# --selftest\nZ_TAB = {}\n", encoding="utf-8")
        t0 = "2026-07-11T10:00:00"
        trace = {"id": "t-retry", "request": "fix the widget parser",
                 "project": "ABSOLUTE_ZERO", "intent": "bug_fix",
                 "recall_tags": ["parser"], "retries": 1, "result": "pass",
                 "pipeline": ["RECALL", "EXECUTE", "VERIFY", "SUMMARIZE"],
                 "transitions": [
                     {"t": t0, "state": "CLASSIFY", "note": ""},
                     {"t": "2026-07-11T10:01:00", "state": "VERIFY",
                      "note": "FAIL: parser chokes on empty header"},
                     {"t": "2026-07-11T10:02:00", "state": "EXECUTE",
                      "note": "guard empty header before split"},
                     {"t": "2026-07-11T10:03:00", "state": "DONE",
                      "note": "ok"}]}
        dump_json(v / "90_META" / "traces" / "t-retry.json", trace)
        fail = dict(trace, id="t-fail", result="fail", retries=2,
                    request="deploy the flux capacitor")
        dump_json(v / "90_META" / "traces" / "t-fail.json", fail)
        rep = harvest(v)
        assert rep["lessons"], "no lesson drafted from retry pair"
        lesson = (v / rep["lessons"][0]).read_text(encoding="utf-8")
        assert "empty header" in lesson and "status: draft" in lesson
        assert "t-fail" in rep["failures"], rep["failures"]
        faults = (v / "10_PROJECTS" / "ABSOLUTE_ZERO" / "FAULTS.md"
                  ).read_text(encoding="utf-8")
        assert "flux capacitor" in faults
        wf = load_json(v / "90_META" / "experience" / "workflows.json", {})
        assert wf["bug_fix"]["runs"] == 2 and wf["bug_fix"]["pass"] == 1
        assert wf["bug_fix"]["seconds"] >= 180 * 2
        assert any(d["function"] == "load" for d in rep["reusable_code"]), \
            rep["reusable_code"]
        pats = rep["patterns"]
        assert "fail-loud" in pats and pats["fail-loud"]["count"] == 3
        # idempotent: second harvest extracts nothing new
        rep2 = harvest(v)
        assert not rep2["lessons"] and rep2["workflows"] == 0
        # retrieval finds the drafted lesson and the workflow
        hits = recall("empty header parser guard", v)
        assert any(k == "lesson" for _, k, _, _ in hits), hits
        # dedup: identical symptom again -> no duplicate lesson
        t3 = dict(trace, id="t-retry2", harvested=False)
        dump_json(v / "90_META" / "traces" / "t-retry2.json", t3)
        rep3 = harvest(v)
        assert not rep3["lessons"], "duplicate lesson not deduped"
    print("selftest OK")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Experience learning engine.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    h = sub.add_parser("harvest")
    h.add_argument("--trace", default=None)
    rc = sub.add_parser("recall")
    rc.add_argument("query")
    rc.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()

    if args.selftest:
        selftest()
    elif args.cmd == "harvest":
        rep = harvest(only=args.trace)
        print(f"harvested   {rep['workflows']} trace(s)")
        for p in rep["lessons"]:
            print(f"lesson      {p} (draft - promote via /review)")
        for f in rep["failures"]:
            print(f"failure     {f} -> FAULTS.md")
        if rep["reusable_code"]:
            print("reusable code candidates:")
            for d in rep["reusable_code"]:
                print(f"  {d['function']}: {', '.join(d['files'])} - "
                      f"{d['advice']}")
        print(f"patterns    {', '.join(rep['patterns']) or 'none'}")
    elif args.cmd == "recall":
        hits = recall(args.query, limit=args.limit)
        if not hits:
            print("not in vault")
        for s, kind, ref, desc in hits:
            print(f"{s:>5}  [{kind}] {desc}")
            print(f"       {ref}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
