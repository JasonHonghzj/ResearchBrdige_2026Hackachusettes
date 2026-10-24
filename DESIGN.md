# ResearchBridge — Design

Hackachusetts 2026 · Track H4, Accelerating Biotechnology Innovation
Status: design for the 8-hour build. Reflects the rules in `.kiro/steering/` and
the finished modules (`gapfinder/fetch.py`, `gapfinder/mesh.py`, `gapfinder/phrases.py`).

---

## 1. One-paragraph summary

ResearchBridge maps a research field as a grid of **diseases × lab methods**, finds the
combinations no paper has tried, ranks them by whether the two literatures share
underlying biology, and produces a **one-page brief**: a defensible novelty statement,
evidence with every claim checked against its source abstract, and the Massachusetts
labs holding each half of the idea. The brief is the deliverable; the web app is how
the brief gets made.

The design principle that governs every decision below: **anything a judge must trust
is produced by code, not by a model.** The LLM is confined to a single, optional,
fully-gated role. Everything load-bearing is deterministic and reproducible.

---

## 2. Component architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  static/index.html   (hand-written, theme-aware, no framework/build)   │
│  heatmap · gap panel · claim strikethrough · validation chart · brief  │
└───────────────┬────────────────────────────────────────────────────────┘
                │ fetch() JSON
┌───────────────▼────────────────────────────────────────────────────────┐
│  app.py  — FastAPI + uvicorn                                            │
│  GET /api/corpus      precomputed                                       │
│  GET /api/grid        precomputed                                       │
│  GET /api/gap/{id}    precomputed                                       │
│  GET /api/validation  precomputed                                       │
│  POST /api/verify     LIVE  (deterministic code gate)                   │
│  GET /api/labs?topic= LIVE  (OpenAlex, region-verified)                 │
└───────┬───────────────────────────────┬────────────────────────────────┘
        │                               │
┌───────▼──────────┐          ┌─────────▼───────────────────────────────┐
│ gapfinder/       │          │ external services                        │
│                  │          │                                          │
│ fetch.py   DONE  │◄────────►│ NCBI E-utilities (PubMed)                │
│ mesh.py    DONE  │          │   esearch / efetch / esummary(mesh)      │
│ phrases.py DONE  │          │                                          │
│ grid.py    P1    │          │ OpenAlex  /works, /institutions          │
│ labs.py    P1    │◄────────►│                                          │
│ verify.py  P3    │          │                                          │
│ brief.py   P4    │          │ no LLM provider — see 4.2                 │
└───────┬──────────┘          └──────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────────────────────┐
│ data/  — caches + committed precomputed JSON                           │
│ corpus_{past,future}.json  grid.json  gaps.json  validation.json       │
│ phrases.json  mesh_trees.json  provenance.json  confirmed.json  │
└────────────────────────────────────────────────────────────────────────┘
```

**Hard constraints (from steering, each earned by a failed experiment):**
- No vector DB, no React/Next, no Docker, no SQLite, no pandas for the grid, no
  `sentence-transformers` on the critical path. A `Counter` is simpler than pandas here.
- Do not rewrite the frontend or add a framework. The design is done; only the data
  source changes (hardcoded `const` arrays → `fetch()`).
- Secrets in `.env` only. `.env.example` stays empty and tracked.
- Every network call is cached to `data/`, keyed by query. **A cache hit is the same
  code path as a cold run** — nothing is faked.

---

## 3. End-to-end data flow

### 3.1 Corpus (precomputed, warmed from cache)

```
PubMed query:  ("Early Detection of Cancer"[MeSH] OR "Early Diagnosis"[MeSH])
   │
   ├─ fetch_window("2005:2018")  → corpus_past.json    (~19 MB, 8,999 papers ≤2018)
   └─ fetch_window("2019:2026")  → corpus_future.json  (~23 MB)
   │
   │  ElementTree parse (not regex): title, journal, year, MeSH UIs, abstract
   │  year read ONLY from Journal/JournalIssue/PubDate (loose search leaked 802 recs)
   │  provenance.json written on every fetch (append-only retrieval log)
   ▼
load_corpus(window)  ← ALWAYS use this, never read corpus_*.json directly.
   Applies the strict year post-filter that removes the 801 date-leaked records
   that PubMed's [dp] filter bleeds across the 2018 boundary.
