from typing import Any

import httpx
from fastapi import HTTPException

from app.config import settings


async def ocr_health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(base_url=settings.ocr_url, timeout=5) as client:
            response = await client.get("/health")
            response.raise_for_status()
            return {"available": True, **response.json()}
    except httpx.HTTPError as exc:
        return {"available": False, "error": str(exc)}


async def recognize_image(path) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(base_url=settings.ocr_url, timeout=300) as client:
            with path.open("rb") as stream:
                response = await client.post("/ocr", files={"image": (path.name, stream, "image/png")})
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"OCR unavailable: {exc}") from exc
