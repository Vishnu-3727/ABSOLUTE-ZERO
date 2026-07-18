#!/usr/bin/env python3
"""ABSOLUTE ARCHIVE - project experience engine (case-based reasoning). Stdlib only.

The experience engine (experience.py) learns at task granularity: one trace,
one symptom->fix, one intent's stats. This layer learns at PROJECT
granularity. When a project completes, its whole run becomes one reusable
*case*: topics, components/stack, key decisions, faults and their fixes,
the workflows that passed, and the lessons it produced. When a new project
starts on similar ground, `similar` pulls the closest past case(s) forward -
so you reuse what worked and skip the trial-and-error you already paid for.

Built on artifacts the OS already produces: INDEX.json notes (tags, links,
summaries per project), 10_PROJECTS/<NAME>/{OVERVIEW,DECISIONS,FAULTS}.md,
bootstrap.json (stack), and 90_META/traces (which workflows a project ran).
Stored: 90_META/experience/cases.json + a real 10_PROJECTS/<NAME>/EXPERIENCE.md
note (indexed, so it also surfaces via query/graph/recall). Contract: CASES.md.

  python scripts/cases.py close <PROJECT>        build + store the case
  python scripts/cases.py close --all            every project with notes
  python scripts/cases.py similar "<topic>"      rank past cases by a query
  python scripts/cases.py similar --project <NEW> rank against a project's profile
  python scripts/cases.py list
  python scripts/cases.py --selftest

ponytail: components come from bootstrap.json + note tags, not graph.py -
external projects (ASUNAMA lives outside the vault) have no code nodes to
walk. Add a graph-component signal when the target project is the vault itself.
"""
import argparse
import math
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import dump_json, load_index, load_json, nwords

VAULT = Path(__file__).resolve().parent.parent
CASES = VAULT / "90_META" / "experience" / "cases.json"
SIG_W = 0.6       # query-coverage (tags/topics/stack) weight in the score
TXT_W = 0.4       # free-text similarity weight
FLOOR = 0.18      # below this a case is noise, not a match - do not surface
MAX_ITEMS = 8     # cap decisions/faults/lessons carried per case


# -- reading vault artifacts ----------------------------------------------
def read(p):
    return p.read_text(encoding="utf-8") if p.exists() else ""


def to_words(text):
    """Stemmed word set with slug/path separators split - so `gps` in a
    query matches `gps-denied-localization` in a case signature. Without
    this, multi-word tags/slugs never intersect single-word queries."""
    return nwords(re.sub(r"[-_/.]", " ", text))


def parse_decisions(text, cap=MAX_ITEMS):
    """`## Heading` + its first bullet (the rationale) = a reusable decision.
    The heading alone says a decision existed; the bullet says why."""
    out = []
    for block in re.split(r"^#{2,3}\s+", text, flags=re.M)[1:]:
        lines = block.splitlines()
        head = lines[0].strip() if lines and lines[0].strip() else ""
        if not head:
            continue
        why = next((l.strip("-*+ ").strip() for l in lines[1:]
                    if l.strip()[:1] in "-*+"), "")
        out.append(f"{head} — {why}" if why else head)
    return out[:cap]


def parse_faults(text, cap=MAX_ITEMS):
    """Split on `## ` blocks; pull Symptom/Fix (or Outcome) bullets."""
    out = []
    for block in re.split(r"^##\s+", text, flags=re.M)[1:]:
        if not block.strip():          # trailing bare `## ` -> no crash
            continue
        head = block.splitlines()[0].strip()
        sym = re.search(r"\*\*Symptom:\*\*\s*(.+)", block)
        fix = re.search(r"\*\*(?:Fix|Outcome|Resolution):\*\*\s*(.+)", block)
        out.append({"symptom": (sym.group(1) if sym else head).strip()[:200],
                    "fix": (fix.group(1).strip()[:200] if fix else "")})
    return out[:cap]


def stack_from_bootstrap(boot):
    """Language/framework/dependency strings = a project's components."""
    comp = []
    for k in ("language", "languages", "framework", "frameworks",
              "dependencies", "deps", "libraries", "components", "stack"):
        v = boot.get(k)
        if isinstance(v, str):
            comp.append(v)
        elif isinstance(v, (list, tuple)):
            comp += [str(x) for x in v]
        elif isinstance(v, dict):
            comp += [str(x) for x in v.keys()]
    return sorted({c.strip() for c in comp if c and str(c).strip()})


def project_workflows(vault, name):
    """Which intents this project ran, from its closed traces."""
    wf = {}
    tdir = vault / "90_META" / "traces"
    if not tdir.is_dir():
        return wf
    for tp in sorted(tdir.glob("*.json")):
        tr = load_json(tp, None)
        if not tr or tr.get("project") != name or tr.get("result") is None:
            continue
        e = wf.setdefault(tr.get("intent", "unknown"), {"runs": 0, "pass": 0})
        e["runs"] += 1
        e["pass"] += tr.get("result") == "pass"
    return wf


