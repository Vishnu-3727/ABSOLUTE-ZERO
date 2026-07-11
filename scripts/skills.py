#!/usr/bin/env python3
"""ABSOLUTE ZERO skill discovery engine. Stdlib only.

Determines which skills should be loaded for a request, in what order.
Skills = vault commands (.claude/commands/*.md) + external plugin skills
(~/.claude/plugins SKILL.md). Matching runs in two spaces: surface keywords
(stemmed jaccard vs the skill text) and capability space (request+intent
mapped through the plugin engine's vocabulary - the honest stdlib version
of semantic matching), plus difflib similarity and a history boost.
Selected skills pull their dependencies, conflicts are resolved (explicit
pairs + subsumption), and the final chain is phase-ordered:
wake -> retrieve/orchestrate -> work -> persist. Manifest (the automatic-
loading contract) -> 90_META/skills/last_discovery.json. Spec: SKILLS.md.

  python scripts/skills.py discover "research vision landing params"
  python scripts/skills.py discover "..." --history chat.txt --json
  python scripts/skills.py --selftest
"""
import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchestrator import classify, words_of
from plugins import caps_from_text, INTENT_CAPS
from context import STOP
from promptc import stem

VAULT = Path(__file__).resolve().parent.parent
MANIFEST = VAULT / "90_META" / "skills" / "last_discovery.json"
MIN_CONF, TOP_N = 0.15, 6
# Execution phases: chain order regardless of confidence.
PHASE = {"wake": 0, "task": 1, "recall": 1, "research": 2, "review": 2,
         "predict": 2, "sleep": 9}
DEFAULT_PHASE = 2
# Skills that must not both run; keep the higher-confidence one.
CONFLICTS = [("wake", "sleep")]
# Superset skills: if the left is selected, the right adds nothing.
SUBSUMES = {"task": ["recall"]}


def norm(text):
    return {stem(w) for w in words_of(text)} - STOP


