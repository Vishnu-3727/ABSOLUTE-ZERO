---
tags: [project, faults, drone, isaac-sim, navigation]
project: ASUNAMA
status: active
confidence: high
date: 2026-07-09
summary: Real ASUNAMA faults — white box, headless deadlock, RTH frame bug, feature piling, coverage stall.
---

# ASUNAMA — Faults

## 2026-06-25 — Isaac renders a blank "white box" / app not responding
- **Symptom:** empty white Kit viewport, "not responding", every colored spawn.
- **Root cause:** Isaac Lab 0.54.4 `spawn_preview_surface` passes `name="Shader"`
  to a Kit command removed in Sim 6.0.0 → `TypeError` thrown to stderr; kit
  `.log` showed nothing. NOT the GPU/Optimus theory chased first.
- **Fix:** bind materials USD-natively (`_bind_material` via `UsdShade`); drop
  `PreviewSurfaceCfg`.
- **Topic:** [[debugging-silent-failures]] · [[read-stderr-not-app-log]]

## 2026-06-25 — Headless capture hangs 20-30 min then dies
- **Symptom:** `data_generator` stuck forever; kit log stops after "Replicator Step".
- **Root cause:** `rep.orchestrator.step(pause_timeline=True)` deadlocks on
  SyntheticData frame-counter desync (`OgnSdOnNewFrame: frames discarded`).
- **Fix:** drop the orchestrator; tick `simulation_app.update()` a bounded
  `RENDER_TICKS=64` then read the annotator.
- **Topic:** [[debugging-silent-failures]] · [[bounded-loop-over-unbounded-wait]]

## 2026-06-27 — Mission never completes (RTH never reaches home)
- **Symptom:** drone explores but Return-To-Home never registers arrival.
- **Root cause:** RTH measured distance to `(0,0)` but home is the base station
  at e.g. `(1,1)` in the vision-anchored frame.
- **Fix:** measure distance to base_station in the absolute frame.
- **Topic:** [[gps-denied-localization]] · [[coordinate-frame-origin]]

## 2026-06-27 — Features pile on top of each other
- **Symptom:** rocks stacked on streaks/soil; markers buried in renders.
- **Root cause:** `sample_xy` silently returned the last (overlapping) candidate
  when it exhausted its try budget.
- **Fix:** return `None` on exhaustion; every caller skips; largest-footprint-first.
- **Topic:** [[coverage-planning]] · [[fail-loud-not-silent-fallback]]

## 2026-06-27 — True coverage stalls below the 95% bar
- **Symptom:** exploration plateaus under acceptance threshold.
- **Root cause:** marking a single occupancy cell per tick under-counts what the
  camera actually sees.
- **Fix:** `mark_explored_footprint(x,y,radius)` gated on pose confidence.
- **Topic:** [[coverage-planning]] · [[coverage-footprint-not-cell]]
