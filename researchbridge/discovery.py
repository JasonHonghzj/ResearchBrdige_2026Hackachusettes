"""Source-grounded method and bridge exploration over the local corpus.

These are curated, inspectable text patterns. A match is a discovery cue, not
evidence of causality, method effectiveness, novelty or a global research gap.
"""
from __future__ import annotations

import re
import unicodedata

from researchbridge.core import citation, evidence_excerpt

METHODS = {
    "llm": {"labels": ("大型語言模型與聊天機器人", "LLMs and chatbots", "Modelos de lenguaje y chatbots"), "pattern": r"\b(large language models?|llms?|chatbots?)\b", "query": "large language model chatbot"},
    "mobile": {"labels": ("行動與數位介入", "Mobile and digital interventions", "Intervenciones móviles y digitales"), "pattern": r"\b(mobile application|mobile app|web-based|digital intervention|digital weight)\b", "query": "mobile application digital intervention web-based"},
    "sensing": {"labels": ("生物感測與生物電子", "Biosensing and bioelectronics", "Biosensores y bioelectrónica"), "pattern": r"\b(biosens\w*|bioelectronic\w*|electrochemical)\b", "query": "biosensing bioelectronics electrochemical"},
    "protein": {"labels": ("蛋白質結構與序列建模", "Protein structure and sequence modeling", "Modelado de estructuras y secuencias proteicas"), "pattern": r"\b(protein|residue level|protein structures)\b", "query": "protein structures sequences embedding"},
    "imaging": {"labels": ("影像與訊號分析", "Image and signal analysis", "Análisis de imágenes y señales"), "pattern": r"\b(denoising|parcellation|ldct|neuroimaging|image processing|cortical)\b", "query": "imaging image denoising cortical parcellation"},
    "cohort": {"labels": ("世代與回溯研究", "Cohort and retrospective studies", "Estudios de cohortes y retrospectivos"), "pattern": r"\b(cohort|retrospective|longitudinal)\b", "query": "cohort retrospective longitudinal"},
    "review": {"labels": ("系統性與範疇回顧", "Systematic and scoping reviews", "Revisiones sistemáticas y de alcance"), "pattern": r"\b(systematic review|scoping review|meta-analysis|narrative review)\b", "query": "systematic review scoping review meta-analysis"},
    "causal": {"labels": ("因果與中介分析", "Causal and mediation analysis", "Análisis causal y de mediación"), "pattern": r"\b(causal mediation|mediation analysis)\b", "query": "causal mediation analysis"},
}
CUES = {
    "medication": {"labels": ("用藥與藥物資訊", "Medication and drug information", "Medicación e información farmacológica"), "pattern": r"\b(medication\w*|drug\w*|pharmacolog\w*)\b", "query": "medication drug information"},
    "literacy": {"labels": ("健康素養與患者教育", "Health literacy and patient education", "Alfabetización en salud y educación del paciente"), "pattern": r"\b(literacy|patient education|patient-centric|patient-centered)\b", "query": "health literacy patient education"},
    "care": {"labels": ("照顧者與照護銜接", "Caregivers and care transitions", "Cuidadores y transiciones asistenciales"), "pattern": r"\b(caregivers?|nursing|discharge|care transition|long-term care)\b", "query": "caregiver nursing discharge care transition"},
    "privacy": {"labels": ("隱私與資料保護", "Privacy and data protection", "Privacidad y protección de datos"), "pattern": r"\b(privacy|confidential\w*|de-identif\w*|data protection)\b", "query": "privacy preserving data protection"},
    "cognition": {"labels": ("認知與失智", "Cognition and dementia", "Cognición y demencia"), "pattern": r"\b(cognit\w*|dementia|memory)\b", "query": "cognitive dementia memory"},
    "access": {"labels": ("可近性與服務取得", "Accessibility and access to care", "Accesibilidad y acceso a la atención"), "pattern": r"\b(accessib\w*|underserved|insurance|coverage|access to)\b", "query": "accessibility underserved insurance coverage"},
    "rehab": {"labels": ("復健與骨折", "Rehabilitation and fractures", "Rehabilitación y fracturas"), "pattern": r"\b(fractures?|rehabilitat\w*|exercise|treadmill)\b", "query": "fracture rehabilitation exercise"},
    "biomarker": {"labels": ("生物標記與蛋白質", "Biomarkers and proteins", "Biomarcadores y proteínas"), "pattern": r"\b(biomarkers?|proteins?|calprotectin)\b", "query": "biomarker protein calprotectin"},
    "genomics": {"labels": ("基因體與序列", "Genomics and sequences", "Genómica y secuencias"), "pattern": r"\b(genom\w*|genetic\w*|sequence\w*)\b", "query": "genomic genetic sequence"},
    "decision": {"labels": ("臨床決策與報告", "Clinical decisions and reports", "Decisiones clínicas e informes"), "pattern": r"\b(clinical decision|calculator\w*|clinical report|dialysis)\b", "query": "clinical decision calculator report dialysis"},
}


