# Technical rules — each one earned by a failed experiment

Do not "simplify" any rule below. Every one replaced something that was tried
and produced wrong output. README.md records each measurement; the scripts that
produced them are in git history.

## Stack

Python 3.13 · `requests` · `xml.etree.ElementTree` · FastAPI + uvicorn ·
`rapidfuzz` · Altair only if a chart needs a library. Frontend is
`static/index.html` — hand-written, theme-aware, no build step, no npm.

**Do not add:** a vector database, React/Next.js, Docker, SQLite, pandas for the
grid (a `Counter` is simpler), or `sentence-transformers` on the critical path.

`sentence-transformers` DOES work but only from the venv at `C:\rs\.venv` —
a system install fails with `WinError 206` (torch's nested license directories
exceed Windows' 260-char path limit under the WindowsApps Python prefix). If used,
generate embeddings with that interpreter, write cosines to JSON, and let the main
app read the file. Never import it in app code.

## MeSH axis rules — `gapfinder/mesh.py`

```
problem axis   C*                               minus NONSPECIFIC_PROBLEM
method axis    E05.393, E05.196, L01.224.050    plus METHOD_ALLOW,
                                                minus E01/E05.200/E05.318, METHOD_DENY
bridge vocab   D*, G*                           rare only (≤3% of corpus), IDF-weighted
```

**Tree numbers need two sources.** Batched `esummary db=mesh` fails for newer
9-digit descriptors — `D000069550` (Machine Learning) maps to uid `68000069550`,
which answers *"cannot get document summary"*. That silently emptied the tree
list for **500 descriptors, 6% of the vocabulary and the most modern 6%**:
Machine Learning (1,034 papers), Deep Learning (711), Liquid Biopsy (507),
COVID-19 (1,106), Circulating Tumor DNA (304), Cell-Free Nucleic Acids (327).
All were dropped from every axis *and* from the bridge vocabulary, and the rules
were never at fault. `gapfinder.mesh._trees_from_rdf()` falls back to
`https://id.nlm.nih.gov/mesh/<UI>.json`, which returns `treeNumber` directly —
500/500 recovered. **Never remove that fallback.**

**And that endpoint returns a bare string, not a list, when a descriptor has
exactly one tree position.** Iterating it yields one "tree number" per character,
which corrupted 183 descriptors. Normalise `str` to `[str]` and validate the
shape. Both bugs were invisible: an empty list just classifies as nothing, and a
stray `'D'` character still satisfies `is_mechanistic()`.

`gapfinder.mesh.audit_trees()` now runs after every resolution and reports empty or
malformed entries. **Silence is the failure mode here, not exceptions** — call the
audit, do not assume a successful fetch means correct data.

Why each exclusion exists:

- **`E01` (diagnostic procedures)** — organ-bound. Colonoscopy and mammography are
  defined by the organ they examine, so they can never transfer. Including them
  made "Breast Neoplasms × Colonoscopy" the top-ranked gap three times.
- **`E05.318` (statistics)** — `Logistic Models`, `Odds Ratio`, `Area Under Curve`
  are not methods anyone applies to a disease.
- **`E05.200`** mirrors `E01`. A descriptor can occupy several tree positions at
  once (`Vaginal Smears` is in both `E01.370` and `E05.200`), and `is_method`
  matches if ANY position matches — so a broad prefix drags in everything
  cross-listed under it.
- **plain `L01`** was tried and rejected: it also admits `Internet`, `Telephone`,
  `Reminder Systems`, `Software`, `Databases, Factual`, `Communication Barriers`.
  Only `L01.224.050` (Artificial Intelligence) belongs.
- **plain `G17`** is unsafe: it holds `Odds Ratio` at `G17.680.500`.
- **`E05.196` (analytical chemistry) IS included** — mass spectrometry, tandem MS,
  MALDI, Raman, NMR, chromatography, surface plasmon resonance. Platform-level,
  organ-independent, and the branch most modern early-detection work lives in.
  Omitting it cost 9 of the 30 method terms.
- **`METHOD_ALLOW`** restores transferable methods the tree cannot reach:
  Metabolomics and Proteomics sit in `H01` as disciplines; Liquid Biopsy and
  Breath Tests sit in the wholesale-excluded `E01` but are not organ-bound.
- **`METHOD_DENY`** drops therapeutics that match a method prefix —
  `Genetic Therapy` is `E05.393.420.301` and is not a detection method.
- **`NONSPECIFIC_PROBLEM`** — tree-C terms that are disease *states*
  (`Recurrence`, `Disease Progression`, `Neoplasm Invasiveness`, `Critical Illness`)
  or organ-less histology (`Carcinoma`, `Adenocarcinoma`). "Recurrence × PCR" is
  not a research gap.

Current axes on the full 79,940-paper corpus: **50 problems × 30 methods**.

## Gap ranking

Rank by **mechanistic bridges**, never by popularity. Measured failures:

| rule | candidates from 1,500 cells | top result |
|---|---|---|
| "busy × busy, empty" | 673 of 673 holes — no discrimination at all | Cervical Cancer × Early Diagnosis |
| + shared neighbours (naive) | 932 — bridges came back `Humans, Female, Male` | Breast × Colonoscopy |
| + mechanistic bridges, IDF | 59 | Breast × Colonoscopy (fixed by the axis rules above) |

Also skip any pair whose shallow MeSH subtrees intersect — sibling terms like
`Early Diagnosis` / `Early Detection of Cancer` are assigned interchangeably by
indexers, so zero co-occurrence is an indexing convention, not a gap.

## Two grids — serving vs validation. Never conflate them.

`build_grid(corpus_slice)` takes a corpus dict so the identical function builds both.
What differs is the slice it is fed, and the two slices answer two different questions.

- **Serving grid — the FULL corpus through the present (≤2026).** This is the grid the
  user and the brief see. A cell is a gap only if it has zero co-occurring papers
  across the *entire* corpus. It must be built on everything known today, or the tool
  commits its worst error: telling a grant applicant "no prior work" when a 2020 or
  2024 paper already filled the cell. Freezing time is a property of the experiment,
  **never** of the product.
- **Validation grid — train ≤ cutoff, score after.** Used ONLY to produce the lift
  number in `validation.json`. It is never used to answer a user's question or decide
  what the brief calls a gap.

Why the validation cutoff is **2018** and not later, on the current corpus — measured
per-year counts expose a hole: 2020–2023 return ~31 papers total, not a real lull but
each fetch window (`2005:2018`, `2019:2026`) hitting the ~10k cap and truncating the
middle. So 2018 is the only split with a dense 2024–2026 holdout to score against; a
2022 cutoff would score against near-nothing and the lift would be meaningless. Moving
the cutoff forward REQUIRES fixing corpus completeness first.

Corpus completeness is a prerequisite for the serving grid regardless of validation.
Use `gapfinder.fetch.fetch_years()` — it slices the span into per-year queries (each well
under the 10k cap) and dedupes by PMID, recovering the truncated middle years. A
single range query returns ~22% of a large result set; per-year retrieval gets the
whole span.

Freshness: even the full corpus is a snapshot. The brief states its corpus date window
and the `provenance.json` timestamp, so "no prior work" always means "none in PubMed as
of \<date\>, within this query" — never an absolute, unbounded claim.

## PubMed — `gapfinder/fetch.py`

- Parse with ElementTree, not regex. Abstracts arrive as several labelled
  `<AbstractText>` sections; regex concatenates them wrongly or misses them.
- Read the year from `Journal/JournalIssue/PubDate` **only**. A loose search put
  801 post-2018 records inside a `2005:2018` fetch.
- Always apply a **strict year post-filter** after the window query. Print and
  electronic dates disagree and leak across the boundary.
- **esearch returns at most 9,999 ids regardless of `retmax`**, and efetch over
  history stops at the same point. A single `2005:2018` query reports 44,156
  results and yields 9,800 — 22%. Use `fetch_years()`, which slices per year
  (largest single year is 5,758) and dedupes by PMID: 44,156/44,156 recovered.
- Per-year counts sum to 50,078 against the range query's 44,156 because a record
  with a 2017 electronic and 2018 print date is returned for both years. Same
  mechanism as the 801-record leak. Dedupe by PMID makes it harmless.
- The topic descriptors have birthdays: `Early Diagnosis` 2004, `Early Detection
  of Cancer` 2009. Pre-2005 is 4% of all-time results and inconsistently
  back-indexed, so **2005 is the natural floor**, not an arbitrary one.
- 3 req/s without an API key, 10 with one. `NCBI_API_KEY` goes in `.env`
  (gitignored) — **never** in `.env.example`, which is tracked.
- Data is UTF-8. The Windows console is cp1252 and will crash printing `≥`; set
  `PYTHONIOENCODING=utf-8` or `sys.stdout.reconfigure(encoding="utf-8")`.

## OpenAlex — collaborator lookup

- **No MeSH filter exists** (225 filterable fields, none for MeSH). Map grid
  terms to search phrases via `data/phrases.json`.
- `authorships.institutions.geo.region` filters **works, not institutions**.
  Grouping by institution afterwards returns every co-author institution
  worldwide. A first attempt listed University of Manchester, UCL and
  AstraZeneca (Sweden) as Massachusetts labs. **The per-institution region
  verification pass is mandatory — never remove it.**
- `pmid` OR-lists cap at **50** (100 silently returns 97).
- Filter out parent universities (`type == "education"` with no lineage) —
  "Harvard University" swamps the useful units (MGH, Brigham, Dana-Farber, Broad).
- **Two queries for two jobs:** MeSH for gap detection, OpenAlex topic search for
  collaborators. Joining on corpus PMIDs yields counts of 1–3 and is useless.
- Always send `mailto` for the polite pool.

## Claim verification — `gapfinder/verify.py`

The model must return the **supporting sentence verbatim**; code decides:

1. `rapidfuzz` confirms the sentence really appears in the abstract
2. every numeral in the claim must appear in the source
3. fail either gate → the claim is deleted

Never ask a model "is this supported?" — that answer cannot be audited, and
auditability is the product's entire selling point. Do not replace the string
gate with embedding similarity; a cosine threshold is unfalsifiable.

LLM usage is minimal and optional: drafting demo claims. Keep it behind a thin
provider interface with precomputed JSON as the default, so the app runs with no
API key at all.

## Demo architecture

Precompute the grid, gaps and validation to JSON and commit them. A cache hit is
the **same code path** as a cold run with step one already done — nothing is
faked, and a new query goes down the live path automatically.

Live on stage: claim verification and the OpenAlex lab lookup (fast, and the best
material). Warm from cache: corpus fetch and grid build (~90s, and boring).
Ship a hardcoded fallback for each live call. Never present cached data as live —
show the retrieval log instead.

## Provenance — non-negotiable for an evidence tool

- `data/provenance.json` is an append-only retrieval log: source, endpoints, exact
  query, date window, available total, retrieved count, coverage, UTC timestamp,
  and a reproducible URL. `gapfinder.fetch._record_provenance()` writes it on every
  fetch. Step 01's retrieval log in the UI must read from this, not hardcoded text.
- **Never read `data/corpus_*.json` directly.** One fetch, two views:
  `load_production()` is every year 2005–2026 (79,940 papers) and is what the
  PRODUCT uses — a researcher wants gaps open now, so nothing is held back.
  `load_corpus(window)` is the VALIDATION view, split strictly at 2018
  (43,353 build / 36,587 score, zero overlap). Both apply the year filter on
  every read, because the raw files contain records from the wrong side.
- `gapfinder.fetch.spot_check(window, n)` re-fetches n random records live and compares
  titles and MeSH UIs against the local cache. 30/30 matched on 2026-10-24.
  Re-run before the demo; it is the answer to "how do we know your data is real".
- Every paper is citable at `https://pubmed.ncbi.nlm.nih.gov/<pmid>/`. Show the
  PMID with every quote in the brief.
