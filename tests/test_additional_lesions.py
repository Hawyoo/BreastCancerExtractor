import json
from pathlib import Path

from app.knowledge import extraction_prompt, questionnaire_catalog, questionnaire_field_index
from app.models import ADDITIONAL_LESION_FIELD_PREFIX, ADDITIONAL_LESION_SCHEMA


def create_patient(client, code: str = "multi-lesion-001") -> dict:
    response = client.post("/api/patients", json={"patient_code": code})
    assert response.status_code == 201
    return response.json()


def add_patient_field(client, patient_id: int, field_name: str, value: str) -> dict:
    response = client.post(
        f"/api/patients/{patient_id}/observations",
        json={
            "field_name": field_name,
            "value": value,
            "confidence": "LOW",
            "source_mode": "RECORDED",
            "operator": "local-user",
        },
    )
    assert response.status_code == 201
    return response.json()


def lesion_payload(**overrides) -> dict:
    payload = {
        "active": True,
        "lesion_label": "右乳病灶",
        "laterality": "RIGHT",
        "location": "外上象限",
        "size_text": "23×18,NA mm",
        "ultrasound_detail": "右乳外上象限低回声肿块23×18 mm",
        "mammography_detail": "",
        "mri_detail": "",
        "pathology_type": "浸润性导管癌",
        "pathology_grade": "2",
        "er": "POSITIVE 90%",
        "pr": "NEGATIVE",
        "her2": "2+",
        "ki67": "30%",
        "other_ihc": "GATA3+",
        "malignancy_basis": "右乳穿刺病理：浸润性导管癌",
        "operator": "reviewer",
    }
    payload.update(overrides)
    return payload


def test_imaging_multiplicity_is_an_imaging_wide_question():
    field = questionnaire_field_index()["pre_mmg_single_lesion"]
    assert field["field_label"] == "影像学恶性病灶是否多发"
    assert field["field_group"] == "pretreatment_imaging"
    assert field["depends_on"] is None
    assert field["field_options"] == [
        {"label": "单发", "value": "SINGLE"},
        {"label": "多发", "value": "MULTIPLE"},
    ]
    keys = [item["key"] for item in questionnaire_catalog()]
    assert keys.index("pre_mmg_single_lesion") < keys.index("pre_us_available")
    for document_type in ("ULTRASOUND", "MAMMOGRAPHY", "MRI"):
        prompt, allowed = extraction_prompt(document_type, "左乳恶性病灶两枚；另见多个良性囊肿")
        assert "pre_mmg_single_lesion" in allowed
        assert "多发良性结节" in prompt


def test_additional_lesion_requires_bilateral_or_multiple_patient_state(client):
    patient = create_patient(client)
    response = client.post(
        f"/api/patients/{patient['id']}/additional-lesions",
        json=lesion_payload(),
    )
    assert response.status_code == 409
    assert "双侧" in response.json()["detail"]


def test_multiple_malignant_lesions_coexist_without_field_conflict(client):
    patient = create_patient(client)
    add_patient_field(client, patient["id"], "pre_mmg_single_lesion", "MULTIPLE")
    first = client.post(
        f"/api/patients/{patient['id']}/additional-lesions",
        json=lesion_payload(),
    )
    second = client.post(
        f"/api/patients/{patient['id']}/additional-lesions",
        json=lesion_payload(lesion_label="左乳第二病灶", laterality="LEFT", er="NEGATIVE"),
    )
    assert first.status_code == second.status_code == 201

    detail = client.get(f"/api/patients/{patient['id']}").json()
    lesions = [
        item for item in detail["observations"]
        if item["field_name"].startswith(ADDITIONAL_LESION_FIELD_PREFIX)
    ]
    assert len(lesions) == 2
    assert not any(item["candidate_conflict"] for item in lesions)
    payloads = [json.loads(item["current_value"]) for item in lesions]
    assert {item["lesion_number"] for item in payloads} == {2, 3}
    assert {item["er"] for item in payloads} == {"POSITIVE 90%", "NEGATIVE"}
    assert all(item["schema"] == ADDITIONAL_LESION_SCHEMA for item in payloads)
    assert payloads[0]["size_text"] == "23×18 mm"


def test_bilateral_single_case_allows_only_one_additional_lesion(client):
    patient = create_patient(client)
    add_patient_field(client, patient["id"], "breast_laterality", "BILATERAL")
    assert client.post(
        f"/api/patients/{patient['id']}/additional-lesions", json=lesion_payload()
    ).status_code == 201
    repeated = client.post(
        f"/api/patients/{patient['id']}/additional-lesions", json=lesion_payload(lesion_label="第三病灶")
    )
    assert repeated.status_code == 409
    assert "只能增加另一侧病灶" in repeated.json()["detail"]


def test_benign_basis_and_generic_special_field_bypass_are_rejected(client):
    patient = create_patient(client)
    add_patient_field(client, patient["id"], "pre_mmg_single_lesion", "MULTIPLE")
    benign = client.post(
        f"/api/patients/{patient['id']}/additional-lesions",
        json=lesion_payload(malignancy_basis="多发纤维腺瘤，考虑良性"),
    )
    assert benign.status_code == 422

    bypass = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": f"{ADDITIONAL_LESION_FIELD_PREFIX}fake",
            "value": "plain text",
            "operator": "local-user",
        },
    )
    assert bypass.status_code == 422


def test_existing_lesion_can_be_deactivated_after_eligibility_is_removed(client):
    patient = create_patient(client)
    multiplicity = add_patient_field(client, patient["id"], "pre_mmg_single_lesion", "MULTIPLE")
    created = client.post(
        f"/api/patients/{patient['id']}/additional-lesions", json=lesion_payload()
    ).json()
    client.patch(
        f"/api/observations/{multiplicity['id']}",
        json={"value": "SINGLE", "operator": "local-user", "reason": "更正为单发"},
    )

    cannot_edit = client.patch(
        f"/api/additional-lesions/{created['id']}", json=lesion_payload(location="中央区")
    )
    assert cannot_edit.status_code == 409
    deactivated = client.patch(
        f"/api/additional-lesions/{created['id']}", json=lesion_payload(active=False)
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False


def test_frontend_exposes_add_lesion_button_and_repeated_tumor_fields():
    root = Path(__file__).parents[1]
    script = (root / "app/static/additional_lesions.js").read_text(encoding="utf-8")
    assert 'add.textContent = "增加病灶"' in script
    for key in ("size_text", "ultrasound_detail", "mammography_detail", "mri_detail",
                "pathology_type", "pathology_grade", "er", "pr", "her2", "ki67", "other_ihc"):
        assert key in script
    shutdown = (root / "app/static/shutdown.js").read_text(encoding="utf-8")
    assert 'lesionScript.src = "/additional_lesions.js"' in shutdown
    app_script = (root / "app/static/app.js").read_text(encoding="utf-8")
    assert '.startsWith("additional_malignant_lesion:")' in app_script
