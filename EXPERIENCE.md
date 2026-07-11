---
tags: [core, experience, learning, runtime]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-11
summary: Experience Learning Engine spec — extracts lessons, failures, workflows, reusable code and patterns after every completed task.
---

# ABSOLUTE ZERO — Experience Learning Engine

Learns from every completed task, automatically, from artifacts the OS
already produces. Implementation: `scripts/experience.py` (stdlib).

## 1. API

```
python scripts/experience.py harvest [--trace <file>]   all unharvested closed traces
python scripts/experience.py recall "<query>"           semantic retrieval
python scripts/experience.py --selftest
```

Idempotent: harvested traces are marked `"harvested": true` and skipped.

## 2. Extraction → storage

| extraction | source | stored where |
|---|---|---|
| Lessons | a VERIFY-fail note followed by its retry EXECUTE note is a symptom→fix pair | drafted into `30_LESSONS/<slug>.md` (`status: draft`, `confidence: low`, trace cited) — real indexed notes; /review promotes or prunes. Deduped ≥0.5 sim vs existing lessons |
| Failures | traces closed `result: fail` | appended to the project's `FAULTS.md` with retries + last note |
| Successful workflows | every closed trace: intent, pipeline, retries, transition-timestamp durations | `90_META/experience/workflows.json` — per-intent runs, pass rate, retries, seconds (the known-good recipes) |
| Reusable code | ast: function bodies across `scripts/`, difflib > 0.75 (main/selftest excluded — those are convention, not duplication) | harvest report: extract-to-shared candidates |
| Architectural patterns | motif regexes counted across the corpus (selftest-guard, docstring-contract, data-table-config, artifact-dir, argparse-subcommands, fail-loud, shared-kernel); ≥3 scripts = confirmed | `90_META/experience/patterns.json` with evidence |

## 3. Semantic retrieval

`recall "<query>"` ranks everything harvested — lessons (direct
`30_LESSONS/` scan, so drafts surface before any reindex), workflows,
patterns — by stemmed-jaccard + difflib similarity, kind-tagged with
citations. Empty → "not in vault".

## 4. Integration

- `/sleep` step 6.5: `experience.py harvest` — learning is part of going to
  sleep, not optional.
- `/task` step 6: after `close`, harvest that trace immediately
  (`harvest --trace <file>`).
- First real harvest (2026-07-11): 9 traces → 1 lesson drafted (classifier
  prefix-match fix), all 7 motifs confirmed, and two genuine duplicate
  functions found (`load` in query/review/promptc, `nwords/norm` in
  experience/skills) — refactor candidates for a future task.
