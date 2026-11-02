"""Methodological checks for the separate retrospective experiment."""
from copy import deepcopy
import json

import pytest

from gapfinder import fetch, grid, mesh
from scripts import evaluate_history as history


@pytest.fixture
def synthetic():
    """Two diseases, two flagged methods and two controls; all train cells empty."""
    trees = {"P1": ["C04.111"], "P2": ["C04.222"],
             "F1": ["E05.393.111"], "F2": ["E05.393.222"],
             "C1": ["E05.393.333"], "C2": ["E05.393.444"],
             "B1": ["D12.111"], "B2": ["G01.111"]}
    corpus = {}

    def add(year, terms):
        pmid = str(len(corpus) + 1)
        corpus[pmid] = {"year": year, "title": pmid,
                        "mesh": [[u, u, False] for u in terms]}

    for disease in ("P1", "P2"):
        for i in range(60):
            add(2018, [disease] + (["B1", "B2"] if i < 2 else []))
    for method in ("F1", "F2", "C1", "C2"):
        for i in range(40):
            add(2018, [method] + (["B1", "B2"] if method.startswith("F") and i < 2 else []))
    for _ in range(220):
        add(2017, [])  # N=500 ensures each bridge's frequency 8 is rare (<=3%).
    for year, terms in [(2019, ["P1", "F1"]), (2020, ["P1", "F1"]),
                        (2020, ["P1", "F2"]), (2019, ["P2", "C1"]),
                        (2020, ["P2", "F2"]), (2021, ["P2", "F2"]),
                        (2022, ["P2", "F2"])]:
        add(year, terms)
    # These would dominate future-selected axes, but must never enter training.
    for _ in range(100):
        add(2026, ["NEW_DISEASE", "NEW_METHOD"])
    return corpus, trees


def test_axes_and_matching_are_training_only_and_thresholds_reconcile(synthetic, monkeypatch):
    corpus, trees = synthetic
    original_build = grid.build

    def training_only(records, **kwargs):
        assert len(records) == 500
        assert all(r["year"] <= 2018 for r in records.values())
        return original_build(records, **kwargs)

    monkeypatch.setattr(grid, "build", training_only)
    monkeypatch.setattr(mesh, "_trees_from_rdf", lambda *_: pytest.fail("No online ontology resolution"))
    result = history.evaluate(corpus, trees, bootstrap_resamples=100)
    assert {r["ui"] for r in result["axis_selection"]["diseases"]} == {"P1", "P2"}
    assert {r["ui"] for r in result["axis_selection"]["methods"]} == {"F1", "F2", "C1", "C2"}
    assert result["population"]["training_papers"] == 500
    assert result["population"]["later_papers"] == 107
    assert result["population"]["pmid_overlap"] == 0
    assert result["candidate_population"] == {
        "cells": 8, "training_filled_cells": 0, "training_empty_cells": 8,
        "sibling_excluded_cells": 0, "eligible_flagged_cells": 4, "eligible_unflagged_cells": 4}
    assert result["matching"]["matched_pairs"] == 4
    for threshold, expected_flagged, expected_control in (("1", 3, 1), ("2", 2, 0), ("3", 1, 0)):
        row = result["thresholds"][threshold]
        assert row["matched_flagged"] == {"n": 4, "hits": expected_flagged, "rate": expected_flagged / 4}
        assert row["matched_control"] == {"n": 4, "hits": expected_control, "rate": expected_control / 4}
        assert row["matched_risk_difference"] == (expected_flagged - expected_control) / 4
    assert result["thresholds"]["1"]["matched_risk_ratio"] == 3
    assert result["thresholds"]["2"]["matched_risk_ratio"] is None
    assert result["thresholds"]["1"]["risk_difference_ci"] == [0.0, 1.0]
    assert result["thresholds"]["2"]["risk_difference_ci"] == [0.5, 0.5]
    assert all(row["risk_ratio_ci"] is None for row in result["thresholds"].values())
    assert result["bootstrap"]["disease_clusters"] == 2
    assert result["bootstrap"]["small_cluster_warning"] is True
    assert result["serving_validation_status"] == "pending_remeasurement"
    assert result["historical_2x_claim_restored"] is False
    assert result["prospective_validation"] is False
    json.dumps(result, allow_nan=False)


