/* Text learning + OCR evidence positioning.
 * Human edits are learned by the backend from the audit trail. This frontend
 * module exports the same correction history as machine-readable JSON and maps
 * each extracted field back to the most relevant OCR line/bbox on the image.
 */
(() => {
  const EXPORT_STORAGE_KEY = "bce-text-learning-v2";
  const EXCLUDED_FIELDS = new Set(["record_number", "contact"]);
  const MANUAL_FILL_MARKER = "人工手动补充";

  function isDerivedKey(key) {
    const value = String(key || "").trim();
    return [
      "clinical_t_component", "clinical_n_component", "clinical_m_component",
      "pathological_t_component", "pathological_n_component", "pathological_m_component",
    ].includes(value) || /_dim[123]_mm$/.test(value);
  }

  const text = value => String(value ?? "").trim();

  function increment(map, key, payload) {
    if (!map.has(key)) map.set(key, {...payload, count: 0});
    map.get(key).count += 1;
  }

  async function collectTextLearningJson() {
    const patients = state.patients?.length ? state.patients : await api("/api/patients");
    const details = [];
    for (const patient of patients) {
      try {
        details.push(await api(`/api/patients/${patient.id}`));
      } catch (_) {
        // A patient can disappear while scanning; skip only that patient.
      }
    }

    const fields = new Map();
    let editCount = 0;
    let manualFillCount = 0;

    function fieldStats(fieldName, label = "") {
      if (!fields.has(fieldName)) {
        fields.set(fieldName, {
          field_name: fieldName,
          label: label || fieldName,
          edit_count: 0,
          manual_fill_count: 0,
          corrections: new Map(),
          manual_values: new Map(),
        });
      }
      const item = fields.get(fieldName);
      if (label && item.label === item.field_name) item.label = label;
      return item;
    }

    for (const detail of details) {
      const byField = new Map((detail.observations || []).map(item => [item.field_name, item]));
      for (const audit of detail.audit_log || []) {
        if (!["USER_EDIT", "USER_EDIT_VERIFIED"].includes(audit.operation)) continue;
        const fieldName = text(audit.field_name);
        if (!fieldName || EXCLUDED_FIELDS.has(fieldName) || isDerivedKey(fieldName)) continue;
        const from = text(audit.old_value);
        const to = text(audit.new_value);
        if (!to || from === to) continue;
        const reason = text(audit.reason);
        const observation = byField.get(fieldName);
        const item = fieldStats(fieldName, observation?.field_label || "");
        item.edit_count += 1;
        editCount += 1;
        increment(item.corrections, JSON.stringify([from, to, reason]), {
          from,
          to,
          ...(reason ? {reason} : {}),
          pattern: `${from || "∅"} → ${to}${reason ? `（${reason}）` : ""}`,
        });
      }

      for (const observation of detail.observations || []) {
        const fieldName = text(observation.field_name);
        if (!fieldName || EXCLUDED_FIELDS.has(fieldName) || isDerivedKey(fieldName)) continue;
        if (text(observation.raw_text) !== MANUAL_FILL_MARKER) continue;
        const value = text(observation.current_value);
        if (!value) continue;
        const item = fieldStats(fieldName, observation.field_label || "");
        item.manual_fill_count += 1;
        manualFillCount += 1;
        increment(item.manual_values, value, {value});
      }
    }

    const fieldRows = [...fields.values()].map(item => ({
      field_name: item.field_name,
      label: item.label,
      edit_count: item.edit_count,
      manual_fill_count: item.manual_fill_count,
      corrections: [...item.corrections.values()].sort((a, b) => b.count - a.count),
      manual_values: [...item.manual_values.values()].sort((a, b) => b.count - a.count),
    })).sort((a, b) =>
      (b.edit_count + b.manual_fill_count) - (a.edit_count + a.manual_fill_count)
      || a.field_name.localeCompare(b.field_name)
    );

    return {
      version: 2,
      type: "bce_text_learning",
      source: "local_human_corrections",
      generated_at: new Date().toISOString(),
      patient_count: details.length,
      edit_count: editCount,
      manual_fill_count: manualFillCount,
      fields: fieldRows,
      policy: {
        use: "learn_field_interpretation_format_and_correction_patterns",
        never_copy_historical_patient_values: true,
        require_current_ocr_evidence: true,
      },
    };
  }

  function downloadJson(payload) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], {type: "application/json;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
    anchor.href = url;
    anchor.download = `BCE_text_learning_${stamp}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function installLearningExportButton() {
    const improve = document.querySelector("#improve-learning");
    if (!improve || document.querySelector("#export-text-learning")) return;
    improve.title = "汇总人工修改与补填；这些纠错会自动用于后续文本识别";
    const button = document.createElement("button");
    button.id = "export-text-learning";
    button.type = "button";
    button.className = "tool";
    button.textContent = "导出学习JSON";
    button.title = "导出可供AI读取的本地文本学习结果";
    improve.insertAdjacentElement("afterend", button);
    button.onclick = async () => {
      const original = button.textContent;
      button.disabled = true;
      button.textContent = "正在整理…";
      try {
        const payload = await collectTextLearningJson();
        localStorage.setItem(EXPORT_STORAGE_KEY, JSON.stringify(payload));
        downloadJson(payload);
        toast(`文本学习JSON已导出：${payload.edit_count} 条修改，${payload.manual_fill_count} 条补填`);
      } catch (error) {
        toast(`导出文本学习失败：${error.message}`);
      } finally {
        button.disabled = false;
        button.textContent = original;
      }
    };
  }

  function normalizeForMatch(value) {
    return text(value)
      .toLowerCase()
      .replace(/[\s\u3000]+/g, "")
      .replace(/[，。；：、,.!?！？“”‘’'"（）()【】\[\]{}<>《》]/g, "");
  }

  function bigrams(value) {
    if (value.length < 2) return value ? [value] : [];
    const result = [];
    for (let index = 0; index < value.length - 1; index += 1) {
      result.push(value.slice(index, index + 2));
    }
    return result;
  }

  function textSimilarity(left, right) {
    const a = normalizeForMatch(left), b = normalizeForMatch(right);
    if (!a || !b) return 0;
    if (a === b) return 1;
    if (a.includes(b) || b.includes(a)) {
      const ratio = Math.min(a.length, b.length) / Math.max(a.length, b.length);
      return 0.88 + 0.12 * ratio;
    }
    const aGrams = bigrams(a), bGrams = bigrams(b);
    if (!aGrams.length || !bGrams.length) return 0;
    const counts = new Map();
    for (const gram of aGrams) counts.set(gram, (counts.get(gram) || 0) + 1);
    let overlap = 0;
    for (const gram of bGrams) {
      const count = counts.get(gram) || 0;
      if (!count) continue;
      overlap += 1;
      counts.set(gram, count - 1);
    }
    return (2 * overlap) / (aGrams.length + bGrams.length);
  }

  function rectFromOcrBox(box) {
    if (!Array.isArray(box)) return null;
    if (box.length >= 4 && box.slice(0, 4).every(value => Number.isFinite(Number(value)))) {
      const [x1, y1, x2, y2] = box.slice(0, 4).map(Number);
      return {
        x: Math.min(x1, x2), y: Math.min(y1, y2),
        width: Math.abs(x2 - x1), height: Math.abs(y2 - y1),
      };
    }
    if (box.length && Array.isArray(box[0])) {
      const points = box.map(point => ({x: Number(point[0]), y: Number(point[1])}))
        .filter(point => Number.isFinite(point.x) && Number.isFinite(point.y));
      if (!points.length) return null;
      const xs = points.map(point => point.x), ys = points.map(point => point.y);
      const left = Math.min(...xs), top = Math.min(...ys);
      const right = Math.max(...xs), bottom = Math.max(...ys);
      return {x: left, y: top, width: right - left, height: bottom - top};
    }
    return null;
  }

  function ocrLinesForDocument(documentId) {
    const documentItem = (state.patient?.documents || []).find(item => item.id === documentId);
    if (!documentItem?.ocr?.result_json) return [];
    try {
      const payload = typeof documentItem.ocr.result_json === "string"
        ? JSON.parse(documentItem.ocr.result_json)
        : documentItem.ocr.result_json;
      return Array.isArray(payload?.lines) ? payload.lines : [];
    } catch (_) {
      return [];
    }
  }

  function locateObservationEvidence(documentId, observationId) {
    const observation = (state.patient?.observations || []).find(item => item.id === observationId);
    if (!observation || text(observation.raw_text) === MANUAL_FILL_MARKER) return [];
    const evidence = text(observation.raw_text) || text(observation.ai_value) || text(observation.current_value);
    if (!evidence) return [];

    const candidates = ocrLinesForDocument(documentId).map((line, index) => {
      const relevance = textSimilarity(evidence, line.text);
      const ocrConfidence = Number.isFinite(Number(line.score)) ? Number(line.score) : 0;
      return {
        line_id: index + 1,
        text: text(line.text),
        ocr_confidence: ocrConfidence,
        relevance,
        score: relevance * 0.9 + ocrConfidence * 0.1,
        rect: rectFromOcrBox(line.box),
      };
    }).filter(item => item.rect && item.relevance >= 0.25)
      .sort((a, b) => b.score - a.score);

    if (!candidates.length || candidates[0].relevance < 0.38) return [];
    const best = candidates[0];
    const threshold = Math.max(0.38, best.relevance - 0.2);
    return candidates.filter(item => item.relevance >= threshold)
      .slice(0, 4)
      .sort((a, b) => a.line_id - b.line_id);
  }

  function drawSmartEvidence() {
    const boxes = state.smartEvidenceBoxes || [];
    if (!state.sourceImage || !boxes.length) return;
    const sx = scaleX(), sy = scaleY();
    ctx.save();
    ctx.font = "12px Segoe UI";
    for (const item of boxes) {
      const r = item.rect;
      const x = r.x * sx, y = r.y * sy, width = r.width * sx, height = r.height * sy;
      ctx.fillStyle = "rgba(49,168,122,.18)";
      ctx.strokeStyle = "#1e8f68";
      ctx.lineWidth = 3;
      ctx.fillRect(x, y, width, height);
      ctx.strokeRect(x, y, width, height);
      const label = `文本定位 ${Math.round(item.score * 100)}% · L${item.line_id}`;
      const labelWidth = Math.max(92, ctx.measureText(label).width + 10);
      const labelY = Math.max(0, y - 20);
      ctx.fillStyle = "rgba(255,255,255,.92)";
      ctx.fillRect(x, labelY, labelWidth, 18);
      ctx.fillStyle = "#1e6f55";
      ctx.fillText(label, x + 5, labelY + 13);
    }
    ctx.restore();
  }

  if (typeof state !== "undefined") state.smartEvidenceBoxes = [];

  function ensureFunctionWrappers() {
    if (typeof draw === "function" && !draw.__bceTextLocationWrapped) {
      const previousDraw = draw;
      const wrappedDraw = (...args) => {
        const result = previousDraw(...args);
        drawSmartEvidence();
        return result;
      };
      wrappedDraw.__bceTextLocationWrapped = true;
      draw = wrappedDraw;
    }

    if (typeof openSavedDocumentPreview === "function" && !openSavedDocumentPreview.__bceTextLocationWrapped) {
      const previousOpen = openSavedDocumentPreview;
      const wrappedOpen = async (documentId, observationId = null) => {
        const result = await previousOpen(documentId, observationId);
        state.smartEvidenceBoxes = observationId ? locateObservationEvidence(documentId, observationId) : [];
        draw();
        if (observationId) {
          const help = document.querySelector("#editor-help");
          if (help && state.smartEvidenceBoxes.length) {
            const best = Math.max(...state.smartEvidenceBoxes.map(item => item.score));
            help.textContent = `已自动定位该字段的OCR证据文字（匹配度 ${Math.round(best * 100)}%）；绿色高亮为文本证据位置。`;
          } else if (help) {
            help.textContent = "已打开来源图片，但没有找到足够可靠的OCR文本位置；请根据证据原文人工核对。";
          }
        }
        return result;
      };
      wrappedOpen.__bceTextLocationWrapped = true;
      openSavedDocumentPreview = wrappedOpen;
    }
  }

  function replaceUiTerminology(root = document.body) {
    if (!root) return;
    const replaceValue = value => {
      if (value.trim() === "来源图") return value.replace("来源图", "文本定位");
      let output = value;
      const replacements = [
        [/查看来源图/g, "文本定位"],
        [/人工标注高信度ROI/g, "人工文本定位"],
        [/高信度ROI/g, "文本定位"],
        [/信息框\s*ROI/g, "文本定位框"],
        [/当前\s*ROI\s*类型/g, "当前文本定位类型"],
        [/ROI\s*类型/g, "文本定位类型"],
        [/ROI/g, "文本定位"],
      ];
      for (const [pattern, replacement] of replacements) output = output.replace(pattern, replacement);
      return output;
    };

    if (root.nodeType === Node.TEXT_NODE) {
      const next = replaceValue(root.nodeValue || "");
      if (next !== root.nodeValue) root.nodeValue = next;
      return;
    }
    if (!(root instanceof Element) && root !== document.body) return;

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      if (["SCRIPT", "STYLE"].includes(node.parentElement?.tagName)) continue;
      const next = replaceValue(node.nodeValue || "");
      if (next !== node.nodeValue) node.nodeValue = next;
    }

    const elements = root instanceof Element
      ? [root, ...root.querySelectorAll("[title],[aria-label],[placeholder]")]
      : [];
    for (const element of elements) {
      for (const attribute of ["title", "aria-label", "placeholder"]) {
        if (!element.hasAttribute(attribute)) continue;
        const current = element.getAttribute(attribute) || "";
        const next = replaceValue(current);
        if (next !== current) element.setAttribute(attribute, next);
      }
    }
  }

  function improveLearningDialogCopy() {
    const help = document.querySelector("#learning-summary-dialog .queue-help");
    if (!help) return;
    const copy = "人工修改与人工补填会自动进入本地文本学习，并用于后续AI提取的纠错；这里仅展示汇总。可在患者列表上方导出JSON供AI或迁移使用。";
    if (help.textContent !== copy) help.textContent = copy;
  }

  const observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === "characterData") replaceUiTerminology(record.target);
      for (const node of record.addedNodes || []) replaceUiTerminology(node);
    }
    installLearningExportButton();
    improveLearningDialogCopy();
    ensureFunctionWrappers();
  });
  observer.observe(document.body, {childList: true, subtree: true, characterData: true});

  replaceUiTerminology();
  installLearningExportButton();
  improveLearningDialogCopy();
  ensureFunctionWrappers();
  [0, 200, 1000].forEach(delay => setTimeout(ensureFunctionWrappers, delay));

  window.BCETextLearning = {
    collectTextLearningJson,
    locateObservationEvidence,
    textSimilarity,
  };
})();
