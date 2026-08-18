from app.config import settings
from app.runtime_config import (
    get_ollama_provider,
    get_selected_ollama_model,
    save_ollama_provider,
    save_selected_ollama_model,
)


def test_ollama_provider_selection_is_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "database" / "test.db")
    selected = save_ollama_provider("WINDOWS_HOST")
    assert selected == {
        "provider": "WINDOWS_HOST",
        "endpoint": "http://host.docker.internal:11434",
    }
    assert get_ollama_provider() == selected


def test_ollama_provider_rejects_arbitrary_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "database" / "test.db")
    try:
        save_ollama_provider("REMOTE")
    except ValueError as error:
        assert "Unsupported" in str(error)
    else:
        raise AssertionError("Arbitrary Ollama providers must be rejected")


def test_each_ollama_provider_remembers_its_selected_model(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "database" / "test.db")
    save_selected_ollama_model("docker-model:latest", "DOCKER")
    save_selected_ollama_model("windows-model:latest", "WINDOWS_HOST")

    save_ollama_provider("DOCKER")
    assert get_selected_ollama_model() == "docker-model:latest"
    save_ollama_provider("WINDOWS_HOST")
    assert get_selected_ollama_model() == "windows-model:latest"


def test_changing_provider_does_not_erase_model_choices(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "database" / "test.db")
    save_selected_ollama_model("windows-model:latest", "WINDOWS_HOST")
    save_ollama_provider("DOCKER")
    save_ollama_provider("WINDOWS_HOST")
    assert get_selected_ollama_model("WINDOWS_HOST") == "windows-model:latest"
