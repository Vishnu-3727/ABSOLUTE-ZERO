#!/usr/bin/env python3
"""ABSOLUTE ZERO project bootstrap engine. Stdlib only.

Autonomous onboarding for any repository: one command detects language
and framework, maps architecture and the dependency graph, runs risk
analysis (static checks + past faults from the ledger), measures the
codebase's own coding conventions, generates documentation and a project
summary, recommends skills, and assembles a budget-capped context
package. Output lands in the vault (10_PROJECTS/<NAME>/BOOTSTRAP.md +
bootstrap.json) - the target repo is never written to. Contract in
BOOTSTRAP.md.

  python scripts/bootstrap.py open <repo-path> [--name X --budget N --json]
  python scripts/bootstrap.py --selftest
"""
import argparse
import ast
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchestrator import words_of
from planner import mine_risks

VAULT = Path(__file__).resolve().parent.parent
MAX_FILES, MAX_PARSE, MAX_SAMPLE = 400, 200, 40
SKIP = {".git", "node_modules", "venv", ".venv", "env", "__pycache__",
        "dist", "build", "target", ".idea", ".vscode", ".obsidian",
        "site-packages", ".tox", "coverage"}
LANG_EXT = {".py": "python", ".js": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "typescript", ".rs": "rust",
            ".go": "go", ".java": "java", ".c": "c", ".h": "c",
            ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp", ".cs": "csharp",
            ".rb": "ruby", ".php": "php", ".swift": "swift",
            ".kt": "kotlin", ".sh": "shell", ".ino": "arduino"}
MARKERS = {"pyproject.toml": "python", "setup.py": "python",
           "requirements.txt": "python", "package.json": "javascript",
           "tsconfig.json": "typescript", "Cargo.toml": "rust",
           "go.mod": "go", "pom.xml": "java", "build.gradle": "java",
           "CMakeLists.txt": "cpp", "Gemfile": "ruby",
           "platformio.ini": "embedded"}
FRAMEWORKS = {  # dep/import name -> human label
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
    "rclpy": "ROS2", "rospy": "ROS1", "torch": "PyTorch",
    "tensorflow": "TensorFlow", "numpy": "NumPy stack",
    "pandas": "Pandas", "cv2": "OpenCV", "opencv-python": "OpenCV",
    "pymavlink": "MAVLink", "mavsdk": "MAVSDK", "dronekit": "DroneKit",
    "pygame": "Pygame", "kivy": "Kivy", "streamlit": "Streamlit",
    "sqlalchemy": "SQLAlchemy", "celery": "Celery", "pytest": "pytest",
    "react": "React", "next": "Next.js", "vue": "Vue", "svelte": "Svelte",
    "express": "Express", "electron": "Electron", "@nestjs/core": "NestJS",
    "tokio": "Tokio", "actix-web": "Actix", "bevy": "Bevy",
    "gin-gonic/gin": "Gin",
}
DIR_ROLES = {"src": "source", "lib": "source", "app": "source",
             "tests": "tests", "test": "tests", "docs": "docs",
             "doc": "docs", "scripts": "tooling", "tools": "tooling",
             "examples": "examples", "config": "config", "conf": "config",
             ".github": "ci", "launch": "ros-launch", "msg": "ros-msgs",
             "urdf": "robot-model", "worlds": "sim-worlds"}
SECRET_RE = re.compile(  # verifier:ignore
    r"(?i)(password|passwd|secret|token|api_key)\s*=\s*[\"'][^\"']{4,}")


def scan_files(repo):
    files, stack = [], [repo]
    while stack and len(files) < MAX_FILES:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for p in entries:
            if p.is_dir():
                if p.name not in SKIP and not p.name.startswith("."):
                    stack.append(p)
                elif p.name == ".github":
                    stack.append(p)
            elif p.is_file() and len(files) < MAX_FILES:
                files.append(p)
    return files


