/* OCR evidence positioning for reviewed fields.
 * Text-learning import/export is owned by text_learning_import.js and the
 * backend API. This module only maps evidence text to OCR line/bbox locations.
 */
(() => {
  const MANUAL_FILL_MARKER = "人工手动补充";

  const text = value => String(value ?? "").trim();

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
    if (
      !observation
      || observation.evidence_status === "REJECTED"
      || text(observation.raw_text) === MANUAL_FILL_MARKER
    ) return [];
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

  function evidenceHelp(documentId, observation) {
    const help = document.querySelector("#editor-help");
    if (!help || !observation) return;
    help.replaceChildren();

    const message = document.createElement("span");
    if (observation.evidence_status === "REJECTED") {
      message.textContent = "该字段的错误文本定位已删除，不再用于定位学习。";
    } else if (state.smartEvidenceBoxes.length) {
      const best = Math.max(...state.smartEvidenceBoxes.map(item => item.score));
      message.textContent = `已自动定位该字段的OCR证据文字（匹配度 ${Math.round(best * 100)}%）；绿色高亮为文本证据位置。`;
    } else {
      message.textContent = "已打开来源图片，但没有找到足够可靠的OCR文本位置；请根据证据原文人工核对。";
    }
    help.appendChild(message);

    if (observation.evidence_status !== "REJECTED" && !state.smartEvidenceBoxes.length) return;

    const button = document.createElement("button");
    button.type = "button";
    button.className = observation.evidence_status === "REJECTED" ? "tool" : "danger-tool";
    button.textContent = observation.evidence_status === "REJECTED" ? "恢复自动定位" : "删除错误定位";
    button.onclick = async () => {
      button.disabled = true;
      try {
        if (observation.evidence_status === "REJECTED") {
          await api(`/api/observations/${observation.id}/evidence-location/restore`, {method: "POST"});
          observation.evidence_status = "AUTO";
          state.smartEvidenceBoxes = locateObservationEvidence(documentId, observation.id);
          toast("已恢复该字段的自动文本定位");
        } else {
          await api(`/api/observations/${observation.id}/evidence-location`, {method: "DELETE"});
          observation.evidence_status = "REJECTED";
          state.smartEvidenceBoxes = [];
          toast("错误文本定位已删除，并已排除出定位学习");
        }
        draw();
        evidenceHelp(documentId, observation);
      } catch (error) {
        toast(`更新文本定位失败：${error.message}`);
        button.disabled = false;
      }
    };
    help.appendChild(button);
  }

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
        const observation = (state.patient?.observations || []).find(item => item.id === observationId);
        state.smartEvidenceBoxes = observationId ? locateObservationEvidence(documentId, observationId) : [];
        draw();
        if (observationId) evidenceHelp(documentId, observation);
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

  const observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === "characterData") replaceUiTerminology(record.target);
      for (const node of record.addedNodes || []) replaceUiTerminology(node);
    }
    ensureFunctionWrappers();
  });
  observer.observe(document.body, {childList: true, subtree: true, characterData: true});

  replaceUiTerminology();
  ensureFunctionWrappers();
  [0, 200, 1000].forEach(delay => setTimeout(ensureFunctionWrappers, delay));

  window.BCETextLearning = {
    locateObservationEvidence,
    textSimilarity,
  };
})();
