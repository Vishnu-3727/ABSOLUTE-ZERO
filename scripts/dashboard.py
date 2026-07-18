#!/usr/bin/env python3
"""ABSOLUTE ZERO dashboard renderer. Stdlib only.

Renders 90_META/dashboard.html - a self-contained full-screen vault
terminal: an Obsidian-style force-directed graph of GRAPH.json in the
center (canvas, drag/zoom/hover, type-filter legend), system vitals +
fault ledger + workflow stats on the left rail, a command deck (click =
copy command) + run output on the right rail, live clock in the top bar.
Pure read: INDEX.json, FAULT_LEDGER.md, workflows.json, PLUGINS.json,
GRAPH.json. Open in any browser; no network, no dependencies.

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

# Node-type palette: validated categorical set (dataviz six checks, dark
# surface #060d18 - lightness band, chroma, CVD >= 12, contrast all PASS).
# Labels/ink stay in text tokens; these hues mark identity only.
TYPE_COLORS = {
    "function":   "#4d87c7",  # most common -> most recessive
    "file":       "#0d94d2",
    "class":      "#0d94d2",  # merged with file: same code-unit family
    "library":    "#9085e9",
    "experience": "#0ea371",
    "skill":      "#d55181",
    "project":    "#c98500",
    "user":       "#e8f4ff",  # single highlight node, not a series
}

CSS = """
:root {
  --bg: #060d18; --panel: #0a1626; --panel2: #0e1e33;
  --ink: #e8f4fd; --ink2: #9db8d2; --muted: #567394;
  --ice: #7dd3fc; --frost: #a5f3fc; --line: #14293f;
  --warn: #c98500; --fail: #e66767; --ok: #0ea371;
}
* { box-sizing: border-box; margin: 0; }
html, body { height: 100%; overflow: hidden; }
body { background: var(--bg); color: var(--ink);
  font: 12px/1.5 "Cascadia Code", Consolas, monospace; }
#app { display: grid; height: 100vh;
  grid-template-rows: 46px 1fr;
  grid-template-columns: 300px 1fr 300px; }
/* top bar */
#top { grid-column: 1 / -1; display: flex; align-items: center;
  gap: 18px; padding: 0 16px; border-bottom: 1px solid var(--line);
  background: var(--panel); }
#top h1 { font-size: 15px; letter-spacing: 5px; font-weight: 700;
  color: var(--frost); white-space: nowrap; }
#top .sub { color: var(--muted); font-size: 10px; letter-spacing: 1px; }
#top .dots { display: flex; gap: 16px; margin-left: auto;
  font-size: 10px; letter-spacing: 1px; color: var(--ink2); }
.dot::before { content: "\\25CF "; }
.dot.on { color: var(--ok); } .dot.ice { color: var(--ice); }
#clock { font-size: 20px; color: var(--frost); font-weight: 700;
  font-variant-numeric: tabular-nums; letter-spacing: 2px; }
/* rails */
.rail { display: flex; flex-direction: column; overflow-y: auto;
  background: var(--panel); border-right: 1px solid var(--line);
  padding: 12px; gap: 12px; }
#right { border-right: 0; border-left: 1px solid var(--line); }
.box { border: 1px solid var(--line); background: var(--panel2);
  padding: 10px 12px; }
h2 { font-size: 10px; letter-spacing: 2px; color: var(--ice);
  text-transform: uppercase; margin-bottom: 8px; display: flex; }
h2 .r { margin-left: auto; color: var(--muted); }
.vitals { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.vt .n { font-size: 24px; font-weight: 700; color: var(--frost);
  font-variant-numeric: tabular-nums; }
.vt .l { font-size: 9px; letter-spacing: 1px; color: var(--muted);
  text-transform: uppercase; }
.ledger { max-height: 230px; overflow-y: auto; }
.ledger li { list-style: none; padding: 6px 0; color: var(--ink2);
  font-size: 10px; border-bottom: 1px solid var(--line); }
table { border-collapse: collapse; width: 100%; font-size: 10px; }
th { text-align: left; color: var(--muted); font-weight: 600;
  padding: 2px 6px 5px 0; border-bottom: 1px solid var(--line); }
td { padding: 4px 6px 4px 0; border-bottom: 1px solid var(--line);
  color: var(--ink2); }
td.k { color: var(--ink); }
.ok { color: var(--ok); } .warn { color: var(--warn); }
.fail { color: var(--fail); }
/* graph stage */
#stage { position: relative; overflow: hidden; }
#graph { position: absolute; inset: 0; width: 100%; height: 100%;
  cursor: grab; }
