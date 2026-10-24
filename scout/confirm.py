"""Confirm candidate gaps against FULL PubMed, not just our corpus.

Why this module exists, and it is the most important lesson in the project:

A cell being empty in our grid means "no paper indexed as early-detection
research carries both terms". It does NOT mean the work has never been done.
Checked against full PubMed, the top 8 ranked gaps had 103, 1224, 91, 391, 1485,
17, 231 and 472 papers respectively. Zero of eight were real gaps. Pitching any
of them would have been humiliating.

The claim that survives is narrower and verifiable:

    "<method> has been used on <problem> N times, and never for EARLY DETECTION
     of it."

So every candidate gets two live queries:

    maturity   problem AND method                  -> how proven the pairing is
    gap        problem AND method AND early-topic  -> must be ~zero

A high maturity count is a FEATURE. It says the method already works on this
disease, so pointing it at early detection is tractable rather than speculative.

Small non-zero gap counts (2-6) are expected: our corpus starts at 2005 because
that is when the topic descriptors were introduced, and ~4% of all-time results
predate it.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

DATA = Path(__file__).resolve().parent.parent / "data"
CACHE = DATA / "gap_confirm.json"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
TOPIC = ('("Early Detection of Cancer"[MeSH Terms] '
         'OR "Early Diagnosis"[MeSH Terms])')

CONTACT = os.environ.get("CONTACT_EMAIL", "dang2002991@gmail.com")
NCBI_KEY = os.environ.get("NCBI_API_KEY", "").strip()
THROTTLE = 0.11 if NCBI_KEY else 0.36

#: allow a few stragglers from before the descriptors existed
GAP_TOLERANCE = 2

_session = requests.Session()
_session.headers.update({"User-Agent": f"ResearchScout ({CONTACT})"})


def _count(term: str) -> int | None:
    params = {"db": "pubmed", "term": term, "retmode": "json", "retmax": 0,
              "email": CONTACT, "tool": "ResearchScout"}
    if NCBI_KEY:
        params["api_key"] = NCBI_KEY
    for attempt in range(3):
        try:
            r = _session.get(BASE, params=params, timeout=90)
            if r.status_code == 200:
                return int(r.json()["esearchresult"]["count"])
        except (requests.RequestException, ValueError, KeyError):
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def _load() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def confirm(candidates: list[dict], *, verbose: bool = True,
            save_every: int = 25) -> list[dict]:
    """Annotate candidates with live `maturity` and `gap_papers` counts.

    Cached by "problem|method" so a rerun costs nothing and a crash mid-way
    loses nothing.
    """
    cache = _load()
    out = []
    queried = 0
    for i, row in enumerate(candidates, 1):
        key = f'{row["problem"]}|{row["method"]}'
        if key not in cache:
            pm = (f'"{row["problem"]}"[MeSH Terms] '
                  f'AND "{row["method"]}"[MeSH Terms]')
            maturity = _count(pm)
            time.sleep(THROTTLE)
            gap = _count(f"{pm} AND {TOPIC}")
            time.sleep(THROTTLE)
            if maturity is None or gap is None:
                if verbose:
                    print(f"   [{i}] query failed, skipping {key}")
                continue
            cache[key] = {"maturity": maturity, "gap_papers": gap}
            queried += 1
            if verbose and queried % 20 == 0:
                print(f"   confirmed {i}/{len(candidates)} "
                      f"({queried} live queries)")
            if queried % save_every == 0:
                CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
        c = cache[key]
        out.append({**row, **c,
                    "real_gap": c["gap_papers"] <= GAP_TOLERANCE})
    CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    if verbose:
        real = sum(1 for r in out if r["real_gap"])
        print(f"[confirm] {len(out)} checked | {real} confirmed real gaps "
              f"({real/max(len(out),1):.0%}) | {queried} live queries")
    return out
