---
tags: [core, token, budget, runtime, v3]
project: ABSOLUTE_ZERO
status: active
confidence: high
date: 2026-07-12
summary: V3 Token Intelligence — budgets, no-LLM gate, adaptive pipeline, one retrieval layer, profiler.
---

# ABSOLUTE ZERO V3 — Token Intelligence

Every token sent to an LLM must be justified. V3 is not new engines — it is
the existing engines cooperating token-first. The cheapest request is the one
that never reaches the model.

## Architecture (token flow)

```
request
   |
   v
CLASSIFY (orchestrator.classify)          0 LLM tokens
   |
   v
BUDGET (orchestrator.budget_for)          0
   trivial 600 | standard 3000 | complex 12000 | research 20000
   (context/promptc clamp to their own 8k hard cap)
   |
   v
GATE (orchestrator.gate) - cheapest answer first:
   1. vault cache hit  (core.retrieve >= 0.6)  -> llm: cache-first
   2. deterministic plugin chain, trivial only -> llm: none
   3. otherwise                                -> llm: required
   |
   +--- llm none -------> ROUTE -> EXECUTE(plugins) -> VERIFY -> SUMMARIZE
   |                      (tool-direct pipeline, 0 LLM tokens)
   |
   +--- cache-first ----> read the hit note before any engine spends tokens
   |
   v
RECALL  context.pack --budget N     one retrieval layer (core.retrieve)
PLAN    planner (standard/complex)
EXECUTE plugins.route first - deterministic local tools before model calls
VERIFY  verifier (deterministic, 0 LLM tokens)
SUMMARIZE + profiler.report         where did the tokens go
```

## The six V3 mechanisms

1. **Token Budget Manager** — `orchestrator.budget_for(intent, complexity)`.
   Budget lands in the trace and every printed downstream command
   (`context.pack --budget N`). Ceiling, not quota.
2. **Capability gate** — `orchestrator.gate`. No-LLM check before any engine
   runs: cached knowledge (vault similarity ≥ 0.6), then a fully
   script-covered plugin chain (trivial requests only — a wrong "none" on a
   complex task costs more than it saves).
3. **Adaptive pipeline** — gate result selects the pipeline. `tool-direct`
   = ROUTE→EXECUTE→VERIFY→SUMMARIZE with zero model calls; state machine
   legality (orchestrator.log) unchanged.
4. **One retrieval layer** — `core.retrieve(query, items, key)` is the only
   scorer. orchestrator.vault_hits, similarity, and the gate all call it;
   engines never re-implement ranking (audit H2 rule extended to retrieval).
5. **Cache freshness** — `core.stale(artifact, sources)`. The expensive
   artifacts are already cached on disk (PLUGINS.json, GRAPH.json, INDEX.json,
   bootstrap.json, experience/*.json); `orchestrator.freshness()` prints a
   STALE line with the exact rebuild command instead of silently serving rot.
6. **Token profiler** — `scripts/profiler.py report`. Per-section prompt
   tokens (parsed from the compiled prompt), completion tokens, plugin tokens
   saved (ESTIMATE, 400/successful script run), USD estimate
   (--price-in/--price-out per 1M), top consumers, suggestions. Reports in
   `90_META/profile/` (artifact dir — committed, never indexed).

## Already-built V3 requirements (no new code)

- Plugin Intelligence + preference learning: plugins.py scan/route/report,
  plugin_stats.json reliability EMA-by-ratio. (PLUGINS.md)
- Tool-first: route scoring weights deterministic/local above token cost.
- Context Intelligence: context.py ranking, fidelity tiers, jaccard dedup,
  extractive history compression, OMITTED tail. (CONTEXT.md)
- Prompt Compiler: promptc.py section fragments, stemmed-jaccard instruction
  dedup, drop-order under budget. (PROMPTC.md)
- Repository compression: bootstrap.py summaries/API/deps/risk instead of
  raw files. (BOOTSTRAP.md)

## Folder structure (V3 additions only)

```
scripts/profiler.py      token profiler (17th script, selftested)
90_META/profile/         per-request token reports (artifact dir)
TOKEN.md                 this spec (indexer ROOT_DOCS)
```

## Migration

Done in one commit: core.retrieve/stale added; orchestrator gained
BUDGETS/gate/freshness/tool-direct and lost its private similarity scorer;
profiler.py new; FLOW step 6 profiles on close. No trace-format break —
old traces lack budget/llm keys and are already closed.

## Benchmark methodology

Baseline = est_tokens of the compiled prompt (promptc stats) per intent
class, before vs after:

1. Same 9 selftest requests through `orchestrator plan` — count requests
   that gate out (llm none / cache-first). Target: every trivial with full
   script coverage.
2. `promptc compile` at V3 budgets vs old flat 5000 default — prompt tokens
   by section (profiler). Target: 50–80% smaller for trivial/standard.
3. plugin_tokens_saved trend in profiler reports across a week of real use.
4. Cache hit = STALE lines per session trending to zero mid-session.

## Performance comparison (measured at ship)

- trivial "fix typo in readme": V2 = RECALL+PLAN+prompt ≈ 5000-budget
  compile; V3 = tool-direct, **0 LLM tokens**.
- standard bug fix: budget 5000→3000 (−40% ceiling) with unchanged VERIFY.
- research: unchanged 20000 — wide reads are the point there.
