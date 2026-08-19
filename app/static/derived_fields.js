(() => {
  function isDerivedKey(key) {
    const value = String(key || "").trim();
    return [
      "clinical_t_component", "clinical_n_component", "clinical_m_component",
      "pathological_t_component", "pathological_n_component", "pathological_m_component",
    ].includes(value) || /_dim[123]_mm$/.test(value);
  }

  function lockCurrentFieldReview() {
    const key = $("#review-field-key")?.textContent?.trim() || "";
    const derived = isDerivedKey(key);
    const textarea = $("#review-current-value");
    const save = $("#save-field-edit");
    const verify = $("#verify-field");
    const note = $("#review-note");
    const label = $("#review-current-value-label");

    for (const element of [textarea, save, verify, note]) {
      if (!element) continue;
      if (derived) {
        if (!element.disabled && element !== textarea) element.dataset.derivedDisabled = "1";
        if (element === textarea) {
          element.dataset.derivedReadonly = element.readOnly ? "0" : "1";
          element.readOnly = true;
        } else {
          element.disabled = true;
        }
      } else if (element === textarea) {
        if (element.dataset.derivedReadonly === "1") element.readOnly = false;
        delete element.dataset.derivedReadonly;
      } else if (element.dataset.derivedDisabled === "1") {
        element.disabled = false;
        delete element.dataset.derivedDisabled;
      }
    }

    if (label) {
      if (!label.dataset.defaultText) label.dataset.defaultText = "当前值";
      const textNode = [...label.childNodes].find(node => node.nodeType === Node.TEXT_NODE);
      if (textNode) textNode.textContent = derived ? "自动整理值（只读）" : label.dataset.defaultText;
    }
    const meta = $("#review-field-meta");
    if (derived && meta && !meta.textContent.includes("自动整理字段")) {
      meta.textContent = `${meta.textContent ? `${meta.textContent} · ` : ""}自动整理字段：请修改并重新确认完整主字段，不能单独修改本字段。`;
    }
  }

  function lockPatientReviewRows() {
    const body = $("#patient-review-body");
    if (!body) return;
    for (const row of body.querySelectorAll("tr")) {
      const key = row.querySelector("th small")?.textContent?.trim() || "";
      if (!isDerivedKey(key)) continue;
      row.dataset.derivedReadonly = "true";
      const actions = row.querySelector(".review-row-actions");
      if (actions) {
        for (const button of actions.querySelectorAll("button")) {
          if (button.textContent !== "查看来源图") button.remove();
        }
        if (!actions.querySelector(".derived-readonly-note")) {
          const note = document.createElement("small");
          note.className = "derived-readonly-note";
          note.textContent = "自动整理 · 只读";
          actions.appendChild(note);
        }
      }
    }
    const select = $("#manual-field-name");
    if (select) {
      for (const option of [...select.options]) {
        if (isDerivedKey(option.value)) option.remove();
      }
    }
  }

  // enhancements.js already moves the canvas origin to the crop center before
  // painting the sanitized bitmap. A redaction center must therefore be moved
  // relative to that crop center. Using absolute source-image coordinates here
  // adds the crop offset twice and makes the saved mask jump down/right.
  function normalizeDegrees(value) {
    let angle = Number(value || 0) % 360;
    if (angle > 180) angle -= 360;
    if (angle <= -180) angle += 360;
    return angle;
  }

  if (typeof buildSanitizedBlob === "function") {
    buildSanitizedBlob = () => new Promise((resolve, reject) => {
      const crop = state.crop;
      if (!crop) return reject(new Error("请先完成裁剪"));
      const output = document.createElement("canvas");
      output.width = Math.max(1, Math.round(crop.width));
      output.height = Math.max(1, Math.round(crop.height));
      const out = output.getContext("2d", {alpha: false});
      out.fillStyle = "#fff";
      out.fillRect(0, 0, output.width, output.height);

      const source = state.editingDocumentId ? state.sourceImage : activeImageSource();
      const cropAngle = normalizeDegrees(crop.rotation) * Math.PI / 180;
      const cropCenterX = crop.x + crop.width / 2;
      const cropCenterY = crop.y + crop.height / 2;

      out.save();
      out.translate(output.width / 2, output.height / 2);
      out.rotate(-cropAngle);
      out.drawImage(source, -cropCenterX, -cropCenterY);
      out.fillStyle = "#111";
      for (const rect of state.redactions) {
        const redactionCenterX = rect.x + rect.width / 2;
        const redactionCenterY = rect.y + rect.height / 2;
        out.save();
        out.translate(redactionCenterX - cropCenterX, redactionCenterY - cropCenterY);
        out.rotate(normalizeDegrees(rect.rotation) * Math.PI / 180);
        out.fillRect(-rect.width / 2, -rect.height / 2, rect.width, rect.height);
        out.restore();
      }
      out.restore();
      output.toBlob(
        blob => blob ? resolve(blob) : reject(new Error("脱敏图片生成失败")),
        "image/png",
      );
    });
  }

  const LEARNING_STORAGE_KEY = "bce-learning-summary-v1";
  const LEARNING_EXCLUDED_FIELDS = new Set(["record_number", "contact"]);

  function learningFieldStats(map, fieldName, label = "") {
    if (!map.has(fieldName)) {
      map.set(fieldName, {
        field_name: fieldName,
        label: label || fieldName,
        edit_count: 0,
        manual_fill_count: 0,
        corrections: new Map(),
        manual_values: new Map(),
      });
    }
    const item = map.get(fieldName);
    if (label && item.label === item.field_name) item.label = label;
    return item;
  }

  function addCount(map, key) {
    const value = String(key ?? "").trim();
    if (!value) return;
    map.set(value, (map.get(value) || 0) + 1);
  }

  async function collectHumanLearningSummary() {
    const patients = state.patients?.length ? state.patients : await api("/api/patients");
    const details = [];
    for (const patient of patients) {
      try {
        details.push(await api(`/api/patients/${patient.id}`));
      } catch (_) {
        // Patient list/detail can race with deletion; skip only that patient.
      }
    }

    const fields = new Map();
    let editCount = 0;
    let manualFillCount = 0;

    for (const detail of details) {
      const observations = detail.observations || [];
      const byField = new Map(observations.map(item => [item.field_name, item]));
      for (const audit of detail.audit_log || []) {
        if (!["USER_EDIT", "USER_EDIT_VERIFIED"].includes(audit.operation)) continue;
        if (!audit.field_name || LEARNING_EXCLUDED_FIELDS.has(audit.field_name) || isDerivedKey(audit.field_name)) continue;
        const oldValue = String(audit.old_value ?? "").trim();
        const newValue = String(audit.new_value ?? "").trim();
        if (!newValue || oldValue === newValue) continue;
        const observation = byField.get(audit.field_name);
        const stats = learningFieldStats(fields, audit.field_name, observation?.field_label || "");
        stats.edit_count += 1;
        editCount += 1;
        const reason = String(audit.reason || "").trim();
        const pattern = `${oldValue || "∅"} → ${newValue}${reason ? `（${reason}）` : ""}`;
        addCount(stats.corrections, pattern);
      }

      for (const observation of observations) {
        if (LEARNING_EXCLUDED_FIELDS.has(observation.field_name) || isDerivedKey(observation.field_name)) continue;
        if (String(observation.raw_text || "").trim() !== "人工手动补充") continue;
        const value = String(observation.current_value ?? "").trim();
        if (!value) continue;
        const stats = learningFieldStats(fields, observation.field_name, observation.field_label || "");
        stats.manual_fill_count += 1;
        manualFillCount += 1;
        addCount(stats.manual_values, value);
      }
    }

    const fieldRows = [...fields.values()].map(item => ({
      field_name: item.field_name,
      label: item.label,
      edit_count: item.edit_count,
      manual_fill_count: item.manual_fill_count,
      corrections: [...item.corrections.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([pattern, count]) => ({pattern, count})),
      manual_values: [...item.manual_values.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([value, count]) => ({value, count})),
    })).sort((a, b) => (b.edit_count + b.manual_fill_count) - (a.edit_count + a.manual_fill_count));

    return {
      version: 1,
      generated_at: new Date().toISOString(),
      patient_count: details.length,
      edit_count: editCount,
      manual_fill_count: manualFillCount,
      fields: fieldRows,
    };
  }

  function ensureLearningDialog() {
    let dialog = $("#learning-summary-dialog");
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.id = "learning-summary-dialog";
    dialog.className = "patient-review-dialog";
    dialog.innerHTML = `
      <div class="patient-review-dialog-header">
        <div><span class="eyebrow">HUMAN CORRECTION SUMMARY</span><h2>改进学习摘要</h2></div>
        <button id="close-learning-summary" class="tool" type="button">关闭</button>
      </div>
      <div style="padding:16px 20px;max-height:70vh;overflow:auto">
        <p id="learning-summary-meta"></p>
        <p class="queue-help">汇总人工修改和人工补填，作为后续规则优化/微调的学习材料；点击不会直接修改大模型权重。</p>
        <div id="learning-summary-body"></div>
      </div>`;
    document.body.appendChild(dialog);
    $("#close-learning-summary").onclick = () => dialog.close();
    return dialog;
  }

  function renderLearningSummary(summary) {
    const dialog = ensureLearningDialog();
    $("#learning-summary-meta").textContent = `已扫描 ${summary.patient_count} 名患者：人工修改 ${summary.edit_count} 条，人工补填 ${summary.manual_fill_count} 条，涉及 ${summary.fields.length} 个字段。`;
    const body = $("#learning-summary-body");
    if (!summary.fields.length) {
      body.innerHTML = '<div class="muted-empty">目前还没有可汇总的人工修改或人工补填。</div>';
    } else {
      body.innerHTML = summary.fields.map(field => {
        const corrections = field.corrections.length
          ? `<ul>${field.corrections.map(item => `<li>${escapeHtml(item.pattern)}${item.count > 1 ? ` ×${item.count}` : ""}</li>`).join("")}</ul>`
          : '<span class="empty-answer">无人工修改</span>';
        const fills = field.manual_values.length
          ? `<ul>${field.manual_values.map(item => `<li>${escapeHtml(item.value)}${item.count > 1 ? ` ×${item.count}` : ""}</li>`).join("")}</ul>`
          : '<span class="empty-answer">无人工补填</span>';
        return `<section style="border-top:1px solid var(--border,#ddd);padding:12px 0">
          <strong>${escapeHtml(field.label)} <small>${escapeHtml(field.field_name)}</small></strong>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:8px">
            <div><b>人工修改 ${field.edit_count}</b>${corrections}</div>
            <div><b>人工补填 ${field.manual_fill_count}</b>${fills}</div>
          </div>
        </section>`;
      }).join("");
    }
    if (!dialog.open) dialog.showModal();
  }

  function installLearningButton() {
    const actions = document.querySelector(".patient-browser-actions");
    if (!actions || $("#improve-learning")) return;
    const button = document.createElement("button");
    button.id = "improve-learning";
    button.className = "tool";
    button.type = "button";
    button.textContent = "改进学习";
    button.title = "汇总目前所有患者的人工修改和人工补填";
    actions.insertBefore(button, $("#scan-patient-packages"));
    button.onclick = async () => {
      const originalText = button.textContent;
      button.disabled = true;
      button.textContent = "正在总结…";
      try {
        const summary = await collectHumanLearningSummary();
        localStorage.setItem(LEARNING_STORAGE_KEY, JSON.stringify(summary));
        renderLearningSummary(summary);
        toast(`学习摘要已更新：${summary.edit_count} 条修改，${summary.manual_fill_count} 条补填`);
      } catch (error) {
        toast(`学习摘要失败：${error.message}`);
      } finally {
        button.disabled = false;
        button.textContent = originalText;
      }
    };
  }

  const reviewKey = $("#review-field-key");
  if (reviewKey) {
    new MutationObserver(lockCurrentFieldReview).observe(reviewKey, {
      childList: true, subtree: true, characterData: true,
    });
  }
  const reviewPanel = $("#field-review-panel");
  if (reviewPanel) {
    new MutationObserver(lockCurrentFieldReview).observe(reviewPanel, {
      attributes: true, attributeFilter: ["hidden"],
    });
  }

  const originalReviewClick = $("#review-patient-summary")?.onclick;
  if (originalReviewClick) {
    $("#review-patient-summary").onclick = async event => {
      const result = originalReviewClick.call(event.currentTarget, event);
      await Promise.resolve(result);
      queueMicrotask(lockPatientReviewRows);
      setTimeout(lockPatientReviewRows, 0);
      return result;
    };
  }

  if (typeof showPatientReview === "function") {
    const originalShowPatientReview = showPatientReview;
    showPatientReview = async (...args) => {
      const result = await originalShowPatientReview(...args);
      lockPatientReviewRows();
      return result;
    };
  }

  const reviewBody = $("#patient-review-body");
  if (reviewBody) {
    new MutationObserver(lockPatientReviewRows).observe(reviewBody, {childList: true, subtree: true});
  }

  installLearningButton();
  lockCurrentFieldReview();
})();
