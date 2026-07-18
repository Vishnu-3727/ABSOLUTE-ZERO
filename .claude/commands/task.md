---
description: ABSOLUTE ZERO — route a request through the Workflow Orchestrator.
argument-hint: <the task request> [--project X]
---
Execute the `/task` flow from `FLOW.md` (contract in `ORCHESTRATOR.md`) for: $ARGUMENTS

1. `python scripts/orchestrator.py plan "$ARGUMENTS"` — add `--project X`
   when known; that is what makes the project's case refresh on close.
   This RUNS recall: context pack, skills, and (standard/complex) the
   planner. Note the trace path.
2. If output says AMBIGUOUS, ask the user to confirm intent before anything else.
3. Read what recall actually returned — the packed notes and the plan file it
   names — and scan FAULT_LEDGER.md. State any matching past fault before
   working. RECALL/PLAN are logged by the runtime already; you start at
   EXECUTE, logging each state as you enter it:
   `python scripts/orchestrator.py log --trace <file> --state <STATE> --note "..."`
4. VERIFY = check every item on the trace's checklist. Fail -> log a retry
   EXECUTE (max 2) or `close --result fail` and escalate to the user.
5. All pass -> log SUMMARIZE, then `close --result pass --summary "..."`.
   `close` then runs the learning loop (harvest, reindex, case, graph) and
   prints one line per engine — read it, a FAILED line is a real failure.
6. Remind: session must still end with /sleep (which closes any open trace).
