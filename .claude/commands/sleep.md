---
description: ABSOLUTE ZERO — session end (write logs, reindex, commit). Mandatory.
---
Execute the `/sleep` flow exactly as defined in `FLOW.md`:
session log, RECENT.md (overwrite, max 10 lines), new FAULTS entries with topic
wikilinks, any transferable 30_LESSONS/ note, ACTIVE_GOALS update, then
`python scripts/indexer.py`, then `git add -A && git commit`.