def cell(disease, method, frequency=40):
    return {"problem_ui": disease, "method_ui": method, "method_papers": frequency}


def test_matching_uses_distinct_controls_same_disease_and_uncapped_frequency_bins():
    flagged = [cell("P1", "F1"), cell("P1", "F2"), cell("P1", "F3"),
               cell("P2", "F4"), cell("P1", "F5", 1000)]
    controls = [cell("P1", "C1"), cell("P1", "C2"), cell("P3", "C3"),
                cell("P1", "C4", 100)]
    out = history.match_without_replacement(flagged, controls, seed=11)
    assert out["matched_pairs"] == 2
    assert len({p["control_id"] for p in out["pairs"]}) == 2
    assert len({p["flagged_id"] for p in out["pairs"]}) == 2
    assert all(p["problem_ui"] == "P1" for p in out["pairs"])
    assert len(out["unmatched_flagged_ids"]) == 3
    assert history.frequency_bin(1024) == 10
    assert history.frequency_bin(40) == 5
    assert history.frequency_bin(63) == 5
    assert history.frequency_bin(64) == 6
    assert out == history.match_without_replacement(list(reversed(flagged)), list(reversed(controls)), seed=11)


@pytest.mark.parametrize("flagged, controls", [
    ([cell("P", "M"), cell("P", "M")], []),
    ([], [cell("P", "M"), cell("P", "M")]),
    ([cell("P", "M")], [cell("P", "M")]),
])
def test_duplicate_or_overlapping_populations_are_refused(flagged, controls):
    with pytest.raises(ValueError):
        history.match_without_replacement(flagged, controls)


@pytest.mark.parametrize("missing_entry", [True, False])
def test_frozen_ontology_gap_is_explicit_and_no_network_or_fake_rates(synthetic, missing_entry):
    corpus, trees = synthetic
    if missing_entry:
        del trees["B1"]
    else:
        trees["B1"] = []
    with pytest.raises(history.IncompleteOntologyError) as exc:
        history.evaluate(corpus, trees)
    assert exc.value.missing == [{"ui": "B1", "name": "B1", "training_papers": 8}]


def test_duplicate_descriptor_would_not_double_training_paper_frequency(synthetic):
    corpus, trees = synthetic
    corpus["1"]["mesh"].append(corpus["1"]["mesh"][0])
    with pytest.raises(ValueError, match="duplicate descriptor"):
        history.evaluate(corpus, trees)


def test_reversed_input_does_not_change_seeded_results_or_mutate_sources(synthetic):
    corpus, trees = synthetic
    before = deepcopy((corpus, trees))
    a = history.evaluate(corpus, trees, seed=8, bootstrap_resamples=50)
    b = history.evaluate(dict(reversed(list(corpus.items()))), trees, seed=8, bootstrap_resamples=50)
    assert a == b
    assert (corpus, trees) == before


def test_disease_blocks_are_kept_paired_and_unequal_sizes_use_total_denominators():
    pairs = [{"problem_ui": "P1", "flagged_future_papers": 1, "control_future_papers": 0}]
    pairs += [{"problem_ui": "P2", "flagged_future_papers": 0, "control_future_papers": 1}] * 3
    result = history.disease_cluster_bootstrap(pairs, resamples=200, seed=9)
    # Whole-block draws permit only -1, -0.5, +1, not independently mixed cells.
    assert result["thresholds"]["1"]["risk_difference_ci"] == [-1.0, 1.0]
    assert result["thresholds"]["1"]["ratio_undefined_resamples"] > 0
    assert result["thresholds"]["1"]["risk_ratio_ci"] is None
    assert result["thresholds"]["2"]["risk_difference_ci"] == [0.0, 0.0]
    middle = history.disease_cluster_bootstrap(pairs, resamples=200, seed=9, confidence=0.1)
    # A replicate with both blocks has (1 - 3) / (1 + 3) = -0.5.
    # Averaging block-specific differences instead would incorrectly produce 0.
    assert middle["thresholds"]["1"]["risk_difference_ci"] == [-0.5, -0.5]


