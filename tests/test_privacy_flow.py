import io
import json

from PIL import Image


def make_image(fmt: str = "PNG") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (24, 18), "white").save(output, format=fmt)
    return output.getvalue()


def create_patient(client) -> dict:
    response = client.post("/api/patients", json={"patient_code": "P0001"})
    assert response.status_code == 201
    return response.json()


def metadata() -> str:
    return json.dumps({
        "source_width": 100,
        "source_height": 80,
        "crop": {"x": 5, "y": 4, "width": 24, "height": 18},
        "redaction_count": 1,
        "client_reencoded": True,
    })


def test_raw_jpeg_is_rejected(client):
    patient = create_patient(client)
    response = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("raw.jpg", make_image("JPEG"), "image/jpeg")},
        data={"display_name": "raw", "sanitization": metadata(), "regions": "[]"},
    )
    assert response.status_code == 415


def test_sanitized_png_and_multiple_regions_are_saved(client):
    patient = create_patient(client)
    regions = [
        {"region_type": "IHC", "label": "IHC", "x": 1, "y": 2, "width": 10, "height": 5},
        {"region_type": "PATHOLOGY", "label": "病理", "x": 2, "y": 8, "width": 12, "height": 6},
    ]
    response = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "术后病理", "document_type": "SURGICAL_PATHOLOGY",
              "sanitization": metadata(), "regions": json.dumps(regions, ensure_ascii=False)},
    )
    assert response.status_code == 201
    assert len(response.json()["regions"]) == 2
    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert detail["documents"][0]["status"] == "ANNOTATED"
    assert "raw.jpg" not in str(detail)


def test_only_human_can_verify_observation(client):
    patient = create_patient(client)
    created = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "HER2_IHC", "value": "2+", "confidence": "HIGH",
              "model_name": "test-model", "model_digest": "abc"},
    ).json()
    assert created["status"] == "AI_PROCESSED"
    verified = client.post(
        f"/api/observations/{created['id']}/verify",
        json={"operator": "reviewer01"},
    )
    assert verified.json()["status"] == "VERIFIED"
    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert [item["operation"] for item in detail["audit_log"]] == ["USER_VERIFY", "AI_EXTRACT"]

