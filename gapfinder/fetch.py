"""PubMed retrieval for ResearchBridge.

Stores title, journal, year, MeSH descriptors AND abstract text — the first pass
only kept year+mesh, which left claim verification and evidence quotes dead.

Uses ElementTree rather than regex: abstracts arrive as several <AbstractText>
sections with Label attributes (BACKGROUND / METHODS / RESULTS), and a regex
either concatenates them wrongly or misses the labelled variants entirely.
"""
from __future__ import annotations

import json
import hashlib
import os
import tempfile
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
    bug put 802 post-2018 records inside a '2005:2018' fetch.
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
WINDOW_YEARS = {"past": range(2005, 2019), "future": range(2019, 2027)}


class CorpusIntegrityError(RuntimeError):
    """A corpus cannot support a completeness claim without a verified manifest."""


def _atomic_text(path: Path, text: str) -> None:
    """Publish one complete file; an interrupted write never becomes a cache hit."""
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _pmids_hash(pmids) -> str:
    return hashlib.sha256("\n".join(sorted(pmids)).encode("utf-8")).hexdigest()


def _manifest_path(cache: Path) -> Path:
    return cache.with_suffix(".meta.json")


def _validated_cache(cache: Path, *, topic_query: str, years) -> tuple[dict, dict]:
    """Validate the exact bytes and all year slices before reusing a full cache.

    Legacy files are preserved, but cannot be silently upgraded to complete:
    their old provenance did not record requested/fetched PMID reconciliation.
    """
    manifest = _manifest_path(cache)
    hint = "Run `python -m gapfinder.fetch --refresh` to rebuild verified full caches."
    try:
        raw = cache.read_bytes()
        recs = json.loads(raw)
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        slices = list(years)
        if (not isinstance(recs, dict) or meta.get("schema_version") != 1
                or meta.get("complete") is not True
                or meta.get("cache") != cache.name
                or meta.get("topic_query") != topic_query
                or meta.get("year_slices") != slices
                or meta.get("corpus_sha256") != hashlib.sha256(raw).hexdigest()
                or meta.get("retrieved_unique") != len(recs)
                or meta.get("requested_unique_count") != len(recs)
                or meta.get("requested_pmids_sha256") != _pmids_hash(recs)):
            raise ValueError("corpus/manifest identity or completeness mismatch")
        per_year = meta["per_year"]
        if set(per_year) != {str(y) for y in slices}:
            raise ValueError("missing year slices")
        requested = set()
        for stats in per_year.values():
            count = stats["available_count"]
            ids = stats["pmids"]
            if (type(count) is not int or count < 0
                    or stats["requested_count"] != count
                    or stats["retrieved_count"] != count
                    or not isinstance(ids, list)
                    or any(not isinstance(pmid, str) or not pmid.isdigit() for pmid in ids)
                    or len(ids) != count or len(set(ids)) != count
                    or stats.get("pmids_sha256") != _pmids_hash(ids)):
                raise ValueError("incomplete year slice")
            requested.update(ids)
        if requested != set(recs) or not isinstance(meta.get("retrieved_utc"), str):
            raise ValueError("requested PMID union or retrieval timestamp mismatch")
        if any(not isinstance(v, dict) or "year" not in v or "mesh" not in v
               for v in recs.values()):
            raise ValueError("invalid corpus record")
        return recs, meta
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise CorpusIntegrityError(f"Unverified corpus {cache.name}: {exc}. {hint}") from exc


def _record_provenance(entry: dict) -> None:
    """Append-only retrieval log. Every number the app shows must be traceable
    to a source, a query and a timestamp — otherwise 'verify the source' is a
    claim we cannot back."""
    log = []
    if PROVENANCE.exists():
        try:
            log = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise CorpusIntegrityError("Refusing to replace an unreadable provenance log") from exc
    if not isinstance(log, list):
        raise CorpusIntegrityError("Refusing to replace a non-list provenance log")
    log.append(entry)
    _atomic_text(PROVENANCE, json.dumps(log, indent=1))


def provenance() -> list[dict]:
    if not PROVENANCE.exists():
        return []
    return json.loads(PROVENANCE.read_text(encoding="utf-8"))


def _read_window(window: str) -> tuple[dict, dict, Path]:
    if window not in WINDOW_YEARS:
        raise ValueError("window must be 'past' or 'future'")
    full = DATA / f"corpus_{window}_full.json"
    part = DATA / f"corpus_{window}.json"
    if not full.exists():
        legacy = f" The capped legacy file {part.name} is not a production source." if part.exists() else ""
        raise FileNotFoundError(f"Missing {full.name}.{legacy} Run `python -m gapfinder.fetch`.")
    recs, meta = _validated_cache(full, topic_query=TOPIC, years=WINDOW_YEARS[window])
    return recs, meta, full


def _read(window: str) -> dict:
    """Read a verified full window; capped and unverified legacy files are refused."""
    return _read_window(window)[0]


