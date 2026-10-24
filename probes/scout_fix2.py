"""Probe 5: bridges restricted to mechanistic MeSH branches (D=substances, G=processes), IDF-weighted."""
import json, math
from collections import Counter, defaultdict

recs = json.load(open("scout_cache.json"))
trees = json.load(open("scout_trees.json"))
N = len(recs)

freq, name_of = Counter(), {}
for r in recs.values():
    for u, major, name in r["mesh"]:
        freq[u] += 1
        name_of[u] = name


def branches(u):
    return set(x[0] for x in (trees.get(u) or []) if x)


def sub(u, d=1):
    return set(".".join(t.split(".")[:d + 1]) for t in (trees.get(u) or []) if t)


GENERIC = {"Humans", "Female", "Male", "Adult", "Aged", "Middle Aged", "Animals",
           "Child", "Adolescent", "Young Adult", "Aged, 80 and over", "Infant",
           "Infant, Newborn", "Retrospective Studies", "Prospective Studies",
           "Reproducibility of Results", "Sensitivity and Specificity",
           "Early Detection of Cancer", "Early Diagnosis", "Mass Screening",
           "Cross-Sectional Studies", "Risk Factors", "Surveys and Questionnaires",
           "Risk Assessment", "Prognosis", "Cohort Studies", "Follow-Up Studies",
           "Predictive Value of Tests", "ROC Curve", "Case-Control Studies",
           "Treatment Outcome", "Time Factors", "Severity of Illness Index",
           "Biomarkers", "Biomarkers, Tumor", "Incidence", "Prevalence"}

# --- mechanistic bridge vocabulary: substances (D) and processes (G), and RARE ---
MAX_BRIDGE_SHARE = 0.03            # appear in <3% of corpus
bridge_terms = [u for u in freq
                if freq[u] >= 4
                and freq[u] <= MAX_BRIDGE_SHARE * N
                and name_of.get(u) not in GENERIC
                and (branches(u) & {"D", "G"})]
print(f"corpus {N} papers | mechanistic bridge vocabulary: {len(bridge_terms)} terms")

problems = sorted([u for u in freq if freq[u] >= 20 and "C" in branches(u)
                   and name_of.get(u) not in GENERIC], key=lambda u: -freq[u])[:40]
methods = sorted([u for u in freq if freq[u] >= 20 and "E" in branches(u)
                  and name_of.get(u) not in GENERIC], key=lambda u: -freq[u])[:40]

papers_of = defaultdict(set)
for pmid, r in recs.items():
    for u, _, _ in r["mesh"]:
        papers_of[u].add(pmid)

idf = {u: math.log(N / freq[u]) for u in freq}
bset = set(bridge_terms)


def mech_neigh(u):
    """mechanistic terms co-occurring with u at least twice"""
    out = set()
    for v in bset:
        if len(papers_of[u] & papers_of[v]) >= 2:
            out.add(v)
    return out


mn_cache = {u: mech_neigh(u) for u in set(problems) | set(methods)}

rows = []
for a in problems:
    for b in methods:
        if papers_of[a] & papers_of[b]:
            continue                               # not a hole
        if sub(a) & sub(b):
            continue                               # vocabulary artifact
        shared = mn_cache[a] & mn_cache[b]
        if len(shared) < 2:
            continue
        score = sum(idf[x] for x in shared)
        top = sorted(shared, key=lambda x: -idf[x])[:6]
        rows.append((score, len(shared), name_of[a], name_of[b],
                     freq[a], freq[b], [name_of[x] for x in top]))

print(f"holes surviving mechanistic-bridge filter: {len(rows)} / {40*40}")
rows.sort(reverse=True)
print("\n--- top candidates ---")
for score, n, pn, mn, pc, mc, bs in rows[:12]:
    print(f"\n  {pn} ({pc}p)  x  {mn} ({mc}p)   score {score:.1f}, {n} bridges")
    print(f"    mechanistic bridges: {', '.join(bs)}")
