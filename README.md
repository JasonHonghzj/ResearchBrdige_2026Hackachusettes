# ResearchBridge

Explore early-detection research, check disease–method pairings against PubMed,
and take a reproducible literature brief into a research discussion.

Hackachusetts 2026 · Track H4, Accelerating Biotechnology Innovation

## Run the demo

Use Python 3.12 or newer. From the repository root:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open [ResearchBridge](http://127.0.0.1:8000). On Windows, `run.cmd` runs the same
FastAPI app, preferring `.venv` when present and otherwise using `python` on PATH.
The app binds to localhost. No API key or corpus rebuild is required for the demo.

## What is implemented

- **Check:** enter exact MeSH disease and method names, or choose a saved example.
  New checks query PubMed; repeated checks can use a saved result. A fresh check
  displays its recorded timestamp. Unknown terms are rejected rather than called gaps.
- **Map:** saved counts over 79,940 deduplicated PubMed papers (2005–2026), with
  50 disease × 32 method axes. A shortlist shows the highest overall paper counts
  across distinct diseases. Ringed cells have ≤2 results in the saved full-PubMed
  early-detection search; that threshold does not establish scientific novelty.
- **Brief:** the exact selected pairing, counts, evidence source, reproducible
  PubMed searches and limitations. Download Markdown or print / save as PDF.
  Editing the inputs clears the previous checked selection until another check succeeds.
- **Library:** a separate 60-paper starter set, 56 official abstracts and 135
  institutions. Search, save up to four papers, compare, check literal source text,
  and export a discussion brief. These relevance scores are text similarity.
- **Method:** corpus coverage, the withdrawn historical lift, the negative result
  for bridge ranking, and a clearly labeled illustrative claim-check walkthrough.

The saved map, examples, briefs and Library work offline once the local server
is running. New or refreshed PubMed checks require Internet access. External PubMed
links also require a connection. No claim-checking model is called by the walkthrough.

**Future work:** verified Massachusetts collaborator matching, a general claim
verification gate, and corrected historical validation. The earlier 2× lift was
withdrawn. Paper counts indicate indexed use, not effectiveness or feasibility.

See [DEMO.md](DEMO.md) for the three-minute walkthrough and rehearsal checks.
The historical Streamlit interface is retained as `streamlit_app.py`; its older
notes in `README_RESEARCHBRIDGE.md` do not describe the primary demo UI.

## Verify

```powershell
python -m pytest tests --ignore=tests/test_app.py -q -p no:cacheprovider
node --check static/gap.js
node --check static/bridge.js
```

`tests/test_app.py` covers the retained Streamlit interface and additionally
requires `streamlit`. The FastAPI demo does not use Streamlit. Browser rehearsal
is necessary: API tests alone do not verify navigation, responsive layout or brief selection.

---

## Measured findings (2026-10-24)

These are real measurements against PubMed and OpenAlex, not estimates.

### Corpus — complete, 2005–2026
| | |
|---|---|
| Production corpus | **79,940 papers** (2005–2026, deduplicated) |
| Validation build / score | 43,353 (≤2018) / 36,587 (>2018), zero overlap |
| MeSH coverage | 100% |
| Abstract coverage | 83% pre-2018, 90% post |
| All-time results for the topic | 83,291 — so this is ~96% of the literature |

**esearch caps at 9,999 ids regardless of `retmax`.** A single `2005:2018` query
reports 44,156 results and returns 9,800 — 22%. Slicing per year (largest year is
5,758) and deduping by PMID recovers 44,156/44,156. Per-year counts sum to 50,078
because a record with a 2017 electronic and 2018 print date is returned for both
years — the same mechanism that leaked 801 post-2018 records into the range fetch.

The topic descriptors have birthdays: `Early Diagnosis` 2004, `Early Detection of
Cancer` 2009. Pre-2005 is 4% of all-time results and inconsistently back-indexed,
so 2005 is the natural floor.

### One fetch, two views
`load_production()` — every year, what the product uses, because a researcher
wants gaps that are open now. `load_corpus(window)` — the validation view, split
strictly at 2018 so the ranking cannot see the window it is scored against.

### A tree-lookup bug that silently crippled every axis
Batched `esummary db=mesh` fails for newer 9-digit descriptors: `D000069550`
(Machine Learning) maps to uid `68000069550`, answered with *"cannot get document
summary"*. **500 descriptors — 6% of the vocabulary and the most modern 6% —** had
empty tree lists and were dropped from all three axes and the bridge vocabulary:
Machine Learning (1,034 papers), COVID-19 (1,106), Deep Learning (711), Liquid
Biopsy (507), Cell-Free Nucleic Acids (327), Circulating Tumor DNA (304).
The rules were correct; the lookup was broken. `https://id.nlm.nih.gov/mesh/<UI>.json`
returns `treeNumber` directly — 500/500 recovered.

### Gap detection: the naive rules fail
Measured on the earlier 50 × 30 grid before the axis rules were tightened. The
failure modes are the durable finding here, not the counts.

| Ranking rule | Candidates from 1,500 cells | Top result |
|---|---|---|
| "busy method × busy problem, empty" | **673 of 673 holes** — no discrimination | Cervical Cancer × Early Diagnosis |
| + shared neighbours (naive Swanson) | 932 | Breast × Colonoscopy |
| + mechanistic bridges, IDF-weighted | **59** | Breast × Colonoscopy |

Root cause of the surviving junk: the method axis contained **organ-bound procedures**.
Colonoscopy and mammography are defined by the organ they examine, so they can never
transfer. Fix is a tree-prefix rule, not a blocklist:

- **keep** `E05.393` (molecular/genetic), `E05.196` (analytical chemistry — mass
  spec, Raman, NMR, chromatography), `L01.224.050` (artificial intelligence)
- **drop** `E01` (diagnostic procedures — mostly organ-bound)
- **drop** `E05.318` (statistics — Logistic Models, Odds Ratio, Area Under Curve)
- **watch** `E05.200` mirrors `E01`; a term can sit in several branches at once
  (`Vaginal Smears` is in both), so branch-letter filtering alone is not enough
- plain `L01` admits Internet, Telephone, Reminder Systems, Software;
  plain `G17` admits Odds Ratio. Both rejected.
- `METHOD_ALLOW` restores what the tree cannot reach: Metabolomics and Proteomics
  are `H01` disciplines; Liquid Biopsy and Breath Tests are `E01` but not
  organ-bound. `METHOD_DENY` drops therapeutics like `Genetic Therapy`.

Resulting axes on the full corpus: **50 problems × 30 methods**, now including
Machine Learning, Deep Learning, Liquid Biopsy, Proteomics, Metabolomics,
Biosensing, Raman and mass spectrometry.

### Time-sliced validation: 2× lift — ⚠️ STALE, MUST BE RE-MEASURED
**Do not pitch these numbers.** They were measured on the 9,800-paper (22%) corpus
with the old 14-term method axis. The corpus is now 4.5× larger and the axis has
30 terms including Machine Learning, Liquid Biopsy and mass spectrometry — none of
which existed on the axis when this ran. Phase 1 re-runs it; the figures below are
recorded only as the prior result and the shape of what to expect.

Grid built from papers ≤2018, scored against 2019–2026.

| Pile | Filled later |
|---|---|
| Flagged (≥2 mechanistic bridges), n=328 | **17%** |
| Popularity-matched control, n=328 | 9% |
| Unflagged empty cells, n=241 | 8% |

Lift **2.0×** vs unflagged, **1.8×** vs popularity-matched.

**Honest ceiling:** at a threshold of ≥3 holdout papers the signal disappears
(6 of 328; matched control equals it). So this ranks candidates ~2× better than chance.
It does **not** predict breakthroughs — do not claim that.

### OpenAlex: works, with traps
- **No MeSH filter** exists (225 filterable fields, none for MeSH) — map terms to search phrases
- `authorships.institutions.geo.region` filters **works, not institutions**. Grouping by
  institution then returns every co-author institution. A first attempt confidently listed
  University of Manchester, UCL and AstraZeneca (Sweden) as Massachusetts labs.
  **A second verification pass per institution is mandatory.**
- `pmid` OR-lists cap at 50 (100 silently returns 97)
- Parent universities (Harvard, MIT) swamp the useful units (MGH, Brigham, Dana-Farber, Broad)
- Two queries for two jobs: **MeSH for gap detection, OpenAlex topic search for collaborators.**
  Joining on corpus PMIDs gives counts of 1–3 and is useless for ranking.

Verified output for `pancreatic cancer early detection`, Massachusetts, 2015+:
MGH 58 · Brigham 37 · Beth Israel Deaconess 24 · Broad 13.

### Starter datasets: seeds only
- `starter/pubmed` — 60 rows, **not a topic set**. README: "Massachusetts affiliation,
  2024 publication date." Contents span autism policy, bilingual speech assessment,
  reading difficulties, dialysis timing, biosensing, a stiffness treadmill. No abstracts.
  No field to map.
- `starter/openalex` — 135 rows, **education institutions only**, so no MGH, Brigham,
  Dana-Farber or Broad — the four that are actually the answer. Carries noise
  (high schools, 0-work entries). The `works` column is useful for size normalisation.

Use both as seeds and as the demo's entry point. Fetch live. Say so openly.

---

## Layout

```text
app.py                  FastAPI app; /api/gap/* and /api/bridge/*
gapfinder/              PubMed fetch, MeSH axes, grid and query confirmation
researchbridge/         Starter-set retrieval, comparison, reports and exports
static/index.html       Responsive UI, no framework or build step
static/gap.js           Pairing selection, checks, map and novelty brief
static/bridge.js        Starter-set Library UI
data/                   Saved map / checks and Bridge database / snapshots
starter/                Original Hackachusetts datasets
streamlit_app.py        Retained earlier interface
probes/                 Exploratory measurement scripts
```

## Reproduce any number here
```bash
python -m gapfinder.fetch        # rebuild both corpora via year slicing
python -m gapfinder.mesh         # print the axes
python -m gapfinder.phrases      # phrase-map coverage
python -c "from gapfinder.fetch import spot_check; print(spot_check('past', 30))"
```

## Prior art to acknowledge
Swanson & Smalheiser's **Arrowsmith** has done literature-based discovery since the 1990s
(Swanson's fish-oil / Raynaud's result, 1986). What is new here is the measured lift,
per-claim code verification, and the handoff to named local labs.

## Caveat worth stating in the pitch
NLM moved from human to largely automated MeSH indexing around 2022. The holdout window
(2019–2026) straddles that change, so some "gap filled" signal could be an indexing shift.
