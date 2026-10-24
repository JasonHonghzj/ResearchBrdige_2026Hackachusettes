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
from scout import confirm

client = TestClient(app)


@pytest.fixture
def counts(monkeypatch, tmp_path):
    """Route every PubMed count through a dict, and isolate the cache."""
    table: dict[str, int] = {}
    monkeypatch.setattr(confirm, "CHECK_CACHE", tmp_path / "check.json")
    monkeypatch.setattr(confirm, "THROTTLE", 0)
    monkeypatch.setattr(confirm, "_count", lambda term: table.get(term, 0))
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
    r = client.get("/api/scout/check",
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
    d = client.get("/api/scout/check",
                   params={"problem": "Breast Neoplasms", "method": "Mammography"}).json()
    assert d["real_gap"] is False
    assert d["verdict"].startswith("Not a gap")


def test_unrecognised_disease_is_not_reported_as_a_gap(counts):
    """A misspelling must not read as pristine territory."""
    counts[q("Mass Spectrometry")] = 100_000
    # nothing registered for the misspelled problem, so it counts 0
    r = client.get("/api/scout/check",
                   params={"problem": "Pankreatik Cancer", "method": "Mass Spectrometry"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "not indexed in MeSH" in detail["error"] and "problem" in detail["error"]
    assert "spelling" in detail["detail"]
    assert "real_gap" not in detail


def test_unrecognised_method_is_rejected_too(counts):
    counts[q("Sepsis")] = 90_000
    r = client.get("/api/scout/check",
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
    r = client.get("/api/scout/check", params={"problem": bad, "method": "Mass Spectrometry"})
    assert r.status_code == 422


def test_zero_maturity_is_flagged_as_untried_not_promising(counts):
    counts[q("Parkinson Disease")] = 100_000
    counts[q("Breath Tests")] = 9_000
    # both terms exist but have never been combined at all
    d = client.get("/api/scout/check",
                   params={"problem": "Parkinson Disease", "method": "Breath Tests"}).json()
    assert d["maturity"] == 0 and d["real_gap"] is True
    assert "at all" in d["verdict"] and "there may be a reason" in d["verdict"]


def test_thin_evidence_is_called_thin(counts):
    counts[q("Sepsis")] = 90_000
    counts[q("Metabolomics")] = 30_000
    counts[pair("Sepsis", "Metabolomics")] = 12
    d = client.get("/api/scout/check",
                   params={"problem": "Sepsis", "method": "Metabolomics"}).json()
    assert d["real_gap"] is True and d["verdict"].startswith("Thin")


def test_second_identical_check_is_served_from_cache(counts):
    counts[q("Obesity")] = 200_000
    counts[q("Genomics")] = 50_000
    counts[pair("Obesity", "Genomics")] = 500
    p = {"problem": "Obesity", "method": "Genomics"}
    assert client.get("/api/scout/check", params=p).json()["cached"] is False
    assert client.get("/api/scout/check", params=p).json()["cached"] is True
    # fresh=true bypasses it
    assert client.get("/api/scout/check", params={**p, "fresh": "true"}).json()["cached"] is False


def test_terms_endpoint_offers_the_real_descriptor_spellings():
    t = client.get("/api/scout/terms").json()
    assert len(t["problems"]) == 50 and len(t["methods"]) == 32
    # MeSH inverts names; the endpoint must serve the inverted form, not prose
    assert "Spectrum Analysis, Raman" in t["methods"]
    assert "Raman Spectrum Analysis" not in t["methods"]
