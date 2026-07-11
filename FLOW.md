# ABSOLUTE ZERO — Flow Definitions

## /wake  (session start, budget ~800 tokens)
1. Read CLAUDE.md, 00_CORE/ACTIVE_GOALS.md, 90_META/INDEX_SUMMARY.md. Nothing else.
2. Ask: "What are we working on?" (or accept task given in same message).
3. Output briefing: what vault knows about this task (from INDEX_SUMMARY only),
   what it does not know, 2-4 clarifying questions if goals are ambiguous.
4. Do NOT speculatively load lessons or project files yet.

## /recall <topic or tags>  (budget ~1-3k tokens per round)
1. Run: python scripts/query.py --tags <tags> [--type lesson|fault|knowledge|decision]
2. Script returns titles + summaries + paths only.
3. Shortlist max 3 relevant hits. Read only matching sections via grep/sed.
4. Report findings with file-path citations. If zero hits: say "not in vault."

## /task <request>  (workflow orchestrator — the default work entry)
Every user request that produces a work product routes through this; bare
questions/greetings are exempt. Contract: ORCHESTRATOR.md.
1. Run: python scripts/orchestrator.py plan "<request>" — creates a trace
   in 90_META/traces/ with intent, complexity, strategy, engines, pipeline,
   verify checklist. AMBIGUOUS output -> ask the user first.
2. Execute the pipeline in order, logging each state:
   python scripts/orchestrator.py log --trace <file> --state <STATE>
   Illegal jumps are rejected loudly — that is the point.
3. RECALL = python scripts/context.py pack "<request>" (budget-aware
   package, contract in CONTEXT.md). Trivial tasks: ledger scan only.
3b. PLAN (standard/complex) = python scripts/planner.py plan "<request>" —
   executable plan: subtasks, dependency-ordered steps, risks from the
   ledger, tests, rollbacks, validation gates (PLANNER.md). Fix any "fail"
   gate before EXECUTE; then walk execution_order.
4. EXECUTE starts with python scripts/plugins.py route "<request>" — follow
   the chain (deterministic local tools before model calls, PLUGINS.md);
   report non-script outcomes via plugins.py report.
5. VERIFY = python scripts/verifier.py check (11 gated checks, VERIFIER.md)
   first, then the trace's checklist. Verifier FAIL or checklist fail ->
   retry EXECUTE (max 2) or close --result fail and escalate. Never
   SUMMARIZE over a failing verifier.
6. Pass -> log SUMMARIZE, close --result pass. Traces are committed history.
7. Dispatching work to a fresh agent/session? Compile its briefing:
   python scripts/promptc.py compile "<request>" --project X (PROMPTC.md).

## Work phase (main session body)
1. Before technical work on any tagged topic: scan FAULT_LEDGER.md for matches.
2. If a past fault matches current work, state it explicitly before proceeding.
3. New project: create 10_PROJECTS/<NAME>/ from 90_META/templates/,
   then /recall on the project's core tags to surface transferable lessons.
4. During work, keep a running scratch list of: decisions made, faults hit,
   lessons learned. This list feeds /sleep.

## /sleep  (session end, mandatory)
0. Close any open orchestrator trace (an open trace at sleep = failed verify).
1. Write dated log to 10_PROJECTS/<proj>/SESSIONS/YYYY-MM-DD.md.
2. Overwrite 10_PROJECTS/<proj>/RECENT.md (max 10 lines: status, next steps).
3. Append new faults to FAULTS.md (with root cause, fix, topic wikilinks).
4. If a fault/insight is transferable: create note in 30_LESSONS/.
5. Update ACTIVE_GOALS.md if goals changed.
6. Run scripts/indexer.py (rebuilds INDEX.json, INDEX_SUMMARY.md, FAULT_LEDGER.md).
7. git add -A && git commit -m "sleep: <proj> <date>"

## /research <topic>
1. Web search, read sources, summarize into 40_RESEARCH/<topic>.md
   with source URLs and frontmatter. Link to related topic notes.
2. Summary in note, not in context. Report 5-line digest to user.

## /review  (weekly, high-budget session, 20-30k tokens allowed)
1. Read all FAULT_LEDGER lines + lesson summaries. Hunt cross-project patterns.
2. Promote repeated patterns to 00_CORE/PRINCIPLES.md.
3. Flag stale ACTIVE_GOALS and orphan notes (no inbound links).
4. Compress: any RECENT.md or ledger bloat gets trimmed.
5. Findings written as one-line ledger/principle entries so daily sessions
   get them nearly free.

## /predict <project>
1. Read last N session logs' summary lines + RECENT.md for the project.
2. Estimate: likely next blockers, risk areas, velocity trend.
3. Every claim labeled ESTIMATE with the evidence file paths.

## Escalation rule
If any single retrieval need exceeds ~8k tokens, stop, tell the user the cost,
and ask whether to proceed or narrow scope.