#!/usr/bin/env python3
"""ABSOLUTE ZERO vault terminal server. Stdlib only.

Serves the dashboard (rebuilt fresh on every page load) and executes the
command deck live: POST /run {"cmd": name, "arg": text} runs the matching
vault script and returns its output as JSON. Security: `cmd` is a key
into the ALLOWED whitelist - the client never supplies a command line,
and `arg` is passed as a single argv element (no shell). Binds 127.0.0.1
only.

  python scripts/server.py            # http://127.0.0.1:8377/
  python scripts/server.py --port 9000
  python scripts/server.py --selftest
"""
import argparse
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dashboard

VAULT = Path(__file__).resolve().parent.parent
PORT = 8377
TIMEOUT = 300
MAX_ARG = 500

# name -> (script under scripts/, fixed argv prefix, takes a positional
# argument, allowed --flag names). Flags are a fixed whitelist per command:
# the client picks values, never flag names, so no argv it sends can become
# an option the script did not opt into.
ALLOWED = {
    "wake":    ("orchestrator.py", ["similarity"], True, ()),
    "task":    ("orchestrator.py", ["plan"], True, ("project",)),
    # log/close close the loop a UI-started task opens - without them the
    # dashboard could begin work it had no way to finish, leaving traces
    # dangling and the learning loop never firing.
    "log":     ("orchestrator.py", ["log"], False, ("trace", "state", "note")),
    "close":   ("orchestrator.py", ["close"], False,
                ("trace", "result", "summary")),
    "recall":  ("context.py", ["pack"], True, ("project",)),
    "plan":    ("planner.py", ["plan"], True, ("project",)),
    "cases":   ("cases.py", ["similar"], True, ()),
    "new":     ("project.py", ["new"], True, ("topic", "tags")),
    "brief":   ("promptc.py", ["compile"], True, ("project",)),
    "query":   ("query.py", [], False, ("tags", "type", "project")),
    "review":  ("review.py", [], False, ()),
    "skills":  ("skills.py", ["discover"], True, ()),
    "agents":  ("agents.py", ["run"], True, ()),
    "index":   ("indexer.py", [], False, ()),
    "graph":   ("graph.py", ["build"], False, ()),
    "verify":  ("verifier.py", ["check"], False, ()),
    "profile": ("profiler.py", ["report"], False, ()),
    "harvest": ("experience.py", ["harvest"], False, ()),
}
# Params naming a path must stay inside the vault directory that owns them.
PATH_PARAMS = {"trace": "90_META/traces"}

MAX_FILE = 1_000_000  # skip pathological files; notes are tiny


def gather_vault_files(vault):
    """All files the UI's client-side parser eats: markdown notes plus
    Obsidian plugin manifests. Paths are vault-relative, posix-style,
    because the client filters on them with the same regexes it uses
    for webkitRelativePath."""
    files = []

    def add(p):
        rel = p.relative_to(vault).as_posix()
        if p.stat().st_size > MAX_FILE:
            return
        try:
            files.append({"path": rel,
                          "text": p.read_text("utf-8", errors="replace")})
        except OSError:
            pass

    for p in vault.rglob("*.md"):
        rel = p.relative_to(vault).as_posix()
        if rel.startswith((".git/", ".obsidian/")) or "/.git/" in rel:
            continue
        add(p)
    obs = vault / ".obsidian"
    if obs.is_dir():
        comm = obs / "community-plugins.json"
        if comm.is_file():
            add(comm)
        for m in obs.glob("plugins/*/manifest.json"):
            add(m)
    return {"files": files}


def _clean(value):
    return str(value or "").strip()[:MAX_ARG]


def _check_path(param, value, vault):
    """A path from the network must not escape the directory it belongs to.
    Loopback-only is not an argument for skipping this: the browser is not
    the only thing that can POST to a local port."""
    home = (vault / PATH_PARAMS[param]).resolve()
    try:
        target = (vault / value).resolve() if not Path(value).is_absolute() \
            else Path(value).resolve()
    except (OSError, ValueError):
        return None
    if target != home and home not in target.parents:
        return None
    return str(target)


def run_cmd(name, arg, vault=VAULT, allowed=ALLOWED, flags=None):
    """Execute one whitelisted deck command; returns a JSON-able dict."""
    if name not in allowed:
        return {"ok": False, "output": f"unknown command: {name}"}
    script, prefix, takes_arg, ok_flags = allowed[name]
    argv = [sys.executable, str(vault / "scripts" / script)] + list(prefix)
    if takes_arg:
        arg = _clean(arg)
        if not arg:
            return {"ok": False, "output": f"{name} needs an argument"}
        argv.append(arg)
    for key, raw in (flags or {}).items():
        if key not in ok_flags:
            return {"ok": False, "output": f"{name}: unknown option {key}"}
        value = _clean(raw)
        if not value:
            continue
        if key in PATH_PARAMS:
            value = _check_path(key, value, vault)
            if value is None:
                return {"ok": False,
                        "output": f"{key} must be inside {PATH_PARAMS[key]}"}
        argv += [f"--{key}", value]
    try:
        r = subprocess.run(argv, cwd=vault, capture_output=True,
                           text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"{name} timed out after {TIMEOUT}s"}
    out = (r.stdout + (("\n" + r.stderr) if r.stderr.strip() else "")).strip()
    return {"ok": r.returncode == 0, "output": out or "(no output)"}


