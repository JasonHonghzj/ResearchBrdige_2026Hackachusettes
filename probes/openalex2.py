"""HISTORICAL. Kept as the record of what was tried and rejected - the
measurements in README.md came from these. They no longer run: the
intermediate caches they read (scout_past.json, scout_cache.json,
scout_results.json) were deleted once superseded by the full corpus and
data/confirmed.json. Read them, do not expect to execute them.
"""
"""Probe 6b: join PubMed MeSH -> PMIDs -> OpenAlex institutions, filtered to Massachusetts."""
import requests, json, time
from collections import Counter, defaultdict

MAILTO = "dang2002991@gmail.com"
API = "https://api.openalex.org"
S = requests.Session()
S.headers.update({"User-Agent": f"researchbridge-probe (mailto:{MAILTO})"})


def get(path, **p):
    p["mailto"] = MAILTO
    for att in range(3):
        try:
            r = S.get(f"{API}/{path}", params=p, timeout=90)
            if r.status_code == 200:
                return r.json()
            print(f"    HTTP {r.status_code} {r.text[:160]}")
            return None
        except Exception as e:
            print("    retry", att, type(e).__name__); time.sleep(2)
    return None


print("TEST A — does the Massachusetts region filter work?")
j = get("works", filter="authorships.institutions.geo.region:Massachusetts", per_page=1)
print("   MA works total:", j["meta"]["count"] if j else "FAILED")

print("\nTEST B — how many PMIDs can one OR list hold?")
past = json.load(open("scout_past.json"))
all_pmids = list(past)
for n in (25, 50, 100):
    j = get("works", filter="pmid:" + "|".join(all_pmids[:n]), per_page=1)
    print(f"   {n} PMIDs -> " + (f"{j['meta']['count']} matched" if j else "REJECTED"))

print("\nTEST C — build MA institution ranking for one MeSH term")
name_of, by_term = {}, defaultdict(list)
for pmid, r in past.items():
    for u, nm in r["mesh"]:
        name_of[u] = nm
        by_term[u].append(pmid)

# pick a transferable method term and a disease term that are actually present
trees = json.load(open("scout_trees.json"))
is_m = lambda u: any(t.startswith("E05.393") or t.startswith("L01")
                     for t in (trees.get(u) or []) if t)
is_p = lambda u: any(t.startswith("C") for t in (trees.get(u) or []) if t)
meth = sorted([u for u in by_term if is_m(u)], key=lambda u: -len(by_term[u]))[:6]
prob = sorted([u for u in by_term if is_p(u)], key=lambda u: -len(by_term[u]))[:6]
print("   method candidates :", [(name_of[u], len(by_term[u])) for u in meth])
print("   problem candidates:", [(name_of[u], len(by_term[u])) for u in prob])


def ma_ranking(ui, cap=600):
    pmids = by_term[ui][:cap]
    tally, matched = Counter(), 0
    for i in range(0, len(pmids), 50):
        chunk = pmids[i:i + 50]
        j = get("works",
                filter="pmid:" + "|".join(chunk)
                       + ",authorships.institutions.geo.region:Massachusetts",
                group_by="institutions.id", per_page=200)
        if not j:
            continue
        for g in j.get("group_by", []):
            if g["key"] != "unknown":
                tally[(g["key"].rsplit("/", 1)[-1], g["key_display_name"])] += g["count"]
                matched += g["count"]
        time.sleep(0.15)
    return tally, len(pmids)


for ui in [meth[0], prob[0]]:
    tally, n = ma_ranking(ui)
    print(f"\n   --- {name_of[ui]} ({n} PMIDs queried) ---")
    if not tally:
        print("       no MA institutions found")
        continue
    for (oid, nm), c in tally.most_common(8):
        print(f"       {c:>4} papers | {nm}")

print("\nTEST D — the gap handoff: who holds each half, and does anyone hold both?")
m_t, _ = ma_ranking(meth[0])
p_t, _ = ma_ranking(prob[0])
mset = {nm for (_, nm) in m_t}
pset = {nm for (_, nm) in p_t}
print(f"   method half '{name_of[meth[0]]}': {len(mset)} MA institutions")
print(f"   problem half '{name_of[prob[0]]}': {len(pset)} MA institutions")
print(f"   hold BOTH already: {len(mset & pset)}")
only_m = sorted(mset - pset)[:5]
only_p = sorted(pset - mset)[:5]
print(f"   method-only (candidates to introduce): {only_m}")
print(f"   problem-only (candidates to introduce): {only_p}")

json.dump({"method_term": name_of[meth[0]], "problem_term": name_of[prob[0]],
           "method_insts": [[nm, c] for (_, nm), c in m_t.most_common()],
           "problem_insts": [[nm, c] for (_, nm), c in p_t.most_common()]},
          open("scout_openalex_result.json", "w"), indent=1)
print("\nwrote scout_openalex_result.json")
