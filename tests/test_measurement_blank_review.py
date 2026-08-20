from app.main import normalize_observation_value, observation_value_is_valid


def test_measurement_master_value_uses_multiplication_sign_without_requiring_three_dimensions():
    field = "pre_us_tumor_size_mm"
    assert normalize_observation_value(field, "25") == "25"
    assert normalize_observation_value(field, "25,18") == "25×18"
    assert normalize_observation_value(field, "25，18，15") == "25×18×15"
    assert normalize_observation_value(field, "25 x 18") == "25×18"
    assert normalize_observation_value(field, "25*18*15") == "25×18×15"
    assert normalize_observation_value(field, "25×18") == "25×18"


def test_blank_is_a_valid_explicit_review_value_even_for_integer_fields():
    assert observation_value_is_valid("menarche_age", "") is True
    assert observation_value_is_valid("pre_us_tumor_size_mm", "") is True


def test_verified_blank_is_not_returned_to_review_required(client):
    patient = client.post("/api/patients", json={"patient_code": "blank-review-case"}).json()
    created = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "menarche_age",
            "value": "13",
            "raw_text": "初潮13岁",
            "confidence": "HIGH",
            "source_mode": "RECORDED",
        },
    ).json()

    edited = client.patch(
        f"/api/observations/{created['id']}",
        json={"value": "", "operator": "local-user", "reason": "病历未提供明确年龄"},
    )
    assert edited.status_code == 200, edited.text
    verified = client.post(
        f"/api/observations/{created['id']}/verify",
        json={"operator": "local-user", "note": "确认留空"},
    )
    assert verified.status_code == 200, verified.text

    detail = client.get(f"/api/patients/{patient['id']}").json()
    observation = next(item for item in detail["observations"] if item["field_name"] == "menarche_age")
    assert observation["current_value"] == ""
    assert observation["status"] == "VERIFIED"
    assert observation["confidence"] == "VERIFIED"


def test_manual_blank_creation_is_verified_and_records_reason(client):
    patient = client.post("/api/patients", json={"patient_code": "manual-blank-case"}).json()
    response = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "menarche_age",
            "value": "",
            "raw_text": "人工明确留空",
            "confidence": "LOW",
            "source_mode": "RECORDED",
            "operator": "local-user",
            "reason": "原始病历没有初潮年龄",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "VERIFIED"
    assert response.json()["confidence"] == "VERIFIED"

    detail = client.get(f"/api/patients/{patient['id']}").json()
    observation = next(item for item in detail["observations"] if item["field_name"] == "menarche_age")
    assert observation["current_value"] == ""
    assert observation["status"] == "VERIFIED"
    audit = next(item for item in detail["audit_log"] if item["field_name"] == "menarche_age")
    assert audit["operation"] == "USER_CREATE"
    assert audit["reason"] == "原始病历没有初潮年龄"


def test_two_dimension_measurement_keeps_master_and_only_generates_existing_dimensions(client):
    patient = client.post("/api/patients", json={"patient_code": "two-dim-case"}).json()
    created = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "pre_us_tumor_size_mm",
            "value": "25,18",
            "raw_text": "肿块约25,18mm",
            "confidence": "HIGH",
            "source_mode": "RECORDED",
        },
    ).json()
    client.post(f"/api/observations/{created['id']}/verify", json={"operator": "local-user"})

    preview = client.get("/api/data-preview").json()
    row = next(item for item in preview["rows"] if item["patient_id"] == patient["id"])
    assert row["values"]["pre_us_tumor_size_mm"] == "25×18"
    assert row["values"]["pre_us_tumor_size_mm_dim1_mm"] == "25"
    assert row["values"]["pre_us_tumor_size_mm_dim2_mm"] == "18"
    assert row["values"]["pre_us_tumor_size_mm_dim3_mm"] == ""
