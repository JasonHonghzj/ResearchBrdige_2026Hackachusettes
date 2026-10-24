from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from contextlib import closing
from pathlib import Path

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "researchbridge.sqlite"
SNAPSHOTS = ROOT / "data" / "snapshots"

TOPICS = {
    "數位健康與照護": r"\b(chatbot|caregiver|care transition|nursing|mobile application|medication literacy|digital|web-based|long-term care)\b",
    "AI 與臨床資訊": r"\b(large language|llms?|artificial intelligence|machine learning|clinical decision|summari[sz])",
    "生技與感測": r"\b(protein|genom|biomarker|biosens|bioelectronic|electrode|calprotectin)",
    "可近性與保險": r"\b(insurance|coverage|accessib|clinical trial|homeless|inequal)",
}
LEXICON = {
    "用藥素養": "medication literacy chatbot", "藥物素養": "medication literacy chatbot",
    "照護銜接": "care transition nursing community discharge", "出院": "discharge care transition",
    "聊天機器人": "chatbot", "大型語言模型": "large language models LLM",
    "人工智慧": "artificial intelligence", "照顧者": "caregiver", "照護者": "caregiver",
    "護理": "nursing care", "失智": "dementia", "蛋白質": "protein structure sequence",
    "蛋白": "protein", "基因": "genomic", "生物感測": "biosensing bioelectronics",
    "感測": "sensing", "保險": "insurance coverage", "產後": "postpartum",
    "臨床試驗": "clinical trials", "隱私": "privacy preserving", "眼科": "ophthalmology",
    "骨折": "fracture", "行動應用": "mobile application", "數位健康": "digital health mobile",
    "alfabetización sobre medicamentos": "medication literacy chatbot",
    "alfabetizacion farmacologica": "medication literacy chatbot",
    "transición de cuidados": "care transition nursing community discharge",
    "transición asistencial": "care transition nursing community discharge",
    "modelos de lenguaje": "large language models LLM",
    "inteligencia artificial": "artificial intelligence",
    "cuidadores": "caregiver", "proteínas": "protein structure sequence",
    "proteína": "protein", "privacidad": "privacy preserving",
    "ensayos clínicos": "clinical trials", "seguros": "insurance coverage",
    "fractura": "fracture", "demencia": "dementia", "salud digital": "digital health mobile",
}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", value).split())


def text_of(node) -> str:
    return "" if node is None else " ".join("".join(node.itertext()).split())


def parse_pubmed(payload: str | bytes) -> dict[str, dict]:
    """Preserve electronic/print/history dates separately, and keep abstract labels."""
    root = ET.fromstring(payload)
    records = {}
    for item in root.findall("PubmedArticle"):
        pmid = text_of(item.find("MedlineCitation/PMID"))
        article = item.find("MedlineCitation/Article")
        if not pmid or article is None:
            continue
        sections = []
        for node in article.findall("Abstract/AbstractText"):
            body = text_of(node)
            if body:
                sections.append({"label": node.get("Label") or node.get("NlmCategory") or "Abstract", "text": body})
        authors, affiliations = [], []
        for author in article.findall("AuthorList/Author"):
            name = text_of(author.find("CollectiveName")) or " ".join(filter(None, [text_of(author.find("LastName")), text_of(author.find("Initials"))]))
            if name:
                authors.append(name)
            affiliations.extend(text_of(n) for n in author.findall("AffiliationInfo/Affiliation") if text_of(n))
        doi = next((text_of(n) for n in item.findall("PubmedData/ArticleIdList/ArticleId") if n.get("IdType") == "doi"), "")
        dates = []
        for path, kind in [("Journal/JournalIssue/PubDate", "journal"), ("ArticleDate", "article")]:
            for node in article.findall(path):
                dates.append({"kind": node.get("DateType", kind), "value": " ".join(text_of(child) for child in node)})
        for node in item.findall("PubmedData/History/PubMedPubDate"):
            dates.append({"kind": node.get("PubStatus", "history"), "value": " ".join(text_of(node.find(k)) for k in ["Year", "Month", "Day"]).strip()})
        records[pmid] = {
            "pmid": pmid, "title": text_of(article.find("ArticleTitle")),
            "journal": text_of(article.find("Journal/ISOAbbreviation")) or text_of(article.find("Journal/Title")),
            "authors": ", ".join(authors), "doi": doi, "sections": sections,
            "abstract": "\n\n".join(s["label"] + ": " + s["text"] for s in sections),
            "affiliations": list(dict.fromkeys(affiliations)), "dates": dates,
            "publication_types": [text_of(n) for n in article.findall("PublicationTypeList/PublicationType")],
            "mesh": [text_of(n) for n in item.findall("MedlineCitation/MeshHeadingList/MeshHeading/DescriptorName")],
        }
    return records


