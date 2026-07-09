---
tags: [lesson, navigation, localization, state-estimation, drift]
project: ASUNAMA
status: active
confidence: high
date: 2026-06-27
summary: Optical-flow dead reckoning drifted unbounded under wind; fixed with periodic absolute visual fixes.
---

# Optical-flow dead reckoning drifts — inject an absolute fix

## What happened
ASUNAMA localization was pure optical-flow dead reckoning. Under wind the
position estimate drifted without bound; coverage and return-to-home became
unreliable.

## Lesson
Odometry-only localization has no error bound. Add a periodic **absolute**
correction (ORB-homography match against a geo-referenced arena map) and blend
the estimate toward it, gated on RANSAC inlier confidence. In production this
is `VISION_POSITION_ESTIMATE` → EKF (`EK3_SRC1_POSXY=6`).

## Transfer
Any odometry robot: a wheeled rover's encoders drift the same way — correct
against fiducials or a map. Topic: [[gps-denied-localization]].
