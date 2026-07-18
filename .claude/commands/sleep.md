---
description: ABSOLUTE ZERO — session end (close traces, capture the case, reindex, commit). Mandatory.
---
Execute the `/sleep` flow from `FLOW.md`, in this order:

1. **Close any open trace first.** Check `90_META/traces/*.json` for
   `"result": null`. An open trace at sleep means the work never passed
   verify — close it honestly (`--result fail`) rather than leaving it
   dangling. Closing runs the learning loop: harvest, reindex, case
   refresh, graph, dashboard. Read its report; a `FAILED` line is real.
2. Session log to `10_PROJECTS/<proj>/SESSIONS/YYYY-MM-DD.md`, overwrite
   `RECENT.md` (max 10 lines), append new FAULTS entries with topic
   wikilinks, add any transferable `30_LESSONS/` note, update
   `ACTIVE_GOALS.md`.
3. `python scripts/cases.py close <PROJECT>` — the run just finished becomes
   a retrievable case, so the next similar project starts with it. A trace
   closed with `--project` in step 1 already refreshed that case; this
   covers work done without a trace. Skip only if no project was touched.
4. `python scripts/indexer.py` — needed only if step 1 closed nothing; the
   learning loop already reindexed otherwise.
5. `git add -A && git commit -m "sleep: <proj> <date>"`.
