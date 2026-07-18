## LAW
- Vault facts only; cite file paths. If it is not in the vault, say 'not in vault' and ask. (CLAUDE.md)
- Ask clarifying questions without hesitation - one question beats one wrong assumption.
- Confirm which OS before OS-dependent commands. pyenv+uv only, never conda.
- End the session with /sleep - a session without /sleep is failed.

## TASK
fix the drift bug
(project: ASUNAMA)
Intent: bug_fix (standard)

## INSTRUCTIONS
- Reproduce before fixing.
- Fix the root cause in the shared path, not the symptom at one caller.
- Record the fault in FAULTS.md with a topic wikilink.
- root cause named, not symptom
- fix exercised (test or run)

## TOOLS
- Use python scripts/query.py for retrieval (fallback: experience, graph)
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
--- 10_PROJECTS/ASUNAMA/EXPERIENCE.md (section) ---
## Key decisions
- 2026-06-27 — Localization anchor = ground-image mosaic, injected to EKF — Chose:** periodic absolute ORB-homography fix vs a geo-referenced map →
- 2026-06-27 — All processing on base-station laptop, Pi Zero = pure relay — Chose:** relay GStreamer/UDP video + MAVLink through Pi 0; compute on laptop.
- 2026-06-24 — Isaac Sim over Gazebo — Chose:** Isaac Sim.
- 2026-06-25 — USD-native material binding, not PreviewSurfaceCfg — Chose:** build `UsdPreviewSurface` directly via `UsdShade`.

## Lessons
- bounded-loop-over-unbounded-wait: Replicator orchestrator wait-for-frame deadlocked forever; a bounded update loop cannot hang.
- coordinate-frame-origin: RTH checked distance to (0,0) but home was the base station; mission never completed.
- coverage-footprint-not-cell: Single-cell coverage marking couldn't reach 95%; mark the camera footprint instead.
- fail-loud-not-silent-fallback: A sampler that silently placed features at the last spot on exhaustion caused overlaps; return None and skip.
- odometry-drift-absolute-fix: Optical-flow dead reckoning drifted unbounded under wind; fixed with periodic absolute visual fixes.
- read-stderr-not-app-log: The Isaac "white box" was a Python TypeError on stderr, not a GPU bug; the app log never showed it.
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
--- 30_LESSONS/bounded-loop-over-unbounded-wait.md (full) ---
# Bounded loop beats a wait-for-condition

## What happened
`rep.orchestrator.step(rt_subframes=48, pause_timeline=True)` deadlocked
forever on `omni.syntheticdata OgnSdOnNewFrame: frames discarded` — the
frame counter desynced under a paused timeline and the wait-for-frame loop
never returned. Looked like a 20-30 min "stuck" hang.

## Lesson
Replace unbounded "wait until frame N / signal arrives" with a
**fixed-iteration** loop (`for _ in range(RENDER_TICKS)` then read). A bounded
loop structurally cannot hang; you trade a guaranteed-terminating loop for a
tiny bit of wasted work.

## Transfer
Any robotics wait: sensor-ready polls, sim step barriers, hardware handshakes.
Prefer a timeout/iteration bound. Topic: [[debugging-silent-failures]].
--- 30_LESSONS/read-stderr-not-app-log.md (full) ---
# Read stderr, not the app's own log

## What happened
Isaac Sim showed a blank "white box" / "not responding" for days. Chased as an
Optimus dGPU / RTX shader-compile problem. The real cause: Isaac Lab's
`spawn_preview_surface` passed `name="Shader"` to a Kit command removed in Sim
6.0.0 → `TypeError` on **every** colored spawn. It threw to **stderr** while an
empty Kit sat onscreen; the kit `.log` never showed it.

## Lesson
When a subprocess/GUI hangs or renders blank, redirect **stderr** to a file
before theorizing about hardware. Python tracebacks go to stderr, not the
app's log. `run_headless_smoke.bat` (headless + redirect) nailed it in one run.

## Transfer
Any embedded/robotics stack where a child process (Kit, Gazebo, a ROS node)
"just hangs." Topic: [[debugging-silent-failures]].
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
--- 10_PROJECTS/ABSOLUTE_ZERO/FAULTS.md (full) ---
# ABSOLUTE ZERO — Faults

