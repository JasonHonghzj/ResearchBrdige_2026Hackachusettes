"""HISTORICAL. Kept as the record of what was tried and rejected - the
measurements in README.md came from these. They no longer run: the
intermediate caches they read (scout_past.json, scout_cache.json,
scout_results.json) were deleted once superseded by the full corpus and
data/confirmed.json. Read them, do not expect to execute them.
"""
"""Probe 6d: collaborator lookup by TOPIC SEARCH (not corpus PMIDs) -> real counts."""
import requests, json, time
from collections import Counter

MAILTO = "dang2002991@gmail.com"
API = "https://api.openalex.org"
S = requests.Session()
S.headers.update({"User-Agent": f"researchbridge-probe (mailto:{MAILTO})"})
try:
    REG = json.load(open("inst_region.json"))
except Exception:
    REG = {}


def get(path, **p):
    p["mailto"] = MAILTO
    for a in range(3):
        try:
            r = S.get(f"{API}/{path}", params=p, timeout=90)
            if r.status_code == 200:
                return r.json()
            print("   HTTP", r.status_code, r.text[:140]); return None
        except Exception:
            time.sleep(2)
    return None


def verify(oids):
    todo = [o for o in oids if o not in REG]
    for i in range(0, len(todo), 50):
        ch = todo[i:i + 50]
        j = get("institutions", filter="ids.openalex:" + "|".join(ch), per_page=50)
        if j:
            for inst in j.get("results", []):
                oid = inst["id"].rsplit("/", 1)[-1]
                g = inst.get("geo") or {}
                REG[oid] = {"region": g.get("region"), "city": g.get("city"),
                            "name": inst["display_name"], "type": inst.get("type"),
                            "lineage": len(inst.get("lineage") or [])}
        for o in ch:
            REG.setdefault(o, {"region": None, "city": None, "name": "?", "type": None, "lineage": 1})
        time.sleep(0.15)
    json.dump(REG, open("inst_region.json", "w"))


def ma_labs(phrase, years="2015-", keep_parents=False):
    f = (f"title_and_abstract.search:{phrase},"
         f"authorships.institutions.geo.region:Massachusetts,"
         f"publication_year:{years}")
    j = get("works", filter=f, group_by="institutions.id", per_page=200)
    if not j:
        print(f"  '{phrase}' FAILED"); return []
    tot = get("works", filter=f, per_page=1)
    raw = Counter({g["key"].rsplit("/", 1)[-1]: g["count"]
                   for g in j.get("group_by", []) if g["key"] != "unknown"})
    verify(list(raw))
    rows = [(c, REG[o]["name"], REG[o]["city"], REG[o]["type"], REG[o]["lineage"])
            for o, c in raw.items() if REG.get(o, {}).get("region") == "Massachusetts"]
    if not keep_parents:
        rows = [r for r in rows if not (r[3] == "education" and r[4] <= 1)] or rows
    rows.sort(reverse=True)
    print(f"\n  \"{phrase}\" — {tot['meta']['count'] if tot else '?'} MA-affiliated works")
    print(f"     {len(raw)} institutions grouped -> {len(rows)} verified in MA")
    for c, nm, city, ty, lin in rows[:8]:
        print(f"       {c:>4} | {nm} ({city}) [{ty}]")
    return rows


print("=" * 72)
print("Collaborator lookup by topic search, Massachusetts, 2015+")
print("=" * 72)
method = ma_labs("exhaled breath volatile organic compounds")
problem = ma_labs("pancreatic cancer early detection")

mset = {r[1] for r in method}
pset = {r[1] for r in problem}
print("\n" + "=" * 72)
print("GAP HANDOFF — who to introduce to whom")
print("=" * 72)
print(f"  holds the METHOD only : {sorted(mset - pset)[:6]}")
print(f"  holds the PROBLEM only: {sorted(pset - mset)[:6]}")
print(f"  already holds both    : {sorted(mset & pset)[:6]}")

json.dump({"method": method, "problem": problem},
          open("scout_openalex_result.json", "w"), indent=1)
print("\nwrote scout_openalex_result.json")
