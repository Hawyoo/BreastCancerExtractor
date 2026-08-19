from functools import lru_cache
from itertools import combinations

import yaml

from app.config import settings
from app.derived_fields import expand_questionnaire_catalog

DOCUMENT_GROUPS = {
    "MEDICAL_RECORD_COVER": {"demographics", "diagnosis", "staging"},
    "ADMISSION": {
        "demographics",
        "reproductive_history",
        "medical_history",
        "family_history",
        "lifestyle",
        "diagnosis",
        "staging",
    },
    "DISCHARGE": {"diagnosis", "staging", "surgery", "neoadjuvant", "adjuvant_treatment"},
    "ULTRASOUND": {"pretreatment_ultrasound", "post_neoadjuvant_imaging"},
    "MAMMOGRAPHY": {"pretreatment_mammography"},
    "MRI": {"pretreatment_mri", "post_neoadjuvant_imaging"},
    "BIOPSY_PATHOLOGY": {"primary_biopsy", "node_biopsy", "metastasis_biopsy", "biomarkers", "diagnosis", "staging"},
    "SURGICAL_PATHOLOGY": {"surgical_pathology", "biomarkers", "diagnosis", "staging", "treatment_response"},
    "IHC": {"primary_biopsy", "node_biopsy", "metastasis_biopsy", "surgical_pathology", "biomarkers"},
    # 手术记录只描述操作和术中所见，不能作为术后组织学、淋巴结病理或 p/ypTNM 的来源。
    "SURGERY": {"surgery"},
    "TREATMENT": {"neoadjuvant", "adjuvant_treatment", "palliative_treatment", "treatment_response"},
}

DOCUMENT_FIELD_EXCLUSIONS = {
    "MEDICAL_RECORD_COVER": {"sex"},
}

# Direct identifiers remain manual_restricted by default. The cohort explicitly
# requires the contact number to be extracted from the medical-record cover,
# so this one document-specific exception is intentionally narrow.
DOCUMENT_FIELD_INCLUSIONS = {
    "MEDICAL_RECORD_COVER": {"contact"},
}


@lru_cache
def questionnaire_catalog() -> list[dict]:
    path = settings.knowledge_path / "schema" / "cohort_fields.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return expand_questionnaire_catalog(payload["fields"])


@lru_cache
def questionnaire_option_index() -> dict[str, list[dict[str, str]]]:
    path = settings.knowledge_path / "schema" / "wps_form_2026_04_09.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    result: dict[str, list[dict[str, str]]] = {}
    for key, definition in payload.get("choice_fields", {}).items():
        raw_options = definition.get("options") or {}
        options = [{"label": str(label), "value": str(value)} for label, value in raw_options.items()]
        targets = definition.get("fields") or ([key] if key != "yes_no" else [])
        for target in targets:
            result[target] = options
    for definition in payload.get("composite_fields", {}).values():
        raw_options = definition.get("options") or {}
        options = [{"label": str(label), "value": str(value)} for label, value in raw_options.items()]
        for target in definition.get("fields", []):
            result[target] = options
    return result


def _allowed_values_for_field(field: dict) -> object:
    """Return validator-friendly values for typed questionnaire fields.

    app.main already rejects values outside ``allowed_values``. Give integer
    and multiselect fields an explicit validation domain so arbitrary model
    text such as ``Heat`` cannot be accepted for an age/count field and a
    multi-choice answer can contain more than one canonical option.
    """
    values = field.get("values")
    field_type = field.get("type", "string")
    if field_type == "integer" and not values:
        # Questionnaire integer fields are non-negative ages/counts/cycles.
        # A generous bound prevents free-text hallucinations without imposing
        # a narrow clinical range on manually documented values.
        return range(0, 10000)
    if field_type == "multiselect" and values:
        ordered = [str(value) for value in values]
        return [
            ",".join(selection)
            for size in range(1, len(ordered) + 1)
            for selection in combinations(ordered, size)
        ]
    return values


@lru_cache
def field_catalog() -> list[dict]:
    return [
        field for field in questionnaire_catalog()
        if field.get("capture") not in {"manual_restricted", "derived_readonly"}
    ]