def _dated_production(recs: dict) -> dict:
    """The query may match an electronic date outside the journal-year scope."""
    years = [year for window in WINDOW_YEARS.values() for year in window]
    first, last = min(years), max(years)
    return {k: v for k, v in recs.items()
            if isinstance(v.get("year"), int) and first <= v["year"] <= last}


def _production_snapshot() -> tuple[dict, list[dict]]:
    recs, sources = {}, []
    for window in WINDOW_YEARS:
        rows, meta, cache = _read_window(window)
        recs.update(rows)
        sources.append({"cache": cache.name, "path": str(cache.resolve()),
                        "sha256": meta["corpus_sha256"],
                        "metadata_sha256": hashlib.sha256(_manifest_path(cache).read_bytes()).hexdigest(),
                        "retrieved_utc": meta["retrieved_utc"], "records": len(rows)})
    return _dated_production(recs), sources


def load_production(cutoff: int | None = None) -> dict:
    """THE GRID THE PRODUCT USES: every year, 2005-2026, deduplicated.

    A researcher wants gaps that are open now, so nothing is held back here.
    `cutoff` exists only for the validation view below.
    """
    recs, _sources = _production_snapshot()
    if cutoff is not None:
        recs = {k: v for k, v in recs.items() if v["year"] <= cutoff}
    return recs


def load_corpus(window: str, cutoff: int = 2018) -> dict:
    """THE VALIDATION VIEW: the same corpus, split strictly at `cutoff`.

    One fetch, two views. The split must be applied on every read, never once
    upstream: PubMed's [dp] filter leaks across the boundary because print and
    electronic dates disagree, so the raw window files contain records from the
    wrong side (801 post-2018 records arrived inside a 2005:2018 range fetch).

    Both views are derived from the same merged production corpus, so changing
    the cutoff cannot discard years that arrived in the other retrieval file.
    """
    if window not in WINDOW_YEARS:
        raise ValueError("window must be 'past' or 'future'")
    recs = load_production()
    if window == "past":
        return {k: v for k, v in recs.items() if v["year"] and v["year"] <= cutoff}
    return {k: v for k, v in recs.items() if v["year"] and v["year"] > cutoff}


