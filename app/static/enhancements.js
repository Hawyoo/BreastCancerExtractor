/* UX and Windows-portable follow-up enhancements.
 * Loaded after app.js so it can extend the existing classic-script globals
 * without forcing a large rewrite of the primary frontend bundle.
 */
(() => {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "/enhancements.css";
  document.head.appendChild(link);

  let aiDisconnected = false;

  function normalizeAngle(value) {
    let angle = Number(value || 0) % 360;
    if (angle > 180) angle -= 360;
    if (angle <= -180) angle += 360;
    return angle;
  }

  function geometry(rect) {
    return {
      x: Number(rect.x || 0), y: Number(rect.y || 0),
      width: Number(rect.width || 0), height: Number(rect.height || 0),
      rotation: normalizeAngle(rect.rotation || 0),
      ...(rect.type ? {type: rect.type} : {}),
      ...(rect.label ? {label: rect.label} : {}),
    };
  }

  // Make rotation-only changes count as real editor revisions.
  editorRevisionSignature = () => JSON.stringify({
    crop: state.crop ? geometry(state.crop) : null,
    redactions: state.redactions.map(geometry),
    rois: state.rois.map(geometry),
    documentType: $("#document-type").value,
    displayName: $("#display-name").value,
  });

  function rotatedCorners(rect, display = true) {
    const sx = display ? scaleX() : 1;
    const sy = display ? scaleY() : 1;
    const cx = (rect.x + rect.width / 2) * sx;
    const cy = (rect.y + rect.height / 2) * sy;
    const hw = rect.width * sx / 2;
    const hh = rect.height * sy / 2;
    const angle = normalizeAngle(rect.rotation) * Math.PI / 180;
    const cos = Math.cos(angle), sin = Math.sin(angle);
    return [[-hw,-hh],[hw,-hh],[hw,hh],[-hw,hh]].map(([x,y]) => ({
      x: cx + x * cos - y * sin,
      y: cy + x * sin + y * cos,
    }));
  }

  function pointInRotatedRect(point, rect) {
    const cx = (rect.x + rect.width / 2) * scaleX();
    const cy = (rect.y + rect.height / 2) * scaleY();
    const angle = -normalizeAngle(rect.rotation) * Math.PI / 180;
    const dx = point.x - cx, dy = point.y - cy;
    const localX = dx * Math.cos(angle) - dy * Math.sin(angle);
    const localY = dx * Math.sin(angle) + dy * Math.cos(angle);
    return Math.abs(localX) <= rect.width * scaleX() / 2 && Math.abs(localY) <= rect.height * scaleY() / 2;
  }

  function rotationHandle(rect) {
    const corners = rotatedCorners(rect, true);
    const topMid = {x: (corners[0].x + corners[1].x) / 2, y: (corners[0].y + corners[1].y) / 2};
    const center = {
      x: (rect.x + rect.width / 2) * scaleX(),
      y: (rect.y + rect.height / 2) * scaleY(),
    };
    const vx = topMid.x - center.x, vy = topMid.y - center.y;
    const length = Math.hypot(vx, vy) || 1;
    return {x: topMid.x + (vx / length) * 26, y: topMid.y + (vy / length) * 26, topMid};
  }

  function drawRotatedOverlay(rect, fill, stroke, label, selected = false) {
    const corners = rotatedCorners(rect, true);
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(corners[0].x, corners[0].y);
    corners.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
    ctx.closePath();
    ctx.fillStyle = fill; ctx.fill();
    ctx.strokeStyle = stroke; ctx.lineWidth = selected ? 3 : 2; ctx.stroke();
    if (label) {
      ctx.font = "12px Segoe UI"; ctx.fillStyle = stroke;
      ctx.fillText(label, corners[0].x + 4, corners[0].y + 14);
    }
    if (selected) {
      for (const p of corners) {
        ctx.fillStyle = "#fff"; ctx.fillRect(p.x - 4, p.y - 4, 8, 8);
        ctx.strokeStyle = stroke; ctx.strokeRect(p.x - 4, p.y - 4, 8, 8);
      }
      const handle = rotationHandle(rect);
      ctx.beginPath(); ctx.moveTo(handle.topMid.x, handle.topMid.y); ctx.lineTo(handle.x, handle.y); ctx.stroke();
      ctx.beginPath(); ctx.arc(handle.x, handle.y, 7, 0, Math.PI * 2);
      ctx.fillStyle = "#fff"; ctx.fill(); ctx.stroke();
    }
    ctx.restore();
  }

  function enhancedDraw() {
    if (!state.sourceImage) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(activeImageSource(), 0, 0, canvas.width, canvas.height);

    if (state.crop) {
      const corners = rotatedCorners(state.crop, true);
      ctx.save();
      ctx.fillStyle = "rgba(0,0,0,.48)";
      ctx.beginPath();
      ctx.rect(0, 0, canvas.width, canvas.height);
      ctx.moveTo(corners[0].x, corners[0].y);
      corners.slice(1).forEach(p => ctx.lineTo(p.x, p.y)); ctx.closePath();
      ctx.fill("evenodd");
      ctx.restore();
      drawRotatedOverlay(state.crop, "rgba(244,201,93,.04)", "#f4c95d", "裁剪", state.cropEditable && state.mode === "crop");
    }

    state.redactions.forEach((rect, index) =>
      drawRotatedOverlay(rect, "rgba(18,18,18,.9)", "#fff", "隐私遮盖", state.mode === "redact" && state.activeRedactionIndex === index)
    );
    state.rois.forEach((roi, index) =>
      drawRotatedOverlay(roi, "rgba(39,147,104,.16)", "#31a87a", roi.label, state.mode === "roi" && state.activeRoiIndex === index)
    );
    if (state.drawing) drawDisplayOverlay(normalizedRect(state.drawing.start, state.drawing.end), "rgba(255,196,68,.16)", "#f2bd3e", state.mode);
    updateSaveAction();
  }
  draw = enhancedDraw;

  // Preserve crop rotation when the original resize helper replaces the crop object.
  const originalResizeCrop = resizeCrop;
  resizeCrop = point => {
    const rotation = normalizeAngle(state.crop?.rotation);
    originalResizeCrop(point);
    if (state.crop) state.crop.rotation = rotation;
  };

  function selectedTransformTarget(point = null) {
    if (state.mode === "crop" && state.cropEditable && state.crop) return {kind: "crop", index: -1, rect: state.crop};
    if (state.mode === "roi") {
      if (point) {
        for (let index = state.rois.length - 1; index >= 0; index--) {
          if (pointInRotatedRect(point, state.rois[index])) return {kind: "roi", index, rect: state.rois[index]};
        }
      }
      if (state.activeRoiIndex >= 0 && state.rois[state.activeRoiIndex]) return {kind: "roi", index: state.activeRoiIndex, rect: state.rois[state.activeRoiIndex]};
    }
    if (state.mode === "redact") {
      if (point) {
        for (let index = state.redactions.length - 1; index >= 0; index--) {
          if (pointInRotatedRect(point, state.redactions[index])) return {kind: "redact", index, rect: state.redactions[index]};
        }
      }
      if (state.activeRedactionIndex >= 0 && state.redactions[state.activeRedactionIndex]) return {kind: "redact", index: state.activeRedactionIndex, rect: state.redactions[state.activeRedactionIndex]};
    }
    return null;
  }

  function setTargetRect(target, rect) {
    if (target.kind === "crop") state.crop = rect;
    else if (target.kind === "roi") state.rois[target.index] = rect;
    else state.redactions[target.index] = rect;
  }

  function clampMovedRect(rect) {
    const angle = normalizeAngle(rect.rotation) * Math.PI / 180;
    const hx = Math.abs(Math.cos(angle)) * rect.width / 2 + Math.abs(Math.sin(angle)) * rect.height / 2;
    const hy = Math.abs(Math.sin(angle)) * rect.width / 2 + Math.abs(Math.cos(angle)) * rect.height / 2;
    let cx = rect.x + rect.width / 2, cy = rect.y + rect.height / 2;
    cx = Math.min(state.sourceImage.naturalWidth - hx, Math.max(hx, cx));
    cy = Math.min(state.sourceImage.naturalHeight - hy, Math.max(hy, cy));
    return {...rect, x: cx - rect.width / 2, y: cy - rect.height / 2};
  }

  function selectTarget(target) {
    if (!target) return;
    if (target.kind === "roi") state.activeRoiIndex = target.index;
    if (target.kind === "redact") state.activeRedactionIndex = target.index;
    updateTransformHelp(target);
  }

  function updateTransformHelp(target = selectedTransformTarget()) {
    const suffix = target ? ` 当前${target.kind === "crop" ? "裁剪框" : target.kind === "roi" ? "ROI" : "遮盖"}：拖动框内部平移，拖动圆形手柄旋转。` : "";
    if (state.sourceImage) $("#editor-help").textContent = `${$("#editor-help").textContent.split(" 当前")[0]}${suffix}`;
  }

  state.activeRedactionIndex = -1;
  state.transformGesture = null;

  canvas.addEventListener("pointerdown", event => {
    if (!state.sourceImage) return;
    const point = canvasPoint(event);
    const candidate = selectedTransformTarget(point) || selectedTransformTarget();
    if (!candidate) return;
    const handle = rotationHandle(candidate.rect);
    const nearRotate = Math.hypot(point.x - handle.x, point.y - handle.y) <= 14;
    const inside = pointInRotatedRect(point, candidate.rect);
    if (!nearRotate && !inside) return;
    if (!nearRotate && candidate.kind !== "redact" && normalizeAngle(candidate.rect.rotation) === 0 && rectEdgesAt(candidate.rect, point)) return;

    selectTarget(candidate);
    const center = {
      x: (candidate.rect.x + candidate.rect.width / 2) * scaleX(),
      y: (candidate.rect.y + candidate.rect.height / 2) * scaleY(),
    };
    state.transformGesture = {
      kind: nearRotate ? "rotate" : "move",
      target: {kind: candidate.kind, index: candidate.index},
      original: {...candidate.rect},
      startSource: toSource(point),
      startPointerAngle: Math.atan2(point.y - center.y, point.x - center.x),
    };
    canvas.setPointerCapture(event.pointerId);
    event.preventDefault(); event.stopImmediatePropagation();
    draw();
  }, true);

  canvas.addEventListener("pointermove", event => {
    const gesture = state.transformGesture;
    if (!gesture || !state.sourceImage) return;
    const point = canvasPoint(event);
    const target = selectedTransformTarget();
    if (!target) return;
    if (gesture.kind === "move") {
      const current = toSource(point);
      const dx = current.x - gesture.startSource.x, dy = current.y - gesture.startSource.y;
      setTargetRect(target, clampMovedRect({...gesture.original, x: gesture.original.x + dx, y: gesture.original.y + dy}));
      canvas.style.cursor = "move";
    } else {
      const center = {
        x: (gesture.original.x + gesture.original.width / 2) * scaleX(),
        y: (gesture.original.y + gesture.original.height / 2) * scaleY(),
      };
      const currentAngle = Math.atan2(point.y - center.y, point.x - center.x);
      const delta = (currentAngle - gesture.startPointerAngle) * 180 / Math.PI;
      setTargetRect(target, {...gesture.original, rotation: normalizeAngle((gesture.original.rotation || 0) + delta)});
      canvas.style.cursor = "grabbing";
    }
    event.preventDefault(); event.stopImmediatePropagation(); draw();
  }, true);

  const finishGesture = event => {
    if (!state.transformGesture) return;
    state.transformGesture = null;
    event.preventDefault(); event.stopImmediatePropagation(); draw();
  };
  canvas.addEventListener("pointerup", finishGesture, true);
  canvas.addEventListener("pointercancel", finishGesture, true);

  // After the original drawing handler creates a redaction, make it immediately selectable.
  canvas.addEventListener("pointerup", () => {
    if (state.mode === "redact" && state.redactions.length) {
      state.activeRedactionIndex = state.redactions.length - 1;
      state.redactions[state.activeRedactionIndex].rotation ||= 0;
      updateTransformHelp(); draw();
    }
    if (state.mode === "roi" && state.activeRoiIndex >= 0) {
      state.rois[state.activeRoiIndex].rotation ||= 0;
      updateTransformHelp(); draw();
    }
    if (state.mode === "crop" && state.crop) {
      state.crop.rotation ||= 0;
      updateTransformHelp(); draw();
    }
  });

  function rotateSelected(delta) {
    const target = selectedTransformTarget();
    if (!target) return toast("请先选择裁剪框、ROI或遮盖区域");
    setTargetRect(target, {...target.rect, rotation: normalizeAngle((target.rect.rotation || 0) + delta)});
    draw(); updateTransformHelp(target);
  }

  const toolbar = document.querySelector(".editor-toolbar");
  const resetButton = $("#reset-editor");
  const rotateGroup = document.createElement("div");
  rotateGroup.className = "transform-controls";
  rotateGroup.innerHTML = `
    <button id="rotate-selected-left" class="tool" type="button" disabled title="所选框左旋1度">↺ 1°</button>
    <button id="rotate-selected-right" class="tool" type="button" disabled title="所选框右旋1度">↻ 1°</button>
    <button id="rotate-selected-reset" class="tool" type="button" disabled>角度归零</button>`;
  toolbar.insertBefore(rotateGroup, resetButton);
  $("#rotate-selected-left").onclick = () => rotateSelected(-1);
  $("#rotate-selected-right").onclick = () => rotateSelected(1);
  $("#rotate-selected-reset").onclick = () => {
    const target = selectedTransformTarget(); if (!target) return toast("请先选择一个框");
    setTargetRect(target, {...target.rect, rotation: 0}); draw();
  };

  const originalEnableEditor = enableEditor;
  enableEditor = enabled => {
    originalEnableEditor(enabled);
    ["#rotate-selected-left", "#rotate-selected-right", "#rotate-selected-reset"].forEach(selector => $(selector).disabled = !enabled);
  };

  // Render rotated crop/redactions into the final sanitized bitmap.
  buildSanitizedBlob = () => new Promise((resolve, reject) => {
    const crop = state.crop;
    const output = document.createElement("canvas");
    output.width = Math.max(1, Math.round(crop.width));
    output.height = Math.max(1, Math.round(crop.height));
    const out = output.getContext("2d", {alpha: false});
    out.fillStyle = "#fff"; out.fillRect(0, 0, output.width, output.height);
    const source = state.editingDocumentId ? state.sourceImage : activeImageSource();
    const angle = normalizeAngle(crop.rotation) * Math.PI / 180;
    const cx = crop.x + crop.width / 2, cy = crop.y + crop.height / 2;
    out.save();
    out.translate(output.width / 2, output.height / 2);
    out.rotate(-angle);
    out.drawImage(source, -cx, -cy);
    out.fillStyle = "#111";
    for (const rect of state.redactions) {
      const rcx = rect.x + rect.width / 2, rcy = rect.y + rect.height / 2;
      out.save(); out.translate(rcx, rcy); out.rotate(normalizeAngle(rect.rotation) * Math.PI / 180);
      out.fillRect(-rect.width / 2, -rect.height / 2, rect.width, rect.height); out.restore();
    }
    out.restore();
    output.toBlob(blob => blob ? resolve(blob) : reject(new Error("脱敏图片生成失败")), "image/png");
  });

  function pointIntoCropOutput(x, y, crop) {
    const angle = -normalizeAngle(crop.rotation) * Math.PI / 180;
    const cx = crop.x + crop.width / 2, cy = crop.y + crop.height / 2;
    const dx = x - cx, dy = y - cy;
    return {
      x: crop.width / 2 + dx * Math.cos(angle) - dy * Math.sin(angle),
      y: crop.height / 2 + dx * Math.sin(angle) + dy * Math.cos(angle),
    };
  }

  function transformedRegions(crop) {
    const rotations = [];
    const regions = [];
    for (const roi of state.rois) {
      const center = pointIntoCropOutput(roi.x + roi.width / 2, roi.y + roi.height / 2, crop);
      if (center.x < -roi.width || center.x > crop.width + roi.width || center.y < -roi.height || center.y > crop.height + roi.height) continue;
      const rotation = normalizeAngle((roi.rotation || 0) - (crop.rotation || 0));
      const left = Math.max(0, center.x - roi.width / 2), top = Math.max(0, center.y - roi.height / 2);
      const right = Math.min(crop.width, center.x + roi.width / 2), bottom = Math.min(crop.height, center.y + roi.height / 2);
      if (right <= left || bottom <= top) continue;
      regions.push({region_type: roi.type, label: roi.label, x: left, y: top, width: right - left, height: bottom - top});
      rotations.push(rotation);
    }
    return {regions, rotations};
  }

  // Replace the save handler so transformed ROI angles are persisted in sanitization_json.
  $("#save-sanitized").onclick = async () => {
    if (!state.patient || !state.sourceImage || !state.crop) return;
    const editingDocumentId = state.editingDocumentId;
    if (editingDocumentId && editorRevisionSignature() === state.editorBaseline) return toast("图片和ROI没有变化，无需重新识别");
    const button = $("#save-sanitized"); button.disabled = true; button.textContent = "正在保存…";
    const patientId = state.patient.id, item = state.rawQueue[state.activeRawIndex];
    if (item) { persistActiveRawItem(); item.status = "SAVING"; renderRawQueue(); }
    try {
      const blob = await buildSanitizedBlob();
      const crop = state.crop;
      const transformed = transformedRegions(crop);
      const persistEnhancement = !editingDocumentId && state.enhancementEnabled;
      const metadata = {
        source_width: state.sourceImage.naturalWidth, source_height: state.sourceImage.naturalHeight,
        crop: geometry(crop), redaction_count: state.redactions.length, client_reencoded: true,
        enhancement_mode: persistEnhancement ? "ENHANCED" : "ORIGINAL",
        enhancement_version: persistEnhancement ? ENHANCEMENT_VERSION : null,
        transforms: {version: 1, roi_rotations: transformed.rotations},
      };
      const form = new FormData();
      form.append("image", blob, "sanitized.png");
      form.append("display_name", $("#display-name").value.trim() || suggestedDisplayName());
      form.append("document_type", $("#document-type").value);
      form.append("sanitization", JSON.stringify(metadata));
      form.append("regions", JSON.stringify(transformed.regions));
      const saveUrl = editingDocumentId ? `/api/documents/${editingDocumentId}` : `/api/patients/${state.patient.id}/documents`;
      const savedDocument = await api(saveUrl, {method: editingDocumentId ? "PUT" : "POST", body: form});
      const target = aiDisconnected ? "OCR_ONLY" : "FULL";
      state.processingJobs.push({id: savedDocument.id, documentId: savedDocument.id, patientId, name: savedDocument.display_name,
        documentType: savedDocument.document_type, target, status: "OCR_QUEUED", stage: "等待OCR", error: null, observationCount: null});
      renderProcessingQueue(); runProcessingQueue();
      if (editingDocumentId) {
        clearEditor(); renderRawQueue(); await refreshCurrentPatient(patientId);
        toast(aiDisconnected ? "脱敏图片已覆盖，新OCR已进入后台队列（AI已断开）" : "脱敏图片已覆盖，旧识别结果已失效；新OCR和AI已进入后台队列");
        return;
      }
      if (item) { item.status = "SAVED"; item.file = null; item.crop = null; item.redactions = []; item.rois = []; }
      clearEditor(); renderRawQueue();
      const next = state.rawQueue.findIndex((candidate, index) => index > state.activeRawIndex && candidate.status === "WAITING");
      const fallback = state.rawQueue.findIndex(candidate => candidate.status === "WAITING");
      state.activeRawIndex = -1;
      const nextIndex = next >= 0 ? next : fallback;
      if (nextIndex >= 0) await loadRawItem(nextIndex);
      toast(nextIndex >= 0 ? "脱敏图已保存；已打开下一张" : "全部原图已确认，后台继续识别");
    } catch (error) {
      if (item) item.status = "EDITING";
      toast(`保存失败：${error.message}`); renderRawQueue();
    } finally { updateSaveAction(); }
  };

  // Restore ROI angles when a previously saved image is reopened.
  const originalOpenSavedDocumentPreview = openSavedDocumentPreview;
  openSavedDocumentPreview = async (documentId, observationId = null) => {
    await originalOpenSavedDocumentPreview(documentId, observationId);
    const doc = (state.patient?.documents || []).find(item => item.id === documentId);
    try {
      const metadata = typeof doc?.sanitization_json === "string" ? JSON.parse(doc.sanitization_json) : (doc?.sanitization_json || {});
      const rotations = metadata?.transforms?.roi_rotations || [];
      state.rois.forEach((roi, index) => roi.rotation = normalizeAngle(rotations[index] || 0));
    } catch (_) { state.rois.forEach(roi => roi.rotation ||= 0); }
    state.editorBaseline = editorRevisionSignature(); draw();
  };

  // One-click upload cancellation: no secondary confirmation.
  const cancelImport = document.createElement("button");
  cancelImport.id = "cancel-raw-upload"; cancelImport.className = "tool"; cancelImport.type = "button";
  cancelImport.textContent = "取消本次上传";
  document.querySelector(".batch-import-bar").appendChild(cancelImport);
  cancelImport.onclick = () => { clearRawQueue(); toast("待上传图片已清空"); };

  // Leaving a patient also drops unsaved browser-only imports directly, without a second confirm.
  $("#exit-patient").onclick = () => {
    clearRawQueue(); state.processingJobs = []; renderProcessingQueue(); state.patient = null; state.selectedObservationId = null;
    $("#patient-workspace").hidden = true; $("#empty-state").hidden = false;
    updatePatientSidebar(); loadPatients().catch(error => toast(error.message)); return true;
  };

  // Processing history is patient-local. Switching patient starts with a clean OCR/AI list.
  const originalSelectPatient = selectPatient;
  selectPatient = async id => {
    const switching = state.patient && state.patient.id !== id;
    if (switching) { state.processingJobs = []; renderProcessingQueue(); }
    return originalSelectPatient(id);
  };

  // Convert the completed-patient review from a modal dialog into a persistent side drawer.
  const reviewDialog = $("#patient-review-dialog");
  reviewDialog.classList.add("patient-review-sidepanel");
  const tableHead = reviewDialog.querySelector("thead tr");
  if (tableHead && tableHead.children.length === 3) tableHead.insertAdjacentHTML("beforeend", "<th>操作</th>");
  const reviewTools = document.createElement("section");
  reviewTools.className = "manual-field-tools";
  reviewTools.innerHTML = `
    <strong>手动补充字段</strong>
    <div class="manual-field-row">
      <select id="manual-field-name" aria-label="字段"></select>
      <input id="manual-field-value" placeholder="输入字段内容">
      <button id="manual-field-add" class="primary" type="button">添加</button>
    </div>
    <small>可补填空白字段，也可修改已有字段；保存后可继续在字段审核区确认。</small>`;
  reviewDialog.querySelector(".patient-review-dialog-header").insertAdjacentElement("afterend", reviewTools);

  async function renderPatientSideReview() {
    if (!state.patient) return;
    const dataset = await api("/api/data-preview?verified_only=false");
    const row = dataset.rows.find(item => item.patient_id === state.patient.id);
    if (!row) throw new Error("未找到当前患者数据");
    $("#patient-review-title").textContent = `患者 ${state.patient.patient_code} · 全部问题与答案`;
    const observations = new Map((state.patient.observations || []).map(item => [item.field_name, item]));
    const body = $("#patient-review-body"); body.innerHTML = "";
    for (const column of dataset.columns) {
      const value = row.values[column.key] ?? "", status = row.statuses[column.key] || "EMPTY";
      const observation = observations.get(column.key);
      const tr = document.createElement("tr");
      tr.innerHTML = `<th><strong>${escapeHtml(column.label)}</strong><small>${escapeHtml(column.key)}</small></th>
        <td>${value === "" ? '<span class="empty-answer">未填写</span>' : escapeHtml(value)}</td>
        <td>${escapeHtml(statusText(status))}</td><td class="review-row-actions"></td>`;
      const actions = tr.querySelector(".review-row-actions");
      if (observation?.document_id) {
        const imageButton = document.createElement("button"); imageButton.type = "button"; imageButton.className = "tool"; imageButton.textContent = "查看来源图";
        imageButton.onclick = () => openSavedDocumentPreview(observation.document_id, observation.id).catch(error => toast(error.message)); actions.appendChild(imageButton);
      }
      if (column.key !== "record_number" && column.key !== "contact") {
        const editButton = document.createElement("button"); editButton.type = "button"; editButton.className = "tool"; editButton.textContent = value === "" ? "手动填写" : "补充记录";
        editButton.onclick = () => {
          $("#manual-field-name").value = column.key; $("#manual-field-value").value = value;
          $("#manual-field-name").dataset.observationId = observation?.id || "";
          $("#manual-field-value").focus();
        };
        actions.appendChild(editButton);
      }
      body.appendChild(tr);
    }
    const select = $("#manual-field-name");
    select.innerHTML = dataset.columns.filter(column => !["record_number", "contact"].includes(column.key))
      .map(column => `<option value="${escapeHtml(column.key)}">${escapeHtml(column.label)} (${escapeHtml(column.key)})</option>`).join("");
    if (!reviewDialog.open) reviewDialog.show();
  }

  showPatientReview = renderPatientSideReview;
  $("#review-patient-summary").onclick = () => renderPatientSideReview().catch(error => toast(error.message));
  $("#close-patient-review").onclick = () => reviewDialog.close();
  $("#manual-field-name").addEventListener("change", () => {
    $("#manual-field-name").dataset.observationId = "";
    $("#manual-field-value").value = "";
  });
  $("#manual-field-add").onclick = async () => {
    if (!state.patient) return;
    const fieldName = $("#manual-field-name").value, value = $("#manual-field-value").value.trim();
    const observationId = $("#manual-field-name").dataset.observationId || "";
    if (!fieldName || !value) return toast("请选择字段并输入内容");
    try {
      if (observationId) {
        await api(`/api/observations/${observationId}`, {method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
          value, operator: "local-user", reason: "患者回顾侧栏手动修改",
        })});
      } else {
        await api(`/api/patients/${state.patient.id}/observations`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
          field_name: fieldName, value, raw_text: "人工手动补充", confidence: "LOW", source_mode: "RECORDED",
        })});
      }
      await refreshCurrentPatient(state.patient.id); await renderPatientSideReview();
      $("#manual-field-value").value = ""; $("#manual-field-name").dataset.observationId = "";
      toast(observationId ? "字段修改已保存" : "字段已手动添加");
    } catch (error) { toast(error.message); }
  };

  // AI-disconnected provider: OCR continues, newly queued FULL jobs become OCR-only.
  const providerSelect = $("#ollama-provider");
  if (![...providerSelect.options].some(option => option.value === "DISABLED")) {
    providerSelect.insertAdjacentHTML("afterbegin", '<option value="DISABLED">断开本地 AI（仅 OCR）</option>');
  }

  function applyAiDisconnected(disconnected) {
    aiDisconnected = Boolean(disconnected);
    document.documentElement.dataset.aiDisconnected = aiDisconnected ? "true" : "false";
    $("#bulk-ai").disabled = aiDisconnected;
    $("#refresh-models").disabled = aiDisconnected;
    if (aiDisconnected) {
      $("#current-model-status").textContent = "当前模型：AI已断开（仅 OCR）";
      $("#model-refresh-status").textContent = "";
    }
    document.querySelectorAll(".run-ai").forEach(button => {
      if (aiDisconnected) {
        if (!button.disabled) button.dataset.aiDisabledByDisconnect = "1";
        button.disabled = true;
      } else if (button.dataset.aiDisabledByDisconnect === "1") {
        button.disabled = false; delete button.dataset.aiDisabledByDisconnect;
      }
    });
    if (aiDisconnected) {
      state.processingJobs.forEach(job => {
        if (job.target === "FULL" && ["OCR_QUEUED", "OCR_RUNNING"].includes(job.status)) job.target = "OCR_ONLY";
        if (job.status === "AI_QUEUED") { job.status = "FAILED"; job.stage = "AI已断开"; job.error = "仅保留OCR模式"; }
      });
      renderProcessingQueue();
    }
  }

  loadHealth = async () => {
    const health = await api("/api/health");
    const disabled = health.ollama?.provider === "DISABLED" || health.ollama?.disabled;
    const ocr = health.ocr?.available ? "OCR已连接" : "OCR未连接";
    if (disabled) $("#service-status").textContent = `● 本地模式 · AI已断开 · ${ocr}`;
    else {
      const provider = health.ollama?.provider === "WINDOWS_HOST" ? "宿主机" : "Docker";
      const processor = health.ollama?.processor && health.ollama.processor !== "IDLE" ? ` · ${health.ollama.processor}` : "";
      const selected = health.ollama?.default_model ? ` · ${health.ollama.default_model}` : "";
      const ollama = health.ollama?.available ? `${provider} Ollama ${health.ollama.models}个模型${selected}${processor}` : `${provider} Ollama未连接`;
      $("#service-status").textContent = `● 本地模式 · ${ollama} · ${ocr}`;
    }
    applyAiDisconnected(disabled);
  };

  loadOllamaProviderSetting = async () => {
    try {
      const setting = await api("/api/settings/ollama-provider");
      $("#ollama-provider").value = setting.provider;
      const disabled = setting.provider === "DISABLED" || setting.health?.disabled;
      if (disabled) $("#ollama-provider-status").textContent = "当前：AI已断开，仅运行OCR";
      else {
        const processor = setting.health.processor === "IDLE" ? "空闲" : setting.health.processor;
        $("#ollama-provider-status").textContent = `当前：${setting.provider === "WINDOWS_HOST" ? "Windows宿主机" : "Docker"} · ${setting.health.available ? `${setting.health.models}个模型 · ${processor}` : "未连接"}`;
      }
      applyAiDisconnected(disabled);
    } catch (error) { $("#ollama-provider-status").textContent = error.message; }
  };

  $("#switch-ollama-provider").onclick = async event => {
    const button = event.currentTarget, provider = $("#ollama-provider").value;
    button.disabled = true; button.textContent = provider === "DISABLED" ? "正在断开…" : "正在测试…";
    try {
      await api("/api/settings/ollama-provider", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({provider})});
      toast(provider === "DISABLED" ? "本地AI已断开；后续仅运行OCR" : `已切换到${provider === "WINDOWS_HOST" ? "Windows宿主机" : "Docker"} Ollama`);
      await Promise.all([loadHealth(), loadOllamaProviderSetting()]);
      if (provider !== "DISABLED") $("#refresh-models").click();
    } catch (error) { toast(error.message); await loadOllamaProviderSetting(); }
    finally { button.disabled = false; button.textContent = "测试连接并使用"; }
  };

  const originalRunProcessingQueue = runProcessingQueue;
  runProcessingQueue = () => {
    if (aiDisconnected) {
      state.processingJobs = state.processingJobs.filter(job => {
        if (job.target === "AI_ONLY") { toast("AI已断开：未加入AI任务"); return false; }
        if (job.target === "FULL") job.target = "OCR_ONLY";
        return true;
      });
      renderProcessingQueue(); runOcrQueue(); return;
    }
    originalRunProcessingQueue();
  };

  const originalRenderDocuments = renderDocuments;
  renderDocuments = () => { originalRenderDocuments(); applyAiDisconnected(aiDisconnected); };

  // Re-run status after all overrides are installed.
  Promise.all([loadHealth(), loadOllamaProviderSetting()]).catch(error => toast(error.message));
})();
