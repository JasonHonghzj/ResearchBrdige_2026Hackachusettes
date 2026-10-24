"""Fetch public-source snapshots, then atomically rebuild the local SQLite database."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from researchbridge.core import ROOT, SNAPSHOTS, build_database, parse_pubmed, read_csv, verified_work

PRIORITY = ["41726533", "41726541", "41726516", "41726433", "41001595", "41049045", "40964651", "40963721", "41140426", "41031082", "41122737", "41509880", "41669754", "41058940", "40933079", "41001172", "41726465", "41001228", "41001598", "40896709"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def get(url, params=None):
    last = None
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, headers={"User-Agent": "ResearchBridgeLocalDemo/0.1"}, timeout=(10, 40))
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last = exc
            if getattr(exc.response, "status_code", None) in {400, 401, 403, 404}:
                break
            time.sleep(1 + attempt)
    # Do not record request URLs: API credentials may be present in their query string.
    raise RuntimeError(type(last).__name__) from last


def enrich(refresh=False, openalex_limit=20):
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    seeds = read_csv(ROOT / "pubmed" / "data.csv")
    errors = []
    pubmed_file = SNAPSHOTS / "pubmed.json"
    if refresh or not pubmed_file.exists():
        try:
            url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            response = get(url, {"db": "pubmed", "id": ",".join(r["pmid"] for r in seeds), "retmode": "xml", "tool": "researchbridge"})
            records = parse_pubmed(response.content)
            requested = {r["pmid"] for r in seeds}
            if not records or not set(records).issubset(requested):
                raise ValueError("Unexpected PubMed identifiers")
            raw_path = SNAPSHOTS / "pubmed.xml"
            raw_path.write_bytes(response.content)
            save_json(pubmed_file, {"source": url, "retrieved_at": now(), "sha256": hashlib.sha256(response.content).hexdigest(), "requested_pmids": sorted(requested), "records": records})
            print(f"PubMed: {len(records)} official records; {sum(bool(r['abstract']) for r in records.values())} abstracts", flush=True)
        except (RuntimeError, ValueError) as exc:
            errors.append({"source": "PubMed", "error": type(exc).__name__})
            print("PubMed retrieval failed; retaining any existing snapshot.", flush=True)
    directory = SNAPSHOTS / "openalex"
    directory.mkdir(parents=True, exist_ok=True)
    for pmid in PRIORITY[:openalex_limit]:
        output = directory / f"{pmid}.json"
        if output.exists() and not refresh:
            continue
        url = f"https://api.openalex.org/works/pmid:{pmid}"
        try:
            params = {"api_key": os.environ["OPENALEX_API_KEY"]} if os.environ.get("OPENALEX_API_KEY") else None
            record = get(url, params).json()
            if not verified_work(record, pmid):
                raise ValueError("PMID mismatch")
            save_json(output, {"source": url, "retrieved_at": now(), "record": record})
            print(f"OpenAlex: PMID {pmid} verified", flush=True)
        except (RuntimeError, ValueError) as exc:
            errors.append({"source": "OpenAlex", "pmid": pmid, "error": type(exc).__name__})
            print(f"OpenAlex: PMID {pmid} unavailable; not creating a link", flush=True)
        time.sleep(0.4)
    save_json(SNAPSHOTS / "retrieval_log.json", {"last_attempt_at": now(), "errors": errors})
    stats = build_database()
    print(json.dumps(stats, ensure_ascii=False), flush=True)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Refresh cached public-source snapshots")
    parser.add_argument("--openalex-limit", type=int, default=20, choices=range(0, 21), metavar="0..20")
    args = parser.parse_args()
    enrich(args.refresh, args.openalex_limit)
