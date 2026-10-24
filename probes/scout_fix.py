"""Probe 4: rank holes by shared neighbours (Swanson ABC) instead of popularity."""
import json, itertools
from collections import Counter, defaultdict

recs = json.load(open("scout_cache.json"))
trees = json.load(open("scout_trees.json"))

freq = Counter()
for r in recs.values():
    for u, major, name in r["mesh"]:
        freq[u] += 1
name_of = {}
for r in recs.values():
    for u, major, name in r["mesh"]:
        name_of[u] = name

STOP_NAMES = {"Humans", "Female", "Male", "Adult", "Aged", "Middle Aged", "Animals",
              "Child", "Adolescent", "Young Adult", "Aged, 80 and over", "Infant",
              "Infant, Newborn", "Retrospective Studies", "Prospective Studies",
              "Reproducibility of Results", "Sensitivity and Specificity",
              "Early Detection of Cancer", "Early Diagnosis", "Mass Screening",
              "Cross-Sectional Studies", "Risk Factors", "Surveys and Questionnaires",
              "Risk Assessment", "Prognosis", "Cohort Studies", "Follow-Up Studies",
              "Predictive Value of Tests", "ROC Curve", "Case-Control Studies",
              "Treatment Outcome", "Time Factors", "Severity of Illness Index"}


def branches(u):
    return set(x[0] for x in (trees.get(u) or []) if x)


def subtree_prefix(u, depth=1):
    """first `depth` levels of each tree position, e.g. 'E01.370'"""
    out = set()
    for t in (trees.get(u) or []):
        if t:
            out.add(".".join(t.split(".")[:depth + 1]))
    return out


problems = [u for u in freq if freq[u] >= 20 and "C" in branches(u)
            and name_of.get(u) not in STOP_NAMES]
methods = [u for u in freq if freq[u] >= 20 and "E" in branches(u)
           and name_of.get(u) not in STOP_NAMES]
problems.sort(key=lambda u: -freq[u])
methods.sort(key=lambda u: -freq[u])
P, M = problems[:40], methods[:40]
print(f"axes: {len(P)} problems x {len(M)} methods (generic terms excluded)")
print("problems:", [name_of[u] for u in P[:10]])
print("methods :", [name_of[u] for u in M[:10]])

# term -> set of papers, for neighbour computation
papers_of = defaultdict(set)
for pmid, r in recs.items():
    for u, major, name in r["mesh"]:
        papers_of[u].add(pmid)

co = Counter()
for pmid, r in recs.items():
    us = {u for u, _, _ in r["mesh"]}
    for a in us:
        for b in us:
            if a < b:
                co[(a, b)] += 1


def cooc(a, b):
    return co[(a, b)] if a < b else co[(b, a)]


# neighbour sets: terms co-occurring at least 3 times
neigh = {}
for u in set(P) | set(M):
    s = set()
    for v in freq:
        if v != u and cooc(u, v) >= 3:
            s.add(v)
    neigh[u] = s

rows = []
for a in P:
    for b in M:
        if cooc(a, b) > 0:
            continue
        # vocabulary-artifact guard: skip if same MeSH subtree region
        if subtree_prefix(a) & subtree_prefix(b):
            continue
        na, nb = neigh[a], neigh[b]
        shared = na & nb
        if not shared:
            continue
        jac = len(shared) / len(na | nb)
        rows.append((len(shared), jac, name_of[a], name_of[b],
                     freq[a], freq[b],
                     [name_of[x] for x in sorted(shared, key=lambda x: -freq[x])[:5]]))

print(f"\nholes with >=1 shared intermediate: {len(rows)}  (was 673 unfiltered)")

rows.sort(key=lambda r: -r[0])
print("\n--- ranked by number of shared intermediate terms (Swanson B-terms) ---")
for sh, jac, pn, mn, pc, mc, bs in rows[:15]:
    print(f"\n  {pn} ({pc}p)  x  {mn} ({mc}p)")
    print(f"    shared intermediates: {sh}  jaccard {jac:.2f}")
    print(f"    bridge terms: {', '.join(bs)}")
