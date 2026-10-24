"""Inspectable corpus-based keywords and pairwise document comparisons."""
from itertools import combinations

import numpy as np

from researchbridge.discovery import CUES, METHODS, matches, source_evidence

FIELDS = {
    "informatics": {"labels": ("醫療資訊與自然語言處理", "Health informatics and NLP", "Informática de salud y PLN"), "pattern": r"\b(chatbots?|large language models?|llms?|clinical report|natural language)\b"},
    "digital": {"labels": ("數位健康與照護服務", "Digital health and care services", "Salud digital y servicios asistenciales"), "pattern": r"\b(mobile application|mobile app|digital health|caregivers?|nursing|care transition|telehealth)\b"},
    "molecular": {"labels": ("分子生物與基因體", "Molecular biology and genomics", "Biología molecular y genómica"), "pattern": r"\b(proteins?|genom\w*|genetic\w*|amino acid)\b"},
    "sensors": {"labels": ("生醫感測與電子", "Biomedical sensing and electronics", "Sensores biomédicos y electrónica"), "pattern": r"\b(biosens\w*|bioelectronic\w*|electrochemical)\b"},
    "neuro": {"labels": ("神經與認知研究", "Neuroscience and cognition", "Neurociencia y cognición"), "pattern": r"\b(cognit\w*|dementia|cortical|brain|neuroimaging)\b"},
    "rehab": {"labels": ("復健與肌肉骨骼", "Rehabilitation and musculoskeletal research", "Rehabilitación e investigación musculoesquelética"), "pattern": r"\b(fractures?|rehabilitat\w*|musculoskeletal|treadmill)\b"},
    "access": {"labels": ("健康服務可近性", "Health services accessibility", "Accesibilidad a servicios de salud"), "pattern": r"\b(health insurance|medicaid|healthcare access|underserved|health literacy)\b"},
}


def profile(paper):
    """Labels require a verbatim title or abstract match; omissions are unknown."""
    methods = {k: source_evidence(paper, v) for k, v in METHODS.items()}
    fields = {k: source_evidence(paper, v) for k, v in FIELDS.items()}
    return {"pmid": paper["pmid"], "tags": sorted(paper["topics"]),
            "methods": {k:v for k,v in methods.items() if v},
            "fields": {k:v for k,v in fields.items() if v},
            "has_abstract": bool(paper.get("abstract")), "mesh": paper.get("mesh", [])}


def compare_papers(index, selected):
    positions = {p["pmid"]: i for i,p in enumerate(index.papers)}
    profiles = {p["pmid"]: profile(p) for p in selected}
    features = index.vectorizer.get_feature_names_out()
    pairs = []
    for a,b in combinations(selected, 2):
        va, vb = index.matrix[positions[a["pmid"]]], index.matrix[positions[b["pmid"]]]
        product = va.multiply(vb).tocoo()
        ordered = sorted(zip(product.col, product.data), key=lambda x: -x[1])
        # Prefer phrases and avoid listing a phrase alongside its individual words.
        terms = []
        for col,_ in ordered:
            term = str(features[col])
            if any(term in other or other in term for other in terms):
                continue
            terms.append(term)
            if len(terms) == 8:
                break
        pa,pb = profiles[a["pmid"]], profiles[b["pmid"]]
        pair = {"a":a["pmid"], "b":b["pmid"], "score":float(np.clip((va @ vb.T).toarray()[0,0],0,1)), "shared_terms":terms,
                "limited_abstract": not pa["has_abstract"] or not pb["has_abstract"]}
        for key in ("tags", "fields", "methods"):
            left, right = set(pa[key]), set(pb[key])
            pair["shared_"+key] = sorted(left & right)
            pair["a_only_"+key] = sorted(left - right)
            pair["b_only_"+key] = sorted(right - left)
        pairs.append(pair)
    return {"profiles": profiles, "pairs": pairs}


def recommended_keywords(papers, limit=6):
    """Rank curated, translatable concepts by observed document frequency."""
    ranked = []
    for family, entries in (("cue", CUES), ("method", METHODS)):
        candidates = []
        for ident,entry in entries.items():
            supported = [p["pmid"] for p in papers if matches(p,entry) and source_evidence(p,entry)]
            if supported:
                candidates.append({"id":family+"_"+ident,"entry":entry,"count":len(supported),"pmids":supported,"query":entry["query"]})
        ranked.append(sorted(candidates,key=lambda x:(-x["count"],x["id"])))
    # Mix methods and research cues instead of displaying near-identical labels.
    output = []
    while any(ranked) and len(output)<limit:
        for group in ranked:
            if group and len(output)<limit:
                output.append(group.pop(0))
    return output
