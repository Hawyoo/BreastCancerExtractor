from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_verified_blank_overrides_an_ai_no_in_patient_detail_and_overview(client):
    patient = client.post("/api/patients", json={"patient_code": "blank-overrides-no"}).json()
    created = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "postoperative_radiotherapy",
            "value": "NO",
            "raw_text": "未见放疗记录",
            "confidence": "MEDIUM",
            "source_mode": "RECORDED",
            "operator": "AI",
        },
    )
    assert created.status_code == 201
    observation_id = created.json()["id"]

    cleared = client.patch(
        f"/api/observations/{observation_id}",
        json={"value": "", "operator": "local-user", "reason": "人工明确留空"},
    )
    assert cleared.status_code == 200
    verified = client.post(
        f"/api/observations/{observation_id}/verify",
        json={"operator": "local-user", "note": "确认最终结果留空"},
    )
    assert verified.status_code == 200

    detail = client.get(f"/api/patients/{patient['id']}").json()
    field = next(
        item for item in detail["observations"]
        if item["field_name"] == "postoperative_radiotherapy"
    )
    assert field["ai_value"] == "NO"
    assert field["current_value"] == ""
    assert field["status"] == "VERIFIED"

    overview = client.get("/api/data-preview?verified_only=false").json()
    row = next(item for item in overview["rows"] if item["patient_id"] == patient["id"])
    assert row["values"]["postoperative_radiotherapy"] == ""
    assert row["statuses"]["postoperative_radiotherapy"] == "VERIFIED"


def test_frontend_does_not_restore_default_no_over_a_reviewed_blank():
    javascript = (ROOT / "app/static/review_inline.js").read_text(encoding="utf-8")

    assert "const choiceValue = observation ? normalizeYesNoValue(value)" in javascript
    assert 'status === "EMPTY"' in javascript
    assert 'raw_text: value' in javascript
    assert ': "人工明确留空"' in javascript
    assert 'operator: "local-user"' in javascript
