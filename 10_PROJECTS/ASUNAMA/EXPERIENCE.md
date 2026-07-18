---
tags: [ardupilot, bootstrap, case, coordinate-frames, coverage, debugging, decisions, diagnostics, drift, drone, experience, faults, isaac-sim, lesson, localization, mapping, navigation, overview, project, python, recent, reliability, research, robotics, session, software, state-estimation]
project: ASUNAMA
status: active
confidence: medium
date: 2026-07-18
summary: Project experience case for ASUNAMA - reusable decisions, faults and stack.
---

# ASUNAMA — Project Experience

## Stack / components
- MAVLink
- NumPy stack
- OpenCV
- PyTorch
- counts
- external
- internal
- markers
- primary
- pytest

## Key decisions
- 2026-06-27 — Localization anchor = ground-image mosaic, injected to EKF — Chose:** periodic absolute ORB-homography fix vs a geo-referenced map →
- 2026-06-27 — All processing on base-station laptop, Pi Zero = pure relay — Chose:** relay GStreamer/UDP video + MAVLink through Pi 0; compute on laptop.
- 2026-06-24 — Isaac Sim over Gazebo — Chose:** Isaac Sim.
- 2026-06-25 — USD-native material binding, not PreviewSurfaceCfg — Chose:** build `UsdPreviewSurface` directly via `UsdShade`.

## Faults & fixes (do not repeat)
- **empty white Kit viewport, "not responding", every colored spawn.** → bind materials USD-natively (`_bind_material` via `UsdShade`); drop
- **`data_generator` stuck forever; kit log stops after "Replicator Step".** → drop the orchestrator; tick `simulation_app.update()` a bounded
- **drone explores but Return-To-Home never registers arrival.** → measure distance to base_station in the absolute frame.
- **rocks stacked on streaks/soil; markers buried in renders.** → return `None` on exhaustion; every caller skips; largest-footprint-first.
- **exploration plateaus under acceptance threshold.** → `mark_explored_footprint(x,y,radius)` gated on pose confidence.

## Lessons
- bounded-loop-over-unbounded-wait: Replicator orchestrator wait-for-frame deadlocked forever; a bounded update loop cannot hang.
- coordinate-frame-origin: RTH checked distance to (0,0) but home was the base station; mission never completed.
- coverage-footprint-not-cell: Single-cell coverage marking couldn't reach 95%; mark the camera footprint instead.
- fail-loud-not-silent-fallback: A sampler that silently placed features at the last spot on exhaustion caused overlaps; return None and skip.
- odometry-drift-absolute-fix: Optical-flow dead reckoning drifted unbounded under wind; fixed with periodic absolute visual fixes.
- read-stderr-not-app-log: The Isaac "white box" was a Python TypeError on stderr, not a GPU bug; the app log never showed it.

## Workflows that ran
- bug_fix: 2/2 pass
