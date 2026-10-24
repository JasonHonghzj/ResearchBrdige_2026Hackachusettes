"""PubMed retrieval for ResearchBridge.

Stores title, journal, year, MeSH descriptors AND abstract text — the probes
only kept year+mesh, which left claim verification and evidence quotes dead.

Uses ElementTree rather than regex: abstracts arrive as several <AbstractText>
sections with Label attributes (BACKGROUND / METHODS / RESULTS), and a regex
either concatenates them wrongly or misses the labelled variants entirely.
"""
from __future__ import annotations

import json
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)

CONTACT = os.environ.get("CONTACT_EMAIL", "dang2002991@gmail.com")
NCBI_KEY = os.environ.get("NCBI_API_KEY", "").strip()
# 3 req/s without a key, 10 with one
THROTTLE = 0.11 if NCBI_KEY else 0.36

_session = requests.Session()
_session.headers.update({"User-Agent": f"ResearchBridge ({CONTACT})"})


def _params(**kw) -> dict:
    kw["email"] = CONTACT
    kw["tool"] = "ResearchBridge"
    if NCBI_KEY:
        kw["api_key"] = NCBI_KEY
    return kw


def _get(endpoint: str, *, tries: int = 4, **kw) -> requests.Response | None:
    for attempt in range(tries):
        try:
            r = _session.get(f"{BASE}/{endpoint}", params=_params(**kw), timeout=180)
            if r.status_code == 200:
                return r
            # 429/5xx are the throttling path: back off and retry
            time.sleep(2 * (attempt + 1))
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    return None


def _text(el: ET.Element | None) -> str:
    """Flatten an element's text including nested markup (<i>, <sup>, …)."""
    if el is None:
        return ""
    return " ".join(t.strip() for t in el.itertext() if t and t.strip())


def _abstract(article: ET.Element) -> str:
    """Join labelled AbstractText sections in order, keeping the labels."""
    parts = []
    for at in article.iterfind(".//Abstract/AbstractText"):
        body = _text(at)
        if not body:
            continue
        label = (at.get("Label") or "").strip()
        parts.append(f"{label}: {body}" if label else body)
    return " ".join(parts)


def _year(article: ET.Element) -> int | None:
    """Journal issue publication year.

    Scoped to Journal/JournalIssue/PubDate on purpose — a loose search picks up
    other PubDate elements and leaks later years into an earlier window. That
    bug put 802 post-2018 records inside a '2005:2018' fetch during the probes.
    """
    for path in (".//Article/Journal/JournalIssue/PubDate/Year",
                 ".//Article/ArticleDate/Year"):
        y = article.find(path)
        if y is not None and (y.text or "").strip().isdigit():
            return int(y.text.strip())
    md = article.find(".//Article/Journal/JournalIssue/PubDate/MedlineDate")
    if md is not None and md.text:
        head = md.text.strip()[:4]
        if head.isdigit():
            return int(head)
    return None


def _parse(xml_text: str) -> dict:
    out = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for pa in root.iterfind(".//PubmedArticle"):
        pmid_el = pa.find(".//MedlineCitation/PMID")
        if pmid_el is None or not (pmid_el.text or "").strip():
            continue
        article = pa.find(".//MedlineCitation")
        mesh = []
        for mh in pa.iterfind(".//MeshHeadingList/MeshHeading"):
            d = mh.find("DescriptorName")
            if d is None:
                continue
            ui = d.get("UI")
            if ui:
                mesh.append([ui, (d.text or "").strip(), d.get("MajorTopicYN", "N")])
        out[pmid_el.text.strip()] = {
            "year": _year(pa),
            "title": _text(pa.find(".//Article/ArticleTitle")),
            "journal": _text(pa.find(".//Article/Journal/ISOAbbreviation")),
            "abstract": _abstract(pa),
            "mesh": mesh,
        }
    return out


PROVENANCE = DATA / "provenance.json"