## 2026-07-11 — committed over a failing verifier gate
- **Symptom:** prompt-compiler changeset committed while `verifier.py check`
  verdict was FAIL; the VERIFY trace note claimed "no gate failures" without
  reading the actual output.
- **Root cause:** two stacked causes. (1) Runtime artifacts under
  `90_META/prompts/` were checked as authored notes — vault-note law
  (frontmatter, live wikilinks) applied to generated files quoting other
  notes. (2) Process: the gate's output was piped through grep and asserted
  green in the same chained command that committed — the commit did not
  depend on the gate's exit code.
- **Fix:** verifier now exempts `ARTIFACT_DIRS` (mirrors indexer
  SKIP_DIRS); and gates must be *read* before the state is logged — never
  chain gate + pass-note + commit in one command. ([[debugging-silent-failures]])
--- 10_PROJECTS/ASUNAMA/DECISIONS.md (full) ---
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
--- 40_RESEARCH/ardupilot-nongps-vision-params.md (section) ---
# ArduPilot non-GPS vision positioning — parameters

For ASUNAMA's vision-anchored EKF fix (feeds `deployment/fc_setup.py`).

## Core params (EKF source set 1)
- `GPS1_TYPE = 0` — disable GPS.
- `VISO_TYPE = 1` — enable visual odometry (**1, not 3**; 3 = VOXL — confirms the
  fc_setup fix). See [[gps-denied-localization]].
- `EK3_SRC1_POSXY = 6` (ExternalNav), `EK3_SRC1_POSZ = 6` or `1` (Baro).
- `EK3_SRC1_VELXY = 6` (ExternalNav) or `0`; `= 5` (OpticalFlow) if a flow
  sensor also feeds velocity — ASUNAMA uses flow for velocity, ExternalNav for
  position.
- `EK3_SRC1_YAW = 6` (ExternalNav) or `1` (Compass).
- `VISO_POS_X/Y/Z` — camera offset on the airframe.

## Quality gating
- `VISO_QUAL_MIN` — messages below this quality are ignored.
- Position error clamped to `[VISO_POS_M_NSE, 100]`, angle error to
  `[VISO_YAW_M_NSE, 1.5]`. Mirrors our inlier-confidence gate on the ORB fix.
--- 10_PROJECTS/ASUNAMA/BOOTSTRAP.md (summary) ---
auto-bootstrap of ASUNAMA - python/MAVLink, NumPy stack, OpenCV, PyTorch, pytest, 277 files, 8 risks
--- 30_LESSONS/retry-prefix-matching-in.md (summary) ---
FAIL: selftest still red -> retry: prefix matching in classify()
--- 10_PROJECTS/ASUNAMA/SESSIONS/2026-06-25.md (title) ---
Session — 2026-06-25
Known but not loaded (pull via query.py if needed): Session — 2026-06-26 (10_PROJECTS/ASUNAMA/SESSIONS/2026-06-26.md); Session — 2026-06-27 (10_PROJECTS/ASUNAMA/SESSIONS/2026-06-27.md); Debugging silent / hidden failures (20_KNOWLEDGE/debugging-silent-failures.md); Coverage & area planning (20_KNOWLEDGE/coverage-planning.md); IDENTITY (00_CORE/IDENTITY.md); PRINCIPLES (00_CORE/PRINCIPLES.md); ABSOLUTE ZERO — Dashboard (DASHBOARD.md); ABSOLUTE ZERO — Planning Engine (PLANNER.md)

## EXAMPLES
Example (30_LESSONS/odometry-drift-absolute-fix.md):
  situation: Optical-flow dead reckoning drifted unbounded under wind; fixed with periodic absolute visual fixes.
  lesson: 

Example (30_LESSONS/read-stderr-not-app-log.md):
  situation: The Isaac "white box" was a Python TypeError on stderr, not a GPU bug; the app log never showed it.
  lesson: 

## VERIFY
[ ] root cause named, not symptom
[ ] fix exercised (test or run)
[ ] FAULTS.md entry with topic wikilink

## OUTPUT
- Cite vault paths for every memory-based claim.
- Log orchestrator states as you pass them; close the trace before finishing.
