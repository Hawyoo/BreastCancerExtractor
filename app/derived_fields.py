from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

TNM_SOURCE_FIELDS = {
    "clinical_stage": ("clinical_t_component", "clinical_n_component", "clinical_m_component"),
    "pathological_stage": ("pathological_t_component", "pathological_n_component", "pathological_m_component"),
}

MEASUREMENT_SOURCE_FIELDS = (
    "pre_us_tumor_size_mm",
    "pre_mri_tumor_size_mm",
    "post_neoadj_us_size_mm",
    "post_neoadj_mri_size_mm",
)


def is_derived_field(field_name: str) -> bool:
    if field_name in {item for values in TNM_SOURCE_FIELDS.values() for item in values}:
        return True
    return bool(re.search(r"_dim[123]_mm$", field_name))


def _tnm_field_definitions(source: dict[str, Any]) -> list[dict[str, Any]]:
    source_key = str(source["key"])
    if source_key not in TNM_SOURCE_FIELDS:
        return []
    if source_key == "clinical_stage":
        labels = ("临床TNM：T（自动）", "临床TNM：N（自动）", "临床TNM：M（自动）")
    else:
        labels = ("病理TNM：T（自动）", "病理TNM：N（自动）", "病理TNM：M（自动）")
    return [
        {
            "key": key,
            "label": label,
            "group": source.get("group", "staging"),
            "type": "derived_tnm_component",
            "capture": "derived_readonly",
            "derived_from": source_key,
            "component": component,
            "description": "仅由人工确认后的完整TNM主字段自动拆分；只读，不允许单独修改。",
        }
        for key, label, component in zip(TNM_SOURCE_FIELDS[source_key], labels, ("T", "N", "M"))
    ]


def _measurement_field_definitions(source: dict[str, Any]) -> list[dict[str, Any]]:
    if source.get("type") != "measurement_3d":
        return []
    source_key = str(source["key"])
    labels = ("径线1", "径线2", "径线3")
    result = []
    for index, label in enumerate(labels, start=1):
        definition: dict[str, Any] = {
            "key": f"{source_key}_dim{index}_mm",
            "label": f"{source.get('label', source_key)}：{label}（自动，mm）",
            "group": source.get("group", "imaging"),
            "type": "derived_measurement",
            "unit": "mm",
            "capture": "derived_readonly",
            "derived_from": source_key,
            "dimension_index": index,
            "description": "仅由人工确认后的完整影像尺寸字符串按原文顺序自动拆分；只读，不允许单独修改。",
        }
        if source.get("depends_on") is not None:
            definition["depends_on"] = source["depends_on"]
        result.append(definition)
    return result