def _record_provenance(entry: dict) -> None:
    """Append-only retrieval log. Every number the app shows must be traceable
    to a source, a query and a timestamp — otherwise 'verify the source' is a
    claim we cannot back."""
    log = []
    if PROVENANCE.exists():
        try:
            log = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        except ValueError:
            log = []
    log = [e for e in log if e.get("cache") != entry.get("cache")]
    log.append(entry)
    PROVENANCE.write_text(json.dumps(log, indent=1), encoding="utf-8")


def provenance() -> list[dict]:
    if not PROVENANCE.exists():
        return []
    return json.loads(PROVENANCE.read_text(encoding="utf-8"))


def _read(window: str) -> dict:
    """Prefer the complete year-sliced corpus over the capped range fetch."""
    full = DATA / f"corpus_{window}_full.json"
    part = DATA / f"corpus_{window}.json"
    if full.exists():
        return json.loads(full.read_text(encoding="utf-8"))
    if part.exists():
        print(f"[fetch] WARNING: using {part.name}, which is capped at ~22% of "
              f"the result set. Run gapfinder.fetch.fetch_years() for the full span.")
        return json.loads(part.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"no corpus for window {window!r}")


def load_production(cutoff: int | None = None) -> dict:
    """THE GRID THE PRODUCT USES: every year, 2005-2026, deduplicated.

    A researcher wants gaps that are open now, so nothing is held back here.
    `cutoff` exists only for the validation view below.
    """
    recs = {}
    for window in ("past", "future"):
        try:
            recs.update(_read(window))
        except FileNotFoundError:
            continue
    recs = {k: v for k, v in recs.items() if v["year"]}
    if cutoff is not None:
        recs = {k: v for k, v in recs.items() if v["year"] <= cutoff}
    return recs


def load_corpus(window: str, cutoff: int = 2018) -> dict:
    """THE VALIDATION VIEW: the same corpus, split strictly at `cutoff`.

    One fetch, two views. The split must be applied on every read, never once
    upstream: PubMed's [dp] filter leaks across the boundary because print and
    electronic dates disagree, so the raw window files contain records from the
    wrong side (801 post-2018 records arrived inside a 2005:2018 range fetch).

    Deriving both views from `load_production` would be equivalent; these stay
    window-scoped so the validation never silently widens its training set.
    """
    recs = _read(window)
    if window == "past":
        return {k: v for k, v in recs.items() if v["year"] and v["year"] <= cutoff}
    return {k: v for k, v in recs.items() if v["year"] and v["year"] > cutoff}


