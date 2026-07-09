---
tags: [lesson, debugging, diagnostics]
project: ASUNAMA
status: active
confidence: high
date: 2026-06-25
summary: The Isaac "white box" was a Python TypeError on stderr, not a GPU bug; the app log never showed it.
---

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
