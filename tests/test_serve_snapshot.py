import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import serve_snapshot


def write_snapshot(directory):
    for name, payload_type in serve_snapshot.REQUIRED_FILES.items():
        (directory / name).write_text(json.dumps(payload_type()), encoding="utf-8")


@pytest.mark.parametrize("missing", serve_snapshot.REQUIRED_FILES)
def test_missing_snapshot_file_stops_before_app_import_without_demo_fallback(tmp_path, monkeypatch, capsys, missing):
    write_snapshot(tmp_path)
    (tmp_path / missing).unlink()
    imports = Mock(side_effect=AssertionError("Invalid snapshots must not import or launch the app"))
    monkeypatch.setattr(serve_snapshot, "import_module", imports)
    with pytest.raises(SystemExit) as exc:
        serve_snapshot.main(["--data-dir", str(tmp_path)])
    assert exc.value.code == 2
    assert missing in capsys.readouterr().err
    imports.assert_not_called()


def test_malformed_json_stops_before_app_import(tmp_path, monkeypatch, capsys):
    write_snapshot(tmp_path)
    (tmp_path / "grid.json").write_text("{broken", encoding="utf-8")
    imports = Mock(side_effect=AssertionError("Malformed snapshots must not launch"))
    monkeypatch.setattr(serve_snapshot, "import_module", imports)
    with pytest.raises(SystemExit) as exc:
        serve_snapshot.main(["--data-dir", str(tmp_path)])
    assert exc.value.code == 2
    assert "grid.json must contain readable, valid JSON" in capsys.readouterr().err
    imports.assert_not_called()


@pytest.mark.parametrize("port", [None, 8766])
def test_launch_uses_resolved_snapshot_and_clears_cached_rows(tmp_path, monkeypatch, port):
    write_snapshot(tmp_path)
    cache_clear, run = Mock(), Mock()
    backend = SimpleNamespace(DATA=Path("historical-demo"), app=object(),
                              _confirmed=SimpleNamespace(cache_clear=cache_clear))
    modules = {"app": backend, "uvicorn": SimpleNamespace(run=run)}
    monkeypatch.setattr(serve_snapshot, "import_module", modules.__getitem__)
    args = ["--data-dir", str(tmp_path / ".." / tmp_path.name)]
    if port is not None:
        args += ["--port", str(port)]
    serve_snapshot.main(args)
    assert backend.DATA == tmp_path.resolve()
    cache_clear.assert_called_once_with()
    run.assert_called_once_with(backend.app, host="127.0.0.1", port=port or 8001)
    # Optional integrity metadata is not needed to launch this Map snapshot.
    assert not (tmp_path / "integrity_check.json").exists()
