import csv
import io
import json

from PIL import Image

from app.knowledge import questionnaire_catalog


def make_image(fmt: str = "PNG") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (24, 18), "white").save(output, format=fmt)
    return output.getvalue()


def create_patient(client) -> dict:
    response = client.post("/api/patients", json={"patient_code": "1234567"})
    assert response.status_code == 201
    return response.json()


def metadata() -> str:
    return json.dumps({
        "source_width": 100,
        "source_height": 80,
        "crop": {"x": 5, "y": 4, "width": 24, "height": 18},
        "redaction_count": 1,
        "client_reencoded": True,
        "enhancement_mode": "ENHANCED",
        "enhancement_version": "browser-demoire-v1",
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


def test_document_ocr_is_persisted(client, monkeypatch):
    patient = create_patient(client)
    uploaded = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "术后病理-第1页", "document_type": "SURGICAL_PATHOLOGY",
              "sanitization": metadata(), "regions": "[]"},
    ).json()

    async def fake_ocr(_):
        return {"engine": "PaddleOCR", "version": "test", "full_text": "ER 90%", "lines": []}

    monkeypatch.setattr("app.main.recognize_image", fake_ocr)
    response = client.post(f"/api/documents/{uploaded['id']}/ocr")
    assert response.status_code == 200
    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert detail["documents"][0]["ocr"]["full_text"] == "ER 90%"
    repeated = client.post(f"/api/documents/{uploaded['id']}/ocr")
    assert repeated.status_code == 409
    assert "只有修改并覆盖图片后" in repeated.json()["detail"]


def test_forced_ocr_replaces_results_only_after_success_and_invalidates_page_fields(client, monkeypatch):
    patient = create_patient(client)
    uploaded = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "入院记录", "document_type": "ADMISSION",
              "sanitization": metadata(), "regions": "[]"},
    ).json()
    results = iter(["首次 OCR", "重新 OCR"])

    async def fake_ocr(_):
        text = next(results)
        return {"engine": "PaddleOCR", "version": "test", "full_text": text, "lines": []}

    monkeypatch.setattr("app.main.recognize_image", fake_ocr)
    assert client.post(f"/api/documents/{uploaded['id']}/ocr").status_code == 200
    observation = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "smoking", "value": "NO", "confidence": "HIGH",
            "source_mode": "RECORDED", "document_id": uploaded["id"],
        },
    )
    assert observation.status_code == 201

    reprocessed = client.post(f"/api/documents/{uploaded['id']}/ocr?force=true")
    assert reprocessed.status_code == 200
    assert reprocessed.json()["reprocessed"] is True
    assert reprocessed.json()["invalidated_observations"] == 1

    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert detail["documents"][0]["ocr"]["full_text"] == "重新 OCR"
    assert detail["documents"][0]["status"] == "OCR_PROCESSED"
    assert not any(item.get("document_id") == uploaded["id"] for item in detail["observations"])
    assert detail["status"] == "UNPROCESSED"
    assert "USER_REPROCESS_OCR" in [item["operation"] for item in detail["audit_log"]]


