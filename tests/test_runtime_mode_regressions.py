import asyncio

from app.config import settings
from app.models import OllamaProviderUpdate, SanitizationMetadata
from app.native_launcher import _ollama_disabled, ensure_ollama
from app.ollama import ollama_health
from app.runtime_config import get_ollama_provider, save_ollama_provider


def test_disabled_provider_is_persisted_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "database" / "test.db")
    payload = OllamaProviderUpdate(provider="DISABLED")
    assert payload.provider == "DISABLED"
    saved = save_ollama_provider(payload.provider)
    assert saved["provider"] == "DISABLED"
    assert saved["endpoint"].startswith("disabled://")
    assert get_ollama_provider() == saved
    health = asyncio.run(ollama_health())
    assert health["disabled"] is True
    assert health["processor"] == "DISABLED"


def test_native_launcher_reads_ocr_only_mode(tmp_path):
    config = tmp_path / "database" / "runtime_config.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"ollama_provider":"DISABLED"}', encoding="utf-8")
    assert _ollama_disabled(tmp_path) is True


def test_sanitization_metadata_keeps_editor_transforms():
    metadata = SanitizationMetadata(
        source_width=100,
        source_height=80,
        crop={"x": 0, "y": 0, "width": 100, "height": 80, "rotation": 2.5},
        redaction_count=1,
        client_reencoded=True,
        transforms={"version": 1, "roi_rotations": [3.0]},
    )
    assert metadata.transforms == {"version": 1, "roi_rotations": [3.0]}


def test_existing_ollama_is_treated_as_external_and_never_spawned(tmp_path, monkeypatch):
    monkeypatch.setattr("app.native_launcher._url_available", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("app.native_launcher._spawn", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")))
    assert ensure_ollama(tmp_path) is None


def test_disabled_mode_does_not_start_ollama(tmp_path, monkeypatch):
    config = tmp_path / "database" / "runtime_config.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"ollama_provider":"DISABLED"}', encoding="utf-8")
    monkeypatch.setattr("app.native_launcher._url_available", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("app.native_launcher._spawn", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")))
    assert ensure_ollama(tmp_path) is None
