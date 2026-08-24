from pathlib import Path

from app.main import suggested_review_document_id

ROOT = Path(__file__).parents[1]


def add_manual_field(client, patient_id: int, field_name: str, value: str):
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


def test_blank_root_and_parent_questions_enter_review_without_polluting_plain_detail(client):
    patient = client.post("/api/patients", json={"patient_code": "blank-parent-001"}).json()

    plain = client.get(f"/api/patients/{patient['id']}").json()
    assert plain["observations"] == []

    review = client.get(
        f"/api/patients/{patient['id']}?review_blank_parents=true"
    ).json()
    by_field = {item["field_name"]: item for item in review["observations"]}

    for field_name in ("clinical_stage", "neoadjuvant_received", "primary_biopsy_performed"):
        assert by_field[field_name]["current_value"] == ""
        assert by_field[field_name]["status"] == "REVIEW_REQUIRED"
        assert by_field[field_name]["virtual_missing"] is True

    # Conditional parents are not shown before their own prerequisite applies.
    assert "primary_pr" not in by_field
    assert "primary_pr_detail" not in by_field
    assert review["status"] == "REVIEW_REQUIRED"

    listed = client.get("/api/patients").json()
    listed_patient = next(item for item in listed if item["id"] == patient["id"])
    assert listed_patient["review_count"] == len(review["observations"])
    assert listed_patient["status"] == "REVIEW_REQUIRED"


def test_manual_parent_answer_reveals_only_applicable_conditional_parent(client):
    patient = client.post("/api/patients", json={"patient_code": "blank-parent-002"}).json()
    add_manual_field(client, patient["id"], "primary_biopsy_performed", "YES")

    review = client.get(
        f"/api/patients/{patient['id']}?review_blank_parents=true"
    ).json()
    by_field = {item["field_name"]: item for item in review["observations"]}

    assert by_field["primary_biopsy_performed"]["status"] == "VERIFIED"
    assert by_field["primary_pr"]["virtual_missing"] is True
    assert "primary_pr_detail" not in by_field


def test_confirming_an_empty_parent_creates_a_verified_blank_and_reduces_review_count(client):
    patient = client.post("/api/patients", json={"patient_code": "blank-parent-003"}).json()
    before = client.get(
        f"/api/patients/{patient['id']}?review_blank_parents=true"
    ).json()
    before_count = sum(item["status"] != "VERIFIED" for item in before["observations"])

    created = add_manual_field(client, patient["id"], "clinical_stage", "")
    assert created["status"] == "VERIFIED"

    after = client.get(
        f"/api/patients/{patient['id']}?review_blank_parents=true"
    ).json()
    stage = next(item for item in after["observations"] if item["field_name"] == "clinical_stage")
    after_count = sum(item["status"] != "VERIFIED" for item in after["observations"])
    assert stage["current_value"] == ""
    assert stage["status"] == "VERIFIED"
    assert not stage.get("virtual_missing", False)
    assert after_count == before_count - 1


def test_frontend_supports_virtual_blank_parent_review_records():
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")

    assert "?review_blank_parents=true" in javascript
    assert "if(observation.virtual_missing)" in javascript
    assert 'raw_text:value?"人工手动补充":"人工明确留空"' in javascript
    assert "if(existing&&!existing.virtual_missing)" in javascript
    assert 'obs.status==="VERIFIED"?"已确认留空":"待人工填写或确认留空"' in javascript
    assert "function reviewDocumentId(observation)" in javascript
    assert "observation?.document_id||observation?.review_document_id" in javascript
    assert "document_id:reviewDocumentId(observation)" in javascript
    assert "const selectedFieldName=" in javascript
    assert "item=>item.field_name===selectedFieldName" in javascript


def test_missing_fields_receive_the_first_matching_review_page_in_patient_order():
    documents = [
        {"id": "admission-1", "document_type": "ADMISSION"},
        {"id": "ultrasound-1", "document_type": "ULTRASOUND"},
        {"id": "ultrasound-2", "document_type": "ULTRASOUND"},
    ]

    assert suggested_review_document_id("sex", documents) == "admission-1"
    assert suggested_review_document_id("pre_us_tumor_size_mm", documents) == "ultrasound-1"
    assert suggested_review_document_id("unknown_custom_field", documents) == "admission-1"
    assert suggested_review_document_id("sex", []) is None
