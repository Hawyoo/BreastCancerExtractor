from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models import PatientCreate

ROOT = Path(__file__).parents[1]


def _script() -> str:
    return (ROOT / "app/static/quick_import.js").read_text(encoding="utf-8")


def test_quick_import_uses_direct_parent_folder_name_as_patient_id():
    script = _script()
    assert "PATIENT_CODE_PATTERN" not in script
    assert "patientCodeFromPath" in script
    assert "const folderName = parts[parts.length - 2]" in script
    assert 'folderName !== "." && folderName !== ".."' in script
    assert "文件夹名 = 患者ID" in script
    assert "文件夹名会原样作为患者ID" in script
    assert "patient.patient_code" in script
    assert "new Map(state.patients.map" in script


def test_patient_create_accepts_normal_folder_names_as_ids():
    for patient_id in ("1234567", "A-001", "病例 2026-08", "乳腺癌患者甲"):
        assert PatientCreate(patient_code=patient_id).patient_code == patient_id


@pytest.mark.parametrize(
    "patient_id",
    ["", "   ", ".", "..", "a/b", r"a\b", "bad:name", "bad*name", "CON", "LPT1", "tail."],
)
def test_patient_create_rejects_unsafe_folder_names(patient_id):
    with pytest.raises(ValidationError):
        PatientCreate(patient_code=patient_id)


def test_quick_import_relaxes_manual_patient_input_to_same_id_rule():
    script = _script()
    assert 'patientInput.placeholder = "患者ID"' in script
    assert "patientInput.maxLength = 120" in script
    assert 'patientInput.removeAttribute("pattern")' in script
    assert 'patientInput.removeAttribute("inputmode")' in script
    assert 'searchInput.placeholder = "输入患者ID"' in script


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
    early_return = shutdown.index("if (!token) return")
    assert loader < params < early_return
    assert 'data-bce-quick-import="1"' in shutdown
    assert "quickImportScript.onload" in shutdown
    assert "exitButton.onclick = leavePatient" in shutdown
