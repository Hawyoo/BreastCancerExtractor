import os
from pathlib import Path

from app.native_launcher import _find_ollama, configure_native_environment


def test_native_environment_uses_portable_subdirectories(tmp_path, monkeypatch):
    monkeypatch.delenv("BCE_PORTABLE_ROOT", raising=False)
    root = configure_native_environment(tmp_path)

    assert root == tmp_path.resolve()
    assert Path(os.environ["DATABASE_PATH"]) == root / "database" / "extractor.db"
    assert Path(os.environ["WORKSPACE_PATH"]) == root / "workspace"
    assert Path(os.environ["MODEL_IMPORT_PATH"]) == root / "models" / "llm"
    assert Path(os.environ["PADDLE_PDX_CACHE_HOME"]) == root / "runtime" / "paddlex-cache"
    assert os.environ["RUNTIME_MODE"] == "windows_native"


def test_bundled_ollama_is_preferred(tmp_path, monkeypatch):
    bundled = tmp_path / "runtime" / "ollama" / "ollama.exe"
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"test")
    monkeypatch.setattr("app.native_launcher.shutil.which", lambda _: None)

    assert _find_ollama(tmp_path) == bundled.resolve()
