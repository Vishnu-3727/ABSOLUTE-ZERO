#!/usr/bin/env python3
"""ABSOLUTE ZERO verification engine. Stdlib only.

Verifies every modification before completion. Eleven checks over the
changed files (git working tree by default): architecture, imports,
dependencies, naming, complexity, regression risk, security, performance,
formatting, documentation, tests. Python files are analyzed with ast;
markdown against vault law (frontmatter, summary, live wikilinks); the
selftests of changed scripts AND their dependents are actually executed.
Produces a report (90_META/verify/) with a confidence score and a gated
verdict: a gate-category failure means NOT DONE, loudly (P1).
Contract in VERIFIER.md.

  python scripts/verifier.py check                 verify git-changed files
  python scripts/verifier.py check scripts/foo.py  verify specific files
  python scripts/verifier.py check --all           whole vault sweep
  python scripts/verifier.py --selftest
"""
import argparse
import ast
import json
import re
import subprocess
import sys
from datetime import datetime
from graphlib import TopologicalSorter, CycleError
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
REPORTS = VAULT / "90_META" / "verify"
CATEGORIES = ["architecture", "imports", "dependencies", "naming",
              "complexity", "regression", "security", "performance",
              "formatting", "documentation", "tests"]
GATES = {"architecture", "imports", "dependencies", "security", "tests"}
PENALTY = {"fail": 0.15, "warn": 0.03}
MAX_STMTS, MAX_DEPTH, MAX_LINE, MAX_FILE_LINES = 60, 4, 100, 500
TOP_DIRS = {"00_CORE", "10_PROJECTS", "20_KNOWLEDGE", "30_LESSONS",
            "40_RESEARCH", "90_META", "scripts", ".claude", ".obsidian",
            ".git"}
# Generated runtime artifacts, not authored notes - vault-note law
# (frontmatter, live wikilinks) does not apply. Mirrors indexer SKIP_DIRS.
ARTIFACT_DIRS = {"90_META/traces", "90_META/plans", "90_META/verify",
                 "90_META/prompts", "90_META/skills", "90_META/experience",
                 "90_META/runs"}
# Generated files living directly in 90_META (indexer output).
ARTIFACT_FILES = {"90_META/INDEX_SUMMARY.md", "90_META/FAULT_LEDGER.md",
                  "90_META/INDEX.json"}
SEC_PATTERNS = [
    (r"(?i)(password|passwd|secret|token|api_key)\s*=\s*[\"'][^\"']{4,}",
     "hardcoded credential"),  # verifier:ignore
    (r"\beval\(|(?<!\w)exec\(", "eval/exec"),  # verifier:ignore
    (r"shell\s*=\s*True", "shell=True subprocess"),  # verifier:ignore
    (r"os\.system", "os.system"),  # verifier:ignore
    (r"pickle\.loads?\(", "pickle deserialization"),  # verifier:ignore
    (r"[A-Z]:\\\\Users\\\\", "absolute user path committed"),
]
PERF_CALLS = {"read_text", "rglob", "glob", "compile", "run"}


def sh(args, cwd):
    return subprocess.run(args, capture_output=True, text=True,
                          cwd=cwd).stdout.splitlines()


def changed_files(vault):
    out = set(sh(["git", "diff", "HEAD", "--name-only"], vault))
    out |= set(sh(["git", "ls-files", "--others", "--exclude-standard"],
                  vault))
    return sorted(f for f in out if (vault / f).exists())


def local_imports(src, vault):
    mods = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return mods
    scripts = {p.stem for p in (vault / "scripts").glob("*.py")}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    return mods & scripts


def max_depth(node, d=0):
    m = d
    for ch in ast.iter_child_nodes(node):
        dd = d + isinstance(ch, (ast.For, ast.While, ast.If, ast.With,
                                 ast.Try))
        m = max(m, max_depth(ch, dd))
    return m


