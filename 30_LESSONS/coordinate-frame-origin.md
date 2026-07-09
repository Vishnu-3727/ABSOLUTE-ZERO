---
tags: [lesson, navigation, localization, coordinate-frames]
project: ASUNAMA
status: active
confidence: high
date: 2026-06-27
summary: RTH checked distance to (0,0) but home was the base station; mission never completed.
---

# "Home" is a named point, not (0,0)

## What happened
The state machine's Return-To-Home measured distance to `(0,0)` via
`is_near_home()`, but home was the **base station** at e.g. `(1,1)` in the
vision-anchored frame. RTH never registered arrival → mission never completed.

## Lesson
Never assume the origin. Measure to the **explicit anchored point** in the
frame you actually navigate in. An implicit `(0,0)` is a latent frame bug.

## Transfer
Directly applies to a rover's return-to-dock, any "go to base" behavior, and
multi-frame transforms (map vs odom vs base_link). Topic:
[[gps-denied-localization]].
