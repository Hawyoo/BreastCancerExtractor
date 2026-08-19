from pathlib import Path

ROOT = Path(__file__).parents[1]


def _script() -> str:
    return (ROOT / "app/static/quick_import.js").read_text(encoding="utf-8")


def test_quick_import_uses_folder_name_as_existing_seven_digit_patient_id():
    script = _script()
    assert "const PATIENT_CODE_PATTERN = /^\\d{7}$/" in script
    assert "patientCodeFromPath" in script
    assert "parts.slice(0, -1).reverse().find" in script
    assert "patient.patient_code" in script
    assert "new Map(state.patients.map" in script


def test_quick_import_creates_missing_patients_and_reuses_existing_patients():
    script = _script()
    assert 'api("/api/patients"' in script
    assert 'method: "POST"' in script
    assert "createdCount += 1" in script
    assert "existingCount += 1" in script
    assert "patientId: patient.id" in script


def test_quick_import_supports_parent_directory_and_multiple_folder_drop():
    script = _script()
    assert 'id="quick-import-folders"' in script
    assert "webkitdirectory multiple" in script
    assert "包含多个患者文件夹的父目录" in script
    assert "一次拖入多个患者文件夹" in script
    assert "webkitGetAsEntry" in script
    assert "readDirectoryEntry" in script
    assert "entriesFromDataTransfer" in script


def test_quick_import_groups_images_by_patient_and_uses_existing_raw_queue():
    script = _script()
    assert "groupEntriesByPatient" in script
    assert "groups.set(code, [])" in script
    assert "state.rawQueuePatientId = state.patient.id" in script
    assert "state.rawQueue.push" in script
    assert "guessDocumentType(entry.file.name)" in script
    assert "renderRawQueue()" in script
    assert "loadRawItem(first)" in script
    assert "selectPatient(group.patientId)" in script


def test_quick_import_does_not_bypass_sanitization_or_upload_raw_images_directly():
    script = _script()
    assert "原图仍只保留在浏览器会话中" in script
    assert "所有原图均经过逐张确认脱敏后才保存" in script
    assert "当前患者仍有未确认原图" in script
    assert "/documents" not in script
    assert "save-sanitized" not in script


def test_quick_import_advances_only_after_current_patient_raw_queue_is_saved():
    script = _script()
    assert 'state.rawQueue.some(item => item.status !== "SAVED")' in script
    assert "const nextIndex = session.index + 1" in script
    assert "await activateGroup(nextIndex)" in script
    assert "MutationObserver" in script


def test_quick_import_can_be_cancelled_safely_when_switching_or_leaving_patient():
    script = _script()
    assert "cancelQuickImport" in script
    assert "手动切换患者将取消剩余快速导入" in script
    assert "退出当前患者将取消剩余快速导入" in script
    assert "已自动创建的患者不会被删除" in script
    assert "clearRawQueue()" in script


def test_quick_import_loader_runs_on_web_docker_and_windows_before_shutdown_early_return():
    shutdown = (ROOT / "app/static/shutdown.js").read_text(encoding="utf-8")
    loader = shutdown.index('quickImportScript.src = "/quick_import.js"')
    params = shutdown.index("const params = new URLSearchParams")
    early_return = shutdown.index("if (!port || !token) return")
    assert loader < params < early_return
    assert 'data-bce-quick-import="1"' in shutdown
    assert "quickImportScript.onload" in shutdown
    assert "exitButton.onclick = leavePatient" in shutdown