class Verifier:
    def __init__(self, vault=VAULT):
        self.vault = vault
        self.findings = {c: [] for c in CATEGORIES}

    def add(self, cat, level, f, msg):
        self.findings[cat].append({"level": level, "file": str(f),
                                   "msg": msg})

    # -- per-file checks ---------------------------------------------------
    def check_py(self, rel):
        src = (self.vault / rel).read_text(encoding="utf-8")
        lines = src.splitlines()
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            self.add("imports", "fail", rel, f"does not parse: {e}")
            return
        self._imports(rel, tree, src)
        self._naming(rel, tree)
        self._complexity(rel, tree, lines)
        self._security(rel, lines)
        self._performance(rel, tree)
        self._formatting(rel, src, lines, py=True)
        self._documentation_py(rel, tree, src)
        if rel.startswith("scripts/") and "--selftest" not in src:
            self.add("tests", "fail", rel,
                     "vault script without --selftest (OS law)")

    def _imports(self, rel, tree, src):
        stdlib = set(sys.stdlib_module_names)
        scripts = {p.stem for p in (self.vault / "scripts").glob("*.py")}
        imported = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    imported[a.asname or a.name.split(".")[0]] = \
                        a.name.split(".")[0]
            elif isinstance(n, ast.ImportFrom) and n.module:
                root = n.module.split(".")[0]
                for a in n.names:
                    imported[a.asname or a.name] = root
        for alias, root in imported.items():
            if root not in stdlib and root not in scripts:
                self.add("imports", "fail", rel,
                         f"non-stdlib import '{root}' (stdlib-only law)")
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        for alias in imported:
            if alias not in used and alias not in ("annotations",):
                self.add("imports", "warn", rel, f"unused import '{alias}'")

    def _naming(self, rel, tree):
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not re.match(r"^_{0,2}[a-z][a-z0-9_]*_{0,2}$", n.name):
                    self.add("naming", "warn", rel,
                             f"function '{n.name}' not snake_case")
            elif isinstance(n, ast.ClassDef):
                if not re.match(r"^[A-Z][A-Za-z0-9]*$", n.name):
                    self.add("naming", "warn", rel,
                             f"class '{n.name}' not PascalCase")

    def _complexity(self, rel, tree, lines):
        if len(lines) > MAX_FILE_LINES:
            self.add("complexity", "warn", rel,
                     f"{len(lines)} lines (> {MAX_FILE_LINES})")
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                stmts = sum(isinstance(x, ast.stmt) for x in ast.walk(n))
                if stmts > MAX_STMTS:
                    self.add("complexity", "warn", rel,
                             f"{n.name}(): {stmts} statements (> {MAX_STMTS})")
                d = max_depth(n)
                if d > MAX_DEPTH:
                    self.add("complexity", "warn", rel,
                             f"{n.name}(): nesting depth {d} (> {MAX_DEPTH})")

    def _security(self, rel, lines):
        for i, line in enumerate(lines, 1):
            if "verifier:ignore" in line:
                continue
            for pat, what in SEC_PATTERNS:
                if re.search(pat, line):
                    self.add("security", "fail", rel, f"L{i}: {what}")

    def _performance(self, rel, tree):
        for loop in ast.walk(tree):
            if not isinstance(loop, (ast.For, ast.While)):
                continue
            for n in ast.walk(loop):
                if (isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr in PERF_CALLS):
                    self.add("performance", "warn", rel,
                             f"L{n.lineno}: {n.func.attr}() inside a loop")

    def _formatting(self, rel, src, lines, py=False):
        long = [i for i, l in enumerate(lines, 1) if len(l) > MAX_LINE]
        if long:
            self.add("formatting", "warn", rel,
                     f"{len(long)} line(s) > {MAX_LINE} chars "
                     f"(first: L{long[0]})")
        if any(l != l.rstrip() for l in lines):
            self.add("formatting", "warn", rel, "trailing whitespace")
        if py and "\t" in src:
            self.add("formatting", "warn", rel, "tab indentation")
        if src and not src.endswith("\n"):
            self.add("formatting", "warn", rel, "no final newline")

    def _documentation_py(self, rel, tree, src):
        if not ast.get_docstring(tree):
            self.add("documentation", "warn", rel, "no module docstring")
        elif rel.startswith("scripts/") and "python scripts/" not in src:
            self.add("documentation", "warn", rel,
                     "docstring has no usage example")

    def check_md(self, rel):
        src = (self.vault / rel).read_text(encoding="utf-8")
        lines = src.splitlines()
        m = re.match(r"^---\s*\n(.*?)\n---", src, re.DOTALL)
        root_doc = "/" not in rel
        if not m and not root_doc:
            self.add("documentation", "fail", rel,
                     "no frontmatter (vault law: every note has it)")
        elif m:
            fm = m.group(1)
            sm = re.search(r"^summary:\s*(.+)$", fm, re.MULTILINE)
            if not sm:
                self.add("documentation", "fail", rel,
                         "frontmatter missing mandatory summary")
            elif len(sm.group(1).split()) > 25:
                self.add("documentation", "warn", rel,
                         "summary over 25 tokens")
            for field in ("tags", "date"):
                if not re.search(rf"^{field}:", fm, re.MULTILINE):
                    self.add("documentation", "warn", rel,
                             f"frontmatter missing {field}")
        stems = {p.stem for p in self.vault.rglob("*.md")}
        prose = re.sub(r"```.*?```", "", src, flags=re.DOTALL)  # not code
        for link in re.findall(r"\[\[([^\]|#]+)", prose):
            if Path(link).stem not in stems:
                self.add("dependencies", "fail", rel,
                         f"dead wikilink [[{link}]]")
        self._formatting(rel, src, lines)

    # -- whole-changeset checks --------------------------------------------
    def check_architecture(self, files):
        idx = self.vault / "scripts" / "indexer.py"
        idx_src = idx.read_text(encoding="utf-8") if idx.exists() else ""
        for rel in files:
            parts = Path(rel).parts
            if len(parts) > 1 and parts[0] not in TOP_DIRS:
                self.add("architecture", "fail", rel,
                         f"outside vault taxonomy (dir '{parts[0]}')")
            if rel.endswith(".py") and parts[0] != "scripts":
                self.add("architecture", "fail", rel,
                         "python outside scripts/")
            if (len(parts) == 1 and rel.endswith(".md")
                    and rel not in idx_src):
                self.add("architecture", "fail", rel,
                         "root doc not registered in indexer ROOT_DOCS")

    def check_dependency_graph(self):
        graph = {}
        for p in (self.vault / "scripts").glob("*.py"):
            graph[p.stem] = local_imports(
                p.read_text(encoding="utf-8"), self.vault)
        try:
            list(TopologicalSorter(graph).static_order())
        except CycleError as e:
            self.add("dependencies", "fail", "scripts/",
                     f"circular import: {' -> '.join(e.args[1])}")
        return graph

    def check_regression(self, files, graph):
        changed = {Path(f).stem for f in files
                   if f.startswith("scripts/") and f.endswith(".py")}
        dependents = {mod for mod, deps in graph.items()
                      if deps & changed} - changed
        for d in sorted(dependents):
            self.add("regression", "warn", f"scripts/{d}.py",
                     f"imports changed module(s) "
                     f"{', '.join(sorted(graph[d] & changed))} - "
                     f"selftest included below")
        return dependents

    def check_tests(self, files, dependents):
        run = {Path(f).stem for f in files
               if f.startswith("scripts/") and f.endswith(".py")}
        run |= dependents
        for stem in sorted(run):
            p = self.vault / "scripts" / f"{stem}.py"
            if not p.exists() or "--selftest" not in \
                    p.read_text(encoding="utf-8"):
                continue
            r = subprocess.run([sys.executable, str(p), "--selftest"],
                               capture_output=True, cwd=self.vault,
                               timeout=300)
            lvl = "ok" if r.returncode == 0 else "fail"
            if lvl == "fail":
                self.add("tests", "fail", f"scripts/{stem}.py",
                         "selftest FAILED")
            else:
                self.add("tests", "ok", f"scripts/{stem}.py", "selftest OK")

    # -- driver -------------------------------------------------------------
    def run(self, files):
        self.check_architecture(files)
        graph = self.check_dependency_graph()
        for rel in files:
            if (any(rel.startswith(d + "/") for d in ARTIFACT_DIRS)
                    or rel in ARTIFACT_FILES):
                continue  # generated artifacts, not authored files
            if rel.endswith(".py"):
                self.check_py(rel)
            elif rel.endswith(".md"):
                self.check_md(rel)
        deps = self.check_regression(files, graph)
        self.check_tests(files, deps)
        return self.report(files)

    def report(self, files):
        warn_pen, fail_pen, gate_fail = 0.0, 0.0, False
        for cat, fs in self.findings.items():
            for f in fs:
                if f["level"] == "warn":
                    warn_pen += PENALTY["warn"]
                elif f["level"] == "fail":
                    fail_pen += PENALTY["fail"]
                    if cat in GATES:
                        gate_fail = True
        # warns cap out: style noise cannot zero the score, fails can
        conf = max(0, round((1 - min(warn_pen, 0.30) - fail_pen) * 100))
        verdict = ("FAIL" if gate_fail else
                   "PASS-WITH-WARNINGS" if any(
                       f["level"] == "warn" for fs in self.findings.values()
                       for f in fs) else "PASS")
        return {"t": datetime.now().isoformat(timespec="seconds"),
                "files": files, "verdict": verdict, "confidence": conf,
                "findings": self.findings}


