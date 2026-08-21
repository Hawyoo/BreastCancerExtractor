from pathlib import Path

ROOT = Path(__file__).parents[1]


def _script() -> str:
    return (ROOT / "app/static/editor_interactions.js").read_text(encoding="utf-8")


def _green_override() -> str:
    return (ROOT / "app/static/roi_green.js").read_text(encoding="utf-8")


def test_canvas_keeps_default_cursor_until_drawing_starts():
    script = _script()
    assert 'canvas.style.cursor = "default"' in script
    assert "BLACK_CROSSHAIR_CURSOR" in script
    assert "stroke='black'" in script
    assert "if (!hit)" in script
    assert "canvas.style.cursor = BLACK_CROSSHAIR_CURSOR" in script


def test_preview_colors_remain_mode_specific():
    script = _script()
    assert 'crop: {fill: "rgba(244,201,93,.18)", stroke: "#f4c95d"}' in script
    assert 'redact: {fill: "rgba(18,18,18,.42)", stroke: "#111111"}' in script
    assert 'roi: {fill: "rgba(39,147,104,.16)", stroke: "#31a87a"}' in script


def test_final_roi_presentation_stays_green_during_drawing_and_editing():
    script = _green_override()
    assert 'const ROI_FILL = "rgba(39,147,104,.16)"' in script
    assert 'const ROI_STROKE = "#31a87a"' in script
    assert 'state.mode === "roi" && state.drawing' in script
    assert 'gesture?.target?.kind === "roi"' in script
    assert 'gesture.target.kind = "roi-green-render"' in script
    assert 'drawDisplayOverlay(rect, ROI_FILL, ROI_STROKE, "")' in script
    assert "#f2bd3e" not in script
    assert "rgba(255,196,68" not in script


def test_redaction_has_resize_handles_and_no_white_label():
    script = _script()
    for handle in ["nw", "n", "ne", "e", "se", "s", "sw", "w"]:
        assert f"{handle}:" in script
    assert 'action: "resize"' in script
    assert "resizeRotatedRect" in script
    assert 'drawPolygon(rect, COLORS.redact.fill, COLORS.redact.stroke, selected, "")' in script
    assert "隐私遮盖" not in script


def test_resize_and_rotation_work_for_rotated_boxes():
    script = _script()
    assert "function resizeRotatedRect" in script
    assert "normalizeAngle(original.rotation)" in script
    assert 'gesture.action === "rotate"' in script
    assert "cursorForHandle(gesture.handle)" in script


def test_final_sanitized_mask_renderer_is_not_reimplemented_here():
    script = _script()
    green = _green_override()
    assert "buildSanitizedBlob" not in script
    assert "out.fillRect" not in script
    assert "buildSanitizedBlob" not in green
    assert "out.fillRect" not in green


def test_unified_editor_and_green_roi_layers_load_before_launcher_only_shutdown_gate():
    shutdown = (ROOT / "app/static/shutdown.js").read_text(encoding="utf-8")
    assert 'editorScript.src = "/editor_interactions.js"' in shutdown
    assert 'greenScript.src = "/roi_green.js"' in shutdown
    assert 'editorScript.onload = loadRoiGreen' in shutdown
    assert 'data-bce-editor-interactions="1"' in shutdown
    assert 'data-bce-roi-green="1"' in shutdown
    assert "if (!token) return" in shutdown
    assert shutdown.index('editorScript.src = "/editor_interactions.js"') < shutdown.index("if (!token) return")
    assert shutdown.index('greenScript.src = "/roi_green.js"') < shutdown.index("if (!token) return")