def spot_check(window: str = "past", n: int = 20, seed: int = 0) -> dict:
    """Re-fetch n random records live and compare against what we stored.

    An integrity check we can run in front of anyone: it proves the local cache
    is faithful to PubMed rather than something we edited.
    """
    import random
    recs = json.loads((DATA / f"corpus_{window}.json").read_text(encoding="utf-8"))
    rng = random.Random(seed)
    sample = rng.sample(sorted(recs), min(n, len(recs)))
    title_ok = mesh_ok = checked = 0
    mismatches = []
    for i in range(0, len(sample), 50):
        chunk = sample[i:i + 50]
        r = _get("efetch.fcgi", db="pubmed", id=",".join(chunk), retmode="xml")
        if r is None:
            continue
        live = _parse(r.text)
        for pmid in chunk:
            if pmid not in live:
                continue
            checked += 1
            stored = recs[pmid]
            t_ok = live[pmid]["title"] == stored["title"]
            m_ok = (sorted(m[0] for m in live[pmid]["mesh"])
                    == sorted(m[0] for m in stored["mesh"]))
            title_ok += t_ok
            mesh_ok += m_ok
            if not (t_ok and m_ok):
                mismatches.append(pmid)
        time.sleep(THROTTLE)
    return {"checked": checked, "titles_match": title_ok,
            "mesh_match": mesh_ok, "mismatches": mismatches,
            "verified_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def fetch_window(topic_query: str, date_range: str, cap: int = 9800,
                 cache_name: str | None = None, refresh: bool = False) -> dict:
    """Fetch one date window. Cached by name; a cache hit is the same code path
    as a cold run with step one already done.

    PubMed's history server will not page past ~10,000 per query, so `cap`
    stays under that; a larger corpus needs date-sliced sub-queries.
    """
    cache = DATA / (cache_name or "corpus.json")
    if cache.exists() and not refresh:
        recs = json.loads(cache.read_text(encoding="utf-8"))
        print(f"[{cache.name}] cached: {len(recs)} records")
        return recs

    query = f"{topic_query} AND {date_range}[dp]"
    r = _get("esearch.fcgi", db="pubmed", term=query, retmode="json",
             retmax=0, usehistory="y")
    if r is None:
        raise RuntimeError("esearch failed")
    meta = r.json()["esearchresult"]
    total = int(meta["count"])
    env, qk = meta["webenv"], meta["querykey"]
    want = min(total, cap)
    print(f"[{cache.name}] {date_range}: {total} available, fetching {want}")

    recs: dict = {}
    for start in range(0, want, 200):
        rr = _get("efetch.fcgi", db="pubmed", WebEnv=env, query_key=qk,
                  retstart=start, retmax=200, retmode="xml")
        if rr is None:
            print(f"   giving up on batch at {start}")
            continue
        recs.update(_parse(rr.text))
        if start % 2000 == 0:
            print(f"   {len(recs)}")
        time.sleep(THROTTLE)

    cache.write_text(json.dumps(recs), encoding="utf-8")
    with_abs = sum(1 for v in recs.values() if v["abstract"])
    with_mesh = sum(1 for v in recs.values() if v["mesh"])

    _record_provenance({
        "cache": cache.name,
        "source": "NCBI E-utilities (PubMed)",
        "endpoints": [f"{BASE}/esearch.fcgi", f"{BASE}/efetch.fcgi"],
        "query": query,
        "date_range": date_range,
        "available_total": total,
        "requested": want,
        "retrieved": len(recs),
        "abstract_coverage": round(with_abs / max(len(recs), 1), 4),
        "mesh_coverage": round(with_mesh / max(len(recs), 1), 4),
        "retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_key_used": bool(NCBI_KEY),
        "reproduce": (f"{BASE}/esearch.fcgi?db=pubmed&retmode=json&usehistory=y"
                      f"&term={requests.utils.quote(query)}"),
        "note": ("Raw window output. PubMed [dp] leaks across the boundary "
                 "(print vs electronic dates) — use gapfinder.fetch.load_corpus(), "
                 "which applies the strict year filter."),
    })

    print(f"[{cache.name}] {len(recs)} records | "
          f"abstract {with_abs} ({with_abs/max(len(recs),1):.0%}) | "
          f"mesh {with_mesh} ({with_mesh/max(len(recs),1):.0%})")
    return recs


