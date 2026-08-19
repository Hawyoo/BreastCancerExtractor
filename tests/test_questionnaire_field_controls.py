from pathlib import Path

from app.main import observation_value_is_valid
from app.knowledge import questionnaire_field_index


ROOT = Path(__file__).parents[1]


def test_integer_fields_reject_free_text_hallucinations():
    metadata = questionnaire_field_index()["menarche_age"]
    assert metadata["field_type"] == "integer"
    assert observation_value_is_valid("menarche_age", "13")
    assert not observation_value_is_valid("menarche_age", "Heat")


def test_chronic_disease_is_a_real_multiselect():
    metadata = questionnaire_field_index()["chronic_disease"]
    assert metadata["field_type"] == "multiselect"
    assert [item["value"] for item in metadata["field_options"]] == [
        "HYPERTENSION",
        "DIABETES",
        "CORONARY_HEART_DISEASE",
        "OTHER",
    ]
    assert observation_value_is_valid("chronic_disease", "HYPERTENSION")
    assert observation_value_is_valid("chronic_disease", "HYPERTENSION,DIABETES")
    assert observation_value_is_valid("chronic_disease", "HYPERTENSION,DIABETES,OTHER")


def test_review_ui_uses_numeric_multiselect_and_nested_chronic_flow():
    javascript = (ROOT / "app/static/review_inline.js").read_text(encoding="utf-8")
    assert 'observation?.field_type !== "multiselect"' in javascript
    assert 'input.type = "number"' in javascript
    assert 'AI原值“${current}”不是数字' in javascript
    assert 'key === "chronic_disease"' in javascript
    assert 'key === "chronic_disease_other"' in javascript
    assert 'includes("OTHER")' in javascript
    assert 'has_chronic_disease: "是否患慢性病"' in javascript
    assert 'chronic_disease: "慢性病（可多选）"' in javascript
    assert 'chronic_disease_other: "其他慢性病（请填写）"' in javascript


def test_tnm_basis_is_hidden_for_non_tnm_fields():
    javascript = (ROOT / "app/static/review_inline.js").read_text(encoding="utf-8")
    assert 'const TNM_FIELDS = new Set(["clinical_stage", "pathological_stage"])' in javascript
    assert 'if (basisBox && !TNM_FIELDS.has(observation.field_name))' in javascript
    assert 'basisBox.hidden = true' in javascript
