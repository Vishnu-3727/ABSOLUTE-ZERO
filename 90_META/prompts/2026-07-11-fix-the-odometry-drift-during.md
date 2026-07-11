## LAW
- Vault facts only; cite file paths. If it is not in the vault, say 'not in vault' and ask. (CLAUDE.md)
- Ask clarifying questions without hesitation - one question beats one wrong assumption.
- Confirm which OS before OS-dependent commands. pyenv+uv only, never conda.
- End the session with /sleep - a session without /sleep is failed.

## TASK
fix the odometry drift during gps denied flight
(project: ASUNAMA)
Intent: bug_fix (standard)

## INSTRUCTIONS
- Reproduce before fixing.
- Fix the root cause in the shared path, not the symptom at one caller.
- Record the fault in FAULTS.md with a topic wikilink.
- root cause named, not symptom
- fix exercised (test or run)

## TOOLS
- Use python scripts/query.py for retrieval (fallback: /review, codex)
- Use python scripts/review.py for audit (fallback: /review, codex)

## CONTEXT
--- 10_PROJECTS/ASUNAMA/OVERVIEW.md (pinned: project spine) ---
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
Research: [[ardupilot-nongps-vision-params]].
--- 10_PROJECTS/ASUNAMA/RECENT.md (pinned: project spine) ---
# ASUNAMA — Recent

- Status: full mission verified in sim (100% coverage, PRECLAND OK, 32 tests green).
- M0-M3 learning augments trained (nav reflex + RTH gate policies).
- Next (pre-flight): regenerate 175 ORB refs (7 labels); set FC non-GPS params
  via `fc_setup.py`; stand up Pi-0 relay; bench hover test.
- See [[asunama-flight-checklist]].
--- 30_LESSONS/odometry-drift-absolute-fix.md (full) ---
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
--- 20_KNOWLEDGE/gps-denied-localization.md (full) ---
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
--- 10_PROJECTS/ASUNAMA/FAULTS.md (summary) ---
Real ASUNAMA faults — white box, headless deadlock, RTH frame bug, feature piling, coverage stall.
--- 30_LESSONS/fail-loud-not-silent-fallback.md (full) ---
# Fail loud — a silent fallback hides the bug

## What happened
`build_features.sample_xy` reject-sampled placement positions but, when it ran
out of tries, **silently** returned the last (overlapping) candidate. Adding
salt/streak features over-subscribed the arena, exhaustion became common, and
features piled on top of each other — invisibly, until renders showed it.

## Lesson
A retry/allocation loop must not "give up" by returning a bad value. Return
`None` on exhaustion and have every caller **skip** (or raise). Silent
fallbacks corrupt state without a trace.

## Transfer
Any placement/retry/allocation/path-planning loop with a try budget. Topic:
[[debugging-silent-failures]], see also [[coverage-planning]].
--- 30_LESSONS/coordinate-frame-origin.md (full) ---
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
--- 30_LESSONS/coverage-footprint-not-cell.md (full) ---
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
--- 30_LESSONS/bounded-loop-over-unbounded-wait.md (summary) ---
Replicator orchestrator wait-for-frame deadlocked forever; a bounded update loop cannot hang.
--- 30_LESSONS/read-stderr-not-app-log.md (summary) ---
The Isaac "white box" was a Python TypeError on stderr, not a GPU bug; the app log never showed it.
--- 10_PROJECTS/ASUNAMA/DECISIONS.md (summary) ---
Key locked decisions — Isaac over Gazebo, absolute visual fix, base-station processing, USD-native materials.
--- 40_RESEARCH/ardupilot-nongps-vision-params.md (summary) ---
ArduPilot non-GPS vision-positioning params — EK3_SRC1, VISO_TYPE, VISION_POSITION_ESTIMATE, EKF origin.
Known but not loaded (pull via query.py if needed): Session — 2026-06-26 (10_PROJECTS/ASUNAMA/SESSIONS/2026-06-26.md); Session — 2026-06-27 (10_PROJECTS/ASUNAMA/SESSIONS/2026-06-27.md); Session — 2026-06-25 (10_PROJECTS/ASUNAMA/SESSIONS/2026-06-25.md); Debugging silent / hidden failures (20_KNOWLEDGE/debugging-silent-failures.md); Coverage & area planning (20_KNOWLEDGE/coverage-planning.md); IDENTITY (00_CORE/IDENTITY.md); PRINCIPLES (00_CORE/PRINCIPLES.md); ABSOLUTE ZERO — Dashboard (DASHBOARD.md)

## EXAMPLES
Example (30_LESSONS/odometry-drift-absolute-fix.md):
  situation: Optical-flow dead reckoning drifted unbounded under wind; fixed with periodic absolute visual fixes.
  lesson: 

## VERIFY
[ ] root cause named, not symptom
[ ] fix exercised (test or run)
[ ] FAULTS.md entry with topic wikilink

## OUTPUT
- Cite vault paths for every memory-based claim.
- Log orchestrator states as you pass them; close the trace before finishing.
