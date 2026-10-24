import pytest
from researchbridge.core import SearchIndex, load_data
from researchbridge.discovery import METHODS, CUES
from researchbridge.queries import LEGACY_QUERIES, canonical_query, localize_query

@pytest.mark.parametrize("entry",list(LEGACY_QUERIES.values())+list(METHODS.values())+list(CUES.values()))
def test_all_builtin_queries_translate_and_keep_the_same_retrieval_query(entry):
    for source in (*entry["labels"],entry["query"],*entry.get("aliases",())):
        for language,label in zip(("zh","en","es"),entry["labels"]):
            assert localize_query(source,language)==label
            assert canonical_query(label)==entry["query"]


def test_custom_queries_are_preserved_verbatim():
    query="請研究 LLM privacy 在 65 歲以上患者的應用"
    for language in ("zh","en","es"):
        assert localize_query(query,language)==query
    assert canonical_query(query)==query


def test_canonical_care_query_retains_care_context_guard():
    index=SearchIndex(load_data()[0])
    ids={p["pmid"] for p in index.search(canonical_query("transición de cuidados"),limit=60)[0]}
    assert "41726541" in ids
    assert "41103975" not in ids and "41367935" not in ids
