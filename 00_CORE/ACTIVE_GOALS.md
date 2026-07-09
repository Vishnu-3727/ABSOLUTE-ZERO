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
- [x] **Phase 3 — Lesson transfer** — 6 lessons + 3 topic notes + ASUNAMA migrated; go/no-go gate PASSED
- [ ] **Phase 4 — /research, /review, /predict**
- [ ] **Phase 5 — Dashboard (Dataview, phase A)**
- [ ] **Phase 6 — Automation (systemd timers, Ubuntu)**

## Notes
- Phases renumbered to match GUIDE.md. ASUNAMA migrated in Phase 3.
- Vault scripts run with `python scripts/indexer.py` / `scripts/query.py` from vault root.
- **ROS2 lessons pending Ubuntu session:** EKF timestamps, QoS, empy/colcon pins
  live in the Ubuntu ROS workspace (not reachable from Windows). Seed on next
  Ubuntu run; tag them `ros2` so a full `/recall ros2,navigation` matches.
