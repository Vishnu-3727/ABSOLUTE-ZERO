#!/usr/bin/env python3
"""ABSOLUTE ZERO plugin intelligence engine. Stdlib only.

Discovers every installed tool, builds a capability database, and routes
requests to the optimal plugin chain. Three discovery sources:
  scripts/*.py            deterministic, local, zero-token (subcommands,
                          imports, permissions parsed from source; latency
                          probed by timing --help)
  .claude/commands/*.md   LLM-executed skills (token cost > 0)
  ~/.claude/plugins/...   external Claude Code plugins / MCP servers
                          (static manifest scan; python cannot invoke MCP,
                          so Claude executes those and reports stats back)

Registry -> 90_META/PLUGINS.json.  Rolling reliability/latency stats from
real executions -> 90_META/plugin_stats.json.  Contract in PLUGINS.md.

  python scripts/plugins.py scan [--probe]
  python scripts/plugins.py list
  python scripts/plugins.py route "convert this pdf and index the summary"
  python scripts/plugins.py exec query -- --tags navigation
  python scripts/plugins.py exec indexer --fallbacks review -- --selftest
  python scripts/plugins.py report --plugin firecrawl --ok --ms 2100
  python scripts/plugins.py --selftest
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchestrator import classify, words_of

VAULT = Path(__file__).resolve().parent.parent
REGISTRY = VAULT / "90_META" / "PLUGINS.json"
STATS = VAULT / "90_META" / "plugin_stats.json"
DEFAULT_RELIABILITY = 0.8  # unknown plugins start slightly distrusted

# Capability vocabulary: normalize free text -> capability tags.
CAP_KEYWORDS = {
    "query": "retrieval", "recall": "retrieval", "search": "retrieval",
    "filter": "retrieval", "find": "retrieval",
    "index": "indexing", "frontmatter": "indexing", "parse": "parsing",
    "similarity": "similarity", "fuzzy": "similarity", "match": "similarity",
    "orphan": "audit", "stale": "audit", "review": "audit", "audit": "audit",
    "orchestrat": "orchestration", "pipeline": "orchestration",
    "state": "orchestration", "trace": "orchestration",
    "context": "context", "budget": "context", "pack": "context",
    "token": "context", "compress": "context",
    "web": "web", "scrape": "web", "crawl": "web", "url": "web",
    "http": "web", "browser": "web", "firecrawl": "web",
    "research": "research", "summarize": "summarization",
    "sleep": "persistence", "session": "persistence", "commit": "persistence",
    "git": "persistence", "log": "persistence",
    "predict": "prediction", "estimate": "prediction",
    "code": "codegen", "codex": "codegen", "implement": "codegen",
    "plugin": "tooling", "discover": "tooling", "route": "tooling",
}
# Intent -> capabilities the runtime will need (beyond request keywords).
INTENT_CAPS = {
    "research": ["research", "web", "retrieval"],
    "bug_fix": ["retrieval", "audit"], "quick_fix": ["retrieval"],
    "feature": ["retrieval", "codegen"], "architecture": ["retrieval",
                                                          "orchestration"],
    "documentation": ["retrieval", "indexing"],
    "performance": ["retrieval", "prediction"],
    "security": ["audit", "retrieval"], "deployment": ["audit",
                                                       "persistence"],
}
PERM_PATTERNS = {
    "fs-write": r"write_text|mkdir|unlink|open\([^)]*['\"]w",
    "network": r"urllib|socket|http\.client|requests",
    "exec": r"subprocess|os\.system",
}


def caps_from_text(text):
    t = text.lower()
    return sorted({cap for kw, cap in CAP_KEYWORDS.items() if kw in t})


def scan_scripts(vault):
    out = []
    for p in sorted((vault / "scripts").glob("*.py")):
        src = p.read_text(encoding="utf-8")
        m = re.search(r'"""(.*?)"""', src, re.DOTALL)
        # first paragraph only: full docstrings leak example keywords
        doc = m.group(1).split("\n\n")[0] if m else ""
        actions = sorted(set(re.findall(r'add_parser\("(\w+)"\)', src)))
        doc += " " + " ".join(actions)
        mods = {m.split(".")[0] for m in
                re.findall(r"^(?:import|from)\s+([\w\.]+)", src, re.MULTILINE)}
        local_mods = {q.stem for q in (vault / "scripts").glob("*.py")}
        deps = sorted(mods - set(sys.stdlib_module_names) - local_mods)
        perms = sorted(k for k, pat in PERM_PATTERNS.items()
                       if re.search(pat, src)) or ["fs-read"]
        out.append({
            "name": p.stem, "kind": "script", "path": f"scripts/{p.name}",
            "capabilities": caps_from_text(doc), "actions": actions,
            "deterministic": True, "local": True, "token_cost": 0,
            "latency_ms": None, "dependencies": deps, "permissions": perms,
            "invoke": f"python scripts/{p.name}",
        })
    return out


def scan_commands(vault):
    out = []
    for p in sorted((vault / ".claude" / "commands").glob("*.md")):
        text = p.read_text(encoding="utf-8")
        m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        desc = m.group(1) if m else p.stem
        out.append({
            "name": f"/{p.stem}", "kind": "skill",
            "path": f".claude/commands/{p.name}",
            "capabilities": caps_from_text(desc + " " + text),
            "actions": [p.stem], "deterministic": False, "local": True,
            "token_cost": 1, "latency_ms": None, "dependencies": ["claude"],
            "permissions": ["llm"], "invoke": f"/{p.stem}",
        })
    return out


def scan_external(home=None):
    """~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/.
    Static only: python cannot invoke MCP, so no probing here."""
    cache = Path(home or Path.home()) / ".claude" / "plugins" / "cache"
    out = []
    if not cache.is_dir():
        return out
    for plug in sorted(q for mkt in cache.iterdir() if mkt.is_dir()
                       for q in mkt.iterdir() if q.is_dir()):
        versions = [v for v in plug.iterdir() if v.is_dir()]
        if not versions:
            continue
        root = versions[0]
        skills = [s.parent.name for s in root.rglob("SKILL.md")]
        blob = plug.name + " " + " ".join(skills)
        for s in list(root.rglob("SKILL.md"))[:20]:
            head = s.read_text(encoding="utf-8", errors="ignore")[:400]
            blob += " " + head
        caps = caps_from_text(blob)
        network = "web" in caps
        out.append({
            "name": plug.name, "kind": "external", "path": str(plug),
            "capabilities": caps, "actions": sorted(set(skills)),
            "deterministic": False, "local": not network,
            "token_cost": 2 if network else 1, "latency_ms": None,
            "dependencies": ["claude-code"], "permissions":
                ["llm"] + (["network"] if network else []),
            "invoke": f"plugin:{plug.name}",
        })
    return out


def probe(plugins, vault):
    """Measure real latency of deterministic scripts (timed --help)."""
    for p in plugins:
        if p["kind"] != "script":
            continue
        t0 = time.perf_counter()
        r = subprocess.run([sys.executable, str(vault / p["path"]), "--help"],
                           capture_output=True, cwd=vault, timeout=60)
        p["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        if r.returncode != 0:
            p["latency_ms"] = None  # broken plugin, fail loud in list


def scan(vault=VAULT, home=None, do_probe=False, registry=None):
    plugins = scan_scripts(vault) + scan_commands(vault) + scan_external(home)
    # same plugin can sit in two marketplaces - first occurrence wins
    seen = set()
    plugins = [p for p in plugins
               if p["name"] not in seen and not seen.add(p["name"])]
    if do_probe:
        probe(plugins, vault)
    reg = registry if registry is not None else REGISTRY
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps({"plugins": plugins}, indent=1) + "\n",
                   encoding="utf-8")
    print(f"registered {len(plugins)} plugins -> {reg.name}")
    return plugins


def load_registry(registry=None):
    reg = registry if registry is not None else REGISTRY
    if not reg.exists():
        raise SystemExit("no PLUGINS.json - run scripts/plugins.py scan first")
    return json.loads(reg.read_text(encoding="utf-8"))["plugins"]


def load_stats(stats_path=None):
    p = stats_path if stats_path is not None else STATS
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def record(name, ok, ms, stats_path=None):
    p = stats_path if stats_path is not None else STATS
    st = load_stats(p)
    e = st.setdefault(name, {"runs": 0, "ok": 0, "ms_avg": 0})
    e["ms_avg"] = int((e["ms_avg"] * e["runs"] + ms) / (e["runs"] + 1))
    e["runs"] += 1
    e["ok"] += 1 if ok else 0
    p.write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8")


def reliability(name, stats):
    e = stats.get(name)
    return e["ok"] / e["runs"] if e and e["runs"] else DEFAULT_RELIABILITY


def latency_class(p, stats):
    ms = (stats.get(p["name"], {}).get("ms_avg") or p["latency_ms"])
    if ms is None:
        return 0.6 if p["kind"] == "external" else 0.3  # unknown heuristic
    return 0.0 if ms < 500 else 0.3 if ms < 3000 else 1.0


def score(p, needed, stats):
    """Optimization goals as weights: coverage first, then deterministic >
    LLM, local > network, reliable > flaky, fast > slow, cheap > tokens."""
    cover = len(set(p["capabilities"]) & needed) / len(needed) if needed else 0
    return round(3.0 * cover
                 + 1.0 * p["deterministic"]
                 + 1.0 * p["local"]
                 + 3.0 * reliability(p["name"], stats)
                 - 1.0 * latency_class(p, stats)
                 - 0.5 * p["token_cost"], 2)


def route(request, vault=VAULT, registry=None, stats_path=None, quiet=False):
    # the router never routes to itself
    plugins = [p for p in load_registry(registry) if p["name"] != "plugins"]
    stats = load_stats(stats_path)
    intent = classify(request)["intent"]
    needed = set(INTENT_CAPS.get(intent, ["retrieval"]))
    needed |= set(caps_from_text(request))
    ranked = sorted(plugins, key=lambda p: score(p, needed, stats),
                    reverse=True)
    # Greedy set cover: chain plugins until every needed capability is held.
    chain, covered = [], set()
    for p in ranked:
        gain = set(p["capabilities"]) & needed - covered
        if gain:
            chain.append(p)
            covered |= gain
        if covered >= needed:
            break
    plan = {"request": request, "intent": intent, "needed": sorted(needed),
            "uncovered": sorted(needed - covered),
            "chain": [{"name": p["name"], "kind": p["kind"],
                       "score": score(p, needed, stats),
                       "covers": sorted(set(p["capabilities"]) & needed),
                       "invoke": p["invoke"]} for p in chain],
            "fallbacks": {}}
    for link in chain:
        alts = [p["name"] for p in ranked
                if p["name"] != link["name"]
                and set(p["capabilities"]) & set(link["capabilities"]) & needed]
        plan["fallbacks"][link["name"]] = alts[:2]
    if not quiet:
        print(f"intent      {intent}")
        print(f"needs       {', '.join(plan['needed'])}")
        for c in plan["chain"]:
            fb = plan["fallbacks"][c["name"]]
            print(f"  {c['score']:>5}  {c['kind']:<8} {c['name']:<22} "
                  f"covers {', '.join(c['covers'])}"
                  + (f"  fallback: {', '.join(fb)}" if fb else ""))
        if plan["uncovered"]:
            print(f"UNCOVERED   {', '.join(plan['uncovered'])} "
                  f"- no plugin has this; model does it directly")
    return plan


def execute(name, args, fallbacks=(), vault=VAULT, registry=None,
            stats_path=None):
    """Run a script plugin, time it, record stats; walk fallbacks on
    failure. Non-script plugins are Claude's to run - use report."""
    plugins = {p["name"]: p for p in load_registry(registry)}
    for pname in [name] + list(fallbacks):
        p = plugins.get(pname)
        if not p or p["kind"] != "script":
            print(f"{pname}: not an executable script plugin, skipping")
            continue
        t0 = time.perf_counter()
        r = subprocess.run([sys.executable, str(vault / p["path"])] + args,
                           cwd=vault, timeout=300)
        ms = int((time.perf_counter() - t0) * 1000)
        record(pname, r.returncode == 0, ms, stats_path)
        if r.returncode == 0:
            print(f"{pname}: OK in {ms}ms")
            return 0
        print(f"{pname}: FAILED (exit {r.returncode}, {ms}ms)"
              + (" - trying fallback" if pname != ([name] + list(fallbacks))[-1]
                 else ""))
    return 1


