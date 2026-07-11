# BOOTSTRAP — Autonomous Project Bootstrapping

Contract for `scripts/bootstrap.py`. Stdlib only. One command onboards
any repository into the vault — nothing is ever written into the target
repo.

## Command

```
python scripts/bootstrap.py open <repo-path> [--name X --budget N --json]
python scripts/bootstrap.py --selftest
```

Auto-trigger (FLOW /wake step 1b): session starts inside a git repo that
is not the vault and has no `10_PROJECTS/<NAME>/` entry — run `open` on
it before any work.

## The ten automatic steps

1. **Language** — extension counts + manifest markers (pyproject,
   package.json, Cargo.toml, go.mod, …); markers outweigh stray files.
2. **Framework** — declared deps ∪ ast imports mapped through the
   FRAMEWORKS table (Django…ROS2…MAVSDK…React…Tokio).
3. **Architecture** — top-dir layout with roles, entrypoints
   (main/app/index, `__main__` blocks, npm start), largest modules.
4. **Dependency graph** — internal module edges (python ast +
   js relative-import regex), external deps (manifests ∪ imports).
5. **Risk analysis** — static checks (no tests / README / LICENSE / CI,
   secrets regex, unpinned deps, >800-line files, TODO debt) **plus**
   FAULT_LEDGER mining: past faults sharing words with the repo's
   language/framework/deps surface as `ledger`-level risks.
6. **Conventions** — measured from the code, not assumed: indent, quote
   style, p95 line length, naming, docstring coverage, type-hint ratio.
7. **Documentation** — `10_PROJECTS/<NAME>/BOOTSTRAP.md` (full
   frontmatter, indexed like any note) + machine-readable
   `bootstrap.json`.
8. **Summary** — 6-line digest, printed and stored.
9. **Skills** — skills.discover on "<language> <framework> <name>",
   names + confidence.
10. **Context package** — priority-ordered sections
    (identity > risks > architecture > conventions > deps > skills),
    ~4 chars/token, budget-capped (default 2500), lowest priority
    dropped first, omissions listed.

After writing, the engine reruns `indexer.py` and `graph.py build`
automatically, so the new project is immediately queryable via /recall
and the knowledge graph.

## Laws

- Read-only toward the target repo. All output lives in the vault.
- Scan caps: 400 files walked, 200 parsed, 40 sampled for conventions —
  bootstrap is a briefing, not an audit.
- Detection is heuristic; the doc's frontmatter says
  `confidence: estimate`. Wrong guesses get corrected by editing
  BOOTSTRAP.md, not by trusting it blindly.