def verified_work(work: dict, pmid: str) -> bool:
    """An exact external PMID is required before accepting an OpenAlex relation."""
    raw = str(work.get("ids", {}).get("pmid") or "").rstrip("/")
    return raw.rsplit("/", 1)[-1] == pmid and str(work.get("id", "")).startswith("https://openalex.org/W")


def work_links(work: dict, pmid: str, directory: list[dict]) -> list[dict]:
    if not verified_work(work, pmid):
        return []
    lookup = {normalize_name(r["institution"]): r for r in directory}
    result = {}
    for authorship in work.get("authorships", []):
        for inst in authorship.get("institutions", []):
            ident, name = inst.get("id", ""), inst.get("display_name", "")
            if not ident.startswith("https://openalex.org/I") or not name:
                continue
            match = lookup.get(normalize_name(name))
            # External affiliations remain visible even when not in the education-only starter list.
            result[ident] = {
                "pmid": pmid, "institution_id": ident, "name": name, "ror": inst.get("ror") or "",
                "country": inst.get("country_code") or "", "city": match["city"] if match else "",
                "directory_name": match["institution"] if match else "",
                "work_id": work["id"], "source_url": work["id"],
                "verification": "exact_pmid_openalex_affiliation",
            }
    return list(result.values())


def topic_tags(title: str, abstract: str = "") -> list[str]:
    text = title + " " + abstract
    return [name for name, pattern in TOPICS.items() if re.search(pattern, text, re.I)]


