import os
from pathlib import Path

from app.native_launcher import DEFAULT_OCR_PORT, _find_ollama, configure_native_environment


def test_native_environment_uses_portable_subdirectories(tmp_path, monkeypatch):
    monkeypatch.delenv("BCE_PORTABLE_ROOT", raising=False)
    monkeypatch.delenv("BCE_OCR_PORT", raising=False)
    root = configure_native_environment(tmp_path)

    assert root == tmp_path.resolve()
    assert Path(os.environ["DATA_PATH"]) == root / "database"
    assert Path(os.environ["CONFIG_PATH"]) == root / "config"
    assert Path(os.environ["RUNTIME_PATH"]) == root / "runtime"
    assert Path(os.environ["DATABASE_PATH"]) == root / "runtime" / "catalog.sqlite"
    assert Path(os.environ["MODEL_IMPORT_PATH"]) == root / "models" / "llm"
    assert Path(os.environ["PADDLE_PDX_CACHE_HOME"]) == root / "runtime" / "paddlex-cache"
    assert os.environ["RUNTIME_MODE"] == "windows_native"
    assert int(os.environ["BCE_OCR_PORT"]) > 0
    assert os.environ["OCR_URL"] == f'http://127.0.0.1:{os.environ["BCE_OCR_PORT"]}'
    assert (root / "database" / "patients").is_dir()
    assert (root / "config").is_dir()
    assert (root / "runtime").is_dir()


def test_native_ocr_default_port_is_high_and_configurable(tmp_path, monkeypatch):
    assert DEFAULT_OCR_PORT == 18765

    monkeypatch.setenv("BCE_OCR_PORT", "28765")
    configure_native_environment(tmp_path)

    assert os.environ["BCE_OCR_PORT"] == "28765"
    assert os.environ["OCR_URL"] == "http://127.0.0.1:28765"


def test_native_ocr_falls_back_when_default_port_cannot_bind(tmp_path, monkeypatch):
    monkeypatch.delenv("BCE_OCR_PORT", raising=False)
    monkeypatch.setattr("app.native_launcher._port_bindable", lambda host, port: False)
    monkeypatch.setattr("app.native_launcher._find_free_tcp_port", lambda host: 28766)

    configure_native_environment(tmp_path)

    assert os.environ["BCE_OCR_PORT"] == "28766"
    assert os.environ["OCR_URL"] == "http://127.0.0.1:28766"


def test_bundled_ollama_is_preferred(tmp_path, monkeypatch):
    bundled = tmp_path / "runtime" / "ollama" / "ollama.exe"
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"test")
    monkeypatch.setattr("app.native_launcher.shutil.which", lambda _: None)

    assert _find_ollama(tmp_path) == bundled.resolve()