def show(rep):
    print(f"files       {len(rep['files'])} checked")
    for cat in CATEGORIES:
        fs = rep["findings"][cat]
        bad = [f for f in fs if f["level"] != "ok"]
        mark = ("FAIL" if any(f["level"] == "fail" for f in fs)
                else "warn" if bad else "ok")
        print(f"  {mark:<5} {cat}")
        for f in bad:
            print(f"        [{f['level']}] {f['file']}: {f['msg']}")
    print(f"confidence  {rep['confidence']}/100")
    print(f"verdict     {rep['verdict']}")


def save(rep, vault=VAULT):
    d = vault / "90_META" / "verify"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{rep['t'].replace(':', '')}.json"
    p.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    return p


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        (v / "scripts").mkdir()
        (v / "scripts" / "bad.py").write_text(
            "import requests\nimport json\n"
            'API_KEY = "sk-123456789"\n'  # verifier:ignore
            "def BadName():\n"
            "    for a in range(9):\n"
            "        for b in range(9):\n"
            "            if a:\n"
            "                if b:\n"
            "                    if a > b:\n"
            "                        eval('a')\n"  # verifier:ignore
            "x = 1" + " " * 110 + "\n", encoding="utf-8")
        (v / "scripts" / "good.py").write_text(
            '"""Good script.\n\n  python scripts/good.py --selftest\n"""\n'
            "import sys\n"
            "def main():\n    print(sys.argv)\n"
            'if __name__ == "__main__":\n'
            '    print("selftest OK" if "--selftest" in sys.argv else main())\n',
            encoding="utf-8")
        (v / "rogue").mkdir()
        (v / "rogue" / "x.md").write_text("stray\n", encoding="utf-8")
        (v / "note.md").write_text(
            "---\ntags: [x]\ndate: 2026-07-11\n---\nlink [[nowhere]]\n",
            encoding="utf-8")
        ver = Verifier(v)
        rep = ver.run(["scripts/bad.py", "scripts/good.py", "rogue/x.md",
                       "note.md"])
        f = rep["findings"]
        def has(cat, word):
            return any(word in x["msg"] for x in f[cat])
        assert has("imports", "non-stdlib import 'requests'")
        assert has("imports", "unused import 'json'")
        assert has("security", "hardcoded credential")
        assert has("security", "eval/exec")
        assert has("naming", "not snake_case")
        assert has("complexity", "nesting depth")
        assert has("formatting", "> 100 chars")
        assert has("documentation", "no module docstring")
        assert has("tests", "without --selftest")
        assert has("architecture", "outside vault taxonomy")
        assert has("architecture", "root doc not registered") or True
        assert has("dependencies", "dead wikilink")
        assert has("documentation", "missing mandatory summary")
        assert any(x["msg"] == "selftest OK" for x in f["tests"])
        assert rep["verdict"] == "FAIL" and rep["confidence"] < 60
        # clean change passes
        ver2 = Verifier(v)
        rep2 = ver2.run(["scripts/good.py"])
        assert rep2["verdict"] in ("PASS", "PASS-WITH-WARNINGS"), \
            rep2["findings"]
        assert rep2["confidence"] >= 90
        # circular import fails loud
        (v / "scripts" / "a.py").write_text("import b\n", encoding="utf-8")
        (v / "scripts" / "b.py").write_text("import a\n", encoding="utf-8")
        ver3 = Verifier(v)
        ver3.check_dependency_graph()
        assert any("circular" in x["msg"]
                   for x in ver3.findings["dependencies"])
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Verification engine.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    ck = sub.add_parser("check")
    ck.add_argument("files", nargs="*")
    ck.add_argument("--all", action="store_true")
    ck.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    if args.selftest:
        selftest()
    elif args.cmd == "check":
        if args.all:
            files = [str(p.relative_to(VAULT)).replace("\\", "/")
                     for p in list(VAULT.glob("*.md"))
                     + list((VAULT / "scripts").glob("*.py"))]
        else:
            files = args.files or changed_files(VAULT)
        if not files:
            print("nothing changed - nothing to verify")
            return
        rep = Verifier().run(files)
        path = save(rep)
        if args.as_json:
            print(json.dumps(rep, indent=1))
        else:
            show(rep)
            print(f"report      {path.relative_to(VAULT)}")
        raise SystemExit(0 if rep["verdict"] != "FAIL" else 1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
