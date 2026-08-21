from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_saved_redaction_uses_crop_relative_coordinates():
    script = (ROOT / "app/static/derived_fields.js").read_text(encoding="utf-8")
    assert "redactionCenterX - cropCenterX" in script
    assert "redactionCenterY - cropCenterY" in script
    assert "buildSanitizedBlob = () => new Promise" in script


def test_learning_ui_keeps_only_json_import_and_export_controls():
    script = (ROOT / "app/static/text_learning_import.js").read_text(encoding="utf-8")
    assert 'document.querySelector("#improve-learning")?.remove()' in script
    assert 'document.querySelector("#learning-summary-dialog")?.remove()' in script
    assert 'button.textContent = "导出学习JSON"' in script
    assert 'importButton.textContent = "导入学习JSON"' in script
    assert 'api("/api/text-learning")' in script
    assert 'api("/api/text-learning/import"' in script
    assert "20 * 1024 * 1024" in script
