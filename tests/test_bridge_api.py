"""Proof that the vendored ResearchBridge engine runs inside Scout's FastAPI app.

Expected PMIDs come from the teammate's own fixed development cases
(researchbridge/evaluate.py), so these tests check the merge did not change
retrieval behaviour, not just that the endpoint returns 200.
"""
import json
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app import app
from researchbridge.core import DB_PATH, build_database

client = TestClient(app)


def test_search_returns_expected_top_paper():
    r = client.get("/api/bridge/search", params={"q": "medication literacy"})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"]["corpus_size"] == 60
    assert body["scope"]["validated"] is False
    assert body["results"][0]["pmid"] == "41726533"


@pytest.mark.parametrize("q", ["用藥素養", "medication literacy", "alfabetización sobre medicamentos"])
def test_same_concept_same_ranking_in_every_language(q):
    body = client.get("/api/bridge/search", params={"q": q}).json()
    assert body["effective_query"] == "medication literacy chatbot"
    assert body["results"][0]["pmid"] == "41726533"


def test_excerpt_is_verbatim_source_text():
    body = client.get("/api/bridge/search", params={"q": "protein structure"}).json()
    hit = next(p for p in body["results"] if p["excerpt"])
    record = sqlite3.connect(DB_PATH).execute(
        "SELECT abstract FROM papers WHERE pmid=?", (hit["pmid"],)).fetchone()[0]
    for sentence in hit["excerpt"].split(". "):
        assert sentence.rstrip(".") in record


def test_nonsense_query_reports_no_results():
    body = client.get("/api/bridge/search", params={"q": "zzxq987654xyz"}).json()
    assert body["count"] == 0 and body["results"] == []


@pytest.mark.parametrize("params", [{"q": ""}, {"q": "x", "mode": "bm25"}, {"q": "x", "limit": 0}])
def test_bad_input_is_rejected(params):
    assert client.get("/api/bridge/search", params=params).status_code == 422


def test_repointed_paths_rebuild_identical_database(tmp_path):
    """starter/ + data/bridge/ must reproduce the teammate's shipped database."""
    rebuilt = tmp_path / "rebuilt.sqlite"
    build_database(rebuilt)

    def dump(path):
        with closing(sqlite3.connect(path)) as conn:
            papers = {pmid: json.loads(p) for pmid, p in conn.execute("SELECT pmid, payload FROM papers")}
            links = sorted(r[0] for r in conn.execute("SELECT pmid || institution_id FROM paper_institutions"))
            prov = dict(conn.execute("SELECT key, value FROM provenance"))
        return papers, links, prov

    assert dump(rebuilt) == dump(DB_PATH)
