---
description: ABSOLUTE ZERO — start a new project (scaffold + auto-inject prior experience).
---
Start a new project. Contract: `PROJECT.md`.

Run `python scripts/project.py new <NAME> --topic "<what this project is>"`
(add `--tags a,b` if the user gave a stack). The topic is the retrieval query,
so write it from what the user actually said, not just the project name.

Then, without being asked:

1. Read the generated `10_PROJECTS/<NAME>/PRIOR_EXPERIENCE.md`.
2. Brief the user on what past runs teach this one — reusable stack, decisions
   that worked, faults to not repeat. If no case cleared the floor, say so
   plainly: this is new ground.
3. Run `python scripts/indexer.py` so the new project is indexed.
4. Fill `OVERVIEW.md`'s Goal / stack / current-state from the conversation —
   a scaffolded file left on placeholders is unfinished work.
