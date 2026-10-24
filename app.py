"""ResearchBridge: local, source-backed research exploration."""
from __future__ import annotations
import html
import json
from pathlib import Path
import streamlit as st
from researchbridge.core import DB_PATH, TOPICS, SearchIndex, build_database, citation, evidence_excerpt, load_data
from researchbridge.discovery import METHODS, CUES, available_cues, bridge_papers, check_claims, label, make_brief, matches, recommend_methods
from researchbridge.i18n import LANG_NAMES, TOPIC_KEYS, translator
from researchbridge.style import css
from researchbridge.insights import FIELDS, recommended_keywords
from researchbridge.reports import labels, paper_report, comparison_report, bridge_relations_report, markdown_sections
from researchbridge.exports import export_bytes
from researchbridge.queries import canonical_query, localize_query

TAB_KEYS = ("tab_search", "tab_bridges", "tab_compare", "tab_check", "tab_brief", "tab_directory", "tab_data")

st.set_page_config(page_title="ResearchBridge", page_icon="🔎", layout="wide")

@st.cache_data(show_spinner=False)
def read_data(signature):
    return load_data()

@st.cache_resource(show_spinner=False)
def search_index(signature, _papers):
    return SearchIndex(_papers)

def set_query(value):
    st.session_state["search_query"] = value
    st.session_state["bridge_search_query"] = value
    st.query_params["q"] = value

def submit_query(source_key):
    # Form callbacks run before either page renders, keeping recommendations current.
    set_query(st.session_state[source_key])

def change_language():
    new = st.session_state["language"]
    current = st.session_state.get("search_query", "")
    translated = localize_query(current, new)
    if translated != current:
        set_query(translated)

def remember_active_tab(language):
    translate = translator(language)
    selected = st.session_state["navigation_tabs"]
    st.session_state["active_tab"] = next(key for key in TAB_KEYS if translate(key) == selected)

def toggle_saved(pmid):
    selected = list(st.session_state.get("comparison", []))
    if pmid in selected:
        selected.remove(pmid)
    elif len(selected) < 4:
        selected.append(pmid)
    st.session_state["comparison"] = selected

def sync_slider():
    st.session_state["score_min"], st.session_state["score_max"] = st.session_state["score_range"]

def sync_bounds():
    lo, hi = st.session_state["score_min"], st.session_state["score_max"]
    if lo <= hi:
        st.session_state["score_range"] = (lo, hi)

def choose_method(ident):
    st.session_state["method_choice"] = ident
    st.session_state["method_choice_" + st.session_state["language"]] = ident
    st.session_state["bridge_choice"] = "all"
    st.session_state["bridge_choice_" + st.session_state["language"]] = "all"

def localized_choice(container, kind, title, options, key, format_func, **kwargs):
    # Remount translated options: the browser otherwise retains old display labels.
    widget_key = key + "_" + lang
    st.session_state[widget_key] = st.session_state.get(key, options[0])
    def remember():
        st.session_state[key] = st.session_state[widget_key]
    return getattr(container, kind)(title, options, format_func=format_func, key=widget_key, on_change=remember, **kwargs)

@st.cache_data(show_spinner=False)
def render_export(title, sections, rows, file_format, language):
    return export_bytes(title,sections,rows,file_format,language)

def export_controls(prefix, title, sections, rows):
    with st.container(border=True):
        a,b = st.columns([1,2],vertical_alignment="bottom")
        fmt = a.selectbox(T("export_format"),["csv","pdf","html"],format_func=str.upper,key=prefix+"_format")
        data,mime = render_export(title,sections,rows,fmt,lang)
        b.download_button(T("export_download",format=fmt.upper()),data,f"researchbridge_{prefix}_{lang}.{fmt}",mime,key=prefix+"_download",width="stretch",on_click="ignore")

def table(rows, columns):
    headers = "".join(f"<th scope='col'>{html.escape(title)}</th>" for _, title in columns)
    def cell(row, key):
        attribute = " style='white-space:nowrap'" if key == "pmid" else ""
        return f"<td{attribute}>{html.escape(str(row.get(key, '')))}</td>"
    body = "".join("<tr>" + "".join(cell(row,key) for key,_ in columns) + "</tr>" for row in rows)
    sizing = " style='min-width:960px'" if len(columns)>4 else ""
    st.html(f"<div class='rb-table-wrap'><table class='rb-table'{sizing}><thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table></div>")

