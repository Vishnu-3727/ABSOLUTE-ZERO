---
tags: [lesson, navigation, coverage, mapping]
project: ASUNAMA
status: active
confidence: high
date: 2026-06-27
summary: Single-cell coverage marking couldn't reach 95%; mark the camera footprint instead.
---

# Mark the sensor footprint, not one grid cell

## What happened
EXPLORE marked one occupancy cell per tick as "covered." True coverage stalled
below the 95% acceptance bar — the camera actually sees a whole footprint each
tick, so single-cell marking under-counted forever.

## Lesson
Coverage marking must match the sensor's real ground footprint
(`mark_explored_footprint(x,y,radius)`, radius = FOV on ground). Gate it on pose
confidence so drift doesn't mark the wrong area.

## Transfer
Any sweep/survey robot — rover mapping, lawn/vacuum coverage. Topic:
[[coverage-planning]].