# -- detection ------------------------------------------------------------
def detect_language(repo, files):
    counts = {}
    for f in files:
        lang = LANG_EXT.get(f.suffix.lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    markers = [m for m in MARKERS if (repo / m).exists()]
    for m in markers:  # a manifest outweighs one stray file
        counts[MARKERS[m]] = counts.get(MARKERS[m], 0) + 2
    primary = max(counts, key=counts.get) if counts else "unknown"
    return {"primary": primary, "counts": counts, "markers": markers}


def declared_deps(repo):
    deps = set()
    req = repo / "requirements.txt"
    if req.exists():
        for line in req.read_text(encoding="utf-8",
                                  errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-")):
                deps.add(re.split(r"[<>=!~\[;\s]", line)[0].lower())
    pyproj = repo / "pyproject.toml"
    if pyproj.exists():
        text = pyproj.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
        if m:
            deps |= {re.split(r"[<>=!~\[;\s]", d)[0].lower()
                     for d in re.findall(r"[\"']([^\"']+)[\"']", m.group(1))}
    pkg = repo / "package.json"
    if pkg.exists():
        try:
            d = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
            deps |= set(d.get("dependencies", {}))
            deps |= set(d.get("devDependencies", {}))
        except json.JSONDecodeError:
            pass
    cargo = repo / "Cargo.toml"
    if cargo.exists():
        text = cargo.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"\[dependencies\](.*?)(\n\[|$)", text, re.DOTALL)
        if m:
            deps |= {ln.split("=")[0].strip() for ln in
                     m.group(1).splitlines() if "=" in ln}
    gomod = repo / "go.mod"
    if gomod.exists():
        deps |= set(re.findall(r"^\s*([\w./-]+)\s+v[\d.]",
                               gomod.read_text(encoding="utf-8",
                                               errors="ignore"), re.M))
    return sorted(deps)


def python_imports(files):
    """rel-stem -> imported top-level names, ast-parsed, capped."""
    out = {}
    for f in [p for p in files if p.suffix == ".py"][:MAX_PARSE]:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        mods = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                mods.add(n.module.split(".")[0])
        out[f.stem] = mods
    return out


def detect_framework(language, deps, imports):
    seen = set(deps)
    for mods in imports.values():
        seen |= mods
    hits = [FRAMEWORKS[k] for k in sorted(seen) if k in FRAMEWORKS]
    return sorted(set(hits)) or ([language] if language != "unknown" else [])


def dep_graph(repo, files, imports):
    """Internal edges (module imports module in this repo) + externals."""
    local = {f.stem for f in files if f.suffix == ".py"}
    local |= {d.name for d in repo.iterdir()
              if d.is_dir() and d.name not in SKIP}
    internal, external = [], set()
    for mod, mods in imports.items():
        for m in sorted(mods):
            if m in local and m != mod:
                internal.append([mod, m])
            elif m not in sys.stdlib_module_names:
                external.add(m)
    # js light pass: relative imports by regex
    for f in [p for p in files if p.suffix in (".js", ".ts", ".jsx",
                                               ".tsx")][:MAX_PARSE]:
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.findall(r"from\s+[\"']\.{1,2}/([\w/-]+)[\"']", text):
            internal.append([f.stem, Path(m).name])
    return {"internal": sorted(map(tuple, set(map(tuple, internal)))),
            "external": sorted(external)}


# -- analysis -------------------------------------------------------------
def risk_analysis(repo, files, language, frameworks, deps, vault):
    risks = []
    names = {f.name.lower() for f in files}
    rels = {str(f.relative_to(repo)).replace("\\", "/").lower()
            for f in files}
    if not any("test" in r for r in rels):
        risks.append(("high", "no tests found",
                      "changes cannot be verified mechanically"))
    if "readme.md" not in names and "readme.rst" not in names:
        risks.append(("med", "no README", "intent lives only in heads"))
    if not any(n.startswith("license") for n in names):
        risks.append(("low", "no LICENSE", "reuse status undefined"))
    if not any(".github/workflows" in r or ".gitlab-ci" in r for r in rels):
        risks.append(("med", "no CI config", "nothing runs tests on push"))
    todo = big = 0
    secret_hits = []
    for f in files[:100]:
        if f.suffix not in LANG_EXT or f.stat().st_size > 200_000:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        todo += len(re.findall(r"\b(TODO|FIXME|HACK)\b", text))
        lines = text.count("\n")
        if lines > 800:
            big += 1
        if SECRET_RE.search(text):
            secret_hits.append(str(f.relative_to(repo)))
    if secret_hits:
        risks.append(("high", f"possible hardcoded secrets: "
                              f"{', '.join(secret_hits[:3])}",
                      "credentials in history are compromised"))
    if big:
        risks.append(("med", f"{big} file(s) over 800 lines",
                      "monoliths resist review and reuse"))
    if todo > 20:
        risks.append(("low", f"{todo} TODO/FIXME markers",
                      "deferred debt is unbudgeted work"))
    req = repo / "requirements.txt"
    if language == "python" and req.exists():
        loose = [ln.split()[0] for ln in req.read_text(
            encoding="utf-8", errors="ignore").splitlines()
            if ln.strip() and not ln.startswith(("#", "-"))
            and "==" not in ln]
        if loose:
            risks.append(("med", f"unpinned deps: {', '.join(loose[:5])}",
                          "builds are not reproducible"))
    # experience pass: past faults that share words with this repo's shape
    text = " ".join([language, repo.name, *frameworks, *deps[:30]])
    for r in mine_risks(text, vault)[:5]:
        risks.append(("ledger", r, "this fault class already cost a session"))
    return risks


def conventions(files, language):
    out, sample = [], []
    ext = {"python": ".py", "javascript": ".js",
           "typescript": ".ts"}.get(language)
    for f in [p for p in files if p.suffix == ext][:MAX_SAMPLE]:
        sample.append(f.read_text(encoding="utf-8", errors="ignore"))
    if not sample:
        return ["no sources sampled - conventions unknown"]
    text = "\n".join(sample)
    lines = text.splitlines()
    four = sum(1 for ln in lines if re.match(r"^    \S", ln))
    two = sum(1 for ln in lines if re.match(r"^  \S", ln))
    tabs = sum(1 for ln in lines if ln.startswith("\t"))
    indent = "tabs" if tabs > max(four, two) else \
        ("2 spaces" if two > four * 2 else "4 spaces")
    out.append(f"indent: {indent}")
    sq, dq = text.count("'"), text.count('"')
    out.append(f"quotes: prefer {chr(39) if sq > dq else chr(34)}")
    longs = sorted(len(ln) for ln in lines)
    if longs:
        out.append(f"line length: p95 = "
                   f"{longs[int(len(longs) * 0.95) - 1]}")
    if language == "python":
        snake = len(re.findall(r"def [a-z0-9_]+\(", text))
        camel = len(re.findall(r"def [a-z]+[A-Z]\w*\(", text))
        out.append(f"naming: {'snake_case' if snake >= camel else 'camelCase'}")
        defs = docd = hinted = args = 0
        for src in sample:
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    defs += 1
                    docd += bool(ast.get_docstring(n))
                    for a in n.args.args:
                        args += 1
                        hinted += bool(a.annotation)
        if defs:
            out.append(f"docstring coverage: {100 * docd // defs}% of "
                       f"{defs} defs")
        if args:
            out.append(f"type hints: {100 * hinted // args}% of args")
    else:
        semis = sum(1 for ln in lines if ln.rstrip().endswith(";"))
        out.append(f"semicolons: {'yes' if semis > len(lines) * 0.2 else 'no'}")
    return out


def architecture(repo, files, language):
    dirs = {}
    for f in files:
        rel = f.relative_to(repo)
        top = rel.parts[0] if len(rel.parts) > 1 else "."
        dirs.setdefault(top, 0)
        dirs[top] += 1
    layout = [{"dir": d, "files": c, "role": DIR_ROLES.get(d, "-")}
              for d, c in sorted(dirs.items(), key=lambda x: -x[1])]
    entry = []
    for f in files:
        if f.name in ("main.py", "app.py", "cli.py", "index.js", "main.go",
                      "main.rs", "Main.java"):
            entry.append(str(f.relative_to(repo)).replace("\\", "/"))
        elif f.suffix == ".py" and f.stat().st_size < 200_000 \
                and '__name__' in f.read_text(encoding="utf-8",
                                              errors="ignore"):
            entry.append(str(f.relative_to(repo)).replace("\\", "/"))
    pkg = repo / "package.json"
    if pkg.exists():
        try:
            d = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
            start = d.get("scripts", {}).get("start")
            if start:
                entry.append(f"npm start ({start})")
        except json.JSONDecodeError:
            pass
    sizes = sorted(((f.stat().st_size, str(f.relative_to(repo))
                     .replace("\\", "/")) for f in files
                    if f.suffix in LANG_EXT), reverse=True)
    return {"layout": layout, "entrypoints": sorted(set(entry))[:8],
            "largest": [{"file": p, "kb": s // 1024} for s, p in sizes[:5]]}


def recommend_skills(name, language, frameworks, vault):
    try:
        from skills import discover
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            got = discover(f"work on the {language} "
                           f"{' '.join(frameworks)} project {name}",
                           vault=vault, quiet=True,
                           manifest=Path(td) / "m.json")
        return [{"name": s["name"], "confidence": s["confidence"]}
                for s in got["skills"]]
    except Exception:
        return []


# -- assembly ---------------------------------------------------------------
def context_package(sections, budget):
    """Priority-ordered sections, ~4 chars/token, drop lowest first."""
    est = [(prio, name, text, max(1, len(text) // 4))
           for prio, name, text in sections]
    keep, used = [], 0
    for prio, name, text, tok in sorted(est):
        if used + tok <= budget:
            keep.append({"section": name, "tokens": tok, "priority": prio})
            used += tok
    kept = {k["section"] for k in keep}
    return {"budget": budget, "used": used,
            "sections": keep,
            "omitted": [name for _, name, _, _ in est if name not in kept]}


def render_doc(pkg):
    p = pkg
    fw = ", ".join(p["frameworks"]) or "none detected"
    lines = [
        "---",
        f"tags: [bootstrap, {p['language']['primary']}]",
        f"project: {p['name']}", "status: active", "confidence: estimate",
        f"date: {date.today()}",
        f"summary: auto-bootstrap of {p['name']} - "
        f"{p['language']['primary']}/{fw}, {p['file_count']} files, "
        f"{len(p['risks'])} risks", "---", "",
        f"# {p['name']} — Bootstrap", "",
        "## Identity",
        f"- path: `{p['repo']}`",
        f"- language: **{p['language']['primary']}** "
        f"(markers: {', '.join(p['language']['markers']) or '-'})",
        f"- frameworks: **{fw}**",
        f"- files scanned: {p['file_count']}", "",
        "## Architecture", "",
        "| dir | files | role |", "|---|---|---|",
        *[f"| {d['dir']} | {d['files']} | {d['role']} |"
          for d in p["architecture"]["layout"][:10]],
        "",
        "entrypoints: " + (", ".join(
            f"`{e}`" for e in p["architecture"]["entrypoints"]) or "none"),
        "",
        "## Dependency graph",
        f"- external: {', '.join(p['deps']['external'][:15]) or 'none'}",
        "- internal edges: " + (", ".join(
            f"{a}->{b}" for a, b in p["deps"]["internal"][:12]) or "none"),
        "",
        "## Risks",
        *([f"- **{lvl}** {risk} — {why}"
           for lvl, risk, why in p["risks"]] or ["- none found"]),
        "",
        "## Conventions (measured, follow these)",
        *[f"- {c}" for c in p["conventions"]],
        "",
        "## Recommended skills",
        *([f"- /{s['name']} ({s['confidence']})"
           for s in p["skills"]] or ["- none above threshold"]),
        "",
        "## Context package",
        f"budget {p['context']['budget']} tokens, used "
        f"{p['context']['used']}",
        *[f"- {s['section']} ({s['tokens']} tok, p{s['priority']})"
          for s in p["context"]["sections"]],
        *([f"- OMITTED: {', '.join(p['context']['omitted'])}"]
          if p["context"]["omitted"] else []),
    ]
    return "\n".join(lines) + "\n"


def bootstrap(repo, vault=VAULT, name=None, budget=2500):
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise SystemExit(f"not a directory: {repo}")
    name = (name or repo.name).replace(" ", "_").upper()
    files = scan_files(repo)
    lang = detect_language(repo, files)
    deps = declared_deps(repo)
    imports = python_imports(files)
    fw = detect_framework(lang["primary"], deps, imports)
    graph = dep_graph(repo, files, imports)
    arch = architecture(repo, files, lang["primary"])
    risks = risk_analysis(repo, files, lang["primary"], fw,
                          deps + graph["external"], vault)
    conv = conventions(files, lang["primary"])
    sk = recommend_skills(name, lang["primary"], fw, vault)
    pkg = {"name": name, "repo": str(repo), "date": str(date.today()),
           "file_count": len(files), "language": lang, "frameworks": fw,
           "deps": {"external": sorted(set(graph["external"]) | set(deps)),
                    "internal": [list(e) for e in graph["internal"]]},
           "architecture": arch, "risks": [list(r) for r in risks],
           "conventions": conv, "skills": sk}
    pkg["summary"] = [
        f"{name}: {lang['primary']} / {', '.join(fw) or 'no framework'}",
        f"{len(files)} files; entrypoints: "
        f"{', '.join(arch['entrypoints'][:3]) or 'none found'}",
        f"deps: {len(pkg['deps']['external'])} external, "
        f"{len(pkg['deps']['internal'])} internal edges",
        f"risks: {len(risks)} "
        f"({sum(1 for r in risks if r[0] == 'high')} high)",
        f"conventions: {conv[0] if conv else '-'}",
        f"skills: {', '.join('/' + s['name'] for s in sk[:3]) or 'none'}",
    ]
    # context package: priority = what Claude must see first
    sections = [
        (1, "identity+summary", "\n".join(pkg["summary"])),
        (2, "risks", "\n".join(f"{l}: {r}" for l, r, _ in risks)),
        (3, "architecture", json.dumps(arch)),
        (4, "conventions", "\n".join(conv)),
        (5, "dependency-graph", json.dumps(pkg["deps"])),
        (6, "skills", json.dumps(sk)),
    ]
    pkg["context"] = context_package(sections, budget)
    proj = vault / "10_PROJECTS" / name
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "BOOTSTRAP.md").write_text(render_doc(pkg), encoding="utf-8")
    (proj / "bootstrap.json").write_text(
        json.dumps(pkg, indent=1) + "\n", encoding="utf-8")
    pkg["doc"] = str(proj / "BOOTSTRAP.md")
    # automatic knowledge integration: reindex + regraph if this is a
    # real vault (temp selftest vaults have no scripts/)
    for tool in ("indexer.py", "graph.py"):
        script = vault / "scripts" / tool
        if script.exists():
            subprocess.run([sys.executable, str(script)]
                           + (["build"] if tool == "graph.py" else []),
                           cwd=vault, capture_output=True, timeout=120)
    return pkg


def show(pkg):
    for line in pkg["summary"]:
        print(f"  {line}")
    print(f"  doc: {pkg['doc']}")
    print(f"  context: {pkg['context']['used']}/{pkg['context']['budget']} "
          f"tokens, {len(pkg['context']['sections'])} sections"
          + (f", omitted {', '.join(pkg['context']['omitted'])}"
             if pkg["context"]["omitted"] else ""))


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        v = Path(td) / "vault"
        (v / "90_META").mkdir(parents=True)
        (v / "90_META" / "FAULT_LEDGER.md").write_text(
            "- [X][fastapi] async handler swallowed exception -> fail loud\n",
            encoding="utf-8")
        repo = Path(td) / "demo-api"
        (repo / "app").mkdir(parents=True)
        (repo / "app" / "main.py").write_text(
            "import fastapi\nimport util\n\n\n"
            "def serve(port: int):\n"
            '    """Run it."""\n'
            "    return util.helper(port)\n\n\n"
            'if __name__ == "__main__":\n    serve(80)\n',
            encoding="utf-8")
        (repo / "app" / "util.py").write_text(
            "def helper(x):\n    return x\n\n\n"
            + 'token = "abcdef123456"\n',  # verifier:ignore
            encoding="utf-8")
        (repo / "requirements.txt").write_text(
            "fastapi\nrequests==2.31.0\n", encoding="utf-8")

        pkg = bootstrap(repo, vault=v, budget=2500)
        assert pkg["language"]["primary"] == "python", pkg["language"]
        assert "requirements.txt" in pkg["language"]["markers"]
        assert "FastAPI" in pkg["frameworks"], pkg["frameworks"]
        assert ["main", "util"] in pkg["deps"]["internal"], pkg["deps"]
        assert "fastapi" in pkg["deps"]["external"]
        assert "app/main.py" in pkg["architecture"]["entrypoints"]
        rtext = " ".join(r[1] for r in pkg["risks"])
        assert "no tests" in rtext and "no README" in rtext, rtext
        assert "unpinned" in rtext and "secrets" in rtext, rtext
        assert any(r[0] == "ledger" for r in pkg["risks"]), \
            "fault ledger not mined"
        conv = " ".join(pkg["conventions"])
        assert "4 spaces" in conv and "snake_case" in conv, conv
        assert len(pkg["summary"]) >= 6
        doc = Path(pkg["doc"]).read_text(encoding="utf-8")
        assert doc.startswith("---") and "summary:" in doc, "frontmatter law"
        assert "## Risks" in doc and "## Conventions" in doc
        assert (v / "10_PROJECTS" / "DEMO-API" / "bootstrap.json").exists()
        assert pkg["context"]["used"] <= 2500
        assert not pkg["context"]["omitted"]

        # tiny budget drops lowest-priority sections, keeps identity
        pkg2 = bootstrap(repo, vault=v, budget=120)
        kept = {s["section"] for s in pkg2["context"]["sections"]}
        assert "identity+summary" in kept, kept
        assert pkg2["context"]["omitted"], "nothing omitted at 120 tokens"

        # javascript repo
        js = Path(td) / "webapp"
        js.mkdir()
        (js / "package.json").write_text(
            '{"dependencies": {"react": "^18.0.0"}, '
            '"scripts": {"start": "vite"}}', encoding="utf-8")
        (js / "index.js").write_text(
            "import { x } from './lib/store';\nconst a = 1;\n",
            encoding="utf-8")
        (js / "lib").mkdir()
        (js / "lib" / "store.js").write_text("export const x = 1;\n",
                                             encoding="utf-8")
        pkg3 = bootstrap(js, vault=v)
        assert pkg3["language"]["primary"] == "javascript"
        assert "React" in pkg3["frameworks"]
        assert ["index", "store"] in pkg3["deps"]["internal"]
        assert any("npm start" in e for e in
                   pkg3["architecture"]["entrypoints"])
    print("selftest OK")


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Project bootstrap engine.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    op = sub.add_parser("open")
    op.add_argument("repo")
    op.add_argument("--name")
    op.add_argument("--budget", type=int, default=2500)
    op.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    if args.selftest:
        selftest()
    elif args.cmd == "open":
        pkg = bootstrap(args.repo, name=args.name, budget=args.budget)
        print(json.dumps(pkg, indent=1) if args.as_json else "", end="")
        if not args.as_json:
            show(pkg)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
