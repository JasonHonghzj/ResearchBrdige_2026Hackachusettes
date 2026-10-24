"""Probe 6c: corrected MA-only institution ranking (verify each institution's own region)."""
import requests, json, time
from collections import Counter, defaultdict

MAILTO = "dang2002991@gmail.com"
API = "https://api.openalex.org"
S = requests.Session()
S.headers.update({"User-Agent": f"research-scout-probe (mailto:{MAILTO})"})
REGION_CACHE = "scout_inst_region.json"
try:
    REG = json.load(open(REGION_CACHE))
except Exception:
    REG = {}


def get(path, **p):
    p["mailto"] = MAILTO
    for att in range(3):
        try:
            r = S.get(f"{API}/{path}", params=p, timeout=90)
            if r.status_code == 200:
                return r.json()
            print(f"    HTTP {r.status_code} {r.text[:140]}")
            return None
        except Exception as e:
            time.sleep(2)
    return None


def verify_regions(oids):
    """fill REG[oid] = (region, city, type, parent_count) for unknown ids"""
    todo = [o for o in oids if o not in REG]
    for i in range(0, len(todo), 50):
        ch = todo[i:i + 50]
        j = get("institutions", filter="ids.openalex:" + "|".join(ch), per_page=50)
        if not j:
            continue
        for inst in j.get("results", []):
            oid = inst["id"].rsplit("/", 1)[-1]
            geo = inst.get("geo") or {}
            REG[oid] = {"region": geo.get("region"), "city": geo.get("city"),
                        "name": inst["display_name"], "type": inst.get("type"),
                        "lineage": len(inst.get("lineage") or [])}
        for o in ch:
            REG.setdefault(o, {"region": None, "city": None, "name": "?",
                               "type": None, "lineage": 1})
        time.sleep(0.15)
    json.dump(REG, open(REGION_CACHE, "w"))


past = json.load(open("scout_past.json"))
trees = json.load(open("scout_trees.json"))
name_of, by_term = {}, defaultdict(list)
for pmid, r in past.items():
    for u, nm in r["mesh"]:
        name_of[u] = nm
        by_term[u].append(pmid)
ui_of = {v: k for k, v in name_of.items()}


def ma_labs(term_name, cap=600, verbose=True):
    ui = ui_of.get(term_name)
    if not ui:
        print(f"  '{term_name}' not in corpus"); return []
    pmids = by_term[ui][:cap]
    raw = Counter()
    for i in range(0, len(pmids), 50):
        j = get("works",
                filter="pmid:" + "|".join(pmids[i:i + 50])
                       + ",authorships.institutions.geo.region:Massachusetts",
                group_by="institutions.id", per_page=200)
        if not j:
            continue
        for g in j.get("group_by", []):
            if g["key"] != "unknown":
                raw[g["key"].rsplit("/", 1)[-1]] += g["count"]
        time.sleep(0.15)
    verify_regions(list(raw))
    rows = [(c, REG[o]["name"], REG[o]["city"], REG[o]["type"], REG[o]["lineage"])
            for o, c in raw.items() if REG.get(o, {}).get("region") == "Massachusetts"]
    rows.sort(reverse=True)
    if verbose:
        dropped = len(raw) - len(rows)
        print(f"\n  {term_name} — {len(pmids)} PMIDs | {len(raw)} institutions grouped, "
              f"{dropped} dropped as non-MA, {len(rows)} kept")
        for c, nm, city, ty, lin in rows[:10]:
            tag = "parent" if lin <= 1 else "unit"
            print(f"      {c:>4} | {nm} ({city}) [{ty}/{tag}]")
    return rows


print("=" * 72)
print("CORRECTED: Massachusetts-only institution rankings")
print("=" * 72)
m = ma_labs("Polymerase Chain Reaction")
p = ma_labs("Pancreatic Neoplasms")
if not p:
    p = ma_labs("Colorectal Neoplasms")

mset = {r[1] for r in m}
pset = {r[1] for r in p}
print("\n" + "=" * 72)
print("GAP HANDOFF")
print("=" * 72)
print(f"  method half : {len(mset)} MA institutions")
print(f"  problem half: {len(pset)} MA institutions")
print(f"  hold both   : {len(mset & pset)}  -> {sorted(mset & pset)[:4]}")
print(f"  method only : {sorted(mset - pset)[:4]}")
print(f"  problem only: {sorted(pset - mset)[:4]}")

json.dump({"method": m, "problem": p}, open("scout_openalex_result.json", "w"), indent=1)
print("\nwrote scout_openalex_result.json")
