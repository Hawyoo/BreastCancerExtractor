from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from app.config import settings
from app.db import connect
from app.derived_fields import is_derived_field

LEARNING_EXCLUDED_FIELDS = {"record_number", "contact"}
_IMPORTED_FILENAME = "imported_text_learning.json"
_FIELD_KEY = re.compile(r"^[A-Za-z0-9_]{1,128}$")
_MAX_TEXT = 4000
_MAX_REASON = 1200
_MAX_COUNT = 1_000_000
_MANUAL_FILL_MARKER = "人工手动补充"


def _clean(value: object, *, limit: int = _MAX_TEXT) -> str:
    return str(value or "").strip()[:limit]


def _field_is_learnable(field_name: str, allowed_fields: set[str] | None) -> bool:
    if (
        not field_name
        or not _FIELD_KEY.fullmatch(field_name)
        or field_name in LEARNING_EXCLUDED_FIELDS
        or is_derived_field(field_name)
    ):
        return False
    return allowed_fields is None or field_name in allowed_fields


def _safe_count(value: object, default: int = 1) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = default
    return max(1, min(_MAX_COUNT, count))


def _empty_profile(source: str = "local_and_imported_learning") -> dict[str, object]:
    return {
        "version": 3,
        "source": source,
        "learning_mode": "field_examples",
        "field_count": 0,
        "example_count": 0,
        "fields": [],
    }


def _imported_path() -> Path:
    return settings.data_path / "learning" / _IMPORTED_FILENAME


def _empty_imported_store() -> dict[str, object]:
    return {
        "version": 2,
        "type": "bce_imported_text_learning",
        "sources": [],
        "fields": [],
    }


def _read_imported_store() -> dict[str, object]:
    path = _imported_path()
    if not path.is_file():
        return _empty_imported_store()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return _empty_imported_store()
    if not isinstance(payload, dict) or not isinstance(payload.get("fields"), list):
        return _empty_imported_store()
    payload.setdefault("sources", [])
    return payload


def _write_imported_store(payload: dict[str, object]) -> None:
    path = _imported_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _normalize_for_match(value: object) -> str:
    text = _clean(value).lower()
    return re.sub(r"[\s\u3000，。；：、,.!?！？“”‘’'\"（）()【】\[\]{}<>《》]+", "", text)


def _bigrams(value: str) -> list[str]:
    if len(value) < 2:
        return [value] if value else []
    return [value[index : index + 2] for index in range(len(value) - 1)]


