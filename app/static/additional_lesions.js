(() => {
  const PREFIX = "additional_malignant_lesion:";
  const SCHEMA = "BCE_ADDITIONAL_MALIGNANT_LESION_V1";
  const MULTIPLICITY_FIELD = "pre_mmg_single_lesion";

  function parseRecord(observation) {
    if (!observation?.field_name?.startsWith(PREFIX)) return null;
    try {
      const value = JSON.parse(String(observation.current_value || ""));
      return value?.schema === SCHEMA ? {observation, value} : null;
    } catch (_) {
      return null;
    }
  }

  function records() {
    return (state?.patient?.observations || [])
      .map(parseRecord)
      .filter(Boolean)
      .sort((left, right) => Number(left.value.lesion_number || 0) - Number(right.value.lesion_number || 0));
  }

  function patientValue(fieldName) {
    return String((state?.patient?.observations || []).find(item => item.field_name === fieldName)?.current_value || "").toUpperCase();
  }

  function eligibility() {
    const laterality = patientValue("breast_laterality");
    const multiplicity = patientValue(MULTIPLICITY_FIELD);
    const triggers = [];
    if (laterality === "BILATERAL") triggers.push("BILATERAL");
    if (multiplicity === "MULTIPLE") triggers.push("MULTIPLE");
    return {eligible: triggers.length > 0, laterality, multiplicity, triggers};
  }

  function field(label, value = "", options = null, wide = false) {
    const wrapper = document.createElement("label");
    wrapper.className = wide ? "additional-lesion-field wide" : "additional-lesion-field";
    const caption = document.createElement("span");
    caption.textContent = label;
    wrapper.appendChild(caption);
    let input;
    if (options) {
      input = document.createElement("select");
      for (const option of options) {
        const element = document.createElement("option");
        element.value = option.value;
        element.textContent = option.label;
        element.selected = String(value || "") === option.value;
        input.appendChild(element);
      }
    } else {
      input = document.createElement("input");
      input.value = value || "";
    }
    wrapper.appendChild(input);
    return {wrapper, input};
  }

  function textarea(label, value = "", wide = true) {
    const item = field(label, value, null, wide);
    const input = document.createElement("textarea");
    input.rows = 2;
    input.value = value || "";
    item.wrapper.replaceChild(input, item.input);
    item.input = input;
    return item;
  }

  function sourceField(documentId = "") {
    const options = [{label: "未指定来源图片", value: ""}].concat(
      (state?.patient?.documents || []).map(document => ({label: document.display_name, value: document.id})),
    );
    return field("来源图片", documentId, options, true);
  }

  function buildEditors(value = {}, observation = null) {
    const grid = document.createElement("div");
    grid.className = "additional-lesion-grid";
    const items = {
      lesion_label: field("病灶名称（可选）", value.lesion_label || ""),
      laterality: field("侧别", value.laterality || "LEFT", [
        {label: "左侧", value: "LEFT"}, {label: "右侧", value: "RIGHT"},
      ]),
      location: field("位置 / 方位", value.location || ""),
      size_text: field("肿块大小", value.size_text || ""),
      ultrasound_detail: textarea("超声结果", value.ultrasound_detail || ""),
      mammography_detail: textarea("钼靶结果", value.mammography_detail || ""),
      mri_detail: textarea("MRI结果", value.mri_detail || ""),
      pathology_type: field("病理类型", value.pathology_type || ""),
      pathology_grade: field("病理分级", value.pathology_grade || ""),
      er: field("ER", value.er || ""),
      pr: field("PR", value.pr || ""),
      her2: field("HER2", value.her2 || ""),
      ki67: field("Ki-67", value.ki67 || ""),
      other_ihc: textarea("其他免疫组化", value.other_ihc || ""),
      document_id: sourceField(observation?.document_id || ""),
      malignancy_basis: textarea("明确恶性依据（必填）", value.malignancy_basis || observation?.raw_text || ""),
    };
    items.size_text.input.placeholder = "例如：23×18 mm；只有两个径线时不要补NA";
    items.malignancy_basis.input.placeholder = "例如：右乳穿刺病理提示浸润性导管癌";
    for (const item of Object.values(items)) grid.appendChild(item.wrapper);
    return {grid, inputs: Object.fromEntries(Object.entries(items).map(([key, item]) => [key, item.input]))};
  }

  function payloadFrom(inputs, active = true, regionId = null) {
    const value = key => String(inputs[key]?.value || "").trim();
    return {
      active,
      lesion_label: value("lesion_label"),
      laterality: value("laterality"),
      location: value("location"),
      size_text: value("size_text"),
      ultrasound_detail: value("ultrasound_detail"),
      mammography_detail: value("mammography_detail"),
      mri_detail: value("mri_detail"),
      pathology_type: value("pathology_type"),
      pathology_grade: value("pathology_grade"),
      er: value("er"),
      pr: value("pr"),
      her2: value("her2"),
      ki67: value("ki67"),
      other_ihc: value("other_ihc"),
      malignancy_basis: value("malignancy_basis"),
      document_id: value("document_id") || null,
      region_id: regionId || null,
      operator: "local-user",
    };
  }

  async function refreshPanel(message = "") {
    await refreshCurrentPatient(state.patient.id);
    renderPanel();
    if (message) toast(message);
  }

  function createForm(panel) {
    const card = document.createElement("section");
    card.className = "additional-lesion-card create";
    const heading = document.createElement("h4");
    heading.textContent = "新增附加恶性病灶";
    card.appendChild(heading);
    const editor = buildEditors();
    card.appendChild(editor.grid);
    const actions = document.createElement("div");
    actions.className = "additional-lesion-actions";
    const save = document.createElement("button");
    save.type = "button";
    save.className = "primary";
    save.textContent = "保存病灶";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "tool";
    cancel.textContent = "取消";
    cancel.onclick = () => card.remove();
    save.onclick = async () => {
      save.disabled = true;
      try {
        await api(`/api/patients/${state.patient.id}/additional-lesions`, {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payloadFrom(editor.inputs)),
        });
        await refreshPanel("附加病灶已保存");
      } catch (error) {
        save.disabled = false;
        toast(error.message);
      }
    };
    actions.append(save, cancel);
    card.appendChild(actions);
    panel.appendChild(card);
    card.scrollIntoView({behavior: "smooth", block: "nearest"});
  }

  function recordCard(record, currentEligibility) {
    const card = document.createElement("section");
    card.className = `additional-lesion-card${record.value.active === false ? " inactive" : ""}`;
    const heading = document.createElement("div");
    heading.className = "additional-lesion-card-heading";
    const title = document.createElement("h4");
    const side = record.value.laterality === "RIGHT" ? "右侧" : "左侧";
    title.textContent = `${record.value.lesion_label || `病灶 ${record.value.lesion_number || ""}`} · ${side}${record.value.active === false ? "（已停用）" : ""}`;
    heading.appendChild(title);
    card.appendChild(heading);

    const editor = buildEditors(record.value, record.observation);
    card.appendChild(editor.grid);
    const editable = record.value.active !== false && currentEligibility.eligible;
    if (!editable) Object.values(editor.inputs).forEach(input => { input.disabled = true; });

    const actions = document.createElement("div");
    actions.className = "additional-lesion-actions";
    if (editable) {
      const save = document.createElement("button");
      save.type = "button";
      save.className = "tool";
      save.textContent = "保存修改";
      save.onclick = async () => {
        save.disabled = true;
        try {
          await api(`/api/additional-lesions/${record.observation.id}`, {
            method: "PATCH", headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payloadFrom(editor.inputs, true, record.observation.region_id)),
          });
          await refreshPanel("病灶修改已保存");
        } catch (error) {
          save.disabled = false;
          toast(error.message);
        }
      };
      actions.appendChild(save);
    }
    if (record.observation.document_id && typeof openSavedDocumentPreview === "function") {
      const source = document.createElement("button");
      source.type = "button";
      source.className = "tool";
      source.textContent = "来源图";
      source.onclick = () => openSavedDocumentPreview(record.observation.document_id, record.observation.id).catch(error => toast(error.message));
      actions.appendChild(source);
    }
    if (record.value.active !== false) {
      const deactivate = document.createElement("button");
      deactivate.type = "button";
      deactivate.className = "tool";
      deactivate.textContent = "停用病灶";
      deactivate.onclick = async () => {
        if (!confirm("停用这个附加病灶？记录和审计历史仍会保留。")) return;
        deactivate.disabled = true;
        try {
          await api(`/api/additional-lesions/${record.observation.id}`, {
            method: "PATCH", headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payloadFrom(editor.inputs, false, record.observation.region_id)),
          });
          await refreshPanel("病灶已停用");
        } catch (error) {
          deactivate.disabled = false;
          toast(error.message);
        }
      };
      actions.appendChild(deactivate);
    }
    card.appendChild(actions);
    return card;
  }

  function ensurePanel() {
    const shell = document.querySelector("#patient-review-dialog .patient-review-table-shell");
    if (!shell) return null;
    let panel = shell.querySelector("#additional-lesions-panel");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "additional-lesions-panel";
      panel.className = "additional-lesions-panel";
      shell.appendChild(panel);
    }
    return panel;
  }

  function renderPanel() {
    const panel = ensurePanel();
    if (!panel || !state?.patient) return;
    const currentEligibility = eligibility();
    const lesionRecords = records();
    panel.innerHTML = "";

    const header = document.createElement("div");
    header.className = "additional-lesions-header";
    const text = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = "多个 / 双侧恶性病灶";
    const note = document.createElement("small");
    note.textContent = "当前核心问卷代表主病灶；这里只增加其他明确恶性病灶的大小、影像、病理和免疫组化。";
    text.append(title, note);
    const add = document.createElement("button");
    add.type = "button";
    add.className = "primary";
    add.textContent = "增加病灶";
    add.disabled = !currentEligibility.eligible;
    add.title = currentEligibility.eligible ? "增加另一明确恶性病灶" : "请先确认乳腺癌为双侧，或确认影像学恶性病灶为多发";
    add.onclick = () => {
      if (!panel.querySelector(".additional-lesion-card.create")) createForm(panel);
    };
    header.append(text, add);
    panel.appendChild(header);

    if (!currentEligibility.eligible) {
      const warning = document.createElement("p");
      warning.className = "additional-lesions-warning";
      warning.textContent = lesionRecords.length
        ? "当前双侧/多发条件已取消。既有病灶仍可查看或停用，但不能新增或继续修改。"
        : "要增加病灶，请先把“乳腺癌偏侧性”设为“双侧”，或把“影像学恶性病灶是否多发”设为“多发”。";
      panel.appendChild(warning);
    }
    lesionRecords.forEach(record => panel.appendChild(recordCard(record, currentEligibility)));
  }

  function scheduleRender() {
    clearTimeout(scheduleRender.timer);
    scheduleRender.timer = setTimeout(renderPanel, 0);
  }

  const body = document.querySelector("#patient-review-body");
  if (body) new MutationObserver(scheduleRender).observe(body, {childList: true, subtree: true});
  scheduleRender();
})();