def test_revising_roi_invalidates_results_and_creates_a_new_ocr_version(client, monkeypatch):
    patient = create_patient(client)
    uploaded = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "免疫组化-第1页", "document_type": "IHC",
              "sanitization": metadata(), "regions": "[]"},
    ).json()

    async def fake_ocr(_):
        return {"engine": "PaddleOCR", "version": "test", "full_text": "ER 90%", "lines": []}

    async def fake_models():
        return [{"name": "local-model", "digest": "digest-1"}]

    async def fake_extract(_model, _prompt, _progress=None, **_options):
        return {"observations": [{
            "field_name": "primary_er", "value": "POSITIVE", "raw_text": "ER 90%",
            "confidence": "HIGH", "source_mode": "RECORDED", "inference_basis": [],
        }]}

    monkeypatch.setattr("app.main.recognize_image", fake_ocr)
    monkeypatch.setattr("app.main.list_extraction_models", fake_models)
    monkeypatch.setattr("app.main.extract_structured", fake_extract)
    assert client.post(f"/api/documents/{uploaded['id']}/ocr").status_code == 200
    assert client.post(f"/api/documents/{uploaded['id']}/extract").status_code == 200
    assert client.post(f"/api/documents/{uploaded['id']}/extract").status_code == 409

    unchanged = client.put(
        f"/api/documents/{uploaded['id']}",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "免疫组化-第1页", "document_type": "IHC",
              "sanitization": metadata(), "regions": "[]"},
    )
    assert unchanged.status_code == 409
    assert "没有变化" in unchanged.json()["detail"]

    new_regions = [{"region_type": "ihc_panel", "label": "IHC", "x": 1, "y": 1, "width": 10, "height": 8}]
    revised = client.put(
        f"/api/documents/{uploaded['id']}",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "免疫组化-第1页", "document_type": "IHC",
              "sanitization": metadata(), "regions": json.dumps(new_regions)},
    )
    assert revised.status_code == 200
    assert revised.json()["invalidated_ocr"] is True
    assert revised.json()["invalidated_observations"] == 1
    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert detail["observations"] == []
    assert detail["documents"][0]["ocr"] is None
    assert detail["audit_log"][0]["operation"] == "USER_REVISE_DOCUMENT"
    assert client.post(f"/api/documents/{uploaded['id']}/ocr").status_code == 200


def test_saving_review_text_regions_preserves_ocr_and_observations(client, monkeypatch):
    patient = create_patient(client)
    uploaded = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "免疫组化-第1页", "document_type": "IHC",
              "sanitization": metadata(), "regions": "[]"},
    ).json()

    async def fake_ocr(_):
        return {
            "engine": "PaddleOCR", "version": "test", "full_text": "HER-2：2+",
            "lines": [{"text": "HER-2：2+", "score": 0.98, "box": [2, 4, 20, 10]}],
        }

    monkeypatch.setattr("app.main.recognize_image", fake_ocr)
    assert client.post(f"/api/documents/{uploaded['id']}/ocr").status_code == 200
    observation = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "document_id": uploaded["id"], "field_name": "primary_her2", "value": "POSITIVE",
            "raw_text": "HER-2：2+", "confidence": "HIGH",
        },
    ).json()

    saved = client.put(
        f"/api/documents/{uploaded['id']}/text-regions",
        json={
            "operator": "reviewer01",
            "regions": [{
                "region_type": "FIELD_EVIDENCE", "label": "primary_her2",
                "x": 1, "y": 3, "width": 21, "height": 9,
            }],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["region_count"] == 1

    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert detail["documents"][0]["ocr"]["full_text"] == "HER-2：2+"
    assert detail["observations"][0]["id"] == observation["id"]
    assert detail["observations"][0]["current_value"] == "POSITIVE"
    assert detail["audit_log"][0]["operation"] == "USER_UPDATE_TEXT_REGIONS"


def test_manual_position_reextracts_only_current_field(client, monkeypatch):
    patient = create_patient(client)
    uploaded = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "免疫组化-第1页", "document_type": "IHC",
              "sanitization": metadata(), "regions": "[]"},
    ).json()

    async def fake_ocr(_):
        return {
            "engine": "PaddleOCR", "version": "test", "full_text": "ER 90%\nHER-2：2+",
            "lines": [
                {"text": "ER 90%", "score": 0.97, "box": [2, 1, 20, 3]},
                {"text": "HER-2：2+", "score": 0.98, "box": [2, 6, 20, 11]},
            ],
        }

    async def fake_models():
        return [{"name": "local-model", "digest": "digest-1"}]

    captured = {}

    async def fake_extract(_model, prompt, _progress=None, **_options):
        captured["prompt"] = prompt
        captured["options"] = _options
        return {"observations": [{
            "field_name": "primary_her2", "value": "2+", "raw_text": "HER-2：2+",
            "confidence": "HIGH", "source_mode": "RECORDED", "inference_basis": [],
        }]}

    monkeypatch.setattr("app.main.recognize_image", fake_ocr)
    monkeypatch.setattr("app.main.list_extraction_models", fake_models)
    monkeypatch.setattr("app.main.extract_structured", fake_extract)
    assert client.post(f"/api/documents/{uploaded['id']}/ocr").status_code == 200
    materialized = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "primary_her2",
            "value": "",
            "confidence": "LOW",
            "source_mode": "RECORDED",
            "operator": "local-user",
        },
    ).json()
    saved = client.put(
        f"/api/observations/{materialized['id']}/evidence-location",
        json={"document_id": uploaded["id"], "x": 1, "y": 5, "width": 21, "height": 8},
    ).json()

    extracted = client.post(
        f"/api/documents/{uploaded['id']}/extract-field",
        json={"field_name": "primary_her2", "region_ids": [saved["region"]["id"]]},
    )
    assert extracted.status_code == 200, extracted.text
    assert extracted.json()["observation"]["value"] == "2+"
    assert "人工复核现场定位：字段 primary_her2，最高优先级" in captured["prompt"]
    assert "HER-2：2+" in captured["prompt"]
    assert "- key: primary_her2" in captured["prompt"]
    assert "- key: primary_er\n" not in captured["prompt"]
    assert captured["options"]["think"] is False

    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert detail["documents"][0]["ocr"]["full_text"] == "ER 90%\nHER-2：2+"
    assert len(detail["observations"]) == 1
    assert detail["observations"][0]["id"] == materialized["id"]
    assert detail["observations"][0]["field_name"] == "primary_her2"
    assert detail["observations"][0]["current_value"] == "2+"
    assert detail["audit_log"][0]["operation"] == "AI_REEXTRACT_FIELD"


