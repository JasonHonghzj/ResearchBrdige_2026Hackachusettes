"""MeSH descriptor name -> OpenAlex search phrase.

OpenAlex has no MeSH filter, so a grid term cannot be carried across directly.
Hand-mapped in data/phrases.json for every axis term; `normalize()` is the
fallback for anything unmapped.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
_raw = json.loads((DATA / "phrases.json").read_text(encoding="utf-8"))
METHODS: dict[str, str] = _raw["methods"]
PROBLEMS: dict[str, str] = _raw["problems"]

# MeSH inverts names for alphabetisation: "Carcinoma, Hepatocellular".
# Qualifiers after the comma are the head noun's modifiers, so reversing the
# clauses recovers readable English: "Hepatocellular Carcinoma".
_NEOPLASM = re.compile(r"\bneoplasms?\b", re.I)


def normalize(name: str) -> str:
    """Best-effort phrase for an unmapped descriptor."""
    parts = [p.strip() for p in name.split(",") if p.strip()]
    if len(parts) > 1:
        name = " ".join(reversed(parts))
    # "Breast Neoplasms" -> "breast cancer"; the literature says cancer
    name = _NEOPLASM.sub("cancer", name)
    return name.strip().lower()


def phrase(name: str, kind: str = "problem") -> str:
    table = METHODS if kind == "method" else PROBLEMS
    return table.get(name) or normalize(name)


def coverage(axis_names, kind: str = "problem"):
    """(mapped, unmapped) — run this after any axis change."""
    table = METHODS if kind == "method" else PROBLEMS
    mapped = [n for n in axis_names if n in table]
    unmapped = [n for n in axis_names if n not in table]
    return mapped, unmapped


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from scout.mesh import build_axes, DATA as MDATA

    corpus = json.loads((MDATA / "corpus_past.json").read_text(encoding="utf-8"))
    corpus = {k: v for k, v in corpus.items() if v["year"] and v["year"] <= 2018}
    P, M, freq, name_of, trees = build_axes(corpus)

    for axis, ids, kind in (("PROBLEM", P, "problem"), ("METHOD", M, "method")):
        names = [name_of[u] for u in ids]
        mapped, unmapped = coverage(names, kind)
        print(f"\n{axis} axis: {len(names)} terms | "
              f"mapped {len(mapped)} | unmapped {len(unmapped)}")
        for n in unmapped:
            print(f"   UNMAPPED  {n:<46} -> fallback: \"{normalize(n)}\"")
