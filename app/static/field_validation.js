(() => {
  const INTEGER_FIELDS = new Set(["menarche_age", "menopause_age"]);

  function installStyles() {
    if (document.querySelector("#field-validation-style")) return;
    const style = document.createElement("style");
    style.id = "field-validation-style";
    style.textContent = `
      .field-format-hint{display:block;margin-top:4px;font-size:11px;line-height:1.45;color:var(--muted,#66736d)}
      .field-validation-message{display:block;margin-top:4px;font-size:11px;line-height:1.45;color:#b42318;font-weight:600}
      .field-validation-message[hidden],.field-format-hint[hidden]{display:none}
      .field-clear-choice{margin-left:4px;border-style:dashed!important}
      .patient-review-inline-input.field-invalid,#review-current-value.field-invalid{border-color:#b42318!important;outline-color:#b42318!important}
      .patient-review-reason{display:block;width:100%;margin-top:6px;padding:6px 8px;border:1px solid var(--line,#dedbd2);border-radius:7px;background:var(--control,#fff);color:var(--ink,#17251f);font:inherit;font-size:11px}
    `;
    document.head.appendChild(style);
  }

  function observationForKey(key) {
    return (state.patient?.observations || []).find(item => item.field_name === key) || null;
  }

  function optionsFor(observation) {
    const options = Array.isArray(observation?.field_options) ? observation.field_options : [];
    if (options.length) return options;
    const allowed = Array.isArray(observation?.allowed_values) ? observation.allowed_values : [];
    return allowed.map(value => ({label: String(value), value: String(value)}));
  }

  function displayOptions(observation) {
    return optionsFor(observation)
      .map(option => String(option.label ?? option.value ?? "").trim())
      .filter(Boolean)
      .join(" / ");
  }

  function fieldType(observation) {
    if (!observation) return "";
    if (INTEGER_FIELDS.has(observation.field_name)) return "integer";
    return String(observation.field_type || "").toLowerCase();
  }

  function normalizeMeasurementValue(observation, value) {
    const text = String(value ?? "").trim();
    if (fieldType(observation) !== "measurement_3d" || !text) return text;
    return text.replace(/(\d)\s*[,，xX*＊]\s*(?=\d)/g, "$1×");
  }

  function formatHint(observation) {
    if (!observation) return "允许留空保存。";
    const key = observation.field_name;
    const type = fieldType(observation);
    if (key === "clinical_stage") return "格式：cT…N…M…，例如 cT2N1M0；也可留空保存。";
    if (key === "pathological_stage") return "格式：pT…N…M… 或 ypT…N…M…，例如 ypT1N0M0；也可留空保存。";
    if (type === "measurement_3d") return "格式：各径线用乘号 × 连接，例如 25×18×15；不要用逗号。也可留空保存。";
    if (type === "integer") return "格式：整数，例如 13；也可留空保存。";
    if (type === "number") return "格式：数字，例如 12 或 12.5；也可留空保存。";
    if (type === "date") return "格式：YYYY-MM-DD，例如 2026-08-20；也可留空保存。";
    if (type === "date_or_partial_date") return "格式：YYYY、YYYY-MM 或 YYYY-MM-DD；也可留空保存。";
    const choices = displayOptions(observation);
    if (choices) return `允许值：${choices}；也可留空保存。`;
    return "允许留空保存。";
  }

  function parseMulti(value) {
    return String(value ?? "")
      .replace(/[\[\]"']/g, "")
      .split(/[,，;；|]+/)
      .map(item => item.trim())
      .filter(Boolean);
  }

  function validationMessage(observation, value) {
    const text = String(value ?? "").trim();
    if (!text) return "";
    if (!observation) return "";
    const key = observation.field_name;
    const type = fieldType(observation);

    if (key === "clinical_stage") {
      return /^(?:c|yc)T.+N.+M.+$/i.test(text) ? "" : "格式不符合要求：临床 TNM 请填写如 cT2N1M0；如果暂无结果，可以留空保存。";
    }
    if (key === "pathological_stage") {
      return /^(?:p|yp)T.+N.+M.+$/i.test(text) ? "" : "格式不符合要求：病理 TNM 请填写如 pT2N1M0 或 ypT1N0M0；如果暂无结果，可以留空保存。";
    }
    if (type === "integer") {
      return /^\d+$/.test(text) ? "" : "格式不符合要求：该字段只能填写整数；如果暂无结果，可以留空保存。";
    }
    if (type === "number") {
      return /^-?(?:\d+(?:\.\d*)?|\.\d+)$/.test(text) ? "" : "格式不符合要求：该字段只能填写数字；如果暂无结果，可以留空保存。";
    }
    if (type === "date") {
      return /^\d{4}-\d{2}-\d{2}$/.test(text) ? "" : "格式不符合要求：日期请填写 YYYY-MM-DD；如果暂无结果，可以留空保存。";
    }
    if (type === "date_or_partial_date") {
      return /^\d{4}(?:-\d{2}(?:-\d{2})?)?$/.test(text) ? "" : "格式不符合要求：请填写 YYYY、YYYY-MM 或 YYYY-MM-DD；如果暂无结果，可以留空保存。";
    }

    const options = optionsFor(observation);
    if (!options.length) return "";
    const allowed = new Set(options.map(option => String(option.value ?? "").trim().toUpperCase()).filter(Boolean));
    if (type === "multiselect") {
      const values = parseMulti(text).map(item => item.toUpperCase());
      if (values.length && values.every(item => allowed.has(item))) return "";
    } else if (allowed.has(text.toUpperCase())) {
      return "";
    }
    return `格式不符合要求：请选择 ${displayOptions(observation)}；如果暂无结果，可以留空保存。`;
  }

  function ensureSequentialMessages() {
    const choices = document.querySelector("#review-choice-options");
    const valueLabel = document.querySelector("#review-current-value-label");
    const anchor = choices || valueLabel;
    if (!anchor) return {};
    let hint = document.querySelector("#review-format-hint");
    if (!hint) {
      hint = document.createElement("small");
      hint.id = "review-format-hint";
      hint.className = "field-format-hint";
      anchor.insertAdjacentElement("afterend", hint);
    }
    let message = document.querySelector("#review-validation-message");
    if (!message) {
      message = document.createElement("small");
      message.id = "review-validation-message";
      message.className = "field-validation-message";
      message.hidden = true;
      hint.insertAdjacentElement("afterend", message);
    }
    return {hint, message};
  }

  function updateSequentialValidation() {
    const observation = typeof selectedObservation === "function" ? selectedObservation() : null;
    if (!observation) return true;
    const valueField = document.querySelector("#review-current-value");
    const saveButton = document.querySelector("#save-field-edit");
    const verifyButton = document.querySelector("#verify-field");
    if (!valueField || !saveButton || !verifyButton) return true;
    const {hint, message} = ensureSequentialMessages();
    if (hint) hint.textContent = formatHint(observation);
    const error = validationMessage(observation, valueField.value);
    if (message) {
      message.textContent = error;
      message.hidden = !error;
    }
    valueField.classList.toggle("field-invalid", Boolean(error));
    saveButton.disabled = Boolean(error);
    verifyButton.disabled = Boolean(error);
    return !error;
  }

  function normalizeSequentialMeasurement() {
    const observation = typeof selectedObservation === "function" ? selectedObservation() : null;
    const valueField = document.querySelector("#review-current-value");
    if (!observation || !valueField) return;
    valueField.value = normalizeMeasurementValue(observation, valueField.value);
  }

  function addSequentialClearChoice() {
    const container = document.querySelector("#review-choice-options");
    const valueField = document.querySelector("#review-current-value");
    if (!container || container.hidden || !valueField || container.querySelector(".field-clear-choice")) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "review-choice-option field-clear-choice";
    button.textContent = "留空";
    button.title = "清空该字段并允许保存";
    button.onclick = () => {
      container.querySelectorAll(".review-choice-option.active").forEach(item => item.classList.remove("active"));
      valueField.value = "";
      updateSequentialValidation();
    };
    container.appendChild(button);
    container.querySelectorAll(".review-choice-option:not(.field-clear-choice)").forEach(item => {
      item.addEventListener("click", () => queueMicrotask(updateSequentialValidation));
    });
  }

  function decorateSequentialReview() {
    const observation = typeof selectedObservation === "function" ? selectedObservation() : null;
    if (!observation) return;
    const valueField = document.querySelector("#review-current-value");
    if (!valueField) return;
    valueField.placeholder = fieldType(observation) === "integer" ? "请输入整数，或留空" : (valueField.placeholder || "可留空保存");
    valueField.oninput = updateSequentialValidation;
    addSequentialClearChoice();
    updateSequentialValidation();
  }

  const previousRenderFieldReview = typeof renderFieldReview === "function" ? renderFieldReview : null;
  if (previousRenderFieldReview) {
    renderFieldReview = () => {
      previousRenderFieldReview();
      decorateSequentialReview();
    };
  }

  ["save-field-edit", "verify-field"].forEach(id => {
    document.querySelector(`#${id}`)?.addEventListener("click", event => {
      normalizeSequentialMeasurement();
      if (updateSequentialValidation()) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    }, true);
  });

  function inlineInput(row) {
    return row.querySelector(".inline-choice-editor input[type=hidden], .patient-review-inline-input, textarea:not([readonly]), input:not([readonly]):not([type=hidden]):not(.patient-review-reason)");
  }

  function ensureInlineMessages(row, observation) {
    const editorCell = row.children?.[1];
    if (!editorCell) return {};
    let hint = row.querySelector(".field-format-hint");
    if (!hint) {
      hint = document.createElement("small");
      hint.className = "field-format-hint";
      editorCell.appendChild(hint);
    }
    hint.textContent = formatHint(observation);
    let message = row.querySelector(".field-validation-message");
    if (!message) {
      message = document.createElement("small");
      message.className = "field-validation-message";
      message.hidden = true;
      editorCell.appendChild(message);
    }
    return {hint, message};
  }

  function ensureInlineReason(row) {
    const editorCell = row.children?.[1];
    const save = row.querySelector(".patient-review-save");
    if (!editorCell || !save) return null;
    let input = row.querySelector(".patient-review-reason");
    if (!input) {
      input = document.createElement("input");
      input.type = "text";
      input.className = "patient-review-reason";
      input.maxLength = 500;
      input.placeholder = "修改原因（可选）";
      input.title = "该内容会写入审计记录的修改原因";
      editorCell.appendChild(input);
    }
    return input;
  }

  function updateInlineValidation(row) {
    const key = row?.dataset?.fieldKey;
    const observation = observationForKey(key);
    const input = inlineInput(row);
    if (!key || !input) return true;
    const {message} = ensureInlineMessages(row, observation);
    const error = validationMessage(observation, input.value);
    if (message) {
      message.textContent = error;
      message.hidden = !error;
    }
    input.classList.toggle("field-invalid", Boolean(error));
    const save = row.querySelector(".patient-review-save");
    if (save) save.disabled = Boolean(error);
    return !error;
  }

  function addInlineClearChoice(row) {
    const editor = row.querySelector(".inline-choice-editor");
    const hidden = editor?.querySelector("input[type=hidden]");
    if (!editor || !hidden || editor.querySelector(".field-clear-choice")) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "review-choice-option field-clear-choice";
    button.textContent = "留空";
    button.title = "清空该字段并允许保存";
    button.onclick = () => {
      editor.querySelectorAll(".review-choice-option.active").forEach(item => item.classList.remove("active"));
      hidden.value = "";
      updateInlineValidation(row);
    };
    editor.appendChild(button);
    editor.querySelectorAll(".review-choice-option:not(.field-clear-choice)").forEach(item => {
      item.addEventListener("click", () => queueMicrotask(() => updateInlineValidation(row)));
    });
  }

  function decorateInlineRows() {
    document.querySelectorAll("#patient-review-body tr[data-field-key]").forEach(row => {
      const input = inlineInput(row);
      if (!input) return;
      addInlineClearChoice(row);
      ensureInlineReason(row);
      input.addEventListener("input", () => updateInlineValidation(row));
      input.addEventListener("change", () => updateInlineValidation(row));
      updateInlineValidation(row);
    });
  }

  async function saveInlineValue(row, button, input) {
    const key = row.dataset.fieldKey;
    const observation = observationForKey(key);
    const reasonInput = ensureInlineReason(row);
    const value = normalizeMeasurementValue(observation, input.value);
    input.value = value;
    const reason = String(reasonInput?.value ?? "").trim() || (value ? "患者事后回顾手动修改" : "人工明确留空");
    const oldValue = observation ? String(observation.current_value ?? "").trim() : null;
    const {message} = ensureInlineMessages(row, observation);
    if (observation && value === oldValue) {
      if (message) {
        message.textContent = "字段值没有变化，无需重复保存。";
        message.hidden = false;
      }
      return;
    }

    button.disabled = true;
    const originalText = button.textContent;
    button.textContent = "保存中…";
    try {
      if (observation) {
        await api(`/api/observations/${observation.id}`, {
          method: "PATCH",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({value, operator: "local-user", reason}),
        });
      } else {
        await api(`/api/patients/${state.patient.id}/observations`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            field_name: key,
            value,
            raw_text: value ? "人工手动补充" : "人工明确留空",
            confidence: "LOW",
            source_mode: "RECORDED",
            operator: "local-user",
            reason,
          }),
        });
      }
      await refreshCurrentPatient(state.patient.id);
      if (typeof showPatientReview === "function") await showPatientReview(key, false);
    } catch (error) {
      if (message) {
        message.textContent = `保存失败：${error.message}`;
        message.hidden = false;
      }
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  }

  const reviewBody = document.querySelector("#patient-review-body");
  if (reviewBody) {
    reviewBody.addEventListener("click", event => {
      const button = event.target.closest(".patient-review-save");
      if (!button) return;
      const row = button.closest("tr[data-field-key]");
      if (!row) return;
      const input = inlineInput(row);
      if (!input) return;
      const observation = observationForKey(row.dataset.fieldKey);
      input.value = normalizeMeasurementValue(observation, input.value);
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!updateInlineValidation(row)) return;
      saveInlineValue(row, button, input);
    }, true);

    new MutationObserver(() => queueMicrotask(decorateInlineRows))
      .observe(reviewBody, {childList: true, subtree: true});
  }

  installStyles();
  decorateSequentialReview();
  decorateInlineRows();
})();
