#!/usr/bin/env python3
"""ABSOLUTE ZERO indexer. Stdlib only.

Walks the vault, parses YAML frontmatter, and emits:
  90_META/INDEX.json        all notes: path, type, project, tags, summary, links, date
  90_META/INDEX_SUMMARY.md  one line per project + counts (<300 tokens)
  90_META/FAULT_LEDGER.md   one line per fault: [proj][tags] symptom -> fix (link)

Run from anywhere: python scripts/indexer.py  (vault root = parent of scripts/).
"""
import argparse
import json
import re
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
META = VAULT / "90_META"

# Dirs/files that are input to the brain but not indexable notes.
SKIP_DIRS = {".git", ".obsidian", ".claude", "templates", "traces", "plans",
             "verify", "prompts", "skills", "experience", "runs"}
SKIP_NAMES = {"INDEX_SUMMARY.md", "FAULT_LEDGER.md", "INDEX.json",
              "GRAPH.json"}
ROOT_DOCS = {"CLAUDE.md", "FLOW.md", "GUIDE.md", "DASHBOARD.md",
             "ORCHESTRATOR.md", "CONTEXT.md", "PLUGINS.md", "PLANNER.md",
             "VERIFIER.md", "PROMPTC.md", "SKILLS.md", "EXPERIENCE.md",
             "AGENTS.md", "GRAPH.md"}

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def parse_frontmatter(text):
    """Minimal YAML: scalars and inline lists `[a, b]`. No deps."""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    body = text[m.end():]
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.strip().startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            fm[key] = [x.strip() for x in val[1:-1].split(",") if x.strip()]
        else:
            fm[key] = val.strip().strip('"').strip("'")
    return fm, body


def note_type(path, tags):
    """Type used by query.py --type. Folder first, project filename refines."""
    rel = path.relative_to(VAULT)
    top = rel.parts[0]
    if path.name in ROOT_DOCS:
        return "doc"
    if top == "20_KNOWLEDGE":
        return "knowledge"
    if top == "30_LESSONS":
        return "lesson"
    if top == "40_RESEARCH":
        return "research"
    if top == "00_CORE":
        return "core"
    if top == "10_PROJECTS":
        name = path.name.upper()
        if "FAULT" in name:
            return "fault"
        if "DECISION" in name:
            return "decision"
        if "OVERVIEW" in name:
            return "overview"
        if "RECENT" in name:
            return "recent"
        if "SESSIONS" in rel.parts:
            return "session"
        return "project"
    return "note"


def project_of(path, fm):
    if fm.get("project"):
        return fm["project"]
    rel = path.relative_to(VAULT)
    if rel.parts[0] == "10_PROJECTS" and len(rel.parts) > 1:
        return rel.parts[1]
    return "-"


def iter_notes():
    for p in VAULT.rglob("*.md"):
        if p.name in SKIP_NAMES:
            continue
        if SKIP_DIRS & set(p.relative_to(VAULT).parts):
            continue
        yield p


def parse_faults(path, body, project, tags):
    """Split a FAULTS.md body into per-section ledger lines."""
    out = []
    for sec in re.split(r"\n(?=## )", body):
        if not sec.startswith("## "):  # skip the H1 preamble chunk
            continue
        head = sec.splitlines()[0][3:].strip()
        if not head or head.startswith("<"):
            continue
        symptom = _field(sec, "Symptom") or head
        fix = _field(sec, "Fix") or "?"
        link = LINK_RE.search(sec)
        link = link.group(1) if link else "?"
        tagstr = ",".join(tags[:3]) if tags else "-"
        out.append(f"[{project}][{tagstr}] {symptom} -> {fix} ([[{link}]])")
    return out


def _field(sec, label):
    m = re.search(rf"\*\*{label}:\*\*\s*(.+)", sec)
    return m.group(1).strip() if m else ""


def build():
    notes, faults, per_project = [], [], {}
    for p in iter_notes():
        text = p.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(text)
        tags = fm.get("tags", []) if isinstance(fm.get("tags"), list) else []
        ntype = note_type(p, tags)
        proj = project_of(p, fm)
        rel = p.relative_to(VAULT).as_posix()
        title = _title(body) or p.stem
        entry = {
            "path": rel,
            "type": ntype,
            "project": proj,
            "tags": tags,
            "title": title,
            "summary": fm.get("summary", ""),
            "status": fm.get("status", ""),
            "confidence": fm.get("confidence", ""),
            "date": fm.get("date", ""),
            "links": LINK_RE.findall(body),
        }
        notes.append(entry)
        d = per_project.setdefault(proj, {"notes": 0, "faults": 0, "lessons": 0})
        d["notes"] += 1
        if ntype == "lesson":
            d["lessons"] += 1
        if ntype == "fault":
            fl = parse_faults(p, body, proj, tags)
            faults.extend(fl)
            d["faults"] += len(fl)
    return notes, faults, per_project


def _title(body):
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def write_outputs(notes, faults, per_project):
    META.mkdir(exist_ok=True)
    (META / "INDEX.json").write_text(
        json.dumps({"generated": str(date.today()), "notes": notes},
                   indent=2, ensure_ascii=False),
        encoding="utf-8")

    lines = [f"# INDEX SUMMARY", "",
             f"Generated {date.today()} · {len(notes)} notes · {len(faults)} faults",
             ""]
    for proj in sorted(per_project):
        c = per_project[proj]
        lines.append(f"- **{proj}**: {c['notes']} notes, "
                     f"{c['lessons']} lessons, {c['faults']} faults")
    (META / "INDEX_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    fl = ["# FAULT LEDGER", "",
          "One line per fault. Scan before technical work on a tagged topic.", ""]
    fl += [f"- {f}" for f in faults] or ["- (none yet)"]
    (META / "FAULT_LEDGER.md").write_text("\n".join(fl) + "\n", encoding="utf-8")


def _selftest():
    fm, body = parse_frontmatter(
        "---\ntags: [a, b]\nproject: X\nsummary: hi\n---\n# T\n[[link]]\n")
    assert fm["tags"] == ["a", "b"], fm
    assert fm["project"] == "X"
    assert LINK_RE.findall(body) == ["link"]
    assert _field("**Fix:** rebooted", "Fix") == "rebooted"
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(description="Rebuild vault index.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    notes, faults, per_project = build()
    write_outputs(notes, faults, per_project)
    print(f"indexed {len(notes)} notes, {len(faults)} faults -> 90_META/")


if __name__ == "__main__":
    main()
