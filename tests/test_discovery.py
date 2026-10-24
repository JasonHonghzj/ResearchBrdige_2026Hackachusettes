import pytest
from researchbridge.core import SearchIndex, load_data, expand_query
from researchbridge.discovery import METHODS, CUES, bridge_papers, recommend_methods, matches, check_claims, make_brief

@pytest.fixture(scope="module")
def index():
    return SearchIndex(load_data()[0])

def test_range_is_inclusive_and_applied_before_limit(index):
    all_results = index.search("large language model", limit=60)[0]
    score = all_results[1]["score"]
    selected = index.search("large language model", score_range=(score,score), limit=1)[0]
    assert selected and selected[0]["pmid"] == all_results[1]["pmid"]
    assert index.search("large language model",score_range=(0.99,1))[0] == []
    with pytest.raises(ValueError):
        index.search("test",score_range=(0.8,0.2))

def test_candidate_filter_and_empty_query(index):
    result = index.search("large language model",candidate_pmids={"40963721"})[0]
    assert [p["pmid"] for p in result] == ["40963721"]
    assert index.search("",score_range=(0.1,1))[0] == []

@pytest.mark.parametrize("query",["alfabetización sobre medicamentos","ALFABETIZACION SOBRE MEDICAMENTOS"])
def test_spanish_query_expansion(index,query):
    assert "medication literacy" in expand_query(query)[0]
    assert index.search(query)[0][0]["pmid"] == "41726533"

def test_goal_method_bridge_returns_actual_different_sources(index):
    goals = index.search("用藥素養",limit=60)[0]
    assert recommend_methods(goals)[0]["id"] == "llm"
    privacy, query = bridge_papers(index,"llm","privacy",limit=60)
    medication, _ = bridge_papers(index,"llm","medication",limit=60)
    assert "privacy" in query
    assert "40963721" in {p["pmid"] for p in privacy}
    assert "40963721" not in {p["pmid"] for p in goals}
    assert {p["pmid"] for p in privacy} != {p["pmid"] for p in medication}
    for p in privacy:
        assert matches(p,METHODS["llm"]) and matches(p,CUES["privacy"])
        for field in ["method_evidence","bridge_evidence"]:
            assert p[field]["text"] in p["title"]+p["abstract"]
    assert bridge_papers(index,"llm","privacy",score_range=(0.99,1))[0] == []

def test_literal_checks_preserve_uncertainty(index):
    p = next(p for p in index.papers if p["pmid"]=="41726533")
    exact = p["sections"][0]["text"]
    reports = check_claims(exact+"\nThis chatbot definitely cures all diseases.",[p])
    assert reports[0]["status"] == "literal_match"
    assert reports[0]["sources"][0]["pmid"] == p["pmid"]
    assert reports[-1]["status"] == "review_required"

@pytest.mark.parametrize("lang",["zh","en","es"])
def test_brief_has_real_sources_and_no_placeholder(index,lang):
    papers,_ = bridge_papers(index,"llm","privacy")
    brief = make_brief("medication literacy","llm","privacy",papers,lang)
    assert "40963721" in brief
    assert papers[0]["bridge_evidence"]["text"] in brief
    assert "00000000" not in brief
