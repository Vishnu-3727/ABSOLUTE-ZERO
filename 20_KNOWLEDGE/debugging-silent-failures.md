---
tags: [knowledge, debugging, diagnostics, reliability]
project: "-"
status: active
confidence: high
date: 2026-06-25
summary: Failures that hide — check stderr, prefer bounded loops, never fall back silently.
---

# Debugging silent / hidden failures

The expensive bugs are the ones that don't announce themselves. Patterns:

- **Read the error STREAM, not the app's own log.** A GUI/subprocess can sit
  blank or "not responding" while a real exception prints to **stderr** that
  never reaches the app's `.log`. Redirect stderr to a file first. See
  [[read-stderr-not-app-log]].
- **Prefer a bounded loop over a wait-for-condition.** Any
  "wait until frame N / signal arrives" can deadlock. A fixed-iteration loop
  structurally cannot hang. See [[bounded-loop-over-unbounded-wait]].
- **Never fall back silently.** A retry/sampler/allocation loop that "gives up"
  by returning the last (bad) value corrupts state invisibly. Return `None`,
  skip, or raise. See [[fail-loud-not-silent-fallback]].
- **Capture the real exit code** — a trailing `echo`/log line after a process
  masks its `$?`.
- **Version early** — an un-versioned project has no chronology and no
  rollback; regressions are unrecoverable.

Lessons: [[read-stderr-not-app-log]], [[bounded-loop-over-unbounded-wait]], [[fail-loud-not-silent-fallback]].
