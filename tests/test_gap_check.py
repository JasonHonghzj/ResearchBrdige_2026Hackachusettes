"""The live novelty check, with PubMed stubbed.

The guard these tests exist for: an unrecognised descriptor matches no papers,
so maturity and gap both come back 0. Without an explicit check that each term
is indexed at all, the verdict would read like a pristine research gap for a
disease that does not exist. That is the single most embarrassing thing this
tool could do, so it is pinned here.
"""
import pytest
from fastapi.testclient import TestClient

from app import app
from gapfinder import confirm

client = TestClient(app)


@pytest.fixture
def counts(monkeypatch, tmp_path):
    """Route every PubMed count through a dict, and isolate the cache."""
    table: dict[str, int] = {}
    monkeypatch.setattr(confirm, "CHECK_CACHE", tmp_path / "check.json")
    monkeypatch.setattr(confirm, "CACHE", tmp_path / "saved-counts.json")
    monkeypatch.setattr(confirm, "THROTTLE", 0)
    monkeypatch.setattr(confirm, "_count", lambda term, **kwargs: table.get(term, 0))
    return table


def q(term):
    return f'"{term}"[MeSH Terms]'


def pair(p, m):
    return f"{q(p)} AND {q(m)}"


def test_established_method_with_no_early_detection_use_is_a_gap(counts):
    counts[q("Obesity")] = 200_000
    counts[q("Polymerase Chain Reaction")] = 400_000
    counts[pair("Obesity", "Polymerase Chain Reaction")] = 2403
    # the early-detection conjunction stays 0
    r = client.get("/api/gap/check",
                   params={"problem": "Obesity", "method": "Polymerase Chain Reaction"})
    assert r.status_code == 200
    d = r.json()
    assert d["maturity"] == 2403 and d["gap_papers"] == 0 and d["real_gap"] is True
    assert "2,403 times" in d["verdict"] and "never" in d["verdict"]
    # the queries must be reproducible by hand
    assert d["queries"]["maturity"] == pair("Obesity", "Polymerase Chain Reaction")
    assert "Early Detection of Cancer" in d["queries"]["gap"]


def test_already_studied_pairing_is_not_a_gap(counts):
    counts[q("Breast Neoplasms")] = 300_000
    counts[q("Mammography")] = 40_000
    counts[pair("Breast Neoplasms", "Mammography")] = 29_166
    counts[f'{pair("Breast Neoplasms", "Mammography")} AND {confirm.TOPIC}'] = 5874
    d = client.get("/api/gap/check",
                   params={"problem": "Breast Neoplasms", "method": "Mammography"}).json()
    assert d["real_gap"] is False
    assert d["verdict"].startswith("Not a gap")


