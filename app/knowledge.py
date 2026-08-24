import re
from functools import lru_cache
from itertools import combinations

import yaml

from app.config import settings
from app.derived_fields import expand_questionnaire_catalog
from app.text_learning import text_learning_prompt_section

IMAGING_MULTIPLICITY_FIELD = "pre_mmg_single_lesion"
IMAGING_DOCUMENT_TYPES = {"ULTRASOUND", "MAMMOGRAPHY", "MRI"}
IMAGING_MULTIPLICITY_RULE = {
    "id": "malignant_lesion_multiplicity_only",
    "field": IMAGING_MULTIPLICITY_FIELD,
    "description": (
        "只统计明确属于乳腺癌/恶性目标的病灶数量。多发良性结节、囊肿、纤维腺瘤或增生结节"
        "不能据此填写MULTIPLE；不能明确至少两个恶性病灶时不要输出MULTIPLE。"
    ),
}

DOCUMENT_FIELD_EXCLUSIONS = {
    "MEDICAL_RECORD_COVER": {"sex"},
}

DOCUMENT_FIELD_INCLUSIONS = {
    "MEDICAL_RECORD_COVER": {"contact"},
    # cT is an imaging-size assessment. Imaging pages expose the complete
    # clinical_stage field, while runtime signal gating decides whether the
    # expensive staging pass is actually needed.
    "ULTRASOUND": {"clinical_stage", IMAGING_MULTIPLICITY_FIELD},
    "MAMMOGRAPHY": {"clinical_stage", IMAGING_MULTIPLICITY_FIELD},
    "MRI": {"clinical_stage", IMAGING_MULTIPLICITY_FIELD},
    # Follow-up dates are stored in the followup group, but treatment records
    # are the preferred source and must therefore expose this field to the AI.
    "TREATMENT": {"last_visit_date"},
}

# Human review may always override a yes/no default to UNKNOWN, even where the
# source WPS form itself exposes only yes/no. This is an internal review option;
# the AI must not invent UNKNOWN when a document is merely silent.
HUMAN_YES_NO_OPTIONS = [
    {"label": "是", "value": "YES"},
    {"label": "否", "value": "NO"},
    {"label": "不详", "value": "UNKNOWN"},
]

PATIENT_LEVEL_BOOLEAN_POLICY = {
    "scope": "patient_level_after_all_current_documents",
    "field_type": "yes_no_unknown",
    "unmentioned_default": "NO",
    "default_provenance": "DEFAULT_UNMENTIONED",
    "human_overrides": ["YES", "NO", "UNKNOWN"],
    "document_level_rule": "单张病历未提及是否型字段时不要由AI输出NO或UNKNOWN；患者级汇总时再统一默认NO。",
}

ADMISSION_FOCUS_MARKERS = ("个人史", "家族史", "婚育史", "月经史", "既往史")
ADMISSION_FOCUS_TERMS = ("吸烟", "饮酒", "烟酒")

# Runtime wording can be clearer than the source form while keeping stable keys.
# These labels are used by review/data-preview/export without changing patient data.
QUESTIONNAIRE_FIELD_OVERRIDES = {
    "menarche_age": {
        "description": "初潮年龄必须填写阿拉伯数字整数，不接受文字或枚举值。",
    },
    "has_chronic_disease": {
        "label": "是否患慢性病",
    },
    "chronic_disease": {
        "label": "慢性病（可多选）",
        "description": "可同时选择高血压、糖尿病、冠心病和其他；多选按标准值顺序保存。",
    },
    "chronic_disease_other": {
        "label": "其他慢性病（请填写）",
    },
    # Keep the historical key so existing data stays readable, while presenting
    # this as one imaging-wide malignant-lesion question instead of a mammography child.
    IMAGING_MULTIPLICITY_FIELD: {
        "label": "影像学恶性病灶是否多发",
        "group": "pretreatment_imaging",
        "depends_on": None,
        "description": (
            "仅统计明确恶性/乳腺癌目标病灶。多个良性结节、囊肿、纤维腺瘤等不构成多发恶性病灶。"
        ),
    },
}


@lru_cache
def questionnaire_catalog() -> list[dict]:
    path = settings.knowledge_path / "schema" / "cohort_fields.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    fields = expand_questionnaire_catalog(payload["fields"])
    runtime_fields = [
        {**field, **QUESTIONNAIRE_FIELD_OVERRIDES.get(field["key"], {})}
        for field in fields
    ]
    multiplicity = next(
        (field for field in runtime_fields if field["key"] == IMAGING_MULTIPLICITY_FIELD), None
    )
    if multiplicity is not None:
        runtime_fields = [field for field in runtime_fields if field["key"] != IMAGING_MULTIPLICITY_FIELD]
        insert_at = next(
            (
                index for index, field in enumerate(runtime_fields)
                if str(field.get("group", "")).startswith("pretreatment_")
            ),
            len(runtime_fields),
        )
        runtime_fields.insert(insert_at, multiplicity)
    return runtime_fields


@lru_cache
def document_roi_catalog() -> dict[str, dict]:
    """Single source of truth for document types, ROI choices and AI target fields."""
    path = settings.knowledge_path / "schema" / "document_roi_mapping.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload.get("documents", {})


def document_target_fields(document_type: str) -> set[str]:
    # Legacy standalone IHC records are treated as biopsy pathology. New data
    # no longer exposes IHC as a separate document type.
    canonical_type = "BIOPSY_PATHOLOGY" if document_type == "IHC" else document_type
    definition = document_roi_catalog().get(canonical_type) or document_roi_catalog().get("OTHER", {})
    return {
        str(field_name)
        for region in definition.get("regions", [])
        for field_name in region.get("target_fields", [])
    }


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


