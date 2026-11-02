"""Retrospective corpus co-occurrence evaluation, not prospective validation.

Example (after verified raw files have been retrieved):
  python -m scripts.evaluate_history --data-dir data --trees data/audit/history_mesh_trees.json

Only publication years and currently stored descriptor assignments are available.
An as-of-2018 index or ontology cannot be reconstructed from these files. This
script therefore never updates serving validation.json or restores the old 2x
claim. It writes a separate, inspectable exploratory result and selected pairs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gapfinder import fetch, grid, mesh


THRESHOLDS = (1, 2, 3)
SCOPE = "Retrospective corpus co-occurrence using current stored MeSH assignments."
LIMITATIONS = [
    "This is not an as-of-2018 or prospective experiment. Current MeSH assignments, "
    "descriptor trees and hand-written axis rules may encode later knowledge.",
    "The stored-year parser prefers Journal/JournalIssue/PubDate/Year, then "
    "ArticleDate/Year, then the leading year of Journal/PubDate/MedlineDate. "
    "This is not when the record, abstract or indexing became available. "
    "Electronic and print dates can differ; source date kinds are not retained separately.",
    "The endpoint is exact descriptor-UI co-occurrence in this early-detection "
    "corpus, not all PubMed work, scientific novelty, feasibility or clinical benefit. "
    "It does not apply PubMed's descendant-term query expansion to each pairing.",
    "MEDLINE indexing changed toward full automation in April 2022; vocabulary "
    "changes and back-indexing can create apparent changes in co-occurrence.",
    "Matching is conditional on the same disease and a training method-frequency "
    "bin. It does not adjust method age, topic trends or every relevant confounder. "
    "Unmatched flagged cells are excluded from the matched comparison and listed.",
    "Bootstrap intervals are descriptive, conditional on the fixed axes, matches "
    "and ontology. They resample diseases, not independent cells. Shared methods "
    "and papers can still correlate different disease clusters; this is not corrected.",
    "The observed corpus is not a random sample of research opportunities. Few "
    "disease clusters, partial final years and changing indexing limit inference. "
    "Intervals do not account for retrieval, ontology or indexing uncertainty.",
    "The three thresholds are exploratory sensitivity checks, without a "
    "multiple-comparison adjustment or a preregistered confirmatory hypothesis.",
    "The historical 2x lift remains withdrawn and corrected prospective "
    "validation remains pending, regardless of these exploratory results.",
]
REFERENCES = [
    {"title": "NLM: Frequently Asked Questions about Indexing for MEDLINE",
     "url": "https://www.nlm.nih.gov/bsd/indexfaq.html",
     "relevance": "Indexing transition and limits of publication-date splits."},
    {"title": "Cameron and Miller: A Practitioner's Guide to Cluster-Robust Inference",
     "url": "https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015_February.pdf",
     "relevance": "Within-cluster dependence, few clusters and multi-way limitations."},
    {"title": "SciPy bootstrap reference",
     "url": "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html",
     "relevance": "Paired resampling and percentile interval definition; "
                  "this script resamples disease blocks using the standard library."},
]
ORIGINAL_VALIDATION_REQUIREMENTS = [
    "The original ranker source revision, exact parameters, frozen candidate "
    "population, selected examples and original numerical outputs.",
    "Archived query text, returned PMID lists, full source records and a "
    "reconciled retrieval log for the original train and holdout corpora.",
    "Records and indexing exactly as available at the historical cutoff, including "
    "record/abstract/index availability dates and a versioned historical ontology; "
    "current publication-year filtering is not a substitute.",
    "A predefined endpoint and eligibility/date rules separating corpus "
    "co-occurrence from historically scoped full-PubMed novelty judgments.",
    "An independent, time-frozen evaluation set, appropriate controls, a specified "
    "uncertainty model and expert adjudication if claiming scientific usefulness.",
]


class IncompleteOntologyError(ValueError):
    """A frozen tree cache cannot classify every frequent training descriptor."""

    def __init__(self, missing: list[dict]):
        self.missing = missing
        super().__init__(f"Frozen ontology is missing {len(missing)} training descriptors; "
                         "evaluation is incomplete and no outcome rates were calculated.")


def _ids_hash(ids) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def _cell_id(row: dict) -> str:
    return row["problem_ui"] + "|" + row["method_ui"]


def frequency_bin(frequency: int) -> int:
    """Uncapped log2 bin: [2**bin, 2**(bin+1)); no future counts are used."""
    if type(frequency) is not int or frequency < 1:
        raise ValueError("A positive integer training frequency is required.")
    return frequency.bit_length() - 1


def match_without_replacement(flagged: list[dict], controls: list[dict], *, seed: int = 0) -> dict:
    """Random 1:1 matches within exact-disease/training-frequency strata.

    Random subsets are chosen when controls are scarce. A control cell is used
    once at most, and matching never reads score-window counts or outcomes.
    """
    if len({_cell_id(r) for r in flagged}) != len(flagged):
        raise ValueError("Duplicate flagged cells.")
    if len({_cell_id(r) for r in controls}) != len(controls):
        raise ValueError("Duplicate control cells.")
    if {_cell_id(r) for r in flagged} & {_cell_id(r) for r in controls}:
        raise ValueError("Flagged and control populations overlap.")
    by_flag, by_control = defaultdict(list), defaultdict(list)
    for rows, target in ((flagged, by_flag), (controls, by_control)):
        for row in rows:
            key = (row["problem_ui"], frequency_bin(row["method_papers"]))
            target[key].append(row)
    rng = random.Random(seed)
    pairs, strata = [], []
    for key in sorted(set(by_flag) | set(by_control)):
        f = sorted(by_flag[key], key=_cell_id)
        c = sorted(by_control[key], key=_cell_id)
        rng.shuffle(f)
        rng.shuffle(c)
        n = min(len(f), len(c))
        pairs.extend({"flagged_id": _cell_id(fr), "control_id": _cell_id(cr),
                      "problem_ui": key[0], "method_frequency_bin": key[1]}
                     for fr, cr in zip(f[:n], c[:n]))
        strata.append({"problem_ui": key[0], "method_frequency_bin": key[1],
                       "frequency_min": 2 ** key[1], "frequency_max_exclusive": 2 ** (key[1] + 1),
                       "flagged_n": len(f), "control_n": len(c), "matched_pairs": n})
    used_f = {p["flagged_id"] for p in pairs}
    used_c = {p["control_id"] for p in pairs}
    return {"method": "1:1, same disease UI and floor(log2(training method frequency))",
            "replacement": False, "seed": seed, "matched_pairs": len(pairs),
            "flagged_n": len(flagged), "control_pool_n": len(controls),
            "flagged_match_share": len(pairs) / len(flagged) if flagged else None,
            "unmatched_flagged_ids": sorted({_cell_id(r) for r in flagged} - used_f),
            "unused_control_ids": sorted({_cell_id(r) for r in controls} - used_c),
            "strata": strata, "pairs": pairs}


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lo = math.floor(index)
    return ordered[lo] + (ordered[math.ceil(index)] - ordered[lo]) * (index - lo)


def disease_cluster_bootstrap(pairs: list[dict], *, resamples: int = 5000,
                              confidence: float = 0.95, seed: int = 1) -> dict:
    """Resample whole matched disease blocks, retaining both sides of each pair.

    Groups can have different sizes. Rates in each replicate use its actual
    number of matched cells, not an average of group-specific rates. A ratio
    interval is withheld if any replicate has a zero control rate; undefined
    ratios are never dropped or silently smoothed.
    """
    if type(resamples) is not int or resamples < 1 or not 0 < confidence < 1:
        raise ValueError("Use positive resamples and a confidence level between 0 and 1.")
    groups = defaultdict(list)
    for pair in pairs:
        if type(pair["flagged_future_papers"]) is not int or pair["flagged_future_papers"] < 0:
            raise ValueError("Invalid flagged outcome count.")
        if type(pair["control_future_papers"]) is not int or pair["control_future_papers"] < 0:
            raise ValueError("Invalid control outcome count.")
        groups[pair["problem_ui"]].append(pair)
    out = {"method": "paired disease-cluster percentile bootstrap",
           "confidence_level": confidence, "resamples": resamples, "seed": seed,
           "disease_clusters": len(groups),
           "scope": "Descriptive conditional intervals; shared-method and cross-disease "
                    "paper dependence are not corrected.",
           "small_cluster_warning": len(groups) < 20, "thresholds": {}}
    if len(groups) < 2:
        out["status"] = "unavailable_fewer_than_two_disease_clusters"
        for threshold in THRESHOLDS:
            out["thresholds"][str(threshold)] = {
                "risk_difference_ci": None, "risk_ratio_ci": None,
                "ratio_undefined_resamples": None}
        return out
    out["status"] = "descriptive_only"
    blocks = []
    for disease in sorted(groups):
        rows = groups[disease]
        blocks.append((len(rows),
                       [sum(r["flagged_future_papers"] >= t for r in rows) for t in THRESHOLDS],
                       [sum(r["control_future_papers"] >= t for r in rows) for t in THRESHOLDS]))
    diffs = {t: [] for t in THRESHOLDS}
    ratios = {t: [] for t in THRESHOLDS}
    undefined = Counter()
    rng = random.Random(seed)
    for _ in range(resamples):
        selected = [blocks[rng.randrange(len(blocks))] for _ in blocks]
        denominator = sum(b[0] for b in selected)
        for j, threshold in enumerate(THRESHOLDS):
            flagged_hits = sum(b[1][j] for b in selected)
            control_hits = sum(b[2][j] for b in selected)
            diffs[threshold].append((flagged_hits - control_hits) / denominator)
            if control_hits:
                ratios[threshold].append(flagged_hits / control_hits)
            else:
                undefined[threshold] += 1
    tail = (1 - confidence) / 2
    for threshold in THRESHOLDS:
        ratio_ci = None
        if not undefined[threshold]:
            ratio_ci = [_quantile(ratios[threshold], tail), _quantile(ratios[threshold], 1 - tail)]
        out["thresholds"][str(threshold)] = {
            "risk_difference_ci": [_quantile(diffs[threshold], tail),
                                   _quantile(diffs[threshold], 1 - tail)],
            "risk_ratio_ci": ratio_ci, "ratio_undefined_resamples": undefined[threshold],
            "ratio_ci_status": "available" if ratio_ci is not None else "zero_control_rate_in_resamples"}
    return out


def evaluate(corpus: dict, trees: dict, *, cutoff: int = 2018,
             start_year: int = 2005, end_year: int = 2026,
             axis_options: dict | None = None, min_shared: int = 2,
             seed: int = 0, bootstrap_resamples: int = 5000,
             confidence: float = 0.95) -> dict:
    """Pure evaluation: select/match from training, then compute later outcomes.

    The caller supplies records and a frozen ontology. The CLI additionally
    verifies complete raw-cache manifests. Missing frequent training descriptors
    are an incomplete evaluation, never an excuse to resolve a newer ontology.
    """
    if not start_year <= cutoff < end_year or type(min_shared) is not int or min_shared < 1:
        raise ValueError("Use start_year <= cutoff < end_year and positive min_shared.")
    if not corpus or not isinstance(trees, dict):
        raise ValueError("A non-empty corpus and descriptor-tree mapping are required.")
    records, exclusions = {}, Counter()
    for pmid, row in sorted(corpus.items()):
        if not isinstance(pmid, str) or not pmid.isdigit() or not isinstance(row, dict):
            raise ValueError("Records must be a mapping from PMID strings to source records.")
        year = row.get("year")
        if year is None:
            exclusions["missing_year"] += 1
            continue
        if type(year) is not int:
            raise ValueError(f"PMID {pmid}: publication year must be an integer.")
        if not start_year <= year <= end_year:
            exclusions["outside_year_window"] += 1
            continue
        terms = row.get("mesh")
        if not isinstance(terms, list) or any(
                not isinstance(t, (tuple, list)) or len(t) != 3
                or not isinstance(t[0], str) or not t[0]
                or not isinstance(t[1], str) or not t[1] for t in terms):
            raise ValueError(f"PMID {pmid}: malformed MeSH descriptors.")
        if len({t[0] for t in terms}) != len(terms):
            raise ValueError(f"PMID {pmid}: duplicate descriptor UI would distort training frequencies.")
        records[pmid] = row
    training = {p: r for p, r in records.items() if r["year"] <= cutoff}
    holdout = {p: r for p, r in records.items() if r["year"] > cutoff}
    if not training or not holdout:
        raise ValueError("Both the training and later-publication corpus must be non-empty.")
    frequencies = Counter(u for r in training.values() for u, _name, _major in r["mesh"])
    names = {u: name for r in training.values() for u, name, _major in r["mesh"]}
    required = {u for u, n in frequencies.items() if n >= grid.MIN_BRIDGE_FREQ}
    missing = [{"ui": u, "name": names[u], "training_papers": frequencies[u]}
               for u in sorted(required) if u not in trees or trees[u] == []]
    if missing:
        raise IncompleteOntologyError(missing)
    for ui in required:
        positions = trees[ui]
        if not isinstance(positions, list) or any(not mesh.well_formed(t) for t in positions):
            raise ValueError(f"Frozen ontology has malformed positions for {ui}.")

    def frozen_trees(uis, verbose=True):
        return {u: list(trees[u]) for u in uis}

    options = dict(mesh.PRODUCTION_AXIS_OPTIONS if axis_options is None else axis_options)
    # No future records enter axis selection, vocabulary frequencies, IDF or ranking.
    # Prevent resolve_trees from making HTTP calls or modifying the shared tree cache.
    with patch.object(mesh, "resolve_trees", frozen_trees):
        trained = grid.rank_gaps(grid.build(training, verbose=False, **options), min_shared=min_shared)
    if not trained.problems or not trained.methods:
        raise ValueError("Training data selected no disease or method axes; do not invent a comparison.")
    flagged = trained.gaps
    controls = [r for r in trained.rejects if r.get("n_bridges") is not None]
    siblings = [r for r in trained.rejects if r.get("n_bridges") is None]
    matching = match_without_replacement(flagged, controls, seed=seed)

    # Matching is complete before the held-out outcomes are even counted.
    future = defaultdict(list)
    pset, mset = set(trained.problems), set(trained.methods)
    for pmid, rec in holdout.items():
        terms = {u for u, _name, _major in rec["mesh"]}
        for p in terms & pset:
            for m in terms & mset:
                future[(p, m)].append(pmid)
    audit_rows = []
    for group, rows in (("flagged", flagged), ("unflagged", controls), ("sibling_excluded", siblings)):
        for row in rows:
            pmids = sorted(future[(row["problem_ui"], row["method_ui"])])
            audit_rows.append({**row, "id": _cell_id(row), "group": group,
                               "training_cooccurrence": 0,
                               "later_papers": len(pmids), "later_pmids": pmids})
    audit_rows.sort(key=lambda r: r["id"])
    by_id = {r["id"]: r for r in audit_rows}
    paired_outcomes = []
    for pair in matching["pairs"]:
        paired_outcomes.append({**pair,
                                "flagged_future_papers": by_id[pair["flagged_id"]]["later_papers"],
                                "control_future_papers": by_id[pair["control_id"]]["later_papers"]})
    bootstrap = disease_cluster_bootstrap(paired_outcomes, resamples=bootstrap_resamples,
                                          confidence=confidence, seed=seed + 1)

    def rate(rows, threshold):
        n = len(rows)
        hits = sum(r["later_papers"] >= threshold for r in rows)
        return {"n": n, "hits": hits, "rate": hits / n if n else None}

    summaries = {}
    matched_f = [by_id[p["flagged_id"]] for p in matching["pairs"]]
    matched_c = [by_id[p["control_id"]] for p in matching["pairs"]]
    for threshold in THRESHOLDS:
        f, c = rate(matched_f, threshold), rate(matched_c, threshold)
        difference = f["rate"] - c["rate"] if f["n"] else None
        ratio = f["rate"] / c["rate"] if f["n"] and c["rate"] else None
        summaries[str(threshold)] = {
            "endpoint": f"later exact-UI corpus co-occurrence >= {threshold} distinct PMIDs",
            "flagged_all": rate([by_id[_cell_id(r)] for r in flagged], threshold),
            "unflagged_all": rate([by_id[_cell_id(r)] for r in controls], threshold),
            "matched_flagged": f, "matched_control": c,
            "matched_risk_difference": difference, "matched_risk_ratio": ratio,
            "ratio_status": "available" if ratio is not None else "no_pairs_or_zero_control_rate",
            **bootstrap["thresholds"][str(threshold)]}
    log_differences = [abs(math.log2(by_id[p["flagged_id"]]["method_papers"])
                           - math.log2(by_id[p["control_id"]]["method_papers"]))
                       for p in matching["pairs"]]
    matching["mean_absolute_log2_method_frequency_difference"] = (
        sum(log_differences) / len(log_differences) if log_differences else None)
    matching["max_absolute_log2_method_frequency_difference"] = max(log_differences, default=None)
    matching["pairs"] = paired_outcomes
    return {
        "schema_version": 1, "analysis_type": "retrospective_corpus_cooccurrence",
        "status": "evaluated_with_caveats" if paired_outcomes else "no_comparable_pairs",
        "scope": SCOPE, "serving_validation_status": "pending_remeasurement",
        "historical_2x_claim_restored": False, "prospective_validation": False,
        "parameters": {"cutoff": cutoff, "start_year": start_year, "end_year": end_year,
                       "axis_options": options, "min_shared_bridges": min_shared,
                       "max_bridge_share": grid.MAX_BRIDGE_SHARE,
                       "min_bridge_frequency": grid.MIN_BRIDGE_FREQ,
                       "min_bridge_axis_cooccurrence": grid.MIN_BRIDGE_COOC,
                       "matching_seed": seed, "bootstrap_seed": seed + 1,
                       "bootstrap_resamples": bootstrap_resamples, "confidence_level": confidence},
        "population": {"supplied_papers": len(corpus), "eligible_papers": len(records),
                       "exclusions": dict(exclusions), "training_papers": len(training),
                       "later_papers": len(holdout), "pmid_overlap": len(training.keys() & holdout.keys()),
                       "training_pmids_sha256": _ids_hash(training),
                       "later_pmids_sha256": _ids_hash(holdout),
                       "training_year_counts": dict(sorted(Counter(r["year"] for r in training.values()).items())),
                       "later_year_counts": dict(sorted(Counter(r["year"] for r in holdout.values()).items()))},
        "axis_selection": {"records_used": "training_only",
                           "diseases": [{"ui": u, "name": trained.name[u], "training_papers": trained.freq[u]}
                                        for u in trained.problems],
                           "methods": [{"ui": u, "name": trained.name[u], "training_papers": trained.freq[u]}
                                       for u in trained.methods],
                           "frequent_training_descriptors_classified": len(required)},
        "candidate_population": {"cells": trained.n_cells, "training_filled_cells": trained.n_filled,
                                 "training_empty_cells": trained.n_cells - trained.n_filled,
                                 "sibling_excluded_cells": len(siblings),
                                 "eligible_flagged_cells": len(flagged),
                                 "eligible_unflagged_cells": len(controls)},
        "matching": matching, "bootstrap": bootstrap, "thresholds": summaries,
        "cell_audit": audit_rows, "limitations": LIMITATIONS,
        "requirements_for_original_effect_validation": ORIGINAL_VALIDATION_REQUIREMENTS,
        "method_references": REFERENCES,
    }


def _write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data",
                        help="Directory containing both verified *_full.json files and manifests")
    parser.add_argument("--trees", type=Path, default=ROOT / "data" / "mesh_trees.json",
                        help="Frozen descriptor-tree JSON; no online resolution is performed")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "history-evaluation.json")
    parser.add_argument("--cutoff", type=int, default=2018)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--bootstrap-resamples", type=int, default=5000)
    parser.add_argument("--confidence", type=float, default=0.95)
    args = parser.parse_args(argv)
    data_dir, tree_path, output = args.data_dir.resolve(), args.trees.resolve(), args.output.resolve()
    if (output.is_relative_to(data_dir) or output.is_relative_to((ROOT / "data").resolve())
            or output == tree_path):
        parser.error("Write the exploratory output separately from all raw/serving data and ontology inputs.")
    try:
        with patch.object(fetch, "DATA", data_dir):
            corpus, sources = fetch._production_snapshot()
        tree_bytes = tree_path.read_bytes()
        trees = json.loads(tree_bytes)
        provenance = {
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "topic_query": fetch.TOPIC, "raw_sources": sources,
            "frozen_ontology": {"path": str(tree_path),
                                "sha256": hashlib.sha256(tree_bytes).hexdigest(),
                                "historical_as_of_version_known": False},
            "source_code": [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                            for p in (Path(__file__), Path(grid.__file__), Path(mesh.__file__), Path(fetch.__file__))],
            "python_version": sys.version,
        }
        try:
            result = evaluate(corpus, trees, cutoff=args.cutoff, seed=args.seed,
                              bootstrap_resamples=args.bootstrap_resamples, confidence=args.confidence)
        except IncompleteOntologyError as exc:
            result = {"schema_version": 1, "analysis_type": "retrospective_corpus_cooccurrence",
                      "status": "incomplete_ontology", "scope": SCOPE,
                      "serving_validation_status": "pending_remeasurement",
                      "historical_2x_claim_restored": False, "prospective_validation": False,
                      "missing_training_descriptors": exc.missing, "error": str(exc),
                      "limitations": LIMITATIONS,
                      "requirements_for_original_effect_validation": ORIGINAL_VALIDATION_REQUIREMENTS,
                      "method_references": REFERENCES}
        result["provenance"] = provenance
        result["command"] = [str(Path(__file__).resolve()), *(argv if argv is not None else sys.argv[1:])]
        _write_result(output, result)
    except (OSError, ValueError, fetch.CorpusIntegrityError) as exc:
        parser.exit(2, f"Historical evaluation could not run: {exc}\n")
    print(f"Retrospective result: {result['status']}; {output}")
    print("Historical 2x lift remains withdrawn; this is not prospective validation.")
    if result["status"] == "incomplete_ontology":
        print(result["error"])
        return 2
    pop, matched = result["population"], result["matching"]
    print(f"Training {pop['training_papers']:,}; later {pop['later_papers']:,}; "
          f"matched pairs {matched['matched_pairs']}; "
          f"disease clusters {result['bootstrap']['disease_clusters']}")
    for threshold, row in result["thresholds"].items():
        f, c = row["matched_flagged"], row["matched_control"]
        print(f">={threshold} later papers: flagged {f['hits']}/{f['n']}; "
              f"control {c['hits']}/{c['n']}; difference {row['matched_risk_difference']}; "
              f"descriptive CI {row['risk_difference_ci']}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
