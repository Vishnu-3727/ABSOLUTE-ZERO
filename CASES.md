---
tags: [core, experience, cases, reasoning, runtime]
project: ABSOLUTE_ZERO
status: active
confidence: medium
date: 2026-07-18
summary: Project Experience Engine spec — turns each completed project into a reusable case and surfaces the closest past case when a similar project starts.
---

# ABSOLUTE ZERO — Project Experience Engine (case-based reasoning)

`experience.py` learns at task granularity (one trace = one symptom→fix).
This layer learns at **project** granularity: a completed project's whole
run becomes one reusable **case**, and when a new project starts on similar
ground the closest past case is pulled forward. Implementation:
`scripts/cases.py` (stdlib). Sits above the experience engine, not inside it.

## 1. API

```
python scripts/cases.py close <PROJECT>          build + store the case
python scripts/cases.py close --all              every project with notes
python scripts/cases.py similar "<topic>"        rank past cases by a query
python scripts/cases.py similar --project <NEW>  rank against a project's profile
python scripts/cases.py list
python scripts/cases.py --selftest
```

## 2. A case (what "the whole run" distills to)

Built from artifacts the OS already produces — no new capture step:

| field | source |
|---|---|
| `tags` | union of `tags` across the project's INDEX.json notes |
| `components` | `10_PROJECTS/<NAME>/bootstrap.json` language / frameworks / deps |
| `topics` | wikilinks out of the project's notes (knowledge/lesson slugs) |
| `decisions` | `## ` headings of `DECISIONS.md` |
| `faults` | `## ` blocks of `FAULTS.md` → `{symptom, fix}` (do-not-repeat list) |
| `lessons` | `30_LESSONS` notes tagged with the project or linked from it |
| `workflows` | closed `90_META/traces` for this project → per-intent runs/pass |
| `signature` | tags ∪ components ∪ topics — the discrete things two projects can literally share |
| `blob` | overview + summaries + decisions + fault symptoms — the free-text match surface |

Stored twice: `90_META/experience/cases.json` (the machine index, `close`
overwrites a project's entry — idempotent) and a real
`10_PROJECTS/<NAME>/EXPERIENCE.md` note (frontmatter'd, so it is indexed and
also surfaces through `query` / `graph` / `experience.recall`).

## 3. Retrieval — the make-or-break

`similar` scores every stored case against the query by IDF-weighted
coverage — how much of the query's *informative* topic the case covers:

```
idf(w)  = log((N+1) / (df(w)+1))          # df = cases whose signature has w; 0 for a word in every case
score   = 0.6 · covered(signature) + 0.4 · covered(blob)
covered(S) = Σ idf(w) for w in query ∩ S  /  Σ idf(w) for w in query
```

Coverage, not jaccard: a broad case must not be penalised for breadth. IDF,
not raw counts: a word every project shares (`python`) carries weight 0, so a
generic query cannot false-positive while a specific one (`odometry`) matches
even alone. The text leg uses *containment* against the case blob (matched ÷
query), not `core.sim` jaccard — a large blob was drowning that term to zero.
Score ties break by recency. Matches below `FLOOR = 0.18` are dropped —
surfacing a wrong "related project" is worse than surfacing none. A free-text
query is tokenized by `core.nwords` (slugs split on `-_/.`); `--project <NEW>`
builds the new project's own profile (even before it is closed) and matches on
that. Each hit prints the terms it matched on, so a weak match is visible, not
hidden.

Verified (selftest + live): a GPS-denied drone query surfaces the ASUNAMA
case and never the unrelated one; an off-topic query returns nothing.

## 4. Integration

- **`/wake`**: when a session names or resumes a project, run
  `cases.py similar --project <NAME>` (or `similar "<topic>"` from the first
  request) and surface the top case's decisions + faults + reusable stack
  **before** starting work — reuse what worked, skip paid-for trial-and-error.
- **`/sleep` / project close**: run `cases.py close <NAME>` so the run just
  finished becomes retrievable next time. Learning is part of closing out.

ponytail: `components` come from `bootstrap.json` + note tags, not `graph.py`
— external projects (ASUNAMA lives at `C:\asunama`, outside the vault) have
no code nodes to walk. Add a graph-component signal when the target project
is the vault itself and precision caps out.
