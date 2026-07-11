# GRAPH — Knowledge Graph

Contract for `scripts/graph.py`. Stdlib only. Typed graph over everything
the vault knows, built deterministically — no hand-curated triples.

## Commands

```
python scripts/graph.py build                 # extract + save 90_META/GRAPH.json
python scripts/graph.py stats                 # node/edge counts by type
python scripts/graph.py query --type function --name classify
python scripts/graph.py neighbors <id> [--edge E --depth N --direction out|in|both]
python scripts/graph.py path <src> <dst>      # BFS shortest path (undirected fallback)
python scripts/graph.py search "<text>" [--type T]
python scripts/graph.py --selftest
```

## Node types (id = `type:name`)

| Type | Source |
|---|---|
| project | 10_PROJECTS dirs + note frontmatter `project:` + the vault itself |
| file | scripts/*.py + root docs + non-experience notes |
| class | ast ClassDef (`class:module.Name`) |
| function | ast FunctionDef incl. methods (`function:module[.Class].name`) |
| library | imported non-local modules (meta.stdlib flag) |
| skill | .claude/commands/*.md |
| experience | lesson / fault / session notes |
| user | 00_CORE/IDENTITY.md (`user:owner`, name from its H1) |

## Edge types

| Edge | Meaning here |
|---|---|
| imports | file imports library or local script |
| calls | function calls function (two-pass ast: bare names, `mod.attr`, from-import bare names) |
| inherits | class extends class (local + cross-module bases) |
| implements | script implements the spec doc its docstring names (X.md at root) |
| depends_on | file on local script; skill on script; vault project on libraries |
| related_to | containment (file–class–function), wikilinks, note–project |
| used_by | reverse usage: library by file, script by skill, project by user |

## Query APIs (importable: `from graph import Graph`)

- `Graph.load()` / `g.save(path)` — JSON storage, exact roundtrip.
- `g.neighbors(id, edge=, direction=, depth=)` — depth-limited BFS;
  `via` suffixed ` (in)` for reverse edges.
- `g.path(src, dst)` — shortest path, directed first, undirected fallback.
- `g.search(text, ntype=)` — semantic search: 0.6·query-coverage +
  0.4·jaccard + 0.3·fuzzy name ratio over name+type+meta, threshold 0.3.
  No hits prints "not in graph".

## Laws

- GRAPH.json is a generated artifact (indexer SKIP_NAMES, verifier
  ARTIFACT_FILES) — never authored, never indexed.
- Rebuild after structural change: /sleep step 6 runs indexer then
  `graph.py build` (graph feeds on INDEX.json).
- Extraction is best-effort static analysis: dynamic dispatch and
  `getattr` calls are invisible — absence of an edge is not proof of
  absence.
