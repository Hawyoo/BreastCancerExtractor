(() => {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const port = params.get("bce_control_port");
  const token = params.get("bce_shutdown_token");
  if (!port || !token) return;

  function showClosedPage() {
    document.title = "Breast Cancer Extractor 已关闭";
    document.body.innerHTML = `
      <main style="font-family:Segoe UI,Arial,sans-serif;max-width:720px;margin:12vh auto;padding:32px">
        <h1>Breast Cancer Extractor 已关闭</h1>
        <p>本程序启动的 OCR / Ollama 相关进程正在退出。</p>
        <p>如果此浏览器标签页没有自动关闭，这是浏览器的安全限制，可以直接关闭本页。</p>
      </main>`;
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
        const response = await fetch(
          `http://127.0.0.1:${encodeURIComponent(port)}/shutdown?token=${encodeURIComponent(token)}`,
          {method: "POST", cache: "no-store"},
        );
        if (!response.ok) throw new Error(`关闭请求失败 (${response.status})`);
        showClosedPage();
        setTimeout(() => {
          try {
            window.open("", "_self");
            window.close();
          } catch (_) {}
        }, 120);
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
