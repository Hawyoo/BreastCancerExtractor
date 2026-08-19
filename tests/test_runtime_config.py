from app.config import settings
from app.runtime_config import (
    get_ollama_provider,
    get_selected_ollama_model,
    save_ollama_provider,
    save_selected_ollama_model,
)


def configure_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_path", tmp_path / "database")
    monkeypatch.setattr(settings, "config_path", tmp_path / "config")
    monkeypatch.setattr(settings, "runtime_path", tmp_path / "runtime")
    monkeypatch.setattr(settings, "database_path", tmp_path / "runtime" / "test.db")


def test_ollama_provider_selection_is_persisted(tmp_path, monkeypatch):
    configure_paths(tmp_path, monkeypatch)
    selected = save_ollama_provider("WINDOWS_HOST")
    assert selected == {
        "provider": "WINDOWS_HOST",
        "endpoint": "http://127.0.0.1:11434",
    }
    assert get_ollama_provider() == selected
    assert (tmp_path / "config" / "runtime_config.json").is_file()
    assert not (tmp_path / "database" / "runtime_config.json").exists()


def test_legacy_runtime_config_moves_out_of_database(tmp_path, monkeypatch):
    configure_paths(tmp_path, monkeypatch)
    legacy = tmp_path / "database" / "runtime_config.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"ollama_provider":"DISABLED"}', encoding="utf-8")
    assert get_ollama_provider()["provider"] == "DISABLED"
    assert not legacy.exists()
    assert (tmp_path / "config" / "runtime_config.json").is_file()


def test_ollama_provider_rejects_arbitrary_endpoint(tmp_path, monkeypatch):
    configure_paths(tmp_path, monkeypatch)
    try:
        save_ollama_provider("REMOTE")
    except ValueError as error:
        assert "Unsupported" in str(error)
    else:
        raise AssertionError("Arbitrary Ollama providers must be rejected")


def test_each_ollama_provider_remembers_its_selected_model(tmp_path, monkeypatch):
    configure_paths(tmp_path, monkeypatch)
    save_selected_ollama_model("docker-model:latest", "DOCKER")
    save_selected_ollama_model("windows-model:latest", "WINDOWS_HOST")

    save_ollama_provider("DOCKER")
    assert get_selected_ollama_model() == "docker-model:latest"
    save_ollama_provider("WINDOWS_HOST")
    assert get_selected_ollama_model() == "windows-model:latest"


def test_changing_provider_does_not_erase_model_choices(tmp_path, monkeypatch):
    configure_paths(tmp_path, monkeypatch)
    save_selected_ollama_model("windows-model:latest", "WINDOWS_HOST")
    save_ollama_provider("DOCKER")
    save_ollama_provider("WINDOWS_HOST")
    assert get_selected_ollama_model("WINDOWS_HOST") == "windows-model:latest"


def test_windows_native_defaults_to_local_windows_ollama(tmp_path, monkeypatch):
    configure_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "runtime_mode", "windows_native")
    assert get_ollama_provider() == {
        "provider": "WINDOWS_HOST",
        "endpoint": "http://127.0.0.1:11434",
    }