```

### 3.2 Axes (deterministic, rule-based)

```
build_axes(corpus)  in mesh.py
   │
   ├─ resolve_trees(): descriptor UI D015415 → mesh uid 68015415 → tree numbers
   │                   (cached in mesh_trees.json; only unknown UIs hit network)
   ├─ problem axis:  tree C*          minus GENERIC, minus NONSPECIFIC_PROBLEM
   ├─ method axis:   E05.393 + L01.224.050   minus E01, E05.200, E05.318
   │                 (organ-bound procedures and statistics can never "transfer")
   ▼
   50 problems × 14 methods   (verified: Breast/Colorectal/Cervical Neoplasms ×
                               PCR / Gene Expression Profiling / HT Sequencing …)
```

Why the exclusions exist is documented in `mesh.py` and `tech.md`; do not simplify
them. E01 made "Breast Neoplasms × Colonoscopy" the top gap three times.

### 3.3 Grid + gap ranking (Phase 1 — `gapfinder/grid.py`)

**Two grids, built by the same code on different corpus slices. Do not confuse them.**

| grid | corpus slice | purpose | who sees it |
|---|---|---|---|
| **serving grid** | **ALL papers ≤ now (2026)** | answer "has anyone tried X×Y?" | the user / the brief |
| **validation grid** | train ≤ cutoff, score after | measure if flagged gaps fill later | the 2× chart only |

The serving grid is the one that must be correct *today*. A cell is a gap only if it
has **zero co-occurring papers across the entire 2005–2026 corpus**. The validation
grid is a historical re-enactment used solely to produce the lift number; it is never
used to tell a user something is unexplored.

```
for each (problem, method) cell:
   co-occurrence = |papers(problem) ∩ papers(method)|      # over the grid's own slice
   if co-occurrence > 0:             cell is filled, skip
   if shallow MeSH subtrees intersect: skip   (siblings = indexing convention, not a gap)
   else:
       bridges = mechanistic D*/G* terms (rare, ≤3% of corpus) that co-occur
                 ≥2× with BOTH the problem and the method
       score   = Σ IDF(bridge)       ← rank by shared biology, NEVER by popularity
       flag if ≥2 shared mechanistic bridges
   ▼
grid.json      serving grid: counts per cell over the FULL corpus, flagged cells marked
gaps.json      flagged candidates with bridges, scores, both-axis frequencies
```

`build_grid(corpus_slice)` takes a corpus dict so the identical function builds both
the serving grid (full corpus) and each validation train grid (≤cutoff). Same code
path — the serving answer and the validation re-enactment can never diverge in logic.

Ranking rule history (why bridges, not popularity):

| rule | candidates from 1,500 cells | top result |
|---|---|---|
| busy × busy, empty | 673 of 673 — no discrimination | Cervical Cancer × Early Diagnosis |
| + naive shared neighbours | 932 — bridges were `Humans, Female, Male` | Breast × Colonoscopy |
| + mechanistic bridges, IDF | 59 | Breast × Colonoscopy (fixed by axis rules) |

### 3.4 Validation (Phase 1 — `validation.json`)

**The concern this section answers.** Validation needs a time split — you cannot
measure "do flagged gaps get filled later" without holding out the later years. But
the split is ONLY for measuring. The grid the user sees is built on the full corpus
through 2026 (§3.3), so we never tell a researcher a cell is empty when a 2020 or 2024
paper already filled it. Freezing time is a property of the *experiment*, not of the
*product*.

#### Why the cutoff stays at 2018 (data-driven, not arbitrary)

Measured per-year counts in the current corpus:

```
2016  394   2019  771    2024   621
2017 3725   2020   23    2025  4984
2018 4880   2021    5    2026  4183
            2022    0
            2023    3
