(() => {
  // This module is loaded after enhancements.js/derived_fields.js. Keep the
  // text-positioning, patient-browser, quick-import and post-review UI follow-ups independent
  // of whether Windows shutdown control is available (e.g. Docker gets the same behavior).
  function loadRoiGreen() {
    if (document.querySelector('script[data-bce-roi-green="1"]')) return;
    const greenScript = document.createElement("script");
    greenScript.src = "/roi_green.js";
    greenScript.async = false;
    greenScript.dataset.bceRoiGreen = "1";
    document.body.appendChild(greenScript);
  }

  const existingEditorScript = document.querySelector('script[data-bce-editor-interactions="1"]');
  if (!existingEditorScript) {
    const editorScript = document.createElement("script");
    editorScript.src = "/editor_interactions.js";
    editorScript.async = false;
    editorScript.dataset.bceEditorInteractions = "1";
    editorScript.onload = loadRoiGreen;
    document.body.appendChild(editorScript);
  } else if (typeof state !== "undefined" && "unifiedTransformGesture" in state) {
    loadRoiGreen();
  } else {
    existingEditorScript.addEventListener("load", loadRoiGreen, {once: true});
  }

  if (!document.querySelector('script[data-bce-atomic-roi="1"]')) {
    const roiScript = document.createElement("script");
    roiScript.src = "/atomic_roi.js";
    roiScript.async = false;
    roiScript.dataset.bceAtomicRoi = "1";
    document.body.appendChild(roiScript);
  }

  function loadQuickImport() {
    if (document.querySelector('script[data-bce-quick-import="1"]')) return;
    const quickImportScript = document.createElement("script");
    quickImportScript.src = "/quick_import.js";
    quickImportScript.async = false;
    quickImportScript.dataset.bceQuickImport = "1";
    quickImportScript.onload = () => {
      // app.js originally assigns the exit button a direct function reference.
      // Rebind it after quick_import.js wraps leavePatient so an active batch
      // cannot be abandoned without the quick-import cancellation guard.
      const exitButton = document.querySelector("#exit-patient");
      if (exitButton && typeof leavePatient === "function") exitButton.onclick = leavePatient;
    };
    document.body.appendChild(quickImportScript);
  }

  if (!document.querySelector('script[data-bce-patient-sort="1"]')) {
    const patientSortScript = document.createElement("script");
    patientSortScript.src = "/patient_sort.js";
    patientSortScript.async = false;
    patientSortScript.dataset.bcePatientSort = "1";
    patientSortScript.onload = loadQuickImport;
    patientSortScript.onerror = loadQuickImport;
    document.body.appendChild(patientSortScript);
  } else {
    loadQuickImport();
  }

  function loadFieldValidation() {
    if (document.querySelector('script[data-bce-field-validation="1"]')) return;
    const validationScript = document.createElement("script");
    validationScript.src = "/field_validation.js";
    validationScript.async = false;
    validationScript.dataset.bceFieldValidation = "1";
    document.body.appendChild(validationScript);
  }

  if (!document.querySelector('script[data-bce-review-inline="1"]')) {
    const reviewScript = document.createElement("script");
    reviewScript.src = "/review_inline.js";
    reviewScript.async = false;
    reviewScript.dataset.bceReviewInline = "1";
    reviewScript.onload = loadFieldValidation;
    document.body.appendChild(reviewScript);
  } else {
    loadFieldValidation();
  }

  function loadTextLearning() {
    if (document.querySelector('script[data-bce-text-learning="1"]')) return;
    const learningScript = document.createElement("script");
    learningScript.src = "/text_learning.js";
    learningScript.async = false;
    learningScript.dataset.bceTextLearning = "1";
    document.body.appendChild(learningScript);
  }

  loadTextLearning();

  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const token = params.get("bce_shutdown_token");
  if (!token) return;

  function showClosingPage() {
    document.title = "Breast Cancer Extractor 正在关闭";
    document.body.innerHTML = `
      <main style="font-family:Segoe UI,Arial,sans-serif;max-width:720px;margin:12vh auto;padding:32px">
        <h1>Breast Cancer Extractor 正在关闭</h1>
        <p>关闭指令已由本地主程序确认，正在停止 OCR / Ollama 并清理子进程。</p>
        <p>Windows EXE 控制台会在清理完成后自动退出；如果浏览器标签页没有自动关闭，可以直接关闭本页。</p>
      </main>`;
  }

  async function submitShutdownRequest() {
    // The Windows native entrypoint exposes this route on the same FastAPI
    // origin. It is therefore allowed by the strict `connect-src 'self'` CSP,
    // and no popup/cross-port form workaround is needed.
    const response = await fetch(
      `/api/native/shutdown?token=${encodeURIComponent(token)}`,
      {method: "POST", cache: "no-store", credentials: "same-origin"},
    );
    if (!response.ok) throw new Error(`关闭请求失败 (${response.status})`);
    const payload = await response.json();
    if (payload?.status !== "shutting_down") throw new Error("关闭控制端返回了无效状态");
    showClosingPage();
    setTimeout(() => {
      try {
        window.open("", "_self");
        window.close();
      } catch (_) {}
    }, 1200);
  }

  function installShutdownButton() {
    const actions = document.querySelector(".topbar-actions");
    if (!actions || document.querySelector("#shutdown-bce")) return;
    const button = document.createElement("button");
    button.id = "shutdown-bce";
    button.type = "button";
    button.className = "danger-tool";
    button.textContent = "关闭程序";
    button.title = "关闭 BCE 及其启动的 OCR / Ollama；不会关闭你原本已启动的系统 Ollama";
    actions.insertBefore(button, document.querySelector("#service-status"));

    button.onclick = async () => {
      button.disabled = true;
      button.textContent = "正在关闭…";
      try {
        await submitShutdownRequest();
      } catch (error) {
        button.disabled = false;
        button.textContent = "关闭程序";
        if (typeof toast === "function") toast(`关闭失败：${error.message}`);
        else alert(`关闭失败：${error.message}`);
      }
    };
  }

  installShutdownButton();
})();
