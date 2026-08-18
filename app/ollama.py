import asyncio
import hashlib
import json
import re
from pathlib import Path
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import settings
from app.runtime_config import get_ollama_provider, get_selected_ollama_model
from app.storage import resolve_gguf

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string"},
                    "value": {"type": ["string", "null"]},
                    "raw_text": {"type": ["string", "null"]},
                    "confidence": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                    "source_mode": {"type": "string", "enum": ["RECORDED", "INFERRED"]},
                    "inference_basis": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "component": {"type": "string"},
                                "fact": {"type": "string"},
                                "source_text": {"type": "string"},
                            },
                            "required": ["component", "fact", "source_text"],
                        },
                    },
                },
                "required": ["field_name", "value", "raw_text", "confidence", "source_mode", "inference_basis"],
            },
        }
    },
    "required": ["observations"],
}

_FILE_DIGEST_CACHE: dict[str, tuple[int, int, str]] = {}


async def ollama_request(
    method: str,
    path: str,
    json: dict[str, Any] | None = None,
    base_url: str | None = None,
) -> Any:
    try:
        endpoint = base_url or get_ollama_provider()["endpoint"]
        timeout = httpx.Timeout(connect=10, read=600, write=120, pool=10)
        async with httpx.AsyncClient(base_url=endpoint, timeout=timeout) as client:
            response = await client.request(method, path, json=json)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        try:
            message = exc.response.json().get("error") or exc.response.text
        except (ValueError, AttributeError):
            message = exc.response.text
        raise HTTPException(status_code=503, detail=f"Ollama error: {message}") from exc
    except httpx.ReadTimeout as exc:
        raise HTTPException(status_code=504, detail="Ollama推理超过10分钟仍未完成，请改用较小模型或缩短OCR文字") from exc
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=503, detail="Ollama连接中断，请确认所选Ollama仍在运行") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {exc}") from exc


async def list_models(base_url: str | None = None) -> list[dict[str, Any]]:
    payload = await ollama_request("GET", "/api/tags", base_url=base_url)
    return payload.get("models", [])


def supports_structured_extraction(model: dict[str, Any]) -> bool:
    name = str(model.get("name") or model.get("model") or "").lower()
    details = model.get("details") if isinstance(model.get("details"), dict) else {}
    families = [str(item).lower() for item in details.get("families") or []]
    family = str(details.get("family") or "").lower()
    embedding_markers = ("embed", "embedding", "nomic-bert", "bert", "bge", "e5-")
    return not any(marker in value for marker in embedding_markers for value in [name, family, *families])


async def list_extraction_models(base_url: str | None = None) -> list[dict[str, Any]]:
    return [model for model in await list_models(base_url) if supports_structured_extraction(model)]


