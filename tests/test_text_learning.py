from pathlib import Path

from app.config import settings
from app.db import connect, init_db, utc_now
from app.knowledge import extraction_prompt
from app.text_learning import build_text_learning_profile, text_learning_prompt_section

ROOT = Path(__file__).resolve().parents[1]


def test_text_learning_is_empty_when_runtime_catalog_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", tmp_path / "missing" / "catalog.sqlite")
    profile = build_text_learning_profile({"primary_her2"})
    assert profile["field_count"] == 0
    assert profile["fields"] == []


def test_human_corrections_become_machine_readable_learning_and_prompt_context(tmp_path, monkeypatch):
    database = tmp_path / "catalog.sqlite"
    monkeypatch.setattr(settings, "database_path", database)
    init_db()
    now = utc_now()

    with connect() as db:
        patient_id = db.execute(
            "INSERT INTO patients(patient_code,status,created_at,updated_at) VALUES(?,?,?,?)",
            ("1234567", "AI_PROCESSED", now, now),
        ).lastrowid
        for _ in range(2):
            db.execute(
                """INSERT INTO audit_log
                   (patient_id,field_name,operation,old_value,new_value,operator,reason,timestamp)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    patient_id,
                    "primary_her2",
                    "USER_EDIT",
                    "POSITIVE",
                    "2+",
                    "local-user",
                    "HER2 2+不应直接映射为阳性",
                    now,
                ),
            )
        db.execute(
            """INSERT INTO audit_log
               (patient_id,field_name,operation,old_value,new_value,operator,reason,timestamp)
               VALUES(?,?,?,?,?,?,?,?)""",
            (patient_id, "contact", "USER_EDIT", "1", "2", "local-user", "排除敏感字段", now),
        )
        db.execute(
            """INSERT INTO observations
               (id,patient_id,field_name,ai_value,current_value,raw_text,confidence,status,source_mode,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "manual-her2",
                patient_id,
                "primary_her2",
                None,
                "3+",
                "人工手动补充",
                "LOW",
                "VERIFIED",
                "RECORDED",
                now,
                now,
            ),
        )

    profile = build_text_learning_profile({"primary_her2", "contact"})
    assert profile["field_count"] == 1
    field = profile["fields"][0]
    assert field["field_name"] == "primary_her2"
    assert field["edit_count"] == 2
    assert field["manual_fill_count"] == 1
    assert field["corrections"][0] == {
        "from": "POSITIVE",
        "to": "2+",
        "reason": "HER2 2+不应直接映射为阳性",
        "count": 2,
    }
    assert field["manual_values"] == [{"value": "3+", "count": 1}]

    learning = text_learning_prompt_section({"primary_her2"})
    assert "本地文本学习结果如下" in learning
    assert '"from":"POSITIVE"' in learning
    assert '"to":"2+"' in learning
    assert "绝不能把历史患者的值复制到当前患者" in learning

    prompt, allowed = extraction_prompt("BIOPSY_PATHOLOGY", "HER2（2+）")
    assert "primary_her2" in allowed
    assert "本地文本学习结果如下" in prompt
    assert "证据定位要求" in prompt
    assert "raw_text必须尽量逐字引用当前OCR中的最小充分证据" in prompt


def test_frontend_exports_learning_json_and_maps_raw_text_to_ocr_bbox():
    script = (ROOT / "app/static/text_learning.js").read_text(encoding="utf-8")
    loader = (ROOT / "app/static/shutdown.js").read_text(encoding="utf-8")

    assert 'learningScript.src = "/text_learning.js"' in loader
    assert 'button.textContent = "导出学习JSON"' in script
    assert 'type: "bce_text_learning"' in script
    assert "result_json" in script
    assert "observation.raw_text" in script
    assert "ocr_confidence" in script
    assert "line_id" in script
    assert "rectFromOcrBox" in script
    assert "locateObservationEvidence" in script
    assert '[/查看来源图/g, "文本定位"]' in script
    assert "BCE_text_learning_" in script