def spot_check(window: str = "past", n: int = 20, seed: int = 0) -> dict:
    """Re-fetch n random records live and compare against what we stored.

    Sample the same verified production sources the grid uses. A failed batch
    or absent PMID is an incomplete check, never a passing comparison.
    """
    import random
    if window not in {*WINDOW_YEARS, "production"} or n < 1:
        raise ValueError("choose past/future/production and a positive sample size")
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    recs, sources = _production_snapshot()
    if window == "past":
        recs, _ = split_strict(recs, 2018)
    elif window == "future":
        _, recs = split_strict(recs, 2018)
    rng = random.Random(seed)
    sample = rng.sample(sorted(recs), min(n, len(recs)))
    title_ok = mesh_ok = checked = 0
    mismatches = []
    missing, unavailable = [], []
    for i in range(0, len(sample), 50):
        chunk = sample[i:i + 50]
        r = _get("efetch.fcgi", db="pubmed", id=",".join(chunk), retmode="xml")
        if r is None:
            missing.extend(chunk)
            unavailable.extend(chunk)
            continue
        live = _parse(r.text)
        for pmid in chunk:
            if pmid not in live:
                missing.append(pmid)
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
    passed = bool(sample) and checked == len(sample) and not mismatches and not missing
    status = "pass" if passed else ("unavailable" if unavailable and not checked else "fail")
    return {"status": status, "ok": passed, "window": window, "seed": seed,
            "requested_sample_size": n, "sample_size": len(sample),
            "sampled_pmids": sample, "missing_pmids": missing,
            "unavailable_pmids": unavailable, "sources": sources,
            "snapshot_pmids_sha256": _pmids_hash(recs),
            "started_utc": started,
            "checked": checked, "titles_match": title_ok,
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
    """Fetch and reconcile every yearly PMID before publishing a full corpus.

    Any failed search, truncated ID list, missing batch or unparseable record
    raises without replacing an existing cache or marking the attempt complete.
    A manifest records each requested PMID and the hash of the corpus bytes.
    """
    cache = DATA / cache_name
    slices = list(years)
    if not slices or any(type(y) is not int for y in slices) or len(set(slices)) != len(slices):
        raise ValueError("years must contain distinct integer year slices")
    if cache.exists() and not refresh:
        recs, _meta = _validated_cache(cache, topic_query=topic_query, years=slices)
        print(f"[{cache.name}] verified cache: {len(recs)} records")
        return recs

    recs: dict = {}
    per_year: dict[int, int] = {}
    reconciliation = {}
    requested = set()
    for year in slices:
        query = f"{topic_query} AND {year}[dp]"
        r = _get("esearch.fcgi", db="pubmed", term=query,
                 retmode="json", retmax=10000)
        if r is None:
            raise CorpusIntegrityError(f"{year}: esearch failed; full cache was not replaced")
        try:
            res = r.json()["esearchresult"]
            ids, count = res["idlist"], int(res["count"])
            if (not isinstance(ids, list) or count < 0
                    or any(not isinstance(pmid, str) or not pmid.isdigit() for pmid in ids)
                    or len(ids) != count or len(set(ids)) != count):
                raise ValueError("reported count does not match unique returned PMID list")
        except (ValueError, KeyError, TypeError) as exc:
            raise CorpusIntegrityError(
                f"{year}: invalid or truncated esearch results; slice this year further. "
                "Full cache was not replaced") from exc
        per_year[year] = count
        time.sleep(THROTTLE)

        before = len(recs)
        year_recs = {}
        for i in range(0, len(ids), 200):
            chunk = ids[i:i + 200]
            rr = _get("efetch.fcgi", db="pubmed", id=",".join(chunk),
                      retmode="xml")
            if rr is None:
                raise CorpusIntegrityError(f"{year}: efetch batch {i} failed; full cache was not replaced")
            parsed = _parse(rr.text)
            if set(parsed) != set(chunk):
                raise CorpusIntegrityError(
                    f"{year}: efetch batch {i} PMID mismatch "
                    f"({len(parsed)}/{len(chunk)}); full cache was not replaced")
            year_recs.update(parsed)
            time.sleep(THROTTLE)
        requested.update(ids)
        recs.update(year_recs)
        reconciliation[str(year)] = {
            "available_count": count, "requested_count": len(ids),
            "retrieved_count": len(year_recs), "pmids": sorted(ids),
            "pmids_sha256": _pmids_hash(ids),
        }
        print(f"   {year}: {per_year[year]:>6} found, "
              f"+{len(recs) - before:>5} new, total {len(recs):,}")

    if set(recs) != requested:
        raise CorpusIntegrityError("Fetched PMID union differs from searches; full cache was not replaced")
    corpus_text = json.dumps(recs)
    retrieved_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta = {"schema_version": 1, "complete": True, "cache": cache.name,
            "topic_query": topic_query, "year_slices": slices,
            "per_year": reconciliation, "requested_unique_count": len(requested),
            "requested_pmids_sha256": _pmids_hash(requested),
            "retrieved_unique": len(recs),
            "corpus_sha256": hashlib.sha256(corpus_text.encode("utf-8")).hexdigest(),
            "retrieved_utc": retrieved_utc}
    # Publish the manifest last. If interrupted between replacements, its hash
    # will reject the changed corpus on the next read rather than bless it.
    _atomic_text(cache, corpus_text)
    _atomic_text(_manifest_path(cache), json.dumps(meta, indent=1))
    with_abs = sum(1 for v in recs.values() if v["abstract"])
    with_mesh = sum(1 for v in recs.values() if v["mesh"])
    _record_provenance({
        "cache": cache.name,
        "source": "NCBI E-utilities (PubMed)",
        "endpoints": [f"{BASE}/esearch.fcgi", f"{BASE}/efetch.fcgi"],
        "query": f"{topic_query} AND <year>[dp]",
        "strategy": "per-year slices, deduplicated by PMID",
        "years": [min(slices), max(slices)],
        "per_year_counts": per_year,
        "per_year_sum": sum(per_year.values()),
        "retrieved_unique": len(recs),
        "abstract_coverage": round(with_abs / max(len(recs), 1), 4),
        "mesh_coverage": round(with_mesh / max(len(recs), 1), 4),
        "retrieved_utc": retrieved_utc,
        "complete": True,
        "corpus_sha256": meta["corpus_sha256"],
        "manifest": _manifest_path(cache).name,
        "api_key_used": bool(NCBI_KEY),
        "note": "Complete requested year slices: every searched PMID was fetched and reconciled.",
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

def main(argv: list[str] | None = None) -> int:
    import argparse
    global DATA, PROVENANCE
    parser = argparse.ArgumentParser(description="Build verified, year-sliced PubMed corpora.")
    parser.add_argument("--refresh", action="store_true", help="replace caches only after every PMID is fetched")
    parser.add_argument("--data-dir", type=Path,
                        help="Store a separate retrieval run here instead of the demo data directory")
    args = parser.parse_args(argv)
    if args.data_dir is not None:
        DATA = args.data_dir.resolve()
        DATA.mkdir(parents=True, exist_ok=True)
        PROVENANCE = DATA / "provenance.json"
    recs = {}
    for window, years in WINDOW_YEARS.items():
        recs.update(fetch_years(TOPIC, years, f"corpus_{window}_full.json", refresh=args.refresh))
    past, future = split_strict(_dated_production(recs), 2018)
    print(f"\nproduction: {len(past) + len(future):,} dated records; "
          f"validation split: {len(past):,} <=2018 / {len(future):,} >2018")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
