import zipfile

from project_config import load_local_env
from scripts.package_project import build_archive


def test_local_env_loads_settings_but_preserves_process_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("RESEARCHBRIDGE_TEST_SETTING=file\nRESEARCHBRIDGE_TEST_PRIORITY=file\n")
    monkeypatch.delenv("RESEARCHBRIDGE_TEST_SETTING", raising=False)
    monkeypatch.setenv("RESEARCHBRIDGE_TEST_PRIORITY", "process")
    assert load_local_env(env_file)
    import os
    assert os.environ["RESEARCHBRIDGE_TEST_SETTING"] == "file"
    assert os.environ["RESEARCHBRIDGE_TEST_PRIORITY"] == "process"
    monkeypatch.delenv("RESEARCHBRIDGE_TEST_SETTING")


def test_clean_package_keeps_demo_sources_and_excludes_local_artifacts(tmp_path):
    root = tmp_path / "project"
    included = ["app.py", "README.md", "project_config.py", ".env.example",
                "data/grid.json", "starter/pubmed/data.csv", "static/bridge.js",
                "docs/VERIFICATION.md"]
    excluded = [".env", ".env.local", ".git/config", "data/corpus_past_full.json",
                "data/corpus_past_full.meta.json", "data/check_cache.json",
                "output/video-review/tool.exe", "gapfinder/__pycache__/fetch.pyc"]
    for name in included + excluded:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("example")
    output = build_archive(root)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {"ResearchBridge/" + name for name in included}
