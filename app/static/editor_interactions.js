(() => {
  const BLACK_CROSSHAIR_CURSOR = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 32 32'%3E%3Cpath d='M16 2V30M2 16H30' stroke='black' stroke-width='1.5'/%3E%3C/svg%3E") 16 16, crosshair`;
  const COLORS = {
    crop: {fill: "rgba(244,201,93,.18)", stroke: "#f4c95d"},
    redact: {fill: "rgba(18,18,18,.42)", stroke: "#111111"},
    roi: {fill: "rgba(39,147,104,.16)", stroke: "#31a87a"},
    activeRoi: {fill: "rgba(255,196,68,.18)", stroke: "#f2bd3e"},
  };
  const HANDLE_RADIUS = 9;
  const MIN_SOURCE_SIZE = 10;

  function normalizeAngle(value) {
    let angle = Number(value || 0) % 360;
    if (angle > 180) angle -= 360;
    if (angle <= -180) angle += 360;
    return angle;
  }

  function rotatedCorners(rect) {
    const cx = (rect.x + rect.width / 2) * scaleX();
    const cy = (rect.y + rect.height / 2) * scaleY();
    const hw = rect.width * scaleX() / 2;
    const hh = rect.height * scaleY() / 2;
    const angle = normalizeAngle(rect.rotation) * Math.PI / 180;
    const cos = Math.cos(angle), sin = Math.sin(angle);
    return [[-hw,-hh],[hw,-hh],[hw,hh],[-hw,hh]].map(([x,y]) => ({
      x: cx + x * cos - y * sin,
      y: cy + x * sin + y * cos,
    }));
  }

  function mid(a, b) {
    return {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2};
  }

  function resizeHandles(rect) {
    const c = rotatedCorners(rect);
    return {
      nw: c[0], n: mid(c[0], c[1]), ne: c[1], e: mid(c[1], c[2]),
      se: c[2], s: mid(c[2], c[3]), sw: c[3], w: mid(c[3], c[0]),
    };
  }

  function rotationHandle(rect) {
    const c = rotatedCorners(rect);
    const top = mid(c[0], c[1]);
    const center = {
      x: (rect.x + rect.width / 2) * scaleX(),
      y: (rect.y + rect.height / 2) * scaleY(),
    };
    const dx = top.x - center.x, dy = top.y - center.y;
    const length = Math.hypot(dx, dy) || 1;
    return {x: top.x + dx / length * 28, y: top.y + dy / length * 28, top};
  }

  function pointInRect(point, rect) {
    const cx = (rect.x + rect.width / 2) * scaleX();
    const cy = (rect.y + rect.height / 2) * scaleY();
    const angle = -normalizeAngle(rect.rotation) * Math.PI / 180;
    const dx = point.x - cx, dy = point.y - cy;
    const lx = dx * Math.cos(angle) - dy * Math.sin(angle);
    const ly = dx * Math.sin(angle) + dy * Math.cos(angle);
    return Math.abs(lx) <= rect.width * scaleX() / 2 && Math.abs(ly) <= rect.height * scaleY() / 2;
  }

  function near(point, target, radius = HANDLE_RADIUS) {
    return Math.hypot(point.x - target.x, point.y - target.y) <= radius;
  }

  function handleHit(point, rect) {
    for (const [name, handle] of Object.entries(resizeHandles(rect))) {
      if (near(point, handle)) return name;
    }
    return null;
  }

  function cursorForHandle(handle) {
    if (["n", "s"].includes(handle)) return "ns-resize";
    if (["e", "w"].includes(handle)) return "ew-resize";
    if (["nw", "se"].includes(handle)) return "nwse-resize";
    return "nesw-resize";
  }

  function targetFor(kind, index, rect) {
    return {kind, index, rect};
  }

  function activeTarget() {
    if (state.mode === "crop" && state.cropEditable && state.crop) return targetFor("crop", -1, state.crop);
    if (state.mode === "roi" && state.activeRoiIndex >= 0 && state.rois[state.activeRoiIndex]) {
      return targetFor("roi", state.activeRoiIndex, state.rois[state.activeRoiIndex]);
    }
    if (state.mode === "redact" && state.activeRedactionIndex >= 0 && state.redactions[state.activeRedactionIndex]) {
      return targetFor("redact", state.activeRedactionIndex, state.redactions[state.activeRedactionIndex]);
    }
    return null;
  }

  function targetsInMode() {
    if (state.mode === "crop") return state.cropEditable && state.crop ? [targetFor("crop", -1, state.crop)] : [];
    if (state.mode === "roi") return state.rois.map((rect, index) => targetFor("roi", index, rect)).reverse();
    if (state.mode === "redact") return state.redactions.map((rect, index) => targetFor("redact", index, rect)).reverse();
    return [];
  }

  function hitTarget(point) {
    const active = activeTarget();
    if (active) {
      const resize = handleHit(point, active.rect);
      if (resize) return {...active, action: "resize", handle: resize};
      if (near(point, rotationHandle(active.rect), 12)) return {...active, action: "rotate"};
    }
    for (const target of targetsInMode()) {
      const resize = handleHit(point, target.rect);
      if (resize) return {...target, action: "resize", handle: resize};
      if (pointInRect(point, target.rect)) return {...target, action: "move"};
    }
    return null;
  }

  function selectTarget(target) {
    if (target.kind === "roi") state.activeRoiIndex = target.index;
    if (target.kind === "redact") state.activeRedactionIndex = target.index;
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

  function resizeRotatedRect(original, handle, point) {
    const center = {x: original.x + original.width / 2, y: original.y + original.height / 2};
    const source = toSource(point);
    const angle = normalizeAngle(original.rotation) * Math.PI / 180;
    const cos = Math.cos(angle), sin = Math.sin(angle);
    const dx = source.x - center.x, dy = source.y - center.y;
    const px = dx * cos + dy * sin;
    const py = -dx * sin + dy * cos;
    let left = -original.width / 2, right = original.width / 2;
    let top = -original.height / 2, bottom = original.height / 2;
    if (handle.includes("w")) left = Math.min(px, right - MIN_SOURCE_SIZE);
    if (handle.includes("e")) right = Math.max(px, left + MIN_SOURCE_SIZE);
    if (handle.includes("n")) top = Math.min(py, bottom - MIN_SOURCE_SIZE);
    if (handle.includes("s")) bottom = Math.max(py, top + MIN_SOURCE_SIZE);
    const localCenter = {x: (left + right) / 2, y: (top + bottom) / 2};
    const worldCenter = {
      x: center.x + localCenter.x * cos - localCenter.y * sin,
      y: center.y + localCenter.x * sin + localCenter.y * cos,
    };
    const width = right - left, height = bottom - top;
    return clampMovedRect({
      ...original,
      x: worldCenter.x - width / 2,
      y: worldCenter.y - height / 2,
      width,
      height,
    });
  }

  function drawPolygon(rect, fill, stroke, selected, label = "") {
    const c = rotatedCorners(rect);
    ctx.save();
    ctx.beginPath(); ctx.moveTo(c[0].x, c[0].y); c.slice(1).forEach(p => ctx.lineTo(p.x, p.y)); ctx.closePath();
    ctx.fillStyle = fill; ctx.fill();
    ctx.strokeStyle = stroke; ctx.lineWidth = selected ? 3 : 2; ctx.stroke();
    if (label) {
      ctx.font = "12px Segoe UI"; ctx.fillStyle = stroke; ctx.fillText(label, c[0].x + 4, c[0].y + 14);
    }
    if (selected) {
      for (const handle of Object.values(resizeHandles(rect))) {
        ctx.fillStyle = "#fff"; ctx.fillRect(handle.x - 4, handle.y - 4, 8, 8);
        ctx.strokeStyle = stroke; ctx.strokeRect(handle.x - 4, handle.y - 4, 8, 8);
      }
      const rotate = rotationHandle(rect);
      ctx.beginPath(); ctx.moveTo(rotate.top.x, rotate.top.y); ctx.lineTo(rotate.x, rotate.y); ctx.stroke();
      ctx.beginPath(); ctx.arc(rotate.x, rotate.y, 7, 0, Math.PI * 2);
      ctx.fillStyle = "#fff"; ctx.fill(); ctx.stroke();
    }
    ctx.restore();
  }

  function drawDraft() {
    if (!state.drawing) return;
    const rect = normalizedRect(state.drawing.start, state.drawing.end);
    const color = state.mode === "redact" ? COLORS.redact : COLORS.crop;
    drawDisplayOverlay(rect, color.fill, color.stroke, "");
  }

  function unifiedDraw() {
    if (!state.sourceImage) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(activeImageSource(), 0, 0, canvas.width, canvas.height);

    if (state.crop) {
      const c = rotatedCorners(state.crop);
      ctx.save();
      ctx.fillStyle = "rgba(0,0,0,.42)";
      ctx.beginPath(); ctx.rect(0, 0, canvas.width, canvas.height);
      ctx.moveTo(c[0].x, c[0].y); c.slice(1).forEach(p => ctx.lineTo(p.x, p.y)); ctx.closePath();
      ctx.fill("evenodd"); ctx.restore();
      drawPolygon(state.crop, "rgba(244,201,93,.10)", COLORS.crop.stroke, state.cropEditable && state.mode === "crop", "裁剪");
    }

    state.redactions.forEach((rect, index) => {
      const selected = state.mode === "redact" && state.activeRedactionIndex === index;
      drawPolygon(rect, COLORS.redact.fill, COLORS.redact.stroke, selected, "");
    });

    state.rois.forEach((roi, index) => {
      const selected = state.mode === "roi" && state.activeRoiIndex === index;
      const editing = state.unifiedTransformGesture?.target.kind === "roi" && state.unifiedTransformGesture.target.index === index;
      const color = editing ? COLORS.activeRoi : COLORS.roi;
      drawPolygon(roi, color.fill, color.stroke, selected, roi.label);
    });

    if (state.drawing) {
      if (state.mode === "roi") {
        const rect = normalizedRect(state.drawing.start, state.drawing.end);
        drawDisplayOverlay(rect, COLORS.activeRoi.fill, COLORS.activeRoi.stroke, "");
      } else {
        drawDraft();
      }
    }
    updateSaveAction();
  }
  draw = unifiedDraw;

  function updateHelp(target = activeTarget()) {
    if (!state.sourceImage || !target) return;
    const name = target.kind === "crop" ? "裁剪框" : target.kind === "roi" ? "ROI" : "遮盖";
    const base = $("#editor-help").textContent.split(" 当前")[0];
    $("#editor-help").textContent = `${base} 当前${name}：拖动框内部平移，拖动方形控制点调整大小，拖动圆形手柄旋转。`;
  }

  function hoverCursor(point) {
    const hit = hitTarget(point);
    if (!hit) return "default";
    if (hit.action === "resize") return cursorForHandle(hit.handle);
    if (hit.action === "rotate") return "grab";
    return "move";
  }

  document.addEventListener("pointerdown", event => {
    if (event.target !== canvas || !state.sourceImage) return;
    const point = canvasPoint(event);
    const hit = hitTarget(point);
    if (!hit) {
      canvas.style.cursor = BLACK_CROSSHAIR_CURSOR;
      return;
    }
    selectTarget(hit);
    const rect = hit.kind === "crop" ? state.crop : hit.kind === "roi" ? state.rois[hit.index] : state.redactions[hit.index];
    const center = {
      x: (rect.x + rect.width / 2) * scaleX(),
      y: (rect.y + rect.height / 2) * scaleY(),
    };
    state.unifiedTransformGesture = {
      action: hit.action,
      handle: hit.handle || null,
      target: {kind: hit.kind, index: hit.index},
      original: {...rect},
      startSource: toSource(point),
      startPointerAngle: Math.atan2(point.y - center.y, point.x - center.x),
    };
    canvas.setPointerCapture(event.pointerId);
    canvas.style.cursor = hit.action === "resize" ? cursorForHandle(hit.handle) : hit.action === "rotate" ? "grabbing" : "move";
    updateHelp(hit); draw();
    event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation();
  }, true);

  document.addEventListener("pointermove", event => {
    if (event.target !== canvas || !state.sourceImage) return;
    const point = canvasPoint(event);
    const gesture = state.unifiedTransformGesture;
    if (gesture) {
      const target = gesture.target;
      if (gesture.action === "move") {
        const current = toSource(point);
        const dx = current.x - gesture.startSource.x, dy = current.y - gesture.startSource.y;
        setTargetRect(target, clampMovedRect({...gesture.original, x: gesture.original.x + dx, y: gesture.original.y + dy}));
        canvas.style.cursor = "move";
      } else if (gesture.action === "rotate") {
        const center = {
          x: (gesture.original.x + gesture.original.width / 2) * scaleX(),
          y: (gesture.original.y + gesture.original.height / 2) * scaleY(),
        };
        const angle = Math.atan2(point.y - center.y, point.x - center.x);
        const delta = (angle - gesture.startPointerAngle) * 180 / Math.PI;
        setTargetRect(target, {...gesture.original, rotation: normalizeAngle((gesture.original.rotation || 0) + delta)});
        canvas.style.cursor = "grabbing";
      } else {
        setTargetRect(target, resizeRotatedRect(gesture.original, gesture.handle, point));
        canvas.style.cursor = cursorForHandle(gesture.handle);
      }
      draw();
      event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation();
      return;
    }
    if (state.drawing) {
      state.drawing.end = point;
      canvas.style.cursor = BLACK_CROSSHAIR_CURSOR;
      draw();
      event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation();
      return;
    }
    canvas.style.cursor = hoverCursor(point);
    event.stopPropagation(); event.stopImmediatePropagation();
  }, true);

  const finishTransform = event => {
    if (event.target !== canvas || !state.unifiedTransformGesture) return;
    state.unifiedTransformGesture = null;
    canvas.style.cursor = "default";
    draw(); updateHelp();
    event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation();
  };
  document.addEventListener("pointerup", finishTransform, true);
  document.addEventListener("pointercancel", finishTransform, true);

  canvas.addEventListener("pointerup", () => {
    if (state.unifiedTransformGesture) return;
    canvas.style.cursor = "default";
    if (state.mode === "redact" && state.redactions.length) state.activeRedactionIndex = state.redactions.length - 1;
    requestAnimationFrame(() => { draw(); updateHelp(); });
  });

  $$('[data-mode]').forEach(button => button.addEventListener("click", () => {
    state.unifiedTransformGesture = null;
    canvas.style.cursor = "default";
    requestAnimationFrame(() => { draw(); updateHelp(); });
  }));

  const originalClearEditor = clearEditor;
  clearEditor = () => {
    state.unifiedTransformGesture = null;
    canvas.style.cursor = "default";
    originalClearEditor();
  };

  state.unifiedTransformGesture = null;
  canvas.style.cursor = "default";
  draw();
})();
