from app.derived_fields import parse_measurement_components_mm, parse_tnm_components
from app.knowledge import extraction_prompt, questionnaire_catalog


def add_and_verify(client, patient_id: int, field_name: str, value: str) -> str:
    created = client.post(
        f"/api/patients/{patient_id}/observations",
        json={
            "field_name": field_name,
            "value": value,
            "raw_text": "人工测试主字段",
            "confidence": "HIGH",
            "source_mode": "RECORDED",
        },
    )
    assert created.status_code == 200, created.text
    observation_id = created.json()["id"]
    verified = client.post(
        f"/api/observations/{observation_id}/verify",
        json={"operator": "reviewer"},
    )
    assert verified.status_code == 200, verified.text
    return observation_id


def test_tnm_component_parser_keeps_context_prefix():
    assert parse_tnm_components("cT2 N1 M0") == ("cT2", "cN1", "cM0")
    assert parse_tnm_components("ypT1cN0M0") == ("ypT1C", "ypN0", "ypM0")
    assert parse_tnm_components("Stage IIA") is None


def test_measurement_parser_preserves_source_order_and_normalizes_units():
    assert parse_measurement_components_mm("32×18×15 mm") == ("32", "18", "15")
    assert parse_measurement_components_mm("3.2*1.8 cm") == ("32", "18", None)
    assert parse_measurement_components_mm("21 x 9") == ("21", "9", None)


def test_derived_fields_exist_in_review_catalog_but_not_ai_prompt():
    catalog = {field["key"]: field for field in questionnaire_catalog()}
    assert catalog["clinical_t_component"]["capture"] == "derived_readonly"
    assert catalog["pathological_n_component"]["capture"] == "derived_readonly"
    assert catalog["pre_us_tumor_size_mm_dim1_mm"]["capture"] == "derived_readonly"

    prompt, allowed = extraction_prompt("DISCHARGE", "cT2N1M0")
    assert "clinical_stage" in allowed
    assert "clinical_t_component" not in allowed
    assert "clinical_t_component" not in prompt


def test_verified_master_fields_materialize_readonly_projections(client):
    patient = client.post("/api/patients", json={"patient_code": "7654321"}).json()

    # Before human verification, no derived fields are materialized.
    pending = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "clinical_stage",
            "value": "cT2N1M0",
            "raw_text": "cT2N1M0",
            "confidence": "HIGH",
            "source_mode": "RECORDED",
        },
    ).json()
    preview = client.get("/api/data-preview").json()
    row = next(item for item in preview["rows"] if item["patient_id"] == patient["id"])
    assert row["values"]["clinical_t_component"] == ""

    client.post(f"/api/observations/{pending['id']}/verify", json={"operator": "reviewer"})
    add_and_verify(client, patient["id"], "pathological_stage", "pT1cN0M0")
    add_and_verify(client, patient["id"], "pre_us_tumor_size_mm", "32×18×15 mm")

    preview = client.get("/api/data-preview").json()
    row = next(item for item in preview["rows"] if item["patient_id"] == patient["id"])
    assert row["values"]["clinical_t_component"] == "cT2"
    assert row["values"]["clinical_n_component"] == "cN1"
    assert row["values"]["clinical_m_component"] == "cM0"
    assert row["values"]["pathological_t_component"] == "pT1C"
    assert row["values"]["pathological_n_component"] == "pN0"
    assert row["values"]["pathological_m_component"] == "pM0"
    assert row["values"]["pre_us_tumor_size_mm"] == "32×18×15 mm"
    assert row["values"]["pre_us_tumor_size_mm_dim1_mm"] == "32"
    assert row["values"]["pre_us_tumor_size_mm_dim2_mm"] == "18"
    assert row["values"]["pre_us_tumor_size_mm_dim3_mm"] == "15"

    detail = client.get(f"/api/patients/{patient['id']}").json()
    derived = {
        item["field_name"]: item
        for item in detail["observations"]
        if item.get("source_mode") == "DERIVED"
    }
    assert derived["clinical_t_component"]["status"] == "VERIFIED"
    assert derived["pre_us_tumor_size_mm_dim3_mm"]["current_value"] == "15"
