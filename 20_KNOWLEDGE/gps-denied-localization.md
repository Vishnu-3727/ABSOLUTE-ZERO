---
tags: [knowledge, navigation, localization, state-estimation, drift]
project: "-"
status: active
confidence: high
date: 2026-06-27
summary: Dead-reckoning drifts unbounded; correct with periodic absolute fixes in an explicit anchored frame.
---

# GPS-denied localization

Core facts that transfer to any odometry-only robot (drone, rover, AUV):

- **Any dead-reckoning estimate drifts unbounded.** Optical flow, wheel
  odometry, IMU integration — error accumulates with no bound. Wind/slip makes
  it worse.
- **Fix = periodic ABSOLUTE reference.** Blend the drifting estimate toward an
  absolute measurement (ORB homography vs a geo-referenced map, fiducial,
  known landmark). In ArduPilot this is `VISION_POSITION_ESTIMATE` into the EKF
  (`EK3_SRC1_POSXY=6` ExternalNav).
- **Gate the fix on confidence** (e.g. RANSAC inlier count) — reject
  featureless input rather than injecting a bad pose.
- **Always work in an explicit anchored frame.** "Home"/"dock"/"origin" is a
  named point, not implicitly (0,0). See [[coordinate-frame-origin]].

Lessons: [[odometry-drift-absolute-fix]], [[coordinate-frame-origin]].
