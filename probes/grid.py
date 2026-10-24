"""HISTORICAL. Kept as the record of what was tried and rejected - the
measurements in README.md came from these. They no longer run: the
intermediate caches they read (scout_past.json, scout_cache.json,
scout_results.json) were deleted once superseded by the full corpus and
data/confirmed.json. Read them, do not expect to execute them.
"""
"""Probe 3: build the problem x method grid and measure whether holes are meaningful."""
import requests, time, re, json, os, itertools
from collections import Counter, defaultdict

EMAIL = "dang2002991@gmail.com"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
S = requests.Session()
S.headers.update({"User-Agent": f"researchbridge-probe ({EMAIL})"})

QUERY = '("Early Detection of Cancer"[MeSH Terms] OR "Early Diagnosis"[MeSH Terms]) AND 2010:2026[dp]'
N_WANT = 6000
CACHE = "scout_cache.json"


def fetch_corpus():
    if os.path.exists(CACHE):
        return json.load(open(CACHE))
    r = S.get(f"{BASE}/esearch.fcgi", params={
        "db": "pubmed", "term": QUERY, "retmode": "json",
        "retmax": 0, "usehistory": "y", "email": EMAIL}, timeout=60)
    j = r.json()["esearchresult"]
    env, qk = j["webenv"], j["querykey"]
    print("corpus available:", j["count"])
    recs = {}
    for start in range(0, N_WANT, 200):
        for attempt in range(3):
            try:
                r = S.get(f"{BASE}/efetch.fcgi", params={
                    "db": "pubmed", "WebEnv": env, "query_key": qk,
                    "retstart": start, "retmax": 200,
                    "retmode": "xml", "email": EMAIL}, timeout=120)
                r.raise_for_status()
                break
            except Exception as e:
                print("  retry", attempt, e); time.sleep(2)
        else:
            continue
        for art in re.findall(r"<PubmedArticle>.*?</PubmedArticle>", r.text, re.S):
            pm = re.search(r"<PMID[^>]*>(\d+)</PMID>", art)
            if not pm:
                continue
            yr = re.search(r"<PubDate>.*?<Year>(\d{4})</Year>", art, re.S)
            mesh = re.findall(
                r'<DescriptorName UI="(D\d+)"[^>]*MajorTopicYN="(Y|N)">([^<]+)</DescriptorName>', art)
            recs[pm.group(1)] = {
                "year": int(yr.group(1)) if yr else None,
                "mesh": [[u, m, n] for u, m, n in mesh],
            }
        print(f"  fetched {len(recs)}")
        time.sleep(0.4)
    json.dump(recs, open(CACHE, "w"))
    return recs


def tree_numbers(uis):
    path = "scout_trees.json"
    trees = json.load(open(path)) if os.path.exists(path) else {}
    todo = [u for u in uis if u not in trees]
    print(f"resolving tree numbers for {len(todo)} descriptors")
    for i in range(0, len(todo), 150):
        chunk = todo[i:i + 150]
        uids = ",".join("68" + u[1:] for u in chunk)
        try:
            r = S.get(f"{BASE}/esummary.fcgi", params={
                "db": "mesh", "id": uids, "retmode": "json"}, timeout=90)
            res = r.json().get("result", {})
        except Exception as e:
            print("  skip chunk", e); continue
        for u in chunk:
            v = res.get("68" + u[1:], {})
            trees[u] = [l.get("treenum", "") for l in v.get("ds_idxlinks", [])]
        print(f"  {i + len(chunk)}/{len(todo)}")
        time.sleep(0.4)
    json.dump(trees, open(path, "w"))
    return trees


recs = fetch_corpus()
print(f"\ncorpus: {len(recs)} records")

freq = Counter()
for r in recs.values():
    for u, major, name in r["mesh"]:
        freq[(u, name)] += 1

uis = [u for (u, n), c in freq.items() if c >= 5]
trees = tree_numbers(uis)

STOP = {"Humans", "Female", "Male", "Adult", "Aged", "Middle Aged", "Animals",
        "Child", "Adolescent", "Young Adult", "Aged, 80 and over", "Infant",
        "Infant, Newborn", "Retrospective Studies", "Prospective Studies",
        "Reproducibility of Results", "Sensitivity and Specificity"}


def branch(u):
    t = trees.get(u) or []
    return set(x[0] for x in t if x)


problems, methods = Counter(), Counter()
for (u, name), c in freq.items():
    if name in STOP or c < 5:
        continue
    b = branch(u)
    if "C" in b or "F03" in str(trees.get(u)):
        problems[(u, name)] = c
    elif "E" in b:
        methods[(u, name)] = c

print(f"\nproblem-axis terms (MeSH tree C): {len(problems)}")
print(f"method-axis terms  (MeSH tree E): {len(methods)}")

TOP = 40
P = [k for k, _ in problems.most_common(TOP)]
M = [k for k, _ in methods.most_common(TOP)]
print("\ntop problems:", [n for _, n in P[:12]])
print("top methods :", [n for _, n in M[:12]])

pset = {u for u, _ in P}
mset = {u for u, _ in M}
co = Counter()
for r in recs.values():
    us = {u for u, _, _ in r["mesh"]}
    for a in us & pset:
        for b in us & mset:
            co[(a, b)] += 1

cells = TOP * TOP
nonzero = sum(1 for (a, _n) in P for (b, _m) in M if co[(a, b)] > 0)
ge3 = sum(1 for (a, _n) in P for (b, _m) in M if co[(a, b)] >= 3)
print(f"\nGRID {TOP}x{TOP} = {cells} cells")
print(f"  non-empty : {nonzero} ({nonzero/cells:.0%})")
print(f"  >=3 papers: {ge3} ({ge3/cells:.0%})")
print(f"  EMPTY     : {cells-nonzero} ({(cells-nonzero)/cells:.0%})")

# the interesting part: holes where BOTH axes are busy
print("\n--- empty cells where both problem and method are busy ---")
holes = []
for (a, pn) in P:
    for (b, mn) in M:
        if co[(a, b)] == 0:
            holes.append((problems[(a, pn)] * methods[(b, mn)], pn, mn,
                          problems[(a, pn)], methods[(b, mn)]))
holes.sort(reverse=True)
for score, pn, mn, pc, mc in holes[:15]:
    print(f"  {pn} ({pc})  x  {mn} ({mc})   -> 0 papers")
print(f"\ntotal holes with both axes >=20 papers: "
      f"{sum(1 for s,p,m,pc,mc in holes if pc>=20 and mc>=20)}")