# -- case construction ----------------------------------------------------
def build_case(vault, name, notes):
    """Roll one project's whole run into a reusable case object."""
    # exclude our own EXPERIENCE.md note: re-ingesting it would feed the
    # 'experience'/'case' boilerplate back into every signature over time.
    pnotes = [n for n in notes if n.get("project") == name
              and not n.get("path", "").endswith("EXPERIENCE.md")]
    tags = sorted({t for n in pnotes for t in n.get("tags", [])})
    links = sorted({l for n in pnotes for l in n.get("links", [])})
    summaries = [n["summary"] for n in pnotes if n.get("summary")]
    pdir = vault / "10_PROJECTS" / name
    overview = read(pdir / "OVERVIEW.md")
    decisions = parse_decisions(read(pdir / "DECISIONS.md"))
    faults = parse_faults(read(pdir / "FAULTS.md"))
    components = stack_from_bootstrap(load_json(pdir / "bootstrap.json", {}))
    workflows = project_workflows(vault, name)
    # lessons: project frontmatter is the reliable link (tags are lowercase,
    # project names upper - a name-in-tags test silently never fires)
    lessons = [f"{Path(n['path']).stem}: {n.get('summary', '')}".strip(": ")
               for n in notes if n.get("type") == "lesson"
               and (n.get("project") == name
                    or Path(n["path"]).stem in links)][:MAX_ITEMS]
    # signature = the topic/stack words two projects can literally share
    # (tags, components and topic slugs, tokenized to stemmed words)
    signature = sorted(to_words(" ".join([name] + tags + components + links)))
    blob = " ".join([name, overview[:600]] + summaries + decisions
                    + [f["symptom"] for f in faults] + components)
    return {"project": name, "date": str(date.today()),
            "tags": tags, "components": components, "topics": links,
            "decisions": decisions, "faults": faults,
            "workflows": workflows, "lessons": lessons,
            "signature": signature, "blob": blob,
            "note": f"10_PROJECTS/{name}/EXPERIENCE.md"}


def write_case_note(vault, case):
    """Human-readable, frontmatter'd EXPERIENCE.md so it is indexed too."""
    name = case["project"]
    p = vault / "10_PROJECTS" / name / "EXPERIENCE.md"
    if not p.parent.exists():
        return None
    tags = sorted(set(case["tags"]) | {"experience", "case"})
    lines = [f"---\ntags: [{', '.join(tags)}]\nproject: {name}\n"
             f"status: active\nconfidence: medium\ndate: {case['date']}\n"
             f"summary: Project experience case for {name} - "
             f"reusable decisions, faults and stack.\n---\n",
             f"# {name} — Project Experience\n",
             "## Stack / components",
             ("- " + "\n- ".join(case["components"])) if case["components"]
             else "- (none recorded)", "",
             "## Key decisions",
             ("- " + "\n- ".join(case["decisions"])) if case["decisions"]
             else "- (none recorded)", "",
             "## Faults & fixes (do not repeat)"]
    for f in case["faults"]:
        lines.append(f"- **{f['symptom']}**"
                     + (f" → {f['fix']}" if f["fix"] else ""))
    if not case["faults"]:
        lines.append("- (none recorded)")
    lines += ["", "## Lessons"]
    lines += ["- " + l for l in case["lessons"]] or ["- (none)"]
    lines += ["", "## Workflows that ran"]
    lines += [f"- {i}: {e['pass']}/{e['runs']} pass"
              for i, e in case["workflows"].items()] or ["- (none traced)"]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def close_project(vault, name, notes, store):
    if not (vault / "10_PROJECTS" / name).exists() \
            and not any(n.get("project") == name for n in notes):
        raise SystemExit(f"no such project: {name} "
                         "(no 10_PROJECTS dir and no notes reference it)")
    case = build_case(vault, name, notes)
    store[name] = case
    dump_json(vault / "90_META" / "experience" / "cases.json", store)
    note = write_case_note(vault, case)
    return case, note


# -- retrieval (the make-or-break) ----------------------------------------
def query_profile(vault, notes, query=None, project=None):
    """Turn a free-text query OR a project into (signature set, text) so it
    can be scored against stored cases the same way."""
    if project:
        c = build_case(vault, project, notes)
        return set(c["signature"]), c["blob"], project
    return to_words(query or ""), query or "", None