def admission_focus_sections(ocr_text: str) -> str:
    """Surface high-value admission sections without adding another model call."""
    text = str(ocr_text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return ""
    marker_positions = sorted(
        (match.start(), marker)
        for marker in ADMISSION_FOCUS_MARKERS
        for match in re.finditer(re.escape(marker), text)
    )
    snippets: list[str] = []
    for index, (start, _marker) in enumerate(marker_positions):
        next_start = marker_positions[index + 1][0] if index + 1 < len(marker_positions) else len(text)
        snippets.append(text[start:min(next_start, start + 700)].strip())
    for term in ADMISSION_FOCUS_TERMS:
        for match in re.finditer(term, text):
            start = max(0, match.start() - 160)
            snippets.append(text[start:min(len(text), match.end() + 220)].strip())
    unique: list[str] = []
    for snippet in snippets:
        compact = " ".join(snippet.split())
        if compact and compact not in unique:
            unique.append(compact)
    return "\n---\n".join(unique)[:2600]


def _field_options_for_field(field: dict, option_index: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    options = [dict(item) for item in option_index.get(field["key"], [])]
    if field.get("type") == "yes_no_unknown":
        existing = {str(item["value"]).upper() for item in options}
        for option in HUMAN_YES_NO_OPTIONS:
            if option["value"] not in existing:
                options.append(dict(option))
    return options


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
            "field_options": _field_options_for_field(field, option_index),
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


def _prompt_preferences() -> dict:
    """Return extraction preferences without derived, read-only field names.

    Derived projections are produced only after human verification.  Keeping
    their names out of the extraction prompt prevents the model from trying to
    emit them while retaining the surrounding clinical rules.
    """
    derived_keys = {
        field["key"]
        for field in questionnaire_catalog()
        if field.get("capture") == "derived_readonly"
    }

    def strip(value):
        if isinstance(value, dict):
            return {
                key: strip(item)
                for key, item in value.items()
                if key not in derived_keys
            }
        if isinstance(value, list):
            return [
                strip(item)
                for item in value
                if not (isinstance(item, str) and item in derived_keys)
            ]
        return value

    return strip(data_processing_preferences())


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
    force_include_fields: bool = False,
) -> tuple[str, set[str]]:
    target_fields = document_target_fields(document_type)
    catalog = field_catalog()
    catalog = [field for field in catalog if field.get("key") in target_fields]

    included_for_document = DOCUMENT_FIELD_INCLUSIONS.get(document_type, set())
    if included_for_document:
        existing = {field["key"] for field in catalog}
        catalog.extend(
            field for field in questionnaire_catalog()
            if field["key"] in included_for_document and field["key"] not in existing
        )

    if include_fields is not None and force_include_fields:
        existing = {field["key"] for field in catalog}
        catalog.extend(
            field for field in questionnaire_catalog()
            if field["key"] in include_fields and field["key"] not in existing
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
    rules = list(document_rules().get(document_type, []))
    if document_type in IMAGING_DOCUMENT_TYPES:
        rules.append(IMAGING_MULTIPLICITY_RULE)
    preferences = _prompt_preferences()
    learning = text_learning_prompt_section(allowed)
    admission_focus = admission_focus_sections(ocr_text) if document_type == "ADMISSION" else ""
    focus_block = (
        "入院记录重点章节（仍须以原始OCR核对，只用于提高家族史和烟酒史等字段的注意力）：\n"
        f"{admission_focus}\n\n"
        if admission_focus else ""
    )
    prompt = (
        f"文档类型：{document_type}\n\n"
        "可抽取字段如下。field_name必须严格使用key；只返回本页有依据的非空字段。"
        "value必须使用字段values或form_options中定义的标准编码，不能返回中文显示标签或解释性句子；"
        "integer类型的value只能填写阿拉伯数字整数，不能填写文字；"
        "measurement_3d类型只记录实际出现的1–3个径线并用×连接；二维值写成25×18，末尾不要添加逗号、乘号或NA；"
        "multiselect类型如同时命中多个选项，按values定义顺序用英文逗号连接标准值，"
        "例如HYPERTENSION,DIABETES，不要只保留一个选项。"
        "yes_no_unknown类型如果本页没有明确相关记录，不要在单张文档层面输出NO或UNKNOWN；"
        "系统会在患者级汇总时把始终未提及的是否型题目统一默认成NO，人工审核仍可改为YES、NO或UNKNOWN：\n"
        f"{yaml.safe_dump(definitions, allow_unicode=True, sort_keys=False)}\n\n"
        "患者级是否题默认规则如下；该规则只用于最终患者汇总，不等同于本页病历明确记录：\n"
        f"{yaml.safe_dump(PATIENT_LEVEL_BOOLEAN_POLICY, allow_unicode=True, sort_keys=False)}\n\n"
        "该文档类型的专用抽取规则如下；专用规则优先于通用文字邻近判断：\n"
        f"{yaml.safe_dump(rules, allow_unicode=True, sort_keys=False)}\n\n"
        "本队列的数据处理偏好如下。推断值必须标记source_mode=INFERRED；前提不满足时使用NOT_APPLICABLE：\n"
        f"{yaml.safe_dump(preferences, allow_unicode=True, sort_keys=False)}\n\n"
        f"{learning + chr(10) + chr(10) if learning else ''}"
        "证据定位要求：raw_text必须尽量逐字引用当前OCR中的最小充分证据，不要改写、概括或仅返回字段值；"
        "这样系统才能把该字段自动定位回原图对应文字。若证据跨多行，可保留相邻原文并用换行连接。\n\n"
        f"{focus_block}"
        f"OCR文字：\n{ocr_text}"
    )
    return prompt, allowed
