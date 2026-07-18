---
description: ABSOLUTE ZERO — session start (load minimal context, brief).
---
Execute the `/wake` flow exactly as defined in `FLOW.md`.

Load ONLY: `CLAUDE.md`, `00_CORE/ACTIVE_GOALS.md`, `90_META/INDEX_SUMMARY.md`.
Do not speculatively read lessons or project files. Then brief per FLOW.md and
ask "What are we working on?" (or accept a task if one was given).

When a project is named or resumed (or a task hints at a topic), run
`python scripts/cases.py similar --project <NAME>` (or `similar "<topic>"`)
and surface the closest past case — its decisions, faults-to-not-repeat, and
reusable stack — BEFORE starting work. Reuse what worked instead of
re-deriving it (contract: `CASES.md`).