```

The 2020–2023 years are nearly empty — not a real research lull, but an artifact of
the two fetch windows (`2005:2018`, `2019:2026`) each hitting PubMed's ~10k-per-query
cap and truncating the middle. Consequences:

- **Cutoff 2018** gives a clean split: 8,999 train papers, and a dense 2024–2026 block
  (~9,800 papers) to score "filled later" against. This is the only split the current
  corpus supports honestly.
- **Cutoff 2020 or 2022** is NOT viable yet: the holdout would be almost empty
  (2020–2023 ≈ 31 papers), so "gap filled" would look falsely near-zero and the lift
  would be meaningless. Moving the cutoff forward REQUIRES fixing corpus completeness
  first (next subsection).

So 2018 is kept for validation deliberately, with the reasoning shown, not hidden.

#### Corpus completeness fix (prerequisite for any later cutoff)

`gapfinder.fetch.fetch_years()` already exists for exactly this: it slices the span into
per-year queries (each well under the 10k cap) and dedupes by PMID, recovering the
truncated middle years. Running it rebuilds a complete 2005–2026 corpus. This feeds
the **serving grid** regardless of validation, because the serving grid must be
complete to be correct. If time permits before the freeze, a complete corpus also
unlocks a forward cutoff (e.g. train ≤2022, score 2023–2026) as a robustness check.

#### Serving-grid freshness note (visible in the brief)

Even the full corpus is a snapshot. The brief states its corpus date window and the
`provenance.json` timestamp, so "no prior work" always means "none in PubMed as of
<date>, within this query" — never an absolute, unbounded claim.

#### Current validation result (re-measure before quoting)

Time-sliced on the 2018 cutoff:

| pile | filled later |
|---|---|
| flagged (≥2 bridges), n=328 | 17% |
| popularity-matched control, n=328 | 9% |
| unflagged empty cells, n=241 | 8% |

Lift ≈ 2× vs unflagged. **Re-measure on the current 50×14 axes before quoting a
number** — the 2.0× came from a dirtier grid. Honest ceiling, shown in the UI: at
≥3 holdout papers the signal vanishes (6 of 328; matched control equals it). We rank
candidates ~2× better than chance; we do **not** predict breakthroughs.

#### What "we get it wrong" looks like, and how each is handled

| the worry | handling |
|---|---|
| user told "gap" but a 2020/2024 paper filled it | serving grid uses the FULL corpus, so the cell is already marked filled |
| corpus missing the middle years hides a real paper | `fetch_years()` rebuilds a complete, deduped span before serving |
| "no prior work" sounds absolute | brief shows the query + corpus date window + provenance timestamp |
| flagged gap never gets filled | expected — we rank candidates ~2×, we do NOT predict; the reject pile is shown |

### 3.5 Labs (Phase 1/4 — `labs.py`, not built)

```
grid term → search phrase (phrases.json; OpenAlex has NO MeSH filter)
   │
   ├─ /works  filter=title_and_abstract.search:<phrase>,
   │          authorships.institutions.geo.region:Massachusetts,
   │          publication_year:2015-   group_by institutions.id
   │
   ├─ MANDATORY per-institution region verification pass (/institutions):
   │    the region filter matches WORKS not institutions, so grouping returns
   │    every co-author institution worldwide. A first attempt listed Manchester,
   │    UCL and AstraZeneca (Sweden) as "Massachusetts labs." Never remove this pass.
   │
   ├─ drop parent universities (type=education, no lineage) — Harvard/MIT swamp
   │    the useful units (MGH, Brigham, Dana-Farber, Broad)
   ▼
   who holds the METHOD only · who holds the PROBLEM only · who holds BOTH
