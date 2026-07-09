---
tags: [core, principles]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-09
summary: Hard-won engineering rules; grows one entry at a time via the /review command.
---

# PRINCIPLES

<!-- Grows via /review. One principle per entry: the rule, then the lesson that earned it (link the lesson note). -->

## P1 — Make failure loud
A failure that hides costs days. Three separate ASUNAMA faults were all the same
shape — the error was there but silent: a traceback on **stderr** while the app
log stayed clean ([[read-stderr-not-app-log]]), an unbounded wait that
**deadlocked** instead of erroring ([[bounded-loop-over-unbounded-wait]]), and a
retry loop that **silently returned a bad value** on exhaustion
([[fail-loud-not-silent-fallback]]).

**Rule:** surface errors where you'll see them, bound every wait, and never fall
back silently — return `None`/skip/raise. Promoted from 3/5 faults in
`90_META/FAULT_LEDGER.md`. Topic: [[debugging-silent-failures]].
