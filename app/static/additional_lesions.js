(() => {
  const FIELD_PREFIX = "additional_malignant_lesion:";
  const PAYLOAD_SCHEMA = "BCE_ADDITIONAL_MALIGNANT_LESION_V1";
  const MULTIPLICITY_FIELD = "pre_mmg_single_lesion"; // stable historical key; UI meaning is imaging-wide in app.knowledge
  const POSITIVE_MALIGNANCY = /(乳腺癌|癌灶|癌组织|癌细胞|浸润性[^，。;；\n]{0,20}癌|原位癌|恶性病灶|恶性肿瘤|明确恶性|\bcarcinoma\b|\bmalignan(?:t|cy)\b|BI\s*-?\s*RADS\s*6)/i;
  const NEGATIVE_MALIGNANCY = /(未见[^，。;；\n]{0,10}(?:恶性|癌)|无[^，。;；\n]{0,10}(?:恶性|癌)|排除[^，。;；\n]{0,10}(?:恶性|癌)|倾向良性|考虑良性|明确良性)/i;

  function escapeLocal(value) {
    if (typeof escapeHtml === "function") return escapeHtml(String(value ?? ""));
    return String(value ?? "").replace(/[&<>"']/g, character => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
  }

  function activeObservation(fieldName) {
    return (state?.patient?.observations || []).find(item => item.field_name === fieldName && item.status !== "SUPERSEDED");
  }

  function patientEligibility() {
    const laterality = String(activeObservation("breast_laterality")?.current_value || "").toUpperCase();
    const multiplicity = String(activeObservation(MULTIPLICITY_FIELD)?.current_value || "").toUpperCase();
    const triggers = [];
    if (laterality === "BILATERAL") triggers.push("BILATERAL");
    if (multiplicity === "MULTIPLE") triggers.push("MULTIPLE");
    return {
      eligible: triggers.length > 0,
      laterality,
      multiplicity,
      triggers,
    };
  }

  function parseLesionObservation(observation) {
    if (!observation?.field_name?.startsWith(FIELD_PREFIX)) return null;
    try {
      const value = JSON.parse(String(observation.current_value || ""));
      if (value?.schema !== PAYLOAD_SCHEMA) return null;
      return {observation, value};
    } catch (_) {
      return null;
    }
  }

  function lesionRecords() {
    return (state?.patient?.observations || [])
      .map(parseLesionObservation)
      .filter(Boolean)
      .sort((a, b) => Number(a.value.lesion_number || 0) - Number(b.value.lesion_number || 0));
  }

  function nextLesionNumber(records) {
    return Math.max(1, ...records.map(item => Number(item.value.lesion_number || 1))) + 1;
  }

  function malignantBasisIsValid(text) {
    const value = String(text || "").trim();
    return Boolean(value && POSITIVE_MALIGNANCY.test(value) && !NEGATIVE_MALIGNANCY.test(value));
  }

  function triggerLabel(triggers) {
    const labels = [];
    if (triggers.includes("BILATERAL")) labels.push("偏侧性：双侧");
    if (triggers.includes("MULTIPLE")) labels.push("影像学恶性病灶：多发");
    return labels.join("；");
  }

  function installStyle() {
    if (document.querySelector("#additional-lesions-style")) return;
    const style = document.createElement("style");
    style.id = "additional-lesions-style";
    style.textContent = `
      .additional-lesions-panel{margin:10px;padding:10px;border:1px solid var(--line,#d9dee7);border-radius:10px;background:var(--paper,#f6f4ef);font-size:11px}
      .additional-lesions-panel[hidden]{display:none!important}
      .additional-lesions-title{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:4px}
      .additional-lesions-title strong{font-size:12px;color:var(--green-dark,#174737)}
      .additional-lesions-note{margin:3px 0 8px;color:var(--muted,#66736d);line-height:1.45}
      .additional-lesions-warning{margin:6px 0;padding:7px;border:1px solid var(--line,#d9dee7);border-radius:7px;background:var(--panel,#fff);line-height:1.45}
      .additional-lesion-card{padding:8px;margin:7px 0;border:1px solid var(--line,#d9dee7);border-radius:8px;background:var(--panel,#fff)}
      .additional-lesion-card.inactive{opacity:.62}
      .additional-lesion-card h4{margin:0 0 6px;font-size:11px}
      .additional-lesion-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
      .additional-lesion-grid label{display:block;color:var(--muted,#66736d);font-size:10px}
      .additional-lesion-grid input,.additional-lesion-grid select,.additional-lesion-grid textarea{box-sizing:border-box;width:100%;margin-top:2px;padding:5px 6px;border:1px solid var(--line,#d9dee7);border-radius:6px;background:var(--control,#fff);color:var(--ink);font:inherit}
      .additional-lesion-grid textarea{resize:vertical;min-height:50px}
      .additional-lesion-wide{grid-column:1/-1}
      .additional-lesion-actions{display:flex;gap:6px;margin-top:7px}
      .additional-lesion-actions .tool{flex:1;padding:5px 6px;font-size:10px}
      .additional-lesion-basis{margin-top:6px;padding:6px;border-radius:6px;background:var(--mint,#eef5f1);white-space:pre-wrap;overflow-wrap:anywhere}
      .imaging-multiplicity-choices{display:flex;gap:6px}
      .imaging-multiplicity-choices button{flex:1;padding:6px;border:1px solid var(--line,#d9dee7);border-radius:7px;background:var(--control,#fff);font:inherit;cursor:pointer}
      .imaging-multiplicity-choices button.active{font-weight:700;outline:2px solid var(--green-dark,#174737);outline-offset:-2px}
      @media(max-width:700px){.additional-lesion-grid{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function fixImagingGroupLabel() {
    document.querySelectorAll(".patient-review-group-row th").forEach(cell => {
      if (cell.textContent.trim() === "pretreatment_imaging") cell.textContent = "影像学总体";
    });
  }

  function enhanceMultiplicityEditor() {
    const row = document.querySelector(`tr[data-field-key="${MULTIPLICITY_FIELD}"]`);
    if (!row || row.dataset.multiplicityEnhanced === "1") return;
    const valueCell = row.querySelector("td");
    const textarea = valueCell?.querySelector("textarea, input:not([type=hidden])");
    if (!valueCell || !textarea) return;
    row.dataset.multiplicityEnhanced = "1";
    textarea.style.display = "none";
    const choices = document.createElement("div");
    choices.className = "imaging-multiplicity-choices";
    const sync = value => {
      textarea.value = value;
      choices.querySelectorAll("button").forEach(button => button.classList.toggle("active", button.dataset.value === value));
    };
    for (const option of [{label: "单发", value: "SINGLE"}, {label: "多发", value: "MULTIPLE"}]) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.value = option.value;
      button.textContent = option.label;
      button.classList.toggle("active", String(textarea.value).toUpperCase() === option.value);
      button.onclick = () => sync(option.value);
      choices.appendChild(button);
    }
    valueCell.appendChild(choices);
  }

  function inputField(label, value = "", options = null, wide = false) {
    const wrapper = document.createElement("label");
    if (wide) wrapper.classList.add("additional-lesion-wide");
    wrapper.append(document.createTextNode(label));
    let input;
    if (options) {
      input = document.createElement("select");
      for (const [text, code] of options) {
        const option = document.createElement("option");
        option.value = code;
        option.textContent = text;
        option.selected = String(value || "") === code;
        input.appendChild(option);
      }
    } else {
      input = document.createElement("input");
      input.value = value || "";
    }
    wrapper.appendChild(input);
    return {wrapper, input};
  }

  function textAreaField(label, value = "", wide = true) {
    const wrapper = document.createElement("label");
    if (wide) wrapper.classList.add("additional-lesion-wide");
    wrapper.append(document.createTextNode(label));
    const input = document.createElement("textarea");
    input.value = value || "";
    wrapper.appendChild(input);
    return {wrapper, input};
  }

  function currentTriggers(original, eligibility) {
    return eligibility.triggers.length ? [...eligibility.triggers] : [...(original?.trigger_basis || [])];
  }

  function lesionValueFromEditors(original, editors, eligibility) {
    return {
      ...original,
      schema: PAYLOAD_SCHEMA,
      active: original?.active !== false,
      malignancy_confirmed: true,
      trigger_basis: currentTriggers(original, eligibility),
      laterality: editors.laterality.value,
      location: editors.location.value.trim(),
      size_text: editors.size_text.value.trim(),
      imaging_detail: editors.imaging_detail.value.trim(),
      pathology_type: editors.pathology_type.value.trim(),
      er: editors.er.value.trim(),
      pr: editors.pr.value.trim(),
      her2: editors.her2.value.trim(),
      ki67: editors.ki67.value.trim(),
      other_ihc: editors.other_ihc.value.trim(),
    };
  }

  function buildEditors(container, value, eligibility, creating = false) {
    const defaultSide = eligibility.laterality === "LEFT" || eligibility.laterality === "RIGHT"
      ? eligibility.laterality : (value?.laterality || "LEFT");
    const fields = {
      laterality: inputField("侧别", value?.laterality || defaultSide, [["左侧", "LEFT"], ["右侧", "RIGHT"]]),
      location: inputField("位置 / 方位", value?.location),
      size_text: inputField("大小（可记录多个原始径线）", value?.size_text),
      imaging_detail: textAreaField("各影像检查补充（可记录超声/MRI/钼靶各自的大小、方位）", value?.imaging_detail),
      pathology_type: inputField("病理类型", value?.pathology_type),
      er: inputField("ER", value?.er),
      pr: inputField("PR", value?.pr),
      her2: inputField("HER2", value?.her2),
      ki67: inputField("Ki-67", value?.ki67),
      other_ihc: inputField("其他IHC", value?.other_ihc, null, true),
    };
    Object.values(fields).forEach(item => container.appendChild(item.wrapper));
    if (!creating && eligibility.laterality !== "BILATERAL" && fields.laterality.input.value === eligibility.laterality) {
      fields.laterality.input.disabled = true;
    }
    return Object.fromEntries(Object.entries(fields).map(([key, item]) => [key, item.input]));
  }

  async function refreshAndRender() {
    if (!state?.patient?.id) return;
    await refreshCurrentPatient(state.patient.id);
    renderAdditionalLesionsPanel();
  }

  async function createLesion(form, eligibility, records) {
    const basis = form.basis.value.trim();
    if (!eligibility.eligible) {
      toast("当前患者不满足双侧或影像学恶性病灶多发条件，不能新增附加病灶");
      return;
    }
    if (!malignantBasisIsValid(basis)) {
      toast("附加病灶必须有明确恶性依据；多发良性结节、囊肿或纤维腺瘤不能添加");
      return;
    }
    const lesionNumber = nextLesionNumber(records);
    const value = lesionValueFromEditors({
      schema: PAYLOAD_SCHEMA,
      active: true,
      lesion_number: lesionNumber,
      malignancy_confirmed: true,
      malignancy_basis: basis,
      trigger_basis: [...eligibility.triggers],
      source_document_id: form.source.value || null,
      created_by: "local-user",
    }, form.editors, eligibility);
    const fieldName = `${FIELD_PREFIX}${crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`}`;
    form.button.disabled = true;
    try {
      const created = await api(`/api/patients/${state.patient.id}/observations`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          field_name: fieldName,
          value: JSON.stringify(value),
          raw_text: basis,
          confidence: "LOW",
          source_mode: "RECORDED",
          document_id: form.source.value || null,
        }),
      });
      await api(`/api/observations/${created.id}/verify`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({operator: "local-user", note: "人工确认明确恶性并建立附加病灶"}),
      });
      toast(`已建立附加恶性病灶 ${lesionNumber}`);
      await refreshAndRender();
    } catch (error) {
      toast(error.message);
      form.button.disabled = false;
    }
  }

  async function saveExisting(record, editors, eligibility, button) {
    if (!eligibility.eligible) return toast("当前双侧/多发条件已取消；旧记录仅可查看或停用，不能修改为新的活动病灶信息");
    const next = lesionValueFromEditors(record.value, editors, eligibility);
    button.disabled = true;
    try {
      await api(`/api/observations/${record.observation.id}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          value: JSON.stringify(next),
          operator: "local-user",
          reason: "人工修改附加恶性病灶",
        }),
      });
      toast("附加病灶已更新");
      await refreshAndRender();
    } catch (error) {
      toast(error.message);
      button.disabled = false;
    }
  }

  async function deactivateExisting(record, eligibility, button) {
    if (!confirm(`停用附加病灶 ${record.value.lesion_number || ""}？记录仍会保留在审计历史中。`)) return;
    const next = {...record.value, active: false, trigger_basis: currentTriggers(record.value, eligibility)};
    button.disabled = true;
    try {
      await api(`/api/observations/${record.observation.id}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          value: JSON.stringify(next),
          operator: "local-user",
          reason: "人工停用附加恶性病灶",
        }),
      });
      toast("附加病灶已停用");
      await refreshAndRender();
    } catch (error) {
      toast(error.message);
      button.disabled = false;
    }
  }

  function buildExistingCard(record, eligibility) {
    const card = document.createElement("section");
    card.className = `additional-lesion-card${record.value.active === false ? " inactive" : ""}`;
    const title = document.createElement("h4");
    title.textContent = `附加病灶 ${record.value.lesion_number || ""} · ${record.value.laterality === "RIGHT" ? "右侧" : "左侧"}${record.value.active === false ? "（已停用）" : ""}`;
    card.appendChild(title);
    if (record.value.active === false) {
      const basis = document.createElement("div");
      basis.className = "additional-lesion-basis";
      basis.textContent = `原恶性依据：${record.value.malignancy_basis || record.observation.raw_text || ""}`;
      card.appendChild(basis);
      return card;
    }

    const grid = document.createElement("div");
    grid.className = "additional-lesion-grid";
    const editors = buildEditors(grid, record.value, eligibility, false);
    if (!eligibility.eligible) Object.values(editors).forEach(input => { input.disabled = true; });
    card.appendChild(grid);
    const basis = document.createElement("div");
    basis.className = "additional-lesion-basis";
    basis.textContent = `明确恶性依据（建立后只读）：${record.value.malignancy_basis || record.observation.raw_text || ""}`;
    card.appendChild(basis);

    const actions = document.createElement("div");
    actions.className = "additional-lesion-actions";
    if (eligibility.eligible) {
      const save = document.createElement("button");
      save.type = "button";
      save.className = "tool";
      save.textContent = "保存修改";
      save.onclick = () => saveExisting(record, editors, eligibility, save);
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
    const deactivate = document.createElement("button");
    deactivate.type = "button";
    deactivate.className = "tool";
    deactivate.textContent = "停用";
    deactivate.onclick = () => deactivateExisting(record, eligibility, deactivate);
    actions.appendChild(deactivate);
    card.appendChild(actions);
    return card;
  }

  function buildCreateForm(eligibility, records) {
    const active = records.filter(item => item.value.active !== false);
    const wrapper = document.createElement("section");
    wrapper.className = "additional-lesion-card";
    if (eligibility.triggers.length === 1 && eligibility.triggers[0] === "BILATERAL" && active.length >= 1) {
      wrapper.innerHTML = "<strong>双侧单发病例已记录一个附加病灶。</strong><div class=\"additional-lesions-note\">如确实还存在多个明确恶性病灶，请先将“影像学恶性病灶是否多发”确认成“多发”。</div>";
      return wrapper;
    }

    const title = document.createElement("h4");
    title.textContent = `添加附加恶性病灶 ${nextLesionNumber(records)}`;
    wrapper.appendChild(title);
    const grid = document.createElement("div");
    grid.className = "additional-lesion-grid";
    const editors = buildEditors(grid, {}, eligibility, true);

    const source = inputField("来源文档（可选）", "", [["未指定", ""], ...(state.patient.documents || []).map(doc => [doc.display_name, doc.id])], true);
    grid.appendChild(source.wrapper);
    const basis = textAreaField("明确恶性依据（必填，必须针对这个附加病灶）");
    basis.input.placeholder = "例如：右乳病理：浸润性导管癌；或报告明确写“右乳恶性病灶/癌灶”……";
    grid.appendChild(basis.wrapper);
    wrapper.appendChild(grid);

    const warning = document.createElement("div");
    warning.className = "additional-lesions-note";
    warning.textContent = "不要因为超声/MRI/钼靶存在多个良性肿块、囊肿、纤维腺瘤或普通结节而添加附加病灶。";
    wrapper.appendChild(warning);
    const actions = document.createElement("div");
    actions.className = "additional-lesion-actions";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tool";
    button.textContent = "确认明确恶性并添加";
    actions.appendChild(button);
    wrapper.appendChild(actions);
    button.onclick = () => createLesion({editors, source: source.input, basis: basis.input, button}, eligibility, records);
    return wrapper;
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

  function renderAdditionalLesionsPanel() {
    installStyle();
    fixImagingGroupLabel();
    enhanceMultiplicityEditor();
    const panel = ensurePanel();
    if (!panel || !state?.patient) return;
    const eligibility = patientEligibility();
    const records = lesionRecords();
    panel.hidden = !eligibility.eligible && records.length === 0;
    panel.innerHTML = "";
    if (panel.hidden) return;

    const title = document.createElement("div");
    title.className = "additional-lesions-title";
    title.innerHTML = `<strong>附加恶性病灶</strong><span>${escapeLocal(eligibility.eligible ? triggerLabel(eligibility.triggers) : "当前未满足新增条件")}</span>`;
    panel.appendChild(title);
    const note = document.createElement("div");
    note.className = "additional-lesions-note";
    note.textContent = "这是低频例外层：患者信息、手术和治疗仍只记录一套。只有明确恶性的第二/更多病灶才在这里记录大小、方位、病理和IHC；触发条件本身不会自动创建病灶。";
    panel.appendChild(note);

    if (!eligibility.eligible && records.length) {
      const warning = document.createElement("div");
      warning.className = "additional-lesions-warning";
      warning.textContent = "当前偏侧性已不是“双侧”，且影像学恶性病灶也不是“多发”。既往附加病灶记录仍保留并可查看/停用，但不能继续新增；如判定有误，请先纠正双侧或影像多发字段。";
      panel.appendChild(warning);
    }

    records.forEach(record => panel.appendChild(buildExistingCard(record, eligibility)));
    if (eligibility.eligible) panel.appendChild(buildCreateForm(eligibility, records));
  }

  function scheduleRender() {
    clearTimeout(scheduleRender.timer);
    scheduleRender.timer = setTimeout(renderAdditionalLesionsPanel, 0);
  }

  installStyle();
  const reviewBody = document.querySelector("#patient-review-body");
  if (reviewBody) new MutationObserver(scheduleRender).observe(reviewBody, {childList: true, subtree: true});

  const reviewButton = document.querySelector("#review-patient-summary");
  if (reviewButton) {
    const prior = reviewButton.onclick;
    reviewButton.onclick = async event => {
      if (prior) await prior.call(reviewButton, event);
      scheduleRender();
    };
  }

  // If the inline review is already visible when this script loads, enhance it immediately.
  scheduleRender();
})();
