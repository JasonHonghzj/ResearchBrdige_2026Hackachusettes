"""Proof that the vendored ResearchBridge engine runs inside the ResearchBridge FastAPI app.

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


# ---------------------------------------------------------------- full surface

def test_meta_serves_teammate_strings_per_language():
    zh = client.get("/api/bridge/meta", params={"lang": "zh"}).json()
    en = client.get("/api/bridge/meta", params={"lang": "en"}).json()
    assert zh["text"]["tab_search"] == "文獻探索" and en["text"]["tab_search"] == "Paper explorer"
    assert en["stats"] == {"papers": 60, "abstracts": 56, "affiliation_links": 79, "institutions": 135}
    assert client.get("/api/bridge/meta", params={"lang": "fr"}).status_code == 422


def test_bridge_results_carry_verbatim_evidence_for_each_side():
    body = client.get("/api/bridge/bridges", params={
        "q": "medication literacy", "method": "llm", "cue": "medication"}).json()
    assert body["method"]["id"] == "llm" and body["cue"]["id"] == "medication"
    assert body["count"] >= 1
    for p in body["results"]:
        assert p["method_evidence"] and p["bridge_evidence"]


def test_auto_method_uses_top_recommendation():
    body = client.get("/api/bridge/bridges", params={"q": "medication literacy"}).json()
    assert body["method"]["id"] == body["recommended_methods"][0]["id"]
    n = len(body["results"])
    assert len(body["pairs"]) == n * (n - 1) // 2


def test_compare_scores_are_bounded_and_pairs_unique():
    ids = [p["pmid"] for p in client.get("/api/bridge/search", params={"q": "large language models"}).json()["results"][:3]]
    assert len(ids) == 3
    body = client.post("/api/bridge/compare", json={"pmids": ids}).json()
    assert len(body["pairs"]) == 3
    assert all(0 <= p["score"] <= 1 for p in body["pairs"])


def test_check_literal_match_and_review_required():
    pmid = "41726533"
    abstract = sqlite3.connect(DB_PATH).execute("SELECT abstract FROM papers WHERE pmid=?", (pmid,)).fetchone()[0]
    real = abstract.split("\n\n")[0].split(": ", 1)[1][:80]
    body = client.post("/api/bridge/check", json={
        "claims": real + "\nChatbots cure all medication errors in every hospital.", "pmids": [pmid]}).json()
    statuses = [r["status"] for r in body["reports"]]
    assert statuses == ["literal_match", "review_required"]


def test_brief_prefers_saved_papers():
    body = client.post("/api/bridge/brief", json={"goal": "protein", "pmids": ["41726533"]}).json()
    assert "41726533" in body["markdown"]


def test_brief_without_matching_papers_is_a_clear_error():
    r = client.post("/api/bridge/brief", json={"goal": "zzxq987654xyz"})
    assert r.status_code == 422


def test_directory_filters():
    body = client.get("/api/bridge/directory", params={"city": "Worcester"}).json()
    assert body["count"] >= 1 and all(r["city"] == "Worcester" for r in body["institutions"])


@pytest.mark.parametrize("kind", ["search", "bridges", "compare", "brief", "directory"])
@pytest.mark.parametrize("fmt", ["csv", "html", "pdf"])
def test_every_export_kind_and_format(kind, fmt):
    r = client.post("/api/bridge/export", json={
        "kind": kind, "format": fmt, "q": "medication literacy", "pmids": ["41726533", "40963721"]})
    if r.status_code == 501:   # PDF needs Windows' Microsoft JhengHei; graceful elsewhere
        assert fmt == "pdf" and "HTML" in r.json()["detail"]
        return
    assert r.status_code == 200
    assert r.headers["content-disposition"].endswith(f'.{fmt}"')
    assert len(r.content) > 200
    if fmt == "pdf":
        assert r.content.startswith(b"%PDF")


def test_csv_export_neutralises_formula_injection():
    """A goal starting with '=' must not become a live spreadsheet formula."""
    r = client.post("/api/bridge/export", json={"kind": "search", "format": "csv", "q": "=chatbot"})
    assert r.status_code == 200
    assert b",=chatbot" not in r.content and b"'=chatbot" in r.content


def test_html_export_escapes_user_input():
    r = client.post("/api/bridge/export", json={"kind": "brief", "format": "html",
                                                 "q": "<script>alert(1)</script> chatbot"})
    assert r.status_code == 200
    assert b"<script>alert(1)" not in r.content


@pytest.mark.parametrize("call", [
    lambda: client.get("/api/bridge/bridges", params={"method": "nope"}),
    lambda: client.get("/api/bridge/bridges", params={"cue": "nope"}),
    lambda: client.post("/api/bridge/compare", json={"pmids": ["1"]}),
    lambda: client.post("/api/bridge/compare", json={"pmids": ["1", "2", "3", "4", "5"]}),
    lambda: client.post("/api/bridge/compare", json={"pmids": ["../etc"]}),
    lambda: client.post("/api/bridge/export", json={"kind": "search", "format": "exe", "q": "x"}),
])
def test_invalid_requests_are_rejected(call):
    assert call().status_code == 422


def test_frontend_assets_served():
    page = client.get("/")
    assert page.status_code == 200 and 'id="view-bridge"' in page.text
    assert client.get("/static/bridge.js").status_code == 200
