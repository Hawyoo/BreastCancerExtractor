/* Portable text-learning import/export layer.
 * Imported learning is persisted by the backend under database/learning/ and
 * automatically merged into future extraction prompts.
 */
(() => {
  const MAX_IMPORT_BYTES = 5 * 1024 * 1024;

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

  async function loadLearningStatus() {
    const status = document.querySelector("#text-learning-status");
    try {
      const payload = await api("/api/text-learning");
      const imported = payload.imported || {};
      if (status) {
        status.textContent = imported.source_count
          ? `长期学习：${imported.source_count} 个导入包 · ${imported.field_count || 0} 个字段`
          : "长期学习：尚未导入学习包";
        status.title = `学习文件保存在 ${imported.storage || "database/learning/"}`;
      }
      return payload;
    } catch (error) {
      if (status) status.textContent = "长期学习状态读取失败";
      throw error;
    }
  }

  function ensureControls() {
    const exportButton = document.querySelector("#export-text-learning");
    if (!exportButton || document.querySelector("#import-text-learning")) return;

    const importButton = document.createElement("button");
    importButton.id = "import-text-learning";
    importButton.type = "button";
    importButton.className = "tool";
    importButton.textContent = "导入学习JSON";
    importButton.title = "导入其他 BCE 导出的文本学习记录，并长期用于后续AI提取";

    const input = document.createElement("input");
    input.id = "import-text-learning-file";
    input.type = "file";
    input.accept = ".json,application/json";
    input.hidden = true;

    const status = document.createElement("small");
    status.id = "text-learning-status";
    status.className = "text-learning-status";
    status.textContent = "长期学习：读取中…";

    exportButton.insertAdjacentElement("afterend", importButton);
    importButton.insertAdjacentElement("afterend", input);
    input.insertAdjacentElement("afterend", status);

    importButton.onclick = () => {
      input.value = "";
      input.click();
    };

    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      if (file.size > MAX_IMPORT_BYTES) {
        toast("学习JSON超过5MB，未导入");
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
          toast(`学习记录已导入：${result.imported_field_count || 0} 个字段${skipped ? `，跳过 ${skipped} 项无效内容` : ""}`);
        }
        await loadLearningStatus();
      } catch (error) {
        toast(`导入学习失败：${error.message}`);
      } finally {
        importButton.disabled = false;
        importButton.textContent = originalText;
      }
    };

    // Export the backend-combined profile, not only the current browser/database
    // corrections. This keeps imported long-term learning portable across machines.
    exportButton.onclick = async () => {
      const originalText = exportButton.textContent;
      exportButton.disabled = true;
      exportButton.textContent = "正在整理…";
      try {
        const payload = await loadLearningStatus();
        downloadJson(payload);
        toast(`学习JSON已导出：${payload.field_count || 0} 个字段，含 ${payload.imported_source_count || 0} 个导入学习包`);
      } catch (error) {
        toast(`导出文本学习失败：${error.message}`);
      } finally {
        exportButton.disabled = false;
        exportButton.textContent = originalText;
      }
    };

    loadLearningStatus().catch(() => {});
  }

  const observer = new MutationObserver(() => ensureControls());
  observer.observe(document.body, {childList: true, subtree: true});
  ensureControls();
})();
