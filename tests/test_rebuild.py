from collections import Counter
import json

import pytest

from gapfinder import confirm, fetch, grid
from gapfinder.validation import pending_validation, serving_validation


@pytest.fixture
def rebuild_inputs(monkeypatch):
    example = grid.Grid(problems=["P"], methods=["M1", "M2"],
                        name={"P": "Disease", "M1": "Method One", "M2": "Method Two"},
                        freq=Counter({"P": 100, "M1": 80, "M2": 60}),
                        trees={}, counts={}, bridges={}, idf={}, n_papers=120)
    monkeypatch.setattr(fetch, "load_production", lambda: {"1": {"year": 2020}})
    monkeypatch.setattr(grid, "build", lambda *a, **kw: example)
    monkeypatch.setattr(grid, "validate", lambda **kw: {"cutoff": 2018, "thresholds": {}})
    return example


def test_emit_confirms_all_empty_cells_including_bridge_rejections(tmp_path, monkeypatch, rebuild_inputs):
    def saved_counts(rows, **kwargs):
        assert len(rows) == 2  # both rejected by the exploratory bridge score
        return [{**row, "maturity": 100, "gap_papers": i, "real_gap": True}
                for i, row in enumerate(rows)]

    monkeypatch.setattr(confirm, "confirm", saved_counts)
    output = grid.emit(tmp_path, verbose=False)
    assert {p.name for p in tmp_path.iterdir()} == {
        "grid.json", "gaps.json", "confirmed.json", "validation.json"}
    assert len(json.loads((tmp_path / "confirmed.json").read_text())) == 2
    assert output["validation"]["status"] == "pending_remeasurement"
    assert output["validation"]["established_negative_result"]["verdict"] is False
    assert output["validation"]["historical_analysis"]["cutoff"] == 2018


def test_failed_confirmation_leaves_existing_serving_snapshots_untouched(tmp_path, monkeypatch, rebuild_inputs):
    for name in ("grid.json", "gaps.json", "confirmed.json", "validation.json"):
        (tmp_path / name).write_text("saved snapshot")
    monkeypatch.setattr(confirm, "confirm", lambda rows, **kw: rows[:1])
    with pytest.raises(RuntimeError, match="Confirmation is incomplete"):
        grid.emit(tmp_path, verbose=False)
    assert all(p.read_text() == "saved snapshot" for p in tmp_path.iterdir())


def test_legacy_validation_cannot_remove_withdrawal_or_approve_lift():
    legacy = {"cutoff": 2018, "thresholds": {"1": {"lift_vs_unflagged": 2.0}}}
    state = serving_validation(legacy)
    assert state["status"] == "pending_remeasurement"
    assert state["withdrawn_claim"].startswith("2.0x")
    assert state["established_negative_result"]["verdict"] is False
    assert state["historical_analysis"] == legacy
    assert serving_validation(pending_validation(legacy)) == state


def test_api_normalises_legacy_validation_and_uses_actionable_repair_command(tmp_path, monkeypatch):
    import app as backend
    monkeypatch.setattr(backend, "DATA", tmp_path)
    (tmp_path / "validation.json").write_text(json.dumps({"cutoff": 2018}))
    state = backend.gap_validation()
    assert state["status"] == "pending_remeasurement"
    assert "established_negative_result" in state
    with pytest.raises(backend.HTTPException) as exc:
        backend._gap_file("confirmed.json")
    assert "python -m gapfinder.grid --emit" in exc.value.detail


def test_scope_uses_actual_saved_map_dimensions():
    import app as backend
    scope = backend._gap_scope_info({"n_papers": 123, "problems": [{}, {}], "methods": [{}]})
    assert "123 PubMed" in scope["corpus"]
    assert "2 disease x 1" in scope["vocabulary"]


def test_unscoped_historical_integrity_is_not_labelled_as_current_verification(tmp_path, monkeypatch):
    import app as backend
    monkeypatch.setattr(backend, "DATA", tmp_path)
    (tmp_path / "integrity_check.json").write_text(json.dumps({"checked": 30, "titles_match": 30}))
    result = backend.gap_integrity()
    assert result["checked"] == 30
    assert result["status"] == "legacy_unscoped" and result["ok"] is None


def test_default_snapshot_matches_served_map_and_preserves_cache_caveat(client):
    import hashlib
    import app as backend
    saved = json.loads((backend.DATA / "snapshot.json").read_text(encoding="utf-8"))
    grid_response = client.get("/api/gap/grid").json()
    scope = client.get("/api/gap/scope").json()
    assert grid_response["n_papers"] == saved["papers"] == 80025
    assert scope["cells_checked"] == saved["cells_checked"] == 534
    assert scope["confirmed_gaps"] == saved["candidate_pairs"] == 425
    assert scope["validated"] is False
    assert scope["snapshot"]["retrieved_on"] == "2026-10-30"
    assert saved["pairing_counts"]["cached_pairs"] == 533
    assert saved["pairing_counts"]["newly_queried_pairs"] == 1
    assert "no per-pair timestamps" in saved["pairing_counts"]["note"]
    assert hashlib.sha256((backend.DATA / "grid.json").read_bytes()).hexdigest() == saved["grid_sha256"]
    assert client.get("/pipeline").status_code == 404