def make_handler(vault, allowed=ALLOWED):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            ui = vault / "scripts" / "ui.html"
            if self.path == "/" and ui.is_file():
                self._send(200, ui.read_text("utf-8", errors="replace"),
                           "text/html")
            elif self.path in ("/", "/dashboard.html"):
                page = dashboard.render(dashboard.gather(vault))
                self._send(200, page, "text/html")
            elif self.path == "/api/vault":
                self._send(200, json.dumps(gather_vault_files(vault)))
            elif self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            else:
                self._send(404, '{"ok": false, "output": "not found"}')

        def do_POST(self):
            if self.path != "/run":
                return self._send(404,
                                  '{"ok": false, "output": "not found"}')
            try:
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n))
                name, arg = str(req.get("cmd", "")), str(req.get("arg", ""))
                flags = req.get("flags") or {}
                if not isinstance(flags, dict):
                    raise ValueError("flags must be an object")
            except (ValueError, json.JSONDecodeError):
                return self._send(400,
                                  '{"ok": false, "output": "bad request"}')
            res = run_cmd(name, arg, vault, allowed, flags)
            self._send(200 if res["ok"] else 422, json.dumps(res))

        def log_message(self, fmt, *args):
            print(f"  {self.address_string()} {fmt % args}")

    return Handler


def serve(port=PORT, vault=VAULT):
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(vault))
    print(f"vault terminal -> http://127.0.0.1:{port}/  (Ctrl+C stops)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def selftest():
    import tempfile
    import threading
    import urllib.request
    import urllib.error
    assert run_cmd("nope", "")["ok"] is False
    assert "needs an argument" in run_cmd("task", "  ")["output"]
    # a flag the command did not opt into is refused, so the client can
    # never bolt an arbitrary option onto a whitelisted script
    r = run_cmd("index", "", flags={"output": "/etc/passwd"})
    assert not r["ok"] and "unknown option" in r["output"], r
    # path params stay inside their directory - traversal is refused
    for escape in ("../../scripts/core.py", "..\\..\\CLAUDE.md",
                   str(Path(VAULT / "CLAUDE.md"))):
        r = run_cmd("close", "", flags={"trace": escape})
        assert not r["ok"] and "must be inside" in r["output"], (escape, r)
    # a legitimate trace path is accepted (argparse then owns validation)
    ok_path = "90_META/traces/does-not-exist.json"
    assert _check_path("trace", ok_path, VAULT) is not None
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        (v / "90_META").mkdir(parents=True)
        (v / "scripts").mkdir()
        (v / "scripts" / "ping.py").write_text(
            "import sys; print('pong', sys.argv[1])", encoding="utf-8")
        allowed = {"ping": ("ping.py", [], True, ("note",))}
        srv = ThreadingHTTPServer(("127.0.0.1", 0),
                                  make_handler(v, allowed))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "ABSOLUTE ZERO" in page, "dashboard not served"
        # ui.html, once present, takes over "/" and /api/vault feeds it
        (v / "scripts" / "ui.html").write_text("UI-SENTINEL",
                                               encoding="utf-8")
        (v / "note one.md").write_text("[[note two]]", encoding="utf-8")
        assert "UI-SENTINEL" in urllib.request.urlopen(
            base + "/").read().decode()
        api = json.loads(urllib.request.urlopen(
            base + "/api/vault").read())
        assert any(f["path"] == "note one.md" and "[[note two]]" in f["text"]
                   for f in api["files"]), api
        req = urllib.request.Request(
            base + "/run", json.dumps({"cmd": "ping", "arg": "x"}).encode(),
            {"Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req).read())
        assert res["ok"] and "pong x" in res["output"]
        # flags travel over the wire and reach argv
        req2 = urllib.request.Request(
            base + "/run",
            json.dumps({"cmd": "ping", "arg": "x",
                        "flags": {"note": "hi"}}).encode(),
            {"Content-Type": "application/json"})
        assert json.loads(urllib.request.urlopen(req2).read())["ok"]
        bad = urllib.request.Request(
            base + "/run", json.dumps({"cmd": "rm -rf /"}).encode(),
            {"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(bad)
            raise AssertionError("non-whitelisted command accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 422
        srv.shutdown()
    print("selftest OK")


def main():
    # vault content is UTF-8; a cp1252 pipe would crash on note titles
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Vault terminal server.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    serve(args.port)


if __name__ == "__main__":
    main()
