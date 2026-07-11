---
tags: [core, verification, runtime]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-11
summary: Verification Engine spec — eleven checks over every modification, confidence score, gated verdict before completion.
---

# ABSOLUTE ZERO — Verification Engine

Verifies every modification before completion. Nothing is DONE until the
verifier says so — a gate failure exits nonzero and the /task VERIFY state
cannot pass. Implementation: `scripts/verifier.py` (stdlib; python analyzed
with `ast`, not regex guesswork).

## 1. API

```
python scripts/verifier.py check              git-changed files (default)
python scripts/verifier.py check <files...>   explicit set
python scripts/verifier.py check --all        whole-vault sweep
python scripts/verifier.py check --json       machine report
python scripts/verifier.py --selftest
```

Reports persist to `90_META/verify/<timestamp>.json`. Exit code: 0 unless
verdict is FAIL.

## 2. The eleven checks

| check | gate | what it does |
|---|---|---|
| architecture | ✔ | files inside vault taxonomy; python only in `scripts/`; root docs registered in indexer ROOT_DOCS |
| imports | ✔ | ast: every import stdlib or local (stdlib-only law = FAIL); unused imports (warn) |
| dependencies | ✔ | circular imports across `scripts/` (graphlib); dead wikilinks in changed notes (code blocks excluded) |
| naming | | ast: snake_case functions (dunders ok), PascalCase classes |
| complexity | | ast: >60 statements or nesting >4 per function; >500-line files |
| regression | | reverse import graph: who imports the changed module — their selftests are pulled into the test run |
| security | ✔ | hardcoded credentials, eval/exec, shell=True, os.system, pickle, absolute user paths; `# verifier:ignore` suppresses a line |
| performance | | IO/subprocess/compile calls inside loops (warn — sometimes inherent, flagged honestly) |
| formatting | | lines >100, trailing whitespace, tabs, missing final newline |
| documentation | | py: module docstring + usage example; md: frontmatter with mandatory summary ≤25 tokens, tags, date |
| tests | ✔ | every vault script has `--selftest` (OS law) and **the selftests of changed + dependent scripts are executed** |

## 3. Confidence and verdict

```
confidence = 100 * (1 - min(0.03*warns, 0.30) - 0.15*fails)   floor 0
verdict    = FAIL                 any fail in a gate category (✔ above)
           = PASS-WITH-WARNINGS   warns only
           = PASS                 clean
```

Warns cap at −30: style noise cannot zero the score. Fails are uncapped and
gate categories block completion — failure is loud by design (P1).

## 4. Integration

- `/task` VERIFY stage: run `verifier.py check` first, then the trace's
  intent checklist. FAIL verdict → retry EXECUTE or close fail; never
  SUMMARIZE over a failing verifier.
- Thresholds, gates, penalties, security patterns are constants at the top
  of `scripts/verifier.py` — tune there.
- First vault-wide sweep (2026-07-11): caught two real violations —
  query.py and review.py predated the selftest law; both fixed.
