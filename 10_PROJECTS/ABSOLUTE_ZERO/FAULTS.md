---
tags: [project, faults, absolute-zero]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-11
summary: Fault log for the vault/OS itself.
---

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
