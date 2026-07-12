#!/usr/bin/env python3
"""ABSOLUTE ZERO shared kernel. Stdlib only.

One home for the primitives every engine used to re-implement (audit
H2/M4): tokenization, stopwords, stemming, jaccard, token estimation,
the canonical similarity function, atomic JSON I/O, and the vault index
loader. Engines import these from here — never from each other — so a
fix lands once and drift stops.

  python scripts/core.py --selftest
"""
import json
import os
import re
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")
# Stopwords never carry relevance; without this, "the" pins fault lines.
STOP = {"the", "a", "an", "to", "of", "in", "on", "for", "and", "or", "is",
        "are", "it", "this", "that", "with", "as", "at", "by", "be", "do",
        "does", "why", "how", "what", "when", "not", "no", "my", "our",
        "every", "all", "some", "into", "from", "after", "before", "during"}


def words_of(text):
    return WORD_RE.findall(text.lower())


def stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


def nwords(text):
    """Stemmed, stopword-free word set: the normalized similarity space."""
    return {stem(w) for w in words_of(text)} - STOP


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0


def est_tokens(text):
    return max(1, len(text) // 4)


def sim(a, b):
    """Canonical text similarity: stemmed jaccard or fuzzy prefix ratio,
    whichever is stronger. ponytail: lexical only; embedding sidecar
    (AZ_EMBED_CMD) is the upgrade path when recall quality caps out."""
    return max(jaccard(nwords(a), nwords(b)),
               SequenceMatcher(None, a.lower()[:200], b.lower()[:200]).ratio())


# Request classification (V3: in the kernel so plugins/context/planner/
# skills need no orchestrator import - that edge was a cycle).
# Dict order is tie-break priority: first listed wins on equal score.
INTENT_KEYWORDS = {
    "security": ["security", "vulnerability", "vuln", "auth", "injection",
                 "secret", "cve", "exploit", "permission", "harden"],
    "deployment": ["deploy", "release", "ship", "ci", "docker", "systemd",
                   "publish", "install", "flash", "provision"],
    "quick_fix": ["typo", "rename", "tweak", "bump", "quick", "trivial"],
    "performance": ["slow", "performance", "optimize", "optimise", "latency",
                    "memory", "profile", "speed", "throughput"],
    "architecture": ["architecture", "redesign", "restructure", "refactor",
                     "decouple", "orchestrator", "state machine"],
    "research": ["research", "investigate", "compare", "evaluate", "survey",
                 "which", "options", "feasibility"],
    "documentation": ["document", "documentation", "docs", "readme",
                      "comment", "explain", "guide", "writeup"],
    "bug_fix": ["bug", "fix", "crash", "error", "broken", "fails", "failing",
                "exception", "traceback", "regression", "wrong", "debug"],
    "feature": ["add", "implement", "feature", "build", "create", "support",
                "new", "extend"],
}
COMPLEX_WORDS = ["entire", "redesign", "architecture", "migrate", "overhaul",
                 "across", "system-wide", "production-ready", "framework"]
TRIVIAL_WORDS = ["typo", "rename", "bump", "one line", "one-line", "quick"]


def classify(request):
    text = request.lower()
    have = set(words_of(text))
    best, best_score = "feature", 0
    for intent, keys in INTENT_KEYWORDS.items():
        # prefix match so secrets/secret, failing/fails etc. all hit
        score = sum(1 for k in keys
                    if (any(w.startswith(k) for w in have)
                        if " " not in k else k in text))
        if score > best_score:
            best, best_score = intent, score
    ambiguous = best_score == 0
    high = (best == "architecture" or len(have) > 60
            or any(w in text for w in COMPLEX_WORDS))
    low = best == "quick_fix" or any(w in text for w in TRIVIAL_WORDS)
    complexity = "complex" if high else ("trivial" if low else "standard")
    return {"intent": best, "complexity": complexity, "ambiguous": ambiguous}


def retrieve(query, items, key=lambda x: x, limit=5, floor=0.15):
    """The one retrieval scorer (V3 rule: one layer feeds all engines).
    Returns [(score, item)] best-first, floor-filtered."""
    scored = sorted(((sim(query, key(it)), it) for it in items),
                    key=lambda s: s[0], reverse=True)
    return [(round(s, 2), it) for s, it in scored[:limit] if s >= floor]


def stale(artifact, sources):
    """True if a cached artifact is missing or older than any source file.
    V3 cache invalidation: rebuild only when this says so."""
    a = Path(artifact)
    if not a.exists():
        return True
    am = a.stat().st_mtime
    return any(s.stat().st_mtime > am for s in map(Path, sources)
               if s.exists())


def load_json(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def dump_json(p, obj):
    """Atomic write (audit H5): tmp file + os.replace, so a crash mid-write
    never leaves truncated JSON for another engine to choke on."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, indent=1) + "\n")
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_index(vault):
    """The vault's note index, or fail loud (P1)."""
    idx = Path(vault) / "90_META" / "INDEX.json"
    if not idx.exists():
        raise SystemExit("no INDEX.json - run scripts/indexer.py first")
    return json.loads(idx.read_text(encoding="utf-8"))["notes"]


def selftest():
    assert words_of("Fix the Date-Crash!") == ["fix", "the", "date-crash"]
    assert stem("fixes") == "fix" and stem("es") == "es"
    assert nwords("fixing the crashes") == {"fix", "crash"}
    c = classify("fix typo in readme")
    assert (c["intent"], c["complexity"]) == ("quick_fix", "trivial")
    assert classify("hello there")["ambiguous"]
    assert jaccard({1, 2}, {2, 3}) == 1 / 3 and jaccard(set(), set()) == 0.0
    assert est_tokens("") == 1 and est_tokens("x" * 40) == 10
    assert sim("guard the empty header", "guarded empty headers") > 0.5
    assert sim("odometry drift", "unrelated banana talk") < 0.3
    hits = retrieve("odometry drift fix",
                    ["odometry drift absolute fix", "banana bread recipe"],
                    floor=0.3)
    assert len(hits) == 1 and hits[0][1].startswith("odometry")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "deep" / "x.json"
        dump_json(p, {"a": [1, 2]})
        assert load_json(p, None) == {"a": [1, 2]}
        assert load_json(Path(td) / "missing.json", 42) == 42
        assert not list(p.parent.glob("*.tmp")), "tmp file leaked"
        src = Path(td) / "src.py"
        src.write_text("x", encoding="utf-8")
        art = Path(td) / "art.json"
        dump_json(art, {})                                # artifact after src
        assert stale(Path(td) / "nope.json", [src])       # missing artifact
        assert not stale(art, [Path(td) / "ghost.py"])    # no live sources
        assert not stale(art, [src])                      # fresh
        os.utime(src, (art.stat().st_mtime + 60,) * 2)
        assert stale(art, [src])                          # source newer
        v = Path(td)
        (v / "90_META").mkdir()
        dump_json(v / "90_META" / "INDEX.json", {"notes": [{"t": 1}]})
        assert load_index(v) == [{"t": 1}]
        try:
            load_index(Path(td) / "novault")
            raise AssertionError("missing index did not fail loud")
        except SystemExit:
            pass
    print("selftest OK")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        selftest()
    else:
        print(__doc__)