if not DB_PATH.exists():
    build_database()
signature = (DB_PATH.stat().st_mtime_ns, (Path(__file__).parent / "researchbridge/core.py").stat().st_mtime_ns)
papers, institutions = read_data(signature)
index = search_index(signature, papers)
by_id = {p["pmid"]: p for p in papers}
for key, value in {"language":"zh", "theme":"light", "search_query":st.query_params.get("q", "用藥素養"), "comparison":[], "score_range":(0.0,1.0), "score_min":0.0, "score_max":1.0, "method_choice":"auto", "bridge_choice":"all"}.items():
    if key not in st.session_state:
        st.session_state[key] = value
if "bridge_search_query" not in st.session_state:
    st.session_state["bridge_search_query"] = st.session_state["search_query"]
lang = st.session_state["language"]
T = translator(lang)
st.html(css(st.session_state["theme"]))
with st.container(key="toolbar"):
    lc, tc = st.columns([1.4,1.0],gap="small",vertical_alignment="center")
    lc.selectbox(T("language"),list(LANG_NAMES),format_func=LANG_NAMES.get,key="language",on_change=change_language)
    localized_choice(tc,"selectbox",T("theme"),["light","dark"],"theme",T)
with st.sidebar:
    st.markdown("## ResearchBridge")
    st.write(T("scope"))
    st.divider()
    mode = localized_choice(st, "radio", T("mode"), ["tfidf","hybrid"], "search_mode", T)
    st.caption(T("model_note"))
    topic = localized_choice(st, "selectbox", T("topic"), ["all"]+list(TOPICS), "topic", lambda x:T("all_topics") if x=="all" else T(TOPIC_KEYS.get(x,"other")))
    journal = localized_choice(st, "selectbox", T("journal"), ["all"]+sorted({p["journal"] for p in papers}), "journal", lambda x:T("all_journals") if x=="all" else x)
    only_abstract = st.checkbox(T("only_abstract"), key="only_abstract")
    only_links = st.checkbox(T("only_links"), key="only_links")
    st.divider()
    st.markdown("**"+T("range")+"**")
    st.slider(T("range"), 0.0, 1.0, step=0.01, key="score_range", on_change=sync_slider, label_visibility="collapsed")
    a,b = st.columns(2)
    low = a.number_input(T("lower"),0.0,1.0,step=0.01,key="score_min",on_change=sync_bounds)
    high = b.number_input(T("upper"),0.0,1.0,step=0.01,key="score_max",on_change=sync_bounds)
    valid_range = low <= high
    if not valid_range:
        st.error(T("invalid_range"))
    st.caption(T("range_note"))
    with st.expander(T("score_help")):
        st.write(T("score_explained"))
    limit = st.select_slider(T("limit"),options=[3,5,10,20,60],value=10,key="limit")
    st.divider()
    st.multiselect(T("comparison_select"),list(by_id),format_func=lambda x:by_id[x]["title"],max_selections=4,key="comparison")
    st.caption(T("tag_note"))
st.html(f"<div class='rb-kicker'>RESEARCHBRIDGE / EVIDENCE EXPLORER</div><div class='rb-hero'>{T('hero')}</div><div class='rb-sub'>{T('subtitle')}</div>")
abstract_count = sum(p["has_abstract"] for p in papers)
link_count = sum(p["institution_count"] for p in papers)
for col,key,value in zip(st.columns(4),["metric_papers","metric_abstracts","metric_links","metric_institutions"],[len(papers),abstract_count,link_count,len(institutions)]):
    col.metric(T(key),value)
# Keep a language-independent page ID; translated labels change widget identity.
active_tab = st.session_state.get("active_tab", "tab_search")
st.session_state["navigation_tabs"] = T(active_tab)
tabs = st.tabs([T(key) for key in TAB_KEYS],key="navigation_tabs",on_change=remember_active_tab,args=(lang,))
base_filters = dict(mode=mode,topic=None if topic=="all" else topic,journal=None if journal=="all" else journal,require_abstract=only_abstract,require_links=only_links,limit=len(papers))
filters = dict(**base_filters,score_range=(low,high))
pool = [p for p in papers if (topic=="all" or topic in p["topics"]) and (journal=="all" or journal==p["journal"]) and (not only_abstract or p["has_abstract"]) and (not only_links or p["institution_count"])]

