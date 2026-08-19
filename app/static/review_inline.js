(() => {
  const reviewDialog = document.querySelector("#patient-review-dialog");
  const reviewComplete = document.querySelector("#review-complete-panel");
  const sidebar = document.querySelector(".patients-panel");
  if (!reviewDialog || !reviewComplete || !sidebar) return;

  const GROUP_LABELS = {
    demographics: "基本信息",
    reproductive_history: "婚育 / 月经史",
    medical_history: "既往史",
    family_history: "家族史",
    lifestyle: "生活方式",
    diagnosis: "诊断",
    staging: "分期",
    surgery: "手术",
    neoadjuvant: "新辅助治疗",
    adjuvant_treatment: "术后治疗",
    palliative_treatment: "姑息治疗",
    treatment_response: "疗效 / 转归",
    pretreatment_ultrasound: "治疗前超声",
    pretreatment_mammography: "治疗前钼靶",
    pretreatment_mri: "治疗前 MRI",
    post_neoadjuvant_imaging: "新辅助后影像",
    primary_biopsy: "原发灶穿刺病理",
    node_biopsy: "淋巴结穿刺病理",
    metastasis_biopsy: "转移灶病理",
    surgical_pathology: "术后病理",
    biomarkers: "免疫组化 / 生物标志物",
    other: "其他",
  };
  const DIRECT_IDENTIFIER_FIELDS = new Set(["record_number", "contact"]);
  const TNM_FIELDS = new Set(["clinical_stage", "pathological_stage"]);
  const INTEGER_FIELD_KEYS = new Set(["menarche_age", "menopause_age"]);
  const YES_NO_FIELD_KEYS = new Set([
    "menopausal_status",
    "has_chronic_disease", "has_family_history", "has_given_birth",
    "smoking_history", "drinking_history", "first_breast_cancer", "prior_breast_surgery",
    "concurrent_other_cancer", "metastatic_at_presentation",
    "pre_us_available", "pre_us_nodes_normal", "pre_mmg_available", "pre_mmg_calcification",
    "pre_mri_available", "pre_mri_nodes_normal",
    "primary_biopsy_performed", "node_biopsy_performed", "metastasis_biopsy_performed",
    "neoadjuvant_received", "post_neoadj_us_available", "post_neoadj_us_tumor_response",
    "post_neoadj_us_nodes_response", "post_neoadj_mri_available", "post_neoadj_mri_tumor_response",
    "post_neoadj_mri_nodes_response", "surgery_performed", "reconstruction_performed",
    "postop_node_metastasis", "post_neoadj_pcr", "postoperative_radiotherapy",
    "postoperative_chemotherapy", "postoperative_endocrine", "postoperative_immunotherapy",
    "postoperative_targeted", "palliative_systemic_treatment", "recurrence", "followup_metastasis",
    "second_primary_cancer", "death",
  ]);
  const FIELD_LABEL_OVERRIDES = {
    has_chronic_disease: "是否患慢性病",
    chronic_disease: "慢性病（可多选）",
    chronic_disease_other: "其他慢性病（请填写）",
  };
  const YES_NO_OPTIONS = [
    {label: "是", value: "YES"},
    {label: "否", value: "NO"},
    {label: "不详", value: "UNKNOWN"},
  ];
  const CHRONIC_OPTIONS = [
    {label: "高血压", value: "HYPERTENSION"},
    {label: "糖尿病", value: "DIABETES"},
    {label: "冠心病", value: "CORONARY_HEART_DISEASE"},
    {label: "其他", value: "OTHER"},
  ];

  const originalStatusText = typeof statusText === "function" ? statusText : value => String(value || "");
  statusText = status => status === "DEFAULT_UNMENTIONED" ? "病历未提及 · 默认否" : originalStatusText(status);

  function derivedField(key) {
    return [
      "clinical_t_component", "clinical_n_component", "clinical_m_component",
      "pathological_t_component", "pathological_n_component", "pathological_m_component",
    ].includes(String(key || "")) || /_dim[123]_mm$/.test(String(key || ""));
  }

  function groupLabel(group) {
    return GROUP_LABELS[group] || group || "其他";
  }

  function displayFieldLabel(key, fallback) {
    return FIELD_LABEL_OVERRIDES[key] || fallback || key;
  }

  function normalizeYesNoValue(value) {
    const text = String(value ?? "").trim();
    return ({"是":"YES", "否":"NO", "不详":"UNKNOWN"})[text] || text.toUpperCase();
  }

  function parseMultiValue(value) {
    const text = String(value ?? "").trim();
    if (!text || text === "NA" || text === "NOT_APPLICABLE") return [];
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) return parsed.map(item => String(item).trim()).filter(Boolean);
    } catch (_) {}
    return text
      .replace(/[\[\]"']/g, "")
      .split(/[,，;；|]+/)
      .map(item => item.trim())
      .filter(Boolean);
  }

  function encodeMultiValue(values, options = CHRONIC_OPTIONS) {
    const selected = new Set(values.map(item => String(item)));
    return options.map(option => option.value).filter(value => selected.has(value)).join(",");
  }

  function isIntegerObservation(observation) {
    return observation?.field_type === "integer" || INTEGER_FIELD_KEYS.has(observation?.field_name);
  }

  function currentPatientValue(key, observations, row) {
    const observation = observations.get(key);
    if (observation) return String(observation.current_value ?? "").trim();
    const preview = row?.values?.[key];
    if (YES_NO_FIELD_KEYS.has(key)) {
      if (preview == null || preview === "" || preview === "NA") return "NO";
      return normalizeYesNoValue(preview);
    }
    return preview == null || preview === "NA" ? "" : String(preview).trim();
  }

  function inlineFieldVisible(key, observations, row) {
    if (key === "chronic_disease") {
      return currentPatientValue("has_chronic_disease", observations, row).toUpperCase() === "YES";
    }
    if (key === "chronic_disease_other") {
      if (currentPatientValue("has_chronic_disease", observations, row).toUpperCase() !== "YES") return false;
      return parseMultiValue(currentPatientValue("chronic_disease", observations, row)).includes("OTHER");
    }
    if (key === "menopause_age") {
      return currentPatientValue("menopausal_status", observations, row).toUpperCase() === "YES";
    }
    return true;
  }

  function fieldInlineOptions(key, observation) {
    if (YES_NO_FIELD_KEYS.has(key)) return YES_NO_OPTIONS;
    if (key === "chronic_disease") return CHRONIC_OPTIONS;
    return Array.isArray(observation?.field_options) ? observation.field_options : [];
  }

  function createChoiceEditor(key, value, options, multiple = false) {
    const wrapper = document.createElement("div");
    wrapper.className = `inline-choice-editor${multiple ? " multiple" : ""}`;
    const input = document.createElement("input");
    input.type = "hidden";
    input.value = value;
    wrapper.appendChild(input);

    const selected = multiple ? new Set(parseMultiValue(value)) : new Set([String(value ?? "")]);
    const sync = () => {
      if (multiple) {
        const activeValues = [...wrapper.querySelectorAll("button.active")].map(button => button.dataset.value);
        input.value = encodeMultiValue(activeValues, options);
      } else {
        input.value = wrapper.querySelector("button.active")?.dataset.value || "";
      }
    };

    for (const option of options) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "review-choice-option";
      button.dataset.value = option.value;
      button.textContent = option.label;
      button.classList.toggle("active", selected.has(String(option.value)));
      button.onclick = () => {
        if (multiple) button.classList.toggle("active");
        else wrapper.querySelectorAll("button").forEach(item => item.classList.toggle("active", item === button));
        sync();
      };
      wrapper.appendChild(button);
    }
    sync();
    return {element: wrapper, input};
  }

  function createInlineEditor(column, observation, value, readonly) {
    const key = column.key;
    const options = fieldInlineOptions(key, observation);
    if (!readonly && key === "chronic_disease") {
      return createChoiceEditor(key, value, options, true);
    }
    if (!readonly && YES_NO_FIELD_KEYS.has(key)) {
      return createChoiceEditor(key, normalizeYesNoValue(value || "NO"), options, false);
    }
    if (!readonly && (observation?.field_type === "integer" || INTEGER_FIELD_KEYS.has(key))) {
      const input = document.createElement("input");
      input.className = "patient-review-inline-input";
      input.type = "number";
      input.step = "1";
      input.min = "0";
      input.inputMode = "numeric";
      const text = String(value ?? "").trim();
      input.value = /^\d+$/.test(text) ? text : "";
      input.placeholder = text && !/^\d+$/.test(text) ? `原值“${text}”无效，请输入数字` : "未填写，直接输入数字";
      return {element: input, input};
    }

    const input = document.createElement("textarea");
    input.className = "patient-review-inline-input";
    input.rows = 1;
    input.value = value;
    input.placeholder = "未填写，直接输入";
    input.readOnly = readonly;
    if (readonly) input.title = derivedField(key) ? "自动整理字段，只读" : "标识字段不在此处修改";
    return {element: input, input};
  }

  // Main sequential field review: multiselect must really be multi-select.
  // yes_no_unknown options come from app.knowledge and always include UNKNOWN for human review.
  const originalRenderReviewChoices = typeof renderReviewChoices === "function" ? renderReviewChoices : null;
  if (originalRenderReviewChoices) {
    renderReviewChoices = observation => {
      if (observation?.field_type !== "multiselect") {
        originalRenderReviewChoices(observation);
        return;
      }
      const container = document.querySelector("#review-choice-options");
      const valueField = document.querySelector("#review-current-value");
      const valueLabel = document.querySelector("#review-current-value-label");
      const options = Array.isArray(observation.field_options) ? observation.field_options : [];
      container.innerHTML = "";
      container.hidden = !options.length;
      valueLabel.hidden = Boolean(options.length);
      const selected = new Set(parseMultiValue(valueField.value));
      for (const option of options) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "review-choice-option";
        button.textContent = option.label;
        button.dataset.value = option.value;
        button.classList.toggle("active", selected.has(String(option.value)));
        button.onclick = () => {
          button.classList.toggle("active");
          const active = [...container.querySelectorAll(".review-choice-option.active")].map(item => item.dataset.value);
          valueField.value = encodeMultiValue(active, options);
        };
        container.appendChild(button);
      }
    };
  }

  // Only TNM fields should display the TNM inference-basis box. Menopause and
  // other inferred fields may carry provenance, but must not show a TNM panel.
  const originalRenderFieldReview = typeof renderFieldReview === "function" ? renderFieldReview : null;
  if (originalRenderFieldReview) {
    renderFieldReview = () => {
      originalRenderFieldReview();
      const observation = typeof selectedObservation === "function" ? selectedObservation() : null;
      if (!observation) return;

      const label = document.querySelector("#review-field-name");
      if (label) label.textContent = displayFieldLabel(observation.field_name, observation.field_label || observation.field_name);

      const basisBox = document.querySelector("#review-inference-basis");
      if (basisBox && !TNM_FIELDS.has(observation.field_name)) {
        basisBox.hidden = true;
        basisBox.innerHTML = "";
      }

      const valueField = document.querySelector("#review-current-value");
      const saveButton = document.querySelector("#save-field-edit");
      const verifyButton = document.querySelector("#verify-field");
      if (!valueField || !saveButton || !verifyButton) return;
      valueField.inputMode = isIntegerObservation(observation) ? "numeric" : "text";
      valueField.placeholder = isIntegerObservation(observation) ? "请输入数字" : "";

      if (isIntegerObservation(observation)) {
        const current = String(valueField.value ?? "").trim();
        if (current && !/^\d+$/.test(current)) {
          valueField.value = "";
          valueField.placeholder = `AI原值“${current}”不是数字，请人工填写`;
        }
        const updateNumericButtons = () => {
          const valid = /^\d+$/.test(valueField.value.trim());
          saveButton.disabled = !valid;
          verifyButton.disabled = !valid;
        };
        valueField.oninput = updateNumericButtons;
        updateNumericButtons();
      }
    };
  }

  function openInlineDialog() {
    if (!reviewDialog.open) reviewDialog.show();
  }

  function closeInlineDialog() {
    if (reviewDialog.open) reviewDialog.close();
  }

  // The original enhancement turns this dialog into a fixed right drawer.
  // Dock the same element below the left review area instead, so it occupies
  // normal document flow and never covers the workspace.
  closeInlineDialog();
  reviewDialog.classList.remove("patient-review-sidepanel");
  reviewDialog.classList.add("patient-review-inline");
  reviewComplete.insertAdjacentElement("afterend", reviewDialog);
  reviewDialog.querySelector(".manual-field-tools")?.remove();

  const table = reviewDialog.querySelector(".patient-review-table");
  const tableHead = table?.querySelector("thead");
  const body = document.querySelector("#patient-review-body");
  if (tableHead) {
    tableHead.innerHTML = "<tr><th>字段</th><th>直接填写 / 修改</th><th>操作</th></tr>";
  }

  async function saveInlineField(column, observation, input, button) {
    if (!state.patient) return;
    const value = String(input.value ?? "").trim();
    const oldValue = observation
      ? String(observation.current_value ?? "").trim()
      : (YES_NO_FIELD_KEYS.has(column.key) ? "NO" : "");
    if (!value) return toast(column.key === "chronic_disease" ? "请至少选择一种慢性病" : "请输入字段内容");
    if ((observation?.field_type === "integer" || INTEGER_FIELD_KEYS.has(column.key)) && !/^\d+$/.test(value)) {
      return toast("该字段只能填写数字");
    }
    if (value === oldValue) return toast(YES_NO_FIELD_KEYS.has(column.key) && !observation ? "病历未提及，当前已按规则默认记为否" : "字段值没有变化");

    button.disabled = true;
    button.textContent = "保存中…";
    try {
      if (observation) {
        await api(`/api/observations/${observation.id}`, {
          method: "PATCH",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            value,
            operator: "local-user",
            reason: "患者事后回顾内嵌面板手动修改",
          }),
        });
      } else {
        await api(`/api/patients/${state.patient.id}/observations`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            field_name: column.key,
            value,
            raw_text: YES_NO_FIELD_KEYS.has(column.key) ? "人工覆盖患者级默认否" : "人工手动补充",
            confidence: "LOW",
            source_mode: "RECORDED",
          }),
        });
      }
      await refreshCurrentPatient(state.patient.id);
      await renderPatientInlineReview(column.key, false);
      toast(observation ? "字段修改已保存" : "字段已手动填写");
    } catch (error) {
      button.disabled = false;
      button.textContent = "保存";
      toast(error.message);
    }
  }

  async function renderPatientInlineReview(focusKey = null, scrollPanel = true) {
    if (!state.patient || !body) return;
    const dataset = await api("/api/data-preview?verified_only=false");
    applyBooleanDefaultsToDataset(dataset);
    const row = dataset.rows.find(item => item.patient_id === state.patient.id);
    if (!row) throw new Error("未找到当前患者数据");

    document.querySelector("#patient-review-title").textContent = `患者 ${state.patient.patient_code} · 事后回顾与修改`;
    const observations = new Map((state.patient.observations || []).map(item => [item.field_name, item]));
    const groups = new Map();
    for (const column of dataset.columns) {
      const key = column.group || "other";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(column);
    }

    body.innerHTML = "";
    for (const [group, columns] of groups) {
      const visibleColumns = columns.filter(column => inlineFieldVisible(column.key, observations, row));
      if (!visibleColumns.length) continue;
      const heading = document.createElement("tr");
      heading.className = "patient-review-group-row";
      heading.innerHTML = `<th colspan="3">${escapeHtml(groupLabel(group))}</th>`;
      body.appendChild(heading);

      for (const column of visibleColumns) {
        const observation = observations.get(column.key);
        const value = observation
          ? String(observation.current_value ?? "")
          : currentPatientValue(column.key, observations, row);
        const defaultNo = !observation && YES_NO_FIELD_KEYS.has(column.key);
        const status = defaultNo ? "DEFAULT_UNMENTIONED" : (row.statuses[column.key] || "EMPTY");
        const readonly = DIRECT_IDENTIFIER_FIELDS.has(column.key) || derivedField(column.key);

        const tr = document.createElement("tr");
        tr.className = "patient-review-inline-row";
        tr.dataset.fieldKey = column.key;

        const fieldCell = document.createElement("th");
        fieldCell.innerHTML = `<strong>${escapeHtml(displayFieldLabel(column.key, column.label))}</strong><small>${escapeHtml(statusText(status))}</small>`;

        const valueCell = document.createElement("td");
        const editor = createInlineEditor(column, observation, value, readonly);
        valueCell.appendChild(editor.element);

        const actionCell = document.createElement("td");
        actionCell.className = "review-row-actions";
        if (!readonly) {
          const saveButton = document.createElement("button");
          saveButton.type = "button";
          saveButton.className = "tool patient-review-save";
          saveButton.textContent = observation ? "保存" : (defaultNo ? "保存修改" : "填写");
          saveButton.onclick = () => saveInlineField(column, observation, editor.input, saveButton);
          actionCell.appendChild(saveButton);
        } else {
          const note = document.createElement("small");
          note.className = "derived-readonly-note";
          note.textContent = derivedField(column.key) ? "自动整理 · 只读" : "只读";
          actionCell.appendChild(note);
        }
        if (observation?.document_id) {
          const imageButton = document.createElement("button");
          imageButton.type = "button";
          imageButton.className = "tool patient-review-source";
          imageButton.textContent = "来源图";
          imageButton.onclick = () => openSavedDocumentPreview(observation.document_id, observation.id).catch(error => toast(error.message));
          actionCell.appendChild(imageButton);
        }

        tr.append(fieldCell, valueCell, actionCell);
        body.appendChild(tr);
      }
    }

    openInlineDialog();
    if (scrollPanel) reviewDialog.scrollIntoView({behavior: "smooth", block: "nearest"});
    if (focusKey) {
      requestAnimationFrame(() => {
        const target = [...body.querySelectorAll("tr[data-field-key]")].find(item => item.dataset.fieldKey === focusKey);
        target?.scrollIntoView({behavior: "smooth", block: "center"});
        target?.querySelector("textarea:not([readonly]),input:not([readonly]):not([type=hidden])")?.focus({preventScroll: true});
      });
    }
  }

  function applyBooleanDefaultsToDataset(dataset) {
    if (!dataset?.rows) return dataset;
    for (const row of dataset.rows) {
      row.values ||= {};
      row.statuses ||= {};
      for (const key of YES_NO_FIELD_KEYS) {
        const current = row.values[key];
        const status = row.statuses[key] || "EMPTY";
        if ((current == null || current === "") && status !== "UNAVAILABLE") {
          row.values[key] = "否";
          row.statuses[key] = "DEFAULT_UNMENTIONED";
        }
      }
    }
    return dataset;
  }

  const originalLoadDataPreview = typeof loadDataPreview === "function" ? loadDataPreview : null;
  if (originalLoadDataPreview) {
    loadDataPreview = async () => {
      const verifiedOnly = document.querySelector("#data-preview-scope").value === "verified";
      const loading = document.querySelector("#data-preview-loading");
      loading.hidden = false;
      document.querySelector("#data-preview-table").hidden = true;
      try {
        state.dataPreview = applyBooleanDefaultsToDataset(await api(`/api/data-preview?verified_only=${verifiedOnly}`));
        renderDataPreview();
      } finally {
        loading.hidden = true;
        document.querySelector("#data-preview-table").hidden = false;
      }
    };
  }

  function csvCell(value) {
    const text = String(value ?? "");
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  const exportButton = document.querySelector("#export-data-csv");
  if (exportButton) {
    exportButton.onclick = async () => {
      const verifiedOnly = document.querySelector("#data-preview-scope").value === "verified";
      if (!state.dataPreview || Boolean(state.dataPreview.verified_only) !== verifiedOnly) await loadDataPreview();
      const dataset = applyBooleanDefaultsToDataset(state.dataPreview);
      const lines = [dataset.columns.map(column => csvCell(column.label)).join(",")];
      for (const row of dataset.rows) {
        const values = dataset.columns.map(column => {
          let value = row.values[column.key] ?? "";
          if (column.key === "record_number" && /^\d{7}$/.test(String(value))) value = `="${value}"`;
          return csvCell(value);
        });
        lines.push(values.join(","));
      }
      const blob = new Blob(["\ufeff", lines.join("\r\n")], {type: "text/csv;charset=utf-8"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = verifiedOnly ? "乳腺癌患者数据_仅人工确认.csv" : "乳腺癌患者数据_全部当前结果.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    };
  }

  showPatientReview = renderPatientInlineReview;
  const reviewButton = document.querySelector("#review-patient-summary");
  if (reviewButton) {
    reviewButton.onclick = () => renderPatientInlineReview().catch(error => toast(error.message));
  }
  const closeButton = document.querySelector("#close-patient-review");
  if (closeButton) {
    closeButton.onclick = () => closeInlineDialog();
  }
})();