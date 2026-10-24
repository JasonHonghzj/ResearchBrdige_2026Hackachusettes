import csv
import json
from pathlib import Path

import pytest

from researchbridge.core import (
    DB_PATH, ROOT, SearchIndex, build_database, evidence_excerpt, expand_query,
    load_data, parse_pubmed, verified_work, work_links,
)


@pytest.fixture(scope="module")
def data():
    return load_data()


@pytest.fixture(scope="module")
def index(data):
    return SearchIndex(data[0])


def test_all_starter_records_preserved(data):
    papers, institutions = data
    assert len(papers) == len({p["pmid"] for p in papers}) == 60
    assert len(institutions) == 135
    assert sum(p["has_abstract"] for p in papers) == 56
    assert all(p["source_url"].endswith(p["pmid"] + "/") for p in papers)


def test_rebuild_is_repeatable_and_original_csv_unchanged(tmp_path):
    before = (ROOT / "pubmed" / "data.csv").read_bytes()
    target = tmp_path / "test.sqlite"
    first = build_database(target)
    second = build_database(target)
    assert first == second
    assert (ROOT / "pubmed" / "data.csv").read_bytes() == before
    assert len(load_data(target)[0]) == 60


def test_no_model_findings_for_missing_abstract(data):
    missing = [p for p in data[0] if not p["has_abstract"]]
    assert missing
    assert all(evidence_excerpt(p, "clinical results") == "" for p in missing)


def test_excerpt_is_exact_source_text(data):
    p = next(p for p in data[0] if p["pmid"] == "41726533")
    excerpt = evidence_excerpt(p, "medication literacy", count=1)
    assert excerpt
    assert any(excerpt in section["text"] for section in p["sections"])


def test_bilingual_query_is_explicit(index):
    expanded, matched = expand_query("用藥素養")
    assert "medication literacy" in expanded
    assert matched == ["用藥素養"]
    results, _, _ = index.search("用藥素養", limit=5)
    assert results[0]["pmid"] == "41726533"


@pytest.mark.parametrize("mode", ["tfidf", "hybrid"])
def test_unknown_query_does_not_return_spurious_results(index, mode):
    assert index.search("zzxq987654xyz", mode=mode)[0] == []
    assert index.search("沒有詞彙對照的問題", mode=mode)[0] == []


def test_filters_apply_before_limit(index, data):
    journal = next(p["journal"] for p in data[0] if p["pmid"] == "41726533")
    matches, _, _ = index.search("", journal=journal, require_abstract=True, limit=60)
    expected = [p for p in data[0] if p["journal"] == journal and p["has_abstract"]]
    assert {p["pmid"] for p in matches} == {p["pmid"] for p in expected}
    assert all(p["score"] is None for p in matches)


def test_care_transition_query_excludes_noncare_transition_matches(index):
    results, _, _ = index.search("照護銜接", limit=60)
    ids = {p["pmid"] for p in results}
    assert "41726541" in ids
    assert "41103975" not in ids  # quantum spin transitions
    assert "41367935" not in ids  # environmental community responses


def test_no_author_name_inference_and_no_duplicate_affiliations():
    inst = {"id": "https://openalex.org/I123", "display_name": "Harvard University", "country_code": "US"}
    work = {"id": "https://openalex.org/W123", "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/123"}, "authorships": [{"institutions": [inst]}, {"institutions": [inst]}]}
    directory = [{"institution": "Harvard University", "city": "Cambridge"}]
    assert verified_work(work, "123")
    assert not verified_work(work, "999")
    assert work_links(work, "999", directory) == []
    links = work_links(work, "123", directory)
    assert len(links) == 1
    assert links[0]["city"] == "Cambridge"
    assert links[0]["source_url"] == "https://openalex.org/W123"
    assert work_links({"authorships": work["authorships"]}, "123", directory) == []


def test_external_affiliations_are_not_falsely_assigned_to_directory():
    work = {"id": "https://openalex.org/W123", "ids": {"pmid": "123"}, "authorships": [{"institutions": [{"id": "https://openalex.org/I123", "display_name": "Harvard Medical School"}]}]}
    result = work_links(work, "123", [{"institution": "Harvard University", "city": "Cambridge"}])[0]
    assert result["city"] == result["directory_name"] == ""


def test_pubmed_parser_preserves_multiple_dates():
    xml = b'''<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>A <i>test</i> paper</ArticleTitle><Journal><JournalIssue><PubDate><Year>2026</Year><Month>Feb</Month></PubDate></JournalIssue></Journal><ArticleDate DateType="Electronic"><Year>2025</Year><Month>12</Month><Day>01</Day></ArticleDate><Abstract><AbstractText Label="RESULTS">Observed source statement.</AbstractText></Abstract></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">10.123/example</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>'''
    p = parse_pubmed(xml)["123"]
    assert p["title"] == "A test paper"
    assert p["dates"] == [{"kind": "journal", "value": "2026 Feb"}, {"kind": "Electronic", "value": "2025 12 01"}]
    assert p["doi"] == "10.123/example"
    assert p["sections"][0]["label"] == "RESULTS"


def test_all_cached_links_have_an_exact_pmid(data):
    for p in data[0]:
        for link in p["institutions"]:
            snapshot = ROOT / "data" / "snapshots" / "openalex" / f"{p['pmid']}.json"
            work = json.loads(snapshot.read_text(encoding="utf-8"))["record"]
            assert verified_work(work, p["pmid"])
            assert link["verification"] == "exact_pmid_openalex_affiliation"

