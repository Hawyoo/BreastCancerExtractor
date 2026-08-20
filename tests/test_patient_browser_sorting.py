from pathlib import Path

ROOT = Path(__file__).parents[1]


def _sort_script() -> str:
    return (ROOT / "app/static/patient_sort.js").read_text(encoding="utf-8")


def test_patient_browser_supports_id_created_and_updated_sort_modes():
    script = _sort_script()
    for mode in (
        "id_asc",
        "id_desc",
        "created_desc",
        "created_asc",
        "updated_desc",
        "updated_asc",
    ):
        assert mode in script
    assert 'new Intl.Collator("zh-CN", {numeric: true' in script
    assert "comparePatientIds" in script
    assert "comparePatients" in script


def test_patient_sort_defaults_to_recently_modified_and_persists_choice():
    script = _sort_script()
    assert 'const DEFAULT_SORT = "updated_desc"' in script
    assert 'const STORAGE_KEY = "bce-patient-browser-sort"' in script
    assert "localStorage.getItem(STORAGE_KEY)" in script
    assert "localStorage.setItem(STORAGE_KEY, select.value)" in script


def test_patient_cards_show_created_and_modified_times_and_total_count():
    script = _sort_script()
    assert "patient.created_at" in script
    assert "patient.updated_at" in script
    assert "添加 ${formatDateTime(patient.created_at)}" in script
    assert "修改 ${formatDateTime(patient.updated_at)}" in script
    assert "共 ${patients.length} 人" in script


def test_patient_sort_reorders_existing_cards_without_changing_patient_api():
    script = _sort_script()
    assert "const originalLoadPatients" in script
    assert "loadPatients = async (...args)" in script
    assert "fragment.appendChild(button)" in script
    assert "list.appendChild(fragment)" in script
    assert 'api("/api/patients"' not in script


def test_refresh_button_uses_sorted_patient_loader():
    script = _sort_script()
    assert 'document.querySelector("#refresh-patients")' in script
    assert "refresh.onclick = loadPatients" in script


def test_patient_sort_loads_before_quick_import_and_before_shutdown_early_return():
    shutdown = (ROOT / "app/static/shutdown.js").read_text(encoding="utf-8")
    patient_sort = shutdown.index('patientSortScript.src = "/patient_sort.js"')
    quick_import = shutdown.index('quickImportScript.src = "/quick_import.js"')
    params = shutdown.index("const params = new URLSearchParams")
    early_return = shutdown.index("if (!port || !token) return")
    assert patient_sort < quick_import < params < early_return
    assert 'data-bce-patient-sort="1"' in shutdown


def test_patient_list_api_already_exposes_timestamps_needed_for_sorting():
    main_py = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "SELECT p.*, COUNT(DISTINCT d.id) AS document_count" in main_py
    assert "ORDER BY p.updated_at DESC" in main_py
