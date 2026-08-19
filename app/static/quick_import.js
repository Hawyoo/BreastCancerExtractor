(() => {
  const PATIENT_CODE_PATTERN = /^\d{7}$/;
  const IMAGE_EXTENSION_PATTERN = /\.(png|jpe?g|webp|bmp|gif|tiff?)$/i;
  const session = {
    groups: [],
    index: -1,
    active: false,
    advancing: false,
    createdCount: 0,
    existingCount: 0,
    imageCount: 0,
  };

  function isImageFile(file) {
    return Boolean(file && ((file.type || "").startsWith("image/") || IMAGE_EXTENSION_PATTERN.test(file.name || "")));
  }

  function patientCodeFromPath(path) {
    const parts = String(path || "").split(/[\\/]+/).filter(Boolean);
    return parts.slice(0, -1).find(part => PATIENT_CODE_PATTERN.test(part)) || null;
  }

  function installStyle() {
    if (document.querySelector("#quick-import-style")) return;
    const style = document.createElement("style");
    style.id = "quick-import-style";
    style.textContent = `
      .quick-import-panel{margin:8px 0 10px;padding:10px;border:1px solid var(--line,#d9dee7);border-radius:10px;background:var(--paper,#f6f4ef)}
      .quick-import-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:5px}
      .quick-import-heading strong{font-size:12px}
      .quick-import-heading small,.quick-import-note,.quick-import-status{font-size:10px;color:var(--muted,#66736d);line-height:1.45}
      .quick-import-actions{display:flex;gap:6px;align-items:center;margin-top:7px}
      .quick-import-actions .file-button,.quick-import-actions .tool{flex:1;justify-content:center;text-align:center}
      .quick-import-drop{margin-top:7px;padding:10px;border:1px dashed var(--line,#b8c1c9);border-radius:8px;text-align:center;font-size:10px;color:var(--muted,#66736d);cursor:pointer}
      .quick-import-drop.dragover{outline:2px solid var(--green-dark,#174737);outline-offset:-2px;background:var(--mint,#eef5f1)}
      .quick-import-status{margin-top:6px;white-space:pre-wrap}
    `;
    document.head.appendChild(style);
  }

  function updateStatus(message = "") {
    const status = document.querySelector("#quick-import-status");
    const cancel = document.querySelector("#quick-import-cancel");
    if (status) status.textContent = message;
    if (cancel) cancel.hidden = !session.active;
  }

  function ensureUi() {
    const browser = document.querySelector("#patient-browser");
    const form = document.querySelector("#patient-form");
    if (!browser || !form || document.querySelector("#quick-import-panel")) return;
    installStyle();
    const panel = document.createElement("section");
    panel.id = "quick-import-panel";
    panel.className = "quick-import-panel";
    panel.innerHTML = `
      <div class="quick-import-heading"><strong>快速导入</strong><small>文件夹名 = 7位病案号</small></div>
      <div class="quick-import-note">每个患者的全部图片放在以病案号命名的文件夹内。可选择一个患者文件夹，也可选择包含多个患者文件夹的父目录；还可一次拖入多个患者文件夹。</div>
      <div class="quick-import-actions">
        <label class="file-button secondary-file-button">选择患者文件夹 / 父目录
          <input id="quick-import-folders" type="file" accept="image/*" webkitdirectory multiple hidden>
        </label>
        <button id="quick-import-cancel" class="tool" type="button" hidden>取消本次快速导入</button>
      </div>
      <div id="quick-import-drop" class="quick-import-drop" tabindex="0">也可以一次拖入多个患者文件夹</div>
      <div id="quick-import-status" class="quick-import-status">尚未选择文件夹</div>
    `;
    form.insertAdjacentElement("afterend", panel);

    const input = panel.querySelector("#quick-import-folders");
    input.addEventListener("change", async event => {
      const entries = [...event.target.files]
        .filter(isImageFile)
        .map(file => ({file, relativePath: file.webkitRelativePath || file.name}));
      event.target.value = "";
      await beginQuickImport(entries);
    });

    const drop = panel.querySelector("#quick-import-drop");
    ["dragenter", "dragover"].forEach(name => drop.addEventListener(name, event => {
      event.preventDefault();
      drop.classList.add("dragover");
    }));
    ["dragleave", "drop"].forEach(name => drop.addEventListener(name, event => {
      event.preventDefault();
      drop.classList.remove("dragover");
    }));
    drop.addEventListener("drop", async event => {
      try {
        const entries = await entriesFromDataTransfer(event.dataTransfer);
        await beginQuickImport(entries);
      } catch (error) {
        toast(`快速导入失败：${error.message}`);
      }
    });

    panel.querySelector("#quick-import-cancel").onclick = () => {
      if (!session.active) return;
      if (!confirm("取消本次快速导入？当前患者尚未确认的原图队列会被清空；已自动创建的患者不会被删除。")) return;
      session.active = false;
      session.groups = [];
      session.index = -1;
      clearRawQueue();
      updateStatus("本次快速导入已取消；已创建的患者保留。\n原始图片未上传到服务器。");
    };
  }

  async function readDirectoryEntry(directoryEntry, prefix = directoryEntry.name) {
    const reader = directoryEntry.createReader();
    const children = [];
    while (true) {
      const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
      if (!batch.length) break;
      children.push(...batch);
    }
    const result = [];
    for (const entry of children) {
      const path = `${prefix}/${entry.name}`;
      if (entry.isDirectory) {
        result.push(...await readDirectoryEntry(entry, path));
      } else if (entry.isFile) {
        const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
        if (isImageFile(file)) result.push({file, relativePath: path});
      }
    }
    return result;
  }

  async function entriesFromDataTransfer(dataTransfer) {
    const items = [...(dataTransfer?.items || [])];
    const result = [];
    if (items.length && items.some(item => typeof item.webkitGetAsEntry === "function")) {
      for (const item of items) {
        const entry = item.webkitGetAsEntry?.();
        if (!entry) continue;
        if (entry.isDirectory) result.push(...await readDirectoryEntry(entry));
        else if (entry.isFile) {
          const file = item.getAsFile();
          if (isImageFile(file)) result.push({file, relativePath: file.name});
        }
      }
      return result;
    }
    return [...(dataTransfer?.files || [])]
      .filter(isImageFile)
      .map(file => ({file, relativePath: file.webkitRelativePath || file.name}));
  }

  function groupEntriesByPatient(entries) {
    const groups = new Map();
    const rejected = [];
    for (const entry of entries) {
      if (!isImageFile(entry.file)) continue;
      const code = patientCodeFromPath(entry.relativePath);
      if (!code) {
        rejected.push(entry.relativePath || entry.file.name);
        continue;
      }
      if (!groups.has(code)) groups.set(code, []);
      groups.get(code).push(entry);
    }
    return {
      groups: [...groups.entries()].map(([patientCode, files]) => ({patientCode, files})),
      rejected,
    };
  }

  async function ensurePatients(groups) {
    await loadPatients();
    const byCode = new Map(state.patients.map(patient => [patient.patient_code, patient]));
    let createdCount = 0;
    let existingCount = 0;
    const prepared = [];
    for (const group of groups.sort((a, b) => a.patientCode.localeCompare(b.patientCode, "zh-CN", {numeric: true}))) {
      let patient = byCode.get(group.patientCode);
      if (!patient) {
        try {
          patient = await api("/api/patients", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({patient_code: group.patientCode}),
          });
          createdCount += 1;
          byCode.set(group.patientCode, patient);
        } catch (error) {
          await loadPatients();
          patient = state.patients.find(item => item.patient_code === group.patientCode);
          if (!patient) throw error;
          existingCount += 1;
        }
      } else {
        existingCount += 1;
      }
      prepared.push({...group, patientId: patient.id});
    }
    await loadPatients();
    return {prepared, createdCount, existingCount};
  }

  function queueFilesForCurrentPatient(group) {
    if (!state.patient || state.patient.id !== group.patientId) throw new Error("患者切换失败，无法建立原图队列");
    state.rawQueuePatientId = state.patient.id;
    const files = [...group.files].sort((left, right) =>
      String(left.relativePath || left.file.name).localeCompare(String(right.relativePath || right.file.name), "zh-CN", {numeric: true})
    );
    for (const entry of files) {
      const documentType = guessDocumentType(entry.file.name);
      const label = documentTypeLabels[documentType] || "文档";
      const queuedSameType = state.rawQueue.filter(item => item.documentType === documentType).length;
      const savedSameType = (state.patient.documents || []).filter(doc => doc.document_type === documentType).length;
      const sequence = queuedSameType + savedSameType + 1;
      state.rawQueue.push({
        id: crypto.randomUUID(),
        file: entry.file,
        localName: entry.relativePath || entry.file.name,
        status: "WAITING",
        documentType,
        displayName: `${label}-第${sequence}页`,
        autoDisplayName: true,
        crop: null,
        cropEditable: false,
        redactions: [],
        rois: [],
      });
    }
    renderRawQueue();
    const first = state.rawQueue.findIndex(item => item.status === "WAITING");
    if (first >= 0 && (state.activeRawIndex < 0 || !state.sourceImage)) {
      loadRawItem(first).catch(error => toast(error.message));
    }
  }

  async function activateGroup(index) {
    if (!session.active || index < 0 || index >= session.groups.length) return;
    session.advancing = true;
    try {
      const group = session.groups[index];
      session.index = index;
      clearRawQueue();
      await selectPatient(group.patientId);
      queueFilesForCurrentPatient(group);
      const remainingPatients = session.groups.length - index;
      updateStatus(
        `快速导入进行中：患者 ${group.patientCode}（${index + 1}/${session.groups.length}）\n` +
        `当前 ${group.files.length} 张待确认；剩余 ${remainingPatients} 个患者批次。` +
        ` 原图仍只保留在浏览器会话中。`
      );
    } finally {
      session.advancing = false;
    }
  }

  async function maybeAdvance() {
    if (!session.active || session.advancing || session.index < 0) return;
    if (!state.rawQueue.length) return;
    if (state.rawQueue.some(item => item.status !== "SAVED")) return;
    const nextIndex = session.index + 1;
    if (nextIndex < session.groups.length) {
      await activateGroup(nextIndex);
      return;
    }
    session.active = false;
    updateStatus(
      `快速导入已完成：${session.groups.length} 个患者，${session.imageCount} 张初始图片；` +
      `新建 ${session.createdCount} 个患者，复用 ${session.existingCount} 个已有患者。\n` +
      `所有原图均经过逐张确认脱敏后才保存。`
    );
  }

  async function beginQuickImport(entries) {
    if (session.active) {
      toast("已有快速导入正在进行，请先完成或取消");
      return;
    }
    const currentPending = state.rawQueue?.some(item => item.file && item.status !== "SAVED");
    if (currentPending) {
      toast("当前患者仍有未确认原图，请先处理完或退出当前患者后再快速导入");
      return;
    }
    const {groups, rejected} = groupEntriesByPatient(entries);
    if (!groups.length) {
      updateStatus("未发现有效患者文件夹。文件夹名必须为7位病案号，例如 1234567。\n可直接选择患者文件夹，或选择包含多个患者文件夹的父目录。");
      return;
    }
    const imageCount = groups.reduce((sum, group) => sum + group.files.length, 0);
    updateStatus(`正在准备 ${groups.length} 个患者、${imageCount} 张图片…`);
    try {
      const {prepared, createdCount, existingCount} = await ensurePatients(groups);
      session.groups = prepared;
      session.index = -1;
      session.active = true;
      session.createdCount = createdCount;
      session.existingCount = existingCount;
      session.imageCount = imageCount;
      if (rejected.length) {
        toast(`已忽略 ${rejected.length} 张无法从路径识别7位病案号的图片`);
      }
      await activateGroup(0);
    } catch (error) {
      session.active = false;
      session.groups = [];
      updateStatus(`快速导入失败：${error.message}`);
      toast(`快速导入失败：${error.message}`);
    }
  }

  ensureUi();
  const rawQueue = document.querySelector("#raw-queue");
  if (rawQueue) {
    new MutationObserver(() => {
      queueMicrotask(() => maybeAdvance().catch(error => toast(`快速导入切换患者失败：${error.message}`)));
    }).observe(rawQueue, {childList: true, subtree: true, characterData: true});
  }
})();
