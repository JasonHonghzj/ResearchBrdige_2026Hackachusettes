"""Time-sliced validation: do the gaps we flag in the PAST get filled in the FUTURE
   more often than comparable empty cells?"""
import requests, time, re, json, os, math, random
from collections import Counter, defaultdict

EMAIL = "dang2002991@gmail.com"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
S = requests.Session()
S.headers.update({"User-Agent": f"research-scout-probe ({EMAIL})"})
random.seed(0)

TOPIC = '("Early Detection of Cancer"[MeSH Terms] OR "Early Diagnosis"[MeSH Terms])'
WINDOWS = {"past": "2005:2018", "future": "2019:2026"}
CAP = 14000


def fetch(tag, daterange):
    cache = f"scout_{tag}.json"
    if os.path.exists(cache):
        d = json.load(open(cache))
        print(f"[{tag}] cached {len(d)} records")
        return d
    q = f"{TOPIC} AND {daterange}[dp]"
    r = S.get(f"{BASE}/esearch.fcgi", params={
        "db": "pubmed", "term": q, "retmode": "json", "retmax": 0,
        "usehistory": "y", "email": EMAIL}, timeout=60)
    j = r.json()["esearchresult"]
    total = int(j["count"]); env, qk = j["webenv"], j["querykey"]
    want = min(total, CAP)
    print(f"[{tag}] {daterange}: {total} available, fetching {want}")
    recs = {}
    for start in range(0, want, 200):
        for att in range(4):
            try:
                rr = S.get(f"{BASE}/efetch.fcgi", params={
                    "db": "pubmed", "WebEnv": env, "query_key": qk,
                    "retstart": start, "retmax": 200, "retmode": "xml",
                    "email": EMAIL}, timeout=180)
                rr.raise_for_status(); break
            except Exception as e:
                print("   retry", att, type(e).__name__); time.sleep(3)
        else:
            continue
        for art in re.findall(r"<PubmedArticle>.*?</PubmedArticle>", rr.text, re.S):
            pm = re.search(r"<PMID[^>]*>(\d+)</PMID>", art)
            if not pm:
                continue
            yr = re.search(r"<PubDate>.*?<Year>(\d{4})</Year>", art, re.S)
            mesh = re.findall(r'<DescriptorName UI="(D\d+)"[^>]*>([^<]+)</DescriptorName>', art)
            recs[pm.group(1)] = {"year": int(yr.group(1)) if yr else None,
                                 "mesh": [[u, n] for u, n in mesh]}
        if start % 2000 == 0:
            print(f"   {len(recs)}")
        time.sleep(0.35)
    json.dump(recs, open(cache, "w"))
    print(f"[{tag}] fetched {len(recs)}")
    return recs


past = fetch("past", WINDOWS["past"])
future = fetch("future", WINDOWS["future"])


def trees_for(uis):
    path = "scout_trees.json"
    trees = json.load(open(path)) if os.path.exists(path) else {}
    todo = sorted(u for u in uis if u not in trees)
    if todo:
        print(f"resolving {len(todo)} tree numbers")
        for i in range(0, len(todo), 150):
            chunk = todo[i:i + 150]
            try:
                r = S.get(f"{BASE}/esummary.fcgi", params={
                    "db": "mesh", "id": ",".join("68" + u[1:] for u in chunk),
                    "retmode": "json"}, timeout=120)
                res = r.json().get("result", {})
            except Exception as e:
                print("  skip", e); continue
            for u in chunk:
                v = res.get("68" + u[1:], {})
                trees[u] = [l.get("treenum", "") for l in v.get("ds_idxlinks", [])]
            time.sleep(0.35)
        json.dump(trees, open(path, "w"))
    return trees


pfreq, name_of = Counter(), {}
for r in past.values():
    for u, n in r["mesh"]:
        pfreq[u] += 1; name_of[u] = n
for r in future.values():
    for u, n in r["mesh"]:
        name_of.setdefault(u, n)

trees = trees_for([u for u in pfreq if pfreq[u] >= 4])
N = len(past)
print(f"\npast corpus {N} | future corpus {len(future)}")


def tn(u):
    return [t for t in (trees.get(u) or []) if t]


def is_problem(u):
    return any(t.startswith("C") for t in tn(u))


def is_method(u):
    # E05 = Investigative Techniques, L01 = Information Science (incl. machine learning).
    # E01 (Diagnosis) deliberately EXCLUDED: organ-bound procedures can never transfer.
    return any(t.startswith("E05") or t.startswith("L01") for t in tn(u))


def is_mech(u):
    return any(t[0] in "DG" for t in tn(u))


