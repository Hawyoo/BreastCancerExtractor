import json

from app.config import settings
from app.db import connect, init_db, utc_now
from app.text_learning import (
    build_text_learning_profile,
    import_text_learning_payload,
    text_learning_prompt_section,
)


def test_reviewed_field_becomes_few_shot_example_with_ocr_location(tmp_path, monkeypatch):
    database = tmp_path / "runtime" / "catalog.sqlite"
    data_path = tmp_path / "database"
    monkeypatch.setattr(settings, "database_path", database)
    monkeypatch.setattr(settings, "data_path", data_path)
    init_db()
    now = utc_now()

    ocr_payload = {
        "engine": "paddleocr",
        "lines": [
            {"text": "免疫组化结果：", "score": 0.99, "box": [20, 90, 210, 120]},
            {
                "text": "HER-2：肿瘤细胞膜呈中等染色，评分2+",
                "score": 0.98,
                "box": [20, 130, 620, 170],
            },
            {"text": "Ki-67阳性指数约30%", "score": 0.97, "box": [20, 180, 350, 215]},
        ],
    }
    evidence_text = "HER-2：肿瘤细胞膜呈中等染色，评分2+"

    with connect() as db:
        patient_id = db.execute(
            "INSERT INTO patients(patient_code,status,created_at,updated_at) VALUES(?,?,?,?)",
            ("7654321", "VERIFIED", now, now),
        ).lastrowid
        db.execute(
            """INSERT INTO documents
               (id,patient_id,display_name,document_type,status,relative_path,sha256,width,height,sanitization_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "doc-her2",
                patient_id,
                "病理报告.png",
                "BIOPSY_PATHOLOGY",
                "AI_PROCESSED",
                "patients/7654321/doc-her2.png",
                "abc123",
                1000,
                800,
                "{}",
                now,
            ),
        )
        db.execute(
            """INSERT INTO ocr_results(document_id,engine,version,full_text,result_json,created_at)
               VALUES(?,?,?,?,?,?)""",
            (
                "doc-her2",
                "paddleocr",
                "test",
                "\n".join(line["text"] for line in ocr_payload["lines"]),
                json.dumps(ocr_payload, ensure_ascii=False),
                now,
            ),
        )
        db.execute(
            """INSERT INTO observations
               (id,patient_id,document_id,field_name,ai_value,current_value,raw_text,confidence,status,source_mode,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "obs-her2",
                patient_id,
                "doc-her2",
                "primary_her2",
                "POSITIVE",
                "2+",
                evidence_text,
                "HIGH",
                "VERIFIED",
                "RECORDED",
                now,
                now,
            ),
        )
        db.execute(
            """INSERT INTO audit_log
               (patient_id,document_id,field_name,operation,old_value,new_value,operator,reason,timestamp)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                patient_id,
                "doc-her2",
                "primary_her2",
                "USER_EDIT_VERIFIED",
                "POSITIVE",
                "2+",
                "local-user",
                "HER2 2+保留原始IHC评分",
                now,
            ),
        )

    profile = build_text_learning_profile({"primary_her2"})
    assert profile["version"] == 3
    assert profile["learning_mode"] == "field_examples"
    assert profile["example_count"] == 1

    field = profile["fields"][0]
    assert field["field_name"] == "primary_her2"
    assert field["edit_count"] == 1
    assert field["example_count"] == 1
    example = field["examples"][0]
    assert example["document_type"] == "BIOPSY_PATHOLOGY"
    assert example["ai_value"] == "POSITIVE"
    assert example["verified_value"] == "2+"
    assert example["value_changed"] is True
    assert example["correction_reason"] == "HER2 2+保留原始IHC评分"

    evidence = example["evidence"]
    assert evidence["text"] == evidence_text
    assert evidence["matched"] is True
    assert evidence["line_ids"] == [2]
    assert evidence["context_before"] == "免疫组化结果："
    assert evidence["context_after"] == "Ki-67阳性指数约30%"
    assert evidence["ocr_confidence"] == 0.98
    assert evidence["lines"][0]["bbox"] == [20.0, 130.0, 620.0, 170.0]
    assert evidence["lines"][0]["relative_bbox"] == [0.02, 0.1625, 0.62, 0.2125]

    prompt = text_learning_prompt_section({"primary_her2"})
    assert "few_shot_field_and_evidence_learning" in prompt
    assert evidence_text in prompt
    assert '"ai_value":"POSITIVE"' in prompt
    assert '"verified_value":"2+"' in prompt
    assert "context_before" in prompt
    assert "bbox" not in prompt
    assert "line_id" not in prompt


def test_v3_examples_survive_export_import_and_remain_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_path", tmp_path / "database")
    monkeypatch.setattr(settings, "database_path", tmp_path / "missing" / "catalog.sqlite")

    payload = {
        "type": "bce_text_learning",
        "version": 3,
        "fields": [
            {
                "field_name": "primary_er",
                "corrections": [],
                "manual_values": [],
                "examples": [
                    {
                        "document_type": "BIOPSY_PATHOLOGY",
                        "ai_value": "POSITIVE",
                        "verified_value": "POSITIVE",
                        "human_verified": True,
                        "evidence": {
                            "text": "ER（约90%肿瘤细胞强阳性）",
                            "matched": True,
                            "line_ids": [31],
                            "context_before": "免疫组化：",
                            "context_after": "PR约80%阳性",
                            "ocr_confidence": 0.97,
                            "match_score": 0.96,
                            "lines": [
                                {
                                    "line_id": 31,
                                    "text": "ER（约90%肿瘤细胞强阳性）",
                                    "ocr_confidence": 0.97,
                                    "relevance": 1.0,
                                    "bbox": [182, 416, 793, 462],
                                    "relative_bbox": [0.18, 0.41, 0.79, 0.46],
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    first = import_text_learning_payload(payload, source_name="machine-a.json")
    second = import_text_learning_payload(payload, source_name="machine-a-copy.json")
    assert first["imported"] is True
    assert first["imported_example_count"] == 1
    assert second["duplicate"] is True

    profile = build_text_learning_profile({"primary_er"})
    assert profile["example_count"] == 1
    example = profile["fields"][0]["examples"][0]
    assert example["evidence"]["line_ids"] == [31]
    assert example["evidence"]["lines"][0]["bbox"] == [182.0, 416.0, 793.0, 462.0]
