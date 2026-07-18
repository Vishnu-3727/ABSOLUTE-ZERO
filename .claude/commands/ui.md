---
description: ABSOLUTE ZERO — open the live vault terminal in a browser.
argument-hint: [--port N]
---
Serve the vault terminal. Contract: `DASHBOARD.md`.

1. `python scripts/dashboard.py` — render current state to
   `90_META/dashboard.html`. Skip this if a trace closed recently; the
   learning loop already regenerated it.
2. `python scripts/server.py [--port N]` — serves it at
   `http://localhost:8080` (default). **This blocks.** Run it in a
   background shell, then tell the user the URL; never run it in the
   foreground and stall the session waiting for a server that never exits.
3. The user stops it themselves (Ctrl-C in that shell).

For a static snapshot instead of a live server, `dashboard.py --out <path>`
writes the HTML anywhere and needs no process left running.
