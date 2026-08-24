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


def test_smart_evidence_highlight_has_no_label_over_the_source_text():
    script = (ROOT / "app/static/text_learning.js").read_text(encoding="utf-8")
    assert "ctx.fillRect(x, y, width, height)" in script
    assert "ctx.strokeRect(x, y, width, height)" in script
    assert "文本定位 ${Math.round(item.score * 100)}%" not in script
    assert "ctx.fillText(label, x + 5" not in script


def test_crop_overlay_has_no_yellow_text_label():
    enhancements = (ROOT / "app/static/enhancements.js").read_text(encoding="utf-8")
    interactions = (ROOT / "app/static/editor_interactions.js").read_text(encoding="utf-8")
    assert 'drawRotatedOverlay(state.crop, "rgba(244,201,93,.04)", "#f4c95d", "",' in enhancements
    crop_polygon = (
        'drawPolygon(state.crop, "rgba(244,201,93,.10)", COLORS.crop.stroke, '
        'state.cropEditable && state.mode === "crop", "")'
    )
    assert crop_polygon in interactions
    assert 'state.cropEditable && state.mode === "crop", "裁剪"' not in enhancements + interactions


def test_zoomed_canvas_keeps_its_left_edge_scrollable():
    styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    assert ".canvas-shell { position: relative; min-height: 340px; display: flex;" in styles
    assert "justify-content: flex-start" in styles
    assert "#image-canvas { display: block; flex: 0 0 auto;" in styles
    assert "margin: auto" in styles
