#!/usr/bin/env python3
"""ABSOLUTE ZERO prompt compiler. Stdlib only.

Constructs prompts dynamically instead of hand-writing them. Composes the
other engines: classify (intent), context.build (automatic context
injection within budget), plugins.route (tool directives), the VERIFY
checklists (acceptance criteria), and 30_LESSONS as the few-shot corpus.
Sections are priority-ordered and dropped lowest-first under token
pressure; instruction lines from all sources are merged and near-duplicates
removed; the result is validated before emit (fail loud, exit 1).
Artifacts -> 90_META/prompts/. Contract in PROMPTC.md.

  python scripts/promptc.py compile "fix the odometry drift" --project ASUNAMA
  python scripts/promptc.py compile "..." --budget 2000 --json
  python scripts/promptc.py --selftest
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import (STOP, classify, est_tokens, jaccard, load_index, stem,
                  words_of)
from core import VERIFY as CHECKLISTS
from context import build as build_context, read_body

VAULT = Path(__file__).resolve().parent.parent
PROMPTS = VAULT / "90_META" / "prompts"
BUDGET, HARD_CAP = 5000, 8000
CONTEXT_SHARE = 0.55   # of budget, handed to context.build
FEWSHOT_K = 2
DEDUP_JACCARD = 0.5

# Immutable core law (distilled from CLAUDE.md - cited, never dropped).
LAW = [
    "Vault facts only; cite file paths. If it is not in the vault, say "
    "'not in vault' and ask. (CLAUDE.md)",
    "Ask clarifying questions without hesitation - one question beats one "
    "wrong assumption.",
    "Confirm which OS before OS-dependent commands. pyenv+uv only, "
    "never conda.",
    "End the session with /sleep - a session without /sleep is failed.",
]
# Intent-specific imperatives (merged with the VERIFY checklist, deduped).
INTENT_LINES = {
    "quick_fix": ["Change only the target; show the diff is minimal."],
    "bug_fix": ["Reproduce before fixing.",
                "Fix the root cause in the shared path, not the symptom "
                "at one caller.",
                "Record the fault in FAULTS.md with a topic wikilink."],
    "feature": ["Check the vault for existing machinery before writing "
                "anything new.",
                "Leave one runnable check behind (--selftest)."],
    "architecture": ["Write the plan and get it agreed before edits.",
                     "Prefer incremental refactor over rewrite."],
    "research": ["Every claim needs a source URL.",
                 "Write the note to 40_RESEARCH/; report a 5-line digest."],
    "documentation": ["Check statements against current code before "
                      "writing them down."],
    "performance": ["Measure a baseline first; measure again after.",
                    "No optimization without a before/after number."],
    "security": ["Name the threat before fixing it.",
                 "Never commit secrets; check the diff."],
    "deployment": ["State the rollback path before deploying.",
                   "Dry-run or stage first."],
}
SECTION_ORDER = ["LAW", "TASK", "INSTRUCTIONS", "TOOLS", "CONTEXT",
                 "EXAMPLES", "VERIFY", "OUTPUT"]
# Drop order under budget pressure (TASK and LAW are never dropped).
DROP_ORDER = ["EXAMPLES", "TOOLS", "CONTEXT", "VERIFY", "INSTRUCTIONS"]
OUTPUT_CONTRACT = ["Cite vault paths for every memory-based claim.",
                   "Log orchestrator states as you pass them; close the "
                   "trace before finishing."]


def dedup_lines(lines):
    """Merge instructions from all sources; near-duplicates removed."""
    kept, seen, dropped = [], [], 0
    for line in lines:
        w = {stem(x) for x in words_of(line)} - STOP
        if w and any(jaccard(w, s) > DEDUP_JACCARD for s in seen):
            dropped += 1
            continue
        kept.append(line)
        seen.append(w)
    return kept, dropped


def few_shot(request, notes, vault, k=FEWSHOT_K):
    """Retrieve the closest lessons as worked examples: situation -> lesson."""
    qw = set(words_of(request)) - STOP
    scored = []
    for n in notes:
        if n["type"] != "lesson":
            continue
        nw = set(words_of(n["title"] + " " + (n["summary"] or ""))) \
            | {t.lower() for t in n["tags"]}
        s = jaccard(qw, nw) + 0.5 * len(qw & {t.lower() for t in n["tags"]})
        if s > 0:
            scored.append((s, n))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for _, n in scored[:k]:
        body = read_body(vault, n["path"]).strip()
        para = next((p for p in body.split("\n\n")
                     if p and not p.startswith("#")), "")[:400]
        out.append(f"Example ({n['path']}):\n  situation: {n['summary']}\n"
                   f"  lesson: {' '.join(para.split())}")
    return out


def tool_lines(request):
    try:
        from plugins import route
        plan = route(request, quiet=True)
    except SystemExit:
        return []
    out = [f"Use {c['invoke']} for {', '.join(c['covers'])}"
           + (f" (fallback: {', '.join(plan['fallbacks'][c['name']])})"
              if plan["fallbacks"].get(c["name"]) else "")
           for c in plan["chain"]]
    if plan["uncovered"]:
        out.append(f"No tool covers {', '.join(plan['uncovered'])} - do it "
                   f"directly.")
    return out


def render_context(pkg):
    lines = []
    for p in pkg["pinned"]:
        lines.append(f"--- {p['path']} (pinned: {p['reason']}) ---")
        lines.append(p["text"].strip())
    for i in pkg["items"]:
        lines.append(f"--- {i['path']} ({i['tier']}) ---")
        lines.append(i["text"].strip())
    if pkg["history"]:
        lines.append("--- conversation history (extractive) ---")
        lines.append(pkg["history"]["text"])
    if pkg["omitted"]:
        lines.append("Known but not loaded (pull via query.py if needed): "
                     + "; ".join(pkg["omitted"][:8]))
    return "\n".join(lines)


def validate(sections, budget, vault):
    checks = []
    total = sum(est_tokens(t) for t in sections.values())
    checks.append(("ok", f"{total} tokens within budget {budget}")
                  if total <= budget else
                  ("fail", f"{total} tokens exceeds budget {budget}"))
    checks.append(("ok", "task present") if sections.get("TASK", "").strip()
                  else ("fail", "TASK section empty"))
    checks.append(("ok", "law present") if sections.get("LAW")
                  else ("fail", "LAW section missing"))
    dead = [p for p in re.findall(r"\b(?:[0-9]{2}_[A-Z]+|scripts)/[\w\-./]+",
                                  "\n".join(sections.values()))
            if not (vault / p).exists()]
    checks.append(("ok", "all cited paths exist") if not dead else
                  ("warn", f"cited paths missing: {', '.join(set(dead))}"))
    empty = [k for k, v in sections.items() if not v.strip()]
    checks.append(("ok", "no empty sections") if not empty else
                  ("warn", f"empty sections: {', '.join(empty)}"))
    return checks, total


def compile_prompt(request, project="", budget=BUDGET, history=None,
                   vault=VAULT, notes=None):
    budget = min(budget, HARD_CAP)
    c = classify(request)
    intent = c["intent"]
    pkg = build_context(request, project, int(budget * CONTEXT_SHARE),
                        history, vault, notes)
    instructions, dropped_dups = dedup_lines(
        INTENT_LINES.get(intent, []) + CHECKLISTS.get(intent, []))
    verify_lines = [f"[ ] {v}" for v in CHECKLISTS.get(intent, [])]
    sections = {
        "LAW": "\n".join(f"- {l}" for l in LAW),
        "TASK": request + (f"\n(project: {project})" if project else "")
                + (f"\nIntent: {intent} ({c['complexity']})"
                   + (" - AMBIGUOUS, confirm with user first"
                      if c["ambiguous"] else "")),
        "INSTRUCTIONS": "\n".join(f"- {l}" for l in instructions),
        "TOOLS": "\n".join(f"- {l}" for l in tool_lines(request)),
        "CONTEXT": render_context(pkg),
        "EXAMPLES": "\n\n".join(few_shot(request, notes if notes is not None
                                         else load_index(vault), vault)),
        "VERIFY": "\n".join(verify_lines),
        "OUTPUT": "\n".join(f"- {l}" for l in OUTPUT_CONTRACT),
    }
    # Token optimization: drop lowest-priority sections until within budget.
    dropped_sections = []
    for victim in DROP_ORDER:
        total = sum(est_tokens(t) for t in sections.values() if t)
        if total <= budget:
            break
        if sections.get(victim):
            dropped_sections.append(victim)
            sections[victim] = ""
    sections = {k: v for k, v in sections.items() if v.strip()}
    checks, total = validate(sections, budget, vault)
    prompt = "\n\n".join(f"## {k}\n{sections[k]}" for k in SECTION_ORDER
                         if k in sections)
    return {"id": f"{datetime.now():%Y-%m-%d}-"
                  + ("-".join(words_of(request)[:5]) or "prompt"),
            "request": request, "intent": intent,
            "budget": budget, "tokens": total, "prompt": prompt,
            "stats": {"sections": {k: est_tokens(v) for k, v in
                                   sections.items()},
                      "dropped_sections": dropped_sections,
                      "merged_duplicates": dropped_dups,
                      "context_omitted": len(pkg["omitted"])},
            "validation": [list(x) for x in checks]}


def save(res, vault=VAULT):
    d = vault / "90_META" / "prompts"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{res['id']}.md"
    n = 2
    while p.exists():
        p = d / f"{res['id']}-{n}.md"
        n += 1
    p.write_text(res["prompt"] + "\n", encoding="utf-8")
    return p


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        (v / "30_LESSONS").mkdir(parents=True)
        (v / "30_LESSONS" / "drift.md").write_text(
            "---\nsummary: s\n---\nAnchor odometry with absolute fixes.\n",
            encoding="utf-8")
        (v / "90_META").mkdir()
        (v / "90_META" / "FAULT_LEDGER.md").write_text(
            "- [X][odometry] drift on takeoff -> anchor\n", encoding="utf-8")
        notes = [{"path": "30_LESSONS/drift.md", "title": "Odometry drift",
                  "type": "lesson", "project": "ASUNAMA",
                  "tags": ["odometry"], "summary":
                  "Dead reckoning drifts; inject absolute fix.",
                  "links": [], "date": "2026-07-01"}]
        res = compile_prompt("fix the odometry drift bug", project="ASUNAMA",
                             budget=3000, vault=v, notes=notes)
        p = res["prompt"]
        assert "## TASK" in p and "## LAW" in p
        assert "drift on takeoff" in p, "ledger not injected"
        assert "Example (30_LESSONS/drift.md)" in p, "few-shot missing"
        assert "root cause" in p.lower(), "intent instructions missing"
        assert res["tokens"] <= 3000
        assert res["stats"]["merged_duplicates"] >= 1, \
            "duplicate instructions not merged"  # intent line vs checklist
        assert all(s != "fail" for s, _ in res["validation"]), \
            res["validation"]
        # budget pressure drops EXAMPLES before TASK/LAW/VERIFY
        tiny = compile_prompt("fix the odometry drift bug", budget=260,
                              vault=v, notes=notes)
        assert "## TASK" in tiny["prompt"] and "## LAW" in tiny["prompt"]
        assert "EXAMPLES" in tiny["stats"]["dropped_sections"]
        assert tiny["tokens"] <= 260, tiny["tokens"]
        # dedup unit
        kept, n = dedup_lines(["Reproduce before fixing.",
                               "Reproduce it before you fix it.",
                               "Cite sources."])
        assert len(kept) == 2 and n == 1, kept
        # validation catches over-budget
        checks, _ = validate({"TASK": "x" * 8000, "LAW": "l"}, 100, v)
        assert any(s == "fail" for s, _ in checks)
    print("selftest OK")


def main():
    # injected note text can be non-cp1252; Windows console chokes without this
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Prompt compiler.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    co = sub.add_parser("compile")
    co.add_argument("request")
    co.add_argument("--project", default="")
    co.add_argument("--budget", type=int, default=BUDGET)
    co.add_argument("--history", default=None)
    co.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    if args.selftest:
        selftest()
    elif args.cmd == "compile":
        res = compile_prompt(args.request, args.project, args.budget,
                             args.history)
        path = save(res)
        if args.as_json:
            res["path"] = str(path)
            print(json.dumps(res, indent=1))
        else:
            print(res["prompt"])
            print(f"\n---\ntokens      {res['tokens']} / {res['budget']}")
            st = res["stats"]
            print(f"sections    " + ", ".join(
                f"{k}={v}" for k, v in st["sections"].items()))
            print(f"merged      {st['merged_duplicates']} duplicate "
                  f"instruction(s)")
            if st["dropped_sections"]:
                print(f"dropped     {', '.join(st['dropped_sections'])}")
            for s, note in res["validation"]:
                print(f"  {s:<5} {note}")
            print(f"saved       {path.relative_to(VAULT)}")
        if any(s == "fail" for s, _ in res["validation"]):
            raise SystemExit(1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
