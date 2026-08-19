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

  function derivedField(key) {
    return [
      "clinical_t_component", "clinical_n_component", "clinical_m_component",
      "pathological_t_component", "pathological_n_component", "pathological_m_component",
    ].includes(String(key || "")) || /_dim[123]_mm$/.test(String(key || ""));
  }

  function groupLabel(group) {
    return GROUP_LABELS[group] || group || "其他";
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
    const value = input.value.trim();
    const oldValue = String(observation?.current_value ?? "").trim();
    if (!value) return toast("请输入字段内容");
    if (observation && value === oldValue) return toast("字段值没有变化");

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
            raw_text: "人工手动补充",
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
      const heading = document.createElement("tr");
      heading.className = "patient-review-group-row";
      heading.innerHTML = `<th colspan="3">${escapeHtml(groupLabel(group))}</th>`;
      body.appendChild(heading);

      for (const column of columns) {
        const observation = observations.get(column.key);
        const preview = row.values[column.key] ?? "";
        const value = observation ? String(observation.current_value ?? "") : String(preview ?? "");
        const status = row.statuses[column.key] || "EMPTY";
        const readonly = DIRECT_IDENTIFIER_FIELDS.has(column.key) || derivedField(column.key);

        const tr = document.createElement("tr");
        tr.className = "patient-review-inline-row";
        tr.dataset.fieldKey = column.key;

        const fieldCell = document.createElement("th");
        fieldCell.innerHTML = `<strong>${escapeHtml(column.label)}</strong><small>${escapeHtml(statusText(status))}</small>`;

        const valueCell = document.createElement("td");
        const input = document.createElement("textarea");
        input.className = "patient-review-inline-input";
        input.rows = 1;
        input.value = value;
        input.placeholder = "未填写，直接输入";
        input.readOnly = readonly;
        if (readonly) input.title = derivedField(column.key) ? "自动整理字段，只读" : "标识字段不在此处修改";
        valueCell.appendChild(input);

        const actionCell = document.createElement("td");
        actionCell.className = "review-row-actions";
        if (!readonly) {
          const saveButton = document.createElement("button");
          saveButton.type = "button";
          saveButton.className = "tool patient-review-save";
          saveButton.textContent = observation ? "保存" : "填写";
          saveButton.onclick = () => saveInlineField(column, observation, input, saveButton);
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
        target?.querySelector("textarea:not([readonly])")?.focus({preventScroll: true});
      });
    }
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
