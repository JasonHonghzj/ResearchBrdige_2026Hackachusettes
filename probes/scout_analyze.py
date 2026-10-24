"""Time-sliced validation, strict date hygiene. Reads caches written by scout_timeslice.py."""
import json, math, random, os, requests, time
from collections import Counter, defaultdict

random.seed(0)
SPLIT = 2018                      # past = year <= SPLIT, future = year > SPLIT
S = requests.Session()
S.headers.update({"User-Agent": "research-scout-probe (dang2002991@gmail.com)"})
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

raw_past = json.load(open("scout_past.json"))
raw_fut = json.load(open("scout_future.json"))

# strict split on parsed publication year; drop any PMID that appears in both
past = {k: v for k, v in raw_past.items() if v["year"] and v["year"] <= SPLIT}
fut = {k: v for k, v in raw_fut.items() if v["year"] and v["year"] > SPLIT}
overlap = set(past) & set(fut)
for k in overlap:
    fut.pop(k, None)
print(f"raw: past {len(raw_past)}, future {len(raw_fut)}")
print(f"strict: past(<={SPLIT}) {len(past)}, future(>{SPLIT}) {len(fut)}, overlap removed {len(overlap)}")
print(f"  dropped from past as leakage: {len(raw_past)-len(past)}")

pfreq, name_of = Counter(), {}
for r in past.values():
    for u, n in r["mesh"]:
        pfreq[u] += 1; name_of[u] = n
for r in fut.values():
    for u, n in r["mesh"]:
        name_of.setdefault(u, n)

# tree numbers
trees = json.load(open("scout_trees.json")) if os.path.exists("scout_trees.json") else {}
todo = sorted(u for u in pfreq if pfreq[u] >= 4 and u not in trees)
if todo:
    print(f"resolving {len(todo)} tree numbers")
    for i in range(0, len(todo), 150):
        ch = todo[i:i + 150]
        try:
            r = S.get(f"{BASE}/esummary.fcgi", params={
                "db": "mesh", "id": ",".join("68" + u[1:] for u in ch),
                "retmode": "json"}, timeout=120)
            res = r.json().get("result", {})
        except Exception as e:
            print("  skip", e); continue
        for u in ch:
            v = res.get("68" + u[1:], {})
            trees[u] = [l.get("treenum", "") for l in v.get("ds_idxlinks", [])]
        time.sleep(0.35)
    json.dump(trees, open("scout_trees.json", "w"))

N = len(past)


def tn(u):
    return [t for t in (trees.get(u) or []) if t]


GENERIC = {"Humans", "Female", "Male", "Adult", "Aged", "Middle Aged", "Animals",
           "Child", "Adolescent", "Young Adult", "Aged, 80 and over", "Infant",
           "Infant, Newborn", "Retrospective Studies", "Prospective Studies",
           "Reproducibility of Results", "Sensitivity and Specificity", "Mice",
           "Early Detection of Cancer", "Early Diagnosis", "Mass Screening",
           "Cross-Sectional Studies", "Risk Factors", "Surveys and Questionnaires",
           "Risk Assessment", "Prognosis", "Cohort Studies", "Follow-Up Studies",
           "Predictive Value of Tests", "ROC Curve", "Case-Control Studies",
           "Treatment Outcome", "Time Factors", "Severity of Illness Index",
           "Biomarkers", "Biomarkers, Tumor", "Incidence", "Prevalence",
           "Reproducibility of Results", "Aged, 80 and over"}

is_problem = lambda u: any(t.startswith("C") for t in tn(u))
# E05 Investigative Techniques + L01 Information Science (ML/AI). E01 Diagnosis EXCLUDED:
# organ-bound procedures (colonoscopy, mammography) can never transfer across organs.
is_method = lambda u: any(t.startswith("E05") or t.startswith("L01") for t in tn(u))
is_mech = lambda u: any(t[0] in "DG" for t in tn(u))

P = sorted([u for u in pfreq if pfreq[u] >= 25 and is_problem(u)
            and name_of[u] not in GENERIC], key=lambda u: -pfreq[u])[:50]