```

### 3.6 Brief (Phase 4 — `brief.py`)

Assembles the one-pager from the above: novelty statement, verified evidence with
PMIDs, the MA lab handoff, and the required caveats. Exportable to PDF via a print
stylesheet (no new dependency). **The brief is the deliverable.**

---

## 4. Where ML / the LLM sits (and where it does not)

This is the most important section. Read it before writing `verify.py`.

### 4.1 The load-bearing path has NO LLM and NO neural model

| step | technique | why not ML |
|---|---|---|
| corpus retrieval | PubMed API + ElementTree | deterministic, reproducible |
| axis construction | MeSH tree-number rules | auditable, each rule earned by a failure |
| gap detection | set intersection (co-occurrence) | a fact, not a prediction |
| gap ranking | IDF-weighted mechanistic bridges | explainable; bridges are shown |
| claim verification | `rapidfuzz` string match + numeral check | **must be auditable** |
| lab lookup | OpenAlex API + region verification | deterministic |

None of these can hallucinate. A gap either has zero co-occurring papers or it does
not. A bridge term either appears in both literatures or it does not. A claim's
sentence either appears in the abstract or it does not.

### 4.2 The ONE place the LLM is allowed: drafting candidate claims

The LLM's only job is **wording** — turning verified evidence into readable prose for
the brief's claim sentences. It proposes; code disposes. Specifically:

- Input to the LLM: a gap and the abstracts of its supporting papers.
- Output from the LLM: for each claim, (a) the claim text, and (b) **the single
  supporting sentence copied verbatim from the abstract.**
- The LLM never decides whether a claim is true. It never scores novelty. It never
  ranks gaps. It never touches the validation numbers.

**As shipped there is no LLM at all.** No provider is wired, no API key is read, and
`requirements.txt` carries no model client. The brief is composed from the gap data
and the two PubMed counts; the claim walkthrough in Method uses claims fixed in the
page. That is the stronger position anyway — every number on screen comes from a
query a reviewer can re-run, and nothing on the critical path can fabricate text.

If live drafting is added later it belongs behind a thin provider interface whose
default reads JSON, so the app keeps running with no key.

### 4.3 Optional, OFF the critical path: embeddings and a learned ranker

Only if Phase 1 finishes early (it probably won't):
- **Semantic bridges** via `sentence-transformers` — one additive feature computed
  offline, cosines written to JSON, read by the app. Dropped gracefully if the file
  is absent. Never imported in app code (WinError 206 path-length issue; only runs
  from the `C:\rs\.venv` interpreter).
- **Learned gap ranker** — logistic regression (NOT gradient boosting; only ~55
  positive labels) over features like `n_shared_bridges`, `idf_sum`, `max_idf`,
  `neighbor_jaccard`, and the best candidate `sibling_cells_filled`. Labels already
  exist in `data/confirmed.json`. This is a stretch extension, not core.

Both are explainable or droppable. Neither is allowed to become load-bearing before
the 6.5-hour freeze.

---

## 5. The claim verification gate — what happens when the LLM is wrong

This is the product's entire selling point, so it gets its own section. The design
assumes the LLM **will** hallucinate and is built to make that harmless.

### 5.1 The four-step gate (`verify.py`)

For every claim the LLM drafts, with its quoted supporting sentence:

```
1. rapidfuzz confirms the quoted sentence ACTUALLY appears in the source abstract
   (fuzzy match tolerates whitespace/markup noise, not fabrication)
      └─ fail → the sentence was invented → DELETE the claim
2. every numeral in the claim text must also appear in the source abstract
      └─ fail → a number was invented or altered → DELETE the claim
3. both gates pass → the claim is kept, shown WITH its PMID and the quoted sentence
4. the UI renders the pass/fail live: kept claims stand, failed claims get a visible
   STRIKETHROUGH so the audience watches fabrication being removed
```

The rule, verbatim from `tech.md`: *the model must return the supporting sentence
verbatim; code decides. Never ask a model "is this supported?" — that answer cannot
be audited, and auditability is the product's entire selling point.*

### 5.2 Failure modes and how each is contained

| LLM failure | what the gate does | user-visible result |
|---|---|---|
| invents a sentence not in the abstract | step 1 fuzzy match fails | claim struck through, deleted |
| paraphrases so heavily it no longer matches | step 1 fails | claim deleted (we accept false-negatives over false-positives) |
| fabricates or changes a number (e.g. "detects 94%") | step 2 numeral check fails | claim deleted |
| cites the wrong PMID | sentence won't be found in that abstract → step 1 fails | claim deleted |
| drafts a vague but harmless claim | passes gates, but adds no evidence | kept; weak claims are visible, not dangerous |
| LLM unavailable / no API key | provider falls back to precomputed JSON | app runs identically |

Design bias: the gate prefers **deleting a true claim over keeping a false one.** A
missed real claim costs us a line of evidence; a kept false claim destroys the tool's
credibility. For an evidence tool that trade is correct.

### 5.3 What we deliberately do NOT do

- We do not ask the model to self-assess ("is this supported? score 0–1"). Unauditable.
- We do not replace the string gate with embedding cosine similarity. A cosine
  threshold is unfalsifiable — you can't point a judge at *why* it passed.
- We do not let the LLM rank, score novelty, or decide which gaps are real.

### 5.4 Residual risks we disclose rather than hide

These are honest limitations kept visible in the UI/pitch (per `product.md`):
- An empty cell is not proof of a research gap on its own. We rank candidates and
  **show the reject pile**; we do not assert that absence is meaningful.
- NLM moved from human to largely automated MeSH indexing ~2022; the 2019–2026
  holdout straddles that, so some "gap filled" signal could be an indexing shift.
- Pre-2018 abstract coverage is 86%, so ~1,200 papers cannot be quoted as evidence.
- The gate verifies that a quote is real and faithful to the abstract. It does **not**
  verify that the underlying science is correct — that is the researcher's job. The
  tool proves provenance, not truth of the finding.

---

## 6. Provenance — why the data is trustworthy

An evidence tool must prove its inputs are real.
- `data/provenance.json` is an append-only log written by `_record_provenance()` on
  every fetch: source, endpoints, exact query, date window, available total, retrieved
  count, coverage, UTC timestamp, and a reproducible URL. The UI's "retrieval log"
  reads from this, not from hardcoded text.
- `gapfinder.fetch.spot_check(window, n)` re-fetches n random records live and compares
  titles and MeSH UIs against the cache (30/30 matched on 2026-10-24). Re-run before
  the demo — it is the answer to "how do we know your data is real."
- Every paper is citable at `https://pubmed.ncbi.nlm.nih.gov/<pmid>/`; the PMID shows
  with every quote in the brief.

