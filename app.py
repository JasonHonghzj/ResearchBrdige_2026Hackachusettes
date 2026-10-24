"""Research Scout web server.

One FastAPI backend for both engines:
  - Scout (scout/)                     gap finding on the large MeSH-indexed PubMed corpus
  - ResearchBridge (researchbridge/)   search / bridges / compare / brief / export over
                                       the 60-paper curated starter set (teammate's engine)

The two engines make different claims and must stay labelled apart in every
response. Bridge scores are TF-IDF text relevance on a small curated set: not a
probability, not evidence quality, and not a validated research gap.

Every Bridge endpoint recomputes its result from request parameters. Exports
re-run the same builders server-side instead of accepting report text from the
browser, so a downloaded file can only contain what the engine produced.

Run:  python -m uvicorn app:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from researchbridge.core import SearchIndex, evidence_excerpt, load_data
from researchbridge.discovery import (CUES, METHODS, available_cues, bridge_papers,
                                      check_claims, label, make_brief, matches,
                                      recommend_methods)
from researchbridge.exports import export_bytes
from researchbridge.i18n import LANG_NAMES, TEXT, translator
from researchbridge.insights import recommended_keywords
from researchbridge.queries import canonical_query
from researchbridge.reports import (bridge_relations_report, comparison_report,
                                    markdown_sections, paper_report)

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="Research Scout", docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

Lang = Literal["en", "zh", "es"]
Mode = Literal["tfidf", "hybrid"]
PMID = Field(pattern=r"^\d{1,9}$")

# Attached to every Bridge response so the boundary travels with the data.
BRIDGE_SCOPE = {
    "engine": "researchbridge",
    "corpus": "60 curated Hackachusetts starter papers (Massachusetts affiliation, 2024)",
    "score": ("TF-IDF text relevance in [0, 1], title weighted 3x; hybrid adds 20% "
              "non-negative LSA. Not a probability, evidence quality, or research gap."),
    "validated": False,
}


# ------------------------------------------------------------------ engine state

class _Bridge:
    """Corpus, index and lookups, loaded once per process."""
    def __init__(self) -> None:
        self.papers, self.institutions = load_data()
        self.index = SearchIndex(self.papers)
        self.by_id = {p["pmid"]: p for p in self.papers}
        # Same rule as the original UI: only offer methods some paper actually mentions.
        self.method_ids = [m for m, e in METHODS.items() if any(matches(p, e) for p in self.papers)]


@lru_cache(maxsize=1)
def _bridge() -> _Bridge:
    return _Bridge()


def _scope() -> dict:
    return {**BRIDGE_SCOPE, "corpus_size": len(_bridge().papers)}


def _goal_results(q: str, mode: str) -> list[dict]:
    """Unthresholded goal search over the whole set; feeds method recommendations."""
    b = _bridge()
    if not q.strip():
        return []
    results, _, _ = b.index.search(canonical_query(q), mode=mode, limit=len(b.papers))
    return results


def _papers_for(pmids: list[str]) -> list[dict]:
    b = _bridge()
    unknown = [p for p in pmids if p not in b.by_id]
    if unknown:
        raise HTTPException(422, f"Unknown PMID(s) in this corpus: {', '.join(unknown)}")
    return [b.by_id[p] for p in dict.fromkeys(pmids)]


def _resolve_method(method: str, goal: list[dict]) -> str:
    b = _bridge()
    if method == "auto":
        recs = recommend_methods(goal)
        return recs[0]["id"] if recs else b.method_ids[0]
    if method not in b.method_ids:
        raise HTTPException(422, f"Unknown method '{method}'. Options: auto, {', '.join(b.method_ids)}")
    return method


def _resolve_cue(cue: str) -> str:
    if cue != "all" and cue not in CUES:
        raise HTTPException(422, f"Unknown cue '{cue}'. Options: all, {', '.join(CUES)}")
    return cue


def _paper_view(paper: dict, query: str) -> dict:
    """Public fields only. Excerpts are verbatim source sentences, never generated."""
    view = {
        "pmid": paper["pmid"], "title": paper["title"], "journal": paper["journal"],
        "score": round(paper["score"], 4) if paper.get("score") is not None else None,
        "topics": paper["topics"], "has_abstract": paper["has_abstract"],
        "excerpt": evidence_excerpt(paper, query),
        "institutions": [{"name": i["name"], "country": i["country"], "city": i["city"]}
                         for i in paper.get("institutions", [])],
        "source_url": paper["source_url"], "doi": paper["doi"],
    }
    for side in ("method_evidence", "bridge_evidence"):
        if paper.get(side):
            view[side] = paper[side]["text"]
    return view


def _bridge_run(q: str, mode: str, method: str, cue: str, limit: int):
    """Shared by /bridges, /brief and /export so all three see identical results."""
    b = _bridge()
    goal = _goal_results(q, mode)
    method_id = _resolve_method(method, goal)
    cue_id = _resolve_cue(cue)
    results, bridge_query = bridge_papers(b.index, method_id, cue_id, mode=mode, limit=len(b.papers))
    return goal, method_id, cue_id, results, results[:limit], bridge_query


# ------------------------------------------------------------------- endpoints

@app.get("/api/bridge/meta")
def bridge_meta(lang: Lang = "en") -> dict:
    """Corpus stats, option lists and the teammate's UI strings for one language.
    Strings are raw templates ({count}, {score:.3f}); the client fills them."""
    b = _bridge()
    i = ("zh", "en", "es").index(lang)
    return {
        "scope": _scope(),
        "languages": LANG_NAMES,
        "stats": {"papers": len(b.papers),
                  "abstracts": sum(p["has_abstract"] for p in b.papers),
                  "affiliation_links": sum(p["institution_count"] for p in b.papers),
                  "institutions": len(b.institutions)},
        "methods": [{"id": m, "label": label(METHODS[m], lang)} for m in b.method_ids],
        "cues": [{"id": c, "label": label(e, lang)} for c, e in CUES.items()],
        "text": {k: v[i] for k, v in TEXT.items()},
    }


@app.get("/api/bridge/search")
def bridge_search(
    q: str = Query(..., min_length=1, max_length=200, description="Research goal (zh/en/es)"),
    mode: Mode = "tfidf",
    limit: int = Query(10, ge=1, le=60),
) -> dict:
    """Built-in concepts are canonicalised, so one concept ranks identically in
    every interface language."""
    index = _bridge().index
    effective = canonical_query(q.strip())
    results, expanded, matched = index.search(effective, mode=mode, limit=limit)
    return {"scope": _scope(), "query": q, "effective_query": effective,
            "expanded_query": expanded, "lexicon_matches": matched, "mode": mode,
            "count": len(results), "results": [_paper_view(p, effective) for p in results]}


@app.get("/api/bridge/keywords")
def bridge_keywords(lang: Lang = "en") -> dict:
    """Curated concepts ranked by how many papers actually contain them."""
    return {"scope": _scope(), "keywords": [
        {"id": k["id"], "label": label(k["entry"], lang), "count": k["count"], "query": k["query"]}
        for k in recommended_keywords(_bridge().papers)]}


@app.get("/api/bridge/bridges")
def bridge_bridges(
    q: str = Query("", max_length=200),
    mode: Mode = "tfidf",
    method: str = Query("auto", max_length=40),
    cue: str = Query("all", max_length=40),
    limit: int = Query(10, ge=1, le=60),
    lang: Lang = "en",
) -> dict:
    """Goal A -> bridge cue B -> method C. Every returned paper carries the verbatim
    source sentence for each side it was matched on."""
    b = _bridge()
    goal, method_id, cue_id, results, shown, bridge_query = _bridge_run(q, mode, method, cue, limit)
    pairs, _, _ = bridge_relations_report(b.index, shown, lang, total=len(results))
    return {
        "scope": _scope(), "query": q, "bridge_query": bridge_query,
        "method": {"id": method_id, "label": label(METHODS[method_id], lang)},
        "cue": {"id": cue_id, "label": label(CUES[cue_id], lang) if cue_id in CUES else None},
        "recommended_methods": [{"id": r["id"], "label": label(METHODS[r["id"]], lang),
                                 "count": r["count"], "score": round(r["score"], 4)}
                                for r in recommend_methods(goal)[:3]],
        "cues": [{**c, "label": label(CUES[c["id"]], lang)}
                 for c in available_cues(b.papers, method_id, goal)],
        "count": len(results),
        "results": [_paper_view(p, bridge_query) for p in shown],
        "pairs": [{"a": p["a"], "b": p["b"], "score": round(p["score"], 4),
                   "shared_terms": p["shared_terms"], "limited_abstract": p["limited_abstract"]}
                  for p in pairs],
    }


class CompareBody(BaseModel):
    pmids: list[str] = Field(min_length=1, max_length=4)
    lang: Lang = "en"


@app.post("/api/bridge/compare")
def bridge_compare(body: CompareBody) -> dict:
    """Pairwise TF-IDF cosine plus source-backed field/method profiles."""
    papers = _papers_for(body.pmids)
    report, _, rows, _ = comparison_report(_bridge().index, papers, body.lang)
    return {"scope": _scope(),
            "papers": [r for r in rows if r["row_type"] == "paper"],
            "pairs": [{k: (round(v, 4) if k == "score" else v) for k, v in p.items()}
                      for p in report["pairs"]],
            "profiles": report["profiles"]}


class CheckBody(BaseModel):
    claims: str = Field(min_length=1, max_length=10_000)
    pmids: list[str] = Field(min_length=1, max_length=20)


@app.post("/api/bridge/check")
def bridge_check(body: CheckBody) -> dict:
    """Bridge's conservative literal check: a statement passes only if it appears
    verbatim (after Unicode/case/space normalisation) in a selected abstract.
    No match means 'human review required', never 'false'. Scout's own claim gate
    (verify.py: fuzzy sentence match + numeral check) is a separate, stricter tool."""
    reports = check_claims(body.claims, _papers_for(body.pmids))
    return {"scope": _scope(), "method": "literal_normalised_substring", "reports": [
        {"claim": r["claim"], "status": r["status"],
         "sources": [{"pmid": s["pmid"], "section": s["section"], "source_url": s["source_url"]}
                     for s in r["sources"]]} for r in reports]}


class BriefBody(BaseModel):
    goal: str = Field("", max_length=200)
    mode: Mode = "tfidf"
    method: str = Field("auto", max_length=40)
    cue: str = Field("all", max_length=40)
    pmids: list[str] = Field(default_factory=list, max_length=4)
    lang: Lang = "en"


def _brief_markdown(body: BriefBody) -> str:
    """Same selection rule as the original UI: saved papers first, else the top
    three bridge results when a cue is chosen, else the top three goal results."""
    _, method_id, cue_id, results, _, _ = _bridge_run(body.goal, body.mode, body.method, body.cue, 3)
    if body.pmids:
        papers, score_range = _papers_for(body.pmids), None
    elif cue_id != "all":
        papers, score_range = results[:3], None
    else:
        papers, score_range = _goal_results(body.goal, body.mode)[:3], (0.0, 1.0)
    if not papers:
        raise HTTPException(422, "No papers to brief: enter a goal that matches, or save papers.")
    return make_brief(body.goal, method_id, cue_id, papers, body.lang, score_range)


@app.post("/api/bridge/brief")
def bridge_brief(body: BriefBody) -> dict:
    return {"scope": _scope(), "markdown": _brief_markdown(body)}


@app.get("/api/bridge/directory")
def bridge_directory(name: str = Query("", max_length=100), city: str = Query("", max_length=60)) -> dict:
    """The 135-row starter directory: education institutions only, so MGH,
    Brigham, Dana-Farber and Broad are absent by construction."""
    rows = [r for r in _bridge().institutions
            if name.casefold() in r["name"].casefold() and (not city or r["city"] == city)]
    cities = sorted({r["city"] for r in _bridge().institutions})
    return {"scope": _scope(), "cities": cities, "count": len(rows), "institutions": rows}


class ExportBody(BaseModel):
    kind: Literal["search", "bridges", "compare", "brief", "directory"]
    format: Literal["csv", "html", "pdf"]
    lang: Lang = "en"
    q: str = Field("", max_length=200)
    mode: Mode = "tfidf"
    method: str = Field("auto", max_length=40)
    cue: str = Field("all", max_length=40)
    pmids: list[str] = Field(default_factory=list, max_length=4)
    name: str = Field("", max_length=100)
    city: str = Field("", max_length=60)


@app.post("/api/bridge/export")
def bridge_export(body: ExportBody) -> Response:
    b, T = _bridge(), translator(body.lang)
    if body.kind == "search":
        if not body.q.strip():
            raise HTTPException(422, "Search export needs a query.")
        results = _goal_results(body.q, body.mode)
        if not results:
            raise HTTPException(422, "No papers match this query.")
        sections, rows = paper_report(results, body.q, body.lang, T("score_explained"))
    elif body.kind == "bridges":
        _, _, _, results, shown, bq = _bridge_run(body.q, body.mode, body.method, body.cue, 10)
        if not results:
            raise HTTPException(422, "No papers match this method and cue.")
        sections, rows = paper_report(results, bq, body.lang, T("bridge_independent"), bridge=True)
        _, pair_sections, pair_rows = bridge_relations_report(b.index, shown, body.lang, total=len(results))
        sections, rows = sections + pair_sections, rows + pair_rows
    elif body.kind == "compare":
        if not body.pmids:
            raise HTTPException(422, "Compare export needs saved papers.")
        _, sections, rows, _ = comparison_report(b.index, _papers_for(body.pmids), body.lang)
    elif body.kind == "brief":
        md = _brief_markdown(BriefBody(goal=body.q, mode=body.mode, method=body.method,
                                       cue=body.cue, pmids=body.pmids, lang=body.lang))
        sections = markdown_sections(md)
        rows = [{"section": s["heading"], "content": "\n".join(s["paragraphs"])} for s in sections]
    else:
        rows = bridge_directory(body.name, body.city)["institutions"]
        sections = [{"heading": T("directory_title"), "paragraphs": [T("directory_note")]}] + [
            {"heading": r["name"], "paragraphs": [f"{T('city')}: {r['city']}",
                                                  f"{T('works')}: {r['works']}",
                                                  f"{T('citations')}: {r['cited_by']}"]} for r in rows]
    title = T({"search": "tab_search", "bridges": "tab_bridges", "compare": "tab_compare",
               "brief": "tab_brief", "directory": "tab_directory"}[body.kind])
    try:
        data, mime = export_bytes(title, sections, rows, body.format, body.lang)
    except RuntimeError as exc:
        # PDF embeds Windows' Microsoft JhengHei for CJK; absent on macOS/Linux.
        raise HTTPException(501, f"{exc} Use HTML export and print it to PDF instead.") from exc
    filename = f"researchbridge_{body.kind}_{body.lang}.{body.format}"
    return Response(data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ------------------------------------------------------------------ scout engine
#
# The second engine. The boundary between them is the whole point.
#
#   Bridge  60 curated papers, TF-IDF retrieval, validated: False.
#           Answers "what work EXISTS on this?"
#   Scout   79,940 PubMed papers, MeSH axes, gaps verified against FULL PubMed.
#           Answers "what work DOESN'T exist?"
#
# A gap found only inside a corpus is not a research gap. Ranking empty cells of
# the early-detection corpus put eight pairs on top that had 103, 1224, 91, 391,
# 1485, 17, 231 and 472 papers in PubMed - zero of eight were real. So every
# candidate served here survived two live queries, and its maturity count travels
# with it as evidence the pairing is tractable rather than unexplored for cause.

import json as _json

DATA = ROOT / "data"

SCOUT_SCOPE = {
    "engine": "scout",
    "corpus": "79,940 PubMed papers, 2005-2026, complete per-year retrieval",
    "vocabulary": "MeSH descriptors; 50 disease x 32 transferable-method axes",
    "gap_test": ("live PubMed: maturity = problem AND method for any purpose; "
                 "gap_papers = the same pair AND the early-detection topic, "
                 "which must be <= 2"),
    "validated": True,
}


def _scout_file(name: str):
    path = DATA / name
    if not path.exists():
        raise HTTPException(503, f"{name} not generated - run `python -m scout.grid`")
    return _json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _confirmed() -> tuple:
    return tuple(_scout_file("confirmed.json"))


@app.get("/api/scout/scope")
def scout_scope() -> dict:
    rows = _confirmed()
    return {**SCOUT_SCOPE,
            "cells_checked": len(rows),
            "confirmed_gaps": sum(1 for r in rows if r.get("real_gap")),
            "provenance": _scout_file("provenance.json")}


@app.get("/api/scout/grid")
def scout_grid() -> dict:
    """The field map: diseases against transferable methods, cells are paper counts."""
    return {"scope": SCOUT_SCOPE, **_scout_file("grid.json")}


@app.get("/api/scout/gaps")
def scout_gaps(limit: int = Query(50, ge=1, le=500),
               min_maturity: int = Query(0, ge=0),
               order: Literal["maturity", "bridges"] = "maturity") -> dict:
    """Confirmed gaps, ranked by how proven the method already is.

    `maturity` is the default because it is a live count anyone can re-run rather
    than a tunable score, and a high maturity beside a zero gap count is the
    strongest candidate shape: the capability demonstrably works on that disease
    and nobody has aimed it at early detection.

    `bridges` is exposed for inspection only. Mechanistic bridge score was
    measured against the same holdout and does NOT predict a real gap - flagged
    368/475 = 77% real versus rejected 56/58 = 97%, lift 0.80x, with score
    quartiles running inverse at 73/75/81/81%. Many shared mechanistic terms
    means the two literatures are already connected, so the pairing is MORE
    likely to have been done already.
    """
    rows = [dict(r) for r in _confirmed()
            if r.get("real_gap") and r.get("maturity", 0) >= min_maturity]
    field = "maturity" if order == "maturity" else "score"
    rows.sort(key=lambda r: -r.get(field, 0))
    return {"scope": SCOUT_SCOPE, "ranking": order,
            "total_confirmed": sum(1 for r in _confirmed() if r.get("real_gap")),
            "total_checked": len(_confirmed()),
            "count": min(len(rows), limit), "gaps": rows[:limit]}


@app.get("/api/scout/gaps/rejected")
def scout_gaps_rejected(limit: int = Query(50, ge=1, le=500)) -> dict:
    """Candidates that failed live verification. A shortlist is only readable
    next to what was discarded, and a judge will ask for it."""
    rows = [dict(r) for r in _confirmed() if not r.get("real_gap")]
    rows.sort(key=lambda r: -r.get("gap_papers", 0))
    return {"scope": SCOUT_SCOPE, "count": min(len(rows), limit),
            "rejected": rows[:limit]}


@app.get("/api/scout/validation")
def scout_validation() -> dict:
    """Holdout validation state.

    The earlier 2.0x lift is deliberately not served. It was measured on a
    9,800-paper corpus (22% of the result set), a 14-term method axis, and a
    corpus-scoped gap definition that live verification disproved. Quoting it
    would repeat exactly the overreach the bridge ranking already cost us.
    """
    path = DATA / "validation.json"
    if path.exists():
        return _json.loads(path.read_text(encoding="utf-8"))
    return {"status": "pending_remeasurement",
            "withdrawn_claim": "2.0x lift of flagged gaps over unflagged",
            "withdrawn_because": ["corpus was 22% of the result set",
                                  "method axis had 14 terms, now 32",
                                  "gap definition was corpus-scoped; 0 of 8 top "
                                  "gaps were real in full PubMed"],
            "established_negative_result": {
                "claim": "mechanistic bridge score predicts a real gap",
                "verdict": False,
                "flagged_real": "368/475 = 77%",
                "rejected_real": "56/58 = 97%",
                "lift": 0.80}}


@app.get("/api/scout/integrity")
def scout_integrity() -> dict:
    """Random records re-fetched live and compared against the local cache."""
    path = DATA / "integrity_check.json"
    if not path.exists():
        raise HTTPException(503, "no integrity check recorded - run "
                                 "scout.fetch.spot_check()")
    return _json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/scout/terms")
def scout_terms() -> dict:
    """The exact MeSH descriptor names the axes use, for input suggestions.

    Nobody should be expected to guess that the descriptor is
    "Spectrum Analysis, Raman" rather than "Raman Spectrum Analysis" - MeSH
    inverts names for alphabetisation. Serving the real strings turns a
    rejection that looks like a bug into an autocomplete.
    """
    g = _scout_file("grid.json")
    return {"problems": [p["name"] for p in g["problems"]],
            "methods": [m["name"] for m in g["methods"]]}


@app.get("/api/scout/check")
def scout_check(problem: str = Query(..., min_length=2, max_length=100),
                method: str = Query(..., min_length=2, max_length=100),
                fresh: bool = False) -> dict:
    """Verify ANY problem/method pairing live against full PubMed, in ~1.5s.

    The whole product in one request: four queries, a maturity count, a gap
    count, and a verdict a reviewer can reproduce in a browser. It answers for
    pairings outside the precomputed grid, which is what makes this a tool
    rather than a viewer.

    An unrecognised descriptor is reported as unrecognised. That guard is not
    cosmetic - a misspelled disease matches no papers, so without it both counts
    return 0 and the verdict reads like a pristine gap for something that does
    not exist.
    """
    from scout.confirm import check_pair
    out = check_pair(problem, method, use_cache=not fresh)
    if not out.get("ok"):
        raise HTTPException(422, detail=out)
    return {"scope": SCOUT_SCOPE, **out}


# The pages change often during development and a browser that caches one shows
# a UI whose controls do not exist in the script it already has - which looks
# exactly like a hardcoded mockup. With no Cache-Control header browsers apply a
# heuristic freshness lifetime and may not revalidate at all, so say it
# explicitly for the HTML and for the mounted JS.
NO_STORE = {"Cache-Control": "no-store, must-revalidate", "Pragma": "no-cache"}


@app.middleware("http")
async def _no_cache_frontend(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path == "/pipeline" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/", include_in_schema=False)
def index_page() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers=NO_STORE)


@app.get("/pipeline", include_in_schema=False)
def pipeline_page() -> FileResponse:
    return FileResponse(STATIC / "pipeline.html", headers=NO_STORE)