def test_ratio_interval_is_available_only_when_every_resample_has_a_control_hit():
    pairs = [{"problem_ui": "P1", "flagged_future_papers": 3, "control_future_papers": 3},
             {"problem_ui": "P2", "flagged_future_papers": 3, "control_future_papers": 3}]
    result = history.disease_cluster_bootstrap(pairs, resamples=50)
    for row in result["thresholds"].values():
        assert row["risk_ratio_ci"] == [1.0, 1.0]
        assert row["ratio_undefined_resamples"] == 0
        assert row["risk_difference_ci"] == [0.0, 0.0]


def test_no_comparators_and_one_disease_do_not_produce_spurious_intervals():
    empty = history.disease_cluster_bootstrap([], resamples=20)
    assert empty["disease_clusters"] == 0
    assert all(r["risk_difference_ci"] is None for r in empty["thresholds"].values())
    one = history.disease_cluster_bootstrap([
        {"problem_ui": "P", "flagged_future_papers": 1, "control_future_papers": 0}], resamples=20)
    assert one["status"] == "unavailable_fewer_than_two_disease_clusters"
    assert one["thresholds"]["1"]["risk_difference_ci"] is None


def test_year_boundary_and_missing_or_outside_year_exclusions(synthetic):
    corpus, trees = synthetic
    corpus["10000"] = {"year": None, "mesh": []}
    corpus["10001"] = {"year": 2004, "mesh": []}
    corpus["10002"] = {"year": 2027, "mesh": []}
    result = history.evaluate(corpus, trees, bootstrap_resamples=20)
    assert result["population"]["exclusions"] == {"missing_year": 1, "outside_year_window": 2}
    assert result["population"]["training_year_counts"][2018] == 280
    assert result["population"]["later_year_counts"][2019] == 2


def test_cli_writes_a_separate_reproducible_result_and_preserves_serving_state(synthetic, tmp_path, monkeypatch):
    corpus, trees = synthetic
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "validation.json").write_text('{"status":"pending_remeasurement"}')
    tree_file = tmp_path / "trees.json"
    tree_file.write_text(json.dumps(trees))
    output = tmp_path / "analysis.json"
    monkeypatch.setattr(fetch, "_production_snapshot", lambda: (corpus, [{"sha256": "source-hash"}]))
    assert history.main(["--data-dir", str(raw), "--trees", str(tree_file),
                         "--output", str(output), "--bootstrap-resamples", "50"]) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["provenance"]["raw_sources"] == [{"sha256": "source-hash"}]
    assert len(result["provenance"]["frozen_ontology"]["sha256"]) == 64
    assert result["serving_validation_status"] == "pending_remeasurement"
    assert json.loads((raw / "validation.json").read_text())["status"] == "pending_remeasurement"
    with pytest.raises(SystemExit):
        history.main(["--data-dir", str(raw), "--trees", str(tree_file),
                      "--output", str(raw / "validation.json")])
    # The selected raw directory can differ from the actual serving directory.
    # A custom --output must not turn an exploratory run into a validation update.
    with pytest.raises(SystemExit):
        history.main(["--data-dir", str(raw), "--trees", str(tree_file),
                      "--output", str(history.ROOT / "data" / "validation.json")])


def test_cli_missing_frozen_terms_writes_incomplete_without_thresholds(synthetic, tmp_path, monkeypatch):
    corpus, trees = synthetic
    del trees["B1"]
    raw = tmp_path / "raw"
    raw.mkdir()
    tree_file = tmp_path / "trees.json"
    tree_file.write_text(json.dumps(trees))
    output = tmp_path / "analysis.json"
    monkeypatch.setattr(fetch, "_production_snapshot", lambda: (corpus, []))
    assert history.main(["--data-dir", str(raw), "--trees", str(tree_file), "--output", str(output)]) == 2
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "incomplete_ontology"
    assert result["historical_2x_claim_restored"] is False
    assert "thresholds" not in result and "cell_audit" not in result
