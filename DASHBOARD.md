---
tags: [meta, dashboard]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-09
summary: Obsidian Dataview dashboard — active goals, recent sessions, open faults, newest lessons.
---

# ABSOLUTE ZERO — Dashboard

> Requires the **Dataview** community plugin (Settings → Community plugins →
> install "Dataview" → enable). Queries re-run live; the tables below refresh on
> every `/sleep` (indexer + new notes). Plain text renders if Dataview is off.

## Open goals
```dataview
TASK
FROM "00_CORE/ACTIVE_GOALS"
WHERE !completed
```

## Active projects
```dataview
TABLE status, summary
FROM #overview
SORT project ASC
```

## Recent sessions
```dataview
TABLE project, summary, date
FROM #session
SORT date DESC
LIMIT 8
```

## Newest lessons
```dataview
TABLE summary, date
FROM #lesson
SORT date DESC
LIMIT 8
```

## Open faults (ledger)
![[90_META/FAULT_LEDGER]]

## Latest research
```dataview
TABLE summary, date
FROM #research
SORT date DESC
LIMIT 5
```
