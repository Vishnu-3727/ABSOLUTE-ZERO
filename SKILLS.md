---
tags: [core, skills, discovery, runtime]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-11
summary: Skill Discovery Engine spec — determines which skills load for a request, ordered, deduplicated, conflict-resolved.
---

# ABSOLUTE ZERO — Skill Discovery Engine

Determines which skills should be loaded for a request, in what order.
Implementation: `scripts/skills.py` (stdlib; reuses `orchestrator.classify`,
the plugin engine's capability vocabulary, `promptc.stem`, `context.STOP`).

## 1. API

```
python scripts/skills.py discover "<request>" [--history <file>] [--json]
python scripts/skills.py --selftest
```

Output: ordered skill list with confidence + reason, printed and written to
`90_META/skills/last_discovery.json` — the **automatic-loading contract**:
the /task runtime reads the manifest and invokes the list top-down (python
cannot force a model to load a skill; the manifest + FLOW law is the
mechanism).

## 2. Requirement → mechanism

| requirement | mechanism |
|---|---|
| Keyword matching | stemmed, stopword-filtered word overlap between request and skill text (name, description, body) |
| Semantic matching | capability space: request+intent → capabilities (plugin engine vocabulary), matched against the skill's capabilities; plus difflib ratio on the description — same-meaning-different-words matches |
| Dependency matching | vault skills that reference `/other` skills pull them in at 0.8× confidence ("dependency of /x") |
| Confidence scoring | `min(1, 0.35·keyword + 0.45·semantic + 0.15·history + 0.05·vault-local)` per skill, reported |
| Conflict detection | explicit pairs (`wake`↔`sleep`: keep higher confidence) + subsumption (`task` ⊃ `recall`: subset dropped); every resolution reported |
| Skill chaining | phase order beats confidence: wake(0) → task/recall(1) → work skills(2) → sleep(9); confidence orders within a phase |
| Automatic loading | manifest file (overwritten each discovery, RECENT.md-style) + LOAD list in /task flow |

Skill sources: `.claude/commands/*.md` (vault, name-collision priority) and
every `SKILL.md` under `~/.claude/plugins/cache` (external). History file:
last 30 lines boost skills whose text overlaps recent conversation.

## 3. Integration

- `/task` INTAKE: `skills.py discover "<request>"` right after
  `orchestrator.py plan` — load the manifest list before RECALL.
- Threshold (0.15), top-N (6), phases, conflict pairs, subsumption table:
  constants at the top of `scripts/skills.py`.
- Skills below threshold: "proceed bare" — never fake a match.
