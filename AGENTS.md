# AGENTS — Multi-Agent Runtime

Contract for `scripts/agents.py`. Stdlib only. Claude is the CPU; agents
are deterministic role workers that drive the other engines in parallel
and hand LLM-shaped work back as work orders.

## Commands

```
python scripts/agents.py compose "<request>"   # show the workflow DAG, no execution
python scripts/agents.py run "<request>"       # execute; record in 90_META/runs/
python scripts/agents.py --selftest
```

## The eight agents

| Agent | Prio | Does (deterministic) |
|---|---|---|
| coordinator | 9 | Composes DAG, schedules, resolves conflicts, summary node |
| reviewer | 8 | Dirty git tree: runs verifier.py (FAIL raises); else VERIFY checklist |
| tester | 7 | Runs `--selftest` on touched vault scripts; any fail raises |
| architect | 6 | LAWS regex check + approach chosen from ALTERNATIVES |
| planner | 5 | planner.build = real plan file; gate fails broadcast to all |
| optimizer | 4 | Reads experience/workflows.json; pass-rate/retry advice |
| researcher | 3 | Scores INDEX.json notes + mines FAULT_LEDGER; risk hit broadcasts |
| implementer | 2 | plugins.route chain + touched scripts = **work order** for Claude |

Prio = blackboard conflict rank, not importance.

## Dynamic workflows (coordinator)

Per subtask (planner.decompose): intent template from WORKFLOWS, then

- **trivial** — prune planner/architect/optimizer, rewire dependencies
  transitively;
- **complex** — guarantee planner/architect/optimizer (extras appended
  after current sinks);
- subtask branches are independent (parallel); a final `coordinator`
  node joins all sinks.

## Runtime mechanics

- **Dependency scheduling**: `graphlib.TopologicalSorter`
  prepare/get_ready/done.
- **Parallel execution**: `ThreadPoolExecutor` (4 workers); ready nodes
  run concurrently; record stores `max_parallel` (interval sweep with
  `perf_counter` — `monotonic()` ticks ~15ms on Windows).
- **Shared memory**: `Blackboard` — versioned keys, compare-and-swap
  (`expected=` version). Conflicts: lists merge; otherwise higher-PRIORITY
  writer wins, ties keep the committed value (stale writer must re-read).
  Every conflict logged in the record.
- **Communication**: `Bus` — per-agent inbox queues, send/broadcast/drain,
  full log in the record. Scheduler auto-notifies dependents when their
  input is ready.
- **Failure**: an agent exception marks the node `fail`; descendants
  become `skipped`; run verdict `fail`. Failure is data, not a crash.

## Run record (90_META/runs/<id>.json — committed, never indexed)

request, subtasks, workflow nodes, per-node results (status/ms/output),
messages, conflicts, final memory snapshot, max_parallel, verdict.
`show` prints the DAG with statuses plus every **WORK ORDER** — those are
Claude's EXECUTE checklist (FLOW step 4b).

## Laws

- Runtime never edits files itself: writing code stays with the CPU via
  work orders (verifier remains the gate).
- Memory keys namespaced `kind.tid` (plan.t1, findings.t2,
  work_order.t1…); `summary` written only by coordinator.
- Use for complex or multi-subtask tasks; a trivial single subtask is
  cheaper through the plain pipeline.
