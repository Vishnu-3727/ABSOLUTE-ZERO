#!/usr/bin/env python3
"""ABSOLUTE ZERO knowledge graph. Stdlib only.

Typed graph over everything the vault knows: projects, files, classes,
functions, libraries, skills, experiences, users - connected by imports,
calls, inherits, implements, depends_on, related_to, used_by. Built
deterministically from ast-parsed scripts, INDEX.json notes, command
skills and IDENTITY.md; stored in 90_META/GRAPH.json (generated, never
indexed). Query APIs: node lookup, BFS traversal, shortest path,
semantic search. Contract in GRAPH.md.

  python scripts/graph.py build
  python scripts/graph.py query --type function --name classify
  python scripts/graph.py neighbors function:orchestrator.classify --depth 2
  python scripts/graph.py path file:scripts/planner.py library:json
  python scripts/graph.py search "conflict resolution shared memory"
  python scripts/graph.py stats
  python scripts/graph.py --selftest
"""
import argparse
import ast
import json
import re
import sys
from collections import deque
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchestrator import words_of

VAULT = Path(__file__).resolve().parent.parent
GRAPH = VAULT / "90_META" / "GRAPH.json"

NODE_TYPES = {"project", "file", "class", "function", "library", "skill",
              "experience", "user"}
EDGE_TYPES = {"imports", "calls", "inherits", "implements", "depends_on",
              "related_to", "used_by"}
EXPERIENCE_NOTES = {"lesson", "fault", "session"}
SPEC_RE = re.compile(r"\b([A-Z][A-Z0-9_]+\.md)\b")
LINK_RE = re.compile(r"\[\[([^\]|#]+)")
SCRIPT_RE = re.compile(r"scripts/(\w+)\.py")
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# fallback note typing when a vault has no INDEX.json yet
FOLDER_TYPES = {"30_LESSONS": "lesson", "20_KNOWLEDGE": "knowledge",
                "40_RESEARCH": "research", "00_CORE": "core"}


class Graph:
    """Storage + traversal. Nodes: id -> {type, name, meta}.
    Edges: (src, dst, type) set. Adjacency built on demand."""

    def __init__(self):
        self.nodes, self.edges = {}, set()
        self._out = self._in = None

    def add_node(self, nid, ntype, name, **meta):
        assert ntype in NODE_TYPES, ntype
        cur = self.nodes.setdefault(nid, {"type": ntype, "name": name,
                                          "meta": {}})
        cur["meta"].update({k: v for k, v in meta.items() if v})
        return nid

    def add_edge(self, src, dst, etype):
        assert etype in EDGE_TYPES, etype
        if src in self.nodes and dst in self.nodes and src != dst:
            self.edges.add((src, dst, etype))
            self._out = self._in = None

    def _adj(self):
        if self._out is None:
            self._out, self._in = {}, {}
            for s, d, t in self.edges:
                self._out.setdefault(s, []).append((d, t))
                self._in.setdefault(d, []).append((s, t))
        return self._out, self._in

    # -- traversal ----------------------------------------------------------
    def neighbors(self, nid, edge=None, direction="both", depth=1):
        """BFS out to `depth` hops. Returns [{id, dist, via}] sorted by
        distance then id; `via` = edge type as seen from the start side."""
        if nid not in self.nodes:
            raise SystemExit(f"unknown node: {nid}")
        out, inc = self._adj()
        seen, frontier, result = {nid}, deque([(nid, 0)]), []
        while frontier:
            cur, dist = frontier.popleft()
            if dist == depth:
                continue
            step = []
            if direction in ("out", "both"):
                step += [(d, t) for d, t in out.get(cur, [])]
            if direction in ("in", "both"):
                step += [(s, t + " (in)") for s, t in inc.get(cur, [])]
            for nxt, via in step:
                if edge and not via.startswith(edge):
                    continue
                if nxt not in seen:
                    seen.add(nxt)
                    result.append({"id": nxt, "dist": dist + 1, "via": via})
                    frontier.append((nxt, dist + 1))
        return sorted(result, key=lambda r: (r["dist"], r["id"]))

    def path(self, src, dst):
        """Shortest path, directed first, undirected fallback.
        Returns [(node, edge-to-next), ..., (dst, None)] or None."""
        for undirected in (False, True):
            got = self._bfs_path(src, dst, undirected)
            if got:
                return got
        return None

    def _bfs_path(self, src, dst, undirected):
        if src not in self.nodes or dst not in self.nodes:
            raise SystemExit(f"unknown node: {src if src not in self.nodes else dst}")
        out, inc = self._adj()
        prev, frontier = {src: None}, deque([src])
        while frontier:
            cur = frontier.popleft()
            if cur == dst:
                chain = []
                while cur is not None:
                    chain.append(cur)
                    cur = prev[cur][0] if prev[cur] else None
                chain.reverse()
                return [(n, prev[chain[i + 1]][1] if i + 1 < len(chain)
                         else None) for i, n in enumerate(chain)]
            step = list(out.get(cur, []))
            if undirected:
                step += [(s, t + " (in)") for s, t in inc.get(cur, [])]
            for nxt, t in step:
                if nxt not in prev:
                    prev[nxt] = (cur, t)
                    frontier.append(nxt)
        return None

    # -- semantic search ----------------------------------------------------
    def search(self, text, ntype=None, limit=8):
        """Query-coverage first (how much of the query the node holds),
        jaccard + fuzzy name ratio as tiebreaks. [(score, id)] ranked."""
        qw = set(words_of(text))
        q = text.lower()
        scored = []
        for nid, n in self.nodes.items():
            if ntype and n["type"] != ntype:
                continue
            corpus = " ".join([n["name"], n["type"],
                               *(str(v) for v in n["meta"].values())])
            nw = set(words_of(corpus))
            cover = len(qw & nw) / len(qw) if qw else 0
            jac = len(qw & nw) / len(qw | nw) if qw | nw else 0
            fuzzy = SequenceMatcher(None, q, n["name"].lower()).ratio()
            score = 0.6 * cover + 0.4 * jac + 0.3 * fuzzy
            if score >= 0.3:
                scored.append((round(score, 2), nid))
        return sorted(scored, reverse=True)[:limit]

    # -- storage ------------------------------------------------------------
    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"generated": datetime.now().isoformat(timespec="seconds"),
             "nodes": self.nodes,
             "edges": sorted(list(e) for e in self.edges)},
            indent=1) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path=GRAPH):
        if not path.exists():
            raise SystemExit("no GRAPH.json - run scripts/graph.py build first")
        d = json.loads(path.read_text(encoding="utf-8"))
        g = cls()
        g.nodes = d["nodes"]
        g.edges = {tuple(e) for e in d["edges"]}
        return g


