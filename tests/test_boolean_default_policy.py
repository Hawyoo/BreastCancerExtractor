from pathlib import Path

from app.knowledge import HUMAN_YES_NO_OPTIONS, PATIENT_LEVEL_BOOLEAN_POLICY, extraction_prompt, questionnaire_field_index

ROOT = Path(__file__).parents[1]


def test_yes_no_fields_offer_unknown_for_human_override():
    index = questionnaire_field_index()
    assert PATIENT_LEVEL_BOOLEAN_POLICY["unmentioned_default"] == "NO"
    assert [item["value"] for item in HUMAN_YES_NO_OPTIONS] == ["YES", "NO", "UNKNOWN"]
    for key in ("has_chronic_disease", "recurrence", "death", "menopausal_status"):
        values = [item["value"] for item in index[key]["field_options"]]
        assert values == ["YES", "NO", "UNKNOWN"]


def test_document_prompt_does_not_turn_silence_into_per_document_no():
    prompt, _ = extraction_prompt("ADMISSION", "患者因乳腺肿块入院。")
    assert "单张文档层面输出NO或UNKNOWN" in prompt
    assert "患者级汇总时把始终未提及的是否型题目统一默认成NO" in prompt
    assert "DEFAULT_UNMENTIONED" in prompt


def test_post_review_defaults_missing_yes_no_fields_but_keeps_manual_unknown():
    javascript = (ROOT / "app/static/review_inline.js").read_text(encoding="utf-8")
    assert 'const YES_NO_FIELD_KEYS = new Set([' in javascript
    assert '{label: "不详", value: "UNKNOWN"}' in javascript
    assert 'return "NO";' in javascript
    assert 'status === "DEFAULT_UNMENTIONED" ? "病历未提及 · 默认否"' in javascript
    assert 'row.values[key] = "否"' in javascript
    assert 'row.statuses[key] = "DEFAULT_UNMENTIONED"' in javascript
    assert 'raw_text: YES_NO_FIELD_KEYS.has(column.key) ? "人工覆盖患者级默认否"' in javascript


def test_ui_csv_export_uses_defaulted_dataset_instead_of_server_blank_csv():
    javascript = (ROOT / "app/static/review_inline.js").read_text(encoding="utf-8")
    assert "applyBooleanDefaultsToDataset" in javascript
    assert 'exportButton.onclick = async () =>' in javascript
    assert 'new Blob(["\\ufeff", lines.join("\\r\\n")]' in javascript
    assert '/api/data-preview.csv?' not in javascript
