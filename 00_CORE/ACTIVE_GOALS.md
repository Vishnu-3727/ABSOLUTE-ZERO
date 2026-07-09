---
tags: [core, goals]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-09
summary: Build-phase checklist for the vault itself; the live to-do the /wake command reads.
---

# ACTIVE GOALS

## Vault build phases
- [x] **Phase 1 — Skeleton** — dirs, IDENTITY, ACTIVE_GOALS, PRINCIPLES, 5 templates, git init
- [x] **Phase 2 — Memory machinery** — indexer.py + query.py (stdlib); root spec files in place
- [ ] **Phase 3 — Lesson transfer test** — ≥5 real lessons in 30_LESSONS/, ROVER-NAV /recall go/no-go gate
- [ ] **Phase 4 — /research, /review, /predict**
- [ ] **Phase 5 — Dashboard (Dataview, phase A)**
- [ ] **Phase 6 — Automation (systemd timers, Ubuntu)**

## Notes
- Phases renumbered to match GUIDE.md. ASUNAMA migration folds into Phase 3 lesson seeding.
- Vault scripts run with `python scripts/indexer.py` / `scripts/query.py` from vault root.
