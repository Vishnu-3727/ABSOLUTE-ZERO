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

# name -> (script under scripts/, fixed argv prefix, takes an argument)
ALLOWED = {
    "wake":    ("orchestrator.py", ["similarity"], True),
    "task":    ("orchestrator.py", ["plan"], True),
    "recall":  ("context.py", ["pack"], True),
    "index":   ("indexer.py", [], False),
    "graph":   ("graph.py", ["build"], False),
    "verify":  ("verifier.py", ["check"], False),
    "profile": ("profiler.py", ["report"], False),
    "sleep":   ("experience.py", ["harvest"], False),
}


def run_cmd(name, arg, vault=VAULT, allowed=ALLOWED):
    """Execute one whitelisted deck command; returns a JSON-able dict."""
    if name not in allowed:
        return {"ok": False, "output": f"unknown command: {name}"}
    script, prefix, takes_arg = allowed[name]
    argv = [sys.executable, str(vault / "scripts" / script)] + list(prefix)
    if takes_arg:
        arg = (arg or "").strip()[:MAX_ARG]
        if not arg:
            return {"ok": False, "output": f"{name} needs an argument"}
        argv.append(arg)
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
            if self.path in ("/", "/dashboard.html"):
                page = dashboard.render(dashboard.gather(vault))
                self._send(200, page, "text/html")
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
            except (ValueError, json.JSONDecodeError):
                return self._send(400,
                                  '{"ok": false, "output": "bad request"}')
            res = run_cmd(name, arg, vault, allowed)
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
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        (v / "90_META").mkdir(parents=True)
        (v / "scripts").mkdir()
        (v / "scripts" / "ping.py").write_text(
            "import sys; print('pong', sys.argv[1])", encoding="utf-8")
        allowed = {"ping": ("ping.py", [], True)}
        srv = ThreadingHTTPServer(("127.0.0.1", 0),
                                  make_handler(v, allowed))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "ABSOLUTE ZERO" in page, "dashboard not served"
        req = urllib.request.Request(
            base + "/run", json.dumps({"cmd": "ping", "arg": "x"}).encode(),
            {"Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req).read())
        assert res["ok"] and "pong x" in res["output"]
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
    ap = argparse.ArgumentParser(description="Vault terminal server.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    serve(args.port)


if __name__ == "__main__":
    main()