def label(entry, lang="zh"):
    return entry["labels"][("zh", "en", "es").index(lang)]


def paper_text(paper):
    return paper["title"] + " " + paper.get("abstract", "")


def matches(paper, entry):
    return bool(re.search(entry["pattern"], paper_text(paper), re.I))


def source_evidence(paper, entry):
    """A verbatim title or abstract sentence containing an actual pattern match."""
    if re.search(entry["pattern"], paper["title"], re.I):
        return {"field": "title", "text": paper["title"], "pmid": paper["pmid"], "source_url": paper["source_url"]}
    for section in paper.get("sections", []):
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", section["text"]):
            if re.search(entry["pattern"], sentence, re.I):
                return {"field": "abstract", "text": sentence.strip(), "pmid": paper["pmid"], "source_url": paper["source_url"]}
    return None


def recommend_methods(goal_results):
    ranked = []
    for ident, method in METHODS.items():
        supporting = [p for p in goal_results if matches(p, method)]
        if supporting:
            ranked.append({"id": ident, "count": len(supporting), "score": max(p["score"] or 0 for p in supporting), "pmids": [p["pmid"] for p in supporting]})
    return sorted(ranked, key=lambda m: (-m["score"], -m["count"], m["id"]))


def available_cues(papers, method_id, goal_results):
    method = METHODS[method_id]
    method_papers = [p for p in papers if matches(p, method)]
    result = []
    for ident, cue in CUES.items():
        supported = [p for p in method_papers if matches(p, cue)]
        if not supported:
            continue
        goals = [p for p in goal_results if matches(p, cue)]
        result.append({"id": ident, "method_count": len(supported), "goal_count": len(goals), "shared": bool(goals), "pmids": [p["pmid"] for p in supported]})
    return sorted(result, key=lambda c: (-int(c["shared"]), -c["method_count"], c["id"]))


def bridge_papers(index, method_id, cue_id="all", **filters):
    method = METHODS[method_id]
    cue = CUES.get(cue_id)
    candidates = {p["pmid"] for p in index.papers if matches(p, method) and (cue is None or matches(p, cue))}
    bridge_query = method["query"] + (" " + cue["query"] if cue else "")
    results, _, _ = index.search(bridge_query, candidate_pmids=candidates, **filters)
    enriched = []
    for paper in results:
        method_evidence = source_evidence(paper, method)
        cue_evidence = source_evidence(paper, cue) if cue else None
        # A bridge must expose actual source text for each selected side.
        if method_evidence and (cue is None or cue_evidence):
            enriched.append({**paper, "method_evidence": method_evidence, "bridge_evidence": cue_evidence})
    return enriched, bridge_query


def check_claims(claims, papers):
    """Conservative literal-source checks, explicitly not entailment verification."""
    def canonical(text):
        return " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    reports = []
    for claim in [line.strip() for line in claims.splitlines() if line.strip()][:20]:
        needle = canonical(claim)
        hits = []
        if len(needle) >= 16:
            for paper in papers:
                for section in paper.get("sections", []):
                    if needle in canonical(section["text"]):
                        hits.append({"pmid": paper["pmid"], "source_url": paper["source_url"], "section": section["label"], "text": section["text"]})
        status = "literal_match" if hits else "review_required"
        reports.append({"claim": claim, "status": status, "sources": hits})
    return reports


