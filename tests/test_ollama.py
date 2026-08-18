import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.config import settings
from app.ollama import (
    extract_structured,
    group_models_by_digest,
    import_gguf,
    list_model_groups,
    ollama_request,
    supports_structured_extraction,
)


def test_gguf_import_uses_blob_and_files_api(tmp_path, monkeypatch):
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"gguf-test")
    monkeypatch.setattr(settings, "model_import_path", tmp_path)
    captured = {}

    monkeypatch.setattr("app.ollama.file_sha256", lambda _: "abc123")

    async def fake_blob(path, digest):
        captured["blob"] = (path.name, digest)

    async def fake_request(method, path, json=None):
        captured["request"] = (method, path, json)
        return {"status": "success"}

    monkeypatch.setattr("app.ollama.ensure_blob", fake_blob)
    monkeypatch.setattr("app.ollama.ollama_request", fake_request)
    result = asyncio.run(import_gguf("model.gguf", "local-model"))

    assert captured["blob"] == ("model.gguf", "sha256:abc123")
    assert captured["request"][2]["files"] == {"model.gguf": "sha256:abc123"}
    assert "modelfile" not in captured["request"][2]
    assert result["status"] == "success"


def test_models_with_same_digest_are_grouped_as_aliases():
    grouped = group_models_by_digest(
        [
            {"name": "Qwen3-8B:latest", "digest": "same-digest", "size": 5_000_000_000},
            {"name": "qwen3-local:latest", "digest": "same-digest", "size": 5_000_000_000},
        ]
    )
    assert len(grouped) == 1
    assert grouped[0]["aliases"] == ["Qwen3-8B:latest", "qwen3-local:latest"]


def test_embedding_models_cannot_be_selected_for_structured_extraction():
    assert not supports_structured_extraction(
        {"name": "nomic-embed-text:v1.5", "details": {"family": "nomic-bert", "families": ["nomic-bert"]}}
    )
    assert supports_structured_extraction(
        {"name": "qwen3.5:9b", "details": {"family": "qwen35", "families": ["qwen35"]}}
    )


def test_model_groups_hide_embedding_models(monkeypatch):
    async def fake_models(_base_url=None):
        return [
            {"name": "nomic-embed-text:latest", "digest": "embed", "details": {"family": "nomic-bert"}},
            {"name": "qwen3.5:9b", "digest": "chat", "details": {"family": "qwen35"}},
        ]

    monkeypatch.setattr("app.ollama.list_models", fake_models)
    grouped = asyncio.run(list_model_groups())
    assert [model["name"] for model in grouped] == ["qwen3.5:9b"]


def test_ollama_read_timeout_has_actionable_message(monkeypatch):
    class TimeoutClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def request(self, *_args, **_kwargs):
            request = httpx.Request("POST", "http://ollama/api/chat")
            raise httpx.ReadTimeout("", request=request)

    monkeypatch.setattr("app.ollama.httpx.AsyncClient", lambda **_kwargs: TimeoutClient())
    with pytest.raises(HTTPException) as error:
        asyncio.run(ollama_request("POST", "/api/chat", json={}))
    assert error.value.status_code == 504
    assert "10分钟" in error.value.detail


def test_structured_extraction_controls_thinking_and_keeps_model_loaded(monkeypatch):
    captured = {}

    class StreamResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield '{"message":{"content":"{\\"observations\\":[]}"},"done":false}'
            yield '{"message":{"content":""},"done":true,"eval_count":1,"eval_duration":1000000000}'

    class StreamClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def stream(self, method, path, json):
            captured.update({"method": method, "path": path, "payload": json})
            return StreamResponse()

    monkeypatch.setattr("app.ollama.httpx.AsyncClient", lambda **_kwargs: StreamClient())
    result = asyncio.run(extract_structured("qwen", "prompt", think=False))
    assert result["observations"] == []
    assert captured["payload"]["think"] is False
    assert captured["payload"]["keep_alive"] == -1
