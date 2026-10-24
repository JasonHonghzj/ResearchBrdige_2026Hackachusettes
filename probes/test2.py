"""HISTORICAL. Kept as the record of what was tried and rejected - the
measurements in README.md came from these. They no longer run: the
intermediate caches they read (scout_past.json, scout_cache.json,
scout_results.json) were deleted once superseded by the full corpus and
data/confirmed.json. Read them, do not expect to execute them.
"""
"""Probe 2: can we get MeSH tree numbers to define grid axes?"""
import requests, json

S = requests.Session()
S.headers.update({"User-Agent": "researchbridge-probe (dang2002991@gmail.com)"})

# Try NLM MeSH lookup API
for ui in ["D006801", "D020345", "D015415"]:
    r = S.get("https://id.nlm.nih.gov/mesh/lookup/details",
              params={"descriptor": ui}, timeout=30)
    print(ui, r.status_code, r.text[:300].replace("\n", " "))
    print()

# Try the SPARQL-ish tree endpoint
r = S.get("https://id.nlm.nih.gov/mesh/lookup/descriptor",
          params={"label": "Biomarkers", "match": "exact", "limit": 5}, timeout=30)
print("descriptor lookup:", r.status_code, r.text[:300])

# Try E-utilities db=mesh
r = S.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
          params={"db": "mesh", "term": "Biomarkers[MeSH Terms]", "retmode": "json"}, timeout=30)
print("\nmesh esearch:", r.status_code, r.text[:300])
ids = r.json()["esearchresult"].get("idlist", [])
if ids:
    r = S.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
              params={"db": "mesh", "id": ",".join(ids[:3]), "retmode": "json"}, timeout=30)
    d = r.json()
    for k, v in d.get("result", {}).items():
        if k == "uids":
            continue
        print("\nesummary keys:", list(v.keys()))
        print("treenum field:", {kk: vv for kk, vv in v.items() if "tree" in kk.lower() or "idx" in kk.lower()})
        break