#legend { position: absolute; top: 10px; left: 12px; display: flex;
  flex-wrap: wrap; gap: 6px; max-width: 70%; }
.chip { display: flex; align-items: center; gap: 5px; font-size: 9px;
  letter-spacing: 1px; color: var(--ink2); text-transform: uppercase;
  border: 1px solid var(--line); background: rgba(10,22,38,.8);
  padding: 3px 8px; cursor: pointer; user-select: none; }
.chip.off { opacity: .3; }
.chip i { width: 8px; height: 8px; border-radius: 50%; }
#hero { position: absolute; bottom: 14px; left: 0; right: 0;
  text-align: center; pointer-events: none; }
#hero .n { font-size: 44px; font-weight: 700; color: var(--frost);
  letter-spacing: 6px; text-shadow: 0 0 24px rgba(125,211,252,.35);
  font-variant-numeric: tabular-nums; }
#hero .l { font-size: 10px; letter-spacing: 4px; color: var(--muted);
  text-transform: uppercase; }
#hint { position: absolute; bottom: 8px; right: 12px;
  color: var(--muted); font-size: 9px; letter-spacing: 1px; }
/* command deck */
.deck { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.deck button { font: inherit; font-size: 10px; letter-spacing: 1px;
  color: var(--ice); background: var(--panel2);
  border: 1px solid var(--line); padding: 8px 4px; cursor: pointer;
  text-transform: uppercase; }
.deck button:hover { background: var(--line); color: var(--frost); }
#out { flex: 1; min-height: 120px; overflow-y: auto; white-space:
  pre-wrap; word-break: break-word; color: var(--ink2); font-size: 10px;
  line-height: 1.6; }
#out .p { color: var(--ok); }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: var(--line); }
"""

# Command deck: (label, server command name, needs an argument). The name
# is a key into server.ALLOWED - the page never builds a command line, it
# asks the server to run one it already trusts. `needs_arg` drives the
# input box, so a command that requires text cannot be fired empty.
DECK = [
    ("task", "task", True),
    ("recall", "recall", True),
    ("cases", "cases", True),
    ("skills", "skills", True),
    ("brief", "brief", True),
    ("agents", "agents", True),
    ("index", "index", False),
    ("graph", "graph", False),
    ("review", "review", False),
    ("verify", "verify", False),
    ("profile", "profile", False),
    ("harvest", "harvest", False),
]

JS = """
const D = window.VAULT_DATA;
/* clock */
const clock = document.getElementById('clock');
setInterval(() => {
  clock.textContent = new Date().toTimeString().slice(0, 8);
}, 250);
/* command deck + output */
const out = document.getElementById('out');
function log(msg, cls) {
  const el = document.createElement('div');
  if (cls) el.className = cls;
  el.textContent = msg;
  out.prepend(el);
}
/* The deck executes through the server that is showing this page. Opened
   as a bare file:// there is no server, so it says so instead of looking
   broken - the page is still a valid static snapshot. */
const LIVE = location.protocol !== 'file:';
const argBox = document.getElementById('arg');
let busy = false;
async function run(cmd, arg, flags) {
  if (!LIVE) {
    log('> ' + cmd + (arg ? ' ' + arg : ''), 'p');
    log('static snapshot - run "python scripts/server.py" for a live deck');
    return;
  }
  if (busy) { log('a command is already running', 'warn'); return; }
  busy = true;
  log('> ' + cmd + (arg ? ' ' + arg : ''), 'p');
  try {
    const r = await fetch('/run', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({cmd: cmd, arg: arg || '', flags: flags || {}})
    });
    const res = await r.json();
    log(res.output, res.ok ? '' : 'fail');
    if (res.ok && REFRESHERS.has(cmd)) {
      log('state changed - reloading board...');
      setTimeout(() => location.reload(), 900);
    }
  } catch (e) {
    log('server unreachable: ' + e, 'fail');
  } finally { busy = false; }
}
/* commands that change what the board displays; reload after them */
const REFRESHERS = new Set(['task', 'close', 'index', 'graph', 'harvest',
                            'new', 'agents']);
document.querySelectorAll('.deck button').forEach(b => {
  b.onclick = () => {
    const needsArg = b.dataset.arg === '1';
    const arg = (argBox && argBox.value || '').trim();
    if (needsArg && !arg) {
      log(b.dataset.cmd + ' needs text in the box above', 'warn');
      argBox && argBox.focus();
      return;
    }
    run(b.dataset.cmd, needsArg ? arg : '');
  };
});
/* close an open trace straight from the board: the UI can finish the work
   it starts, which is the whole point of a control surface */
