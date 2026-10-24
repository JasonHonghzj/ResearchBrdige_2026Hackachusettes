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
import re
import time
from pathlib import Path

import requests

DATA = Path(__file__).resolve().parent.parent / "data"
CACHE = DATA / "gap_confirm.json"
CHECK_CACHE = DATA / "check_cache.json"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
TOPIC = ('("Early Detection of Cancer"[MeSH Terms] '
         'OR "Early Diagnosis"[MeSH Terms])')

CONTACT = os.environ.get("CONTACT_EMAIL", "dang2002991@gmail.com")
NCBI_KEY = os.environ.get("NCBI_API_KEY", "").strip()
THROTTLE = 0.11 if NCBI_KEY else 0.36

#: allow a few stragglers from before the descriptors existed
GAP_TOLERANCE = 2

_session = requests.Session()
_session.headers.update({"User-Agent": f"ResearchBridge ({CONTACT})"})


def _count(term: str) -> int | None:
    params = {"db": "pubmed", "term": term, "retmode": "json", "retmax": 0,
              "email": CONTACT, "tool": "ResearchBridge"}
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


#: MeSH descriptor names hold letters, digits, spaces and this punctuation.
#: Anything else is REJECTED rather than escaped: the value is interpolated into
#: a PubMed query string, and a stray bracket or quote silently changes which
#: query actually runs.
TERM_OK = re.compile(r"^[A-Za-z0-9 ,\-()'./+]{2,100}$")


def _term_query(term: str) -> str:
    return f'"{term}"[MeSH Terms]'


def _read_check_cache() -> dict:
    if CHECK_CACHE.exists():
        try:
            return json.loads(CHECK_CACHE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def check_pair(problem: str, method: str, *, use_cache: bool = True) -> dict:
    """Verify one problem/method pairing live, in about a second.

    Four queries, and the first two matter more than they look:

        1. problem alone   is this actually a MeSH descriptor?
        2. method alone    likewise
        3. both            maturity - how proven the pairing already is
        4. both + topic    the gap - must be within tolerance

    Without 1 and 2 this tool has a humiliating failure mode: a misspelled or
    invented term matches nothing, so maturity and gap both return 0 and the
    verdict reads like a pristine research gap for a disease that does not
    exist. An unrecognised term is reported as unrecognised, never as a gap.
    """
    problem, method = problem.strip(), method.strip()
    for label, term in (("problem", problem), ("method", method)):
        if not TERM_OK.match(term):
            return {"ok": False, "problem": problem, "method": method,
                    "error": f"{label} is not a usable MeSH descriptor name"}

    key = f"{problem}|{method}"
    cache = _read_check_cache()
    if use_cache and key in cache:
        return {**cache[key], "cached": True}

    started = time.time()
    p_alone = _count(_term_query(problem))
    time.sleep(THROTTLE)
    m_alone = _count(_term_query(method))
    time.sleep(THROTTLE)
    if p_alone is None or m_alone is None:
        return {"ok": False, "problem": problem, "method": method,
                "error": "PubMed did not respond"}

    unknown = [l for l, n in (("problem", p_alone), ("method", m_alone)) if n == 0]
    if unknown:
        return {"ok": False, "problem": problem, "method": method,
                "problem_papers": p_alone, "method_papers": m_alone,
                "error": "not indexed in MeSH: " + ", ".join(unknown),
                "detail": ("PubMed returns nothing for that descriptor, so it is "
                           "most likely misspelled or not a MeSH heading. Zero "
                           "results here is a spelling problem, not a gap.")}

    pair = f"{_term_query(problem)} AND {_term_query(method)}"
    maturity = _count(pair)
    time.sleep(THROTTLE)
    gap = _count(f"{pair} AND {TOPIC}")
    if maturity is None or gap is None:
        return {"ok": False, "problem": problem, "method": method,
                "error": "PubMed did not respond"}

    low = problem.lower()
    real_gap = gap <= GAP_TOLERANCE
    if not real_gap:
        verdict = (f"Not a gap. {gap} papers already apply {method} to early "
                   f"detection of {low}.")
    elif maturity == 0:
        verdict = (f"No paper applies {method} to {low} at all, for any purpose. "
                   f"That is untried rather than untried-for-early-detection, so "
                   f"there may be a reason.")
    elif maturity >= 50:
        verdict = (f"{method} has been applied to {low} {maturity:,} times, and "
                   f"{'never' if gap == 0 else f'only {gap} times'} for detecting "
                   f"it early. The method is established on this disease.")
    else:
        verdict = (f"Thin. Only {maturity} papers apply {method} to {low} for any "
                   f"purpose, so there is little evidence the method works here.")

    out = {"ok": True, "problem": problem, "method": method,
           "problem_papers": p_alone, "method_papers": m_alone,
           "maturity": maturity, "gap_papers": gap,
           "real_gap": real_gap, "tolerance": GAP_TOLERANCE, "verdict": verdict,
           "queries": {"maturity": pair, "gap": f"{pair} AND {TOPIC}"},
           "elapsed_s": round(time.time() - started, 2),
           "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    cache[key] = out
    CHECK_CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return {**out, "cached": False}


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