def _text_similarity(left: object, right: object) -> float:
    a = _normalize_for_match(left)
    b = _normalize_for_match(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        ratio = min(len(a), len(b)) / max(len(a), len(b))
        return 0.88 + 0.12 * ratio
    left_grams = Counter(_bigrams(a))
    right_grams = Counter(_bigrams(b))
    overlap = sum((left_grams & right_grams).values())
    denominator = sum(left_grams.values()) + sum(right_grams.values())
    return (2 * overlap / denominator) if denominator else 0.0


def _rect_from_box(box: object) -> list[float] | None:
    if not isinstance(box, list):
        return None
    if len(box) >= 4 and all(isinstance(value, (int, float)) for value in box[:4]):
        x1, y1, x2, y2 = [float(value) for value in box[:4]]
        return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
    if box and all(isinstance(point, list) and len(point) >= 2 for point in box):
        points: list[tuple[float, float]] = []
        for point in box:
            try:
                points.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                continue
        if not points:
            return None
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return [min(xs), min(ys), max(xs), max(ys)]
    return None


def _relative_bbox(bbox: list[float] | None, width: object, height: object) -> list[float] | None:
    if not bbox:
        return None
    try:
        image_width = float(width)
        image_height = float(height)
    except (TypeError, ValueError):
        return None
    if image_width <= 0 or image_height <= 0:
        return None
    return [
        round(max(0.0, min(1.0, bbox[0] / image_width)), 5),
        round(max(0.0, min(1.0, bbox[1] / image_height)), 5),
        round(max(0.0, min(1.0, bbox[2] / image_width)), 5),
        round(max(0.0, min(1.0, bbox[3] / image_height)), 5),
    ]


def _ocr_lines(result_json: object) -> list[dict[str, object]]:
    try:
        payload = json.loads(str(result_json or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    lines = payload.get("lines") if isinstance(payload, dict) else None
    return [item for item in lines if isinstance(item, dict)] if isinstance(lines, list) else []


def _locate_evidence(
    evidence_text: str,
    result_json: object,
    width: object,
    height: object,
) -> dict[str, object]:
    """Map reviewed evidence text back to OCR lines for export/audit.

    Coordinates are retained for traceability and current-image highlighting.
    Cross-patient LLM learning uses the evidence text and neighboring context,
    not absolute pixel positions.
    """
    evidence = _clean(evidence_text)
    if not evidence:
        return {
            "text": "",
            "matched": False,
            "line_ids": [],
            "lines": [],
            "context_before": "",
            "context_after": "",
        }

    lines = _ocr_lines(result_json)
    if not lines:
        return {
            "text": evidence,
            "matched": False,
            "line_ids": [],
            "lines": [],
            "context_before": "",
            "context_after": "",
        }

    candidates: list[dict[str, object]] = []
    for index, line in enumerate(lines):
        line_text = _clean(line.get("text"))
        if not line_text:
            continue
        relevance = _text_similarity(evidence, line_text)
        try:
            ocr_confidence = float(line.get("score") or 0)
        except (TypeError, ValueError):
            ocr_confidence = 0.0
        bbox = _rect_from_box(line.get("box"))
        score = relevance * 0.9 + max(0.0, min(1.0, ocr_confidence)) * 0.1
        candidates.append(
            {
                "index": index,
                "line_id": index + 1,
                "text": line_text,
                "ocr_confidence": round(ocr_confidence, 4),
                "relevance": round(relevance, 4),
                "score": round(score, 4),
                "bbox": bbox,
                "relative_bbox": _relative_bbox(bbox, width, height),
            }
        )

    candidates.sort(key=lambda item: float(item["score"]), reverse=True)
    if not candidates or float(candidates[0]["relevance"]) < 0.38:
        return {
            "text": evidence,
            "matched": False,
            "line_ids": [],
            "lines": [],
            "context_before": "",
            "context_after": "",
            "best_match_score": round(float(candidates[0]["score"]), 4) if candidates else 0.0,
        }

    best_relevance = float(candidates[0]["relevance"])
    threshold = max(0.38, best_relevance - 0.2)
    selected = [item for item in candidates if float(item["relevance"]) >= threshold][:4]
    selected.sort(key=lambda item: int(item["line_id"]))
    selected_indices = [int(item["index"]) for item in selected]
    first_index = min(selected_indices)
    last_index = max(selected_indices)
    before = _clean(lines[first_index - 1].get("text")) if first_index > 0 else ""
    after = _clean(lines[last_index + 1].get("text")) if last_index + 1 < len(lines) else ""

    exported_lines = [
        {
            "line_id": item["line_id"],
            "text": item["text"],
            "ocr_confidence": item["ocr_confidence"],
            "relevance": item["relevance"],
            "bbox": item["bbox"],
            "relative_bbox": item["relative_bbox"],
        }
        for item in selected
    ]
    confidences = [float(item["ocr_confidence"]) for item in selected if float(item["ocr_confidence"]) > 0]
    return {
        "text": evidence,
        "matched": True,
        "line_ids": [item["line_id"] for item in selected],
        "lines": exported_lines,
        "context_before": before,
        "context_after": after,
        "ocr_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "match_score": round(max(float(item["score"]) for item in selected), 4),
    }


def _example_fingerprint(field_name: str, example: dict[str, object]) -> str:
    evidence = example.get("evidence") if isinstance(example.get("evidence"), dict) else {}
    canonical = {
        "field_name": field_name,
        "document_type": _clean(example.get("document_type"), limit=128),
        "ai_value": _clean(example.get("ai_value")),
        "verified_value": _clean(example.get("verified_value")),
        "evidence_text": _clean(evidence.get("text") if isinstance(evidence, dict) else ""),
        "context_before": _clean(evidence.get("context_before") if isinstance(evidence, dict) else ""),
        "context_after": _clean(evidence.get("context_after") if isinstance(evidence, dict) else ""),
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_location_line(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    try:
        line_id = int(raw.get("line_id") or 0)
    except (TypeError, ValueError):
        line_id = 0
    if line_id <= 0:
        return None
    bbox = _rect_from_box(raw.get("bbox"))
    relative_bbox = raw.get("relative_bbox")
    if not (
        isinstance(relative_bbox, list)
        and len(relative_bbox) == 4
        and all(isinstance(value, (int, float)) for value in relative_bbox)
    ):
        relative_bbox = None
    try:
        ocr_confidence = float(raw.get("ocr_confidence") or 0)
    except (TypeError, ValueError):
        ocr_confidence = 0.0
    try:
        relevance = float(raw.get("relevance") or 0)
    except (TypeError, ValueError):
        relevance = 0.0
    return {
        "line_id": line_id,
        "text": _clean(raw.get("text")),
        "ocr_confidence": round(max(0.0, min(1.0, ocr_confidence)), 4),
        "relevance": round(max(0.0, min(1.0, relevance)), 4),
        "bbox": bbox,
        "relative_bbox": relative_bbox,
    }


def _normalize_example(field_name: str, raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    ai_value = _clean(raw.get("ai_value"))
    verified_value = _clean(raw.get("verified_value") or raw.get("corrected_value"))
    evidence_raw = raw.get("evidence")
    if isinstance(evidence_raw, dict):
        evidence_text = _clean(evidence_raw.get("text") or evidence_raw.get("accepted_text"))
        before = _clean(evidence_raw.get("context_before"), limit=1200)
        after = _clean(evidence_raw.get("context_after"), limit=1200)
        lines = [
            normalized
            for item in (evidence_raw.get("lines") or [])
            if (normalized := _normalize_location_line(item)) is not None
        ][:8]
        matched = bool(evidence_raw.get("matched")) or bool(lines)
        line_ids = [
            int(value)
            for value in (evidence_raw.get("line_ids") or [])
            if isinstance(value, int) and value > 0
        ][:8]
        if not line_ids:
            line_ids = [int(item["line_id"]) for item in lines]
        try:
            ocr_confidence = float(evidence_raw.get("ocr_confidence") or 0)
        except (TypeError, ValueError):
            ocr_confidence = 0.0
        try:
            match_score = float(evidence_raw.get("match_score") or evidence_raw.get("best_match_score") or 0)
        except (TypeError, ValueError):
            match_score = 0.0
    else:
        evidence_text = _clean(raw.get("evidence_text") or raw.get("accepted_evidence"))
        before = _clean(raw.get("context_before"), limit=1200)
        after = _clean(raw.get("context_after"), limit=1200)
        lines = []
        line_ids = []
        matched = False
        ocr_confidence = 0.0
        match_score = 0.0

    if not verified_value and not evidence_text:
        return None

    try:
        learning_weight = float(raw.get("learning_weight") or 1.0)
    except (TypeError, ValueError):
        learning_weight = 1.0
    learning_weight = max(0.5, min(5.0, learning_weight))
    reason = _clean(raw.get("correction_reason") or raw.get("reason"), limit=_MAX_REASON)
    example = {
        "document_type": _clean(raw.get("document_type"), limit=128) or "OTHER",
        "ai_value": ai_value,
        "verified_value": verified_value,
        "value_changed": bool(raw.get("value_changed")) or bool(ai_value and verified_value and ai_value != verified_value),
        "human_verified": bool(raw.get("human_verified", True)),
        "correction_reason": reason,
        "learning_weight": round(learning_weight, 2),
        "evidence_rejected": bool(raw.get("evidence_rejected")) or bool(
            isinstance(evidence_raw, dict) and evidence_raw.get("rejected_by_user")
        ),
        "evidence": {
            "text": evidence_text,
            "matched": matched,
            "line_ids": line_ids,
            "lines": lines,
            "context_before": before,
            "context_after": after,
            "ocr_confidence": round(max(0.0, min(1.0, ocr_confidence)), 4),
            "match_score": round(max(0.0, min(1.0, match_score)), 4),
        },
    }
    example["example_id"] = _example_fingerprint(field_name, example)[:20]
    return example


def _normalize_import_payload(payload: dict[str, object]) -> dict[str, object]:
    kind = payload.get("type")
    if kind not in (None, "bce_text_learning", "bce_imported_text_learning"):
        raise ValueError("不是 BCE 文本学习 JSON")
    try:
        version = int(payload.get("version", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("学习 JSON version 无效") from exc
    if version not in {1, 2, 3}:
        raise ValueError(f"暂不支持学习 JSON version={version}")

    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, list):
        raise ValueError("学习 JSON 缺少 fields 数组")

    fields: list[dict[str, object]] = []
    skipped_fields = 0
    skipped_entries = 0
    for raw in raw_fields:
        if not isinstance(raw, dict):
            skipped_fields += 1
            continue
        field_name = _clean(raw.get("field_name"), limit=128)
        if not _field_is_learnable(field_name, None):
            skipped_fields += 1
            continue

        corrections: list[dict[str, object]] = []
        for correction in raw.get("corrections") or []:
            if not isinstance(correction, dict):
                skipped_entries += 1
                continue
            old_value = _clean(correction.get("from"))
            new_value = _clean(correction.get("to"))
            if not new_value or old_value == new_value:
                skipped_entries += 1
                continue
            reason = _clean(correction.get("reason"), limit=_MAX_REASON)
            corrections.append(
                {
                    "from": old_value,
                    "to": new_value,
                    **({"reason": reason} if reason else {}),
                    "count": _safe_count(correction.get("count")),
                }
            )

        manual_values: list[dict[str, object]] = []
        for manual in raw.get("manual_values") or []:
            if not isinstance(manual, dict):
                skipped_entries += 1
                continue
            value = _clean(manual.get("value"))
            if not value:
                skipped_entries += 1
                continue
            manual_values.append({"value": value, "count": _safe_count(manual.get("count"))})

        examples: list[dict[str, object]] = []
        for example_raw in raw.get("examples") or []:
            example = _normalize_example(field_name, example_raw)
            if example is None:
                skipped_entries += 1
                continue
            examples.append(example)

        if not corrections and not manual_values and not examples:
            skipped_fields += 1
            continue
        fields.append(
            {
                "field_name": field_name,
                "label": _clean(raw.get("label"), limit=200) or field_name,
                "corrections": corrections,
                "manual_values": manual_values,
                "examples": examples,
            }
        )

    return {
        "version": 3,
        "source": "imported_text_learning",
        "fields": fields,
        "skipped_fields": skipped_fields,
        "skipped_entries": skipped_entries,
    }


def _fingerprint_fields(fields: list[dict[str, object]]) -> str:
    canonical = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _example_quality(example: dict[str, object]) -> tuple[float, str]:
    evidence = example.get("evidence") if isinstance(example.get("evidence"), dict) else {}
    score = 0.0
    if bool(example.get("value_changed")):
        score += 4.0
    if bool(example.get("human_verified")):
        score += 2.0
    if isinstance(evidence, dict) and bool(evidence.get("matched")):
        score += 3.0
    if isinstance(evidence, dict) and _clean(evidence.get("text")):
        score += 1.0
    score += min(2.0, float(example.get("learning_weight") or 1.0) / 2)
    return score, str(example.get("example_id") or "")


def _merge_field_lists(
    profiles: Iterable[list[dict[str, object]]],
    *,
    allowed_fields: set[str] | None = None,
    max_fields: int = 24,
    max_examples_per_field: int = 6,
) -> list[dict[str, object]]:
    """Merge local/imported learning while keeping migration idempotent."""
    fields: dict[str, dict[str, object]] = {}

    def item_for(field_name: str, label: str = "") -> dict[str, object]:
        item = fields.setdefault(
            field_name,
            {
                "field_name": field_name,
                "label": label or field_name,
                "corrections": {},
                "manual_values": {},
                "examples": {},
            },
        )
        if label and item["label"] == field_name:
            item["label"] = label
        return item

    for field_list in profiles:
        for raw in field_list:
            field_name = _clean(raw.get("field_name"), limit=128)
            if not _field_is_learnable(field_name, allowed_fields):
                continue
            item = item_for(field_name, _clean(raw.get("label"), limit=200))
            correction_map: dict[tuple[str, str, str], int] = item["corrections"]  # type: ignore[assignment]
            for correction in raw.get("corrections") or []:  # type: ignore[union-attr]
                if not isinstance(correction, dict):
                    continue
                old_value = _clean(correction.get("from"))
                new_value = _clean(correction.get("to"))
                if not new_value or old_value == new_value:
                    continue
                reason = _clean(correction.get("reason"), limit=_MAX_REASON)
                key = (old_value, new_value, reason)
                correction_map[key] = max(correction_map.get(key, 0), _safe_count(correction.get("count")))

            manual_map: dict[str, int] = item["manual_values"]  # type: ignore[assignment]
            for manual in raw.get("manual_values") or []:  # type: ignore[union-attr]
                if not isinstance(manual, dict):
                    continue
                value = _clean(manual.get("value"))
                if not value:
                    continue
                manual_map[value] = max(manual_map.get(value, 0), _safe_count(manual.get("count")))

            example_map: dict[str, dict[str, object]] = item["examples"]  # type: ignore[assignment]
            for raw_example in raw.get("examples") or []:  # type: ignore[union-attr]
                example = _normalize_example(field_name, raw_example)
                if example is None:
                    continue
                example_id = str(example["example_id"])
                current = example_map.get(example_id)
                if current is None or _example_quality(example) > _example_quality(current):
                    example_map[example_id] = example

    ranked = sorted(
        fields.values(),
        key=lambda item: (
            sum(item["corrections"].values())  # type: ignore[union-attr]
            + sum(item["manual_values"].values())  # type: ignore[union-attr]
            + len(item["examples"]) * 3,  # type: ignore[arg-type]
            str(item["field_name"]),
        ),
        reverse=True,
    )[:max_fields]

    result: list[dict[str, object]] = []
    for item in ranked:
        correction_map: dict[tuple[str, str, str], int] = item["corrections"]  # type: ignore[assignment]
        manual_map: dict[str, int] = item["manual_values"]  # type: ignore[assignment]
        example_map: dict[str, dict[str, object]] = item["examples"]  # type: ignore[assignment]
        corrections = sorted(correction_map.items(), key=lambda pair: (-pair[1], pair[0]))[
            :max_examples_per_field
        ]
        manual_values = sorted(manual_map.items(), key=lambda pair: (-pair[1], pair[0]))[
            :max_examples_per_field
        ]
        examples = sorted(example_map.values(), key=_example_quality, reverse=True)[:max_examples_per_field]
        result.append(
            {
                "field_name": item["field_name"],
                "label": item["label"],
                "edit_count": sum(count for _, count in corrections),
                "manual_fill_count": sum(count for _, count in manual_values),
                "example_count": len(examples),
                "corrections": [
                    {
                        "from": key[0],
                        "to": key[1],
                        **({"reason": key[2]} if key[2] else {}),
                        "count": count,
                    }
                    for key, count in corrections
                ],
                "manual_values": [{"value": value, "count": count} for value, count in manual_values],
                "examples": examples,
            }
        )
    return result


def _audit_rows() -> list[sqlite3.Row]:
    try:
        with connect() as db:
            return db.execute(
                """SELECT id,patient_id,document_id,field_name,old_value,new_value,reason,operation,timestamp
                   FROM audit_log
                   WHERE field_name IS NOT NULL
                     AND operation IN ('USER_EDIT','USER_EDIT_VERIFIED')
                   ORDER BY id DESC"""
            ).fetchall()
    except (sqlite3.Error, OSError):
        return []


def _local_learning_fields() -> list[dict[str, object]]:
    fields: dict[str, dict[str, object]] = {}

    def get_field(field_name: str) -> dict[str, object]:
        return fields.setdefault(
            field_name,
            {
                "field_name": field_name,
                "label": field_name,
                "corrections": Counter(),
                "manual_values": Counter(),
                "examples": [],
            },
        )

    audits = _audit_rows()
    audit_keys: dict[tuple[object, object, str], list[sqlite3.Row]] = {}
    for row in audits:
        field_name = _clean(row["field_name"], limit=128)
        if not _field_is_learnable(field_name, None):
            continue
        old_value = _clean(row["old_value"])
        new_value = _clean(row["new_value"])
        if new_value and old_value != new_value:
            reason = _clean(row["reason"], limit=_MAX_REASON)
            get_field(field_name)["corrections"][(old_value, new_value, reason)] += 1  # type: ignore[index]
        audit_keys.setdefault((row["patient_id"], row["document_id"], field_name), []).append(row)
        audit_keys.setdefault((row["patient_id"], None, field_name), []).append(row)

    try:
        with connect() as db:
            observations = db.execute(
                """SELECT o.id,o.patient_id,o.document_id,o.field_name,o.ai_value,o.current_value,
                          o.raw_text,o.confidence,o.status,o.source_mode,o.updated_at,
                          o.evidence_status,
                          d.document_type,d.width,d.height,r.result_json
                   FROM observations o
                   LEFT JOIN documents d ON d.id=o.document_id
                   LEFT JOIN ocr_results r ON r.document_id=o.document_id
                   WHERE o.current_value IS NOT NULL AND TRIM(o.current_value)<>''
                   ORDER BY o.updated_at DESC"""
            ).fetchall()
    except (sqlite3.Error, OSError):
        observations = []

    seen_examples: set[tuple[str, str]] = set()
    for row in observations:
        field_name = _clean(row["field_name"], limit=128)
        if not _field_is_learnable(field_name, None):
            continue
        current_value = _clean(row["current_value"])
        raw_text = _clean(row["raw_text"])
        item = get_field(field_name)

        if raw_text == _MANUAL_FILL_MARKER:
            item["manual_values"][current_value] += 1  # type: ignore[index]
            continue

        key = (row["patient_id"], row["document_id"], field_name)
        matching_audits = audit_keys.get(key) or audit_keys.get((row["patient_id"], None, field_name)) or []
        human_edited = bool(matching_audits)
        human_verified = str(row["status"] or "").upper() == "VERIFIED"
        if not human_verified and not human_edited:
            continue

        ai_value = _clean(row["ai_value"])
        reason = ""
        for audit in matching_audits:
            if _clean(audit["new_value"]) == current_value:
                reason = _clean(audit["reason"], limit=_MAX_REASON)
                break
        if not reason and matching_audits:
            reason = _clean(matching_audits[0]["reason"], limit=_MAX_REASON)

        evidence_rejected = str(row["evidence_status"] or "AUTO").upper() == "REJECTED"
        evidence = (
            {
                "text": "",
                "matched": False,
                "line_ids": [],
                "lines": [],
                "context_before": "",
                "context_after": "",
                "rejected_by_user": True,
            }
            if evidence_rejected
            else _locate_evidence(raw_text, row["result_json"], row["width"], row["height"])
        )
        value_changed = bool(ai_value and ai_value != current_value)
        learning_weight = 3.0 if value_changed else (2.0 if human_verified else 1.5)
        if evidence.get("matched"):
            learning_weight += 0.5
        example = {
            "document_type": _clean(row["document_type"], limit=128) or "OTHER",
            "ai_value": ai_value,
            "verified_value": current_value,
            "value_changed": value_changed,
            "human_verified": human_verified or human_edited,
            "correction_reason": reason,
            "learning_weight": learning_weight,
            "evidence_rejected": evidence_rejected,
            "evidence": evidence,
        }
        normalized = _normalize_example(field_name, example)
        if normalized is None:
            continue
        example_id = str(normalized["example_id"])
        dedupe_key = (field_name, example_id)
        if dedupe_key in seen_examples:
            continue
        seen_examples.add(dedupe_key)
        item["examples"].append(normalized)  # type: ignore[union-attr]

    result: list[dict[str, object]] = []
    for item in fields.values():
        corrections = [
            {
                "from": old_value,
                "to": new_value,
                **({"reason": reason} if reason else {}),
                "count": count,
            }
            for (old_value, new_value, reason), count in item["corrections"].items()  # type: ignore[union-attr]
        ]
        manual_values = [
            {"value": value, "count": count}
            for value, count in item["manual_values"].items()  # type: ignore[union-attr]
        ]
        result.append(
            {
                "field_name": item["field_name"],
                "label": item["label"],
                "corrections": corrections,
                "manual_values": manual_values,
                "examples": item["examples"],
            }
        )
    return result


def imported_text_learning_status() -> dict[str, object]:
    store = _read_imported_store()
    fields = store.get("fields") if isinstance(store.get("fields"), list) else []
    sources = store.get("sources") if isinstance(store.get("sources"), list) else []
    return {
        "source_count": len(sources),
        "field_count": len(fields),
        "correction_pattern_count": sum(
            len(field.get("corrections") or []) for field in fields if isinstance(field, dict)
        ),
        "manual_value_count": sum(
            len(field.get("manual_values") or []) for field in fields if isinstance(field, dict)
        ),
        "example_count": sum(
            len(field.get("examples") or []) for field in fields if isinstance(field, dict)
        ),
        "storage": f"database/learning/{_IMPORTED_FILENAME}",
    }


def import_text_learning_payload(payload: dict[str, object], *, source_name: str) -> dict[str, object]:
    normalized = _normalize_import_payload(payload)
    incoming_fields = normalized["fields"]
    if not isinstance(incoming_fields, list) or not incoming_fields:
        raise ValueError("学习 JSON 中没有可导入的有效文本学习记录")

    fingerprint = _fingerprint_fields(incoming_fields)
    store = _read_imported_store()
    sources = store.get("sources") if isinstance(store.get("sources"), list) else []
    if any(isinstance(item, dict) and item.get("fingerprint") == fingerprint for item in sources):
        return {
            "imported": False,
            "duplicate": True,
            "message": "这份学习记录已经导入过，没有重复增加权重",
            "skipped_fields": normalized["skipped_fields"],
            "skipped_entries": normalized["skipped_entries"],
            "status": imported_text_learning_status(),
        }

    existing_fields = store.get("fields") if isinstance(store.get("fields"), list) else []
    merged_fields = _merge_field_lists(
        [existing_fields, incoming_fields],
        max_fields=1000,
        max_examples_per_field=100,
    )
    now = datetime.now(UTC).isoformat()
    sources.append(
        {
            "fingerprint": fingerprint,
            "source_name": _clean(source_name, limit=255) or "imported-learning.json",
            "imported_at": now,
        }
    )
    _write_imported_store(
        {
            "version": 2,
            "type": "bce_imported_text_learning",
            "sources": sources,
            "fields": merged_fields,
        }
    )
    imported_examples = sum(
        len(field.get("examples") or []) for field in incoming_fields if isinstance(field, dict)
    )
    return {
        "imported": True,
        "duplicate": False,
        "source_name": _clean(source_name, limit=255),
        "fingerprint": fingerprint,
        "imported_field_count": len(incoming_fields),
        "imported_example_count": imported_examples,
        "skipped_fields": normalized["skipped_fields"],
        "skipped_entries": normalized["skipped_entries"],
        "status": imported_text_learning_status(),
    }


def build_text_learning_profile(
    allowed_fields: Iterable[str] | None = None,
    *,
    max_fields: int = 24,
    max_examples_per_field: int = 6,
) -> dict[str, object]:
    """Build few-shot field learning from current reviews plus imported records."""
    allowed = set(allowed_fields) if allowed_fields is not None else None
    imported = _read_imported_store()
    imported_fields = imported.get("fields") if isinstance(imported.get("fields"), list) else []
    merged = _merge_field_lists(
        [_local_learning_fields(), imported_fields],
        allowed_fields=allowed,
        max_fields=max_fields,
        max_examples_per_field=max_examples_per_field,
    )
    return {
        "version": 3,
        "source": "local_and_imported_learning",
        "learning_mode": "field_examples",
        "field_count": len(merged),
        "example_count": sum(int(field.get("example_count") or 0) for field in merged),
        "fields": merged,
        "imported_source_count": len(imported.get("sources") or []),
        "policy": {
            "learn": [
                "how_each_field_is_filled",
                "which_ocr_sentences_are_valid_evidence",
                "how_to_quote_minimal_raw_text_for_positioning",
            ],
            "never_copy_historical_patient_values": True,
            "require_current_ocr_evidence": True,
            "bbox_is_traceability_not_cross_patient_rule": True,
        },
    }


def _prompt_learning_payload(profile: dict[str, object]) -> dict[str, object]:
    """Drop pixel metadata before prompt injection; keep semantic evidence/context."""
    prompt_fields: list[dict[str, object]] = []
    for field in profile.get("fields") or []:
        if not isinstance(field, dict):
            continue
        examples: list[dict[str, object]] = []
        for example in field.get("examples") or []:
            if not isinstance(example, dict):
                continue
            evidence = example.get("evidence") if isinstance(example.get("evidence"), dict) else {}
            examples.append(
                {
                    "document_type": example.get("document_type"),
                    "ai_value": example.get("ai_value"),
                    "verified_value": example.get("verified_value"),
                    "value_changed": example.get("value_changed"),
                    "correction_reason": example.get("correction_reason"),
                    "evidence_text": (
                        evidence.get("text")
                        if isinstance(evidence, dict) and not example.get("evidence_rejected")
                        else ""
                    ),
                    "context_before": (
                        evidence.get("context_before")
                        if isinstance(evidence, dict) and not example.get("evidence_rejected")
                        else ""
                    ),
                    "context_after": (
                        evidence.get("context_after")
                        if isinstance(evidence, dict) and not example.get("evidence_rejected")
                        else ""
                    ),
                }
            )
        prompt_fields.append(
            {
                "field_name": field.get("field_name"),
                "corrections": field.get("corrections") or [],
                "examples": examples,
            }
        )
    return {
        "learning_mode": "few_shot_field_and_evidence_learning",
        "fields": prompt_fields,
    }


def text_learning_prompt_section(allowed_fields: Iterable[str] | None = None) -> str:
    profile = build_text_learning_profile(allowed_fields)
    if not profile["fields"]:
        return ""
    payload = json.dumps(_prompt_learning_payload(profile), ensure_ascii=False, separators=(",", ":"))
    return (
        "本地文本学习结果如下。以下是本机历史人工审核形成的字段学习样例。你必须自主归纳两个方面："
        "①该字段在什么原文条件下应如何填写/规范化；②什么样的OCR语句才是该字段的有效证据，"
        "raw_text应引用哪一段最小充分原文。examples中的evidence_text及其前后文用于学习证据选择；"
        "ai_value→verified_value用于学习历史误判与正确填写方式。"
        "这些都是历史病例样例，绝不能把历史患者的值复制到当前患者；也绝不能复制历史evidence_text。"
        "当前OCR没有相应证据时不得因为历史样例而填值；历史规则与当前OCR冲突时始终以当前OCR为准。"
        "导出JSON中的bbox/line_id只用于追溯和当前图片高亮，不作为跨病例像素位置规则。"
        "如果当前OCR中存在与历史样例相似的证据表达，应按历史人工审核形成的填写方式理解，"
        "同时raw_text仍须逐字引用当前OCR中的真实证据。\n"
        f"{payload}"
    )
