---
tags: [core, context, budget, runtime]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-11
summary: Context Budget Manager spec — builds the optimal context package per request within a token ceiling.
---

# ABSOLUTE ZERO — Context Budget Manager

Decides what enters model context, at what fidelity, within a token budget.
Makes CLAUDE.md's context law (5k target / 8k max, pull not push, max 3 full
notes) computable instead of honor-system. Implementation:
`scripts/context.py` (stdlib; reuses `orchestrator.classify`).

## 1. API

```
python scripts/context.py pack "<request>" [--project X] [--budget 5000]
                                           [--history <file>] [--json]
python scripts/context.py --selftest
```

Inputs: request text, INDEX.json (Knowledge), FAULT_LEDGER.md (Experience),
similarity scoring (shared with the Similarity Engine), `.claude/commands/`
(Skills), optional conversation-history file, project name.
Output: the Optimal Context Package — human table, or `--json` for the full
machine package (includes the compressed texts).

Package shape:

```json
{
  "request": "...", "intent": "bug_fix", "budget": 5000, "used": 3626,
  "pinned":  [{"path", "tier", "tokens", "reason", "text"}],
  "items":   [{"path", "tier", "tokens", "score", "reason", "text"}],
  "history": {"path", "tokens", "text"},
  "skills":  ["recall", "review"],
  "dropped_dups": ["..."], "omitted": ["title (path)"]
}
```

## 2. Algorithm (selection pipeline)

1. **Budget clamp** — `min(--budget, 8000)`; the 8k hard cap is law.
2. **Wake-set dedup** — CLAUDE.md, ACTIVE_GOALS, INDEX_SUMMARY are already
   in context at session start; never double-loaded.
3. **Pinned architecture spine** — survives any budget pressure:
   project OVERVIEW.md + RECENT.md, plus FAULT_LEDGER lines whose words
   intersect the request (stopword-filtered). If the spine alone exceeds
   the budget, warn loudly (that is the escalation case).
4. **History compression** — extractive, ≤15% of budget: lines matching
   request words + last 10 lines; oldest evicted first when over cap.
   (Abstractive summarization is the model's job at runtime, not python's.)
5. **Rank** — score every candidate note (see §3), drop score < 0.5.
   Budget is a ceiling, not a quota: irrelevant notes stay out even with
   room to spare.
6. **Deduplicate** — pairwise Jaccard on title+summary words > 0.6 →
   lower-scored note dropped, reported in `dropped_dups`.
7. **Greedy select with fidelity degradation** (semantic compression):
   `full` (≤400 tok) → `section` (only headings whose section matches
   request words) → `summary` (frontmatter line) → `title`. Highest score
   first; degrade until it fits; stop when < 8 tokens remain.
8. **One-hop dependency pull** — outbound wikilinks of every selected/pinned
   note come along at summary tier while budget allows (this carries the
   fault → topic-note rule). One hop only; go transitive if chains deepen.
9. **Skill prioritization** — intent → relevant commands
   (research → /research /recall, security → /recall /review, …
   default /recall).
10. **Omitted tail** — everything known-but-not-loaded is listed by title,
    so the model knows what it does not know and can pull later.

## 3. Scoring function

```
score(note) = 2.0 * |request_words ∩ note_tags|
            + 1.5 * max(jaccard(request_words, title+summary words),
                        SequenceMatcher(request, title+summary).ratio())
            + type_prior          fault 1.0 > lesson .8 > knowledge/decision .6
                                  > research .5 > overview/recent .4 > core .3
                                  > session .2 > doc .1
            + 0.5 * [note.project == --project]
            + recency             ≤30d +0.3, ≤180d +0.15, else 0
```

Rationale: tags are curated signal (heaviest); faults outrank everything of
equal relevance (they are the expensive lessons); sessions and root docs are
low-prior because they are long and rarely the answer. Token cost estimate:
`len(text) / 4`.

## 4. Integration

- `/task` RECALL stage runs `context.py pack` (the orchestrator's plan
  output prints the exact command). Trivial tasks: ledger scan only.
- `/recall` stays `query.py` for cheap manual lookups; `pack` is the
  budget-aware superset.
- Weights, priors, caps are constants at the top of `scripts/context.py` —
  edit there; this doc describes, code decides.
