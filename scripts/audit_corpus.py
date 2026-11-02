"""Audit a new verified retrieval without replacing the saved demonstration.

Run from the repository root with ``python -m scripts.audit_corpus --help``.
The default is offline. Live spot checks and an isolated emit require explicit
flags; --audit-only suppresses both even when those flags are supplied.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from gapfinder import fetch


ROOT = Path(__file__).resolve().parents[1]
SAVED_DATA = ROOT / "data"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_source(path: Path) -> dict:
    return {"path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_json(path: Path, value) -> None:
    fetch._atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def coverage(rows: dict) -> dict:
    n = len(rows)
    abstracts = sum(bool(str(row.get("abstract") or "").strip()) for row in rows.values())
    mesh = sum(bool(row.get("mesh")) for row in rows.values())
    return {"papers": n, "with_abstract": abstracts, "with_mesh": mesh,
            "abstract_coverage": round(abstracts / n, 6) if n else None,
            "mesh_coverage": round(mesh / n, 6) if n else None}


def audit_sources(corpus_dir: Path, saved_data_dir: Path = SAVED_DATA) -> dict:
    """Verify raw manifests, then report the same merge and scope as production."""
    corpus_dir, saved_data_dir = Path(corpus_dir).resolve(), Path(saved_data_dir).resolve()
    windows, sources = {}, []
    for window, years in fetch.WINDOW_YEARS.items():
        path = corpus_dir / f"corpus_{window}_full.json"
        rows, manifest = fetch._validated_cache(path, topic_query=fetch.TOPIC, years=years)
        windows[window] = rows
        sources.append({"window": window, "corpus": file_source(path),
                        "manifest": file_source(fetch._manifest_path(path)),
                        "retrieved_utc": manifest["retrieved_utc"],
                        "search_slices": [{"year": int(year), "available_count": stats["available_count"],
                                           "requested_count": stats["requested_count"],
                                           "retrieved_count": stats["retrieved_count"]}
                                          for year, stats in manifest["per_year"].items()],
                        "raw_coverage": coverage(rows)})
    past_ids, future_ids = set(windows["past"]), set(windows["future"])
    overlap = past_ids & future_ids
    conflicts = sorted(pmid for pmid in overlap if windows["past"][pmid] != windows["future"][pmid])
    merged = {**windows["past"], **windows["future"]}
    production = fetch._dated_production(merged)
    past, future = fetch.split_strict(production, 2018)
    years = sorted({y for span in fetch.WINDOW_YEARS.values() for y in span})
    by_year = [{"year": year, **coverage({p: r for p, r in production.items() if r["year"] == year})}
               for year in years]
    excluded = [{"pmid": pmid, "year": row.get("year")}
                for pmid, row in sorted(merged.items()) if pmid not in production]

    grid_path, log_path = saved_data_dir / "grid.json", saved_data_dir / "provenance.json"
    saved_grid = json.loads(grid_path.read_text(encoding="utf-8"))
    saved_log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    if not isinstance(saved_log, list):
        raise ValueError("Saved provenance must be a JSON list")
    latest_saved = {}
    for row in saved_log:
        if row.get("cache") in {f"corpus_{w}_full.json" for w in windows}:
            latest_saved[row["cache"]] = row
    current_log = corpus_dir / "provenance.json"
    return {
        "schema_version": 1, "run_kind": "current_verified_retrieval_audit",
        "audited_utc": utc_now(), "source_integrity": "pass",
        "does_not_restore_saved_snapshot": True,
        "sources": sources,
        "current_provenance": file_source(current_log) if current_log.exists() else None,
        "topic_query": fetch.TOPIC, "journal_year_scope": [min(years), max(years)],
        "merge": {"raw_past": len(past_ids), "raw_future": len(future_ids),
                  "cross_window_duplicates": len(overlap), "overlap_pmids": sorted(overlap),
                  "conflicting_record_pmids": conflicts,
                  "duplicate_resolution": "future retrieval record wins, as in load_production",
                  "raw_union": len(merged), "raw_sum_minus_overlap": len(past_ids) + len(future_ids) - len(overlap),
                  "excluded_journal_year_records": excluded,
                  "production": len(production), "production_pmids_sha256": fetch._pmids_hash(production)},
        "production_coverage": coverage(production),
        "coverage_by_year": by_year,
        "strict_2018_split": {"build_papers": len(past), "score_papers": len(future),
                              "overlap": len(set(past) & set(future)),
                              "union_equals_production": set(past) | set(future) == set(production)},
        "saved_demo_comparison": {
            "label": "Historical saved demonstration; its original raw records are not reconstructed by this run.",
            "saved_map": file_source(grid_path), "saved_map_papers": saved_grid["n_papers"],
            "saved_provenance": file_source(log_path) if log_path.exists() else None,
            "saved_full_retrievals": [{"cache": key, "retrieved_unique": row.get("retrieved_unique"),
                                       "retrieved_utc": row.get("retrieved_utc")}
                                      for key, row in latest_saved.items()],
            "current_minus_saved_map": len(production) - saved_grid["n_papers"],
            "same_count_would_not_prove_identical_records": True,
        },
        "warnings": (["Cross-window duplicate records differ; the production merge uses the later window."]
                     if conflicts else []),
    }


@contextmanager
def corpus_source(corpus_dir: Path):
    """Redirect the original fetch functions, restoring globals even on failure."""
    before = fetch.DATA, fetch.PROVENANCE
    fetch.DATA, fetch.PROVENANCE = corpus_dir, corpus_dir / "provenance.json"
    try:
        yield
    finally:
        fetch.DATA, fetch.PROVENANCE = before


@contextmanager
def isolated_runtime(corpus_dir: Path, working: Path):
    from gapfinder import confirm, mesh
    changes = [(mesh, "DATA", working), (mesh, "TREE_CACHE", working / "mesh_trees.json"),
               (confirm, "DATA", working), (confirm, "CACHE", working / "gap_confirm.json"),
               (confirm, "CHECK_CACHE", working / "check_cache.json")]
    old = [(module, key, getattr(module, key)) for module, key, _ in changes]
    try:
        for module, key, value in changes:
            setattr(module, key, value)
        with corpus_source(corpus_dir):
            yield
    finally:
        for module, key, value in old:
            setattr(module, key, value)


def isolated_emit(corpus_dir: Path, output_dir: Path, saved_data_dir: Path, *, verbose: bool = True) -> dict:
    """Run the real emitter, using copied caches and failing fast on unavailable counts.

    Saved counts have no pair timestamps and are explicitly retained as saved
    observations. Only missing query pairs are sent to PubMed; each live count
    receives its own timestamp in live_query_log.jsonl.
    """
    from gapfinder import confirm, grid
    working, serving = output_dir / "working_data", output_dir / "serving"
    working.mkdir(parents=True, exist_ok=True)
    serving.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in ("mesh_trees.json", "gap_confirm.json"):
        original = saved_data_dir / name
        if not original.exists():
            raise FileNotFoundError(f"Required saved cache is missing: {original}")
        shutil.copyfile(original, working / name)
        copied.append(file_source(original))
    initial_counts = json.loads((working / "gap_confirm.json").read_text(encoding="utf-8"))
    if not isinstance(initial_counts, dict):
        raise ValueError("Saved confirmation cache must be a JSON object")
    query_log = output_dir / "live_query_log.jsonl"
    original_count = confirm._count

    def counted(term, **kwargs):
        value = original_count(term, **kwargs)
        with query_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"queried_utc": utc_now(), "query": term, "count": value}) + "\n")
        if value is None:
            raise RuntimeError("PubMed count unavailable; isolated emit stopped at the first failed query.")
        return value

    before_count = confirm._count
    try:
        confirm._count = counted
        with isolated_runtime(corpus_dir, working):
            emitted = grid.emit(outdir=serving, verbose=verbose)
    finally:
        confirm._count = before_count
    current_log = corpus_dir / "provenance.json"
    if current_log.exists():
        shutil.copyfile(current_log, serving / "provenance.json")
    production_check = output_dir / "spot_check_production.json"
    if production_check.exists():
        shutil.copyfile(production_check, serving / "integrity_check.json")

    g, checked = emitted["grid"], emitted["confirmed"]
    filled = {(g["problems"][i]["ui"], g["methods"][j]["ui"]) for i, j, n in g["counts"] if n > 0}
    empty = {(p["ui"], m["ui"]) for p in g["problems"] for m in g["methods"]} - filled
    actual = {(row["problem_ui"], row["method_ui"]) for row in checked}
    if actual != empty or len(checked) != len(empty):
        raise RuntimeError("Isolated serving output does not cover every empty cell exactly once")
    reused = sum(f'{row["problem"]}|{row["method"]}' in initial_counts for row in checked)
    return {"status": "pass", "scope": "Real grid.emit and serving-file consistency; HTTP/browser behavior is separate.",
            "serving_dir": str(serving.resolve()), "source_kind": "current retrieval; confirmation cache reuse recorded separately",
            "cache_time_note": "Copied saved counts have no per-pair timestamps; only missing pairs are queried in this run.",
            "all_counts_refreshed_live": bool(checked) and reused == 0, "copied_caches": copied,
            "papers": g["n_papers"], "cells": g["cells"], "filled": g["filled"],
            "empty": len(empty), "checked": len(checked), "cached_pairs": reused,
            "newly_queried_pairs": len(checked) - reused,
            "confirmed_gaps": sum(row["real_gap"] for row in checked),
            "historical_validation_status": emitted["validation"]["status"],
            "files": {p.name: file_source(p) for p in sorted(serving.iterdir()) if p.is_file()},
            "live_query_log": file_source(query_log) if query_log.exists() else None}


def _check_output(corpus_dir: Path, output_dir: Path, saved_data_dir: Path) -> None:
    protected = [corpus_dir.resolve(), saved_data_dir.resolve(), SAVED_DATA.resolve()]
    if any(output_dir == path or output_dir.is_relative_to(path) for path in protected):
        raise ValueError("Output must be outside both raw corpus and saved demonstration data directories")
    if output_dir == ROOT.resolve() or (output_dir.exists() and any(output_dir.iterdir())):
        raise ValueError("Choose a fresh audit output directory, not the repository root or a previous run")


def run_audit(corpus_dir: Path, output_dir: Path, *, saved_data_dir: Path = SAVED_DATA,
              spot_check: bool = False, emit: bool = False, audit_only: bool = False,
              seed: int = 20261030, verbose: bool = True) -> dict:
    corpus_dir, output_dir = Path(corpus_dir).resolve(), Path(output_dir).resolve()
    saved_data_dir = Path(saved_data_dir).resolve()
    _check_output(corpus_dir, output_dir, saved_data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    initial_saved = {p.name: file_source(p)["sha256"] for p in saved_data_dir.glob("*.json")}
    result = {"schema_version": 1, "started_utc": utc_now(), "run_kind": "current_retrieval_audit",
              "does_not_restore_saved_snapshot": True, "corpus_dir": str(corpus_dir),
              "output_dir": str(output_dir), "audit_only": audit_only, "spot_checks": [],
              "end_to_end": {"status": "skipped", "reason": "audit_only" if audit_only else "not_requested"}}
    try:
        audit = audit_sources(corpus_dir, saved_data_dir)
        write_json(output_dir / "corpus_audit.json", audit)
        result["source_audit"] = file_source(output_dir / "corpus_audit.json")
        with (output_dir / "coverage_by_year.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(audit["coverage_by_year"][0]))
            writer.writeheader()
            writer.writerows(audit["coverage_by_year"])
        if spot_check and not audit_only:
            with corpus_source(corpus_dir):
                for window, size in (("production", 30), ("past", 15), ("future", 15)):
                    if verbose:
                        print(f"[audit] Live {window} spot check: requested {size}", flush=True)
                    checked = fetch.spot_check(window, n=size, seed=seed)
                    name = f"spot_check_{window}.json"
                    write_json(output_dir / name, checked)
                    result["spot_checks"].append({"window": window, "status": checked["status"],
                                                 "ok": checked["ok"], "artifact": file_source(output_dir / name)})
        else:
            result["spot_checks_skipped"] = "audit_only" if audit_only else "not_requested"
        if emit and not audit_only:
            if verbose:
                print("[audit] Real isolated grid.emit; cached counts are reused and missing pairs query PubMed", flush=True)
            result["end_to_end"] = {"status": "running"}
            result["end_to_end"] = isolated_emit(corpus_dir, output_dir, saved_data_dir, verbose=verbose)
        result["status"] = "pass" if all(row["ok"] for row in result["spot_checks"]) else "failed"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
        if result["end_to_end"]["status"] == "running":
            result["end_to_end"] = {"status": "failed", "serving_not_promoted_to_demo": True}
        elif emit and not audit_only:
            result["end_to_end"] = {"status": "skipped", "reason": "prerequisite_failed"}
    finally:
        final_saved = {p.name: file_source(p)["sha256"] for p in saved_data_dir.glob("*.json")}
        result["saved_demo_json_unchanged"] = final_saved == initial_saved
        if not result["saved_demo_json_unchanged"]:
            result["status"] = "failed"
        result["completed_utc"] = utc_now()
        write_json(output_dir / "run.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", required=True, type=Path, help="Directory containing verified full corpora and manifests")
    parser.add_argument("--output-dir", required=True, type=Path, help="Fresh isolated run directory outside source/demo data")
    parser.add_argument("--saved-data-dir", type=Path, default=SAVED_DATA, help="Historical demonstration and count/tree caches")
    parser.add_argument("--spot-check", action="store_true", help="Live production 30 / past 15 / future 15 checks")
    parser.add_argument("--emit", action="store_true", help="Run the real grid.emit into output-dir/serving; missing pairs query PubMed")
    parser.add_argument("--audit-only", action="store_true", help="Offline source audit only; overrides --spot-check and --emit")
    parser.add_argument("--seed", type=int, default=20261030)
    args = parser.parse_args(argv)
    try:
        result = run_audit(args.corpus_dir, args.output_dir, saved_data_dir=args.saved_data_dir,
                           spot_check=args.spot_check, emit=args.emit, audit_only=args.audit_only, seed=args.seed)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Audit could not start: {exc}\n")
    print(f"[audit] {result['status']}: {args.output_dir.resolve() / 'run.json'}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
