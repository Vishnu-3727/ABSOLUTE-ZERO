# ABSOLUTE ZERO — Build Guide

Execute phases in order. Do not skip acceptance tests. Confirm the user's OS
before any OS-dependent step (target is Ubuntu 24.04 unless told otherwise).

## Phase 1 — Skeleton (one session)
1. Create structure:
   00_CORE/ (IDENTITY.md, ACTIVE_GOALS.md, PRINCIPLES.md)
   10_PROJECTS/  20_KNOWLEDGE/  30_LESSONS/  40_RESEARCH/
   90_META/ (templates/, INDEX_SUMMARY.md placeholder)
   scripts/
2. Write IDENTITY.md by interviewing the user (hardware, prefs, active projects).
3. Create templates: project OVERVIEW, DECISIONS, FAULTS, session log, lesson note.
   Every template includes full YAML frontmatter with mandatory summary field.
4. git init, first commit.
5. Migrate existing project context (ASCEND, BMS, etc.) by interviewing the user
   and/or importing their existing vault notes. Populate initial 30_LESSONS/
   from known past faults.
ACCEPT: vault opens in Obsidian, graph shows linked notes, git log has commits.

## Phase 2 — Memory machinery (one to two sessions)
1. scripts/indexer.py (stdlib only): walks vault, parses frontmatter, emits
   90_META/INDEX.json (all notes: path, tags, summary, links, date),
   90_META/INDEX_SUMMARY.md (one line per project + counts, <300 tokens),
   90_META/FAULT_LEDGER.md (one line per fault: [proj][tags] symptom -> fix (link)).
2. scripts/query.py: CLI filters INDEX.json by tags/type/project/date,
   prints title + summary + path per hit. Nothing else.
3. Wire /wake and /sleep per FLOW.md.
ACCEPT: /wake loads under 1k tokens of vault content. query.py returns correct
hits for a known tag. /sleep produces log, ledger update, and a git commit.

## Phase 3 — Lesson transfer test (one session)
1. Ensure 30_LESSONS/ has at least 5 real lessons from past drone/BMS work,
   each linked to topic notes.
2. TEST: start a fake project "ROVER-NAV" (autonomous rover, ROS2).
   /recall ros2,navigation must surface the drone-era lessons (EKF timestamps,
   QoS, empy pin, etc.) with file citations, total context cost under 5k tokens.
3. TEST: /recall on a topic not in vault must return "not in vault" with no
   fabricated memory.
ACCEPT: both tests pass. This is the go/no-go gate for the whole system.

## Phase 4 — Research, review, predict (one to two sessions)
Implement /research, /review, /predict per FLOW.md.
ACCEPT: /research produces a sourced note; /review promotes at least one
pattern to PRINCIPLES.md; /predict cites evidence paths and labels estimates.

## Phase 5 — Dashboard, phase A only
1. DASHBOARD.md in vault root using Dataview queries (requires Dataview plugin):
   active goals, recent sessions, open faults, newest lessons.
2. Obsidian graph view = the brain visual. No web UI yet.
ACCEPT: dashboard renders in Obsidian and updates after a /sleep.
Web dashboard (single-file HTML + stdlib http.server reading INDEX.json) is
Phase 5B, ONLY after two weeks of real use proves the memory loop.

## Phase 6 — Automation (Ubuntu)
1. systemd user timer: nightly indexer run + git commit.
2. Weekly reminder to run /review.
ACCEPT: timer fires, index stays fresh without manual runs.

## Standing rules for the builder
- Never expand scope beyond the current phase.
- Every script: stdlib only, works on Linux and Windows paths (use pathlib).
- If a phase acceptance test fails, fix before proceeding, never skip.
- Keep all generated notes terse. Verbose notes are a token tax forever.