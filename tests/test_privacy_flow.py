import csv
import io
import json

from PIL import Image


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


def test_all_patient_preview_and_excel_compatible_chinese_csv(client):
    patient = client.post("/api/patients", json={"patient_code": "0123456"}).json()
    client.post(
        f"/api/patients/{patient['id']}/observations",
        json={"field_name": "sex", "value": "FEMALE", "confidence": "HIGH"},
    )

    preview = client.get("/api/data-preview").json()
    assert len(preview["columns"]) == 158
    assert preview["columns"][0]["label"] == "病案号（7位）"
    assert preview["columns"][-1]["label"] == "其他收集信息"
    assert preview["rows"][0]["values"]["record_number"] == "0123456"
    assert preview["rows"][0]["values"]["sex"] == "女"
    assert preview["rows"][0]["statuses"]["sex"] == "AI_PROCESSED"

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


def test_conditional_question_exports_na_when_prerequisite_is_no(client):
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
    assert preview["rows"][0]["values"]["neoadjuvant_cycles"] == "NA"


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
    assert preview["rows"][0]["values"]["neoadjuvant_cycles"] == "NA"

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

    async def fake_extract(_model, _prompt, _progress=None, **_options):
        return {"observations": []}

    monkeypatch.setattr("app.main.recognize_image", fake_ocr)
    monkeypatch.setattr("app.main.list_extraction_models", fake_models)
    monkeypatch.setattr("app.main.extract_structured", fake_extract)
    assert client.post(f"/api/documents/{uploaded['id']}/ocr").status_code == 200
    assert client.post(f"/api/documents/{uploaded['id']}/extract").status_code == 200

    detail = client.get(f"/api/patients/{patient['id']}").json()
    observation = next(item for item in detail["observations"] if item["field_name"] == "metastatic_at_presentation")
    assert observation["current_value"] == "NO"
    assert observation["source_mode"] == "INFERRED"
    assert observation["status"] == "REVIEW_REQUIRED"
    assert "AI_DEFAULT" in [item["operation"] for item in detail["audit_log"]]


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
