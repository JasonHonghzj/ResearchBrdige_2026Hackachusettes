"""Build a source/demo ZIP without local settings, history or review runtimes."""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {".kiro", "docs", "data", "gapfinder", "researchbridge",
               "scripts", "starter", "static", "tests"}
ROOT_FILES = {".env.example", ".gitattributes", ".gitignore", "run.cmd"}
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}


def build_archive(root: Path = ROOT, output: Path | None = None) -> Path:
    root = root.resolve()
    output = output or root / "output" / "researchbridge-clean.zip"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            rel = path.relative_to(root)
            if any(part in SKIP_PARTS for part in rel.parts):
                continue
            if rel.name.startswith(".env") and rel.name != ".env.example":
                continue
            if len(rel.parts) == 1:
                if not (rel.name in ROOT_FILES or rel.suffix in {".md", ".py"}
                        or rel.name.startswith("requirements") and rel.suffix == ".txt"):
                    continue
            elif rel.parts[0] not in DIRECTORIES:
                continue
            if rel.parts[0] == "data" and (rel.name.startswith("corpus_")
                                           or rel.name == "check_cache.json"):
                continue
            if rel.suffix in {".pyc", ".log", ".tmp"}:
                continue
            archive.write(path, "ResearchBridge/" + rel.as_posix())
    temporary.replace(output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Destination ZIP (default: output/researchbridge-clean.zip)")
    args = parser.parse_args()
    result = build_archive(output=args.output)
    print(f"Created {result} ({result.stat().st_size:,} bytes)")