@lru_cache
def questionnaire_field_index() -> dict[str, dict]:
    option_index = questionnaire_option_index()
    return {
        field["key"]: {
            "field_order": index,
            "field_label": field["label"],
            "field_group": field.get("group", "other"),
            "field_type": field.get("type", "string"),
            "allowed_values": _allowed_values_for_field(field),
            "field_options": option_index.get(field["key"], []),
            "depends_on": field.get("depends_on"),
            "capture": field.get("capture"),
            "derived_from": field.get("derived_from"),
        }
        for index, field in enumerate(questionnaire_catalog())
    }


@lru_cache
def document_rules() -> dict[str, list[dict]]:
    path = settings.knowledge_path / "rules" / "document_rules.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload.get("document_rules", {})


@lru_cache
def data_processing_preferences() -> dict:
    path = settings.knowledge_path / "rules" / "data_processing_preferences.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def source_priority(field_name: str, document_type: str | None) -> int:
    """Return the configured source rank for a questionnaire field.

    Human verification still outranks every document source; this rank is used
    to choose between otherwise comparable AI/recorded candidates.
    """
    rules = data_processing_preferences().get("source_priority", {})
    configured = rules.get(field_name)
    if configured is None:
        for name, definition in rules.items():
            if name.startswith("_") and field_name in definition.get("fields", []):
                configured = definition
                break
    if not configured or not document_type:
        return 0
    ordered = configured.get("ordered_documents", [])
    try:
        return len(ordered) - ordered.index(document_type)
    except ValueError:
        return 0


def extraction_prompt(
    document_type: str,
    ocr_text: str,
    *,
    include_fields: set[str] | None = None,
    exclude_fields: set[str] | None = None,
) -> tuple[str, set[str]]:
    groups = DOCUMENT_GROUPS.get(document_type)
    catalog = field_catalog()
    if groups:
        catalog = [field for field in catalog if field.get("group") in groups]

    included_for_document = DOCUMENT_FIELD_INCLUSIONS.get(document_type, set())
    if included_for_document:
        existing = {field["key"] for field in catalog}
        catalog.extend(
            field for field in questionnaire_catalog()
            if field["key"] in included_for_document and field["key"] not in existing
        )

    excluded_for_document = DOCUMENT_FIELD_EXCLUSIONS.get(document_type, set())
    if excluded_for_document:
        catalog = [field for field in catalog if field.get("key") not in excluded_for_document]
    if include_fields is not None:
        catalog = [field for field in catalog if field.get("key") in include_fields]
    if exclude_fields:
        catalog = [field for field in catalog if field.get("key") not in exclude_fields]
    definitions = [
        {
            key: field.get(key)
            for key in (
                "key", "label", "group", "type", "values", "unit", "dimensions", "optional_dimensions",
                "depends_on", "form_type", "form_options", "normalization", "single_value_per_context",
                "exclude_markers", "description", "allowed_prefixes", "required_components",
                "source_strategy",
            )
            if field.get(key) is not None
        }
        for field in catalog
    ]
    allowed = {field["key"] for field in catalog}
    rules = document_rules().get(document_type, [])
    preferences = data_processing_preferences()
    prompt = (
        f"文档类型：{document_type}\n\n"
        "可抽取字段如下。field_name必须严格使用key；只返回本页有依据的非空字段。"
        "integer类型的value只能填写阿拉伯数字整数，不能填写文字；"
        "multiselect类型如同时命中多个选项，按values定义顺序用英文逗号连接标准值，"
        "例如HYPERTENSION,DIABETES，不要只保留一个选项：\n"
        f"{yaml.safe_dump(definitions, allow_unicode=True, sort_keys=False)}\n\n"
        "该文档类型的专用抽取规则如下；专用规则优先于通用文字邻近判断：\n"
        f"{yaml.safe_dump(rules, allow_unicode=True, sort_keys=False)}\n\n"
        "本队列的数据处理偏好如下。推断值必须标记source_mode=INFERRED；前提不满足时使用NOT_APPLICABLE：\n"
        f"{yaml.safe_dump(preferences, allow_unicode=True, sort_keys=False)}\n\n"
        f"OCR文字：\n{ocr_text}"
    )
    return prompt, allowed
