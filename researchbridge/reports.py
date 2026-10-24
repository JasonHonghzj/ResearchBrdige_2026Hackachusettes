"""Shared source-backed content for the UI and all export formats."""
from researchbridge.core import citation, evidence_excerpt
from researchbridge.discovery import METHODS, label
from researchbridge.i18n import translator, TOPIC_KEYS
from researchbridge.insights import FIELDS, compare_papers
from researchbridge.queries import canonical_query


def labels(kind, values, lang):
    T = translator(lang)
    if kind == "tags":
        return " / ".join(T(TOPIC_KEYS.get(x,"other")) for x in values) or T("not_identified")
    entries = FIELDS if kind == "fields" else METHODS
    return " / ".join(label(entries[x],lang) for x in values) or T("not_identified")


def paper_report(papers, query, lang, context, bridge=False):
    T = translator(lang)
    sections = [{"heading":T("export_context"),"paragraphs":[query,context,T("source_language")]}]
    if canonical_query(query) != query:
        sections[0]["paragraphs"].append(T("expansion",query=canonical_query(query)))
    rows = []
    for paper in papers:
        excerpt = evidence_excerpt(paper,canonical_query(query))
        paragraphs = [citation(paper)]
        if paper.get("score") is not None:
            paragraphs.append(T("bridge_rank" if bridge else "score",score=paper["score"]))
        if paper.get("method_evidence"):
            paragraphs.extend([T("method_evidence")+": "+paper["method_evidence"]["text"],T("cue_evidence")+": "+paper["bridge_evidence"]["text"]] if paper.get("bridge_evidence") else [paper["method_evidence"]["text"]])
        elif excerpt:
            paragraphs.append(excerpt)
        sections.append({"heading":paper["title"],"paragraphs":paragraphs})
        rows.append({"pmid":paper["pmid"],"title":paper["title"],"journal":paper["journal"],"score":paper.get("score"),"query":query,"retrieval_query":canonical_query(query),"score_context":context,"tags":labels("tags",paper["topics"],lang),"source_excerpt":excerpt,"method_evidence":paper.get("method_evidence",{}).get("text",""),"bridge_evidence":(paper.get("bridge_evidence") or {}).get("text",""),"source_url":paper["source_url"]})
    return sections, rows


def comparison_report(index, papers, lang):
    T = translator(lang)
    report = compare_papers(index,papers)
    sections = [{"heading":T("compare_title"),"paragraphs":[T("comparison_formula"),T("profile_note")]}]
    rows = []
    for paper in papers:
        p = report["profiles"][paper["pmid"]]
        row = {"row_type":"paper","pmid":paper["pmid"],"title":paper["title"],"tags":labels("tags",p["tags"],lang),"fields":labels("fields",p["fields"],lang),"methods":labels("methods",p["methods"],lang),"publication_type":" / ".join(paper["publication_types"]),"source_url":paper["source_url"]}
        rows.append(row)
        paragraphs = [citation(paper)] + [T(k)+": "+row[k] for k in ("tags","fields","methods")]
        for kind in ("fields","methods"):
            for ident,evidence in p[kind].items():
                paragraphs.append(labels(kind,[ident],lang)+": "+evidence["text"])
        sections.append({"heading":paper["title"],"paragraphs":paragraphs})
    pair_sections = []
    for pair in report["pairs"]:
        heading = f"PMID {pair['a']} / PMID {pair['b']}"
        paragraphs = [T("comparison_score")+f": {pair['score']:.3f}"]
        shared = [T(k)+": "+labels(k,pair["shared_"+k],lang) for k in ("tags","fields","methods") if pair["shared_"+k]]
        paragraphs.append(T("shared")+"\n"+("\n".join(shared) or T("none_shared")))
        for side,heading_key in (("a","paper_a"),("b","paper_b")):
            differences = [T(k)+": "+labels(k,pair[side+"_only_"+k],lang) for k in ("tags","fields","methods") if pair[side+"_only_"+k]]
            paragraphs.append(T("differences")+" - "+T(heading_key)+"\n"+("\n".join(differences) or T("no_unique_items")))
        paragraphs.append(T("shared_terms")+": "+(", ".join(pair["shared_terms"]) or T("none_shared")))
        if pair["limited_abstract"]:
            paragraphs.append(T("limited_pair"))
        pair_sections.append({"heading":heading,"paragraphs":paragraphs})
        rows.append({"row_type":"pair","pmid_a":pair["a"],"pmid_b":pair["b"],"correlation_score_cosine":pair["score"],"score_definition":T("comparison_formula"),"shared_terms":", ".join(pair["shared_terms"]),"similarities":paragraphs[1],"differences_a":paragraphs[2],"differences_b":paragraphs[3],"limited_abstract":pair["limited_abstract"]})
    return report, sections + pair_sections, rows, pair_sections


def bridge_relations_report(index, papers, lang, total=None):
    """Unique document-to-document pairs for the Bridge papers currently shown."""
    T = translator(lang)
    pairs = compare_papers(index,papers)["pairs"]
    ranks = {p["pmid"]:n for n,p in enumerate(papers,1)}
    sections = [{"heading":T("bridge_pair_title"),"paragraphs":[
        T("bridge_pair_scope",shown=len(papers),total=len(papers) if total is None else total,pairs=len(pairs)),
        T("comparison_formula"),
    ]}]
    legend = [f"{ranks[p['pmid']]:02d} · PMID {p['pmid']} · {p['title']} · {p['source_url']}" for p in papers]
    sections[0]["paragraphs"].extend(legend)
    rows = []
    for pair in pairs:
        row = {"row_type":"bridge_pair","rank_a":ranks[pair["a"]],"rank_b":ranks[pair["b"]],
               "pmid_a":pair["a"],"pmid_b":pair["b"],"paper_similarity_cosine":pair["score"],
               "shared_terms":", ".join(pair["shared_terms"]),"limited_abstract":pair["limited_abstract"],
               "compared_papers":len(papers),"total_matching_papers":len(papers) if total is None else total,
               "score_definition":T("comparison_formula")}
        rows.append(row)
        paragraphs = [T("bridge_pair_score")+f": {pair['score']:.3f}",
                      T("shared_terms")+": "+(row["shared_terms"] or T("none_shared"))]
        if pair["limited_abstract"]:
            paragraphs.append(T("limited_pair"))
        sections.append({"heading":f"{row['rank_a']:02d} - {row['rank_b']:02d} · PMID {pair['a']} / {pair['b']}","paragraphs":paragraphs})
    return pairs, sections, rows


def markdown_sections(text):
    sections = []
    current = {"heading":"ResearchBridge","paragraphs":[]}
    for line in text.splitlines():
        if line.startswith("#"):
            if current["paragraphs"]:
                sections.append(current)
            current = {"heading":line.lstrip("# "),"paragraphs":[]}
        elif line.strip():
            current["paragraphs"].append(line.lstrip("> "))
    if current["paragraphs"]:
        sections.append(current)
    return sections
