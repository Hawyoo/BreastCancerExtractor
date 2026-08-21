from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_saved_redaction_uses_crop_relative_coordinates():
    script = (ROOT / "app/static/derived_fields.js").read_text(encoding="utf-8")
    assert "redactionCenterX - cropCenterX" in script
    assert "redactionCenterY - cropCenterY" in script
    assert "buildSanitizedBlob = () => new Promise" in script


def test_learning_ui_keeps_only_json_import_and_export_controls():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    derived = (ROOT / "app/static/derived_fields.js").read_text(encoding="utf-8")
    script = (ROOT / "app/static/text_learning_import.js").read_text(encoding="utf-8")
    assert 'id="export-text-learning"' in html
    assert 'id="import-text-learning"' in html
    assert 'id="import-text-learning-file"' in html
    assert 'src="/text_learning.js"' in html
    assert 'src="/text_learning_import.js"' in html
    assert "改进学习" not in html
    assert "installLearningButton" not in derived
    assert 'api("/api/text-learning")' in script
    assert 'api("/api/text-learning/import"' in script
    assert "20 * 1024 * 1024" in script
    assert "MutationObserver" not in script


def test_wrong_text_location_can_be_deleted_and_restored():
    script = (ROOT / "app/static/text_learning.js").read_text(encoding="utf-8")
    assert 'button.textContent = observation.evidence_status === "REJECTED" ? "恢复自动定位" : "删除错误定位"' in script
    assert 'method: "DELETE"' in script
    assert "/evidence-location/restore" in script
    assert 'observation.evidence_status = "REJECTED"' in script
    assert "已排除出定位学习" in script
