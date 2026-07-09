---
tags: [lesson, robotics, reliability]
project: ASUNAMA
status: active
confidence: high
date: 2026-06-25
summary: Replicator orchestrator wait-for-frame deadlocked forever; a bounded update loop cannot hang.
---

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