def test_unrecognised_disease_is_not_reported_as_a_gap(counts):
    """A misspelling must not read as pristine territory."""
    counts[q("Mass Spectrometry")] = 100_000
    # nothing registered for the misspelled problem, so it counts 0
    r = client.get("/api/gap/check",
                   params={"problem": "Pankreatik Cancer", "method": "Mass Spectrometry"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "not indexed in MeSH" in detail["error"] and "problem" in detail["error"]
    assert "spelling" in detail["detail"]
    assert "real_gap" not in detail


def test_unrecognised_method_is_rejected_too(counts):
    counts[q("Sepsis")] = 90_000
    r = client.get("/api/gap/check",
                   params={"problem": "Sepsis", "method": "Raman Spectrum Analysis"})
    assert r.status_code == 422
    assert "method" in r.json()["detail"]["error"]


@pytest.mark.parametrize("bad", [
    'Obesity"[All Fields] OR "x',      # query injection via a quote
    "Obesity[MeSH] AND x",             # bracket
    "a",                               # too short for the endpoint
    "x" * 101,                         # too long for the endpoint
])
def test_terms_that_could_rewrite_the_query_are_refused(counts, bad):
    r = client.get("/api/gap/check", params={"problem": bad, "method": "Mass Spectrometry"})
    assert r.status_code == 422


def test_zero_maturity_is_flagged_as_untried_not_promising(counts):
    counts[q("Parkinson Disease")] = 100_000
    counts[q("Breath Tests")] = 9_000
    # both terms exist but have never been combined at all
    d = client.get("/api/gap/check",
                   params={"problem": "Parkinson Disease", "method": "Breath Tests"}).json()
    assert d["maturity"] == 0 and d["real_gap"] is True
    assert "at all" in d["verdict"] and "there may be a reason" in d["verdict"]


def test_thin_evidence_is_called_thin(counts):
    counts[q("Sepsis")] = 90_000
    counts[q("Metabolomics")] = 30_000
    counts[pair("Sepsis", "Metabolomics")] = 12
    d = client.get("/api/gap/check",
                   params={"problem": "Sepsis", "method": "Metabolomics"}).json()
    assert d["real_gap"] is True and d["verdict"].startswith("Thin")


def test_second_identical_check_is_served_from_cache(counts):
    counts[q("Obesity")] = 200_000
    counts[q("Genomics")] = 50_000
    counts[pair("Obesity", "Genomics")] = 500
    p = {"problem": "Obesity", "method": "Genomics"}
    assert client.get("/api/gap/check", params=p).json()["cached"] is False
    assert client.get("/api/gap/check", params=p).json()["cached"] is True
    # fresh=true bypasses it
    assert client.get("/api/gap/check", params={**p, "fresh": "true"}).json()["cached"] is False


def test_terms_endpoint_offers_the_real_descriptor_spellings():
    t = client.get("/api/gap/terms").json()
    assert len(t["problems"]) == 50 and len(t["methods"]) == 32
    # MeSH inverts names; the endpoint must serve the inverted form, not prose
    assert "Spectrum Analysis, Raman" in t["methods"]
    assert "Raman Spectrum Analysis" not in t["methods"]


def test_cached_pair_ignores_case_and_repeated_spaces(counts, monkeypatch):
    counts[q("Stroke")] = 200_000
    counts[q("Machine Learning")] = 100_000
    counts[pair("Stroke", "Machine Learning")] = 1452
    counts[f'{pair("Stroke", "Machine Learning")} AND {confirm.TOPIC}'] = 13
    client.get("/api/gap/check", params={"problem": "Stroke", "method": "Machine Learning"})

    def no_network(*args, **kwargs):
        pytest.fail("A differently capitalized saved pairing must not need PubMed")

    monkeypatch.setattr(confirm, "_count", no_network)
    response = client.get("/api/gap/check", params={"problem": " stroke ", "method": "Machine   learning"})
    assert response.status_code == 200
    assert response.json()["cached"] is True
    assert response.json()["gap_papers"] == 13


def test_saved_verification_works_offline_for_already_studied_pair(counts, monkeypatch):
    import json
    confirm.CACHE.write_text(json.dumps({"Stroke|Machine Learning": {"maturity": 1452, "gap_papers": 13}}))

    def no_network(*args, **kwargs):
        pytest.fail("Committed query counts should work offline")

    monkeypatch.setattr(confirm, "_count", no_network)
    response = client.get("/api/gap/check", params={"problem": "Stroke", "method": "Machine learning"})
    assert response.status_code == 200
    data = response.json()
    assert data["data_source"] == "saved_verification" and data["cached"] is True
    assert data["checked_utc"] is None and data["real_gap"] is False


def test_pubmed_outage_is_service_error_not_invalid_pair(counts, monkeypatch):
    calls = []

    def unavailable(term, **kwargs):
        calls.append(term)
        return None

    monkeypatch.setattr(confirm, "_count", unavailable)
    response = client.get("/api/gap/check", params={"problem": "Stomach Neoplasms", "method": "Breath Tests"})
    assert response.status_code == 503
    data = response.json()["detail"]
    assert data["error_code"] == "pubmed_unavailable" and data["retryable"] is True
    assert "real_gap" not in data and len(calls) == 1
    assert data["queries"]["maturity"] == pair("Stomach Neoplasms", "Breath Tests")


def test_failed_refresh_returns_explicitly_labeled_saved_result(counts, monkeypatch):
    import json
    confirm.CACHE.write_text(json.dumps({"Stroke|Machine Learning": {"maturity": 1452, "gap_papers": 13}}))
    monkeypatch.setattr(confirm, "_count", lambda *args, **kwargs: None)
    response = client.get("/api/gap/check", params={"problem": "Stroke", "method": "Machine Learning", "fresh": True})
    assert response.status_code == 200
    data = response.json()
    assert data["refresh_failed"] is True and data["cached"] is True
    assert data["gap_papers"] == 13 and data["checked_utc"] is None
    assert "not been refreshed" in data["refresh_error"]


def test_explicit_refresh_queries_pubmed_instead_of_snapshot(counts):
    import json
    confirm.CACHE.write_text(json.dumps({"Stroke|Machine Learning": {"maturity": 1452, "gap_papers": 13}}))
    counts[q("Stroke")] = 200_000
    counts[q("Machine Learning")] = 100_000
    counts[pair("Stroke", "Machine Learning")] = 1500
    counts[f'{pair("Stroke", "Machine Learning")} AND {confirm.TOPIC}'] = 14
    data = client.get("/api/gap/check", params={"problem": "Stroke", "method": "Machine Learning", "fresh": True}).json()
    assert data["cached"] is False and data["gap_papers"] == 14
    assert data["checked_utc"]


def test_pubmed_count_stops_at_shared_deadline(monkeypatch):
    now = [0.0]
    calls = []
    monkeypatch.setattr(confirm.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(confirm.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))

    def timeout(*args, **kwargs):
        calls.append(kwargs["timeout"])
        now[0] += sum(kwargs["timeout"])
        raise confirm.requests.Timeout()

    monkeypatch.setattr(confirm._session, "get", timeout)
    assert confirm._count(q("Stroke"), deadline=1.0) is None
    assert len(calls) == 1 and now[0] <= 1.0
