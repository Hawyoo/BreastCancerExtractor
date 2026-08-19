from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_saved_redaction_uses_crop_relative_coordinates():
    script = (ROOT / "app/static/derived_fields.js").read_text(encoding="utf-8")
    assert "redactionCenterX - cropCenterX" in script
    assert "redactionCenterY - cropCenterY" in script
    assert "buildSanitizedBlob = () => new Promise" in script


def test_improve_learning_summarizes_human_edits_and_manual_fills():
    script = (ROOT / "app/static/derived_fields.js").read_text(encoding="utf-8")
    assert 'button.textContent = "改进学习"' in script
    assert '"USER_EDIT", "USER_EDIT_VERIFIED"' in script
    assert '"人工手动补充"' in script
    assert 'localStorage.setItem(LEARNING_STORAGE_KEY' in script
    assert 'LEARNING_EXCLUDED_FIELDS = new Set(["record_number", "contact"])' in script