def similar(vault, store, query=None, project=None, notes=None, limit=5,
            floor=FLOOR):
    qsig, _qtext, exclude = query_profile(vault, notes or [], query, project)
    if not qsig or not store:
        return []
    # IDF over the store's signatures: matching a rare topic word (odometry,
    # in one case) counts for more than a stack word every project shares
    # (python). A word in *every* case gets weight 0 - so a generic query
    # ("python") scores nothing and cannot false-positive, while a specific
    # one ("odometry") matches even as a single word. This is the fix for
    # the generic-term class the review flagged.
    N = len(store)
    df = {}
    for case in store.values():
        for w in set(case.get("signature", [])):
            df[w] = df.get(w, 0) + 1

    def idf(w):
        return math.log((N + 1) / (df.get(w, 0) + 1))
    qweight = sum(idf(w) for w in qsig) or 1.0
    ranked = []
    for name, case in store.items():
        if name == exclude:
            continue
        csig = set(case.get("signature", []))
        cblob = nwords(case.get("blob", ""))
        sig_hit = qsig & csig
        cover = sum(idf(w) for w in sig_hit) / qweight
        # text leg = containment (matched / query), not jaccard: a big blob
        # was drowning the old sim() score to ~0, making 0.4 dead weight.
        tcov = sum(idf(w) for w in qsig & cblob) / qweight
        score = round(SIG_W * cover + TXT_W * tcov, 3)
        if score >= floor:
            ranked.append((score, case, sorted(sig_hit or (qsig & cblob))))
    # recency breaks score ties deterministically (newest run first)
    ranked.sort(key=lambda r: (r[0], r[1].get("date", "")), reverse=True)
    return ranked[:limit]