def test_document_can_be_selectively_deleted_with_audit(client):
    patient = create_patient(client)
    uploaded = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "超声-第1页", "document_type": "ULTRASOUND",
              "sanitization": metadata(), "regions": "[]"},
    ).json()
    assert client.get(f"/api/documents/{uploaded['id']}/image").status_code == 200
    deleted = client.delete(f"/api/documents/{uploaded['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/documents/{uploaded['id']}/image").status_code == 404
    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert detail["documents"] == []
    assert detail["audit_log"][0]["operation"] == "USER_DELETE_DOCUMENT"


def test_patient_delete_removes_all_database_and_managed_image_data(client):
    patient = create_patient(client)
    uploaded = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "术后病理", "document_type": "SURGICAL_PATHOLOGY",
              "sanitization": metadata(), "regions": "[]"},
    ).json()
    assert client.get(f"/api/documents/{uploaded['id']}/image").status_code == 200
    deleted = client.delete(f"/api/patients/{patient['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/patients/{patient['id']}").status_code == 404
    assert client.get(f"/api/documents/{uploaded['id']}/image").status_code == 404
    assert all(item["id"] != patient["id"] for item in client.get("/api/patients").json())


def test_ollama_structured_extraction_enters_human_review(client, monkeypatch):
    patient = create_patient(client)
    uploaded = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "术后病理-第1页", "document_type": "SURGICAL_PATHOLOGY",
              "sanitization": metadata(), "regions": "[]"},
    ).json()

    async def fake_ocr(_):
        return {"engine": "PaddleOCR", "version": "test", "full_text": "ER 90%", "lines": []}

    async def fake_models():
        return [{"name": "local-model", "digest": "digest-1"}]

    async def fake_extract(_model, _prompt, _progress=None, **_options):
        return {"observations": [{
            "field_name": "postop_tumor_er", "value": "POSITIVE", "raw_text": "ER 90%",
            "confidence": "MEDIUM", "source_mode": "RECORDED", "inference_basis": [],
        }]}

    monkeypatch.setattr("app.main.recognize_image", fake_ocr)
    monkeypatch.setattr("app.main.list_extraction_models", fake_models)
    monkeypatch.setattr("app.main.extract_structured", fake_extract)
    client.post(f"/api/documents/{uploaded['id']}/ocr")
    response = client.post(f"/api/documents/{uploaded['id']}/extract")
    assert response.status_code == 200
    assert response.json()["model_digest"] == "digest-1"
    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert detail["observations"][0]["status"] == "REVIEW_REQUIRED"


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

    edited = client.patch(
        f"/api/observations/{created['id']}",
        json={"value": "3+", "operator": "reviewer01", "reason": "再次对照原图修正"},
    )
    assert edited.status_code == 200
    assert edited.json()["status"] == "VERIFIED"
    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert detail["observations"][0]["current_value"] == "3+"
    assert detail["observations"][0]["status"] == "VERIFIED"
    assert detail["audit_log"][0]["operation"] == "USER_EDIT_VERIFIED"

    confirmed_again = client.post(
        f"/api/observations/{created['id']}/verify",
        json={"operator": "reviewer01", "note": "二次确认"},
    )
    assert confirmed_again.status_code == 200
    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert detail["audit_log"][0]["operation"] == "USER_VERIFY"


