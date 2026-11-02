"""Serve a generated Map snapshot without replacing the historical demo files."""
from __future__ import annotations

import argparse
from importlib import import_module
import json
from pathlib import Path


REQUIRED_FILES = {
    "grid.json": dict,
    "gaps.json": dict,
    "confirmed.json": list,
    "validation.json": dict,
    "provenance.json": list,
}


def snapshot_directory(path: Path) -> Path:
    directory = path.expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f"Snapshot directory does not exist: {directory}")
    missing = [name for name in REQUIRED_FILES if not (directory / name).is_file()]
    if missing:
        raise ValueError(f"Snapshot is incomplete; missing: {', '.join(missing)}")
    for name, expected_type in REQUIRED_FILES.items():
        try:
            payload = json.loads((directory / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError(f"{name} must contain readable, valid JSON: {exc}") from exc
        if not isinstance(payload, expected_type):
            raise ValueError(f"{name} must contain a JSON {expected_type.__name__}")
    return directory


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Port must be an integer from 1 to 65535") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be an integer from 1 to 65535")
    return port


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=(
        "Serve isolated generated Map data on localhost without replacing demo files. "
        "The immediate Check cache and Library retain the main project's sources. "
        "integrity_check.json is optional; its endpoint returns 503 when absent."
    ))
    parser.add_argument("--data-dir", required=True, type=Path,
                        help="Directory containing grid, gaps, confirmed, validation and provenance JSON")
    parser.add_argument("--port", type=_port, default=8001)
    args = parser.parse_args(argv)
    try:
        directory = snapshot_directory(args.data_dir)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    # Pass the configured application object to Uvicorn so a second import cannot
    # silently restore the historical DATA directory.
    backend = import_module("app")
    uvicorn = import_module("uvicorn")
    backend.DATA = directory
    backend._confirmed.cache_clear()
    print(f"Serving isolated Map data from {directory}", flush=True)
    uvicorn.run(backend.app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