def connect(path: Path = DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def build_database(path: Path = DB_PATH, root: Path = ROOT) -> dict:
    seeds = read_csv(root / "pubmed" / "data.csv")
    directory = read_csv(root / "openalex" / "data.csv")
    if len({r["pmid"] for r in seeds}) != len(seeds):
        raise ValueError("Duplicate PMID in starter CSV")
    snapshot_dir = root / "data" / "snapshots"
    enriched_file = snapshot_dir / "pubmed.json"
    snapshot = json.loads(enriched_file.read_text(encoding="utf-8")) if enriched_file.exists() else {}
    enriched = snapshot.get("records", {})
    papers, links = [], []
    for seed in seeds:
        pmid = seed["pmid"]
        record = enriched.get(pmid, {})
        abstract = record.get("abstract", "")
        title = record.get("title") or seed["title"]
        work_file = snapshot_dir / "openalex" / f"{pmid}.json"
        work_snapshot = json.loads(work_file.read_text(encoding="utf-8")) if work_file.exists() else {}
        paper_links = work_links(work_snapshot.get("record", {}), pmid, directory)
        links.extend(paper_links)
        papers.append({
            **seed, "title": title, "journal": record.get("journal") or seed["journal"],
            "authors": record.get("authors") or seed["authors"], "starter_title": seed["title"],
            "starter_published": seed["published"], "doi": record.get("doi", ""), "abstract": abstract,
            "sections": record.get("sections", []), "affiliations": record.get("affiliations", []),
            "dates": record.get("dates", []), "publication_types": record.get("publication_types", []),
            "mesh": record.get("mesh", []), "topics": topic_tags(title, abstract),
            "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "metadata_source": "PubMed XML" if record else "starter CSV",
            "retrieved_at": snapshot.get("retrieved_at", "") if record else "",
            "has_abstract": bool(abstract), "institution_count": len(paper_links),
            "directory_link_count": sum(bool(x["directory_name"]) for x in paper_links),
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".building.sqlite")
    if temporary.exists():
        temporary.unlink()
    with closing(connect(temporary)) as conn, conn:
        conn.executescript("""
            CREATE TABLE papers (pmid TEXT PRIMARY KEY, title TEXT NOT NULL, journal TEXT NOT NULL, abstract TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE institutions (name TEXT PRIMARY KEY, city TEXT NOT NULL, works INTEGER NOT NULL, cited_by INTEGER NOT NULL);
            CREATE TABLE paper_institutions (pmid TEXT NOT NULL REFERENCES papers(pmid), institution_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(pmid,institution_id));
            CREATE TABLE provenance (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        for p in papers:
            conn.execute("INSERT INTO papers VALUES (?,?,?,?,?)", (p["pmid"], p["title"], p["journal"], p["abstract"], json.dumps(p, ensure_ascii=False)))
        conn.executemany("INSERT INTO institutions VALUES (?,?,?,?)", [(r["institution"], r["city"], int(r["works"]), int(r["cited_by"])) for r in directory])
        for link in links:
            conn.execute("INSERT OR REPLACE INTO paper_institutions VALUES (?,?,?)", (link["pmid"], link["institution_id"], json.dumps(link, ensure_ascii=False)))
        for source in ["pubmed/data.csv", "openalex/data.csv"]:
            conn.execute("INSERT INTO provenance VALUES (?,?)", (source, hashlib.sha256((root / source).read_bytes()).hexdigest()))
    temporary.replace(path)
    return {"papers": len(papers), "abstracts": sum(p["has_abstract"] for p in papers), "institutions": len(directory), "affiliation_links": len(links), "papers_with_links": sum(p["institution_count"] > 0 for p in papers), "directory_links": sum(bool(x["directory_name"]) for x in links)}


def load_data(path: Path = DB_PATH):
    if not path.exists():
        build_database(path)
    with closing(connect(path)) as conn:
        papers = [json.loads(r[0]) for r in conn.execute("SELECT payload FROM papers ORDER BY pmid DESC")]
        institutions = [dict(r) for r in conn.execute("SELECT * FROM institutions ORDER BY works DESC")]
        links = [json.loads(r[0]) for r in conn.execute("SELECT payload FROM paper_institutions ORDER BY pmid,institution_id")]
    grouped = {}
    for link in links:
        grouped.setdefault(link["pmid"], []).append(link)
    for paper in papers:
        paper["institutions"] = grouped.get(paper["pmid"], [])
    return papers, institutions


def expand_query(query: str):
    additions, matches = [], []
    def canonical(text):
        return "".join(c for c in unicodedata.normalize("NFKD", text).casefold() if not unicodedata.combining(c))
    remainder = canonical(query).strip()
    for word in sorted(LEXICON, key=len, reverse=True):
        normalized = canonical(word)
        pattern = re.escape(normalized) if not re.search(r"[a-z]", normalized) else r"\b" + re.escape(normalized) + r"\b"
        if re.search(pattern, remainder):
            additions.append(LEXICON[word])
            matches.append(word)
            remainder = re.sub(pattern, " ", remainder)
    expanded = " ".join([remainder] + additions).strip()
    return expanded, matches


class SearchIndex:
    """TF-IDF baseline + explicit, local LSA reranking; no downloaded model or LLM."""
    def __init__(self, papers: list[dict]):
        self.papers = papers
        docs = [(p["title"] + " ") * 3 + p.get("abstract", "") for p in papers]
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True, strip_accents="unicode")
        self.matrix = self.vectorizer.fit_transform(docs)
        components = min(24, self.matrix.shape[0] - 1, self.matrix.shape[1] - 1)
        self.svd = TruncatedSVD(n_components=components, random_state=42) if components >= 2 else None
        self.latent = normalize(self.svd.fit_transform(self.matrix)) if self.svd else None

    def search(self, query: str, mode="tfidf", topic=None, journal=None, require_abstract=False, require_links=False, limit=10, score_range=None, candidate_pmids=None):
        if score_range is not None:
            low, high = score_range
            if not 0 <= low <= high <= 1:
                raise ValueError("Score range must satisfy 0 <= lower <= upper <= 1")
            if not query.strip() and (low, high) != (0, 1):
                return [], "", []
        expanded, matched = expand_query(query)
        scores = np.ones(len(self.papers))
        if query.strip():
            vector = self.vectorizer.transform([expanded])
            if not vector.nnz:
                return [], expanded, matched
            lexical = (self.matrix @ vector.T).toarray().ravel()
            scores = lexical.copy()
            if mode == "hybrid" and self.svd:
                latent_query = normalize(self.svd.transform(vector))
                semantic = (self.latent @ latent_query.T).ravel()
                scores = 0.8 * lexical + 0.2 * np.maximum(semantic, 0)
            # LSA may reorder grounded matches, but cannot introduce zero-lexical matches.
            scores[lexical <= 1e-12] = 0
            scores = np.clip(scores, 0, 1)
        ranked = sorted(range(len(self.papers)), key=lambda i: (-float(scores[i]), i))
        results = []
        for i in ranked:
            p = self.papers[i]
            if scores[i] <= 1e-12:
                continue
            if candidate_pmids is not None and p["pmid"] not in candidate_pmids:
                continue
            if query.strip() and score_range is not None and not score_range[0] <= float(scores[i]) <= score_range[1]:
                continue
            # "transition" and "community" alone also retrieve physics/environment papers.
            # The curated care-transition expansion therefore requires a care-context word.
            is_care_query = expanded == "care transition nursing community discharge" or any(term in matched for term in ["照護銜接", "transición de cuidados", "transición asistencial"])
            if is_care_query and not re.search(r"\b(care|nursing|discharge|patients?|caregivers?)\b", p["title"] + " " + p.get("abstract", ""), re.I):
                continue
            if topic and topic not in p["topics"]:
                continue
            if journal and journal != p["journal"]:
                continue
            if require_abstract and not p["has_abstract"]:
                continue
            if require_links and not p["institution_count"]:
                continue
            results.append({**p, "score": float(scores[i]) if query.strip() else None})
            if len(results) >= limit:
                break
        return results, expanded, matched


def evidence_excerpt(paper: dict, query: str = "", count=2) -> str:
    """Return exact source sentences. Never synthesize findings from a title."""
    sections = paper.get("sections", [])
    if not sections:
        return ""
    expanded, _ = expand_query(query)
    tokens = set(re.findall(r"[a-z]{3,}", expanded.lower()))
    candidates = []
    for section in sections:
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", section["text"]):
            if len(sentence.strip()) >= 20:
                score = len(tokens.intersection(re.findall(r"[a-z]{3,}", sentence.lower())))
                candidates.append((score, len(candidates), sentence.strip()))
    best = sorted(candidates, key=lambda x: (-x[0], x[1]))[:count]
    return " ".join(x[2] for x in sorted(best, key=lambda x: x[1]))


def citation(paper: dict) -> str:
    dates = "; ".join(f"{x['kind']}: {x['value']}" for x in paper.get("dates", []) if x["kind"] in {"journal", "Electronic", "Print"}) or f"starter date (unverified): {paper['starter_published']}"
    return f"{paper['authors']}. {paper['title']} {paper['journal']}. {dates}. PMID: {paper['pmid']}. {paper['source_url']}"

