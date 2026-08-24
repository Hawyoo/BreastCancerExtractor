from pathlib import Path

import yaml

from app.knowledge import questionnaire_field_index


ROOT = Path(__file__).parents[1]


def add_field(client, patient_id: int, field_name: str, value: str) -> dict:
    response = client.post(
        f"/api/patients/{patient_id}/observations",
        json={"field_name": field_name, "value": value, "confidence": "HIGH"},
    )
    assert response.status_code == 201
    return response.json()


def test_review_order_follows_the_approved_clinical_workflow():
    index = questionnaire_field_index()
    ordered = [
        "record_number",
        "smoking_history",
        "menarche_age",
        "has_family_history",
        "prior_breast_surgery",
        "has_chronic_disease",
        "metastatic_at_presentation",
        "pre_us_available",
        "pre_mri_available",
        "pre_mmg_available",
        "clinical_stage",
        "primary_biopsy_performed",
        "node_biopsy_performed",
        "metastasis_biopsy_performed",
        "neoadjuvant_received",
        "post_neoadj_us_available",
        "post_neoadj_mri_available",
        "surgery_performed",
        "postop_tumor_pathology_type",
        "fish_result",
        "post_neoadj_pcr",
        "post_neoadj_mp_grade",
        "post_neoadj_rcb_grade",
        "pathological_stage",
        "postoperative_chemotherapy",
        "postoperative_radiotherapy",
        "postoperative_endocrine",
        "postoperative_targeted",
        "postoperative_immunotherapy",
        "recurrence",
        "followup_metastasis",
        "second_primary_cancer",
        "death",
        "last_visit_date",
    ]
    positions = [index[key]["review_order"] for key in ordered]
    assert positions == sorted(positions)


def test_metastasis_biopsy_is_controlled_by_metastasis_at_presentation(client):
    index = questionnaire_field_index()
    assert index["metastasis_biopsy_performed"]["depends_on"] == {
        "field": "metastatic_at_presentation",
        "equals": "YES",
        "otherwise": "NOT_APPLICABLE",
    }

    patient = client.post("/api/patients", json={"patient_code": "review-order-001"}).json()
    presentation = add_field(client, patient["id"], "metastatic_at_presentation", "NO")
    hidden = client.get(
        f"/api/patients/{patient['id']}?review_blank_parents=true"
    ).json()
    assert "metastasis_biopsy_performed" not in {
        item["field_name"] for item in hidden["observations"]
    }

    response = client.patch(
        f"/api/observations/{presentation['id']}",
        json={"value": "YES", "operator": "reviewer", "reason": "确认来院时已有转移"},
    )
    assert response.status_code == 200
    revealed = client.get(
        f"/api/patients/{patient['id']}?review_blank_parents=true"
    ).json()
    by_field = {item["field_name"]: item for item in revealed["observations"]}
    assert by_field["metastatic_site"]["virtual_missing"] is True
    assert by_field["metastasis_biopsy_performed"]["virtual_missing"] is True


def test_no_age_or_post_neoadjuvant_mammography_fields_were_added():
    index = questionnaire_field_index()
    assert "age" not in index
    assert not any(key.startswith("post_neoadj_mmg") for key in index)


def test_regimen_naming_preferences_match_review_requirements():
    preferences = yaml.safe_load(
        (ROOT / "knowledge/rules/data_processing_preferences.yaml").read_text(encoding="utf-8")
    )
    naming = preferences["treatment_classification"]["regimen_naming"]
    assert "EC-T" in naming["chemotherapy"]["rule"]
    assert "HP" in naming["targeted"]["rule"]
    assert "中文原名" in naming["endocrine"]["rule"]
