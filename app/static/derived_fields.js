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

  const shutdownScript = document.createElement("script");
  shutdownScript.src = "/shutdown.js";
  shutdownScript.defer = true;
  document.body.appendChild(shutdownScript);
  lockCurrentFieldReview();
})();
