/* Document types and ROI options come from knowledge/schema/document_roi_mapping.yaml. */
(() => {
  if (typeof roiTypesByDocument === "undefined" || typeof updateRoiTypeOptions !== "function") return;

  async function loadDocumentRoiCatalog() {
    const response = await fetch("/api/knowledge/document-types");
    if (!response.ok) throw new Error(`无法读取文档字段配置 (${response.status})`);
    const payload = await response.json();
    const documents = [...(payload.documents || [])].sort((left, right) => {
      if (left.key === "OTHER") return -1;
      if (right.key === "OTHER") return 1;
      return 0;
    });
    const configuredTypes = {};
    for (const document of documents) {
      documentTypeLabels[document.key] = document.label;
      const options = (document.regions || []).map(region => [region.key, region.label]);
      if (!options.some(([key]) => key === "OTHER")) options.push(["OTHER", "其他信息"]);
      configuredTypes[document.key] = options;
    }
    for (const key of Object.keys(roiTypesByDocument)) delete roiTypesByDocument[key];
    Object.assign(roiTypesByDocument, configuredTypes);

    const selector = document.querySelector("#document-type");
    const selected = selector.value;
    selector.innerHTML = documents
      .map(document => `<option value="${document.key}">${document.label}</option>`)
      .join("");
    selector.value = configuredTypes[selected] ? selected : "OTHER";
    updateRoiTypeOptions();
  }

  loadDocumentRoiCatalog().catch(error => console.error(error));
})();