def test_patient_observations_follow_review_group_and_questionnaire_order(client):
    patient = create_patient(client)
    later = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "primary_her2", "value": "2+", "confidence": "HIGH"},
    ).json()
    earlier = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "sex", "value": "FEMALE", "confidence": "HIGH"},
    ).json()
    client.post(
        f"/api/observations/{earlier['id']}/verify",
        json={"operator": "reviewer01"},
    )

    observations = client.get(f"/api/patients/{patient['id']}").json()["observations"]
    assert [item["id"] for item in observations] == [later["id"], earlier["id"]]
    assert observations[0]["field_label"] == "原发灶免疫组化Her-2"
    assert observations[1]["field_label"] == "性别"
    assert observations[1]["field_order"] < observations[0]["field_order"]


def test_duplicate_pathology_grades_are_consolidated_and_normalized(client):
    patient = create_patient(client)
    for value in ("G2", "Ⅱ级", "2"):
        response = client.post(
            f"/api/patients/{patient['id']}/observations",
            json={"field_name": "postop_tumor_pathology_grade", "value": value, "confidence": "HIGH"},
        )
        assert response.status_code == 201

    observations = client.get(f"/api/patients/{patient['id']}").json()["observations"]
    grades = [item for item in observations if item["field_name"] == "postop_tumor_pathology_grade"]
    assert len(grades) == 1
    assert grades[0]["current_value"] == "2"
    assert grades[0]["candidate_count"] == 3
    assert grades[0]["candidate_conflict"] is False


def test_birads_subcategory_can_be_edited_and_human_verified(client):
    patient = create_patient(client)
    created = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "pre_mmg_birads", "value": "BI-RADS 4", "confidence": "HIGH"},
    ).json()
    edited = client.patch(
        f"/api/observations/{created['id']}",
        json={"value": "4B", "operator": "reviewer01", "reason": "按报告亚类修正"},
    )
    assert edited.status_code == 200
    assert edited.json()["value"] == "4B"
    verified = client.post(
        f"/api/observations/{created['id']}/verify",
        json={"operator": "reviewer01"},
    )
    assert verified.status_code == 200
    observation = client.get(f"/api/patients/{patient['id']}").json()["observations"][0]
    assert observation["current_value"] == "4B"
    assert observation["status"] == "VERIFIED"
    assert observation["invalid_only"] is False


def test_same_questionnaire_field_is_consolidated_before_human_review(client):
    patient = create_patient(client)
    yes = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "postoperative_endocrine",
            "value": "YES",
            "raw_text": "行托瑞米芬内分泌治疗至今",
            "confidence": "HIGH",
        },
    ).json()
    client.post(
        f"/api/observations/{yes['id']}/verify",
        json={"operator": "reviewer01"},
    )
    client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "postoperative_endocrine",
            "value": "RECORDED",
            "raw_text": "现内分泌治",
            "confidence": "HIGH",
        },
    )
    client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "postoperative_endocrine",
            "value": "NO",
            "raw_text": "术后给予对症治疗",
            "confidence": "HIGH",
        },
    )

    observations = client.get(f"/api/patients/{patient['id']}").json()["observations"]
    assert len(observations) == 1
    assert observations[0]["id"] == yes["id"]
    assert observations[0]["current_value"] == "YES"
    assert observations[0]["status"] == "REVIEW_REQUIRED"
    assert observations[0]["candidate_count"] == 3
    assert observations[0]["discarded_candidate_count"] == 1
    assert observations[0]["candidate_conflict"] is True

    resolved = client.post(
        f"/api/observations/{yes['id']}/verify",
        json={"operator": "reviewer01", "note": "保留证据明确的YES"},
    )
    assert resolved.status_code == 200
    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert len(detail["observations"]) == 1
    assert detail["observations"][0]["status"] == "VERIFIED"
    assert detail["observations"][0]["candidate_count"] == 1
    assert "USER_RESOLVE_FIELD_CANDIDATES" in [item["operation"] for item in detail["audit_log"]]


