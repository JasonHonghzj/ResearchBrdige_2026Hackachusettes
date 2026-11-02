"""Package the current local raw corpus and its matching serving/audit snapshot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "ResearchBridgeCorpus/"
REQUIRED = (
    "corpus_past_full.json", "corpus_past_full.meta.json",
    "corpus_future_full.json", "corpus_future_full.meta.json",
    "provenance.json", "grid.json", "snapshot.json", "confirmed.json",
    "validation.json", "audit/corpus_audit.json", "audit/history-evaluation.json",
)


def package_run(data_dir: Path, output: Path) -> dict:
    data_dir, output = data_dir.resolve(), output.resolve()
    if output.is_relative_to(data_dir):
        raise ValueError("Archive must be outside the source data directory")
    for name in REQUIRED:
        if not (data_dir / name).is_file():
            raise ValueError(f"Current snapshot is missing {name}")
    audit = json.loads((data_dir / "audit/corpus_audit.json").read_text(encoding="utf-8"))
    snapshot = json.loads((data_dir / "snapshot.json").read_text(encoding="utf-8"))
    grid_bytes = (data_dir / "grid.json").read_bytes()
    grid = json.loads(grid_bytes)
    if audit.get("source_integrity") != "pass":
        raise ValueError("Source integrity audit must pass before packaging")
    if (snapshot["papers"] != grid["n_papers"]
            or audit["merge"]["production"] != snapshot["papers"]
            or snapshot["grid_sha256"] != hashlib.sha256(grid_bytes).hexdigest()):
        raise ValueError("Snapshot, grid and audited production do not agree")
    for window in ("past", "future"):
        path = data_dir / f"corpus_{window}_full.json"
        meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta["corpus_sha256"]:
            raise ValueError(f"Raw corpus hash mismatch: {window}")

    sources = {}
    for path in sorted(data_dir.rglob("*")):
        rel = path.relative_to(data_dir)
        if (not path.is_file() or path.is_symlink()
                or any(part in {"__pycache__", ".pytest_cache", "bridge"} for part in rel.parts)
                or path.suffix in {".pyc", ".tmp", ".log"}
                or path.name == "check_cache.json"):
            continue
        if not path.resolve().is_relative_to(data_dir):
            raise ValueError(f"Source escapes data directory: {rel}")
        sources["data/" + rel.as_posix()] = path
    sources["docs/VERIFICATION.md"] = ROOT / "docs/VERIFICATION.md"
    entries = []
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, path in sorted(sources.items()):
            contents = path.read_bytes()
            entries.append({"path": name, "bytes": len(contents),
                            "sha256": hashlib.sha256(contents).hexdigest()})
            archive.writestr(PREFIX + name, contents)
        manifest = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "kind": "current_corpus_serving_and_audit_snapshot",
            "snapshot": snapshot,
            "restore": "Copy data/ into the companion source checkout; large corpus files stay Git-ignored. Install dependencies before starting run.cmd.",
            "entries": entries,
        }
        archive.writestr(PREFIX + "CONTENTS.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    with zipfile.ZipFile(temporary) as archive:
        corrupt = archive.testzip()
        if corrupt:
            raise ValueError(f"ZIP CRC failure: {corrupt}")
        for entry in entries:
            contents = archive.read(PREFIX + entry["path"])
            if len(contents) != entry["bytes"] or hashlib.sha256(contents).hexdigest() != entry["sha256"]:
                raise ValueError(f"Archive content mismatch: {entry['path']}")
    temporary.replace(output)
    return {"path": str(output), "bytes": output.stat().st_size,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "entries": len(entries) + 1, "crc": "pass", "member_hashes": "pass"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output", type=Path, default=ROOT / "output/researchbridge-corpus.zip")
    args = parser.parse_args()
    print(json.dumps(package_run(args.data_dir, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