GENERIC = {"Humans", "Female", "Male", "Adult", "Aged", "Middle Aged", "Animals",
           "Child", "Adolescent", "Young Adult", "Aged, 80 and over", "Infant",
           "Infant, Newborn", "Retrospective Studies", "Prospective Studies",
           "Reproducibility of Results", "Sensitivity and Specificity", "Mice",
           "Early Detection of Cancer", "Early Diagnosis", "Mass Screening",
           "Cross-Sectional Studies", "Risk Factors", "Surveys and Questionnaires",
           "Risk Assessment", "Prognosis", "Cohort Studies", "Follow-Up Studies",
           "Predictive Value of Tests", "ROC Curve", "Case-Control Studies",
           "Treatment Outcome", "Time Factors", "Severity of Illness Index",
           "Biomarkers", "Biomarkers, Tumor", "Incidence", "Prevalence", "Adaptor Proteins, Signal Transducing"}

P = sorted([u for u in pfreq if pfreq[u] >= 25 and is_problem(u)
            and name_of[u] not in GENERIC], key=lambda u: -pfreq[u])[:50]
M = sorted([u for u in pfreq if pfreq[u] >= 15 and is_method(u)
            and name_of[u] not in GENERIC], key=lambda u: -pfreq[u])[:30]
print(f"axes: {len(P)} problems x {len(M)} transferable methods")
print("problems:", [name_of[u] for u in P[:10]])
print("methods :", [name_of[u] for u in M[:15]])

pap_past = defaultdict(set)
for pmid, r in past.values().__class__ and past.items():
    for u, _ in r["mesh"]:
        pap_past[u].add(pmid)
pap_fut = defaultdict(set)
for pmid, r in future.items():
    for u, _ in r["mesh"]:
        pap_fut[u].add(pmid)

idf = {u: math.log(N / pfreq[u]) for u in pfreq}
bridges_vocab = {u for u in pfreq if 4 <= pfreq[u] <= 0.03 * N
                 and is_mech(u) and name_of[u] not in GENERIC}
print(f"mechanistic bridge vocabulary: {len(bridges_vocab)}")

mech_n = {}
for u in set(P) | set(M):
    mech_n[u] = {v for v in bridges_vocab if len(pap_past[u] & pap_past[v]) >= 2}


def subtop(u):
    return {".".join(t.split(".")[:2]) for t in tn(u)}


holes, flagged = [], []
for a in P:
    for b in M:
        if pap_past[a] & pap_past[b]:
            continue
        if subtop(a) & subtop(b):
            continue
        filled = len(pap_fut[a] & pap_fut[b])
        shared = mech_n[a] & mech_n[b]
        rec = {"p": name_of[a], "m": name_of[b], "pc": pfreq[a], "mc": pfreq[b],
               "filled": filled, "nb": len(shared),
               "score": sum(idf[x] for x in shared),
               "bridges": [name_of[x] for x in sorted(shared, key=lambda x: -idf[x])[:5]]}
        holes.append(rec)
        if len(shared) >= 2:
            flagged.append(rec)

print(f"\nempty cells in PAST grid: {len(holes)}")
print(f"flagged by mechanistic-bridge rule: {len(flagged)}")


def rate(rows, thr=1):
    if not rows:
        return 0.0, 0
    k = sum(1 for r in rows if r["filled"] >= thr)
    return k / len(rows), k


for thr in (1, 3):
    fr, fk = rate(flagged, thr)
    ar, ak = rate(holes, thr)
    print(f"\n--- fill threshold: >={thr} future paper(s) ---")
    print(f"  FLAGGED gaps filled : {fk}/{len(flagged)} = {fr:.0%}")
    print(f"  ALL empty cells     : {ak}/{len(holes)} = {ar:.0%}")
    unflagged = [r for r in holes if r["nb"] < 2]
    ur, uk = rate(unflagged, thr)
    print(f"  UNFLAGGED cells     : {uk}/{len(unflagged)} = {ur:.0%}")
    if ur > 0:
        print(f"  LIFT over unflagged : {fr/ur:.1f}x")

    # popularity-matched control: same axis-popularity deciles, ignore bridges
    buckets = defaultdict(list)
    for r in holes:
        buckets[(min(4, int(math.log10(max(r['pc'], 1)) * 2)),
                 min(4, int(math.log10(max(r['mc'], 1)) * 2)))].append(r)
    ctrl = []
    for r in flagged:
        key = (min(4, int(math.log10(max(r['pc'], 1)) * 2)),
               min(4, int(math.log10(max(r['mc'], 1)) * 2)))
        pool = [x for x in buckets[key] if x["nb"] < 2]
        if pool:
            ctrl.append(random.choice(pool))
    cr, ck = rate(ctrl, thr)
    print(f"  POPULARITY-MATCHED  : {ck}/{len(ctrl)} = {cr:.0%}"
          + (f"   -> lift {fr/cr:.1f}x" if cr else ""))

print("\n--- top 12 flagged gaps, with what actually happened ---")
for r in sorted(flagged, key=lambda r: -r["score"])[:12]:
    verdict = f"FILLED ({r['filled']} papers)" if r["filled"] else "still open"
    print(f"  {r['p']} ({r['pc']}p) x {r['m']} ({r['mc']}p)  ->  {verdict}")
    print(f"      bridges: {', '.join(r['bridges'])}")

json.dump({"holes": holes, "flagged": flagged}, open("scout_results.json", "w"), indent=1)
print("\nwrote scout_results.json")