def make_brief(goal, method_id, cue_id, papers, lang="zh", score_range=(0, 1)):
    selected_method = label(METHODS[method_id], lang) if method_id in METHODS else {"zh": "未選擇", "en": "Not selected", "es": "Sin seleccionar"}[lang]
    selected_cue = label(CUES[cue_id], lang) if cue_id in CUES else {"zh": "全部線索", "en": "All cues", "es": "Todas las conexiones"}[lang]
    texts = {
        "zh": ["研究機會簡報", "研究目標", "候選方法", "感興趣的 Bridge", "相關度範圍", "來源與原文", "論文所載機構", "研究團隊聯繫信草稿", "待確認的探索假設，不代表已證實的研究空缺、因果機制或療效。機構僅代表來源收錄的 affiliation。", "主旨：研究方向交流", "研究團隊您好：", "我正在探索以下研究目標：", "我對以下方法與線索感興趣：", "下列文獻提供了值得進一步閱讀的起點。我希望了解此方向的適用範圍、限制與可行的驗證方式。", "期待有機會交流，謝謝。"],
        "en": ["Research opportunity brief", "Research goal", "Candidate method", "Bridge of interest", "Relevance range", "Sources and verbatim excerpts", "Affiliations recorded in the papers", "Draft outreach message", "An exploratory hypothesis, not an established research gap, causal mechanism or treatment effect. Institutions are recorded affiliations only.", "Subject: Exploring a research direction", "Dear research team,", "I am exploring this research goal:", "I am interested in this method and research cue:", "The papers below offer starting points for further reading. I would value your perspective on scope, limitations and feasible validation.", "Thank you for considering a discussion."],
        "es": ["Informe de oportunidad de investigación", "Objetivo de investigación", "Método candidato", "Conexión de interés", "Intervalo de relevancia", "Fuentes y extractos originales", "Afiliaciones registradas en los artículos", "Borrador de contacto", "Hipótesis exploratoria; no demuestra una laguna de investigación, un mecanismo causal ni un efecto terapéutico. Las instituciones son solo afiliaciones registradas.", "Asunto: Exploración de una línea de investigación", "Estimado equipo de investigación:", "Estoy explorando este objetivo:", "Me interesa este método y esta conexión:", "Los artículos siguientes ofrecen puntos de partida para una lectura más profunda. Agradecería su perspectiva sobre el alcance, las limitaciones y una validación viable.", "Gracias por considerar una conversación."],
    }[lang]
    title, goal_h, method_h, cue_h, range_h, sources_h, affiliations_h, outreach_h, caveat, subject, greeting, goal_line, cue_line, request, close = texts
    range_text = f"{score_range[0]:.2f} - {score_range[1]:.2f}" if score_range is not None else {"zh":"手動清單或 Bridges；不套用搜尋門檻", "en":"Saved selection or Bridges; search threshold does not apply", "es":"Selección guardada o conexiones; sin umbral de búsqueda"}[lang]
    parts = [f"# {title}", f"## {goal_h}\n{goal}", f"## {method_h}\n{selected_method}", f"## {cue_h}\n{selected_cue}", f"{range_h}: {range_text}", caveat, f"## {sources_h}"]
    for paper in papers:
        parts.append(f"### {paper['title']}\n{citation(paper)}")
        excerpts = list(dict.fromkeys(paper[field]["text"] for field in ("method_evidence", "bridge_evidence") if paper.get(field)))
        if not excerpts:
            from researchbridge.queries import canonical_query
            excerpt = evidence_excerpt(paper, canonical_query(goal))
            excerpts = [excerpt] if excerpt else []
        parts.extend("> " + excerpt for excerpt in excerpts)
    names = sorted({i["name"] for p in papers for i in p.get("institutions", [])})
    parts.extend([f"## {affiliations_h}", "\n".join("- " + name for name in names) or "—", f"## {outreach_h}", f"{subject}\n\n{greeting}\n\n{goal_line} {goal}\n\n{cue_line} {selected_method} / {selected_cue}\n\n{request}\n\n" + "\n".join(p["source_url"] for p in papers) + f"\n\n{close}"])
    return "\n\n".join(parts)
