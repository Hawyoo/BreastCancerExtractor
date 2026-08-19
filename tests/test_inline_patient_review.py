from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_completed_patient_review_is_inline_and_direct_editable():
    source = (ROOT / "app" / "static" / "review_inline.js").read_text(encoding="utf-8")

    assert 'reviewComplete.insertAdjacentElement("afterend", reviewDialog)' in source
    assert 'reviewDialog.classList.remove("patient-review-sidepanel")' in source
    assert 'reviewDialog.classList.add("patient-review-inline")' in source
    assert 'reviewDialog.querySelector(".manual-field-tools")?.remove()' in source
    assert 'input.className = "patient-review-inline-input"' in source
    assert 'saveInlineField(column, observation, input, saveButton)' in source
    assert '患者事后回顾内嵌面板手动修改' in source
    assert 'raw_text: "人工手动补充"' in source


def test_inline_review_is_height_limited_and_scrollable():
    css = (ROOT / "app" / "static" / "enhancements.css").read_text(encoding="utf-8")

    assert ".patient-review-inline[open]" in css
    assert "position:static!important" in css
    assert "max-height:min(58vh,620px)" in css
    assert ".patient-review-inline .patient-review-table-shell" in css
    assert "overflow:auto" in css
    assert ".patient-review-inline .manual-field-tools{display:none!important}" in css


def test_review_module_loads_even_without_windows_shutdown_control():
    source = (ROOT / "app" / "static" / "shutdown.js").read_text(encoding="utf-8")
    loader = source.index('reviewScript.src = "/review_inline.js"')
    shutdown_guard = source.index("if (!port || !token) return;")

    assert loader < shutdown_guard
