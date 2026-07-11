---
description: ABSOLUTE ZERO — route a request through the Workflow Orchestrator.
argument-hint: <the task request> [--project X]
---
Execute the `/task` flow from `FLOW.md` (contract in `ORCHESTRATOR.md`) for: $ARGUMENTS

1. `python scripts/orchestrator.py plan "$ARGUMENTS"` — note the trace path.
2. If output says AMBIGUOUS, ask the user to confirm intent before anything else.
3. Follow the printed pipeline in order, logging each state as you enter it:
   `python scripts/orchestrator.py log --trace <file> --state <STATE> --note "..."`
   RECALL = scan FAULT_LEDGER.md + run the printed query command; state any
   matching past fault before working. Trivial tasks: ledger scan only.
4. VERIFY = check every item on the trace's checklist. Fail -> log a retry
   EXECUTE (max 2) or `close --result fail` and escalate to the user.
5. All pass -> log SUMMARIZE, then `close --result pass --summary "..."`.
6. Remind: session must still end with /sleep (which closes any open trace).
