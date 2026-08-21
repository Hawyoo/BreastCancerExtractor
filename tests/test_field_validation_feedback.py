from pathlib import Path

ROOT = Path(__file__).parents[1]


def _script() -> str:
    return (ROOT / "app/static/field_validation.js").read_text(encoding="utf-8")


def test_invalid_values_use_inline_red_message_not_popup_feedback():
    script = _script()
    assert "field-validation-message" in script
    assert "color:#b42318" in script
    assert "格式不符合要求" in script
    assert "event.stopImmediatePropagation()" in script
    assert "alert(" not in script
    assert "toast(`格式" not in script


def test_blank_value_is_explicitly_allowed_for_strict_fields():
    script = _script()
    assert 'if (!text) return "";' in script
    assert "也可留空保存" in script
    assert 'value ? "人工手动补充" : "人工明确留空"' in script
    assert 'reason = String(reasonInput?.value ?? "").trim()' in script
    assert 'operator: "local-user"' in script


def test_choice_fields_offer_a_clear_to_blank_action():
    script = _script()
    assert 'button.textContent = "留空"' in script
    assert 'valueField.value = ""' in script
    assert 'hidden.value = ""' in script
    assert "field-clear-choice" in script


def test_common_strict_formats_have_visible_guidance():
    script = _script()
    assert "格式：整数，例如 13" in script
    assert "格式：数字，例如 12 或 12.5" in script
    assert "格式：YYYY-MM-DD" in script
    assert "YYYY、YYYY-MM 或 YYYY-MM-DD" in script
    assert "cT2N1M0" in script
    assert "ypT1N0M0" in script
    assert "允许值：" in script


def test_measurements_show_one_to_three_dimensions_with_multiplication_sign():
    script = _script()
    assert "尺寸可记录 1–3 个径线" in script
    assert "25、25×18、25×18×15" in script
    assert "多个径线统一用乘号 × 连接" in script
    assert "不要用逗号" in script
    assert "normalizeMeasurementValue" in script


def test_sequential_review_no_longer_disables_blank_integer_values():
    script = _script()
    assert "saveButton.disabled = Boolean(error)" in script
    assert "verifyButton.disabled = Boolean(error)" in script
    assert "valueField.oninput = updateSequentialValidation" in script
    assert "const error = validationMessage(observation, valueField.value)" in script


def test_patient_review_save_reuses_existing_observation_or_creates_one():
    script = _script()
    assert "async function saveInlineValue" in script
    assert "if (observation)" in script
    assert 'method: "PATCH"' in script
    assert 'method: "POST"' in script
    assert "field_name: key" in script
    assert "await refreshCurrentPatient(state.patient.id)" in script


def test_patient_review_can_record_a_custom_edit_reason():
    script = _script()
    assert "patient-review-reason" in script
    assert 'input.placeholder = "修改原因（可选）"' in script
    assert "该内容会写入审计记录的修改原因" in script
    assert 'body: JSON.stringify({value, operator: "local-user", reason})' in script


def test_validation_module_loads_after_review_inline_on_all_runtimes():
    shutdown = (ROOT / "app/static/shutdown.js").read_text(encoding="utf-8")
    review = shutdown.index('reviewScript.src = "/review_inline.js"')
    validation = shutdown.index('validationScript.src = "/field_validation.js"')
    early_return = shutdown.index("if (!token) return")
    assert validation < review < early_return
    assert "reviewScript.onload = loadFieldValidation" in shutdown
    assert 'data-bce-field-validation="1"' in shutdown