def test_conflict_review_can_verify_the_selected_candidate(client):
    patient = create_patient(client)
    requested = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "postoperative_endocrine", "value": "YES", "confidence": "HIGH"},
    ).json()
    selected = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "postoperative_endocrine", "value": "NO", "confidence": "HIGH"},
    ).json()

    verified = client.post(
        f"/api/observations/{requested['id']}/verify",
        json={"candidate_id": selected["id"], "value": "NO", "operator": "reviewer01"},
    )
    assert verified.status_code == 200
    assert verified.json()["id"] == selected["id"]
    assert verified.json()["requested_id"] == requested["id"]
    assert requested["id"] in verified.json()["superseded_ids"]
    observation = client.get(f"/api/patients/{patient['id']}").json()["observations"][0]
    assert observation["id"] == selected["id"]
    assert observation["current_value"] == "NO"
    assert observation["status"] == "VERIFIED"


def test_manual_review_location_ignores_ai_document_mapping_within_patient(client):
    patient = create_patient(client)
    first = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("first.png", make_image(), "image/png")},
        data={"display_name": "病案首页", "document_type": "MEDICAL_RECORD_COVER",
              "sanitization": metadata(), "regions": "[]"},
    ).json()
    second = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("second.png", make_image(), "image/png")},
        data={"display_name": "MRI-第1页", "document_type": "MRI",
              "sanitization": metadata(), "regions": "[]"},
    ).json()
    observation = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "contact", "value": "13800000000", "confidence": "HIGH",
              "document_id": first["id"]},
    ).json()

    first_location = client.put(
        f"/api/observations/{observation['id']}/evidence-location",
        json={"document_id": first["id"], "x": 1, "y": 2, "width": 8, "height": 6,
              "operator": "reviewer01"},
    )
    assert first_location.status_code == 200
    old_region_id = first_location.json()["region"]["id"]
    moved = client.put(
        f"/api/observations/{observation['id']}/evidence-location",
        json={"document_id": second["id"], "x": 3, "y": 4, "width": 10, "height": 7,
              "operator": "reviewer01"},
    )
    assert moved.status_code == 200
    assert moved.json()["document_id"] == second["id"]
    assert moved.json()["region"]["id"] != old_region_id

    detail = client.get(f"/api/patients/{patient['id']}").json()
    stored = next(item for item in detail["observations"] if item["id"] == observation["id"])
    assert stored["document_id"] == second["id"]
    assert stored["region_id"] == moved.json()["region"]["id"]
    assert old_region_id not in {region["id"] for doc in detail["documents"] for region in doc["regions"]}

    other_patient = client.post("/api/patients", json={"patient_code": "7654321"}).json()
    foreign = client.post(
        f"/api/patients/{other_patient['id']}/documents",
        files={"image": ("foreign.png", make_image(), "image/png")},
        data={"display_name": "其他患者", "document_type": "ADMISSION",
              "sanitization": metadata(), "regions": "[]"},
    ).json()
    rejected = client.put(
        f"/api/observations/{observation['id']}/evidence-location",
        json={"document_id": foreign["id"], "x": 1, "y": 1, "width": 5, "height": 5},
    )
    assert rejected.status_code == 409


