---
description: ABSOLUTE ZERO — onboard an existing repository into the vault.
argument-hint: <path to repo> [--name NAME]
---
Onboard an existing codebase. Contract: `BOOTSTRAP.md`. This reads the
target repo and writes only into the vault — the repo is never modified.

1. Check `ls 10_PROJECTS/` first. The engine derives the project name from
   the directory name (spaces to underscores, uppercased), which can land
   next to an existing project instead of on it — `AbsoluteZero` becomes
   `ABSOLUTEZERO`, a second project beside `ABSOLUTE_ZERO`. If the derived
   name collides in spirit with one already there, pass `--name` explicitly.
2. `python scripts/bootstrap.py open <repo> [--name NAME]` — detects stack,
   maps architecture and dependencies, runs risk analysis against the fault
   ledger, and writes `10_PROJECTS/<NAME>/BOOTSTRAP.md` + `bootstrap.json`.
3. `python scripts/cases.py similar --project <NAME>` — surface what past
   projects teach this one before touching the code.
4. `python scripts/indexer.py` so the new project is indexed.

For a project that does not exist yet, use `/new` instead — that scaffolds
from templates and injects prior experience.
