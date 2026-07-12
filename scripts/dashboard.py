#!/usr/bin/env python3
"""ABSOLUTE ZERO dashboard renderer. Stdlib only.

Renders 90_META/dashboard.html - a self-contained ICE-themed control room
for the vault: stat tiles (notes, faults, lessons, engines, graph size),
notes-per-project bars, the fault ledger, workflow stats from the
experience engine, and the freshest notes. Pure read: INDEX.json,
FAULT_LEDGER.md, workflows.json, PLUGINS.json, GRAPH.json. Open the
output in any browser; no network, no dependencies.

  python scripts/dashboard.py
  python scripts/dashboard.py --out somewhere.html
  python scripts/dashboard.py --selftest
"""
import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import load_json

VAULT = Path(__file__).resolve().parent.parent
OUT = VAULT / "90_META" / "dashboard.html"
MAX_ROWS = 12

# ICE palette: deep-water surface, glacial accents. Single-hue sequential.
CSS = """
:root {
  --bg: #0a1220; --panel: #101c30; --panel2: #16263f;
  --ink: #e8f4fd; --ink2: #9db8d2; --muted: #5f7a96;
  --ice: #7dd3fc; --ice2: #38bdf8; --ice3: #0ea5e9; --frost: #a5f3fc;
  --line: #1e3350; --warn: #fbbf24; --fail: #f87171; --ok: #34d399;
}
* { box-sizing: border-box; margin: 0; }
body { background: var(--bg); color: var(--ink); padding: 28px;
  font: 15px/1.5 "Segoe UI", system-ui, sans-serif; }
a { color: var(--ice); text-decoration: none; }
header { display: flex; align-items: baseline; gap: 14px;
  margin-bottom: 6px; }
h1 { font-size: 26px; letter-spacing: 4px; font-weight: 700;
  background: linear-gradient(90deg, var(--frost), var(--ice3));
  -webkit-background-clip: text; background-clip: text; color: transparent; }
.sub { color: var(--muted); font-size: 13px; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 2px;
  color: var(--ice); margin-bottom: 12px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit,
  minmax(150px, 1fr)); gap: 12px; margin: 22px 0; }
.tile { background: linear-gradient(180deg, var(--panel2), var(--panel));
  border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.tile .n { font-size: 30px; font-weight: 700; color: var(--frost);
  font-variant-numeric: tabular-nums; }
.tile .l { color: var(--ink2); font-size: 12px; text-transform: uppercase;
  letter-spacing: 1px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit,
  minmax(340px, 1fr)); gap: 14px; }
section { background: var(--panel); border: 1px solid var(--line);
  border-radius: 10px; padding: 18px; overflow-x: auto; }
.bar-row { display: grid; grid-template-columns: 130px 1fr 40px;
  gap: 10px; align-items: center; margin: 7px 0; font-size: 13px; }
.bar-row .name { color: var(--ink2); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.bar { height: 10px; border-radius: 0 4px 4px 0;
  background: linear-gradient(90deg, var(--ice3), var(--ice)); }
.bar-row .v { color: var(--ink); font-variant-numeric: tabular-nums; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { text-align: left; color: var(--muted); font-weight: 600;
  padding: 4px 10px 8px 0; border-bottom: 1px solid var(--line); }
td { padding: 6px 10px 6px 0; border-bottom: 1px solid var(--line);
  color: var(--ink2); vertical-align: top; }
td.k, td b { color: var(--ink); }
ul { list-style: none; }
li { padding: 6px 0; border-bottom: 1px solid var(--line); font-size: 13px;
  color: var(--ink2); }
.tag { display: inline-block; background: var(--panel2);
  border: 1px solid var(--line); color: var(--ice); border-radius: 5px;
  padding: 0 7px; font-size: 11px; margin-right: 6px; }
.ok { color: var(--ok); } .warn { color: var(--warn); }
.fail { color: var(--fail); }
footer { color: var(--muted); font-size: 12px; margin-top: 20px; }
"""


def esc(s):
    return html.escape(str(s), quote=True)


def bar_rows(pairs):
    """Single-hue bars: name, bar scaled to max, value."""
    top = max((v for _, v in pairs), default=1) or 1
    rows = []
    for name, v in pairs:
        pct = max(4, round(100 * v / top))
        rows.append(
            f'<div class="bar-row"><span class="name" title="{esc(name)}">'
            f'{esc(name)}</span><div><div class="bar" '
            f'style="width:{pct}%"></div></div>'
            f'<span class="v">{v}</span></div>')
    return "\n".join(rows)


def gather(vault):
    meta = vault / "90_META"
    notes = load_json(meta / "INDEX.json", {"notes": []})["notes"]
    ledger = [l.lstrip("- ").strip() for l in
              (meta / "FAULT_LEDGER.md").read_text(encoding="utf-8")
              .splitlines() if l.startswith("- ")] \
        if (meta / "FAULT_LEDGER.md").exists() else []
    wf = load_json(meta / "experience" / "workflows.json", {})
    plugins = load_json(meta / "PLUGINS.json", {"plugins": []})["plugins"]
    graph = load_json(meta / "GRAPH.json", {"nodes": {}, "edges": []})
    by_proj, by_type = {}, {}
    for n in notes:
        by_proj[n["project"]] = by_proj.get(n["project"], 0) + 1
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    recent = sorted((n for n in notes if n.get("date")),
                    key=lambda n: n["date"], reverse=True)[:MAX_ROWS]
    return {"notes": notes, "ledger": ledger, "wf": wf, "plugins": plugins,
            "graph": graph, "by_proj": by_proj, "by_type": by_type,
            "recent": recent}