---

## 7. Demo architecture (live vs warm)

- **Precompute and commit** grid/gaps/validation to JSON. Warm from cache the slow,
  boring parts (corpus fetch + grid build, ~90 s).
- **Live on stage:** claim verification and the OpenAlex lab lookup — fast and the best
  material. Each live call ships a hardcoded fallback for network failure.
- Never present cached data as live; show the retrieval log instead.

Demo priority order (strongest first):
1. Claim verification with the visible strikethrough — deterministic, 100% reliable.
2. The field map with ringed flagged cells.
3. The 2× validation chart, with both controls and the ceiling caveat shown.
4. The brief with the MA labs.

---

## 8. Build order and freeze

| phase | hrs | who | output |
|---|---|---|---|
| 0 | 0–0.3 | both | env smoke-check, lock JSON contracts |
| 1 | 0–3 | A | `grid.py` (serving grid on FULL corpus + validation grid on cutoff), `labs.py`; emit grid/gaps/validation.json; re-measure lift |
| 1a | within P1 | A | run `fetch_years()` to rebuild a complete 2005–2026 corpus so the serving grid is correct (recovers truncated 2020–2023) |
| 2 | 0–3 | B | `app.py` + rewire frontend (work against mockup data from minute 1) |
| 3 | 3–5 | both | `verify.py` — the four-step gate (best demo moment) |
| 4 | 5–6.5 | both | `brief.py`, live labs with "holds both" category, caching + fallbacks |
| — | 6.5 | — | **hard code freeze, non-negotiable** |
| 5 | 6.5–8 | both | three timed rehearsals, no new features |

Cut order if time runs short: learned ranker → semantic bridges → live labs (fall back
to precomputed MGH 58 · Brigham 37 · BIDMC 24 · Broad 13). Never cut claim verification
or the field map.

---

## 9. Claims matrix — what we will and will not say

| claim | allowed? | basis |
|---|---|---|
| "no prior work applies method X to disease Y, as of <date>" | ✅ | serving grid over FULL corpus ≤2026, zero co-occurrence, provenance shown |
| "no prior work" as an absolute, timeless claim | ❌ | always scoped to the query + corpus date window |
| "every claim is verified against its source" | ✅ | the code gate, demonstrated live |
| "flagged gaps fill ~2× more often than controls" | ✅ (re-measured) | time-sliced validation, both controls shown |
| "finds breakthroughs" / "predicts discoveries" | ❌ | signal vanishes at ≥3 holdout papers |
| "would have found a real gap years early" | ❌ | not demonstrated |
| "the method itself is novel" | ❌ | Arrowsmith did LBD since the 1990s — acknowledged |
| "the starter CSVs are the corpus" | ❌ | 60/135 unrelated rows, no field to map |

Novelty we DO claim: the measured lift, **code-level claim verification**, and the
handoff to named local labs. Acknowledge Arrowsmith up front — it preempts the one
question a knowledgeable judge will ask.
