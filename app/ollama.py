from typing import Any

import httpx
from fastapi import HTTPException

from app.config import settings


async def ollama_request(method: str, path: str, json: dict[str, Any] | None = None) -> Any:
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_url, timeout=120) as client:
            response = await client.request(method, path, json=json)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {exc}") from exc


async def list_models() -> list[dict[str, Any]]:
    payload = await ollama_request("GET", "/api/tags")
    return payload.get("models", [])


async def import_gguf(filename: str, model_name: str) -> dict[str, Any]:
    # /models/llm is mounted read-only into the Ollama container.
    modelfile = f"FROM /models/llm/{filename}\nPARAMETER temperature 0\n"
    return await ollama_request(
        "POST",
        "/api/create",
        json={"model": model_name, "modelfile": modelfile, "stream": False},
    )

