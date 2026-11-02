"""Offline regression checks for production retrieval and its audit trail."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from gapfinder import fetch, mesh, phrases


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "DATA", tmp_path)
    monkeypatch.setattr(fetch, "PROVENANCE", tmp_path / "provenance.json")
    monkeypatch.setattr(fetch.time, "sleep", lambda _seconds: None)
    # Every test must opt in to a stubbed response; accidental HTTP is a failure.
    monkeypatch.setattr(fetch, "_get", lambda *a, **kw: pytest.fail("unexpected network request"))
    return tmp_path


def search(ids, count=None):
    return SimpleNamespace(json=lambda: {"esearchresult": {
        "idlist": ids, "count": str(len(ids) if count is None else count)}})


def record(pmid, year=2018, title="Original title"):
    return (f'<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article>'
            f'<ArticleTitle>{title}</ArticleTitle><Journal><JournalIssue><PubDate>'
            f'<Year>{year}</Year></PubDate></JournalIssue><ISOAbbreviation>J</ISOAbbreviation>'
            '</Journal><Abstract><AbstractText>Source abstract.</AbstractText></Abstract></Article>'
            '<MeshHeadingList><MeshHeading><DescriptorName UI="D1" MajorTopicYN="N">'
            'Disease</DescriptorName></MeshHeading></MeshHeadingList></MedlineCitation></PubmedArticle>')


def response(*articles):
    return SimpleNamespace(text="<PubmedArticleSet>" + "".join(articles) + "</PubmedArticleSet>")


def scripted(monkeypatch, replies):
    replies = iter(replies)
    monkeypatch.setattr(fetch, "_get", lambda *a, **kw: next(replies))


def build_cache(monkeypatch, years, cache="corpus_past_full.json", ids=None):
    ids = ids or ["1"]
    replies = []
    for year in years:
        replies.extend([search(ids), response(*(record(p, year=year) for p in ids))])
    scripted(monkeypatch, replies)
    return fetch.fetch_years(fetch.TOPIC, years, cache, refresh=True)


def test_complete_cache_reconciles_dedupes_and_can_be_reused(isolated, monkeypatch):
    rows = build_cache(monkeypatch, range(2017, 2019))
    assert set(rows) == {"1"}
    cache = isolated / "corpus_past_full.json"
    meta = json.loads(cache.with_suffix(".meta.json").read_text())
    assert meta["complete"] is True
    assert meta["requested_unique_count"] == 1
    assert meta["corpus_sha256"] == hashlib.sha256(cache.read_bytes()).hexdigest()
    assert set(meta["per_year"]) == {"2017", "2018"}
    assert meta["per_year"]["2017"]["pmids"] == ["1"]
    monkeypatch.setattr(fetch, "_get", lambda *a, **kw: pytest.fail("verified hit must stay offline"))
    assert fetch.fetch_years(fetch.TOPIC, range(2017, 2019), cache.name) == rows


@pytest.mark.parametrize("replies", [
    [None],
    [search(["1"], count=2)],
    [search(["1", "1"], count=2)],
    [search(["1"]), None],
    [search(["1", "2"]), response(record("1"))],
    [search(["1"]), SimpleNamespace(text="<broken")],
    [search(["1"]), response(record("2"))],
])
def test_incomplete_attempt_never_replaces_cache_or_logs_complete(isolated, monkeypatch, replies):
    build_cache(monkeypatch, range(2018, 2019))
    before = {p.name: p.read_bytes() for p in isolated.iterdir()}
    scripted(monkeypatch, replies)
    with pytest.raises(fetch.CorpusIntegrityError):
        fetch.fetch_years(fetch.TOPIC, range(2018, 2019), "corpus_past_full.json", refresh=True)
    assert {p.name: p.read_bytes() for p in isolated.iterdir()} == before


def test_failure_after_an_earlier_successful_batch_preserves_official_cache(isolated, monkeypatch):
    build_cache(monkeypatch, range(2018, 2019))
    before = {p.name: p.read_bytes() for p in isolated.iterdir()}
    ids = [str(i) for i in range(1, 202)]
    scripted(monkeypatch, [search(ids), response(*(record(p) for p in ids[:200])), None])
    with pytest.raises(fetch.CorpusIntegrityError):
        fetch.fetch_years(fetch.TOPIC, range(2018, 2019), "corpus_past_full.json", refresh=True)
    assert {p.name: p.read_bytes() for p in isolated.iterdir()} == before


def test_failed_initial_fetch_does_not_create_full_cache(isolated, monkeypatch):
    scripted(monkeypatch, [search(["1"]), None])
    with pytest.raises(fetch.CorpusIntegrityError):
        fetch.fetch_years(fetch.TOPIC, range(2018, 2019), "corpus_past_full.json")
    assert list(isolated.iterdir()) == []


@pytest.mark.parametrize("tamper", ["bytes", "year", "pmids", "query"])
def test_cache_identity_and_reconciliation_are_checked(isolated, monkeypatch, tamper):
    build_cache(monkeypatch, range(2018, 2019))
    cache = isolated / "corpus_past_full.json"
    manifest = cache.with_suffix(".meta.json")
    meta = json.loads(manifest.read_text())
    if tamper == "bytes":
        cache.write_text("{}")
    elif tamper == "year":
        meta["per_year"] = {}
    elif tamper == "pmids":
        meta["per_year"]["2018"]["pmids"] = ["2"]
    else:
        meta["topic_query"] = "another query"
    manifest.write_text(json.dumps(meta))
    with pytest.raises(fetch.CorpusIntegrityError, match="--refresh"):
        fetch.fetch_years(fetch.TOPIC, range(2018, 2019), cache.name)


def test_legacy_caches_are_preserved_and_refused_as_complete(isolated):
    full = isolated / "corpus_past_full.json"
    full.write_text("{}")
    with pytest.raises(fetch.CorpusIntegrityError, match="--refresh"):
        fetch.fetch_years(fetch.TOPIC, range(2005, 2019), full.name)
    assert full.read_text() == "{}"
    full.unlink()
    (isolated / "corpus_past.json").write_text("{}")
    with pytest.raises(FileNotFoundError, match="legacy"):
        fetch.load_production()


def test_provenance_appends_history_and_refuses_corrupt_log(isolated):
    fetch._record_provenance({"cache": "same.json", "attempt": 1})
    fetch._record_provenance({"cache": "same.json", "attempt": 2})
    assert [r["attempt"] for r in fetch.provenance()] == [1, 2]
    fetch.PROVENANCE.write_text("invalid JSON")
    with pytest.raises(fetch.CorpusIntegrityError):
        fetch._record_provenance({"attempt": 3})
    assert fetch.PROVENANCE.read_text() == "invalid JSON"


def test_any_cutoff_splits_same_merged_corpus(monkeypatch):
    all_rows = {str(y): {"year": y} for y in range(2017, 2022)}
    monkeypatch.setattr(fetch, "_production_snapshot", lambda: (all_rows, []))
    for cutoff in (2017, 2018, 2020):
        past = fetch.load_corpus("past", cutoff)
        future = fetch.load_corpus("future", cutoff)
        assert set(past).isdisjoint(future)
        assert set(past) | set(future) == set(all_rows)
        assert all(r["year"] <= cutoff for r in past.values())
        assert all(r["year"] > cutoff for r in future.values())
    with pytest.raises(ValueError):
        fetch.load_corpus("misspelled")


@pytest.fixture
def production_cache(isolated, monkeypatch):
    monkeypatch.setattr(fetch, "WINDOW_YEARS", {"past": range(2018, 2019), "future": range(2019, 2020)})
    build_cache(monkeypatch, range(2018, 2019), ids=["1", "2"])
    build_cache(monkeypatch, range(2019, 2020), "corpus_future_full.json", ids=["3"])
    # A corrupt capped legacy file must never be used for the production check.
    (isolated / "corpus_past.json").write_text("invalid legacy file")
    return isolated


def test_production_requires_both_verified_windows(production_cache):
    assert set(fetch.load_production()) == {"1", "2", "3"}
    # A later cutoff must include records originally retrieved in the future file.
    assert set(fetch.load_corpus("past", cutoff=2019)) == {"1", "2", "3"}
    assert fetch.load_corpus("future", cutoff=2019) == {}
    (production_cache / "corpus_future_full.json").unlink()
    with pytest.raises(FileNotFoundError):
        fetch.load_production()


def test_production_excludes_journal_years_outside_retrieval_scope(isolated, monkeypatch):
    # Per-year [dp] can match electronic dates although the stored journal year
    # is outside 2005-2026. Keep raw retrieval reconciliation, filter the view.
    def fake_read(window):
        years = [2004, 2005, 2026, 2027, None] if window == "past" else []
        rows = {str(i): {"year": year} for i, year in enumerate(years)}
        cache = isolated / (window + ".json")
        cache.with_suffix(".meta.json").write_text("{}")
        return rows, {"corpus_sha256": "raw-hash", "retrieved_utc": "snapshot-time"}, cache
    monkeypatch.setattr(fetch, "_read_window", fake_read)
    assert {r["year"] for r in fetch.load_production().values()} == {2005, 2026}


def test_spot_check_identifies_sources_sample_and_result(production_cache, monkeypatch):
    scripted(monkeypatch, [response(record("1"), record("2"))])
    out = fetch.spot_check("past", n=2, seed=7)
    assert out["status"] == "pass" and out["ok"] is True
    assert out["checked"] == out["sample_size"] == 2
    assert out["seed"] == 7 and set(out["sampled_pmids"]) == {"1", "2"}
    assert out["missing_pmids"] == out["mismatches"] == []
    assert len(out["sources"]) == 2
    for source in out["sources"]:
        assert source["sha256"] == hashlib.sha256((production_cache / source["cache"]).read_bytes()).hexdigest()
        assert len(source["metadata_sha256"]) == 64
    assert out["started_utc"] and out["verified_utc"]


@pytest.mark.parametrize("reply,status,checked", [
    (None, "unavailable", 0),
    (response(record("1")), "fail", 1),
    (response(record("1", title="Changed title"), record("2")), "fail", 2),
])
def test_spot_check_failures_cannot_pass(production_cache, monkeypatch, reply, status, checked):
    scripted(monkeypatch, [reply])
    out = fetch.spot_check("past", n=2)
    assert out["status"] == status and out["ok"] is False
    assert out["checked"] == checked


def test_empty_spot_check_is_not_a_pass(monkeypatch):
    monkeypatch.setattr(fetch, "_production_snapshot", lambda: ({}, []))
    out = fetch.spot_check("production", n=30)
    assert out["status"] == "fail" and out["ok"] is False
    assert out["sample_size"] == out["checked"] == 0


def test_fetch_cli_uses_full_year_slices(monkeypatch):
    calls = []
    def fake(topic, years, cache, refresh=False):
        calls.append((topic, list(years), cache, refresh))
        return {}
    monkeypatch.setattr(fetch, "fetch_years", fake)
    assert fetch.main(["--refresh"]) == 0
    assert [(c[1], c[2], c[3]) for c in calls] == [
        (list(range(2005, 2019)), "corpus_past_full.json", True),
        (list(range(2019, 2027)), "corpus_future_full.json", True),
    ]


def test_fetch_cli_can_keep_a_new_retrieval_separate_from_demo(tmp_path, monkeypatch):
    original = tmp_path / "demo"
    original.mkdir()
    (original / "grid.json").write_text("saved demo")
    monkeypatch.setattr(fetch, "DATA", original)
    monkeypatch.setattr(fetch, "PROVENANCE", original / "provenance.json")
    output = tmp_path / "new-run"
    destinations = []
    def fake(topic, years, cache, refresh=False):
        destinations.append((fetch.DATA, fetch.PROVENANCE, cache))
        return {}
    monkeypatch.setattr(fetch, "fetch_years", fake)
    assert fetch.main(["--data-dir", str(output)]) == 0
    assert len(destinations) == 2
    assert all(data == output and log == output / "provenance.json"
               for data, log, _ in destinations)
    assert list(original.iterdir()) == [original / "grid.json"]
    assert (original / "grid.json").read_text() == "saved demo"


@pytest.mark.parametrize("module", [mesh, phrases])
def test_axis_clis_share_production_source_and_options(monkeypatch, module):
    corpus, seen = {"1": {"year": 2020}}, []
    monkeypatch.setattr(fetch, "load_production", lambda: corpus)
    def fake(rows, **options):
        seen.append((rows, options))
        return [], [], {}, {}, {}
    monkeypatch.setattr(mesh, "build_axes", fake)
    assert module.main() == 0
    assert seen == [(corpus, {"min_problem": 60, "min_method": 40, "n_problems": 50, "n_methods": 32})]