# -- extraction ---------------------------------------------------------
def _first_line(doc):
    return (doc or "").strip().splitlines()[0][:120] if doc else ""


def extract_scripts(g, vault):
    """ast pass over scripts/*.py: files, classes, functions, libraries,
    imports/depends_on/inherits/implements; two-pass call resolution."""
    scripts = sorted((vault / "scripts").glob("*.py")) \
        if (vault / "scripts").exists() else []
    locals_ = {p.stem: p for p in scripts}
    trees, defs, aliases, from_names = {}, {}, {}, {}
    for p in scripts:
        try:
            trees[p.stem] = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
    # pass 1: nodes + static edges + def tables
    for mod, tree in trees.items():
        rel = f"scripts/{mod}.py"
        fid = g.add_node(f"file:{rel}", "file", rel,
                         doc=_first_line(ast.get_docstring(tree)))
        defs[mod], aliases[mod], from_names[mod] = {}, {}, {}
        for spec in SPEC_RE.findall(ast.get_docstring(tree) or ""):
            if (vault / spec).exists():
                g.add_node(f"file:{spec}", "file", spec)
                g.add_edge(fid, f"file:{spec}", "implements")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    _import_edge(g, fid, a.name.split(".")[0], locals_,
                                 aliases[mod], a.asname or a.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                _import_edge(g, fid, top, locals_, aliases[mod], None)
                if top in locals_:  # from mod import name -> bare-name calls
                    for a in node.names:
                        from_names[mod][a.asname or a.name] = (top, a.name)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                cid = g.add_node(f"class:{mod}.{node.name}", "class",
                                 f"{mod}.{node.name}", file=rel,
                                 doc=_first_line(ast.get_docstring(node)))
                g.add_edge(fid, cid, "related_to")
                defs[mod][node.name] = cid
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        mid = g.add_node(
                            f"function:{mod}.{node.name}.{m.name}",
                            "function", f"{mod}.{node.name}.{m.name}",
                            file=rel, doc=_first_line(ast.get_docstring(m)))
                        g.add_edge(cid, mid, "related_to")
                        defs[mod][f"{node.name}.{m.name}"] = mid
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fnid = g.add_node(f"function:{mod}.{node.name}", "function",
                                  f"{mod}.{node.name}", file=rel,
                                  doc=_first_line(ast.get_docstring(node)))
                g.add_edge(fid, fnid, "related_to")
                defs[mod][node.name] = fnid
    # pass 1b: inherits (needs all class tables)
    for mod, tree in trees.items():
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                target = None
                if isinstance(base, ast.Name):
                    target = defs[mod].get(base.id) or _foreign_class(
                        g, base.id, aliases[mod], defs)
                elif isinstance(base, ast.Attribute) \
                        and isinstance(base.value, ast.Name):
                    bmod = aliases[mod].get(base.value.id)
                    if bmod in defs:
                        target = defs[bmod].get(base.attr)
                if target:
                    g.add_edge(defs[mod][node.name], target, "inherits")
    # pass 2: calls
    for mod, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            caller = defs[mod].get(node.name) or next(
                (v for k, v in defs[mod].items()
                 if k.endswith("." + node.name)), None)
            if not caller:
                continue
            for c in ast.walk(node):
                if not isinstance(c, ast.Call):
                    continue
                callee = None
                if isinstance(c.func, ast.Name):
                    callee = defs[mod].get(c.func.id)
                    if not callee and c.func.id in from_names[mod]:
                        fmod, fname = from_names[mod][c.func.id]
                        callee = defs.get(fmod, {}).get(fname)
                elif isinstance(c.func, ast.Attribute) \
                        and isinstance(c.func.value, ast.Name):
                    cmod = aliases[mod].get(c.func.value.id)
                    if cmod in defs:
                        callee = defs[cmod].get(c.func.attr)
                if callee and callee != caller \
                        and callee.startswith("function:"):
                    g.add_edge(caller, callee, "calls")


def _import_edge(g, fid, top, locals_, alias_table, alias):
    if top in locals_:
        tgt = g.add_node(f"file:scripts/{top}.py", "file",
                         f"scripts/{top}.py")
        g.add_edge(fid, tgt, "imports")
        g.add_edge(fid, tgt, "depends_on")
        if alias:
            alias_table[alias] = top
        alias_table[top] = top
    else:
        lid = g.add_node(f"library:{top}", "library", top,
                         stdlib=top in sys.stdlib_module_names)
        g.add_edge(fid, lid, "imports")
        g.add_edge(lid, fid, "used_by")


def _foreign_class(g, name, alias_table, defs):
    mod = alias_table.get(name)
    if mod in defs and name in defs[mod]:
        return defs[mod][name]
    return None


def load_notes(vault):
    """INDEX.json when present; else a minimal frontmatter scan so fresh
    vaults still graph."""
    index = vault / "90_META" / "INDEX.json"
    if index.exists():
        return json.loads(index.read_text(encoding="utf-8"))["notes"]
    notes = []
    for folder, ntype in FOLDER_TYPES.items():
        for p in sorted((vault / folder).glob("**/*.md")) \
                if (vault / folder).exists() else []:
            text = p.read_text(encoding="utf-8")
            m = FM_RE.match(text)
            fm = dict(re.findall(r"^(\w+):\s*(.+)$", m.group(1), re.M)) \
                if m else {}
            notes.append({"path": str(p.relative_to(vault)).replace("\\", "/"),
                          "type": ntype, "title": p.stem,
                          "project": fm.get("project", "-"),
                          "summary": fm.get("summary", ""), "tags": [],
                          "links": LINK_RE.findall(text)})
    return notes


def extract_notes(g, vault):
    notes = load_notes(vault)
    by_stem = {}
    for n in notes:
        stem = Path(n["path"]).stem
        ntype = "experience" if n["type"] in EXPERIENCE_NOTES else "file"
        nid = g.add_node(f"{ntype}:{stem}" if ntype == "experience"
                         else f"file:{n['path']}", ntype,
                         n["title"] or stem, path=n["path"],
                         note_type=n["type"], summary=n.get("summary", ""),
                         tags=" ".join(n.get("tags", [])))
        by_stem[stem.lower()] = nid
        proj = n.get("project", "-")
        if proj and proj not in ("-", ""):
            pid = g.add_node(f"project:{proj}", "project", proj)
            g.add_edge(nid, pid, "related_to")
    if (vault / "10_PROJECTS").exists():
        for d in sorted((vault / "10_PROJECTS").iterdir()):
            if d.is_dir():
                g.add_node(f"project:{d.name}", "project", d.name)
    for n in notes:
        src = by_stem[Path(n["path"]).stem.lower()]
        for link in n.get("links", []):
            dst = by_stem.get(Path(link.strip()).stem.lower())
            if dst:
                g.add_edge(src, dst, "related_to")


def extract_skills(g, vault):
    cmds = vault / ".claude" / "commands"
    if not cmds.exists():
        return
    for p in sorted(cmds.glob("*.md")):
        sid = g.add_node(f"skill:{p.stem}", "skill", p.stem)
        for mod in SCRIPT_RE.findall(p.read_text(encoding="utf-8")):
            tgt = f"file:scripts/{mod}.py"
            if tgt in g.nodes:
                g.add_edge(sid, tgt, "depends_on")
                g.add_edge(tgt, sid, "used_by")


def extract_user(g, vault):
    ident = vault / "00_CORE" / "IDENTITY.md"
    if not ident.exists():
        return
    text = ident.read_text(encoding="utf-8")
    m = re.search(r"^#\s+(.+)$", text, re.M)
    uid = g.add_node("user:owner", "user", m.group(1).strip() if m
                     else "owner", path="00_CORE/IDENTITY.md")
    for nid, n in list(g.nodes.items()):
        if n["type"] == "project":
            g.add_edge(nid, uid, "used_by")


def build(vault=VAULT, out=None):
    g = Graph()
    root = vault.name.replace(" ", "_").upper()
    g.add_node(f"project:{root}", "project", root, path=str(vault))
    extract_scripts(g, vault)
    extract_notes(g, vault)
    extract_skills(g, vault)
    extract_user(g, vault)
    # vault project depends on every imported library
    for nid, n in list(g.nodes.items()):
        if n["type"] == "library":
            g.add_edge(f"project:{root}", nid, "depends_on")
        if n["type"] == "file" and nid.startswith("file:scripts/"):
            g.add_edge(nid, f"project:{root}", "related_to")
    g.save(out if out is not None else GRAPH)
    return g


# -- CLI ------------------------------------------------------------------
def show_stats(g):
    by_type = {}
    for n in g.nodes.values():
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    by_edge = {}
    for _, _, t in g.edges:
        by_edge[t] = by_edge.get(t, 0) + 1
    print(f"nodes       {len(g.nodes)}   edges {len(g.edges)}")
    for t in sorted(NODE_TYPES):
        print(f"  {t:<12} {by_type.get(t, 0)}")
    print("edges")
    for t in sorted(EDGE_TYPES):
        print(f"  {t:<12} {by_edge.get(t, 0)}")


def show_node(g, nid, prefix="  "):
    n = g.nodes[nid]
    extra = n["meta"].get("doc") or n["meta"].get("summary") or ""
    print(f"{prefix}{nid:<44} {extra[:60]}")


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        (v / "scripts").mkdir(parents=True)
        (v / "SPEC.md").write_text("# spec\n", encoding="utf-8")
        (v / "scripts" / "m1.py").write_text(
            '"""Demo one. Contract in SPEC.md."""\n'
            "import json\nimport m2\nfrom m2 import helper\n\n"
            "class Base:\n    pass\n\n"
            "class Child(Base):\n"
            "    def method(self):\n        return m2.helper()\n\n"
            "def top():\n    return util()\n\n"
            "def util():\n    return json.dumps({})\n\n"
            "def wrap():\n    return helper()\n",
            encoding="utf-8")
        (v / "scripts" / "m2.py").write_text(
            '"""Demo two."""\n\ndef helper():\n    return 1\n',
            encoding="utf-8")
        (v / "30_LESSONS").mkdir()
        (v / "30_LESSONS" / "hard-lesson.md").write_text(
            "---\nproject: DEMO\nsummary: fail loud not silent\n---\n"
            "see [[deep-topic]]\n", encoding="utf-8")
        (v / "20_KNOWLEDGE").mkdir()
        (v / "20_KNOWLEDGE" / "deep-topic.md").write_text(
            "---\nsummary: graph theory basics\n---\nbody\n",
            encoding="utf-8")
        (v / ".claude" / "commands").mkdir(parents=True)
        (v / ".claude" / "commands" / "demo.md").write_text(
            "run scripts/m1.py please\n", encoding="utf-8")
        (v / "00_CORE").mkdir()
        (v / "00_CORE" / "IDENTITY.md").write_text(
            "# Vishnu\nbuilder\n", encoding="utf-8")

        g = build(vault=v, out=v / "GRAPH.json")
        types = {n["type"] for n in g.nodes.values()}
        assert types == NODE_TYPES, NODE_TYPES - types
        etypes = {t for _, _, t in g.edges}
        assert etypes == EDGE_TYPES, EDGE_TYPES - etypes

        e = g.edges
        assert ("file:scripts/m1.py", "library:json", "imports") in e
        assert ("file:scripts/m1.py", "file:scripts/m2.py", "depends_on") in e
        assert ("class:m1.Child", "class:m1.Base", "inherits") in e
        assert ("file:scripts/m1.py", "file:SPEC.md", "implements") in e
        assert ("function:m1.top", "function:m1.util", "calls") in e
        assert ("function:m1.Child.method", "function:m2.helper",
                "calls") in e, "cross-module call missed"
        assert ("function:m1.wrap", "function:m2.helper", "calls") in e, \
            "from-import bare call missed"
        assert ("experience:hard-lesson", "file:20_KNOWLEDGE/deep-topic.md",
                "related_to") in e, "wikilink edge missed"
        assert ("skill:demo", "file:scripts/m1.py", "depends_on") in e
        assert ("file:scripts/m1.py", "skill:demo", "used_by") in e
        assert ("experience:hard-lesson", "project:DEMO", "related_to") in e
        assert ("project:DEMO", "user:owner", "used_by") in e
        assert g.nodes["user:owner"]["name"] == "Vishnu"

        # storage roundtrip
        g2 = Graph.load(v / "GRAPH.json")
        assert g2.nodes == g.nodes and g2.edges == g.edges, "roundtrip drift"

        # traversal: depth-limited BFS + shortest path
        n1 = {r["id"] for r in g2.neighbors("file:scripts/m1.py", depth=1,
                                            direction="out")}
        assert "library:json" in n1 and "class:m1.Child" in n1
        assert "function:m2.helper" not in n1
        n2 = {r["id"] for r in g2.neighbors("file:scripts/m1.py", depth=2,
                                            direction="out")}
        assert "function:m1.Child.method" in n2
        p = g2.path("class:m1.Child", "function:m2.helper")
        assert p and p[-1][0] == "function:m2.helper", p
        assert [n for n, _ in p][0] == "class:m1.Child"
        only_calls = g2.neighbors("function:m1.top", edge="calls",
                                  direction="out", depth=1)
        assert [r["id"] for r in only_calls] == ["function:m1.util"]

        # semantic search
        hits = g2.search("graph theory")
        assert hits and hits[0][1] == "file:20_KNOWLEDGE/deep-topic.md", hits
        hits = g2.search("helper", ntype="function")
        assert hits[0][1] == "function:m2.helper"
        assert g2.search("zzqx quantum blockchain") == []
    print("selftest OK")


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Knowledge graph.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("build")
    sub.add_parser("stats")
    q = sub.add_parser("query")
    q.add_argument("--type", dest="ntype", choices=sorted(NODE_TYPES))
    q.add_argument("--name", default="")
    ne = sub.add_parser("neighbors")
    ne.add_argument("node")
    ne.add_argument("--edge", choices=sorted(EDGE_TYPES))
    ne.add_argument("--depth", type=int, default=1)
    ne.add_argument("--direction", choices=["out", "in", "both"],
                    default="both")
    pa = sub.add_parser("path")
    pa.add_argument("src")
    pa.add_argument("dst")
    se = sub.add_parser("search")
    se.add_argument("text")
    se.add_argument("--type", dest="ntype", choices=sorted(NODE_TYPES))
    se.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    if args.cmd == "build":
        g = build()
        show_stats(g)
        print(f"saved       {GRAPH.relative_to(VAULT)}")
        return
    if not args.cmd:
        ap.print_help()
        return
    g = Graph.load()
    if args.cmd == "stats":
        show_stats(g)
    elif args.cmd == "query":
        for nid, n in sorted(g.nodes.items()):
            if args.ntype and n["type"] != args.ntype:
                continue
            if args.name.lower() in n["name"].lower():
                show_node(g, nid, "")
    elif args.cmd == "neighbors":
        for r in g.neighbors(args.node, edge=args.edge, depth=args.depth,
                             direction=args.direction):
            print(f"  {r['dist']}  {r['via']:<18} {r['id']}")
    elif args.cmd == "path":
        p = g.path(args.src, args.dst)
        if not p:
            print("no path")
            return
        for node, via in p:
            print(f"  {node}" + (f"  --{via}-->" if via else ""))
    elif args.cmd == "search":
        hits = g.search(args.text, ntype=args.ntype, limit=args.limit)
        if not hits:
            print("not in graph")
            return
        for score, nid in hits:
            print(f"{score:.2f}  ", end="")
            show_node(g, nid, "")


if __name__ == "__main__":
    main()
