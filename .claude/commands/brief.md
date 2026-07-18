---
description: ABSOLUTE ZERO — compile a briefing for a fresh agent/session, and price it.
argument-hint: <the request> [--project X]
---
Compile a self-contained briefing for handing work to a fresh agent or
session. Contracts: `PROMPTC.md`, `TOKEN.md`.

1. `python scripts/promptc.py compile "$ARGUMENTS"` — add `--project X` when
   the work belongs to one. This writes the briefing to `90_META/prompts/`.
2. `python scripts/profiler.py report` — prices the briefing just compiled
   (it reads the newest prompt). Report the token count and cost.
3. If the briefing is over budget, say which section is heaviest rather than
   silently handing over an oversized prompt — the profiler breaks the count
   down by section.

Use this when dispatching work elsewhere, not for work you are doing now:
`/task` already packs its own context.
