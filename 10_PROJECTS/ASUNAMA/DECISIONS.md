---
tags: [project, decisions, drone, navigation]
project: ASUNAMA
status: active
confidence: high
date: 2026-07-09
summary: Key locked decisions — Isaac over Gazebo, absolute visual fix, base-station processing, USD-native materials.
---

# ASUNAMA — Decisions

## 2026-06-27 — Localization anchor = ground-image mosaic, injected to EKF
- **Chose:** periodic absolute ORB-homography fix vs a geo-referenced map →
  `VISION_POSITION_ESTIMATE` into the Pixhawk EKF.
- **Over:** physical fiducial markers; pure optical-flow dead reckoning.
- **Why:** dead reckoning drifts unbounded; markers need arena prep. See
  [[gps-denied-localization]].

## 2026-06-27 — All processing on base-station laptop, Pi Zero = pure relay
- **Chose:** relay GStreamer/UDP video + MAVLink through Pi 0; compute on laptop.
- **Over:** onboard Pi 5 compute.
- **Why:** Pi 5 died; laptop has the GPU for ORB/render anyway.

## 2026-06-24 — Isaac Sim over Gazebo
- **Chose:** Isaac Sim.
- **Over:** Gazebo.
- **Why:** needs photoreal synthetic frames for ORB + domain randomization for
  sim-to-real; Gazebo can't.

## 2026-06-25 — USD-native material binding, not PreviewSurfaceCfg
- **Chose:** build `UsdPreviewSurface` directly via `UsdShade`.
- **Over:** Isaac Lab `PreviewSurfaceCfg`.
- **Why:** it's broken in Sim 6.0.0 (see [[FAULTS]] / [[read-stderr-not-app-log]]).