document.querySelectorAll('.tclose').forEach(b => {
  b.onclick = () => run('close', '', {
    trace: '90_META/traces/' + b.dataset.file,
    result: b.dataset.result,
    summary: 'closed from the vault terminal'
  });
});
/* ---- force graph (ponytail: naive O(n^2) repulsion; quadtree if the
   vault ever grows past ~1500 nodes) ---- */
const canvas = document.getElementById('graph');
const ctx = canvas.getContext('2d');
const N = D.nodes, E = D.edges, COL = D.colors;
const hidden = new Set();
let W, H, dpr = window.devicePixelRatio || 1;
function resize() {
  const r = canvas.parentElement.getBoundingClientRect();
  W = r.width; H = r.height;
  canvas.width = W * dpr; canvas.height = H * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
resize(); window.addEventListener('resize', resize);
/* init positions: golden-angle spiral, degree-heavy nodes inward */
const deg = new Array(N.length).fill(0);
E.forEach(([a, b]) => { deg[a]++; deg[b]++; });
const order = N.map((_, i) => i).sort((a, b) => deg[b] - deg[a]);
order.forEach((idx, rank) => {
  const a = rank * 2.39996, r = 14 * Math.sqrt(rank + 1);
  N[idx].x = r * Math.cos(a); N[idx].y = r * Math.sin(a);
  N[idx].vx = 0; N[idx].vy = 0;
});
const adj = N.map(() => []);
E.forEach(([a, b]) => { adj[a].push(b); adj[b].push(a); });
let alpha = 1, cam = { x: 0, y: 0, z: 0.72 }, hover = -1, dragN = -1;
function vis(i) { return !hidden.has(N[i].t); }
function radius(i) { return Math.min(13, 2.2 + Math.sqrt(deg[i]) * 1.15); }
function step() {
  if (alpha < 0.003) return;
  const k = 900 * alpha;
  for (let i = 0; i < N.length; i++) {
    if (!vis(i)) continue;
    const a = N[i];
    for (let j = i + 1; j < N.length; j++) {
      if (!vis(j)) continue;
      const b = N[j];
      let dx = a.x - b.x, dy = a.y - b.y;
      let d2 = dx * dx + dy * dy + 0.01;
      if (d2 > 90000) continue;
      const f = k / d2;
      dx *= f; dy *= f;
      a.vx += dx; a.vy += dy; b.vx -= dx; b.vy -= dy;
    }
    a.vx -= a.x * 0.012 * alpha; a.vy -= a.y * 0.012 * alpha;
  }
  E.forEach(([ai, bi]) => {
    if (!vis(ai) || !vis(bi)) return;
    const a = N[ai], b = N[bi];
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) + 0.01;
    const f = (d - 46) * 0.02 * alpha / d;
    a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
  });
  N.forEach((n, i) => {
    if (i === dragN) { n.vx = 0; n.vy = 0; return; }
    n.vx *= 0.85; n.vy *= 0.85; n.x += n.vx; n.y += n.vy;
  });
  alpha *= 0.996;
}
function draw() {
  ctx.clearRect(0, 0, W, H);
  const g = ctx.createRadialGradient(W / 2, H / 2, 60, W / 2, H / 2,
                                     Math.max(W, H) * 0.7);
  g.addColorStop(0, 'rgba(14,40,70,.55)');
  g.addColorStop(1, 'rgba(6,13,24,0)');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  ctx.save();
  ctx.translate(W / 2 + cam.x, H / 2 + cam.y); ctx.scale(cam.z, cam.z);
  const hi = hover >= 0 ? new Set([hover, ...adj[hover]]) : null;
  ctx.lineWidth = 1 / cam.z;
  E.forEach(([a, b]) => {
    if (!vis(a) || !vis(b)) return;
    const lit = hi && (a === hover || b === hover);
    ctx.strokeStyle = lit ? 'rgba(165,243,252,.7)'
                          : 'rgba(125,211,252,.10)';
    ctx.beginPath(); ctx.moveTo(N[a].x, N[a].y);
    ctx.lineTo(N[b].x, N[b].y); ctx.stroke();
  });
  N.forEach((n, i) => {
    if (!vis(i)) return;
    const r = radius(i), dim = hi && !hi.has(i);
    ctx.globalAlpha = dim ? 0.15 : 1;
    ctx.fillStyle = 'rgba(125,211,252,.16)';
    ctx.beginPath(); ctx.arc(n.x, n.y, r * 2.1, 0, 7); ctx.fill();
    ctx.fillStyle = COL[n.t] || '#7dd3fc';
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 7); ctx.fill();
    ctx.globalAlpha = 1;
  });
  ctx.fillStyle = '#e8f4fd';
  ctx.font = `${11 / cam.z}px Consolas, monospace`;
  ctx.textAlign = 'center';
  N.forEach((n, i) => {
    if (!vis(i)) return;
    const always = n.t === 'project' || n.t === 'user' || deg[i] >= 22;
    if (i === hover || (always && (!hi || hi.has(i))))
      ctx.fillText(n.n, n.x, n.y - radius(i) - 5 / cam.z);
  });
  ctx.restore();
}
(function loop() { step(); draw(); requestAnimationFrame(loop); })();
/* interaction */
function pick(mx, my) {
  const x = (mx - W / 2 - cam.x) / cam.z, y = (my - H / 2 - cam.y) / cam.z;
  for (let i = N.length - 1; i >= 0; i--) {
    if (!vis(i)) continue;
    const dx = N[i].x - x, dy = N[i].y - y, r = radius(i) + 4;
    if (dx * dx + dy * dy < r * r) return i;
  }
  return -1;
}
let panning = false, px = 0, py = 0;
canvas.onmousedown = e => {
  const i = pick(e.offsetX, e.offsetY);
  if (i >= 0) { dragN = i; alpha = Math.max(alpha, 0.25); }
  else { panning = true; }
  px = e.offsetX; py = e.offsetY;
};
canvas.onmousemove = e => {
  if (dragN >= 0) {
    N[dragN].x += (e.offsetX - px) / cam.z;
    N[dragN].y += (e.offsetY - py) / cam.z;
    alpha = Math.max(alpha, 0.12);
  } else if (panning) {
    cam.x += e.offsetX - px; cam.y += e.offsetY - py;
  } else {
    hover = pick(e.offsetX, e.offsetY);
    canvas.style.cursor = hover >= 0 ? 'pointer' : 'grab';
  }
  px = e.offsetX; py = e.offsetY;
};
window.onmouseup = () => {
  if (dragN >= 0 && Math.abs(N[dragN].vx) < 99) {
    const n = N[dragN];
    log(`[${n.t}] ${n.n}` + (n.m ? `\\n${n.m}` : '') +
        `\\nlinks: ${deg[N.indexOf(n)]}`);
  }
  dragN = -1; panning = false;
};
canvas.onwheel = e => {
  e.preventDefault();
  const f = e.deltaY < 0 ? 1.12 : 0.89;
  cam.z = Math.min(6, Math.max(0.25, cam.z * f));
};
/* legend type filter */
document.querySelectorAll('.chip').forEach(c => {
  c.onclick = () => {
    const t = c.dataset.t;
    hidden.has(t) ? hidden.delete(t) : hidden.add(t);
    c.classList.toggle('off');
    alpha = Math.max(alpha, 0.3);
  };
});
"""


def esc(s):
    return html.escape(str(s), quote=True)


def graph_payload(graph):
    """GRAPH.json -> compact embed: nodes [{n,t,m,x..}], edges [i,j]."""
    ids = list(graph["nodes"].keys())
    pos = {nid: i for i, nid in enumerate(ids)}
    nodes = []
    for nid in ids:
        n = graph["nodes"][nid]
        t = n["type"] if n["type"] in TYPE_COLORS else "function"
        meta = n.get("meta", {})
        m = meta.get("path") or meta.get("summary") or ""
        nodes.append({"n": n["name"], "t": t, "m": str(m)[:120]})
    edges = [[pos[a], pos[b]] for a, b, _ in graph["edges"]
             if a in pos and b in pos]
    return {"nodes": nodes, "edges": edges, "colors": TYPE_COLORS}


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
    by_type = {}
    for n in notes:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    recent = sorted((n for n in notes if n.get("date")),
                    key=lambda n: n["date"], reverse=True)[:MAX_ROWS]
    # Live runtime state. The board used to read five static artifacts and
    # show nothing of what the OS was actually doing: open work, project
    # cases and agent runs were invisible in the one place meant to show
    # the system.
    traces = []
    for p in sorted((meta / "traces").glob("*.json"), reverse=True):
        t = load_json(p, None)
        if not t:
            continue
        states = [x["state"] for x in t.get("transitions", [])]
        traces.append({"id": t.get("id", p.stem), "file": p.name,
                       "intent": t.get("intent", "?"),
                       "project": t.get("project", ""),
                       "result": t.get("result"),
                       "state": states[-1] if states else "?"})
    cases = sorted(load_json(meta / "experience" / "cases.json", {}).values(),
                   key=lambda c: c.get("date", ""), reverse=True)
    runs = []
    for p in sorted((meta / "runs").glob("*.json"), reverse=True)[:MAX_ROWS]:
        r = load_json(p, None)
        if r:
            runs.append({"id": r.get("id", p.stem),
                         "verdict": r.get("verdict", "?"),
                         "nodes": len(r.get("workflow", [])),
                         "parallel": r.get("max_parallel", 0)})
    return {"notes": notes, "ledger": ledger, "wf": wf, "plugins": plugins,
            "graph": graph, "by_type": by_type, "recent": recent,
            "traces": traces, "cases": cases, "runs": runs}


def render(d):
    scripts = sum(1 for p in d["plugins"] if p.get("kind") == "script")
    vitals = [(len(d["notes"]), "notes"), (len(d["ledger"]), "faults"),
              (d["by_type"].get("lesson", 0), "lessons"),
              (scripts or 17, "engines"),
              (len(d["traces"]), "traces"), (len(d["cases"]), "cases")]
    vit = "\n".join(f'<div class="vt"><div class="n">{n}</div>'
                    f'<div class="l">{esc(l)}</div></div>'
                    for n, l in vitals)
    faults = "\n".join(f"<li>{esc(f)}</li>"
                       for f in d["ledger"][:MAX_ROWS]) or "<li>none yet</li>"
    wf_rows = []
    for intent, e in sorted(d["wf"].items()):
        runs, ok = e.get("runs", 0), e.get("pass", 0)
        cls = "ok" if ok == runs else "warn" if ok else "fail"
        avg = e.get("seconds", 0) // max(1, runs)
        wf_rows.append(f'<tr><td class="k">{esc(intent)}</td>'
                       f'<td><span class="{cls}">{ok}/{runs}</span></td>'
                       f'<td>{e.get("retries", 0)}</td><td>{avg}s</td></tr>')
    wf_html = "\n".join(wf_rows) or \
        '<tr><td colspan="4">no closed traces harvested yet</td></tr>'

    pay = graph_payload(d["graph"])
    counts = {}
    for n in pay["nodes"]:
        counts[n["t"]] = counts.get(n["t"], 0) + 1
    legend = "\n".join(
        f'<span class="chip" data-t="{esc(t)}">'
        f'<i style="background:{TYPE_COLORS[t]}"></i>{esc(t)} {c}</span>'
        for t, c in sorted(counts.items(), key=lambda x: -x[1]))
    deck = "\n".join(
        f'<button data-cmd="{esc(cmd)}" data-arg="{1 if need else 0}"'
        f'{" class=\"needs\"" if need else ""}>{esc(label)}</button>'
        for label, cmd, need in DECK)

    open_t = [t for t in d["traces"] if t["result"] is None]
    trace_rows = "\n".join(
        f'<tr><td class="k">{esc(t["id"][:34])}</td>'
        f'<td>{esc(t["state"])}</td>'
        f'<td><button class="tclose" data-file="{esc(t["file"])}"'
        f' data-result="pass">pass</button>'
        f'<button class="tclose" data-file="{esc(t["file"])}"'
        f' data-result="fail">fail</button></td></tr>'
        for t in open_t[:MAX_ROWS]) or \
        '<tr><td colspan="3">no open work</td></tr>'
    case_rows = "\n".join(
        f'<tr><td class="k">{esc(c.get("project", "?"))}</td>'
        f'<td>{len(c.get("decisions", []))}</td>'
        f'<td>{len(c.get("faults", []))}</td>'
        f'<td>{len(c.get("lessons", []))}</td></tr>'
        for c in d["cases"][:MAX_ROWS]) or \
        '<tr><td colspan="4">no projects closed into cases yet</td></tr>'
    run_rows = "\n".join(
        f'<tr><td class="k">{esc(r["id"][:30])}</td>'
        f'<td><span class="{"ok" if r["verdict"] == "pass" else "fail"}">'
        f'{esc(r["verdict"])}</span></td>'
        f'<td>{r["nodes"]}</td><td>x{r["parallel"]}</td></tr>'
        for r in d["runs"][:5]) or \
        '<tr><td colspan="4">no agent runs</td></tr>'
    closed = sum(1 for t in d["traces"] if t["result"] == "pass")
    recent = "\n".join(f'[{n["type"]}] {n["title"]} ({n.get("date", "")})'
                       for n in d["recent"]) or "vault is empty"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ABSOLUTE ZERO — vault terminal</title>
<style>{CSS}</style></head><body>
<div id="app">
<div id="top"><h1>&#10052; ABSOLUTE ZERO</h1>
<span class="sub">VAULT TERMINAL &middot; {date.today()}</span>
<div class="dots"><span class="dot on">CORE ONLINE</span>
<span class="dot ice">GRAPH {len(pay["nodes"])} / {len(pay["edges"])}</span>
<span class="dot ice">ENGINES {scripts or 17}</span></div>
<div id="clock">--:--:--</div></div>

<div class="rail" id="left">
<div class="box"><h2>system vitals</h2>
<div class="vitals">{vit}</div></div>
<div class="box"><h2>fault ledger
<span class="r">{len(d["ledger"])}</span></h2>
<ul class="ledger">{faults}</ul></div>
<div class="box"><h2>workflow stats</h2>
<table><tr><th>intent</th><th>pass</th><th>retry</th><th>avg</th></tr>
{wf_html}</table></div>
<div class="box"><h2>project cases
<span class="r">{len(d["cases"])}</span></h2>
<table><tr><th>project</th><th>dec</th><th>faults</th><th>lessons</th></tr>
{case_rows}</table></div>
<div class="box"><h2>agent runs</h2>
<table><tr><th>run</th><th>verdict</th><th>nodes</th><th>par</th></tr>
{run_rows}</table></div>
</div>

<div id="stage">
<canvas id="graph"></canvas>
<div id="legend">{legend}</div>
<div id="hint">drag node &middot; drag space to pan &middot; wheel zoom
&middot; chip filters type</div>
<div id="hero"><div class="n">{len(d["notes"])}</div>
<div class="l">notes indexed</div></div>
</div>

<div class="rail" id="right">
<div class="box"><h2>open work
<span class="r">{len(open_t)}</span></h2>
<table><tr><th>trace</th><th>state</th><th>close</th></tr>
{trace_rows}</table></div>
<div class="box"><h2>command deck</h2>
<input id="arg" placeholder="request / query for the marked commands">
<div class="deck">{deck}</div></div>
<div class="box" style="flex:1;display:flex;flex-direction:column">
<h2>run output</h2>
<div id="out">READY
click a node for details; a command to run it

RECENT NOTES
{esc(recent)}</div></div>
</div>
</div>
<script>window.VAULT_DATA = {json.dumps(pay, separators=(",", ":"))};
</script>
<script>{JS}</script>
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
        (meta / "GRAPH.json").write_text(json.dumps({
            "nodes": {"file:a": {"type": "file", "name": "a",
                                 "meta": {"path": "scripts/a.py"}},
                      "function:a.f": {"type": "function", "name": "a.f",
                                       "meta": {}},
                      "weird:x": {"type": "weird", "name": "x", "meta": {}}},
            "edges": [["file:a", "function:a.f", "related_to"],
                      ["file:a", "ghost:missing", "calls"]]}),
            encoding="utf-8")
        out = build(v, out=meta / "d.html")
        page = out.read_text(encoding="utf-8")
        assert "ABSOLUTE ZERO" in page
        assert "Fail &lt;loud&gt;" in page, "titles not HTML-escaped"
        assert "drift -&gt; anchor" in page, "ledger line missing"
        assert "1/2" in page, "workflow pass rate missing"
        pay = json.loads(page.split("window.VAULT_DATA = ")[1]
                         .split(";\n</script>")[0])
        assert len(pay["nodes"]) == 3, "graph nodes not embedded"
        assert pay["edges"] == [[0, 1]], "dangling edge not dropped"
        assert pay["nodes"][2]["t"] == "function", \
            "unknown type not mapped to fallback color"
        assert "command deck" in page.lower()
        assert "http" not in page.split("</style>")[1] \
            .replace("https", ""), "external resource crept in"
        # empty vault still renders
        v2 = Path(td) / "empty"
        (v2 / "90_META").mkdir(parents=True)
        page2 = build(v2, out=v2 / "d.html").read_text(encoding="utf-8")
        assert "vault is empty" in page2
        assert re.search(r"no closed traces", page2)
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Render the vault terminal.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    out = build(out=Path(args.out) if args.out else None)
    print(f"dashboard -> {out}")


if __name__ == "__main__":
    main()