def test_verification_atomically_saves_the_unsaved_review_roi(client):
    patient = create_patient(client)
    document = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("admission.png", make_image(), "image/png")},
        data={"display_name": "入院记录", "document_type": "ADMISSION",
              "sanitization": metadata(), "regions": "[]"},
    ).json()
    observation = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "family_history_detail", "value": "母亲乳腺癌", "confidence": "HIGH",
              "document_id": document["id"]},
    ).json()

    verified = client.post(
        f"/api/observations/{observation['id']}/verify",
        json={
            "value": "母亲乳腺癌",
            "operator": "reviewer01",
            "evidence_location": {
                "document_id": document["id"], "x": 2, "y": 3, "width": 9, "height": 6,
                "operator": "reviewer01",
            },
        },
    )
    assert verified.status_code == 200
    result = verified.json()
    assert result["status"] == "VERIFIED"
    assert result["region"]["region_type"] == "FIELD_REVIEW_EVIDENCE"
    assert result["region_id"] == result["region"]["id"]

    detail = client.get(f"/api/patients/{patient['id']}").json()
    stored = next(item for item in detail["observations"] if item["id"] == observation["id"])
    assert stored["status"] == "VERIFIED"
    assert stored["region_id"] == result["region_id"]
    operations = [item["operation"] for item in detail["audit_log"]]
    assert "USER_SET_EVIDENCE_LOCATION" in operations
    assert "USER_VERIFY" in operations


def test_deleting_manual_review_location_removes_only_its_atomic_region(client):
    patient = create_patient(client)
    document = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("admission.png", make_image(), "image/png")},
        data={
            "display_name": "入院记录",
            "document_type": "ADMISSION",
            "sanitization": metadata(),
            "regions": "[]",
        },
    ).json()
    observation = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "family_history_detail",
            "value": "母亲乳腺癌",
            "confidence": "HIGH",
            "document_id": document["id"],
        },
    ).json()
    saved = client.put(
        f"/api/observations/{observation['id']}/evidence-location",
        json={"document_id": document["id"], "x": 2, "y": 3, "width": 9, "height": 6},
    ).json()

    deleted = client.delete(f"/api/observations/{observation['id']}/evidence-location")
    assert deleted.status_code == 200
    assert deleted.json()["removed_region_id"] == saved["region"]["id"]

    detail = client.get(f"/api/patients/{patient['id']}").json()
    stored = next(item for item in detail["observations"] if item["id"] == observation["id"])
    assert stored["region_id"] is None
    assert stored["evidence_status"] == "REJECTED"
    assert saved["region"]["id"] not in {
        region["id"] for item in detail["documents"] for region in item["regions"]
    }


def test_all_patient_preview_and_excel_compatible_chinese_csv(client):
    patient = client.post("/api/patients", json={"patient_code": "0123456"}).json()
    client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "sex", "value": "FEMALE", "confidence": "HIGH"},
    )
    client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "contact", "value": "13800000000", "confidence": "HIGH"},
    )

    preview = client.get("/api/data-preview").json()
    assert len(preview["columns"]) == len(questionnaire_catalog())
    assert preview["columns"][0]["label"] == "病案号（7位）"
    assert preview["columns"][-1]["label"] == "其他收集信息"
    assert preview["rows"][0]["values"]["record_number"] == "0123456"
    assert preview["rows"][0]["values"]["contact"] == "13800000000"
    assert preview["rows"][0]["statuses"]["contact"] == "AI_PROCESSED"
    assert preview["rows"][0]["values"]["sex"] == "女"
    assert preview["rows"][0]["statuses"]["sex"] == "AI_PROCESSED"
    assert preview["review_metrics"] == {
        "total_fields": 2,
        "verified_fields": 0,
        "pending_fields": 2,
        "conflict_fields": 0,
        "manually_modified_fields": 0,
        "verification_rate": 0.0,
    }

    verified = client.get("/api/data-preview?verified_only=true").json()
    assert verified["rows"][0]["values"]["sex"] == ""

    exported = client.get("/api/data-preview.csv")
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    csv_text = exported.content.decode("utf-8-sig")
    assert csv_text.splitlines()[0].startswith("病案号（7位）,性别,联系方式")
    csv_rows = list(csv.reader(io.StringIO(csv_text)))
    assert csv_rows[1][0] == '="0123456"'
    assert ",女," in csv_text
    assert "filename*=UTF-8''" in exported.headers["content-disposition"]