M = sorted([u for u in pfreq if pfreq[u] >= 15 and is_method(u)
            and name_of[u] not in GENERIC], key=lambda u: -pfreq[u])[:30]
print(f"\naxes: {len(P)} problems x {len(M)} transferable methods")
print("problems:", [name_of[u] for u in P[:10]])
print("methods :", [name_of[u] for u in M])

pp, pf = defaultdict(set), defaultdict(set)
for k, r in past.items():
    for u, _ in r["mesh"]:
        pp[u].add(k)
for k, r in fut.items():
    for u, _ in r["mesh"]:
        pf[u].add(k)

idf = {u: math.log(N / pfreq[u]) for u in pfreq}
vocab = {u for u in pfreq if 4 <= pfreq[u] <= 0.03 * N and is_mech(u)
         and name_of[u] not in GENERIC}
print(f"mechanistic bridge vocabulary: {len(vocab)}")
mech = {u: {v for v in vocab if len(pp[u] & pp[v]) >= 2} for u in set(P) | set(M)}
subtop = lambda u: {".".join(t.split(".")[:2]) for t in tn(u)}

holes = []
for a in P:
    for b in M:
        if pp[a] & pp[b]:
            continue
        if subtop(a) & subtop(b):
            continue
        sh = mech[a] & mech[b]
        holes.append({"p": name_of[a], "m": name_of[b], "pc": pfreq[a], "mc": pfreq[b],
                      "filled": len(pf[a] & pf[b]), "nb": len(sh),
                      "score": sum(idf[x] for x in sh),
                      "bridges": [name_of[x] for x in sorted(sh, key=lambda x: -idf[x])[:5]]})

flagged = [h for h in holes if h["nb"] >= 2]
unflag = [h for h in holes if h["nb"] < 2]
print(f"\nempty cells in PAST grid: {len(holes)}  (of {len(P)*len(M)})")
print(f"flagged by mechanistic-bridge rule: {len(flagged)}")


def rate(rows, thr):
    if not rows:
        return 0.0, 0
    k = sum(1 for r in rows if r["filled"] >= thr)
    return k / len(rows), k


for thr in (1, 3):
    fr, fk = rate(flagged, thr)
    ur, uk = rate(unflag, thr)
    ar, ak = rate(holes, thr)
    print(f"\n=== fill threshold >= {thr} future paper(s) ===")
    print(f"  FLAGGED   : {fk}/{len(flagged)} = {fr:.0%}")
    print(f"  UNFLAGGED : {uk}/{len(unflag)} = {ur:.0%}")
    print(f"  ALL HOLES : {ak}/{len(holes)} = {ar:.0%}")
    if ur:
        print(f"  LIFT      : {fr/ur:.2f}x vs unflagged")
    # popularity-matched control
    dec = lambda r: (min(5, int(math.log10(max(r['pc'], 1)) * 2.5)),
                     min(5, int(math.log10(max(r['mc'], 1)) * 2.5)))
    pool = defaultdict(list)
    for r in unflag:
        pool[dec(r)].append(r)
    ctrl = [random.choice(pool[dec(r)]) for r in flagged if pool[dec(r)]]
    cr, ck = rate(ctrl, thr)
    print(f"  MATCHED CTRL: {ck}/{len(ctrl)} = {cr:.0%}"
          + (f"  -> lift {fr/cr:.2f}x" if cr else "  -> lift inf"))

print("\n--- all flagged gaps, ranked, with what actually happened ---")
for r in sorted(flagged, key=lambda r: -r["score"]):
    v = f"FILLED x{r['filled']}" if r["filled"] else "still open"
    print(f"  [{v:>12}] {r['p']} ({r['pc']}p) x {r['m']} ({r['mc']}p)")
    print(f"                 bridges: {', '.join(r['bridges'])}")

json.dump({"flagged": flagged, "holes": holes}, open("scout_results.json", "w"), indent=1)
print("\nwrote scout_results.json")
