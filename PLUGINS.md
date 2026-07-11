---
tags: [core, plugins, tooling, runtime]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-11
summary: Plugin Intelligence Engine spec — discovers tools, builds a capability database, routes requests to optimal plugin chains.
---

# ABSOLUTE ZERO — Plugin Intelligence Engine

Discovers every installed tool, scores them on a capability database, and
routes work to the cheapest thing that can do it. Core rule: **a python
script that does the job beats a model call that does the job.**
Implementation: `scripts/plugins.py` (stdlib; reuses `orchestrator.classify`).

## 1. Architecture

```
discovery                        registry              routing
  scripts/*.py  ── parse ──┐                      request
  (docstring, subcommands,  ├─► 90_META/          ──► classify intent
   imports, perms; latency  │   PLUGINS.json      ──► needed capabilities
   probed for real)         │                     ──► score every plugin
  .claude/commands/*.md ────┤   90_META/          ──► greedy set-cover chain
  (skills; LLM-executed)    │   plugin_stats.json     + fallbacks per link
  ~/.claude/plugins/cache ──┘        ▲
  (external/MCP; static)             │ feedback: exec (scripts, timed,
                                     │ auto-fallback) and report (Claude
                                     └ logs MCP/skill outcomes)
```

Execution split, same as the rest of the OS: python runs what python can
(script plugins, timed and retried), Claude runs skills/MCP and feeds
results back via `report` so reliability learning covers everything.

## 2. API

```
python scripts/plugins.py scan [--probe]          rebuild registry (probe = time each script)
python scripts/plugins.py list                    capability database, human view
python scripts/plugins.py route "<request>"       optimal chain + fallbacks
python scripts/plugins.py exec <name> [--fallbacks a,b] -- <args...>
python scripts/plugins.py report --plugin X --ok|--fail --ms N
python scripts/plugins.py --selftest
```

Registry entry (the capability database record):

```json
{"name": "query", "kind": "script|skill|external",
 "path": "scripts/query.py", "capabilities": ["retrieval"],
 "actions": ["..."], "deterministic": true, "local": true,
 "token_cost": 0, "latency_ms": 113,
 "dependencies": [], "permissions": ["fs-read"],
 "invoke": "python scripts/query.py"}
```

How each attribute is obtained — measured where possible, honest heuristic
where not:

| attribute | scripts | skills / external |
|---|---|---|
| capabilities | docstring 1st para + subcommand names → keyword map | description / SKILL.md heads → keyword map |
| actions | argparse `add_parser` names | command/skill names |
| latency | **measured** (timed run; stats improve it) | unknown → class heuristic, learned via `report` |
| token savings | `token_cost 0` | 1 (LLM) / 2 (LLM+network) |
| cost | local+deterministic = free | token_cost + latency class |
| reliability | **learned**: ok/runs from every exec/report (default 0.8 unknown) | same, via `report` |
| dependencies | non-stdlib imports (`sys.stdlib_module_names`) | claude / claude-code |
| permissions | source regex: fs-write, network, exec | llm (+network if web-capable) |

## 3. Scheduler (scoring + set cover)

```
score = 3.0 * capability_coverage        the job must get done
      + 3.0 * reliability                a flaky tool loses to a working LLM
      + 1.0 * deterministic              prefer no model call
      + 1.0 * local                      prefer no network
      - 1.0 * latency_class              <500ms 0 · <3s 0.3 · slower 1.0
      - 0.5 * token_cost                 minimize tokens
```

Chain building: rank all plugins, then greedy set-cover — take the best
plugin, add the next-ranked plugin that covers a still-missing capability,
until covered or exhausted. Capabilities nobody has are reported as
UNCOVERED: the model does those directly (never pretend a tool exists).
Fallbacks: per chain link, the next 2 ranked plugins sharing a needed
capability. The router never routes to itself.

## 4. Execution runtime + fallback logic

- `exec` runs script plugins: timed, exit-code checked, stats recorded,
  and on failure walks `--fallbacks` in order until one succeeds.
- Skills and external/MCP plugins are executed by Claude (python cannot
  invoke MCP); Claude then calls `report --plugin X --ok/--fail --ms N`.
  Reliability is `ok/runs` — a plugin that keeps failing sinks below the
  LLM alternatives and stops being selected. Stats persist in
  `90_META/plugin_stats.json` (committed: it is OS execution history).

## 5. Integration

- `/task` EXECUTE stage: run `plugins.py route "<request>"` first; follow
  the chain; report outcomes for non-script links.
- Optimization goals are the score weights (§3) — tune there, nowhere else.
- Rescan after adding scripts/skills/plugins: `plugins.py scan --probe`.
