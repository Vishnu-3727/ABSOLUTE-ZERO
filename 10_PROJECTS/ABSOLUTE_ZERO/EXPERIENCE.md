---
tags: [absolute-zero, budget, bug-fix, case, cases, compiler, context, core, dashboard, discovery, experience, faults, goals, identity, meta, orchestrator, planning, plugins, principles, project, prompts, quick-fix, reasoning, runtime, scaffold, skills, token, tooling, v3, verification]
project: ABSOLUTE_ZERO
status: active
confidence: medium
date: 2026-07-18
summary: Project experience case for ABSOLUTE_ZERO - reusable decisions, faults and stack.
---

# ABSOLUTE_ZERO — Project Experience

## Stack / components
- (none recorded)

## Key decisions
- (none recorded)

## Faults & fixes (do not repeat)
- **prompt-compiler changeset committed while `verifier.py check`** → verifier now exempts `ARTIFACT_DIRS` (mirrors indexer

## Lessons
- bounded-loop-over-unbounded-wait: Replicator orchestrator wait-for-frame deadlocked forever; a bounded update loop cannot hang.
- fail-loud-not-silent-fallback: A sampler that silently placed features at the last spot on exhaustion caused overlaps; return None and skip.
- read-stderr-not-app-log: The Isaac "white box" was a Python TypeError on stderr, not a GPU bug; the app log never showed it.
- removed-the-broken-file: verify failed -> removed the broken file
- retry-prefix-matching-in: FAIL: selftest still red -> retry: prefix matching in classify()

## Workflows that ran
- feature: 8/8 pass
- performance: 2/2 pass
- architecture: 3/3 pass
- quick_fix: 1/1 pass
- security: 1/1 pass
- research: 1/1 pass
