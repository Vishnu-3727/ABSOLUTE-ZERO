---
tags: [core, planning, runtime]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-11
summary: Planning Engine spec — decomposes requests into validated, executable, dependency-ordered implementation plans.
---

# ABSOLUTE ZERO — Planning Engine

Plans before implementation. Turns a request into an executable plan the
/task EXECUTE stage walks step by step. Implementation:
`scripts/planner.py` (stdlib; reuses `orchestrator.classify`,
`context.STOP`, and the plugin registry).

## 1. API

```
python scripts/planner.py plan "<request>" [--project X] [--json]
python scripts/planner.py validate 90_META/plans/<id>.json
python scripts/planner.py --selftest
```

Plans persist to `90_META/plans/<id>.json` (runtime artifacts, committed,
never indexed). `--json` prints the machine plan; default is the human view.

## 2. Requirement → mechanism

| requirement | mechanism |
|---|---|
| Task decomposition | conjunction split ("and", "then", ";") → ≤5 subtasks, each classified separately; each expands to its intent's step template |
| Risk analysis | per-step risk from templates + **known risks mined from FAULT_LEDGER** (stopword-filtered word overlap — the expensive lessons resurface) |
| Dependency ordering | steps carry `depends_on`; whole graph ordered by `graphlib.TopologicalSorter`; cycles = validation FAIL, loud |
| Alternative solutions | per-intent approach table (always includes the do-less option) + per-step plugin fallbacks from the plugin engine |
| Estimated complexity | classify per subtask → points (trivial 1 / standard 3 / complex 8), summed; label = worst subtask |
| Rollback strategy | **real git baseline** (`rev-parse HEAD` at plan time) + per-step surgical rollback (`checkout -- files` / `revert`) |
| Test strategy | every step ships with a test; a step without a test fails validation |
| Architecture validation | gates: acyclic graph, every step has test+rollback, OS laws (stdlib-only, CLAUDE.md no-rewrite, ROOT_DOCS registration), 8k escalation warning on complex plans, git baseline present |
| Executable plans | steps bound to registry plugins (`bind_plugins` reuses the scheduler's scoring); `execution_order` is the walk list; "plan is executable" is a gate, not a hope |

## 3. Plan schema

```json
{
 "id": "2026-07-11-add-a-web-dashboard",
 "request": "...", "subtasks": ["...", "..."],
 "complexity": {"points": 6, "label": "standard", "per_subtask": ["standard", "standard"]},
 "risks_known": ["ledger lines matching the request"],
 "approaches": ["alternatives per intent"],
 "rollback": {"baseline": "4c1458d", "strategy": "..."},
 "steps": [{"id": "t1.s1", "subtask": "...", "intent": "feature",
            "action": "recall", "plugin": "query", "alternatives": ["..."],
            "depends_on": [], "risk": "...", "test": "...", "rollback": "..."}],
 "execution_order": ["t1.s1", "t2.s1", "...", "commit"],
 "validation": [["ok", "dependency graph is acyclic"], ["ok", "plan is executable"]]
}
```

## 4. Integration

- `/task` PLAN stage (standard/complex): run `planner.py plan "<request>"`,
  fix any `fail` gates before EXECUTE, then walk `execution_order` — one
  orchestrator EXECUTE log per step, using each step's bound plugin.
- Step templates, alternatives, and laws are data dicts at the top of
  `scripts/planner.py` — extend there; this doc describes, code decides.
- `validate` re-checks a stored plan (useful at VERIFY/REVIEW after edits).