def paper_card(paper,rank,query,prefix="search"):
    with st.container(border=True):
        a,b = st.columns([5,1])
        a.markdown(f"#### {rank:02d} · {paper['title']}")
        selected = paper["pmid"] in st.session_state["comparison"]
        key = f"save_{paper['pmid']}" if prefix=="search" else f"{prefix}_save_{paper['pmid']}"
        b.button(T("remove" if selected else "save"),key=key,on_click=toggle_saved,args=(paper["pmid"],),disabled=not selected and len(st.session_state["comparison"])>=4,width="stretch")
        st.caption(T("paper_meta",journal=paper["journal"],pmid=paper["pmid"],source=paper["metadata_source"]))
        tags = " / ".join(T(TOPIC_KEYS.get(x,"other")) for x in paper["topics"]) or T("other")
        st.caption(T("paper_tags",tags=tags,abstract=T("yes" if paper["has_abstract"] else "no"),links=paper["institution_count"]))
        if paper.get("score") is not None:
            st.caption(T("bridge_rank" if prefix=="bridge" else "score",score=paper["score"]))
        if prefix=="bridge":
            st.markdown("**"+T("bridge_evidence")+"**")
            for field,heading in [("method_evidence","method_evidence"),("bridge_evidence","cue_evidence")]:
                if paper.get(field):
                    st.caption(T(heading))
                    st.write(paper[field]["text"])
        else:
            excerpt = evidence_excerpt(paper,canonical_query(query))
            if excerpt:
                st.markdown("**"+T("excerpt")+"**")
                st.write(excerpt)
            else:
                st.info(T("no_abstract"))
        a,b = st.columns(2)
        a.link_button(T("pubmed"),paper["source_url"],width="stretch")
        if paper["doi"]:
            b.link_button(T("doi"),f"https://doi.org/{paper['doi']}",width="stretch")
        with st.expander(T("provenance")):
            for section in paper["sections"]:
                st.markdown(f"**{section['label']}**")
                st.write(section["text"])
            if paper["dates"]:
                table(paper["dates"],[("kind",T("date_type")),("value",T("date_value"))])
            st.caption(T("starter_date",date=paper["starter_published"]))
            if paper["starter_title"]!=paper["title"]:
                st.caption(T("starter_title",title=paper["starter_title"]))
            st.write(T("authors")+": "+paper["authors"])
            st.write(T("publication_type")+": "+(" / ".join(paper["publication_types"]) or T("unavailable")))
            if paper["mesh"]:
                st.write("PubMed MeSH: "+" / ".join(paper["mesh"]))
            st.caption(T("retrieved",date=paper["retrieved_at"] or T("unavailable")))
            if paper["affiliations"]:
                st.markdown("**"+T("pubmed_affiliations")+"**")
                for affiliation in paper["affiliations"]:
                    st.write(affiliation)
            st.code(citation(paper),language=None)
        with st.expander(T("affiliations",count=paper["institution_count"])):
            if not paper["institutions"]:
                st.write(T("no_links"))
            for inst in paper["institutions"]:
                st.markdown(f"**{inst['name']}**")
                st.caption((inst["country"] or T("unavailable"))+" · "+(T("directory_city",city=inst["city"]) if inst["city"] else T("not_directory")))
                st.write(inst["institution_id"])
                if inst["ror"]:
                    st.write("ROR: "+inst["ror"])
                st.link_button(T("work_source"),inst["source_url"],key=f"{prefix}_link_{paper['pmid']}_{inst['institution_id']}")
                st.caption(T("affiliation_note"))

