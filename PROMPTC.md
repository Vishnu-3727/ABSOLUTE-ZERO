---
tags: [core, prompts, compiler, runtime]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-11
summary: Prompt Compiler spec — dynamically constructs optimized, validated prompts from intent, context, experience, tools and budget.
---

# ABSOLUTE ZERO — Prompt Compiler

Constructs prompts dynamically instead of hand-writing them. One compiled
prompt briefs a model (or a fresh agent) on a task with everything the OS
knows, inside a token budget. Implementation: `scripts/promptc.py`
(stdlib; composes classify, context.build, plugins.route, the VERIFY
checklists, and 30_LESSONS).

## 1. API

```
python scripts/promptc.py compile "<request>" [--project X] [--budget 5000]
                                              [--history <file>] [--json]
python scripts/promptc.py --selftest
```

Artifact: `90_META/prompts/<id>.md` (the compiled prompt, committed).
Exit 1 if validation fails. `--json` adds per-section stats.

## 2. Input → section pipeline

| input | becomes | source |
|---|---|---|
| Intent | TASK line + INSTRUCTIONS + VERIFY | `orchestrator.classify`, `INTENT_LINES`, checklists |
| Context | CONTEXT (auto-injected, tiered, budgeted) | `context.build` gets 55% of the budget |
| Knowledge/Experience | pinned ledger lines + ranked notes inside CONTEXT | context manager's spine + ranking |
| Skills/Repository | TOOLS directives with fallbacks | `plugins.route` chain |
| Experience (few-shot) | EXAMPLES: situation → lesson | closest 30_LESSONS notes by tag/jaccard |
| Budget | section drop + context tiering | see §3 |

Section order: LAW → TASK → INSTRUCTIONS → TOOLS → CONTEXT → EXAMPLES →
VERIFY → OUTPUT. LAW is the distilled CLAUDE.md core and, with TASK, is
never dropped.

## 3. Requirement → mechanism

- **Token optimization** — budget clamped to the 8k law; context gets a
  55% share (internally tiered full→section→summary→title); whole sections
  drop lowest-priority-first (EXAMPLES → TOOLS → CONTEXT → VERIFY →
  INSTRUCTIONS) until the prompt fits.
- **Instruction merging** — intent imperatives + verify checklist collected
  into one INSTRUCTIONS section.
- **Duplicate removal** — stemmed word-set jaccard > 0.5 between lines →
  later line dropped; count reported in stats.
- **Priority ordering** — fixed section order (law and task first), drop
  order encoded in `DROP_ORDER`, context items already score-ordered.
- **Automatic context injection** — the full context package (pinned
  spine, ranked tiered notes, extractive history, OMITTED tail) rendered
  into CONTEXT with per-source citations.
- **Few-shot retrieval** — top-2 lessons as worked examples
  (`situation: <summary>` / `lesson: <first paragraph>`), cited.
- **Prompt validation** — gates before emit: within budget (fail), TASK
  nonempty (fail), LAW present (fail), cited vault paths exist (warn),
  no empty sections (warn). Fail → exit 1, nothing emitted as "done".

## 4. Integration

- Brief a fresh agent or session on any task:
  `promptc.py compile "<request>" --project X` and hand over the artifact.
- /task usage: the compiled prompt is the RECALL+PLAN briefing in one shot
  when dispatching work outside the current context.
- LAW lines, intent imperatives, drop order, weights: constants at the top
  of `scripts/promptc.py`.
