#!/usr/bin/env python3
"""ABSOLUTE ZERO project scaffolder - autonomous experience injection. Stdlib only.

Starting a project is the trigger, not a chore. `new` creates the standard
`10_PROJECTS/<NAME>/` structure from the vault templates AND automatically
pulls the closest past experience (via `cases.py`) into a
`PRIOR_EXPERIENCE.md` note - so a new project opens with the decisions that
worked, the faults to avoid, and the reusable stack already in front of you,
without anyone running a query. This is the OS acting on a lifecycle event
(project start) instead of waiting to be asked. Contract: PROJECT.md.

  python scripts/project.py new <NAME> [--topic "..."] [--tags a,b]
  python scripts/project.py --selftest

ponytail: the trigger is the `new` command (deterministic, cross-platform).
A filesystem watcher that fires the moment a 10_PROJECTS/<dir> appears is the
true-daemon upgrade - Phase 6, an Ubuntu systemd user service; not worth a
fragile Windows watcher today.
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import load_json
import cases

VAULT = Path(__file__).resolve().parent.parent
# project file -> template. RECENT is generated inline (no template exists).
FILES = {"OVERVIEW": "project_OVERVIEW.md",
         "DECISIONS": "project_DECISIONS.md",
         "FAULTS": "project_FAULTS.md"}


def fill(text, name, summary):
    """Instantiate a template: name/date/summary, and strip the example
    ledger entry so a fresh project starts clean - the placeholder entries
    carry `[[<...>]]` links that would otherwise dangle."""
    # strip BEFORE substitution: once <YYYY-MM-DD> becomes a real date the
    # example header no longer starts with '<' and would survive.
    text = re.split(r"\n## <", text, 1)[0].rstrip() + "\n"
    text = text.replace("[[<NAME>_DECISIONS]]", "DECISIONS.md") \
               .replace("[[<NAME>_FAULTS]]", "FAULTS.md")
    text = text.replace("<NAME>", name) \
               .replace("<YYYY-MM-DD>", str(date.today()))
    return re.sub(r"summary: <[^>]*>", "summary: " + summary, text)


def prior_experience_note(name, topic, hits):
    """The auto-injected note: what past runs teach this new project."""
    head = (f"---\ntags: [experience, prior, case]\nproject: {name}\n"
            f"status: active\nconfidence: medium\ndate: {date.today()}\n"
            f"summary: Prior experience auto-injected for {name} from "
            f"{len(hits)} past case(s).\n---\n\n"
            f"# {name} — Prior Experience (auto-injected)\n")
    if topic:
        head += f"\n> Topic: {topic}\n"
    if not hits:
        return head + "\nNo similar past project found — this is new ground.\n"
    body = []
    for score, case, matched in hits:
        body.append(f"\n## Related: [[{case['project']}]]  "
                    f"(match {score}, on {', '.join(matched)})")
        if case.get("components"):
            body.append("- **Reuse stack:** "
                        + ", ".join(case["components"][:8]))
        for d in case.get("decisions", [])[:4]:
            body.append(f"- **Decision that worked:** {d}")
        for f in case.get("faults", [])[:4]:
            body.append(f"- **Avoid fault:** {f['symptom']}"
                        + (f" → {f['fix']}" if f.get("fix") else ""))
        for l in case.get("lessons", [])[:3]:
            body.append(f"- **Lesson:** {l}")
    return head + "\n".join(body) + "\n"


def new_project(vault, name, topic=None, tags=None):
    """Scaffold + autonomously inject prior experience. Returns (dir, hits)."""
    if not re.fullmatch(r"[A-Za-z0-9][\w -]*", name or ""):
        raise SystemExit("project name must be alphanumeric/underscore/dash")
    pdir = vault / "10_PROJECTS" / name
    if pdir.exists():
        raise SystemExit(f"project already exists: {name}")
    tmpl = vault / "90_META" / "templates"
    (pdir / "SESSIONS").mkdir(parents=True)
    for key, fname in FILES.items():
        summary = f"{name} {key.lower()} - scaffolded {date.today()}"
        (pdir / f"{key}.md").write_text(
            fill((tmpl / fname).read_text(encoding="utf-8"), name, summary),
            encoding="utf-8")
    (pdir / "RECENT.md").write_text(
        f"---\ntags: [project, recent]\nproject: {name}\nstatus: active\n"
        f"confidence: medium\ndate: {date.today()}\n"
        f"summary: Rolling recent state for {name}.\n---\n\n"
        f"# {name} — Recent\n\n- {date.today()}: scaffolded\n",
        encoding="utf-8")
    # --- autonomous step: pull prior experience without being asked ---
    store = load_json(vault / "90_META" / "experience" / "cases.json", {})
    query = topic or " ".join([name] + list(tags or []))
    hits = cases.similar(vault, store, query=query) if store else []
    (pdir / "PRIOR_EXPERIENCE.md").write_text(
        prior_experience_note(name, topic, hits), encoding="utf-8")
    return pdir, hits


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Project scaffolder.")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    n = sub.add_parser("new")
    n.add_argument("name")
    n.add_argument("--topic", default=None)
    n.add_argument("--tags", default="")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    if args.cmd == "new":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        pdir, hits = new_project(VAULT, args.name, args.topic, tags)
        rel = pdir.relative_to(VAULT)
        print(f"created {rel}/  (OVERVIEW, DECISIONS, FAULTS, RECENT, "
              f"SESSIONS/, PRIOR_EXPERIENCE)")
        if hits:
            print(f"\ninjected prior experience from {len(hits)} past "
                  f"project(s):")
            for score, case, matched in hits:
                print(f"  {score:>5}  {case['project']}  "
                      f"(on {', '.join(matched)})")
                for f in case.get("faults", [])[:2]:
                    print(f"         avoid: {f['symptom']}")
            print(f"\nsee {rel}/PRIOR_EXPERIENCE.md")
        else:
            print("no similar past project — new ground.")
        print("\nrun 'python scripts/indexer.py' to index the new project.")
    else:
        ap.print_help()


def selftest():
    import tempfile
    from core import dump_json
    with tempfile.TemporaryDirectory() as td:
        v = Path(td)
        # minimal templates (real placeholder shape)
        tdir = v / "90_META" / "templates"
        tdir.mkdir(parents=True)
        (tdir / "project_OVERVIEW.md").write_text(
            "---\ntags: [project, overview]\nproject: <NAME>\nstatus: active\n"
            "confidence: medium\ndate: <YYYY-MM-DD>\n"
            "summary: <one line, ≤25 tokens>\n---\n\n# <NAME> — Overview\n\n"
            "## Links\n- Decisions: [[<NAME>_DECISIONS]]\n", encoding="utf-8")
        (tdir / "project_DECISIONS.md").write_text(
            "---\nproject: <NAME>\nsummary: <one line>\ndate: <YYYY-MM-DD>\n"
            "---\n\n# <NAME> — Decisions\n\n## <YYYY-MM-DD> — <title>\n"
            "- **Chose:** <what>\n", encoding="utf-8")
        (tdir / "project_FAULTS.md").write_text(
            "---\nproject: <NAME>\nsummary: <one line>\ndate: <YYYY-MM-DD>\n"
            "---\n\n# <NAME> — Faults\n\n## <YYYY-MM-DD> — <symptom>\n"
            "- **Topic:** [[<knowledge-note>]]\n", encoding="utf-8")
        # a stored DRONE case to be surfaced (build via cases end-to-end)
        (v / "10_PROJECTS" / "DRONE").mkdir(parents=True)
        (v / "10_PROJECTS" / "DRONE" / "DECISIONS.md").write_text(
            "## Use VIO for GPS-denied localization\n- **Chose:** vision\n",
            encoding="utf-8")
        (v / "10_PROJECTS" / "DRONE" / "FAULTS.md").write_text(
            "## drift\n- **Symptom:** pose drifts without absolute reference\n"
            "- **Fix:** add fiducial re-localization\n", encoding="utf-8")
        dump_json(v / "10_PROJECTS" / "DRONE" / "bootstrap.json",
                  {"language": "python", "frameworks": ["ROS2"]})
        notes = [{"path": "10_PROJECTS/DRONE/OVERVIEW.md", "type": "overview",
                  "project": "DRONE", "tags": ["drone", "navigation", "gps",
                  "localization"], "summary": "GPS-denied drone nav",
                  "links": []}]
        store = {}
        cases.close_project(v, "DRONE", notes, store)

        # THE feature: scaffold a new drone project -> structure + auto inject
        pdir, hits = new_project(v, "DRONE2",
                                 topic="gps denied drone navigation")
        for f in ("OVERVIEW", "DECISIONS", "FAULTS", "RECENT",
                  "PRIOR_EXPERIENCE"):
            assert (pdir / f"{f}.md").exists(), f
        assert (pdir / "SESSIONS").is_dir()
        ov = (pdir / "OVERVIEW.md").read_text(encoding="utf-8")
        assert "project: DRONE2" in ov and "summary: DRONE2" in ov
        assert "<NAME>" not in ov and "[[<NAME>" not in ov, "placeholder left"
        dec = (pdir / "DECISIONS.md").read_text(encoding="utf-8")
        assert "## " + str(date.today()) not in dec  # example entry stripped
        prior = (pdir / "PRIOR_EXPERIENCE.md").read_text(encoding="utf-8")
        assert "[[DRONE]]" in prior, "past case not injected"
        assert "Avoid fault" in prior and "pose drifts" in prior
        assert hits and hits[0][1]["project"] == "DRONE"
        # fail loud: re-create existing project
        try:
            new_project(v, "DRONE2")
            raise AssertionError("re-create did not fail loud")
        except SystemExit:
            pass
        # bad name fails loud
        try:
            new_project(v, "../evil")
            raise AssertionError("bad name accepted")
        except SystemExit:
            pass
        # no cases -> honest 'new ground', still scaffolds
        pdir2, hits2 = new_project(v, "FRESH", topic="quantum basket weaving")
        assert not hits2
        assert "new ground" in (pdir2 / "PRIOR_EXPERIENCE.md").read_text(
            encoding="utf-8")
    print("selftest OK")


if __name__ == "__main__":
    main()
