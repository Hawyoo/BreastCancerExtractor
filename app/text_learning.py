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
_MAX_TEXT = 2000
_MAX_REASON = 1000
_MAX_COUNT = 1_000_000


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
        "version": 1,
        "source": source,
        "field_count": 0,
        "fields": [],
    }


def _imported_path() -> Path:
    return settings.data_path / "learning" / _IMPORTED_FILENAME


def _empty_imported_store() -> dict[str, object]:
    return {
        "version": 1,
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


def _normalize_import_payload(payload: dict[str, object]) -> dict[str, object]:
    kind = payload.get("type")
    if kind not in (None, "bce_text_learning", "bce_imported_text_learning"):
        raise ValueError("不是 BCE 文本学习 JSON")
    try:
        version = int(payload.get("version", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("学习 JSON version 无效") from exc
    if version not in {1, 2}:
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

        if not corrections and not manual_values:
            skipped_fields += 1
            continue
        fields.append(
            {
                "field_name": field_name,
                "label": _clean(raw.get("label"), limit=200) or field_name,
                "corrections": corrections,
                "manual_values": manual_values,
            }
        )

    return {
        "version": 1,
        "source": "imported_text_learning",
        "fields": fields,
        "skipped_fields": skipped_fields,
        "skipped_entries": skipped_entries,
    }


def _fingerprint_fields(fields: list[dict[str, object]]) -> str:
    canonical = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _merge_field_lists(
    profiles: Iterable[list[dict[str, object]]],
    *,
    allowed_fields: set[str] | None = None,
    max_fields: int = 24,
    max_examples_per_field: int = 6,
) -> list[dict[str, object]]:
    """Merge learning sources without inflating identical migrated examples.

    For an identical correction/manual value we retain the largest observed count
    across sources instead of summing it. This makes export -> import -> export
    migrations idempotent and prevents repeatedly importing the same history from
    artificially increasing one rule's weight.
    """
    fields: dict[str, dict[str, object]] = {}

    def item_for(field_name: str, label: str = "") -> dict[str, object]:
        item = fields.setdefault(
            field_name,
            {
                "field_name": field_name,
                "label": label or field_name,
                "corrections": {},
                "manual_values": {},
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

    ranked = sorted(
        fields.values(),
        key=lambda item: (
            sum(item["corrections"].values()) + sum(item["manual_values"].values()),  # type: ignore[union-attr]
            str(item["field_name"]),
        ),
        reverse=True,
    )[:max_fields]

    result: list[dict[str, object]] = []
    for item in ranked:
        correction_map: dict[tuple[str, str, str], int] = item["corrections"]  # type: ignore[assignment]
        manual_map: dict[str, int] = item["manual_values"]  # type: ignore[assignment]
        corrections = sorted(correction_map.items(), key=lambda pair: (-pair[1], pair[0]))[:max_examples_per_field]
        manual_values = sorted(manual_map.items(), key=lambda pair: (-pair[1], pair[0]))[:max_examples_per_field]
        result.append(
            {
                "field_name": item["field_name"],
                "label": item["label"],
                "edit_count": sum(count for _, count in corrections),
                "manual_fill_count": sum(count for _, count in manual_values),
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
            }
        )
    return result


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
            },
        )

    try:
        with connect() as db:
            audits = db.execute(
                """SELECT field_name,old_value,new_value,reason
                   FROM audit_log
                   WHERE field_name IS NOT NULL
                     AND operation IN ('USER_EDIT','USER_EDIT_VERIFIED')
                   ORDER BY id DESC"""
            ).fetchall()
            manual_rows = db.execute(
                """SELECT field_name,current_value
                   FROM observations
                   WHERE raw_text='人工手动补充'
                     AND current_value IS NOT NULL
                     AND TRIM(current_value)<>''
                   ORDER BY updated_at DESC"""
            ).fetchall()
    except (sqlite3.Error, OSError):
        return []

    for row in audits:
        field_name = _clean(row["field_name"], limit=128)
        if not _field_is_learnable(field_name, None):
            continue
        old_value = _clean(row["old_value"])
        new_value = _clean(row["new_value"])
        if not new_value or old_value == new_value:
            continue
        reason = _clean(row["reason"], limit=_MAX_REASON)
        item = get_field(field_name)
        item["corrections"][(old_value, new_value, reason)] += 1  # type: ignore[index]

    for row in manual_rows:
        field_name = _clean(row["field_name"], limit=128)
        if not _field_is_learnable(field_name, None):
            continue
        value = _clean(row["current_value"])
        if not value:
            continue
        item = get_field(field_name)
        item["manual_values"][value] += 1  # type: ignore[index]

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
        result.append({**item, "corrections": corrections, "manual_values": manual_values})
    return result


def imported_text_learning_status() -> dict[str, object]:
    store = _read_imported_store()
    fields = store.get("fields") if isinstance(store.get("fields"), list) else []
    sources = store.get("sources") if isinstance(store.get("sources"), list) else []
    return {
        "source_count": len(sources),
        "field_count": len(fields),
        "correction_pattern_count": sum(len(field.get("corrections") or []) for field in fields if isinstance(field, dict)),
        "manual_value_count": sum(len(field.get("manual_values") or []) for field in fields if isinstance(field, dict)),
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
            "version": 1,
            "type": "bce_imported_text_learning",
            "sources": sources,
            "fields": merged_fields,
        }
    )
    return {
        "imported": True,
        "duplicate": False,
        "source_name": _clean(source_name, limit=255),
        "fingerprint": fingerprint,
        "imported_field_count": len(incoming_fields),
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
    """Merge current human corrections with portable imported learning records."""
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
        "version": 1,
        "source": "local_and_imported_learning",
        "field_count": len(merged),
        "fields": merged,
        "imported_source_count": len(imported.get("sources") or []),
    }


def text_learning_prompt_section(allowed_fields: Iterable[str] | None = None) -> str:
    profile = build_text_learning_profile(allowed_fields)
    if not profile["fields"]:
        return ""
    payload = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    return (
        "本地文本学习结果如下（来自当前人工修改/补填与已导入学习记录）。这些内容只用于学习字段解释、格式和常见纠错模式；"
        "绝不能把历史患者的值复制到当前患者。只有当前OCR存在相应原文证据时才能采用学习结果。"
        "当历史纠正与当前OCR证据冲突时，以当前OCR为准；人工纠正模式可用于避免重复发生同类误判。\n"
        f"{payload}"
    )
