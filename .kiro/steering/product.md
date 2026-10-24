# ResearchBridge — what it is and what it must not claim

Hackachusetts 2026, track H4 (Accelerating Biotechnology Innovation).
Two data-science students, 8-hour build.

## What it does

Maps a research field as a grid of **diseases × lab methods**, finds combinations
no paper has tried, ranks them by whether the two literatures share underlying
biology, and produces a one-page brief: the evidence with every claim checked
against its source abstract, plus the Massachusetts labs holding each half.

Primary use case: a researcher needs a defensible **novelty statement** for a
grant — "no prior work applies method X to disease Y". Proving that absence
rigorously is the one thing this genuinely does well.

## Claims that are supported by measurement

- Flagged gaps are filled in later literature about **2× more often** than
  comparable empty cells (17% vs 9% popularity-matched vs 8% unflagged, measured
  on a 2018 cutoff scored against 2019–2026). **Re-measure after any axis change.**
- Every claim in the brief is verified against source text in code, not by a model.

## Claims that are NOT supported — never write these into the UI or pitch

- ❌ "Finds breakthroughs" / "predicts discoveries". At a threshold of ≥3 holdout
  papers the signal vanishes (6 of 328; the matched control equals it).
- ❌ "Would have found a real gap years before publication." Not demonstrated.
- ❌ Novelty of the method itself. Swanson & Smalheiser's **Arrowsmith** has done
  literature-based discovery since the 1990s (Swanson's fish-oil / Raynaud's
  result, 1986). What is new here: the measured lift, code-level claim
  verification, and the handoff to named local labs. Acknowledge Arrowsmith.
- ❌ That the two provided starter CSVs are the corpus. They cannot be — see tech.md.

## Required caveats to keep visible

- An empty cell is not evidence of a research gap on its own. We rank candidates;
  we do not assert absence is meaningful. Show the reject pile.
- NLM moved from human to largely automated MeSH indexing around 2022. The
  holdout window (2019–2026) straddles that change, so some "gap filled" signal
  could be an indexing shift rather than real research.
- Pre-2018 abstract coverage is 86%, so ~1,200 papers cannot be quoted as evidence.

## Demo priority order

1. Claim verification with the visible strikethrough — deterministic, 100%
   reliable, needs no explanation. **This is the strongest 20 seconds.**
2. The field map with ringed flagged cells.
3. The 2× validation chart, with both controls and the ceiling caveat shown.
4. The brief with the MA labs.

The brief is the deliverable. The web app is how the brief gets made.
