#!/usr/bin/env python3
"""ABSOLUTE ZERO token profiler. Stdlib only.

V3 accountability: after a request, show where the tokens went. Parses a
compiled prompt from 90_META/prompts (newest by default), estimates
per-section prompt tokens, adds completion tokens (--completion file or
--completion-tokens N), plugin tokens saved (successful script-plugin runs
from plugin_stats.json, ~SAVED_PER_RUN LLM tokens each - ESTIMATE), cost
at --price-in/--price-out USD per 1M tokens, top consumers, and one
suggestion per oversized section. Report saved to 90_META/profile/.

  python scripts/profiler.py report
  python scripts/profiler.py report --prompt 90_META/prompts/X.md --completion-tokens 800
  python scripts/profiler.py --selftest
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import est_tokens, load_json, dump_json

VAULT = Path(__file__).resolve().parent.parent
PROMPTS = VAULT / "90_META" / "prompts"
STATS = VAULT / "90_META" / "plugin_stats.json"
PROFILE = VAULT / "90_META" / "profile"
SAVED_PER_RUN = 400  # ESTIMATE: LLM tokens one deterministic run replaces
PRICE_IN, PRICE_OUT = 3.0, 15.0  # USD per 1M tokens, override via flags


def parse_sections(text):
    """Split a compiled prompt on '## SECTION' headers -> {name: tokens}."""
    sections, name, buf = {}, "PREAMBLE", []
    for line in text.splitlines():
        if line.startswith("## "):
            if buf and "".join(buf).strip():
                sections[name] = est_tokens("\n".join(buf))
            name, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if buf and "".join(buf).strip():
        sections[name] = est_tokens("\n".join(buf))
    return sections


def plugin_savings(stats_path=STATS):
    stats = load_json(Path(stats_path), {})
    ok = sum(s.get("ok", 0) for s in stats.values())
    return ok * SAVED_PER_RUN, ok


def suggest(sections, total):
    out = []
    for name, tok in sections.items():
        if total and tok / total > 0.4:
            out.append(f"{name} is {100 * tok // total}% of the prompt - "
                       f"compress it or cut its budget share")
    if sections.get("EXAMPLES", 0) > 300:
        out.append("EXAMPLES over 300 tokens - one lesson is usually enough")
    if not out:
        out.append("no oversized section - budget is working")
    return out


def latest_prompt():
    files = sorted(PROMPTS.glob("*.md"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit("no compiled prompts in 90_META/prompts - "
                         "run promptc.py first or pass --prompt")
    return files[0]


def report(prompt=None, completion=None, completion_tokens=0,
           price_in=PRICE_IN, price_out=PRICE_OUT, out_dir=PROFILE,
           stats_path=STATS):
    p = Path(prompt) if prompt else latest_prompt()
    sections = parse_sections(p.read_text(encoding="utf-8"))
    prompt_tok = sum(sections.values())
    if completion:
        completion_tokens = est_tokens(
            Path(completion).read_text(encoding="utf-8"))
    saved, runs = plugin_savings(stats_path)
    cost = (prompt_tok * price_in + completion_tokens * price_out) / 1e6
    top = sorted(sections.items(), key=lambda kv: kv[1], reverse=True)
    rep = {"t": datetime.now().isoformat(timespec="seconds"),
           "prompt_file": str(p), "prompt_tokens": prompt_tok,
           "completion_tokens": completion_tokens,
           "total_tokens": prompt_tok + completion_tokens,
           "sections": sections,
           "plugin_tokens_saved_estimate": saved, "plugin_ok_runs": runs,
           "cost_usd_estimate": round(cost, 4),
           "suggestions": suggest(sections, prompt_tok)}
    out = Path(out_dir) / f"{p.stem}.json"
    dump_json(out, rep)
    print(f"prompt      {prompt_tok} tokens  ({p.name})")
    print(f"completion  {completion_tokens} tokens")
    print(f"total       {rep['total_tokens']} tokens  "
          f"~${rep['cost_usd_estimate']} (ESTIMATE)")
    print(f"saved       ~{saved} tokens lifetime via {runs} plugin runs "
          f"(ESTIMATE, {SAVED_PER_RUN}/run)")
    for name, tok in top[:3]:
        print(f"top         {name:<12} {tok}")
    for s in rep["suggestions"]:
        print(f"suggest     {s}")
    print(f"report      {out.relative_to(VAULT) if out.is_relative_to(VAULT) else out}")
    return rep


def selftest():
    import tempfile
    text = ("## LAW\n- pull not push\n\n## TASK\nfix the crash\n\n"
            "## CONTEXT\n" + "x" * 4000 + "\n\n## EXAMPLES\n" + "y" * 1600)
    secs = parse_sections(text)
    assert set(secs) == {"LAW", "TASK", "CONTEXT", "EXAMPLES"}
    assert secs["CONTEXT"] >= 1000
    sugg = suggest(secs, sum(secs.values()))
    assert any("CONTEXT" in s for s in sugg)      # 40% rule fires
    assert any("EXAMPLES" in s for s in sugg)     # 300-token rule fires
    balanced = {"TASK": 10, "LAW": 10, "CONTEXT": 10}
    assert suggest(balanced, 30)[0].startswith("no oversized")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        pf = td / "2026-07-12-test.md"
        pf.write_text(text, encoding="utf-8")
        st = td / "stats.json"
        dump_json(st, {"indexer": {"ok": 3, "runs": 3}})
        rep = report(prompt=pf, completion_tokens=500, out_dir=td,
                     stats_path=st)
        assert rep["completion_tokens"] == 500
        assert rep["plugin_tokens_saved_estimate"] == 3 * SAVED_PER_RUN
        assert (td / "2026-07-12-test.json").exists()
        assert rep["total_tokens"] == rep["prompt_tokens"] + 500
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Token profiler.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("report")
    r.add_argument("--prompt", default=None)
    r.add_argument("--completion", default=None)
    r.add_argument("--completion-tokens", type=int, default=0)
    r.add_argument("--price-in", type=float, default=PRICE_IN)
    r.add_argument("--price-out", type=float, default=PRICE_OUT)
    args = ap.parse_args()
    if args.selftest:
        selftest()
    elif args.cmd == "report":
        report(args.prompt, args.completion, args.completion_tokens,
               args.price_in, args.price_out)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
