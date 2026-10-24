"""MeSH tree handling: resolve descriptor UIs to tree numbers and classify them.

Tree numbers are the whole basis of the axis rules and are NOT in the PubMed
record. Two sources, in order: batched `esummary db=mesh` (the uid is mechanical,
D015415 -> 68015415), then a per-descriptor fallback to NLM's MeSH RDF service.
The fallback is not optional — see `_trees_from_rdf`.

Branch rules, each one earned by a failed probe (see README):

  problem axis  C*                            diseases, minus NONSPECIFIC_PROBLEM
  method axis   E05.393, E05.196, L01.224.050 plus METHOD_ALLOW,
                                              minus METHOD_EXCLUDE / METHOD_DENY
  bridge vocab  D*, G*                        substances, physiological processes

  EXCLUDED from the method axis:
    E01       diagnostic procedures — mostly organ-bound. Colonoscopy and
              mammography are defined by the organ they examine, so they can
              never transfer; leaving them in made "Breast Neoplasms x
              Colonoscopy" the top-ranked gap. Two E01 terms that are NOT
              organ-bound (Liquid Biopsy, Breath Tests) are restored by name
              through METHOD_ALLOW.
    E05.318   statistics — Logistic Models, Odds Ratio, Area Under Curve are not
              methods anyone "applies to a disease".
    E05.200   mirrors E01. A descriptor can sit in several branches at once
              (Vaginal Smears is in both E01.370 and E05.200), so filtering on
              the branch letter alone is not sufficient.

On the full 79,940-paper corpus these rules yield 50 problems x 30 methods.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

DATA = Path(__file__).resolve().parent.parent / "data"
TREE_CACHE = DATA / "mesh_trees.json"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

CONTACT = os.environ.get("CONTACT_EMAIL", "dang2002991@gmail.com")
NCBI_KEY = os.environ.get("NCBI_API_KEY", "").strip()
THROTTLE = 0.11 if NCBI_KEY else 0.36

_session = requests.Session()
_session.headers.update({"User-Agent": f"ResearchScout ({CONTACT})"})


def _load_cache() -> dict:
    # Single source of truth. An earlier probe cache was kept as a fallback here
    # and held 176 descriptors with empty tree lists; falling back to it would
    # silently restore the exact failure audit_trees() exists to catch.
    if TREE_CACHE.exists():
        return json.loads(TREE_CACHE.read_text(encoding="utf-8"))
    return {}


MESH_RDF = "https://id.nlm.nih.gov/mesh"


def _trees_from_rdf(ui: str) -> list[str]:
    """Authoritative single-descriptor lookup from NLM's MeSH RDF service.

    Needed because the esummary uid convention ("D015415" -> 68015415) does not
    hold for the newer 9-digit descriptors: D000069550 (Machine Learning) maps to
    68000069550, which esummary answers with "cannot get document summary".
    That silently emptied the tree list for 500 descriptors — 6% of the corpus
    vocabulary, and the most modern 6%: Machine Learning, Deep Learning,
    Liquid Biopsy, Circulating Tumor DNA, Cell-Free Nucleic Acids, COVID-19.
    All were dropped from every axis AND from the bridge vocabulary.
    """
    try:
        r = _session.get(f"{MESH_RDF}/{ui}.json", timeout=60)
        if r.status_code != 200:
            return []
        raw = r.json().get("treeNumber") or []
        # A descriptor with exactly ONE tree position returns a bare string, not
        # a one-item list. Iterating that string yields one "tree number" per
        # character, which silently corrupted 183 descriptors — and the damage
        # is invisible because a stray 'D' still satisfies is_mechanistic().
        if isinstance(raw, str):
            raw = [raw]
        out = []
        for t in raw:
            if not isinstance(t, str):
                continue
            tn = t.rsplit("/", 1)[-1].strip()
            # a real tree number is a capital letter followed by digits/dots
            if len(tn) >= 3 and tn[0].isupper() and tn[1].isdigit():
                out.append(tn)
        return out
    except (requests.RequestException, ValueError):
        return []


def resolve_trees(uis, verbose: bool = True) -> dict:
    """UI -> list of tree numbers. Cached; only unknown UIs hit the network.

    Batched esummary first (fast, covers ~94%), then a per-descriptor RDF
    fallback for whatever came back empty.
    """
    trees = _load_cache()
    todo = sorted({u for u in uis if u not in trees})
    if todo and verbose:
        print(f"[mesh] resolving {len(todo)} descriptors via esummary")
    for i in range(0, len(todo), 150):
        chunk = todo[i:i + 150]
        uids = ",".join("68" + u[1:] for u in chunk)
        payload = {"db": "mesh", "id": uids, "retmode": "json",
                   "email": CONTACT, "tool": "ResearchScout"}
        if NCBI_KEY:
            payload["api_key"] = NCBI_KEY
        try:
            r = _session.get(f"{BASE}/esummary.fcgi", params=payload, timeout=120)
            result = r.json().get("result", {}) if r.status_code == 200 else {}
        except (requests.RequestException, ValueError):
            result = {}
        for u in chunk:
            entry = result.get("68" + u[1:], {})
            trees[u] = [lnk.get("treenum", "")
                        for lnk in entry.get("ds_idxlinks", [])
                        if lnk.get("treenum")]
        time.sleep(THROTTLE)

    # fallback for everything esummary could not place
    gaps = [u for u in trees if not trees[u]]
    if gaps:
        if verbose:
            print(f"[mesh] {len(gaps)} unresolved -> NLM MeSH RDF fallback")
        recovered = 0
        for n, u in enumerate(gaps, 1):
            tns = _trees_from_rdf(u)
            if tns:
                trees[u] = tns
                recovered += 1
            if verbose and n % 100 == 0:
                print(f"   {n}/{len(gaps)}  recovered {recovered}")
            time.sleep(0.12)
        if verbose:
            print(f"[mesh] recovered {recovered}/{len(gaps)}")

    TREE_CACHE.write_text(json.dumps(trees), encoding="utf-8")
    audit_trees(trees, verbose=verbose)
    return trees


def well_formed(tn: str) -> bool:
    """A MeSH tree number is a capital letter, a digit, then dotted digits."""
    return (isinstance(tn, str) and len(tn) >= 3
            and tn[0].isupper() and tn[1].isdigit())


def audit_trees(trees: dict | None = None, verbose: bool = True) -> dict:
    """Fail loudly on empty or malformed tree numbers.

    Two separate lookup bugs shipped silently before this existed — an esummary
    uid convention that breaks for 9-digit descriptors (500 empty), and an RDF
    field that is a bare string when there is exactly one tree position, which
    iterated per character (183 corrupted). Neither raised anything: an empty
    list just means "classifies as nothing", and a stray 'D' character still
    satisfies is_mechanistic(). Both cost real terms off the axes.

    Call this after every resolution. Silence is the failure mode to defend
    against, not exceptions.
    """
    if trees is None:
        trees = _load_cache()
    empty = [u for u, t in trees.items() if not t]
    broken = {u: t for u, t in trees.items()
              if t and not all(well_formed(x) for x in t)}
    report = {"total": len(trees), "empty": len(empty), "malformed": len(broken)}
    if verbose and (empty or broken):
        print(f"[mesh] TREE AUDIT FAILED — {len(empty)} empty, "
              f"{len(broken)} malformed of {len(trees)}")
        for u, t in list(broken.items())[:3]:
            print(f"   {u}: {t[:6]}")
        print("   re-resolve these: drop them from data/mesh_trees.json and "
              "call resolve_trees() again")
    elif verbose:
        print(f"[mesh] tree audit clean: {len(trees):,} descriptors")
    return report


# ---------------------------------------------------------------- classifiers

def is_problem(tns) -> bool:
    return any(t.startswith("C") for t in tns)


#: Positive method prefixes. Narrow on purpose.
#   E05.393     molecular / genetic investigative techniques (PCR, sequencing,
#               expression profiling, genotyping) — genuinely platform-level
#   L01.224.050 Artificial Intelligence subtree only
#
# Plain L01 (Information Science) was tried and rejected: it also contains
# Internet, Telephone, Reminder Systems, Software, Databases and Communication
# Barriers. And plain G17 (Mathematical Concepts) is unsafe — it holds Odds
# Ratio at G17.680.500. A descriptor needs only ONE matching position, so a
# broad prefix drags in everything that happens to be cross-listed under it.
#   E05.196     analytical chemistry — mass spectrometry, chromatography,
#               Raman and infrared spectroscopy, surface plasmon resonance.
#               Platform-level and organ-independent, and the branch most
#               modern early-detection work actually lives in.
METHOD_PREFIXES = ("E05.393", "E05.196", "L01.224.050")
METHOD_EXCLUDE = ("E01", "E05.200", "E05.318")

#: Transferable methods the tree rules cannot reach, kept as an explicit list so
#: the omission is a decision rather than an accident:
#:   - Metabolomics / Proteomics sit in H01 (Natural Sciences) as disciplines
#:   - Liquid Biopsy and Breath Tests sit in E01, which is excluded wholesale
#:     because that is where the organ-bound procedures live — but neither of
#:     these is organ-bound, so the blanket rule is wrong for them specifically
METHOD_ALLOW = {
    "Metabolomics", "Proteomics", "Genomics", "Transcriptome",
    "Liquid Biopsy", "Breath Tests", "Biosensing Techniques",
    "Multiomics", "Single-Cell Analysis",
}

#: Therapeutic or care-delivery terms that match a method prefix but are not
#: detection methods. `Genetic Therapy` is E05.393.420.301 and would otherwise
#: rank as a method applied to a disease in an early-DIAGNOSTICS field map.
METHOD_DENY = {
    "Genetic Therapy", "Genetic Counseling", "Drug Therapy",
    "Immunotherapy", "Radiotherapy",
}


def is_method(tns, name: str | None = None) -> bool:
    """Transferable method: platform-level, not organ-bound, not statistics."""
    if name in METHOD_DENY:
        return False
    if name in METHOD_ALLOW:
        return True
    if any(t.startswith(METHOD_EXCLUDE) for t in tns):
        return False
    return any(t.startswith(METHOD_PREFIXES) for t in tns)


def is_mechanistic(tns) -> bool:
    return any(t[:1] in ("D", "G") for t in tns)


def subtree(tns, depth: int = 1) -> set[str]:
    """First `depth`+1 levels of each position, for artifact detection.
    Two terms sharing a shallow subtree are siblings — their co-occurrence is
    an indexing convention, not evidence. ('Early Diagnosis' vs
    'Early Detection of Cancer': indexers pick one, never both.)"""
    return {".".join(t.split(".")[:depth + 1]) for t in tns}


# Terms that describe the study rather than its subject. Excluded from every axis.
GENERIC = {
    "Humans", "Female", "Male", "Adult", "Aged", "Middle Aged", "Animals",
    "Child", "Adolescent", "Young Adult", "Aged, 80 and over", "Infant",
    "Infant, Newborn", "Mice", "Rats", "Child, Preschool",
    "Retrospective Studies", "Prospective Studies", "Cross-Sectional Studies",
    "Cohort Studies", "Follow-Up Studies", "Case-Control Studies",
    "Longitudinal Studies", "Pilot Projects", "Feasibility Studies",
    "Reproducibility of Results", "Sensitivity and Specificity",
    "Predictive Value of Tests", "ROC Curve", "Area Under Curve",
    "Risk Factors", "Risk Assessment", "Prognosis", "Incidence", "Prevalence",
    "Treatment Outcome", "Time Factors", "Severity of Illness Index",
    "Surveys and Questionnaires", "Early Detection of Cancer", "Early Diagnosis",
    "Mass Screening", "Biomarkers", "Biomarkers, Tumor",
}


# Tree-C terms that are disease *states or attributes* rather than targets, plus
# histology with no organ. "Recurrence x PCR" is not a research gap, and nobody
# sets out to study "Carcinoma" in the abstract. Excluded from the problem axis.
NONSPECIFIC_PROBLEM = {
    "Disease Progression", "Genetic Predisposition to Disease",
    "Precancerous Conditions", "Neoplasm Recurrence, Local",
    "Neoplasm Invasiveness", "Neoplasm Metastasis", "Lymphatic Metastasis",
    "Asymptomatic Diseases", "Chronic Disease", "Recurrence",
    "Postoperative Complications", "Neoplasm Staging", "Comorbidity",
    "Neoplasms", "Carcinoma", "Adenocarcinoma", "Adenoma",
    "Carcinoma, Squamous Cell", "Neoplasms, Second Primary",
    "Acute Disease", "Critical Illness", "Disease Models, Animal",
    "Neoplastic Cells, Circulating", "Diabetes Mellitus",
}


def build_axes(corpus: dict, min_problem: int = 25, min_method: int = 15,
               n_problems: int = 50, n_methods: int = 30):
    """Returns (problems, methods, freq, name_of, trees) from a corpus dict."""
    from collections import Counter
    freq, name_of = Counter(), {}
    for rec in corpus.values():
        for ui, name, _major in rec["mesh"]:
            freq[ui] += 1
            name_of[ui] = name
    trees = resolve_trees([u for u in freq if freq[u] >= 4])

    def ok(ui):
        n = name_of.get(ui)
        return n not in GENERIC and n not in NONSPECIFIC_PROBLEM

    problems = sorted((u for u in freq
                       if freq[u] >= min_problem and ok(u)
                       and is_problem(trees.get(u) or [])),
                      key=lambda u: -freq[u])[:n_problems]
    methods = sorted((u for u in freq
                      if freq[u] >= min_method and ok(u)
                      and is_method(trees.get(u) or [], name_of.get(u))),
                     key=lambda u: -freq[u])[:n_methods]
    return problems, methods, freq, name_of, trees


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    corpus = json.loads((DATA / "corpus_past.json").read_text(encoding="utf-8"))
    corpus = {k: v for k, v in corpus.items() if v["year"] and v["year"] <= 2018}
    problems, methods, freq, name_of, trees = build_axes(corpus)

    print(f"\ncorpus: {len(corpus)} papers (<=2018)")
    print(f"\nPROBLEM axis — {len(problems)} terms")
    for u in problems[:12]:
        print(f"   {freq[u]:>5}  {name_of[u]}")
    print(f"\nMETHOD axis — {len(methods)} terms (E05.393 + L01, "
          f"E01/E05.200/E05.318 excluded)")
    for u in methods:
        print(f"   {freq[u]:>5}  {name_of[u]:<46} {(trees.get(u) or [''])[0]}")