with tabs[0]:
    st.markdown("### "+T("start"))
    with st.form("search_form"):
        a,b = st.columns([5,1],vertical_alignment="bottom")
        query = a.text_input(T("query"),key="search_query",placeholder=T("query_placeholder"))
        b.form_submit_button(T("search"),key="search_submit",type="primary",width="stretch",on_click=submit_query,args=("search_query",))
    st.markdown("**"+T("keywords")+"**")
    st.caption(T("keyword_note",count=len(pool)))
    suggestions = recommended_keywords(pool)
    for start in range(0,len(suggestions),3):
        for col,item in zip(st.columns(3),suggestions[start:start+3]):
            col.button(T("keyword_count",label=label(item["entry"],lang),count=item["count"]),key="keyword_"+item["id"],on_click=set_query,args=(localize_query(item["query"],lang),),width="stretch")
    effective_query = canonical_query(query)
    unthresholded_results,_,_ = index.search(effective_query,**base_filters) if query.strip() else ([],query,[])
    goal_results,expanded,matched = index.search(effective_query,**filters) if valid_range and query.strip() else ([],query,[])
    st.caption(T("range_active",low=low,high=high))
    st.caption(T("results",total=len(goal_results),shown=min(limit,len(goal_results))))
    if matched or effective_query != query:
        st.caption(T("expansion",query=expanded))
    st.caption(T("source_language"))
    if not query.strip():
        st.info(T("enter_goal"))
    elif valid_range and not goal_results:
        st.info(T("empty"))
    if goal_results:
        st.caption(T("export_scope",count=len(goal_results)))
        search_sections,search_rows = paper_report(goal_results,query,lang,T("range_active",low=low,high=high)+"\n"+T("score_explained"))
        export_controls("search",T("tab_search"),search_sections,search_rows)
    for rank,paper in enumerate(goal_results[:limit],1):
        paper_card(paper,rank,query)
with tabs[1]:
    st.markdown("### "+T("bridge_title"))
    st.write(T("bridge_intro"))
    with st.form("bridge_search_form"):
        a,b = st.columns([5,1],vertical_alignment="bottom")
        a.text_input(T("query"),key="bridge_search_query",placeholder=T("query_placeholder"))
        b.form_submit_button(T("search"),key="bridge_search_submit",type="primary",width="stretch",on_click=submit_query,args=("bridge_search_query",))
    st.caption(T("bridge_goal_note"))
    st.caption(T("bridge_independent"))
    recommendations = recommend_methods(unthresholded_results)
    st.markdown("**"+T("recommended")+"**")
    if recommendations:
        for col,rec in zip(st.columns(3),recommendations[:3]):
            with col,st.container(border=True):
                st.markdown("**"+label(METHODS[rec["id"]],lang)+"**")
                st.caption(T("method_support",count=rec["count"],score=rec["score"]))
                st.button(T("explore_method"),key="explore_"+rec["id"],on_click=choose_method,args=(rec["id"],))
    else:
        st.info(T("no_methods"))
    method_ids = [ident for ident,method in METHODS.items() if any(matches(p,method) for p in papers)]
    choice = localized_choice(st,"selectbox",T("choose_method"),["auto"]+method_ids,"method_choice",lambda x:T("auto_method") if x=="auto" else label(METHODS[x],lang))
    method_id = choice if choice!="auto" else (recommendations[0]["id"] if recommendations else method_ids[0])
    cues = available_cues(pool,method_id,unthresholded_results)
    cue_by_id = {c["id"]:c for c in cues}
    if st.session_state["bridge_choice"] not in ["all"]+list(cue_by_id):
        st.session_state["bridge_choice"] = "all"
    def cue_label(ident):
        if ident=="all":
            return T("all_cues")
        return label(CUES[ident],lang)
    cue_id = localized_choice(st,"selectbox",T("choose_bridge"),["all"]+list(cue_by_id),"bridge_choice",cue_label)
    if cue_id!="all":
        c = cue_by_id[cue_id]
        st.caption(T("shared_cue" if c["shared"] else "extension_cue"))
        st.caption(T("cue_counts",method=c["method_count"],goal=c["goal_count"]))
    nodes = [(T("goal_a"),query or "—"),(T("bridge_b"),label(CUES[cue_id],lang) if cue_id in CUES else T("all_cues")),(T("method_c"),label(METHODS[method_id],lang))]
    st.html("<div class='rb-chain'>"+"".join(f"<div class='rb-node'><small>{html.escape(h)}</small><strong>{html.escape(v)}</strong></div>" for h,v in nodes)+"</div>")
    bridge_results,bridge_query = bridge_papers(index,method_id,cue_id,**base_filters)
    st.caption(T("bridge_query",query=bridge_query))
    st.caption(T("results",total=len(bridge_results),shown=min(limit,len(bridge_results))))
    st.info(T("bridge_note"))
    visible_bridge_results = bridge_results[:limit]
    bridge_pairs,pair_sections,pair_rows = bridge_relations_report(index,visible_bridge_results,lang,total=len(bridge_results))
    st.markdown("### "+T("bridge_pair_title"))
    st.html(f"<p class='rb-example'>Ex: {html.escape(T('bridge_pair_intro'))}</p>")
    st.caption(T("bridge_pair_scope",shown=len(visible_bridge_results),total=len(bridge_results),pairs=len(bridge_pairs)))
    with st.expander(T("bridge_pair_formula")):
        st.write(T("comparison_formula"))
    if bridge_pairs:
        pair_display = [{"a":f"{row['rank_a']:02d} · PMID {row['pmid_a']}",
                         "b":f"{row['rank_b']:02d} · PMID {row['pmid_b']}",
                         "score":f"{row['paper_similarity_cosine']:.3f}"} for row in pair_rows]
        table(pair_display,[("a",T("paper_a")),("b",T("paper_b")),("score",T("bridge_pair_score"))])
        if any(pair["limited_abstract"] for pair in bridge_pairs):
            st.caption(T("limited_pair"))
    else:
        st.info(T("bridge_pair_minimum"))
    if not bridge_results:
        st.info(T("bridge_empty"))
    else:
        bridge_sections,bridge_rows = paper_report(bridge_results,bridge_query,lang,T("bridge_independent"),bridge=True)
        for row in bridge_rows:
            row["row_type"] = "paper"
        bridge_sections.extend(pair_sections)
        bridge_rows.extend(pair_rows)
        export_controls("bridges",T("tab_bridges"),bridge_sections,bridge_rows)
    for rank,paper in enumerate(visible_bridge_results,1):
        paper_card(paper,rank,bridge_query,"bridge")
