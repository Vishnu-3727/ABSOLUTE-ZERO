# ❄️ ABSOLUTE ZERO

**A deterministic agentic OS for LLMs.** Zero dependencies. Zero vendor lock-in.
Zero forgotten lessons.

ABSOLUTE ZERO is a personal engineering brain built as an Obsidian vault plus 14
stdlib-only Python engines. The LLM (Claude, GPT, anything with a shell) is the
CPU; the scripts are the syscalls; markdown is the memory. Every task is
classified, planned, context-packed within a token budget, routed to the best
tool, executed, mechanically verified, and harvested for lessons — so the same
mistake is never paid for twice.

> The bet: you don't need a proprietary model to outperform SOTA coding agents.
> You need better orchestration around whichever model you have.

## Why it exists

LLM sessions are amnesiac. Context windows are budgets, not warehouses. Agent
frameworks are dependency towers that rot. ABSOLUTE ZERO answers all three with
one design:

- **Memory is markdown** — human-readable, git-versioned, greppable forever.
- **Intelligence is swappable** — every engine is a plain CLI with JSON output;
  any model on any machine can drive it.
- **Nothing is trusted** — an 11-check verifier gates every change; a state
  machine rejects illegal workflow transitions loudly; failures become ledger
  entries that future tasks are forced to see.

## The engines

| Engine | Script | What it does |
|---|---|---|
| Orchestrator | `orchestrator.py` | Classifies every request (intent × complexity), issues a strategy pipeline, enforces the state machine trace |
| Context | `context.py` | Builds the Optimal Context Package: pinned spine, scored ranking, fidelity tiers, dedup, budget ceiling, OMITTED tail |
| Planner | `planner.py` | Decomposes into subtasks, per-intent step templates with risk/test/rollback, topological order, validation gates |
| Verifier | `verifier.py` | 11 checks (ast analysis, vault law, security patterns, real selftest execution) → gated verdict; FAIL exits 1 |
| Plugins | `plugins.py` | Discovers every tool, scores by coverage/reliability/latency, greedy set-covers a chain + fallbacks, learns from outcomes |
| Prompt compiler | `promptc.py` | Composes LAW > TASK > INSTRUCTIONS > TOOLS > CONTEXT > EXAMPLES > VERIFY > OUTPUT under budget pressure |
| Skills | `skills.py` | Discovers which skills to load, resolves conflicts/subsumption, phase-orders the chain |
| Experience | `experience.py` | Harvests closed traces into draft lessons, fault entries, workflow stats, duplicate-code alerts, pattern counts |
| Agents | `agents.py` | 8-role multi-agent runtime: dynamic DAG per request, parallel scheduling, CAS blackboard, message bus |
| Graph | `graph.py` | Typed knowledge graph (8 node / 7 edge types) over code, notes, skills; BFS, shortest path, semantic search |
| Bootstrap | `bootstrap.py` | Onboards any repo in one command: language, frameworks, architecture, risks, conventions, context package |
| Indexer | `indexer.py` | Frontmatter → INDEX.json, INDEX_SUMMARY.md, FAULT_LEDGER.md |
| Query | `query.py` | Pull-based retrieval by tags/type/project/date |
| Review | `review.py` | Orphan + stale note detection |

All engines: stdlib only, cross-platform (`pathlib`), self-tested
(`--selftest` is law — 14/14), fail loud (P1).

## Quick start

```bash
git clone https://github.com/Vishnu-3727/ABSOLUTE-ZERO.git
cd ABSOLUTE-ZERO
cp scripts/hooks/pre-commit .git/hooks/   # commit gate: verifier must pass

python scripts/indexer.py                 # build the index
python scripts/orchestrator.py plan "fix the date crash in review.py"
python scripts/context.py pack "odometry drift on takeoff" --project ASUNAMA
python scripts/verifier.py check          # gate your changes
python scripts/dashboard.py               # render the ICE dashboard (HTML)

# health check: every engine proves itself
for s in scripts/*.py; do python "$s" --selftest; done
```

Requires Python 3.11+. No `pip install`. Ever. (That's a law — the verifier
rejects non-stdlib imports.)

## The workflow

```
/wake  → briefing from CLAUDE.md + ACTIVE_GOALS + INDEX_SUMMARY (≈800 tokens)
/task  → orchestrator trace: RECALL → PLAN → EXECUTE → VERIFY → SUMMARIZE
          (VERIFY fail → retry EXECUTE, max 2, enforced by the state machine)
/recall → query.py + graph.py, citations or "not in vault" — never invented
/sleep → session log, experience harvest, reindex, graph rebuild, commit
```

Command contracts live in `FLOW.md`; the constitution is `CLAUDE.md`; each
engine has a one-page spec at the vault root (`ORCHESTRATOR.md`, `CONTEXT.md`,
…).

## Vault anatomy

```
00_CORE/        identity, active goals, principles (grown via /review)
10_PROJECTS/    per-project OVERVIEW / DECISIONS / FAULTS / SESSIONS
20_KNOWLEDGE/   topic notes
30_LESSONS/     transferable lessons (auto-drafted from failed verifies)
40_RESEARCH/    sourced research notes
90_META/        INDEX.json, FAULT_LEDGER, traces, plans, runs, dashboard.html
scripts/        the 14 engines
```

Every note carries YAML frontmatter with a mandatory ≤25-token `summary` —
that's what makes budget-priced retrieval possible.

## Design laws

1. **Stdlib only.** Dependencies are future breakage.
2. **Fail loud.** Silent fallbacks cost sessions (learned the hard way — see
   the fault ledger).
3. **Budget is a ceiling, not a quota.** Low-relevance context stays out even
   with room left.
4. **Vault facts only.** Claims carry file-path citations or "not in vault".
5. **Every script carries its own proof.** `--selftest` or it doesn't merge.
6. **Artifacts are committed, never indexed.** Work memory ≠ knowledge memory.

## Audit

A full principal-systems audit (architecture, bottlenecks, scalability,
failure recovery, redesign proposals with patches) lives in
[`AUDIT.md`](AUDIT.md). Current score: **69/100**, with a prioritized roadmap
to production grade.

## Status

Phases 1–5A + eight OS engines complete. Next: Phase 6 (Ubuntu systemd
automation), embedding sidecar for semantic retrieval, CI selftest matrix.

Built by [Vishnu Vardhan K S](https://github.com/Vishnu-3727) — embedded
systems, drones, ROS2, edge AI.
