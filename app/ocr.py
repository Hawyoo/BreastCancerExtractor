import io
import math
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.db import connect, rows_as_dicts


async def ocr_health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(base_url=settings.ocr_url, timeout=5) as client:
            response = await client.get("/health")
            response.raise_for_status()
            return {"available": True, **response.json()}
    except httpx.HTTPError as exc:
        return {"available": False, "error": str(exc)}


def _document_regions(path: Path) -> list[dict[str, Any]]:
    """Return saved ROI geometry for the sanitized image being OCRed."""
    try:
        relative_path = path.resolve().relative_to(settings.data_path.resolve()).as_posix()
    except (OSError, ValueError):
        return []

    with connect() as db:
        document = db.execute(
            "SELECT id FROM documents WHERE relative_path=?",
            (relative_path,),
        ).fetchone()
        if document is None:
            return []
        rows = db.execute(
            """SELECT id AS region_id,region_type,label,x,y,width,height
               FROM regions WHERE document_id=? ORDER BY created_at,id""",
            (document["id"],),
        ).fetchall()
    return rows_as_dicts(rows)


def _crop_region_png(source: Image.Image, region: dict[str, Any]) -> bytes | None:
    """Crop one saved ROI from the sanitized bitmap and return PNG bytes."""
    left = max(0, math.floor(float(region["x"])))
    top = max(0, math.floor(float(region["y"])))
    right = min(source.width, math.ceil(float(region["x"]) + float(region["width"])))
    bottom = min(source.height, math.ceil(float(region["y"]) + float(region["height"])))
    if right <= left or bottom <= top:
        return None

    output = io.BytesIO()
    source.crop((left, top, right, bottom)).save(output, format="PNG", optimize=True)
    return output.getvalue()


async def _recognize_png_bytes(client: httpx.AsyncClient, filename: str, content: bytes) -> dict[str, Any]:
    response = await client.post(
        "/ocr",
        files={"image": (filename, content, "image/png")},
    )
    response.raise_for_status()
    return response.json()


def _compose_ai_ocr_text(page_text: str, regions: list[dict[str, Any]]) -> str:
    """Append human-guided ROI context without pretending ROI text is verified data."""
    meaningful = [region for region in regions if str(region.get("full_text") or "").strip()]
    if not meaningful:
        return page_text

    parts = [
        page_text.rstrip(),
        "",
        "【人工标注高信度ROI】",
        (
            "说明：以下区域由人工框选，ROI的标签/类型用于提供高可信的语义归属；"
            "区域内文字仍由OCR识别，不等于字段值已经人工确认。"
            "提取与ROI标签相关的字段时应优先参考对应ROI；若ROI文字与整页其他文字冲突，"
            "不要仅因存在ROI就自动提高confidence，必须结合原文并保留真实证据。"
        ),
    ]
    for index, region in enumerate(meaningful, start=1):
        parts.extend(
            [
                "",
                f"[高信度ROI {index}]",
                f"类型：{region.get('region_type') or 'OTHER'}",
                f"标签：{region.get('label') or '信息区域'}",
                "局部OCR：",
                str(region.get("full_text") or "").strip(),
            ]
        )
    return "\n".join(parts).strip()


async def recognize_image(path: Path) -> dict[str, Any]:
    """OCR the full page and, when present, separately OCR human-marked ROIs."""
    regions = _document_regions(path)
    try:
        async with httpx.AsyncClient(base_url=settings.ocr_url, timeout=300) as client:
            with path.open("rb") as stream:
                response = await client.post("/ocr", files={"image": (path.name, stream, "image/png")})
            response.raise_for_status()
            result = response.json()

            page_text = str(result.get("full_text") or "")
            result["page_text"] = page_text
            result["regions"] = []
            if not regions:
                return result

            try:
                source = Image.open(path).convert("RGB")
                source.load()
            except (OSError, UnidentifiedImageError) as exc:
                raise HTTPException(status_code=422, detail="Invalid sanitized image") from exc

            region_results: list[dict[str, Any]] = []
            for index, region in enumerate(regions, start=1):
                cropped = _crop_region_png(source, region)
                if cropped is None:
                    continue
                try:
                    roi_result = await _recognize_png_bytes(client, f"roi-{index}.png", cropped)
                except httpx.HTTPStatusError as exc:
                    # A malformed/tiny ROI should not discard an otherwise successful full-page OCR.
                    region_results.append(
                        {
                            **region,
                            "full_text": "",
                            "lines": [],
                            "ocr_error": f"HTTP {exc.response.status_code}",
                        }
                    )
                    continue
                region_results.append(
                    {
                        **region,
                        "engine": roi_result.get("engine"),
                        "version": roi_result.get("version"),
                        "full_text": str(roi_result.get("full_text") or ""),
                        "lines": roi_result.get("lines") or [],
                    }
                )

            result["regions"] = region_results
            result["full_text"] = _compose_ai_ocr_text(page_text, region_results)
            return result
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"OCR unavailable: {exc}") from exc