selected_papers = [by_id[x] for x in st.session_state["comparison"] if x in by_id]
with tabs[2]:
    st.markdown("### "+T("compare_title"))
    st.caption(T("compare_note"))
    if not selected_papers:
        st.info(T("compare_empty"))
    else:
        st.caption(T("profile_note"))
        comparison,comparison_sections,comparison_rows,pair_sections = comparison_report(index,selected_papers,lang)
        profile_rows = [row for row in comparison_rows if row["row_type"]=="paper"]
        st.caption(T("table_hint"))
        table(profile_rows,[("pmid","PMID"),("title",T("paper_title")),("tags",T("tags")),("fields",T("fields")),("methods",T("methods"))])
        for paper in selected_papers:
            with st.expander(f"PMID {paper['pmid']} · "+T("comparison_evidence")):
                st.markdown("**"+paper["title"]+"**")
                st.link_button(T("pubmed"),paper["source_url"])
                p = comparison["profiles"][paper["pmid"]]
                for kind in ("fields","methods"):
                    for ident,evidence in p[kind].items():
                        st.markdown("**"+labels(kind,[ident],lang)+"**")
                        st.write(evidence["text"])
                st.write(T("publication_type")+": "+(" / ".join(paper["publication_types"]) or T("unavailable")))
                st.write("MeSH: "+(" / ".join(paper["mesh"]) or T("unavailable")))
        st.markdown("### "+T("comparison_score"))
        st.caption(T("comparison_formula"))
        if not pair_sections:
            st.info(T("pair_minimum"))
        for pair,section in zip(comparison["pairs"],pair_sections):
            with st.container(border=True):
                st.markdown("**"+section["heading"]+"**")
                st.write(T("paper_a")+": "+by_id[pair["a"]]["title"])
                st.write(T("paper_b")+": "+by_id[pair["b"]]["title"])
                st.metric(T("comparison_score"),f"{pair['score']:.3f}")
                for paragraph in section["paragraphs"][1:]:
                    lines = paragraph.splitlines()
                    if len(lines)>1:
                        st.markdown("**"+lines[0]+"**")
                        st.markdown("  \n".join(lines[1:]))
                    else:
                        st.caption(paragraph)
        export_controls("comparison",T("tab_compare"),comparison_sections,comparison_rows)
        st.download_button(T("download_comparison"),json.dumps(comparison,ensure_ascii=False,indent=2),"researchbridge_comparison.json","application/json")
        st.download_button(T("download_citations"),"\n\n".join(citation(p) for p in selected_papers),"researchbridge_citations.txt","text/plain")
