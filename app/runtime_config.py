import json
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings


def ollama_provider_endpoints() -> dict[str, str]:
    native_url = settings.ollama_url
    if urlparse(native_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        native_url = "http://127.0.0.1:11434"
    return {
        "DOCKER": "http://ollama:11434",
        "WINDOWS_HOST": (
            "http://host.docker.internal:11434"
            if settings.runtime_mode == "docker"
            else native_url
        ),
    }


def runtime_config_path() -> Path:
    return settings.database_path.parent / "runtime_config.json"


def load_runtime_config() -> dict[str, object]:
    path = runtime_config_path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_runtime_config(payload: dict[str, object]) -> None:
    path = runtime_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def default_ollama_provider() -> str:
    if settings.runtime_mode == "windows_native":
        return "WINDOWS_HOST"
    hostname = urlparse(settings.ollama_url).hostname
    return "WINDOWS_HOST" if hostname == "host.docker.internal" else "DOCKER"


def get_ollama_provider() -> dict[str, str]:
    endpoints = ollama_provider_endpoints()
    provider = load_runtime_config().get("ollama_provider")
    if provider in endpoints:
        return {"provider": str(provider), "endpoint": endpoints[str(provider)]}
    provider = default_ollama_provider()
    endpoint = settings.ollama_url if provider == "DOCKER" else endpoints[provider]
    return {"provider": provider, "endpoint": endpoint}


def save_ollama_provider(provider: str) -> dict[str, str]:
    endpoints = ollama_provider_endpoints()
    if provider not in endpoints:
        raise ValueError("Unsupported Ollama provider")
    payload = load_runtime_config()
    payload["ollama_provider"] = provider
    save_runtime_config(payload)
    return {"provider": provider, "endpoint": endpoints[provider]}


def get_selected_ollama_model(provider: str | None = None) -> str:
    selected_provider = provider or get_ollama_provider()["provider"]
    models = load_runtime_config().get("ollama_models", {})
    if isinstance(models, dict):
        selected = models.get(selected_provider)
        if isinstance(selected, str):
            return selected
    return settings.default_llm_model


def save_selected_ollama_model(model_name: str, provider: str | None = None) -> dict[str, str]:
    selected_provider = provider or get_ollama_provider()["provider"]
    if selected_provider not in ollama_provider_endpoints():
        raise ValueError("Unsupported Ollama provider")
    payload = load_runtime_config()
    models = payload.get("ollama_models")
    if not isinstance(models, dict):
        models = {}
    models[selected_provider] = model_name
    payload["ollama_models"] = models
    save_runtime_config(payload)
    return {"provider": selected_provider, "model": model_name}
