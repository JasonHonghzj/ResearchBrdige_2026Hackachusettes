# Technical integrity rules

Maintained 2026-11-02. Tested setup: Python 3.12.14, FastAPI, Starlette, httpx2,
requests, ElementTree, NumPy/scikit-learn for Library search, ReportLab/pypdf for
exports. Dependency pins are in requirements-tested.txt. No frontend build step.

## Engine boundaries

Keep the gapfinder grid in Counter/dict operations. The separate Library uses
SQLite and TF-IDF/LSA. No neural runtime, vector database, React or Docker is needed.
Frontend requests and exports must retain the exact displayed selection/IDs/language;
late responses cannot overwrite a newer request. Distinguish total_count/shown_count.

## MeSH and retrieval

Preserve the NLM RDF tree fallback for modern descriptors. Normalize string tree
values into lists and audit empty/malformed tree entries. Diseases use C* minus
nonspecific states; methods use E05.393/E05.196/L01.224.050 with the explicit
allow/deny rules. Do not broaden to organ-bound E01 or statistical E05.318 methods.
Rare D*/G* mechanistic bridges are experimental, not validated predictors.

Retrieve annual PubMed slices, reconcile every searched/fetched PMID, and require
matching complete manifests and hashes before cache reuse. Keep append-only source
provenance; never replace a corrupt log silently. load_production() merges raw windows,
deduplicates by PMID and applies stored publication year 2005–2026. load_corpus()
splits that same population, avoiding date-boundary overlap or lost years.

## Current source and output contracts

The default 2026-10-30 snapshot has 80,025 papers, 50×32 axes, 534 checked empty cells,
425 low-result candidates. The 43,353/36,672 strict split has no overlap. data/snapshot.json
exposes dates, counts and cache scope. 533 pairing counts were reused, one newly queried.
A historical saved count without a timestamp is not a fresh check. Spot checks compare
sampled titles/MeSH IDs and retain source hashes, PMID membership and timestamps;
they do not establish full abstract correctness.

Use isolated audit/emit output before promoting a new snapshot. grid without --emit
only inspects. --emit writes grid/gaps/confirmed/validation, confirms all empty cells,
and stops before publishing on required failures. Update matching caches/provenance
and snapshot metadata; restart the app to reload cached confirmed rows.

The 2× claim remains withdrawn and serving validation pending. Keep dated historical
negative evidence separate from the current training-only matched retrospective
analysis. Do not restore claims from a co-occurrence rerun. Refer to the README and
docs/VERIFICATION.md rather than discarded historical plans.

## Sources and packaging

Keep source bytes stable across Git checkouts. Paper quotes retain PMIDs. Official
Library source snapshots and extracted seed CSVs support offline rebuilds. Current
code and small audit evidence belong in Git; raw corpora, generated archives,
credentials, virtual environments and temporary review runtimes do not. .env loading
must preserve values already supplied by the process environment.