def fetch_years(topic_query: str, years: range, cache_name: str,
                refresh: bool = False) -> dict:
    """Fetch a multi-year span COMPLETELY, by slicing into per-year queries.

    Why this exists: esearch returns at most 9,999 ids no matter what `retmax`
    says, and efetch-over-history will not page past the same point. A single
    2005:2018 query reports 44,156 results and hands back 9,800 — 22%. Every
    individual year is well under the cap (largest is 5,758), so year-by-year
    retrieval gets the whole span.

    Per-year counts sum to 50,078 against the range query's 44,156 because a
    record with a 2017 electronic and 2018 print date is returned for both
    years. That double counting is the same mechanism that leaked 801 post-2018
    records into the earlier range fetch. Dedupe is by PMID, so it is harmless.
    """
    cache = DATA / cache_name
    if cache.exists() and not refresh:
        recs = json.loads(cache.read_text(encoding="utf-8"))
        print(f"[{cache.name}] cached: {len(recs)} records")
        return recs

    recs: dict = {}
    per_year: dict[int, int] = {}
    for year in years:
        query = f"{topic_query} AND {year}[dp]"
        r = _get("esearch.fcgi", db="pubmed", term=query,
                 retmode="json", retmax=10000)
        if r is None:
            print(f"   {year}: esearch failed, skipping")
            continue
        res = r.json()["esearchresult"]
        ids = res.get("idlist", [])
        per_year[year] = int(res["count"])
        if len(ids) < per_year[year]:
            print(f"   {year}: WARNING only {len(ids)} of {per_year[year]} ids "
                  f"returned — slice this year further")
        time.sleep(THROTTLE)

        before = len(recs)
        for i in range(0, len(ids), 200):
            rr = _get("efetch.fcgi", db="pubmed", id=",".join(ids[i:i + 200]),
                      retmode="xml")
            if rr is None:
                continue
            recs.update(_parse(rr.text))
            time.sleep(THROTTLE)
        print(f"   {year}: {per_year[year]:>6} found, "
              f"+{len(recs) - before:>5} new, total {len(recs):,}")

    cache.write_text(json.dumps(recs), encoding="utf-8")
    with_abs = sum(1 for v in recs.values() if v["abstract"])
    with_mesh = sum(1 for v in recs.values() if v["mesh"])
    _record_provenance({
        "cache": cache.name,
        "source": "NCBI E-utilities (PubMed)",
        "endpoints": [f"{BASE}/esearch.fcgi", f"{BASE}/efetch.fcgi"],
        "query": f"{topic_query} AND <year>[dp]",
        "strategy": "per-year slices, deduplicated by PMID",
        "years": [min(years), max(years) if years else None],
        "per_year_counts": per_year,
        "per_year_sum": sum(per_year.values()),
        "retrieved_unique": len(recs),
        "abstract_coverage": round(with_abs / max(len(recs), 1), 4),
        "mesh_coverage": round(with_mesh / max(len(recs), 1), 4),
        "retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_key_used": bool(NCBI_KEY),
        "note": ("Complete span. esearch caps at 9,999 ids regardless of retmax, "
                 "so a single range query returns ~22% of a 44k result set."),
    })
    print(f"[{cache.name}] {len(recs):,} unique records | "
          f"abstract {with_abs/max(len(recs),1):.0%} | "
          f"mesh {with_mesh/max(len(recs),1):.0%}")
    return recs


def split_strict(recs: dict, cutoff: int) -> tuple[dict, dict]:
    """Strict year split. The window query alone is not enough — print and
    electronic dates disagree and leak across the boundary."""
    past = {k: v for k, v in recs.items() if v["year"] and v["year"] <= cutoff}
    future = {k: v for k, v in recs.items() if v["year"] and v["year"] > cutoff}
    return past, future


TOPIC = ('("Early Detection of Cancer"[MeSH Terms] '
         'OR "Early Diagnosis"[MeSH Terms])')

if __name__ == "__main__":
    import sys
    refresh = "--refresh" in sys.argv
    past = fetch_window(TOPIC, "2005:2018", cache_name="corpus_past.json",
                        refresh=refresh)
    future = fetch_window(TOPIC, "2019:2026", cache_name="corpus_future.json",
                          refresh=refresh)
    p, _ = split_strict(past, 2018)
    _, f = split_strict(future, 2018)
    print(f"\nstrict split: past(<=2018) {len(p)} | future(>2018) {len(f)}")
    print(f"  leaked out of past window: {len(past) - len(p)}")
    ex = next((v for v in p.values() if v["abstract"]), None)
    if ex:
        print(f"\nsample abstract ({len(ex['abstract'])} chars):")
        print("  " + ex["abstract"][:260] + "…")
