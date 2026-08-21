/* BCE text-learning import/export controls.
 * The backend owns the actual learning profile: reviewed field examples,
 * correction patterns, OCR evidence text and traceable OCR locations.
 */
(() => {
  const MAX_IMPORT_BYTES = 20 * 1024 * 1024;

  function removeLegacyLearningUi() {
    document.querySelector("#improve-learning")?.remove();
    document.querySelector("#learning-summary-dialog")?.remove();
  }

  function downloadJson(payload) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], {type: "application/json;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
    anchor.href = url;
    anchor.download = `BCE_text_learning_v3_${stamp}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function ensureExportButton() {
    let button = document.querySelector("#export-text-learning");
    if (button) {
      button.textContent = "导出学习JSON";
      button.title = "导出字段填写方法、人工纠正样例和OCR文本定位证据";
      return button;
    }
    const actions = document.querySelector(".patient-browser-actions");
    if (!actions) return null;
    button = document.createElement("button");
    button.id = "export-text-learning";
    button.type = "button";
    button.className = "tool";
    button.textContent = "导出学习JSON";
    button.title = "导出字段填写方法、人工纠正样例和OCR文本定位证据";
    const reference = document.querySelector("#scan-patient-packages");
    actions.insertBefore(button, reference || null);
    return button;
  }

  async function loadLearningStatus() {
    const status = document.querySelector("#text-learning-status");
    try {
      const payload = await api("/api/text-learning");
      const imported = payload.imported || {};
      if (status) {
        const totalExamples = Number(payload.example_count || 0);
        const importedPackages = Number(imported.source_count || 0);
        status.textContent = `学习样例：${totalExamples} 条 · 长期导入：${importedPackages} 包`;
        status.title = `学习文件保存在 ${imported.storage || "database/learning/"}；定位坐标随JSON导出用于追溯`;
      }
      return payload;
    } catch (error) {
      if (status) status.textContent = "学习状态读取失败";
      throw error;
    }
  }

  function ensureControls() {
    removeLegacyLearningUi();
    const exportButton = ensureExportButton();
    if (!exportButton) return;

    let importButton = document.querySelector("#import-text-learning");
    let input = document.querySelector("#import-text-learning-file");
    let status = document.querySelector("#text-learning-status");

    if (!importButton) {
      importButton = document.createElement("button");
      importButton.id = "import-text-learning";
      importButton.type = "button";
      importButton.className = "tool";
      importButton.textContent = "导入学习JSON";
      importButton.title = "导入其他 BCE 导出的字段学习样例，并长期用于后续AI提取";
      exportButton.insertAdjacentElement("afterend", importButton);
    }

    if (!input) {
      input = document.createElement("input");
      input.id = "import-text-learning-file";
      input.type = "file";
      input.accept = ".json,application/json";
      input.hidden = true;
      importButton.insertAdjacentElement("afterend", input);
    }

    if (!status) {
      status = document.createElement("small");
      status.id = "text-learning-status";
      status.className = "text-learning-status";
      status.textContent = "学习样例：读取中…";
      input.insertAdjacentElement("afterend", status);
    }

    importButton.onclick = () => {
      input.value = "";
      input.click();
    };

    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      if (file.size > MAX_IMPORT_BYTES) {
        toast("学习JSON超过20MB，未导入");
        return;
      }
      importButton.disabled = true;
      const originalText = importButton.textContent;
      importButton.textContent = "正在导入…";
      try {
        const raw = await file.text();
        let profile;
        try {
          profile = JSON.parse(raw);
        } catch (_) {
          throw new Error("文件不是有效JSON");
        }
        const result = await api("/api/text-learning/import", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({source_name: file.name, profile}),
        });
        if (result.duplicate) {
          toast("这份学习记录已经导入过，没有重复增加权重");
        } else {
          const skipped = Number(result.skipped_fields || 0) + Number(result.skipped_entries || 0);
          const examples = Number(result.imported_example_count || 0);
          toast(`学习记录已导入：${result.imported_field_count || 0} 个字段 · ${examples} 条证据样例${skipped ? ` · 跳过 ${skipped} 项无效内容` : ""}`);
        }
        await loadLearningStatus();
      } catch (error) {
        toast(`导入学习失败：${error.message}`);
      } finally {
        importButton.disabled = false;
        importButton.textContent = originalText;
      }
    };

    exportButton.onclick = async () => {
      const originalText = exportButton.textContent;
      exportButton.disabled = true;
      exportButton.textContent = "正在整理…";
      try {
        const payload = await loadLearningStatus();
        downloadJson(payload);
        toast(`学习JSON已导出：${payload.field_count || 0} 个字段 · ${payload.example_count || 0} 条人工审核证据样例`);
      } catch (error) {
        toast(`导出文本学习失败：${error.message}`);
      } finally {
        exportButton.disabled = false;
        exportButton.textContent = originalText;
      }
    };

    if (!status.dataset.loaded) {
      status.dataset.loaded = "1";
      loadLearningStatus().catch(() => {});
    }
  }

  const observer = new MutationObserver(() => ensureControls());
  observer.observe(document.body, {childList: true, subtree: true});
  ensureControls();
})();