def show_list(registry=None, stats_path=None):
    stats = load_stats(stats_path)
    for p in load_registry(registry):
        st = stats.get(p["name"], {})
        rel = f"{reliability(p['name'], stats):.2f}"
        ms = st.get("ms_avg") or p["latency_ms"] or "?"
        print(f"{p['name']:<24} {p['kind']:<8} det={int(p['deterministic'])} "
              f"local={int(p['local'])} tok={p['token_cost']} rel={rel} "
              f"ms={ms}")
        print(f"    caps: {', '.join(p['capabilities']) or '-'}")
        print(f"    deps: {', '.join(p['dependencies']) or '-'}   "
              f"perms: {', '.join(p['permissions'])}")


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        (v / "scripts").mkdir()
        (v / "scripts" / "fetcher.py").write_text(
            '"""Scrape a url over http and search the web."""\n'
            "import urllib.request\nimport subprocess\n"
            'def main():\n    open("x", "w").write_text\n', encoding="utf-8")
        (v / ".claude" / "commands").mkdir(parents=True)
        (v / ".claude" / "commands" / "research.md").write_text(
            "---\ndescription: web research and summarize into notes\n---\n",
            encoding="utf-8")
        reg, st = v / "PLUGINS.json", v / "stats.json"
        plugs = scan(v, home=v / "nohome", registry=reg)
        byname = {p["name"]: p for p in plugs}
        f = byname["fetcher"]
        assert f["capabilities"] == ["retrieval", "web"], f["capabilities"]
        assert f["permissions"] == ["exec", "fs-write", "network"]
        assert f["dependencies"] == [], "stdlib flagged as dependency"
        assert byname["/research"]["kind"] == "skill"
        # determinism preference: script beats skill on identical coverage
        plan = route("scrape the url and search the web", vault=v,
                     registry=reg, stats_path=st, quiet=True)
        assert plan["chain"][0]["name"] == "fetcher", plan["chain"]
        assert "/research" in plan["fallbacks"]["fetcher"]
        # reliability learning: repeated failures demote below the skill
        for _ in range(5):
            record("fetcher", False, 100, st)
        stats = load_stats(st)
        assert reliability("fetcher", stats) == 0.0
        assert score(byname["/research"], {"web"}, stats) > \
            score(f, {"web"}, stats), "flaky plugin not demoted"
        # set cover chains a second plugin for uncovered capability
        (v / "scripts" / "indexerx.py").write_text(
            '"""Index frontmatter notes."""\n', encoding="utf-8")
        scan(v, home=v / "nohome", registry=reg)
        plan = route("scrape the web and index the notes", vault=v,
                     registry=reg, stats_path=st, quiet=True)
        names = [c["name"] for c in plan["chain"]]
        assert "indexerx" in names and len(names) >= 2, names
        # execute walks fallbacks and records stats
        (v / "scripts" / "bad.py").write_text("raise SystemExit(1)\n",
                                              encoding="utf-8")
        (v / "scripts" / "good.py").write_text("print('ok')\n",
                                               encoding="utf-8")
        scan(v, home=v / "nohome", registry=reg)
        rc = execute("bad", [], fallbacks=["good"], vault=v, registry=reg,
                     stats_path=st)
        assert rc == 0
        stats = load_stats(st)
        assert stats["bad"]["ok"] == 0 and stats["good"]["ok"] == 1
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Plugin intelligence engine.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    sc = sub.add_parser("scan")
    sc.add_argument("--probe", action="store_true")
    sub.add_parser("list")
    rt = sub.add_parser("route")
    rt.add_argument("request")
    ex = sub.add_parser("exec")
    ex.add_argument("plugin")
    ex.add_argument("--fallbacks", default="")
    rp = sub.add_parser("report")
    rp.add_argument("--plugin", required=True)
    g = rp.add_mutually_exclusive_group(required=True)
    g.add_argument("--ok", action="store_true")
    g.add_argument("--fail", action="store_true")
    rp.add_argument("--ms", type=int, required=True)
    argv, tail = sys.argv[1:], []
    if "--" in argv:  # everything after -- goes verbatim to the plugin
        i = argv.index("--")
        argv, tail = argv[:i], argv[i + 1:]
    args = ap.parse_args(argv)

    if args.selftest:
        selftest()
    elif args.cmd == "scan":
        scan(do_probe=args.probe)
    elif args.cmd == "list":
        show_list()
    elif args.cmd == "route":
        route(args.request)
    elif args.cmd == "exec":
        fbs = [f for f in args.fallbacks.split(",") if f]
        raise SystemExit(execute(args.plugin, tail, fbs))
    elif args.cmd == "report":
        record(args.plugin, args.ok, args.ms)
        print(f"recorded {args.plugin}: {'ok' if args.ok else 'fail'} "
              f"{args.ms}ms")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
