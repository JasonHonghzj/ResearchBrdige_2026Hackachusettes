"""Exercise local Uvicorn endpoints and real exports in all Library languages.

This verifies HTTP and file contents, not browser layout or a system print dialog.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlsplit

import requests
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]


def verify(base_url: str, output: Path) -> dict:
    if urlsplit(base_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Use the local test server; this script sends no data to third parties.")
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    session = requests.Session()

    def call(method, route, **kwargs):
        response = session.request(method, base_url.rstrip("/") + route, timeout=(5, 30), **kwargs)
        response.raise_for_status()
        return response

    all_ids = [p["pmid"] for p in call("GET", "/api/bridge/search", params={"q": "study", "limit": 60}).json()["results"]]
    assert len(all_ids) == 32
    seeds = json.loads((ROOT / "data/bridge/snapshots/pubmed.json").read_text(encoding="utf-8"))["records"]
    literal = seeds["41726533"]["sections"][0]["text"][:80]
    for lang in ("en", "zh", "es"):
        meta = call("GET", "/api/bridge/meta", params={"lang": lang}).json()
        assert meta["stats"]["papers"] == 60 and meta["stats"]["abstracts"] == 56
        search = call("GET", "/api/bridge/search", params={"q": "study", "limit": 20}).json()
        assert search["total_count"] == 32 and search["shown_count"] == 20
        assert [p["pmid"] for p in search["results"]] == all_ids[:20]
        compared = call("POST", "/api/bridge/compare", json={"pmids": ["41726533", "41726516"], "lang": lang}).json()
        assert len(compared["papers"]) == 2 and len(compared["pairs"]) == 1
        brief = call("POST", "/api/bridge/brief", json={"goal": "medication literacy", "pmids": ["41726533"], "lang": lang}).json()
        assert "41726533" in brief["markdown"]
        cases.append({"language": lang, "localized_search_tab": meta["text"]["tab_search"],
                      "total_matches": search["total_count"], "shown_matches": search["shown_count"],
                      "compare": "pass", "brief": "pass"})
        for kind, params, expected in (
            ("search", {"q": "study"}, all_ids),
            ("bridges", {"q": "medication literacy", "method": "llm", "cue": "privacy"}, ["40963721", "41726516"]),
            ("compare", {"pmids": ["41726533", "41726516"]}, ["41726533", "41726516"]),
            ("brief", {"q": "medication literacy", "pmids": ["41726533"]}, ["41726533"]),
            ("directory", {"name": "Harvard"}, []),
        ):
            for fmt in ("csv", "html", "pdf"):
                response = call("POST", "/api/bridge/export", json={"kind": kind, "format": fmt, "lang": lang, **params})
                content = response.content
                path = output / f"{kind}-{lang}.{fmt}"
                path.write_bytes(content)
                if fmt == "pdf":
                    assert content.startswith(b"%PDF")
                    reader = PdfReader(io.BytesIO(content))
                    assert len(reader.pages) > 0
                    text = "\n".join(page.extract_text() or "" for page in reader.pages)
                else:
                    text = content.decode("utf-8-sig")
                    if fmt == "csv" and kind == "search":
                        rows = list(csv.DictReader(io.StringIO(text)))
                        assert len(rows) == 32
                        assert [row["pmid"] for row in rows] == all_ids
                assert len(text.strip()) > 40 and all(pmid in text for pmid in expected)
                cases.append({"kind": kind, "language": lang, "format": fmt, "status": "pass",
                              "path": str(path.resolve()), "bytes": len(content),
                              "sha256": hashlib.sha256(content).hexdigest()})
    checked = call("POST", "/api/bridge/check", json={"claims": literal + "\nA fabricated statement that is absent from the sources.", "pmids": ["41726533"]}).json()
    assert [r["status"] for r in checked["reports"]] == ["literal_match", "review_required"]
    saved = call("GET", "/api/gap/check", params={"problem": "Obesity", "method": "Polymerase Chain Reaction"}).json()
    assert saved["maturity"] == 2403 and saved["gap_papers"] == 0 and saved["cached"] is True
    state = call("GET", "/api/gap/validation").json()
    assert state["status"] == "pending_remeasurement"
    result = {"status": "pass", "checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "base_url": base_url, "languages": ["en", "zh", "es"], "export_cases": 45,
              "literal_source_check": "pass", "saved_gap_check": "pass", "cases": cases,
              "scope": "Real localhost HTTP responses and CSV/HTML/PDF contents. Browser layout and print preview are separate."}
    (output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checked = verify(args.base_url, args.output)
    print(f"HTTP verification {checked['status']}: {checked['export_cases']} exports; en/zh/es")
