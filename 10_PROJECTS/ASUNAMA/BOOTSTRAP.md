---
tags: [bootstrap, python]
project: ASUNAMA
status: active
confidence: estimate
date: 2026-07-11
summary: auto-bootstrap of ASUNAMA - python/MAVLink, NumPy stack, OpenCV, PyTorch, pytest, 277 files, 8 risks
---

# ASUNAMA — Bootstrap

## Identity
- path: `C:\asunama`
- language: **python** (markers: -)
- frameworks: **MAVLink, NumPy stack, OpenCV, PyTorch, pytest**
- files scanned: 277

## Architecture

| dir | files | role |
|---|---|---|
| data | 185 | - |
| . | 23 | - |
| training | 14 | - |
| simulation | 13 | - |
| deployment | 10 | - |
| tests | 8 | tests |
| perception | 6 | - |
| navigation | 6 | - |
| mavlink_layer | 4 | - |
| localization | 4 | - |

entrypoints: `deployment/base_station_main.py`, `deployment/fc_setup.py`, `deployment/ground_control.py`, `deployment/rpi5_main.py`, `localization/visual_localizer.py`, `perception/calibration/calibrate_camera.py`, `perception/camera_abstraction.py`, `perception/orb_detector.py`

## Dependency graph
- external: PIL, carb, cv2, isaaclab, numpy, omni, pxr, pymavlink, pytest, serial, torch, yaml
- internal edges: arena_builder->simulation, arena_env->simulation, arena_map_generator->simulation, base_station_main->localization, base_station_main->mavlink_layer, base_station_main->navigation, base_station_main->perception, calibrate_camera->perception, data_generator->simulation, domain_randomizer->simulation, drone_model->simulation, eval_coverage->navigation

## Risks
- **low** no LICENSE — reuse status undefined
- **med** no CI config — nothing runs tests on push
- **med** 2 file(s) over 800 lines — monoliths resist review and reuse
- **ledger** [ASUNAMA][project,faults,drone] empty white Kit viewport, "not responding", every colored spawn. -> bind materials USD-natively (`_bind_material` via `UsdShade`); drop ([[debugging-silent-failures]]) — this fault class already cost a session
- **ledger** [ASUNAMA][project,faults,drone] `data_generator` stuck forever; kit log stops after "Replicator Step". -> drop the orchestrator; tick `simulation_app.update()` a bounded ([[debugging-silent-failures]]) — this fault class already cost a session
- **ledger** [ASUNAMA][project,faults,drone] drone explores but Return-To-Home never registers arrival. -> measure distance to base_station in the absolute frame. ([[gps-denied-localization]]) — this fault class already cost a session
- **ledger** [ASUNAMA][project,faults,drone] rocks stacked on streaks/soil; markers buried in renders. -> return `None` on exhaustion; every caller skips; largest-footprint-first. ([[coverage-planning]]) — this fault class already cost a session
- **ledger** [ASUNAMA][project,faults,drone] exploration plateaus under acceptance threshold. -> `mark_explored_footprint(x,y,radius)` gated on pose confidence. ([[coverage-planning]]) — this fault class already cost a session

## Conventions (measured, follow these)
- indent: 4 spaces
- quotes: prefer "
- line length: p95 = 83
- naming: snake_case
- docstring coverage: 31% of 329 defs
- type hints: 41% of args

## Recommended skills
- /task (0.38)
- /caveman-review (0.45)
- /code-review (0.45)
- /codex-result-handling (0.45)
- /gpt-5-4-prompting (0.45)
- /ponytail-audit (0.45)
- /sleep (0.3)

## Context package
budget 2500 tokens, used 1154
- identity+summary (75 tok, p1)
- risks (262 tok, p2)
- architecture (273 tok, p3)
- conventions (33 tok, p4)
- dependency-graph (431 tok, p5)
- skills (80 tok, p6)
