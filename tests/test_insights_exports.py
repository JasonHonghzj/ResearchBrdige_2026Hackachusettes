from io import BytesIO
import pytest
from pypdf import PdfReader
from researchbridge.core import load_data, SearchIndex
from researchbridge.insights import compare_papers, recommended_keywords, profile
from researchbridge.reports import comparison_report, paper_report
from researchbridge.exports import export_bytes, csv_bytes, html_bytes

@pytest.fixture(scope="module")
def data():
    papers,_ = load_data()
    return SearchIndex(papers),{p["pmid"]:p for p in papers}

def test_pairwise_cosine_is_symmetric_and_traceable(data):
    index, by_id = data
    selected = [by_id["41726533"],by_id["41726516"]]
    result = compare_papers(index,selected)
    pair = result["pairs"][0]
    reverse = compare_papers(index,list(reversed(selected)))["pairs"][0]
    assert 0<=pair["score"]<=1 and pair["score"] == pytest.approx(reverse["score"])
    assert pair["shared_methods"] == ["llm"]
    assert pair["shared_terms"]
    assert compare_papers(index,[selected[0],selected[0]])["pairs"][0]["score"] == pytest.approx(1)
    for p in selected:
        details = profile(p)
        for kind in ("fields","methods"):
            for evidence in details[kind].values():
                assert evidence["text"] in p["title"]+p["abstract"]

def test_missing_abstract_flag_and_unique_differences(data):
    index, by_id = data
    a = by_id["41726533"]
    b = next(p for p in index.papers if not p["abstract"])
    pair = compare_papers(index,[a,b])["pairs"][0]
    assert pair["limited_abstract"]
    assert not (set(pair["a_only_methods"]) & set(pair["shared_methods"]))

def test_keyword_counts_come_from_current_pool(data):
    index,_ = data
    suggestions = recommended_keywords(index.papers)
    assert len(suggestions)==6
    assert all(x["count"]==len(set(x["pmids"])) for x in suggestions)
    tiny = [p for p in index.papers if p["pmid"]=="41726533"]
    assert all(x["count"]==1 and x["pmids"]==["41726533"] for x in recommended_keywords(tiny))
    assert recommended_keywords([])==[]

@pytest.mark.parametrize("lang",["zh","en","es"])
def test_all_export_formats_preserve_comparison_content(data,lang):
    index,by_id = data
    _,sections,rows,_ = comparison_report(index,[by_id["41726533"],by_id["41726516"]],lang)
    for fmt in ("csv","html","pdf"):
        content,mime = export_bytes("ResearchBridge 比較 / Comparación",sections,rows,fmt,lang)
        assert content
        if fmt=="pdf":
            reader=PdfReader(BytesIO(content))
            text="\n".join(p.extract_text() for p in reader.pages)
            assert "41726533" in text and "41726516" in text
            fonts=reader.pages[0]["/Resources"]["/Font"].get_object().values()
            assert any(font.get_object().get("/FontDescriptor") and "/FontFile2" in font.get_object()["/FontDescriptor"].get_object() for font in fonts)
        else:
            decoded=content.decode("utf-8-sig")
            assert "41726533" in decoded and "41726516" in decoded
            assert "cosine" in decoded or "coseno" in decoded

def test_exports_escape_user_text_and_spreadsheet_formulas():
    assert b"<script>" not in html_bytes("<script>alert(1)</script>",[{"heading":"<h1>","paragraphs":["<img src=x>"]}])
    assert "'=1+1" in csv_bytes([{"query":"=1+1"}]).decode("utf-8-sig")
    assert "0.35" in csv_bytes([{"score":0.35}]).decode("utf-8-sig")

def test_three_bridge_results_have_exactly_three_unique_document_pairs(data):
    from researchbridge.reports import bridge_relations_report
    index,by_id=data
    selected=[by_id[x] for x in ("40963721","41726516","41726533")]
    pairs,sections,rows=bridge_relations_report(index,selected,"zh",total=6)
    assert len(pairs)==len(rows)==3
    assert {(r["rank_a"],r["rank_b"]) for r in rows}=={(1,2),(1,3),(2,3)}
    expected=compare_papers(index,selected)["pairs"]
    assert [r["paper_similarity_cosine"] for r in rows]==pytest.approx([p["score"] for p in expected])
    assert all(r["pmid_a"]!=r["pmid_b"] for r in rows)
    assert "3／6" in sections[0]["paragraphs"][0]
    assert all(r["row_type"]=="bridge_pair" for r in rows)
    assert "40963721" in " ".join(sections[0]["paragraphs"])


@pytest.mark.parametrize("size",[0,1])
def test_fewer_than_two_bridge_results_do_not_invent_a_score(data,size):
    from researchbridge.reports import bridge_relations_report
    index,_=data
    pairs,_,rows=bridge_relations_report(index,index.papers[:size],"en")
    assert pairs==rows==[]


@pytest.mark.parametrize("lang",["zh","en","es"])
def test_bridge_pair_exports_include_pair_scores(data,lang):
    from researchbridge.reports import bridge_relations_report
    from researchbridge.i18n import translator
    index,by_id=data
    selected=[by_id[x] for x in ("40963721","41726516","41726533")]
    _,sections,rows=bridge_relations_report(index,selected,lang)
    for fmt in ("csv","html","pdf"):
        content,_=export_bytes(translator(lang)("bridge_pair_title"),sections,rows,fmt,lang)
        text="\n".join(p.extract_text() for p in PdfReader(BytesIO(content)).pages) if fmt=="pdf" else content.decode("utf-8-sig")
        assert "40963721" in text and "41726533" in text
        if fmt=="csv":
            assert "paper_similarity_cosine" in text
        else:
            assert f"{rows[0]['paper_similarity_cosine']:.3f}" in text
