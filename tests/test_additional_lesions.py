import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.knowledge import extraction_prompt, field_catalog, questionnaire_field_index
from app.models import ADDITIONAL_LESION_SCHEMA, ObservationCreate, ObservationEdit

ROOT = Path(__file__).parents[1]
MULTIPLICITY_FIELD = "pre_mmg_single_lesion"


def lesion_payload(*, basis: str, triggers: list[str] | None = None) -> str:
    return json.dumps(
        {
            "schema": ADDITIONAL_LESION_SCHEMA,
            "active": True,
            "lesion_number": 2,
            "malignancy_confirmed": True,
            "malignancy_basis": basis,
            "trigger_basis": triggers or ["MULTIPLE"],
            "laterality": "LEFT",
            "location": "10点钟",
            "size_text": "超声18×12 mm；MRI 20×14 mm",
            "imaging_detail": "超声10点钟18×12 mm；MRI同部位20×14 mm",
            "er": "POSITIVE",
        },
        ensure_ascii=False,
    )


def test_mammography_historical_key_is_promoted_to_imaging_wide_question():
    field = questionnaire_field_index()[MULTIPLICITY_FIELD]
    assert field["field_label"] == "影像学恶性病灶是否多发"
    assert field["field_group"] == "pretreatment_imaging"
    assert field["depends_on"] is None
    assert field["field_options"] == [
        {"label": "单发", "value": "SINGLE"},
        {"label": "多发", "value": "MULTIPLE"},
    ]


@pytest.mark.parametrize("document_type", ["ULTRASOUND", "MAMMOGRAPHY", "MRI"])
def test_all_breast_imaging_documents_can_extract_malignant_multiplicity(document_type: str):
    prompt, allowed = extraction_prompt(document_type, "左乳恶性病灶两枚；另见多个良性囊肿")
    assert MULTIPLICITY_FIELD in allowed
    assert "多个良性结节" in prompt
    assert "绝不能据此输出MULTIPLE" in prompt


def test_imaging_multiplicity_inclusion_does_not_open_the_whole_general_imaging_group():
    for document_type in ("ULTRASOUND", "MAMMOGRAPHY", "MRI"):
        _, allowed = extraction_prompt(document_type, "test")
        assert MULTIPLICITY_FIELD in allowed
        assert "other_pretreatment_imaging" not in allowed


def test_ai_field_catalog_does_not_contain_additional_lesion_prefix():
    assert not any(field["key"].startswith("additional_malignant_lesion:") for field in field_catalog())


def test_explicit_malignancy_is_required_for_additional_lesion_create():
    valid = lesion_payload(basis="右乳病理：浸润性导管癌")
    created = ObservationCreate(
        field_name="additional_malignant_lesion:test",
        value=valid,
        raw_text="右乳病理：浸润性导管癌",
        confidence="LOW",
        source_mode="RECORDED",
    )
    assert created.value == valid

    with pytest.raises(ValidationError):
        ObservationCreate(
            field_name="additional_malignant_lesion:benign",
            value=lesion_payload(basis="超声示多发纤维腺瘤，考虑良性"),
            confidence="LOW",
            source_mode="RECORDED",
        )


def test_additional_lesion_prefix_cannot_bypass_structured_schema():
    with pytest.raises(ValidationError):
        ObservationCreate(
            field_name="additional_malignant_lesion:plain-text",
            value="普通文本，绕过结构化校验",
            confidence="LOW",
            source_mode="RECORDED",
        )


def test_negative_malignancy_statement_is_rejected_on_edit_too():
    with pytest.raises(ValidationError):
        ObservationEdit(
            value=lesion_payload(basis="该结节未见恶性证据"),
            operator="local-user",
        )


def test_additional_lesion_requires_bilateral_or_multiple_trigger():
    with pytest.raises(ValidationError):
        ObservationCreate(
            field_name="additional_malignant_lesion:no-trigger",
            value=lesion_payload(basis="明确恶性病灶", triggers=["SINGLE"]),
            confidence="LOW",
            source_mode="RECORDED",
        )


def test_additional_lesion_cannot_be_ai_inferred():
    with pytest.raises(ValidationError):
        ObservationCreate(
            field_name="additional_malignant_lesion:ai",
            value=lesion_payload(basis="明确恶性病灶"),
            confidence="LOW",
            source_mode="INFERRED",
            inference_basis=[{"fact": "model guess"}],
            ruleset_version="test",
        )


def test_frontend_only_opens_exception_layer_for_bilateral_or_multiple_and_requires_malignancy():
    script = (ROOT / "app/static/additional_lesions.js").read_text(encoding="utf-8")
    assert 'laterality === "BILATERAL"' in script
    assert 'multiplicity === "MULTIPLE"' in script
    assert "malignantBasisIsValid" in script
    assert "多发良性结节、囊肿或纤维腺瘤不能添加" in script
    assert 'confidence: "LOW"' in script
    assert "/verify" in script


def test_existing_lesions_remain_visible_if_eligibility_is_later_removed():
    script = (ROOT / "app/static/additional_lesions.js").read_text(encoding="utf-8")
    assert "panel.hidden = !eligibility.eligible && records.length === 0" in script
    assert "旧记录仅可查看或停用" in script
    assert "if (eligibility.eligible) panel.appendChild(buildCreateForm" in script


def test_additional_lesion_can_preserve_multiple_imaging_findings_without_entity_tree():
    script = (ROOT / "app/static/additional_lesions.js").read_text(encoding="utf-8")
    assert "imaging_detail" in script
    assert "各影像检查补充" in script


def test_additional_lesion_is_observation_exception_not_new_database_entity_table():
    db_source = (ROOT / "app/db.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS additional_lesions" not in db_source
    policy = (ROOT / "knowledge/rules/additional_lesion_policy.yaml").read_text(encoding="utf-8")
    assert "observation_exception_layer" in policy
    assert "Patient Package" in policy


def test_loader_starts_additional_lesion_ui_after_inline_review():
    shutdown = (ROOT / "app/static/shutdown.js").read_text(encoding="utf-8")
    assert 'reviewScript.onload = loadAdditionalLesions' in shutdown
    assert 'script.src = "/additional_lesions.js"' in shutdown
