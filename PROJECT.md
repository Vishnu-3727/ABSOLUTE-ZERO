---
tags: [core, project, scaffold, experience, runtime]
project: ABSOLUTE_ZERO
status: active
confidence: medium
date: 2026-07-18
summary: Project scaffolder spec — creating a project auto-injects the closest past case.
---

# ABSOLUTE ZERO — Project Scaffolder (autonomous experience injection)

Starting a project is a lifecycle event the OS can act on. `cases.py similar`
already retrieves the closest past run — but only when someone remembers to
ask. This layer removes the asking: creating a project **is** the query.
Implementation: `scripts/project.py` (stdlib). Sits above `cases.py` and
reuses its retrieval; it does not reimplement matching.

## 1. API

```
python scripts/project.py new <NAME>                    scaffold + inject
python scripts/project.py new <NAME> --topic "gps denied drone nav"
python scripts/project.py new <NAME> --tags drone,ros2
python scripts/project.py --selftest
```

`--topic` is the retrieval query. Without it the query is the project name
plus `--tags` — so naming a project descriptively is itself a search.

## 2. What `new` creates

`10_PROJECTS/<NAME>/` from the vault templates, placeholders instantiated
(`<NAME>`, `<YYYY-MM-DD>`, `summary:`) and the example ledger entry stripped
so a fresh project carries no dangling placeholder wikilinks:

| file | source |
|---|---|
| `OVERVIEW.md` | `90_META/templates/project_OVERVIEW.md` |
| `DECISIONS.md` | `90_META/templates/project_DECISIONS.md` |
| `FAULTS.md` | `90_META/templates/project_FAULTS.md` |
| `RECENT.md` | generated (no template exists) |
| `SESSIONS/` | empty dir for session logs |
| `PRIOR_EXPERIENCE.md` | **generated from case retrieval — the point of this engine** |

Fails loud on an existing project (never overwrites a live ledger) and on a
name that is not alphanumeric/underscore/dash (`../evil` is refused).

## 3. The injected note

`PRIOR_EXPERIENCE.md` is a real frontmatter'd note — indexed, graphed and
reachable by `query`/`recall` like anything else. Per retrieved case it
carries the reusable stack, the decisions that worked, the faults to avoid
(symptom → fix) and the lessons, each headed by the match score and the terms
it matched on. No case clears the floor → the note says so plainly ("new
ground") rather than manufacturing a weak relation.

## 4. Integration

- **project start**: `new` is the trigger. The prior experience is on disk
  before the first line of work.
- **`/wake`**: already runs `cases.py similar`; for a scaffolded project the
  note is there to read directly.
- **`/sleep`**: `cases.py close <NAME>` turns the finished run into the next
  project's injected note. The loop closes.

ponytail: the trigger is the `new` command — deterministic and
cross-platform. A watcher firing the moment a `10_PROJECTS/<dir>` appears is
the true-daemon upgrade; it belongs on the Ubuntu systemd side, not in a
fragile Windows watcher today.
