---
tags: [lesson, software, reliability]
project: ASUNAMA
status: active
confidence: high
date: 2026-06-27
summary: A sampler that silently placed features at the last spot on exhaustion caused overlaps; return None and skip.
---

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