with tabs[3]:
    st.markdown("### "+T("check_title"))
    st.write(T("check_note"))
    check_ids = st.multiselect(T("check_sources"),list(by_id),default=[p["pmid"] for p in goal_results[:3]],format_func=lambda x:by_id[x]["title"],key="check_ids")
    claims = st.text_area(T("claims"),key="claims",height=150)
    if st.button(T("check_button"),key="check_button",type="primary"):
        st.session_state["claim_report"] = {"inputs":(claims,check_ids),"reports":check_claims(claims,[by_id[x] for x in check_ids])} if claims.strip() and check_ids else None
        if not claims.strip() or not check_ids:
            st.info(T("check_empty"))
    report = st.session_state.get("claim_report")
    if report and report["inputs"]==(claims,check_ids):
        for item in report["reports"]:
            with st.container(border=True):
                st.write(item["claim"])
                (st.success if item["sources"] else st.warning)(T(item["status"]))
                for s in item["sources"]:
                    st.link_button(T("matched_source",pmid=s["pmid"],section=s["section"]),s["source_url"])
with tabs[4]:
    st.markdown("### "+T("brief_title"))
    st.write(T("brief_note"))
    brief_papers = selected_papers or (bridge_results[:3] if cue_id!="all" else goal_results[:3])
    st.caption(T("brief_selection",count=len(selected_papers)) if selected_papers else T("brief_current"))
    if brief_papers:
        brief = make_brief(query,method_id,cue_id,brief_papers,lang,None if selected_papers or cue_id!="all" else (low,high))
        brief_sections = markdown_sections(brief)
        brief_rows = [{"section":s["heading"],"content":"\n".join(s["paragraphs"])} for s in brief_sections]
        export_controls("brief",T("tab_brief"),brief_sections,brief_rows)
        st.download_button(T("download_brief"),brief.encode("utf-8"),f"researchbridge_brief_{lang}.md","text/markdown",key="download_brief")
        st.markdown(brief)
    else:
        st.info(T("empty"))
with tabs[5]:
    st.markdown("### "+T("directory_title"))
    st.write(T("directory_note"))
    a,b = st.columns(2)
    name_filter = a.text_input(T("institution_name"),key="institution_query")
    city_filter = localized_choice(b,"selectbox",T("city"),["all"]+sorted({x["city"] for x in institutions}),"city",lambda x:T("all_cities") if x=="all" else x)
    rows = [x for x in institutions if name_filter.casefold() in x["name"].casefold() and (city_filter=="all" or x["city"]==city_filter)]
    st.caption(T("directory_results",count=len(rows)))
    table(rows,[("name",T("institution_name")),("city",T("city")),("works",T("works")),("cited_by",T("citations"))])
    if rows:
        directory_sections = [{"heading":T("directory_title"),"paragraphs":[T("directory_note")]}]+[{"heading":r["name"],"paragraphs":[T("city")+": "+r["city"],T("works")+": "+str(r["works"]),T("citations")+": "+str(r["cited_by"])]} for r in rows]
        export_controls("directory",T("tab_directory"),directory_sections,rows)
with tabs[6]:
    st.markdown("### "+T("data_title"))
    st.write(T("data_scope",papers=len(papers),abstracts=abstract_count,linked=sum(bool(p["institution_count"]) for p in papers),links=link_count,institutions=len(institutions)))
    st.write(T("data_method"))
    st.write(T("data_generation"))
    st.link_button("PubMed E-utilities","https://www.ncbi.nlm.nih.gov/books/NBK25497/")
    st.link_button("OpenAlex authorships","https://help.openalex.org/data/authorships/")
    evaluation = Path(__file__).parent / "data/evaluation.json"
    if evaluation.exists():
        report = json.loads(evaluation.read_text(encoding="utf-8"))
        st.markdown("**"+T("evaluation")+"**")
        st.caption(T("evaluation_note"))
        table(report["summary"],[("方法",T("eval_mode")),("案例數",T("eval_cases")),("預期文獻在第一筆",T("eval_top1")),("預期文獻在前五筆",T("eval_top5")),("MRR@5","MRR@5")])
        st.download_button(T("download_evaluation"),json.dumps(report,ensure_ascii=False,indent=2),"researchbridge_evaluation.json","application/json")
    with st.expander(T("reproduce")):
        st.code("python -m researchbridge.ingest\npython -m researchbridge.evaluate\npython -m pytest tests --basetemp=.cache/testtmp\npython -m streamlit run app.py",language="bash")
st.html('<div class="rb-footer">ResearchBridge · '+T("footer")+'</div>')
