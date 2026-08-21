from __future__ import annotations

import json
from collections import Counter
from typing import Iterable

from app.db import connect
from app.derived_fields import is_derived_field

LEARNING_EXCLUDED_FIELDS = {"record_number", "contact"}
LEARNING_OPERATIONS = {"USER_EDIT", "USER_EDIT_VERIFIED"}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _field_is_learnable(field_name: str, allowed_fields: set[str] | None) -> bool:
    if not field_name or field_name in LEARNING_EXCLUDED_FIELDS or is_derived_field(field_name):
        return False
    return allowed_fields is None or field_name in allowed_fields


def build_text_learning_profile(
    allowed_fields: Iterable[str] | None = None,
    *,
    max_fields: int = 24,
    max_examples_per_field: int = 6,
) -> dict[str, object]:
    """Summarize human corrections into compact, machine-readable learning data.

    The profile deliberately contains patterns/examples rather than model weights.
    It is rebuilt from the local audit trail for every extraction so new human
    corrections become available immediately and can always be audited or removed.
    """
    allowed = set(allowed_fields) if allowed_fields is not None else None
    fields: dict[str, dict[str, object]] = {}

    def get_field(field_name: str) -> dict[str, object]:
        return fields.setdefault(
            field_name,
            {
                "field_name": field_name,
                "edit_count": 0,
                "manual_fill_count": 0,
                "corrections": Counter(),
                "manual_values": Counter(),
            },
        )

    with connect() as db:
        audits = db.execute(
            """SELECT field_name,old_value,new_value,reason,operation
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

    for row in audits:
        field_name = _clean(row["field_name"])
        if not _field_is_learnable(field_name, allowed):
            continue
        old_value = _clean(row["old_value"])
        new_value = _clean(row["new_value"])
        if not new_value or old_value == new_value:
            continue
        reason = _clean(row["reason"])
        item = get_field(field_name)
        item["edit_count"] = int(item["edit_count"]) + 1
        item["corrections"][(old_value, new_value, reason)] += 1  # type: ignore[index]

    for row in manual_rows:
        field_name = _clean(row["field_name"])
        if not _field_is_learnable(field_name, allowed):
            continue
        value = _clean(row["current_value"])
        if not value:
            continue
        item = get_field(field_name)
        item["manual_fill_count"] = int(item["manual_fill_count"]) + 1
        item["manual_values"][value] += 1  # type: ignore[index]

    ranked = sorted(
        fields.values(),
        key=lambda item: (int(item["edit_count"]) + int(item["manual_fill_count"]), item["field_name"]),
        reverse=True,
    )[:max_fields]

    result_fields: list[dict[str, object]] = []
    for item in ranked:
        corrections = [
            {
                "from": old_value,
                "to": new_value,
                **({"reason": reason} if reason else {}),
                "count": count,
            }
            for (old_value, new_value, reason), count in item["corrections"].most_common(max_examples_per_field)  # type: ignore[union-attr]
        ]
        manual_values = [
            {"value": value, "count": count}
            for value, count in item["manual_values"].most_common(max_examples_per_field)  # type: ignore[union-attr]
        ]
        result_fields.append(
            {
                "field_name": item["field_name"],
                "edit_count": item["edit_count"],
                "manual_fill_count": item["manual_fill_count"],
                "corrections": corrections,
                "manual_values": manual_values,
            }
        )

    return {
        "version": 1,
        "source": "local_human_corrections",
        "field_count": len(result_fields),
        "fields": result_fields,
    }


def text_learning_prompt_section(allowed_fields: Iterable[str] | None = None) -> str:
    profile = build_text_learning_profile(allowed_fields)
    if not profile["fields"]:
        return ""
    payload = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    return (
        "本地文本学习结果如下（来自历史人工修改/补填）。这些内容只用于学习字段解释、格式和常见纠错模式；"
        "绝不能把历史患者的值复制到当前患者。只有当前OCR存在相应原文证据时才能采用学习结果。"
        "当历史纠正与当前OCR证据冲突时，以当前OCR为准；人工纠正模式可用于避免重复发生同类误判。\n"
        f"{payload}"
    )
