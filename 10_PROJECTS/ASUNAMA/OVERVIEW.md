---
tags: [project, overview, drone, navigation, isaac-sim]
project: ASUNAMA
status: active
confidence: high
date: 2026-07-09
summary: IRoC-U 2026 GPS-denied autonomous survey drone; Isaac Sim arena + vision-anchored base-station nav.
---

# ASUNAMA — Overview

## Goal
Team ASUNAMA, IRoC-U 2026: a **GPS-denied** autonomous survey drone that maps a
Martian arena, detects terrain features, and returns to base — no GPS, bounded
drift, ≥95% coverage, zero boundary breaches, under wind.

## Stack
- Sim: Isaac Sim 6.0.0 + Isaac Lab 0.54.4 at `C:\isaaclab`
  (`env_isaaclab\Scripts\python.exe`). Repo: `C:\asunama` (Windows side).
- ROS2 workspace lives on **Ubuntu** (not indexed here yet).
- Localization: ORB homography vs geo-referenced arena map → EKF vision fix.
- Nav: classical (occupancy grid, frontier + A*, FSM); PPO boundary-reflex +
  RTH-gate as thin learned augments (degrade to no-op without torch).
- Hardware: RTX 4060 Laptop (8GB) + AMD 890M Optimus; base-station laptop does
  all processing, Pi Zero is a pure relay.

## Current state
Full mission verified in sim (`covered=100%`, `PRECLAND OK`, 32 tests green).
Pre-flight items remain — see [[asunama-flight-checklist]] / RECENT.

## Links
Decisions: [[DECISIONS]] · Faults: [[FAULTS]] · Topics:
[[gps-denied-localization]], [[coverage-planning]], [[debugging-silent-failures]].
