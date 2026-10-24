# Repo structure and build order

```
gapfinder/
  fetch.py      PubMed retrieval -> data/corpus_{past,future}.json      [DONE]
  mesh.py       tree numbers, axis rules, build_axes()                   [DONE]
  phrases.py    MeSH name -> OpenAlex search phrase                      [DONE]
  grid.py       co-occurrence, mechanistic bridges, IDF ranking          [phase 1]
  labs.py       OpenAlex MA institution lookup (port probes/openalex4) [phase 1]
  verify.py     the four-step claim gate                                 [phase 3]
  brief.py      assembles the one-pager                                  [phase 4]
app.py          FastAPI: serves static/index.html + 6 endpoints          [phase 2]

data/           caches + committed precomputed JSON (corpus_*.json gitignored,
                regenerate with `python -m gapfinder.fetch`, ~3 min)
probes/         the 11 exploratory scripts behind every number in README.md
static/         index.html — the designed frontend, already working as a mockup
starter/        the two provided Hackachusetts datasets, extracted
```

## Endpoints (`app.py`)

| route | source |
|---|---|
| `GET /api/corpus` | precomputed |
| `GET /api/grid` | precomputed |
| `GET /api/gap/{id}` | precomputed |
| `POST /api/verify` | live (code gate) |
| `GET /api/labs?topic=` | live OpenAlex |
| `GET /api/validation` | precomputed |

`static/index.html` currently holds its data in three `const` arrays
(`PROBLEMS`, `METHODS`, `COUNTS`). Phase 2 replaces those with `fetch()` calls.
Everything else in it — tooltips, cell clicks, the strikethrough sequence, bar
animation, tab switching, both themes — already works. **Do not rewrite the
frontend or introduce a framework.** The design is done; only the data source changes.

## Build order

- **Phase 1** (hrs 0–3, person A) — `grid.py`, `labs.py`; emit `grid.json`,
  `gaps.json`, `validation.json`. Re-measure the lift against the new 50×14 axes;
  the 2.0× figure came from a dirtier grid and does not match current code.
- **Phase 2** (hrs 0–3, person B, parallel) — `app.py` + rewire the frontend.
  Work against the mockup's existing hardcoded data from minute one; never idle
  waiting on phase 1.
- **Phase 3** (hrs 3–5, both) — `verify.py`. The best demo moment; two brains.
- **Phase 4** (hrs 5–6.5) — `brief.py`, live labs with the "already holds both
  halves" category, response caching plus hardcoded fallbacks.
- **Code freeze at 6.5 hours.** Non-negotiable.
- **Phase 5** (hrs 6.5–8) — three timed rehearsals. No new features.

## Out of scope unless phase 1 finishes early

- **Learned gap ranker.** Strongest extension: the time-sliced validation produced
  labels (533 empty cells, each live-verified in `data/confirmed.json`).
  Logistic regression — NOT gradient boosting, there are only ~55 positives.
  Candidate features: `n_shared_bridges`, `idf_sum`, `max_idf`, axis frequencies,
  `neighbor_jaccard`, `method_year_trend`, and `sibling_cells_filled` (has this
  method already been used on related diseases in the same subtree?) — that last
  one is the best bet and may beat the bridge count.
- Semantic bridges via embeddings. One additive feature, computed offline, dropped
  gracefully if the file is absent.

## Conventions

- Type hints on public functions; module docstrings explain *why*, since most
  rules here exist to prevent a specific wrong output.
- Cache every network call to `data/`, keyed by query. Cache hit and cold run
  must be the same code path.
- Secrets in `.env` only. `.env.example` is tracked and stays empty.