# -- CLI ------------------------------------------------------------------
def _print_case(score, case, matched=None):
    print(f"\n{score:>5}  {case['project']}  "
          f"[{', '.join(case['tags'][:6]) or 'no tags'}]")
    if matched:                        # show WHY it matched (trust)
        print(f"       matched:   {', '.join(matched)}")
    if case["components"]:
        print(f"       stack:     {', '.join(case['components'][:8])}")
    for d in case["decisions"][:4]:
        print(f"       decision:  {d}")
    for f in case["faults"][:4]:
        print(f"       fault:     {f['symptom']}"
              + (f"  →  {f['fix']}" if f["fix"] else ""))
    for intent, e in list(case.get("workflows", {}).items())[:3]:
        print(f"       workflow:  {intent}: {e['pass']}/{e['runs']} pass")
    for l in case["lessons"][:3]:
        print(f"       lesson:    {l}")
    print(f"       see:       {case['note']}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Project experience engine.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("close")
    c.add_argument("project", nargs="?")
    c.add_argument("--all", action="store_true")
    s = sub.add_parser("similar")
    s.add_argument("query", nargs="?")
    s.add_argument("--project")
    s.add_argument("--limit", type=int, default=5)
    sub.add_parser("list")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    if args.cmd == "close":
        notes = load_index(VAULT)
        store = load_json(CASES, {})
        pdir = VAULT / "10_PROJECTS"
        if args.all and not pdir.exists():
            raise SystemExit("no 10_PROJECTS/ dir to close")
        names = ([d.name for d in pdir.iterdir() if d.is_dir()]
                 if args.all else [args.project])
        if not names or names == [None]:
            raise SystemExit("give a project name or --all")
        for name in names:
            case, note = close_project(VAULT, name, notes, store)
            print(f"closed  {name}: {len(case['decisions'])} decisions, "
                  f"{len(case['faults'])} faults, "
                  f"{len(case['components'])} components"
                  + (f" -> {note.relative_to(VAULT)}" if note else ""))
        print("run 'python scripts/indexer.py' to index the new "
              "EXPERIENCE.md note(s)")
    elif args.cmd == "similar":
        if not args.query and not args.project:
            raise SystemExit("give a query or --project")
        store = load_json(CASES, {})
        if not store:
            print("no cases yet - run 'cases.py close <PROJECT>' first")
            return
        notes = load_index(VAULT) if args.project else []
        hits = similar(VAULT, store, query=args.query, project=args.project,
                       notes=notes, limit=args.limit)
        if not hits:
            print("no similar past projects (nothing above the match floor)")
            return
        print(f"{len(hits)} similar past project(s):")
        for score, case, matched in hits:
            _print_case(score, case, matched)
    elif args.cmd == "list":
        store = load_json(CASES, {})
        for name, case in store.items():
            print(f"{name:<20} {len(case['decisions'])} decisions, "
                  f"{len(case['faults'])} faults, cased {case['date']}")
        if not store:
            print("no cases yet")
    else:
        ap.print_help()


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        (v / "90_META" / "experience").mkdir(parents=True)
        (v / "90_META" / "traces").mkdir()
        for name in ("DRONE", "WEBAPP"):
            (v / "10_PROJECTS" / name).mkdir(parents=True)
        # DRONE: a GPS-denied drone project, with a real fault + stack
        (v / "10_PROJECTS" / "DRONE" / "DECISIONS.md").write_text(
            "## Use VIO for GPS-denied localization\n"
            "## EKF fuses odometry and vision\n", encoding="utf-8")
        (v / "10_PROJECTS" / "DRONE" / "FAULTS.md").write_text(
            "## odometry drift\n- **Symptom:** pose drifts without absolute "
            "reference\n- **Fix:** add fiducial re-localization\n",
            encoding="utf-8")
        dump_json(v / "10_PROJECTS" / "DRONE" / "bootstrap.json",
                  {"language": "python", "frameworks": ["ROS2", "PX4"]})
        (v / "10_PROJECTS" / "WEBAPP" / "DECISIONS.md").write_text(
            "## React SPA with Vite\n## Tailwind for styling\n",
            encoding="utf-8")
        dump_json(v / "10_PROJECTS" / "WEBAPP" / "bootstrap.json",
                  {"language": "python", "frameworks": ["React", "Vite"]})
        notes = [
            {"path": "10_PROJECTS/DRONE/OVERVIEW.md", "type": "overview",
             "project": "DRONE", "tags": ["drone", "navigation", "gps",
             "localization"], "summary": "GPS-denied drone navigation",
             "links": ["odometry-drift-absolute-fix"]},
            {"path": "30_LESSONS/odometry-drift-absolute-fix.md",
             "type": "lesson", "project": "DRONE",
             "tags": ["navigation", "drone"],
             "summary": "drift needs an absolute reference", "links": []},
            {"path": "10_PROJECTS/WEBAPP/OVERVIEW.md", "type": "overview",
             "project": "WEBAPP", "tags": ["react", "frontend", "web"],
             "summary": "React dashboard SPA", "links": []},
        ]
        store = {}
        case, note = close_project(v, "DRONE", notes, store)
        assert note and note.exists(), "EXPERIENCE.md not written"
        txt = note.read_text(encoding="utf-8")
        assert "GPS-denied" in txt and "pose drifts" in txt
        assert "ROS2" in case["components"] and "PX4" in case["components"]
        assert case["faults"][0]["fix"].startswith("add fiducial")
        assert any("odometry-drift" in l for l in case["lessons"]), \
            case["lessons"]
        close_project(v, "WEBAPP", notes, store)
        assert (v / "90_META" / "experience" / "cases.json").exists()
        # THE make-or-break: a drone query surfaces DRONE, never WEBAPP
        hits = similar(v, store, query="gps denied drone navigation slam")
        assert hits and hits[0][1]["project"] == "DRONE", hits
        assert all(c["project"] != "WEBAPP" for _s, c, _m in hits), \
            "unrelated WEBAPP leaked into drone results"
        assert hits[0][2], "no matched-terms evidence returned"
        # generic word: DRONE and WEBAPP both are python. A python-heavy query
        # must rank by the SPECIFIC words, not the shared stack word.
        gen = similar(v, store, query="python drone navigation")
        assert gen and gen[0][1]["project"] == "DRONE", gen
        assert all(c["project"] != "WEBAPP" for _s, c, _m in gen), \
            "generic 'python' leaked the unrelated WEBAPP case"
        # a bare fully-shared word carries zero information -> no match
        assert not similar(v, store, query="python"), \
            "bare generic word false-positived"
        # off-topic query -> nothing
        assert not similar(v, store,
                           query="quarterly tax accounting spreadsheet"), \
            "noise query matched a case"
        # project-profile retrieval: a new drone project finds the old one
        newnotes = notes + [
            {"path": "10_PROJECTS/DRONE2/OVERVIEW.md", "type": "overview",
             "project": "DRONE2", "tags": ["drone", "navigation", "slam"],
             "summary": "new autonomous drone, vision nav", "links": []}]
        (v / "10_PROJECTS" / "DRONE2").mkdir()
        hits2 = similar(v, store, project="DRONE2", notes=newnotes)
        assert hits2 and hits2[0][1]["project"] == "DRONE", hits2
        # idempotent close: re-closing overwrites, does not duplicate
        n0 = len(store)
        close_project(v, "DRONE", notes, store)
        assert len(store) == n0
        # fail loud on a project that does not exist (P1)
        try:
            close_project(v, "GHOST", notes, store)
            raise AssertionError("close of nonexistent project did not fail")
        except SystemExit:
            pass
        # malformed FAULTS.md (trailing bare heading) must not crash
        assert parse_faults("## real\n- **Symptom:** boom\n\n## ")[0][
            "symptom"] == "boom"
        assert parse_faults("## ") == []
        # decision rationale: heading + first bullet captured together
        d = parse_decisions("## Chose X\n- because Y is faster\n")
        assert d == ["Chose X — because Y is faster"], d
    print("selftest OK")


if __name__ == "__main__":
    main()
