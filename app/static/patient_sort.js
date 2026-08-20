(() => {
  const STORAGE_KEY = "bce-patient-browser-sort";
  const DEFAULT_SORT = "updated_desc";
  const SORT_OPTIONS = [
    ["id_asc", "患者ID：小 → 大"],
    ["id_desc", "患者ID：大 → 小"],
    ["created_desc", "添加时间：新 → 旧"],
    ["created_asc", "添加时间：旧 → 新"],
    ["updated_desc", "修改时间：新 → 旧"],
    ["updated_asc", "修改时间：旧 → 新"],
  ];
  const COLLATOR = new Intl.Collator("zh-CN", {numeric: true, sensitivity: "base"});

  function currentSortMode() {
    const value = localStorage.getItem(STORAGE_KEY) || DEFAULT_SORT;
    return SORT_OPTIONS.some(([key]) => key === value) ? value : DEFAULT_SORT;
  }

  function timestamp(value) {
    const parsed = Date.parse(String(value || ""));
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function comparePatientIds(left, right) {
    return COLLATOR.compare(String(left.patient_code || ""), String(right.patient_code || ""));
  }

  function comparePatients(left, right, mode = currentSortMode()) {
    let result = 0;
    if (mode === "id_asc") result = comparePatientIds(left, right);
    else if (mode === "id_desc") result = comparePatientIds(right, left);
    else if (mode === "created_asc") result = timestamp(left.created_at) - timestamp(right.created_at);
    else if (mode === "created_desc") result = timestamp(right.created_at) - timestamp(left.created_at);
    else if (mode === "updated_asc") result = timestamp(left.updated_at) - timestamp(right.updated_at);
    else result = timestamp(right.updated_at) - timestamp(left.updated_at);
    return result || comparePatientIds(left, right);
  }

  function formatDateTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date).replace(/\//g, "-");
  }

  function installStyles() {
    if (document.querySelector("#patient-sort-style")) return;
    const style = document.createElement("style");
    style.id = "patient-sort-style";
    style.textContent = `
      .patient-sort-toolbar{display:flex;align-items:center;gap:8px;margin:10px 0 8px;padding:8px 9px;border:1px solid var(--line,#d9dee7);border-radius:9px;background:var(--paper,#f6f4ef)}
      .patient-sort-toolbar label{display:flex;align-items:center;gap:6px;min-width:0;flex:1;font-size:11px;color:var(--muted,#66736d)}
      .patient-sort-toolbar select{min-width:0;flex:1;padding:5px 7px;border:1px solid var(--line,#cfd6dc);border-radius:7px;background:var(--surface,#fff);color:inherit;font:inherit}
      .patient-browser-count{white-space:nowrap;font-size:11px;color:var(--muted,#66736d)}
      .patient-item .patient-card-dates{display:block;margin-top:3px;font-size:9px;line-height:1.35;opacity:.76;font-weight:400}
      @media (max-width:760px){.patient-sort-toolbar{align-items:stretch;flex-direction:column}.patient-sort-toolbar label{width:100%}.patient-browser-count{align-self:flex-end}}
    `;
    document.head.appendChild(style);
  }

  function ensureControls() {
    const list = document.querySelector("#patient-list");
    if (!list) return null;
    let toolbar = document.querySelector("#patient-sort-toolbar");
    if (!toolbar) {
      toolbar = document.createElement("div");
      toolbar.id = "patient-sort-toolbar";
      toolbar.className = "patient-sort-toolbar";
      toolbar.innerHTML = `
        <label>患者排序
          <select id="patient-sort-mode" aria-label="患者排序方式">
            ${SORT_OPTIONS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
          </select>
        </label>
        <span id="patient-browser-count" class="patient-browser-count">共 0 人</span>
      `;
      list.insertAdjacentElement("beforebegin", toolbar);
      const select = toolbar.querySelector("#patient-sort-mode");
      select.value = currentSortMode();
      select.addEventListener("change", () => {
        localStorage.setItem(STORAGE_KEY, select.value);
        applyPatientSort();
      });
    }
    return toolbar;
  }

  function decorateCard(button, patient) {
    button.dataset.patientCode = String(patient.patient_code || "");
    let dates = button.querySelector(".patient-card-dates");
    if (!dates) {
      dates = document.createElement("small");
      dates.className = "patient-card-dates";
      button.appendChild(dates);
    }
    dates.textContent = `添加 ${formatDateTime(patient.created_at)} · 修改 ${formatDateTime(patient.updated_at)}`;
    dates.title = `添加时间：${formatDateTime(patient.created_at)}\n最近修改：${formatDateTime(patient.updated_at)}`;
  }

  function applyPatientSort() {
    ensureControls();
    const list = document.querySelector("#patient-list");
    if (!list || !Array.isArray(state?.patients)) return;
    const patients = [...state.patients].sort((left, right) => comparePatients(left, right));
    const cardsByCode = new Map();
    [...list.querySelectorAll(".patient-item")].forEach(button => {
      const code = button.querySelector("strong")?.textContent?.trim() || "";
      if (code) cardsByCode.set(code, button);
    });
    const fragment = document.createDocumentFragment();
    for (const patient of patients) {
      const code = String(patient.patient_code || "");
      const button = cardsByCode.get(code);
      if (!button) continue;
      decorateCard(button, patient);
      fragment.appendChild(button);
    }
    list.appendChild(fragment);
    const count = document.querySelector("#patient-browser-count");
    if (count) count.textContent = `共 ${patients.length} 人`;
    const select = document.querySelector("#patient-sort-mode");
    if (select) select.value = currentSortMode();
  }

  installStyles();
  ensureControls();

  const originalLoadPatients = typeof loadPatients === "function" ? loadPatients : null;
  if (originalLoadPatients) {
    loadPatients = async (...args) => {
      const result = await originalLoadPatients(...args);
      applyPatientSort();
      return result;
    };
    const refresh = document.querySelector("#refresh-patients");
    if (refresh) refresh.onclick = loadPatients;
  }

  applyPatientSort();
})();