def group_models_by_digest(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for model in models:
        name = model.get("name") or model.get("model")
        key = str(model.get("digest") or name)
        if key not in grouped:
            grouped[key] = {**model, "name": name, "aliases": []}
        if name and name not in grouped[key]["aliases"]:
            grouped[key]["aliases"].append(name)
    return list(grouped.values())


async def list_model_groups(base_url: str | None = None) -> list[dict[str, Any]]:
    """Return only models that can be used for chat-based extraction.

    Embedding-only models are intentionally filtered before grouping so model
    counts, aliases, and the model picker all describe the same usable set.
    """
    return group_models_by_digest(await list_extraction_models(base_url))


async def model_source_digests() -> dict[str, list[str]]:
    sources: dict[str, list[str]] = {}
    for model in await list_models():
        name = model.get("name") or model.get("model")
        if not name:
            continue
        details = await ollama_request("POST", "/api/show", json={"model": name})
        modelfile = str(details.get("modelfile", ""))
        match = re.search(r"sha256[-:]([0-9a-fA-F]{64})", modelfile)
        if match:
            sources.setdefault(match.group(1).lower(), []).append(str(name))
    return sources


async def ollama_health(base_url: str | None = None) -> dict[str, Any]:
    runtime = get_ollama_provider()
    endpoint = base_url or runtime["endpoint"]
    try:
        models = await list_model_groups(endpoint)
        running = await ollama_request("GET", "/api/ps", base_url=endpoint)
        running_models = running.get("models", [])
        vram_bytes = sum(int(model.get("size_vram") or 0) for model in running_models)
        return {
            "available": True,
            "models": len(models),
            "default_model": get_selected_ollama_model(runtime["provider"]),
            "endpoint": endpoint,
            "provider": runtime["provider"] if base_url is None else None,
            "processor": "GPU" if vram_bytes > 0 else ("CPU" if running_models else "IDLE"),
            "vram_bytes": vram_bytes,
        }
    except HTTPException as exc:
        return {"available": False, "models": 0, "error": str(exc.detail), "endpoint": endpoint,
                "provider": runtime["provider"] if base_url is None else None, "processor": "UNAVAILABLE"}


async def ollama_runtime_status() -> dict[str, int | str]:
    running = await ollama_request("GET", "/api/ps")
    running_models = running.get("models", [])
    vram_bytes = sum(int(model.get("size_vram") or 0) for model in running_models)
    return {
        "processor": "GPU" if vram_bytes > 0 else ("CPU" if running_models else "IDLE"),
        "vram_bytes": vram_bytes,
    }


async def extract_structured(
    model: str,
    prompt: str,
    progress: Callable[[dict[str, Any]], None] | None = None,
    *,
    think: bool = False,
) -> dict[str, Any]:
    endpoint = get_ollama_provider()["endpoint"]
    timeout = httpx.Timeout(connect=10, read=600, write=120, pool=10)
    request_payload = {
        "model": model,
        "stream": True,
        "think": think,
        "keep_alive": -1,
        "format": EXTRACTION_SCHEMA,
        "options": {"temperature": 0},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是乳腺癌科研病历结构化抽取器。只依据提供的OCR文字输出JSON。"
                    "不得补造缺失资料。TNM/分期若原文明确记载，必须优先抽取原记录；"
                    "只有原文未记录且事实足以判断时才可推断，并将source_mode设为INFERRED、"
                    "confidence最高为MEDIUM，逐项填写inference_basis。TNM中T表示原发肿瘤、N表示区域"
                    "淋巴结、M表示远处转移；cT逐项列出治疗前超声、钼靶和MRI尺寸，pT/ypT优先采用"
                    "术后病理报告的浸润癌最大径，pN/ypN优先采用术后淋巴结病理。其他字段为RECORDED。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    content_parts: list[str] = []
    generated_chunks = 0
    metrics: dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(base_url=endpoint, timeout=timeout) as client:
            async with client.stream("POST", "/api/chat", json=request_payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    message = chunk.get("message") or {}
                    thinking = str(message.get("thinking") or "")
                    content = str(message.get("content") or "")
                    if thinking or content:
                        generated_chunks += 1
                    if content:
                        content_parts.append(content)
                    if progress:
                        progress({
                            "stage": "THINKING" if thinking and not content_parts else "GENERATING_JSON",
                            "generated_tokens": generated_chunks,
                        })
                    if chunk.get("done"):
                        metrics = {
                            key: chunk.get(key)
                            for key in (
                                "total_duration", "load_duration", "prompt_eval_count",
                                "prompt_eval_duration", "eval_count", "eval_duration", "done_reason",
                            )
                        }
    except httpx.HTTPStatusError as exc:
        try:
            message = exc.response.json().get("error") or exc.response.text
        except (ValueError, AttributeError):
            message = exc.response.text
        raise HTTPException(status_code=503, detail=f"Ollama error: {message}") from exc
    except httpx.ReadTimeout as exc:
        raise HTTPException(status_code=504, detail="Ollama推理超过10分钟仍未完成，请改用较小模型或缩短OCR文字") from exc
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=503, detail="Ollama连接中断，请确认所选Ollama仍在运行") from exc
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=f"Ollama流式响应异常: {exc}") from exc

    if progress:
        progress({"stage": "VALIDATING", "generated_tokens": generated_chunks})
    try:
        result = json.loads("".join(content_parts))
        result["_ollama_metrics"] = metrics
        return result
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Ollama returned invalid structured output") from exc


async def import_gguf(filename: str, model_name: str) -> dict[str, Any]:
    model_path = resolve_gguf(filename)
    digest = await asyncio.to_thread(cached_file_sha256, model_path)
    blob_digest = f"sha256:{digest}"
    await ensure_blob(model_path, blob_digest)
    result = await ollama_request(
        "POST",
        "/api/create",
        json={
            "model": model_name,
            "files": {filename: blob_digest},
            "parameters": {"temperature": 0},
            "stream": False,
        },
    )
    return {**result, "digest": blob_digest, "source_file": filename}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def cached_file_sha256(path: Path) -> str:
    stat = path.stat()
    key = str(path.resolve())
    cached = _FILE_DIGEST_CACHE.get(key)
    if cached and cached[:2] == (stat.st_size, stat.st_mtime_ns):
        return cached[2]
    digest = file_sha256(path)
    _FILE_DIGEST_CACHE[key] = (stat.st_size, stat.st_mtime_ns, digest)
    return digest


async def ensure_blob(path: Path, digest: str) -> None:
    timeout = httpx.Timeout(connect=10, read=3600, write=3600, pool=10)
    try:
        async with httpx.AsyncClient(base_url=get_ollama_provider()["endpoint"], timeout=timeout) as client:
            exists = await client.head(f"/api/blobs/{digest}")
            if exists.status_code == 200:
                return
            if exists.status_code != 404:
                exists.raise_for_status()

            async def chunks():
                with path.open("rb") as stream:
                    while chunk := await asyncio.to_thread(stream.read, 8 * 1024 * 1024):
                        yield chunk

            response = await client.post(
                f"/api/blobs/{digest}",
                content=chunks(),
                headers={"Content-Type": "application/octet-stream"},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            message = exc.response.json().get("error") or exc.response.text
        except (ValueError, AttributeError):
            message = exc.response.text
        raise HTTPException(status_code=503, detail=f"Ollama blob import failed: {message}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Ollama blob import unavailable: {exc}") from exc
