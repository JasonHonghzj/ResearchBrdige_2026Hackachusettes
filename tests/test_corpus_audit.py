"""Offline checks of new-run audits and isolation around the real emitter."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from gapfinder import confirm, fetch, mesh
from scripts import audit_corpus as audit


def dump(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def row(pmid, year, kind="problem"):
    return {"year": year, "title": f"Paper {pmid}", "journal": "J",
            "abstract": "Abstract." if int(pmid) % 2 else "",
            "mesh": [["D1", "Disease", "N"]] if kind == "problem" else [["D2", "Method", "N"]]}


def verified_window(directory, window, records):
    cache = directory / f"corpus_{window}_full.json"
    dump(cache, records)
    years = list(fetch.WINDOW_YEARS[window])
    slices = {}
    for index, year in enumerate(years):
        ids = sorted(records) if index == 0 else []
        slices[str(year)] = {"available_count": len(ids), "requested_count": len(ids),
                             "retrieved_count": len(ids), "pmids": ids,
                             "pmids_sha256": fetch._pmids_hash(ids)}
    dump(fetch._manifest_path(cache), {
        "schema_version": 1, "complete": True, "cache": cache.name,
        "topic_query": fetch.TOPIC, "year_slices": years, "per_year": slices,
        "requested_unique_count": len(records), "retrieved_unique": len(records),
        "requested_pmids_sha256": fetch._pmids_hash(records),
        "corpus_sha256": hashlib.sha256(cache.read_bytes()).hexdigest(),
        "retrieved_utc": "2026-10-30T12:00:00Z"})


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    raw, saved = tmp_path / "raw", tmp_path / "saved"
    raw.mkdir()
    saved.mkdir()
    past = {str(i): row(str(i), 2018) for i in range(1, 71)}
    past["141"] = row("141", 2004)
    future = {str(i): row(str(i), 2020, "method") for i in range(71, 141)}
    future["1"] = past["1"]  # the merge must deduplicate this electronic/print boundary record
    future["142"] = row("142", 2027)
    verified_window(raw, "past", past)
    verified_window(raw, "future", future)
    dump(raw / "provenance.json", [{"cache": "new retrieval", "retrieved_utc": "2026-10-30T12:00:00Z"}])
    dump(saved / "grid.json", {"n_papers": 79940})
    dump(saved / "provenance.json", [{"cache": "corpus_past_full.json", "retrieved_unique": 44156,
                                      "retrieved_utc": "2026-10-24T19:56:38Z"}])
    dump(saved / "gap_confirm.json", {"Disease|Method": {"maturity": 10, "gap_papers": 0}})
    dump(saved / "mesh_trees.json", {"D1": ["C01.100"], "D2": ["E05.393.100"]})
    monkeypatch.setattr(fetch, "_get", lambda *a, **kw: pytest.fail("unexpected PubMed request"))
    monkeypatch.setattr(confirm, "_count", lambda *a, **kw: pytest.fail("unexpected count query"))
    monkeypatch.setattr(mesh._session, "get", lambda *a, **kw: pytest.fail("unexpected MeSH request"))
    monkeypatch.setattr(fetch.time, "sleep", lambda *_a: None)
    return raw, saved, {**past, **future}


def test_audit_reconciles_dedup_scope_coverage_and_historical_baseline(inputs):
    raw, saved, _ = inputs
    result = audit.audit_sources(raw, saved)
    assert result["source_integrity"] == "pass"
    assert result["run_kind"] == "current_verified_retrieval_audit"
    assert result["does_not_restore_saved_snapshot"] is True
    assert result["merge"]["raw_past"] == 71
    assert result["merge"]["raw_future"] == 72
    assert result["merge"]["cross_window_duplicates"] == 1
    assert result["merge"]["raw_union"] == result["merge"]["raw_sum_minus_overlap"] == 142
    assert result["merge"]["production"] == 140
    assert {r["year"] for r in result["merge"]["excluded_journal_year_records"]} == {2004, 2027}
    assert result["strict_2018_split"] == {"build_papers": 70, "score_papers": 70,
                                           "overlap": 0, "union_equals_production": True}
    years = {r["year"]: r for r in result["coverage_by_year"]}
    assert len(years) == 22
    assert years[2018]["papers"] == years[2020]["papers"] == 70
    assert years[2018]["abstract_coverage"] == 0.5
    assert years[2020]["mesh_coverage"] == 1
    assert years[2005]["abstract_coverage"] is None
    assert result["saved_demo_comparison"]["saved_map_papers"] == 79940
    assert result["saved_demo_comparison"]["current_minus_saved_map"] == 140 - 79940
    assert len(result["sources"]) == 2
    assert all(len(source["corpus"]["sha256"]) == 64 for source in result["sources"])


def test_default_and_audit_only_do_not_use_network_or_emit(inputs, tmp_path, monkeypatch):
    raw, saved, _ = inputs
    monkeypatch.setattr(audit, "isolated_emit", lambda *a, **kw: pytest.fail("emit must be skipped"))
    monkeypatch.setattr(fetch, "spot_check", lambda *a, **kw: pytest.fail("live check must be skipped"))
    out = tmp_path / "audit"
    result = audit.run_audit(raw, out, saved_data_dir=saved, emit=True, spot_check=True, audit_only=True)
    assert result["status"] == "pass" and result["saved_demo_json_unchanged"] is True
    assert result["end_to_end"]["status"] == "skipped"
    assert result["end_to_end"]["reason"] == "audit_only"
    assert result["spot_checks_skipped"] == "audit_only"
    assert (out / "coverage_by_year.csv").is_file()
    assert json.loads((out / "run.json").read_text())["does_not_restore_saved_snapshot"] is True


def xml_response(records, ids):
    articles = []
    for pmid in ids:
        item = records[pmid]
        ui, name, _ = item["mesh"][0]
        articles.append(f'<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article>'
                        f'<ArticleTitle>{item["title"]}</ArticleTitle><Journal><JournalIssue><PubDate>'
                        f'<Year>{item["year"]}</Year></PubDate></JournalIssue></Journal></Article>'
                        f'<MeshHeadingList><MeshHeading><DescriptorName UI="{ui}">{name}</DescriptorName>'
                        '</MeshHeading></MeshHeadingList></MedlineCitation></PubmedArticle>')
    return SimpleNamespace(text="<PubmedArticleSet>" + "".join(articles) + "</PubmedArticleSet>")


def test_real_spot_check_uses_isolated_source_and_writes_three_artifacts(inputs, tmp_path, monkeypatch):
    raw, saved, records = inputs
    requests = []
    before = fetch.DATA, fetch.PROVENANCE
    def fake_get(endpoint, **kwargs):
        assert fetch.DATA == raw
        ids = kwargs["id"].split(",")
        requests.append(ids)
        return xml_response(records, ids)
    monkeypatch.setattr(fetch, "_get", fake_get)
    out = tmp_path / "spot-audit"
    result = audit.run_audit(raw, out, saved_data_dir=saved, spot_check=True, seed=123, verbose=False)
    assert result["status"] == "pass"
    assert [len(ids) for ids in requests] == [30, 15, 15]
    assert (fetch.DATA, fetch.PROVENANCE) == before
    for window, n in (("production", 30), ("past", 15), ("future", 15)):
        data = json.loads((out / f"spot_check_{window}.json").read_text())
        assert data["ok"] is True and data["checked"] == n
        assert data["seed"] == 123 and len(data["sampled_pmids"]) == n
        assert all(Path(s["path"]).parent == raw for s in data["sources"])


def test_spot_check_failure_is_recorded_as_failed_run(inputs, tmp_path, monkeypatch):
    raw, saved, _ = inputs
    monkeypatch.setattr(fetch, "_get", lambda *a, **kw: None)
    result = audit.run_audit(raw, tmp_path / "unavailable", saved_data_dir=saved, spot_check=True, verbose=False)
    assert result["status"] == "failed"
    assert all(check["ok"] is False for check in result["spot_checks"])
    assert result["saved_demo_json_unchanged"] is True


def test_real_emit_uses_copied_caches_without_touching_originals(inputs, tmp_path):
    raw, saved, _ = inputs
    before = fetch.DATA, fetch.PROVENANCE, confirm.CACHE, confirm.CHECK_CACHE, mesh.TREE_CACHE
    original_bytes = {p.name: p.read_bytes() for p in saved.iterdir()}
    out = tmp_path / "emit-audit"
    result = audit.run_audit(raw, out, saved_data_dir=saved, emit=True, verbose=False)
    assert result["status"] == "pass", result.get("error")
    assert result["saved_demo_json_unchanged"] is True
    emitted = result["end_to_end"]
    assert emitted["status"] == "pass" and emitted["papers"] == 140
    assert emitted["checked"] == emitted["empty"] == emitted["cached_pairs"] == 1
    assert emitted["newly_queried_pairs"] == 0
    assert emitted["all_counts_refreshed_live"] is False
    assert emitted["historical_validation_status"] == "pending_remeasurement"
    assert json.loads((out / "serving" / "provenance.json").read_text())[0]["cache"] == "new retrieval"
    assert {p.name: p.read_bytes() for p in saved.iterdir()} == original_bytes
    assert (fetch.DATA, fetch.PROVENANCE, confirm.CACHE, confirm.CHECK_CACHE, mesh.TREE_CACHE) == before


def test_emit_stops_at_first_unavailable_missing_pair_and_restores_globals(inputs, tmp_path, monkeypatch):
    raw, saved, _ = inputs
    dump(saved / "gap_confirm.json", {})
    before = fetch.DATA, confirm.CACHE, mesh.TREE_CACHE
    queries = []
    def unavailable(term, **kwargs):
        queries.append(term)
        return None
    monkeypatch.setattr(confirm, "_count", unavailable)
    out = tmp_path / "failed-emit"
    result = audit.run_audit(raw, out, saved_data_dir=saved, emit=True, verbose=False)
    assert result["status"] == result["end_to_end"]["status"] == "failed"
    assert len(queries) == 1
    assert "first failed query" in result["error"]["message"]
    assert not (out / "serving" / "grid.json").exists()
    assert (fetch.DATA, confirm.CACHE, mesh.TREE_CACHE) == before
    assert len((out / "live_query_log.jsonl").read_text().splitlines()) == 1


def test_missing_pair_success_records_both_live_queries_and_isolated_cache(inputs, tmp_path, monkeypatch):
    raw, saved, _ = inputs
    dump(saved / "gap_confirm.json", {})
    replies = iter([11, 1])
    monkeypatch.setattr(confirm, "_count", lambda *a, **kw: next(replies))
    out = tmp_path / "new-pair"
    result = audit.run_audit(raw, out, saved_data_dir=saved, emit=True, verbose=False)
    assert result["status"] == "pass", result.get("error")
    assert result["end_to_end"]["cached_pairs"] == 0
    assert result["end_to_end"]["newly_queried_pairs"] == 1
    assert result["end_to_end"]["all_counts_refreshed_live"] is True
    events = [json.loads(line) for line in (out / "live_query_log.jsonl").read_text().splitlines()]
    assert [event["count"] for event in events] == [11, 1]
    assert all(event["queried_utc"] for event in events)
    assert json.loads((saved / "gap_confirm.json").read_text()) == {}
    assert json.loads((out / "working_data" / "gap_confirm.json").read_text())["Disease|Method"] == {
        "maturity": 11, "gap_papers": 1}


def test_tampered_source_is_failure_not_end_to_end_claim(inputs, tmp_path):
    raw, saved, _ = inputs
    (raw / "corpus_past_full.json").write_text("{}")
    out = tmp_path / "invalid"
    result = audit.run_audit(raw, out, saved_data_dir=saved, emit=True)
    assert result["status"] == "failed"
    assert result["error"]["type"] == "CorpusIntegrityError"
    assert result["end_to_end"] == {"status": "skipped", "reason": "prerequisite_failed"}
    assert not (out / "corpus_audit.json").exists()
    assert (out / "run.json").is_file()


def test_output_cannot_write_raw_saved_or_previous_run(inputs, tmp_path):
    raw, saved, _ = inputs
    for out in (raw, raw / "child", saved):
        with pytest.raises(ValueError, match="outside"):
            audit.run_audit(raw, out, saved_data_dir=saved)
    out = tmp_path / "previous"
    out.mkdir()
    dump(out / "run.json", {"previous": True})
    with pytest.raises(ValueError, match="fresh"):
        audit.run_audit(raw, out, saved_data_dir=saved)
    assert json.loads((out / "run.json").read_text()) == {"previous": True}
