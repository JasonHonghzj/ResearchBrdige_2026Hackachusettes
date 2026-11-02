# Maintained repository structure

Maintained 2026-11-02. See README.md for runnable commands.

- app.py: FastAPI main UI, /api/gap/*, /api/bridge/*, /api/docs.
- static/: current HTML/CSS/JavaScript UI; no build step.
- gapfinder/: annual retrieval, MeSH trees/axes, phrase utility, grid and confirmation.
- researchbridge/: separate Library, SQLite, official snapshots, reports and exports.
- data/: current serving JSON, snapshot metadata, Library sources and audit evidence.
- data/audit/: source audit, frozen retrospective ontology and current evaluations.
- starter/: extracted CSV seeds and source retrieval scripts.
- scripts/: source audit, retrospective evaluation, isolated serving, HTTP verification,
  clean source packaging and raw corpus packaging.
- tests/: maintained Python and JavaScript state regressions.
- docs/VERIFICATION.md: consolidated evidence, limitations and manual visual checks.

The default 80,025-paper map runs without raw corpora. data/corpus_*.json files and
manifests are local, Git-ignored, needed for rebuilding and included only in the
separate corpus ZIP. output/ contains regenerated local artifacts, never runtime
requirements. .venv and credentials are local only. No legacy Streamlit, pipeline,
probes, duplicate starter archives or staged old/new serving versions are shipped.
