# ResearchBridge

Check a disease–method pairing against PubMed, explore an early-detection map,
and export a reproducible literature brief for research discussion.

Hackachusetts 2026 · Track H4, Accelerating Biotechnology Innovation.

## Run

Tested with Python 3.12.14 on Windows. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-tested.txt
.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open [ResearchBridge](http://127.0.0.1:8000). On Windows, `run.cmd` starts the
same application and prefers `.venv`. On macOS/Linux, use `.venv/bin/python`.
The UI is the working application, and its saved examples are selectable inputs.
The default map now uses the verified **2026-10-30 retrieval**, promoted on
2026-11-02. There is one maintained UI: FastAPI with HTML/JavaScript.

`requirements-tested.txt` pins the tested main application and test environment.
`requirements.txt` lists direct dependency requirements for a fresh resolution.
For the commands below, use the virtual environment's Python when it is not activated.

Dependencies need Internet access to install. The committed map, Library and
saved examples run offline afterwards. New or refreshed PubMed checks require
Internet access. Optional `NCBI_API_KEY`, `CONTACT_EMAIL` and `OPENALEX_API_KEY`
settings belong in `.env` (copy the empty `.env.example`); process environment
variables take precedence. Keep `.env` private. No LLM API key is required.

## What works

- **Check:** choose a saved example or enter exact MeSH disease/method names.
  Check PubMed queries the overall pairing and the same pairing restricted to
  early detection. Refresh PubMed requests a new check. Saved results are labeled;
  failed refreshes show an explicit saved fallback when available.
- **Map:** browse 50 diseases × 32 methods. Empty corpus cells are checked against
  the broader PubMed query. A ringed candidate has at most two early-detection
  results in its saved count. Shortlists order by overall pairing counts.
- **Brief:** the selected pairing, both counts, source status, exact PubMed
  searches and limitations. Download Markdown or print/save PDF. Editing the
  query clears the previous selection until another check succeeds.
- **Library:** a separate 60-paper starter collection, with 56 official abstracts
  and 135 institutions. Search, save up to four papers, compare, check literal
  source text, and export CSV/HTML/PDF. TF-IDF/LSA scores measure text relevance.
- **Method:** corpus coverage, evidence limitations, the withdrawn historical
  performance claim and a clearly labeled scripted claim-check illustration.
  The illustration does not call a verification model.

A low count is a lead for specialist review, not proof of novelty, feasibility
or clinical effectiveness. Verified collaborator recommendations and a general
scientific claim-verification service remain future work.

## Current saved snapshot

| Item | Value |
|---|---:|
| Retrieval date | 2026-10-30 |
| Production papers, stored publication year 2005–2026 | **80,025** |
| Disease × method axes | **50 × 32** |
| Filled / empty cells | 1,066 / 534 |
| Pairings with confirmation counts | 534 |
| Low-result candidate pairings (≤2) | **425** |
| MeSH / abstract coverage | 100% / 86.24% |
| Strict ≤2018 / >2018 split | 43,353 / 36,672; no overlap |

The raw windows contain 44,156 and 36,684 unique PMIDs, with 803 shared PMIDs.
Their union has 80,037 records; 12 with stored publication year 2027 are excluded.
The sample audit independently re-fetched 60 different PMIDs and matched titles
and MeSH IDs. It did not inspect every record or abstract.

**Pairing-count timing:** 533 pairings reuse historical count caches; one missing
pairing was queried during the 2026-10-30 build. The 425 candidates are not a
claim that every pairing was re-queried on that date. The UI exposes this boundary.

The earlier **2× lift remains withdrawn**. The separate retrospective evaluation
uses training-only axes and 171 matched pairs; its results do not support restoring
that claim. It uses current MeSH assignments rather than an as-of-2018 index.
Validation remains `pending_remeasurement`. See [verification and limitations](docs/VERIFICATION.md).

## Verify

```powershell
python -m pytest tests -q -p no:cacheprovider -W error::DeprecationWarning
node --check static/gap.js
node --check static/bridge.js
node --test tests/frontend_bridge_state.test.cjs
```

The current suite covers the maintained application; Streamlit is no longer required.
For real localhost HTTP responses and 45 three-language export combinations,
start the app and run:

```powershell
python -m scripts.verify_live_http --base-url http://127.0.0.1:8000 --output output/http-verification
```

This checks responses, IDs, counts and exported contents. Native print preview,
390px layout and complete visual review require the manual checks in
[docs/VERIFICATION.md](docs/VERIFICATION.md#manual-browser-checks).

## Sources and rebuilding

Committed JSON and the Library SQLite database are enough to start the app.
Large raw corpus files and their manifests are local, ignored by Git and excluded
from the clean source ZIP. They are required to rebuild or audit the map.

Retrieve complete raw files when absent (network required):

```powershell
python -m gapfinder.fetch
```

Retrieval uses annual slices, reconciles all searched/fetched PMIDs and writes
`data/corpus_past_full.json` and `data/corpus_future_full.json`, each with a
SHA-256 completeness manifest. Add `--refresh` to replace a verified retrieval.
PubMed indexing changes, so a new retrieval may produce different totals.

Audit and build into a **fresh** output directory before replacing serving data:

```powershell
python -m scripts.audit_corpus --corpus-dir data --output-dir output/audit-new --spot-check --emit
python -m scripts.serve_snapshot --data-dir output/audit-new/serving --port 8001
```

The audit is offline unless `--spot-check` or `--emit` is supplied; `--audit-only`
suppresses both network stages. Emission uses saved pairing counts and queries
missing ones. Required failures stop publication. The isolated server changes
Map data; the Library and immediate Check cache retain their own sources.
After review, copy the generated serving JSON and matching caches/provenance into
`data/`, update `data/snapshot.json`, and restart the app. A rebuild does not
establish a predictive performance claim.

To run the separate retrospective evaluation with its frozen reference ontology:

```powershell
python -m scripts.evaluate_history --data-dir data --trees data/audit/history_mesh_trees.json --output output/history-evaluation.json
```

To rebuild only the Library database from committed seeds and source snapshots:

```powershell
python -c "from researchbridge.core import build_database; print(build_database())"
```

## Package

```powershell
python -m scripts.package_project
python -m scripts.package_corpus
```

`output/researchbridge-clean.zip` contains current code, docs, tests, saved map and
Library sources. It excludes credentials, virtual environments, generated output
and raw corpora. The separate `output/researchbridge-corpus.zip` preserves local
raw corpora and current audit evidence, with verified member hashes. Generated
ZIPs are local artifacts and are not pushed into Git history.

## Layout

```text
app.py                 FastAPI, UI and both API engines
static/                Current HTML/CSS/JavaScript UI
gapfinder/             PubMed retrieval, MeSH axes, grid, query confirmation
researchbridge/        Starter Library, SQLite, search, reports and exports
data/                  Current serving JSON, Library database and source snapshots
  snapshot.json        Current snapshot date, counts, hash and cache boundaries
  audit/               Current corpus audit and retrospective evaluation evidence
starter/               Extracted original CSV seeds and their retrieval scripts
scripts/               Audit, evaluation, isolated serving, HTTP checks and packaging
tests/                 Maintained Python and frontend state regression tests
docs/VERIFICATION.md   Verification scope, cleanup record and remaining limitations
```

Source bytes are preserved with `.gitattributes` because provenance hashes must
match across checkouts. Acknowledge Swanson & Smalheiser's Arrowsmith and prior
literature-based discovery work when presenting the prototype.
