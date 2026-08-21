from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app.text_learning import (
    build_text_learning_profile,
    import_text_learning_payload,
    imported_text_learning_status,
)

router = APIRouter()
MAX_LEARNING_IMPORT_BYTES = 20 * 1024 * 1024


@router.get("/api/text-learning")
def get_text_learning() -> dict[str, object]:
    profile = build_text_learning_profile(max_fields=1000, max_examples_per_field=50)
    return {
        **profile,
        "type": "bce_text_learning",
        "version": 3,
        "generated_for": "ai_field_and_evidence_learning",
        "imported": imported_text_learning_status(),
    }


@router.post("/api/text-learning/import")
def import_text_learning(payload: dict[str, object]) -> dict[str, object]:
    encoded_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    if encoded_size > MAX_LEARNING_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="学习JSON超过20MB，已拒绝导入")

    source_name = str(payload.get("source_name") or "imported-learning.json").strip()
    profile = payload.get("profile")
    if not isinstance(profile, dict):
        raise HTTPException(status_code=422, detail="缺少有效的学习JSON profile")
    try:
        return import_text_learning_payload(profile, source_name=source_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