def render(d):
    scripts = sum(1 for p in d["plugins"] if p.get("kind") == "script")
    tiles = [(len(d["notes"]), "notes"), (len(d["ledger"]), "faults"),
             (d["by_type"].get("lesson", 0), "lessons"),
             (scripts or 14, "engines"),
             (len(d["graph"]["nodes"]), "graph nodes"),
             (len(d["graph"]["edges"]), "graph edges")]
    tile_html = "\n".join(
        f'<div class="tile"><div class="n">{n}</div>'
        f'<div class="l">{esc(l)}</div></div>' for n, l in tiles)

    proj = bar_rows(sorted(d["by_proj"].items(), key=lambda x: -x[1]))
    types = bar_rows(sorted(d["by_type"].items(), key=lambda x: -x[1]))

    faults = "\n".join(
        f"<li>{esc(f)}</li>" for f in d["ledger"][:MAX_ROWS]) \
        or "<li>none yet</li>"

    wf_rows = []
    for intent, e in sorted(d["wf"].items()):
        runs, ok = e.get("runs", 0), e.get("pass", 0)
        cls = "ok" if ok == runs else "warn" if ok else "fail"
        avg = e.get("seconds", 0) // max(1, runs)
        wf_rows.append(
            f'<tr><td class="k">{esc(intent)}</td>'
            f'<td><span class="{cls}">{ok}/{runs}</span></td>'
            f'<td>{e.get("retries", 0)}</td><td>{avg}s</td></tr>')
    wf_html = "\n".join(wf_rows) or \
        '<tr><td colspan="4">no closed traces harvested yet</td></tr>'

    recent = "\n".join(
        f'<li><span class="tag">{esc(n["type"])}</span>'
        f'<b>{esc(n["title"])}</b> '
        f'<span class="sub">{esc(n.get("date", ""))} · '
        f'{esc(n["path"])}</span></li>' for n in d["recent"]) \
        or "<li>vault is empty</li>"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ABSOLUTE ZERO — ICE dashboard</title>
<style>{CSS}</style></head><body>
<header><h1>ABSOLUTE ZERO</h1>
<span class="sub">agentic OS · ICE dashboard · generated {date.today()}
</span></header>
<div class="tiles">{tile_html}</div>
<div class="grid">
<section><h2>Notes by project</h2>{proj}</section>
<section><h2>Notes by type</h2>{types}</section>
<section><h2>Fault ledger</h2><ul>{faults}</ul></section>
<section><h2>Workflow stats (experience engine)</h2>
<table><tr><th>intent</th><th>pass</th><th>retries</th><th>avg</th></tr>
{wf_html}</table></section>
<section style="grid-column:1/-1"><h2>Recent notes</h2>
<ul>{recent}</ul></section>
</div>
<footer>stdlib only · zero dependencies · regenerate with
<b>python scripts/dashboard.py</b></footer>
</body></html>
"""


def build(vault=VAULT, out=None):
    out = out if out is not None else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(gather(vault)), encoding="utf-8")
    return out


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        meta = v / "90_META"
        meta.mkdir(parents=True)
        (meta / "INDEX.json").write_text(json.dumps({"notes": [
            {"path": "30_LESSONS/a.md", "type": "lesson", "project": "X",
             "tags": [], "title": "Fail <loud>", "summary": "s",
             "date": "2026-07-01"},
            {"path": "20_KNOWLEDGE/b.md", "type": "knowledge", "project": "Y",
             "tags": [], "title": "Nav", "summary": "s",
             "date": "2026-07-02"}]}), encoding="utf-8")
        (meta / "FAULT_LEDGER.md").write_text(
            "# L\n\n- [X][t] drift -> anchor\n", encoding="utf-8")
        (meta / "experience").mkdir()
        (meta / "experience" / "workflows.json").write_text(
            json.dumps({"bug_fix": {"runs": 2, "pass": 1, "retries": 1,
                                    "seconds": 120}}), encoding="utf-8")
        out = build(v, out=meta / "d.html")
        page = out.read_text(encoding="utf-8")
        assert "ABSOLUTE ZERO" in page
        assert "Fail &lt;loud&gt;" in page, "titles not HTML-escaped"
        assert "drift -&gt; anchor" in page, "ledger line missing"
        assert "1/2" in page, "workflow pass rate missing"
        assert page.count('class="tile"') == 6, "tile count drifted"
        assert "http" not in page.split("</style>")[1].split("<footer")[0] \
            .replace("https", ""), "external resource crept in"
        # empty vault still renders
        v2 = Path(td) / "empty"
        (v2 / "90_META").mkdir(parents=True)
        page2 = build(v2, out=v2 / "d.html").read_text(encoding="utf-8")
        assert "vault is empty" in page2
        assert re.search(r"no closed traces", page2)
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Render the ICE dashboard.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    out = build(out=Path(args.out) if args.out else None)
    print(f"dashboard -> {out}")


if __name__ == "__main__":
    main()
