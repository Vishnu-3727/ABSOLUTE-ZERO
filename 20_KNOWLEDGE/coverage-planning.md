---
tags: [knowledge, navigation, coverage, mapping]
project: "-"
status: active
confidence: high
date: 2026-06-27
summary: Mark the sensor footprint, not one cell; place features by clearance discs, skip on exhaustion.
---

# Coverage & area planning

Transfers to any sweep/survey robot (drone survey, rover mapping, vacuum):

- **Mark the FOOTPRINT, not one cell.** A camera/sensor sees an area each tick.
  Marking a single grid cell per step cannot reach high coverage (drone survey
  stalled below 95% until footprint marking was used). Radius = sensor FOV on
  the ground. See [[coverage-footprint-not-cell]].
- **Coverage metrics are geometric** (true pose vs estimate) — validate them
  headless/fast, no render needed.
- **Placement by clearance discs, largest-footprint-first.** Reject-sample
  against an occupancy list; if the sampler exhausts its tries, SKIP — never
  silently force-place. See [[fail-loud-not-silent-fallback]].

Lessons: [[coverage-footprint-not-cell]].
