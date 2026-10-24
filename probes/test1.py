"""HISTORICAL. Kept as the record of what was tried and rejected - the
measurements in README.md came from these. They no longer run: the
intermediate caches they read (scout_past.json, scout_cache.json,
scout_results.json) were deleted once superseded by the full corpus and
data/confirmed.json. Read them, do not expect to execute them.
"""
"""Feasibility probe 1: can we get a big MeSH-annotated corpus fast?"""
import requests, time, re

EMAIL = "dang2002991@gmail.com"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
S = requests.Session()
S.headers.update({"User-Agent": f"researchbridge-probe ({EMAIL})"})

QUERY = '("Early Detection of Cancer"[MeSH Terms] OR "Early Diagnosis"[MeSH Terms]) AND 2010:2026[dp]'

r = S.get(f"{BASE}/esearch.fcgi", params={
    "db": "pubmed", "term": QUERY, "retmode": "json",
    "retmax": 0, "usehistory": "y", "email": EMAIL,
}, timeout=60)
r.raise_for_status()
j = r.json()["esearchresult"]
print("total hits:", j["count"])
print("webenv:", j["webenv"][:30], "querykey:", j["querykey"])

# pull one batch of 200 and look at MeSH annotation rate
t0 = time.time()
r = S.get(f"{BASE}/efetch.fcgi", params={
    "db": "pubmed", "WebEnv": j["webenv"], "query_key": j["querykey"],
    "retstart": 0, "retmax": 200, "retmode": "xml", "email": EMAIL,
}, timeout=120)
r.raise_for_status()
xml = r.text
print(f"efetch 200 records in {time.time()-t0:.1f}s, {len(xml)/1024:.0f} KB")

arts = re.findall(r"<PubmedArticle>.*?</PubmedArticle>", xml, re.S)
print("articles parsed:", len(arts))
with_mesh = sum(1 for a in arts if "<MeshHeading>" in a)
with_abs = sum(1 for a in arts if "<AbstractText" in a)
print(f"have MeSH: {with_mesh}/{len(arts)}   have abstract: {with_abs}/{len(arts)}")

terms = re.findall(r'<DescriptorName UI="(D\d+)"[^>]*>([^<]+)</DescriptorName>', arts[0])
print("\nexample record MeSH terms:")
for ui, name in terms:
    print("  ", ui, name)
