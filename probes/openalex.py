"""HISTORICAL. Kept as the record of what was tried and rejected - the
measurements in README.md came from these. They no longer run: the
intermediate caches they read (scout_past.json, scout_cache.json,
scout_results.json) were deleted once superseded by the full corpus and
data/confirmed.json. Read them, do not expect to execute them.
"""
"""Probe 6: can OpenAlex name the Massachusetts labs holding each half of a gap?"""
import requests, json, time

MAILTO = "dang2002991@gmail.com"
API = "https://api.openalex.org"
S = requests.Session()
S.headers.update({"User-Agent": f"researchbridge-probe (mailto:{MAILTO})"})


def get(path, **params):
    params["mailto"] = MAILTO
    for att in range(3):
        try:
            r = S.get(f"{API}/{path}", params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            print(f"   HTTP {r.status_code}: {r.text[:200]}")
            return None
        except Exception as e:
            print("   retry", att, type(e).__name__); time.sleep(2)
    return None


print("=" * 70)
print("TEST 1 — connectivity + is there a MeSH filter on works?")
print("=" * 70)
# Pancreatic Neoplasms = D010190 ; Breath Tests = D001942
for ui, label in [("D010190", "Pancreatic Neoplasms"), ("D001942", "Breath Tests")]:
    j = get("works", filter=f"mesh.descriptor_ui:{ui}", per_page=1)
    n = j["meta"]["count"] if j else "FAILED"
    print(f"  mesh.descriptor_ui:{ui}  ({label})  ->  {n} works")

print("\n  can we AND two MeSH terms?")
j = get("works", filter="mesh.descriptor_ui:D010190,mesh.descriptor_ui:D001942", per_page=1)
print("   both terms ->", j["meta"]["count"] if j else "FAILED", "works")

print("\n" + "=" * 70)
print("TEST 2 — group works by institution for one half of the gap")
print("=" * 70)
j = get("works", filter="mesh.descriptor_ui:D001942", group_by="institutions.id", per_page=200)
if not j:
    print("  FAILED")
    raise SystemExit
groups = j.get("group_by", [])
print(f"  institutions returned: {len(groups)}")
for g in groups[:5]:
    print(f"    {g['count']:>6}  {g['key_display_name']}")

print("\n" + "=" * 70)
print("TEST 3 — which of those are in Massachusetts?")
print("=" * 70)
ids = [g["key"].rsplit("/", 1)[-1] for g in groups if g["key"] != "unknown"]
counts = {g["key"].rsplit("/", 1)[-1]: g["count"] for g in groups}
ma = []
for i in range(0, min(len(ids), 200), 50):
    chunk = ids[i:i + 50]
    j = get("institutions", filter="ids.openalex:" + "|".join(chunk), per_page=50)
    if not j:
        continue
    for inst in j.get("results", []):
        geo = inst.get("geo") or {}
        if geo.get("region") == "Massachusetts":
            ma.append({"name": inst["display_name"], "city": geo.get("city"),
                       "ror": (inst.get("ror") or "").rsplit("/", 1)[-1],
                       "type": inst.get("type"),
                       "works_on_topic": counts.get(inst["id"].rsplit("/", 1)[-1], 0)})
    time.sleep(0.2)
ma.sort(key=lambda x: -x["works_on_topic"])
print(f"  Massachusetts institutions among top {len(ids)}: {len(ma)}")
for m in ma[:12]:
    print(f"    {m['works_on_topic']:>5} works | {m['name']} ({m['city']}) "
          f"| {m['type']} | ROR {m['ror']}")

print("\n" + "=" * 70)
print("TEST 4 — the real use case: MA labs on each half of the gap")
print("=" * 70)


def ma_labs(ui, label, topn=200):
    j = get("works", filter=f"mesh.descriptor_ui:{ui}", group_by="institutions.id", per_page=200)
    if not j:
        return []
    gs = [g for g in j.get("group_by", []) if g["key"] != "unknown"]
    cnt = {g["key"].rsplit("/", 1)[-1]: g["count"] for g in gs}
    out = []
    idl = list(cnt)[:topn]
    for i in range(0, len(idl), 50):
        jj = get("institutions", filter="ids.openalex:" + "|".join(idl[i:i + 50]), per_page=50)
        if not jj:
            continue
        for inst in jj.get("results", []):
            geo = inst.get("geo") or {}
            if geo.get("region") == "Massachusetts":
                out.append((cnt.get(inst["id"].rsplit("/", 1)[-1], 0),
                            inst["display_name"], geo.get("city")))
        time.sleep(0.2)
    out.sort(reverse=True)
    print(f"\n  [{label}] — {len(out)} MA institutions")
    for c, n, city in out[:6]:
        print(f"    {c:>5}  {n} ({city})")
    return out


ma_method = ma_labs("D001942", "METHOD half: Breath Tests")
ma_problem = ma_labs("D010190", "PROBLEM half: Pancreatic Neoplasms")

both = {n for _, n, _ in ma_method} & {n for _, n, _ in ma_problem}
print(f"\n  institutions holding BOTH halves already: {len(both)}")
if both:
    print("   ", ", ".join(sorted(both)[:6]))

json.dump({"method": ma_method, "problem": ma_problem},
          open("scout_openalex_result.json", "w"), indent=1)
print("\nwrote scout_openalex_result.json")