def test_neoadjuvant_question_exports_blank_when_prerequisite_is_no(client):
    patient = create_patient(client)
    client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "neoadjuvant_received", "value": "NO", "confidence": "HIGH"},
    )
    client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "neoadjuvant_cycles", "value": "6", "confidence": "HIGH"},
    )
    preview = client.get("/api/data-preview").json()
    assert preview["rows"][0]["values"]["neoadjuvant_cycles"] == ""
    assert preview["rows"][0]["statuses"]["neoadjuvant_cycles"] == "NOT_APPLICABLE"


def test_all_nested_neoadjuvant_followups_stay_blank_when_treatment_was_not_received(client):
    patient = create_patient(client)
    client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "neoadjuvant_received", "value": "NO", "confidence": "HIGH"},
    )
    preview = client.get("/api/data-preview").json()["rows"][0]
    downstream = {
        "neoadjuvant_regimen",
        "neoadjuvant_cycles",
        "post_neoadj_us_available",
        "post_neoadj_us_size_mm",
        "post_neoadj_us_tumor_response",
        "post_neoadj_us_nodes",
        "post_neoadj_us_nodes_response",
        "post_neoadj_mri_available",
        "post_neoadj_mri_size_mm",
        "post_neoadj_mri_tumor_response",
        "post_neoadj_mri_nodes",
        "post_neoadj_mri_nodes_response",
        "post_neoadj_pcr",
        "post_neoadj_mp_grade",
        "post_neoadj_rcb_grade",
    }
    for field_name in downstream:
        assert preview["values"][field_name] == "", field_name
        assert preview["statuses"][field_name] == "NOT_APPLICABLE", field_name

    exported = client.get("/api/data-preview.csv")
    csv_rows = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig"))))
    header, data = csv_rows[0], csv_rows[1]
    catalog = questionnaire_catalog()
    labels = {field["key"]: field["label"] for field in catalog}
    for field_name in downstream:
        assert data[header.index(labels[field_name])] == "", field_name


def test_inapplicable_conditional_fields_leave_review_queue_and_return_when_parent_changes(client):
    patient = create_patient(client)
    parent = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "neoadjuvant_received", "value": "NO", "confidence": "HIGH"},
    ).json()
    child = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "neoadjuvant_cycles", "value": "6", "confidence": "HIGH"},
    ).json()
    client.post(f"/api/observations/{parent['id']}/verify", json={"operator": "reviewer01"})

    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert [item["id"] for item in detail["observations"]] == [parent["id"]]
    assert "neoadjuvant_cycles" in detail["conditional_na_fields"]
    assert detail["status"] == "VERIFIED"
    preview = client.get("/api/data-preview?verified_only=true").json()
    assert preview["rows"][0]["values"]["neoadjuvant_cycles"] == ""
    assert preview["rows"][0]["statuses"]["neoadjuvant_cycles"] == "NOT_APPLICABLE"

    edited = client.patch(
        f"/api/observations/{parent['id']}",
        json={"value": "YES", "operator": "reviewer01", "reason": "复核后改为接受新辅助治疗"},
    )
    assert edited.status_code == 200
    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert {item["id"] for item in detail["observations"]} == {parent["id"], child["id"]}
    child_result = next(item for item in detail["observations"] if item["id"] == child["id"])
    assert child_result["status"] == "AI_PROCESSED"


def test_choice_field_metadata_is_returned_for_button_review(client):
    patient = create_patient(client)
    client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "breast_laterality", "value": "LEFT", "confidence": "HIGH"},
    )
    observation = client.get(f"/api/patients/{patient['id']}").json()["observations"][0]
    assert observation["field_options"] == [
        {"label": "左侧", "value": "LEFT"},
        {"label": "右侧", "value": "RIGHT"},
        {"label": "双侧", "value": "BILATERAL"},
    ]


def test_historical_record_token_is_forced_to_human_review(client):
    patient = create_patient(client)
    client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "postoperative_endocrine", "value": "record", "confidence": "HIGH"},
    )
    observation = client.get(f"/api/patients/{patient['id']}").json()["observations"][0]
    assert observation["invalid_only"] is True
    assert observation["status"] == "REVIEW_REQUIRED"


