---
tags: [core, orchestrator, runtime]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-11
summary: Workflow Orchestrator spec — central runtime routing every request through classify, recall, execute, verify, summarize.
---

# ABSOLUTE ZERO — Workflow Orchestrator

Central runtime of the OS. Every user request passes through it.
Claude is the CPU; `scripts/orchestrator.py` is the deterministic plumbing;
markdown flows are the programs.

## 1. Architecture

```
user request
     |
     v
 /task (.claude/commands/task.md)
     |
     v
 orchestrator.py plan  ──────────────► 90_META/traces/<id>.json
     |  intent + complexity + strategy
     |  + engine set + pipeline + verify checklist
     v
 Claude executes pipeline, logging each state:
     RECALL ──► [SIMILARITY] ──► [PLAN] ──► EXECUTE ──► VERIFY ──► [REVIEW] ──► SUMMARIZE
       |                                        ^           |
       |                                        +── retry ──+  (max 2, then ESCALATE)
       v
   engines (existing, not redesigned):
     knowledge   = 20_KNOWLEDGE/ via scripts/query.py
     experience  = FAULT_LEDGER.md + 30_LESSONS/ + SESSIONS/
     similarity  = orchestrator.py similarity (fuzzy over INDEX.json)
     skills      = .claude/commands/*.md
     audit       = scripts/review.py
     dashboard   = DASHBOARD.md
     context     = scripts/context.py pack (CONTEXT.md; always on)
     plugins     = scripts/plugins.py route/exec (PLUGINS.md; EXECUTE stage)
     planner     = scripts/planner.py plan (PLANNER.md; PLAN stage)
     verifier    = scripts/verifier.py check (VERIFIER.md; VERIFY stage)
     |
     v
 orchestrator.py close ──► trace final state DONE / ESCALATED ──► /sleep
```

## 2. State machine

States: `CLASSIFY, RECALL, SIMILARITY, PLAN, EXECUTE, VERIFY, REVIEW, SUMMARIZE, DONE, ESCALATED`.

- A trace starts at CLASSIFY (written by `plan`).
- Legal next state = next unvisited stage of the trace's pipeline. Anything
  else is rejected loudly (P1: make failure loud).
- VERIFY may transition back to EXECUTE (a retry) at most 2 times; after
  that the only exit is `close --result fail` → ESCALATED, and the user
  decides.
- `close --result pass` is only legal after SUMMARIZE is logged; this makes
  skipping verification structurally impossible.

Pipelines by strategy:

| complexity | strategy              | pipeline |
|---|---|---|
| trivial  | direct                | RECALL → EXECUTE → VERIFY → SUMMARIZE |
| standard | recall-execute-verify | RECALL → PLAN → EXECUTE → VERIFY → SUMMARIZE |
| complex  | deep                  | RECALL → SIMILARITY → PLAN → EXECUTE → VERIFY → REVIEW → SUMMARIZE |

RECALL depth follows complexity: trivial = FAULT_LEDGER scan only;
standard = ledger + query.py on `recall_tags`; complex adds the similarity
pass. Deep tasks respect the 8k escalation rule — state the cost, ask.

## 3. Folder structure (additions only)

```
AbsoluteZero/
├── ORCHESTRATOR.md            this spec (root doc)
├── .claude/commands/task.md   /task entry point
├── scripts/orchestrator.py    plumbing: plan / log / close / similarity
└── 90_META/traces/            one JSON per task (runtime artifact, not notes)
```

## 4. Interfaces

CLI (run from vault root, stdlib only):

```
python scripts/orchestrator.py plan "<request>" [--project X]
python scripts/orchestrator.py log --trace <file> --state <STATE> [--note "..."]
python scripts/orchestrator.py close --trace <file> --result pass|fail [--summary "..."]
python scripts/orchestrator.py similarity "<text>" [--limit 5]
python scripts/orchestrator.py --selftest
```

Trace JSON schema:

```json
{
  "id": "2026-07-11-fix-the-stale-date-crash",
  "request": "verbatim user request",
  "project": "ASUNAMA",
  "intent": "bug_fix",
  "complexity": "standard",
  "strategy": "recall-execute-verify",
  "engines": ["experience", "knowledge", "audit"],
  "pipeline": ["RECALL", "PLAN", "EXECUTE", "VERIFY", "SUMMARIZE"],
  "verify": ["root cause named, not symptom", "..."],
  "recall_tags": ["navigation"],
  "ambiguous": false,
  "transitions": [{"t": "ISO-8601", "state": "CLASSIFY", "note": "..."}],
  "retries": 0,
  "result": null
}
```

Intent → engines and intent → verify-checklist tables live as data dicts in
`orchestrator.py` (`ENGINES`, `VERIFY`) — edit there, this doc describes,
code decides.

## 5. Intent taxonomy

`quick_fix, bug_fix, feature, architecture, research, documentation,
performance, security, deployment` — keyword-scored, prefix-matched,
ties broken by dict order (riskier intents first). Zero keyword hits →
`ambiguous: true` and the runtime must ask the user before proceeding
(one question beats one wrong assumption).

## 6. Integration guide

1. `/task <request>` is the front door; FLOW.md routes every non-trivial
   request through it. Bare greetings/questions with no work product are
   exempt — no trace for "what does query.py do".
2. The runtime obeys the trace: log each state as you enter it; an illegal
   jump is a bug in the runtime, not in the plumbing.
3. VERIFY items come from the trace, not memory. All pass → SUMMARIZE.
   Any fail → retry (logged) or close fail.
4. /sleep closes any open trace before the session-log step; an open trace
   at sleep time is a failed verification by definition.
5. Traces are runtime artifacts: indexed never (indexer skips `traces/`),
   committed always (they are the OS's execution history).

## 7. Example execution traces

Real runs, committed:

- `90_META/traces/2026-07-11-design-and-implement-a-workflow.json` — deep pipeline (this orchestrator's own build), clean pass
- `90_META/traces/2026-07-11-fix-the-intent-tie-break.json` — direct pipeline, one real VERIFY-fail retry