def expand_questionnaire_catalog(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Insert read-only derived fields immediately after their editable source field."""
    expanded: list[dict[str, Any]] = []
    for field in fields:
        expanded.append(field)
        expanded.extend(_tnm_field_definitions(field))
        expanded.extend(_measurement_field_definitions(field))
    return expanded


def parse_tnm_components(value: object) -> tuple[str, str, str] | None:
    text = str(value or "").strip().upper()
    text = re.sub(r"[\s,，;；]+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    match = re.fullmatch(r"(YC|YP|C|P)T(.+?)N(.+?)M(.+)", text)
    if not match:
        return None
    prefix = match.group(1).lower()
    return (
        f"{prefix}T{match.group(2)}",
        f"{prefix}N{match.group(3)}",
        f"{prefix}M{match.group(4)}",
    )


def _format_number(value: float) -> str:
    rounded = round(value, 6)
    if rounded.is_integer():
        return str(int(rounded))
    return (f"{rounded:.6f}").rstrip("0").rstrip(".")


def parse_measurement_components_mm(value: object) -> tuple[str | None, str | None, str | None] | None:
    """Parse 1-3 source-order dimensions and normalize cm to mm.

    The editable master value is never rewritten. These values are only a
    read-only projection after human verification.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        raw_values = list(value)[:3]
        numbers = [float(item) for item in raw_values if item not in (None, "")]
        if not numbers:
            return None
        formatted = [_format_number(number) for number in numbers]
        return tuple((formatted + [None, None, None])[:3])  # type: ignore[return-value]
    if isinstance(value, dict):
        raw_values = [value.get("length"), value.get("width"), value.get("height")]
        present = [item for item in raw_values if item not in (None, "")]
        if not present:
            return None
        formatted = [_format_number(float(item)) if item not in (None, "") else None for item in raw_values]
        return tuple(formatted)  # type: ignore[return-value]

    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError, json.JSONDecodeError):
        parsed = None
    if isinstance(parsed, (list, tuple, dict)):
        return parse_measurement_components_mm(parsed)

    unit_multiplier = 10.0 if re.search(r"(?:\bcm\b|厘米)", text, re.IGNORECASE) else 1.0
    cleaned = re.sub(r"(?:mm|cm|毫米|厘米)", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace("＊", "*")
    match = re.search(
        r"(-?\d+(?:\.\d+)?)\s*[×xX*]\s*(-?\d+(?:\.\d+)?)"
        r"(?:\s*[×xX*]\s*(-?\d+(?:\.\d+)?))?",
        cleaned,
    )
    if match:
        values = [match.group(1), match.group(2), match.group(3)]
    else:
        single = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*", cleaned)
        if not single:
            return None
        values = [single.group(1), None, None]
    formatted = [
        _format_number(float(item) * unit_multiplier) if item is not None else None
        for item in values
    ]
    return tuple(formatted)  # type: ignore[return-value]


def _derived_targets(source_field: str, source_value: object) -> dict[str, str | None]:
    if source_field in TNM_SOURCE_FIELDS:
        parsed = parse_tnm_components(source_value)
        if not parsed:
            return {}
        return dict(zip(TNM_SOURCE_FIELDS[source_field], parsed))
    if source_field in MEASUREMENT_SOURCE_FIELDS:
        parsed = parse_measurement_components_mm(source_value)
        if not parsed:
            return {}
        return {
            f"{source_field}_dim{index}_mm": component
            for index, component in enumerate(parsed, start=1)
        }
    return {}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def refresh_derived_observations(connection: sqlite3.Connection) -> int:
    """Materialize read-only projections from uniquely verified source fields.

    Derived observations are persisted so they travel inside patient.sqlite and
    appear in patient review/data preview/CSV, but they are always regenerated
    from their editable master field. If the master loses VERIFIED status or
    verified masters conflict, the projection is removed.
    """
    connection.row_factory = sqlite3.Row
    source_fields = tuple(TNM_SOURCE_FIELDS) + tuple(MEASUREMENT_SOURCE_FIELDS)
    placeholders = ",".join("?" for _ in source_fields)
    rows = connection.execute(
        f"""SELECT * FROM observations
            WHERE field_name IN ({placeholders}) AND status='VERIFIED'
            ORDER BY patient_id,field_name,updated_at DESC""",
        source_fields,
    ).fetchall()

    grouped: dict[tuple[int, str], list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault((int(row["patient_id"]), str(row["field_name"])), []).append(row)

    desired: dict[tuple[int, str], dict[str, Any]] = {}
    for (patient_id, source_field), candidates in grouped.items():
        unique_values = {str(row["current_value"] or "").strip() for row in candidates}
        unique_values.discard("")
        if len(unique_values) != 1:
            continue
        source = candidates[0]
        for target_field, target_value in _derived_targets(source_field, source["current_value"]).items():
            if target_value in (None, ""):
                continue
            desired[(patient_id, target_field)] = {
                "value": str(target_value),
                "source": source,
                "source_field": source_field,
            }

    target_fields = tuple(
        [item for values in TNM_SOURCE_FIELDS.values() for item in values]
        + [f"{source}_dim{index}_mm" for source in MEASUREMENT_SOURCE_FIELDS for index in (1, 2, 3)]
    )
    target_placeholders = ",".join("?" for _ in target_fields)
    existing_rows = connection.execute(
        f"""SELECT * FROM observations
            WHERE field_name IN ({target_placeholders}) AND source_mode='DERIVED'""",
        target_fields,
    ).fetchall()
    existing: dict[tuple[int, str], list[sqlite3.Row]] = {}
    for row in existing_rows:
        existing.setdefault((int(row["patient_id"]), str(row["field_name"])), []).append(row)

    changed = 0
    for key, rows_for_field in existing.items():
        if key in desired:
            continue
        for row in rows_for_field:
            connection.execute("DELETE FROM observations WHERE id=?", (row["id"],))
            changed += 1

    timestamp = _now()
    for (patient_id, field_name), item in desired.items():
        value = str(item["value"])
        source = item["source"]
        derivation_json = json.dumps(
            {
                "kind": "verified_master_projection",
                "source_field": item["source_field"],
                "source_observation_id": source["id"],
                "read_only": True,
            },
            ensure_ascii=False,
        )
        rows_for_field = existing.get((patient_id, field_name), [])
        current = rows_for_field[0] if rows_for_field else None
        if current is not None:
            needs_update = any(
                (
                    str(current["current_value"] or "") != value,
                    current["status"] != "VERIFIED",
                    current["confidence"] != "VERIFIED",
                    current["document_id"] != source["document_id"],
                    current["region_id"] != source["region_id"],
                    current["derivation_json"] != derivation_json,
                )
            )
            if needs_update:
                connection.execute(
                    """UPDATE observations SET document_id=?,region_id=?,ai_value=NULL,current_value=?,raw_text=?,
                       confidence='VERIFIED',status='VERIFIED',source_mode='DERIVED',derivation_json=?,
                       ruleset_version='derived-v1',model_name=NULL,model_digest=NULL,prompt_version=NULL,
                       ocr_version=?,updated_at=? WHERE id=?""",
                    (
                        source["document_id"],
                        source["region_id"],
                        value,
                        f"由已确认字段 {item['source_field']} 自动拆分",
                        derivation_json,
                        source["ocr_version"],
                        timestamp,
                        current["id"],
                    ),
                )
                changed += 1
            for duplicate in rows_for_field[1:]:
                connection.execute("DELETE FROM observations WHERE id=?", (duplicate["id"],))
                changed += 1
            continue

        observation_id = uuid.uuid5(uuid.NAMESPACE_URL, f"bce-derived:{patient_id}:{field_name}").hex
        connection.execute(
            """INSERT OR REPLACE INTO observations
               (id,patient_id,document_id,region_id,field_name,ai_value,current_value,raw_text,confidence,status,
                source_mode,derivation_json,ruleset_version,model_name,model_digest,prompt_version,ocr_version,
                created_at,updated_at)
               VALUES(?,?,?,?,?,NULL,?,?, 'VERIFIED','VERIFIED','DERIVED',?,'derived-v1',NULL,NULL,NULL,?,?,?)""",
            (
                observation_id,
                patient_id,
                source["document_id"],
                source["region_id"],
                field_name,
                value,
                f"由已确认字段 {item['source_field']} 自动拆分",
                derivation_json,
                source["ocr_version"],
                timestamp,
                timestamp,
            ),
        )
        changed += 1
    return changed