def test_admission_without_metastasis_mention_creates_reviewable_default_no(client, monkeypatch):
    patient = create_patient(client)
    uploaded = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "入院记录-第1页", "document_type": "ADMISSION",
              "sanitization": metadata(), "regions": "[]"},
    ).json()

    async def fake_ocr(_):
        return {"engine": "PaddleOCR", "version": "test", "full_text": "因发现乳房肿块入院", "lines": []}

    async def fake_models():
        return [{"name": "local-model", "digest": "digest-1"}]

    extraction_calls = []

    async def fake_extract(_model, _prompt, _progress=None, **_options):
        extraction_calls.append(_options)
        return {"observations": []}

    monkeypatch.setattr("app.main.recognize_image", fake_ocr)
    monkeypatch.setattr("app.main.list_extraction_models", fake_models)
    monkeypatch.setattr("app.main.extract_structured", fake_extract)
    assert client.post(f"/api/documents/{uploaded['id']}/ocr").status_code == 200
    assert client.post(f"/api/documents/{uploaded['id']}/extract").status_code == 200
    assert extraction_calls == [{"think": False}]

    detail = client.get(f"/api/patients/{patient['id']}").json()
    observation = next(item for item in detail["observations"] if item["field_name"] == "metastatic_at_presentation")
    assert observation["current_value"] == "NO"
    assert observation["source_mode"] == "INFERRED"
    assert observation["status"] == "REVIEW_REQUIRED"
    assert "AI_DEFAULT" in [item["operation"] for item in detail["audit_log"]]


def test_explicit_pathological_tnm_runs_one_focused_staging_pass(client, monkeypatch):
    patient = create_patient(client)
    uploaded = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={"display_name": "术后病理", "document_type": "SURGICAL_PATHOLOGY",
              "sanitization": metadata(), "regions": "[]"},
    ).json()

    async def fake_ocr(_):
        return {"engine": "PaddleOCR", "version": "test", "full_text": "术后病理：ypT1cN0M0", "lines": []}

    async def fake_models():
        return [{"name": "local-model", "digest": "digest-1"}]

    calls = []

    async def fake_extract(_model, prompt, _progress=None, **options):
        calls.append({"prompt": prompt, **options})
        if not options.get("think"):
            return {"observations": []}
        return {"observations": [{
            "field_name": "pathological_stage", "value": "ypT1cN0M0", "raw_text": "ypT1cN0M0",
            "confidence": "HIGH", "source_mode": "RECORDED", "inference_basis": [],
        }]}

    monkeypatch.setattr("app.main.recognize_image", fake_ocr)
    monkeypatch.setattr("app.main.list_extraction_models", fake_models)
    monkeypatch.setattr("app.main.extract_structured", fake_extract)
    assert client.post(f"/api/documents/{uploaded['id']}/ocr").status_code == 200
    assert client.post(f"/api/documents/{uploaded['id']}/extract").status_code == 200
    assert [call["think"] for call in calls] == [False, True]
    assert "- key: pathological_stage" in calls[1]["prompt"]
    assert "- key: clinical_stage\n" not in calls[1]["prompt"]

    observations = client.get(f"/api/patients/{patient['id']}").json()["observations"]
    assert observations[0]["field_name"] == "pathological_stage"
    assert observations[0]["current_value"] == "ypT1CN0M0"


def test_inferred_tnm_requires_provenance_and_review(client):
    patient = create_patient(client)
    rejected = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "clinical_stage", "value": "cT2N1M0", "confidence": "MEDIUM",
              "source_mode": "INFERRED"},
    )
    assert rejected.status_code == 422

    accepted = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "clinical_stage",
            "value": "cT2N1M0",
            "confidence": "MEDIUM",
            "source_mode": "INFERRED",
            "ruleset_version": "AJCC-breast-8-local-v1",
            "inference_basis": [
                {"component": "T", "fact": "最大径25 mm", "source_text": "肿块约25 mm"}
            ],
        },
    )
    assert accepted.status_code == 201
    assert accepted.json()["status"] == "REVIEW_REQUIRED"
    detail = client.get(f"/api/patients/{patient['id']}").json()
    assert detail["observations"][0]["source_mode"] == "INFERRED"
    assert detail["audit_log"][0]["operation"] == "AI_INFER"