def scan_skills(vault, home=None):
    """Vault commands + external plugin skills, with their text."""
    out = []
    for p in sorted((vault / ".claude" / "commands").glob("*.md")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        out.append({"name": p.stem, "invoke": f"/{p.stem}", "origin": "vault",
                    "text": (m.group(1) if m else "") + " " + text,
                    "deps": sorted({d for d in re.findall(r"/(\w+)", text)
                                    if d != p.stem
                                    and (vault / ".claude" / "commands" /
                                         f"{d}.md").exists()})})
    cache = Path(home or Path.home()) / ".claude" / "plugins" / "cache"
    seen = {s["name"] for s in out}
    if cache.is_dir():
        for sk in sorted(cache.rglob("SKILL.md")):
            name = sk.parent.name
            if name in seen:
                continue
            seen.add(name)
            head = sk.read_text(encoding="utf-8", errors="ignore")[:500]
            out.append({"name": name, "invoke": f"skill:{name}",
                        "origin": "external", "text": head, "deps": []})
    return out


def score_skill(skill, request, intent, hist_words):
    qw = norm(request)
    sw = norm(skill["text"])
    kw = len(qw & sw) / len(qw) if qw else 0            # keyword match
    need = set(INTENT_CAPS.get(intent, [])) | set(caps_from_text(request))
    have = set(caps_from_text(skill["text"]))
    sem = len(need & have) / len(need) if need else 0    # capability space
    sem = max(sem, SequenceMatcher(None, request.lower(),
                                   skill["text"][:200].lower()).ratio())
    hist = 0.15 if hist_words & (norm(skill["name"]) | sw) else 0
    local = 0.05 if skill["origin"] == "vault" else 0
    return round(min(1.0, 0.35 * kw + 0.45 * sem + hist + local), 2)


def discover(request, history=None, vault=VAULT, home=None, quiet=False,
             manifest=None):
    intent = classify(request)["intent"]
    hist_words = set()
    if history:
        lines = Path(history).read_text(encoding="utf-8",
                                        errors="ignore").splitlines()
        hist_words = norm(" ".join(lines[-30:]))
    skills = scan_skills(vault, home)
    scored = [(score_skill(s, request, intent, hist_words), s)
              for s in skills]
    picked = sorted([x for x in scored if x[0] >= MIN_CONF],
                    key=lambda x: x[0], reverse=True)[:TOP_N]
    chosen = {s["name"]: {"skill": s, "conf": c, "reason": "matched"}
              for c, s in picked}

    # dependency matching: selected skills pull what they reference
    for name in list(chosen):
        for dep in chosen[name]["skill"]["deps"]:
            if dep not in chosen:
                depsk = next((s for s in skills if s["name"] == dep), None)
                if depsk:
                    chosen[dep] = {"skill": depsk,
                                   "conf": round(chosen[name]["conf"] * 0.8, 2),
                                   "reason": f"dependency of /{name}"}

    # conflict detection: explicit pairs, keep higher confidence
    conflicts = []
    for a, b in CONFLICTS:
        if a in chosen and b in chosen:
            drop = a if chosen[a]["conf"] < chosen[b]["conf"] else b
            keep = b if drop == a else a
            conflicts.append(f"/{a} vs /{b}: kept /{keep} "
                             f"({chosen[keep]['conf']}), dropped /{drop}")
            del chosen[drop]
    # subsumption: a superset skill makes the subset redundant
    for sup, subs in SUBSUMES.items():
        for sub in subs:
            if sup in chosen and sub in chosen:
                conflicts.append(f"/{sub} subsumed by /{sup}")
                del chosen[sub]

    # skill chaining: phase order, then confidence
    order = sorted(chosen.values(),
                   key=lambda e: (PHASE.get(e["skill"]["name"],
                                            DEFAULT_PHASE), -e["conf"]))
    result = {"request": request, "intent": intent,
              "skills": [{"invoke": e["skill"]["invoke"],
                          "name": e["skill"]["name"],
                          "confidence": e["conf"], "reason": e["reason"],
                          "origin": e["skill"]["origin"]} for e in order],
              "conflicts": conflicts}
    m = manifest if manifest is not None else MANIFEST
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    if not quiet:
        print(f"intent      {intent}")
        print("LOAD (in order)")
        for s in result["skills"]:
            print(f"  {s['confidence']:>5}  {s['invoke']:<24} "
                  f"{s['origin']:<9} {s['reason']}")
        if not result["skills"]:
            print("  none above threshold - proceed bare")
        for c in conflicts:
            print(f"CONFLICT    {c}")
        print(f"manifest    {m.relative_to(vault) if m.is_relative_to(vault) else m}")
    return result


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        cmd = v / ".claude" / "commands"
        cmd.mkdir(parents=True)
        def mk(name, desc, body=""):
            (cmd / f"{name}.md").write_text(
                f"---\ndescription: {desc}\n---\n{body}\n", encoding="utf-8")
        mk("wake", "session start briefing from vault memory")
        mk("sleep", "session end - write logs, reindex, commit")
        mk("recall", "pull vault memory by topic tags query search")
        mk("research", "web research summarize sources into notes",
           "then /recall related topics")
        mk("task", "route request through workflow orchestrator pipeline",
           "includes /recall and ends reminding /sleep")
        nohome = v / "nohome"
        r = discover("research vision landing params on the web",
                     vault=v, home=nohome, quiet=True,
                     manifest=v / "m.json")
        names = [s["name"] for s in r["skills"]]
        assert names and names[0] != "sleep", names
        assert "research" in names, names
        top_research = next(s for s in r["skills"] if s["name"] == "research")
        assert top_research["confidence"] >= 0.15
        # dependency: research references /recall -> pulled unless subsumed
        assert "recall" in names or any("subsumed" in c
                                        for c in r["conflicts"]), (names,
                                                                   r["conflicts"])
        # chaining: sleep (phase 9) last if present
        if "sleep" in names:
            assert names[-1] == "sleep", names
        # conflict: craft request matching wake and sleep
        r2 = discover("session start briefing and session end commit logs",
                      vault=v, home=nohome, quiet=True,
                      manifest=v / "m2.json")
        n2 = [s["name"] for s in r2["skills"]]
        assert not ("wake" in n2 and "sleep" in n2), n2
        assert any("kept" in c for c in r2["conflicts"]), r2["conflicts"]
        # subsumption: task + recall both matched -> recall dropped
        r3 = discover("route this task through the orchestrator pipeline "
                      "and pull vault memory by tags", vault=v, home=nohome,
                      quiet=True, manifest=v / "m3.json")
        n3 = [s["name"] for s in r3["skills"]]
        if "task" in n3:
            assert "recall" not in n3, n3
        # confidence bounded
        assert all(0 <= s["confidence"] <= 1 for s in r["skills"])
        # history boost lifts a skill
        h = v / "h.txt"
        h.write_text("we were doing web research yesterday\n",
                     encoding="utf-8")
        rh = discover("continue where we left off", history=h, vault=v,
                      home=nohome, quiet=True, manifest=v / "m4.json")
        assert any(s["name"] == "research" for s in rh["skills"]), \
            rh["skills"]
        assert (v / "m.json").exists(), "manifest not written"
    print("selftest OK")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Skill discovery engine.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("discover")
    d.add_argument("request")
    d.add_argument("--history", default=None)
    d.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    if args.selftest:
        selftest()
    elif args.cmd == "discover":
        res = discover(args.request, args.history, quiet=args.as_json)
        if args.as_json:
            print(json.dumps(res, indent=1))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
