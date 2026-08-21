import json
from pathlib import Path

from app.config import settings
from app.text_learning import (
    build_text_learning_profile,
    import_text_learning_payload,
    imported_text_learning_status,
    text_learning_prompt_section,
)

ROOT = Path(__file__).resolve().parents[1]


def sample_profile(count: int = 3) -> dict[str, object]:
    return {
        "type": "bce_text_learning",
        "version": 2,
        "generated_at": "2026-08-21T12:00:00+08:00",
        "fields": [
            {
                "field_name": "primary_her2",
                "label": "原发灶 HER2",
                "edit_count": count,
                "manual_fill_count": 0,
                "corrections": [
                    {
                        "from": "POSITIVE",
                        "to": "2+",
                        "reason": "HER2 2+不应直接映射为阳性",
                        "count": count,
                    }
                ],
                "manual_values": [],
            },
            {
                "field_name": "contact",
                "corrections": [{"from": "1", "to": "2", "count": 99}],
                "manual_values": [],
            },
        ],
    }


def test_imported_learning_persists_without_patient_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_path", tmp_path / "database")
    monkeypatch.setattr(settings, "database_path", tmp_path / "missing" / "catalog.sqlite")

    result = import_text_learning_payload(sample_profile(), source_name="old-machine.json")
    assert result["imported"] is True
    assert result["duplicate"] is False
    assert result["imported_field_count"] == 1
    assert result["skipped_fields"] == 1

    stored = tmp_path / "database" / "learning" / "imported_text_learning.json"
    assert stored.is_file()
    payload = json.loads(stored.read_text(encoding="utf-8"))
    assert payload["type"] == "bce_imported_text_learning"
    assert len(payload["sources"]) == 1

    profile = build_text_learning_profile({"primary_her2"})
    assert profile["field_count"] == 1
    assert profile["imported_source_count"] == 1
    assert profile["fields"][0]["corrections"][0]["count"] == 3
    assert "HER2 2+不应直接映射为阳性" in text_learning_prompt_section({"primary_her2"})


def test_reimport_same_profile_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_path", tmp_path / "database")
    monkeypatch.setattr(settings, "database_path", tmp_path / "missing" / "catalog.sqlite")

    first = import_text_learning_payload(sample_profile(), source_name="first.json")
    second = import_text_learning_payload(sample_profile(), source_name="renamed.json")
    assert first["imported"] is True
    assert second["duplicate"] is True

    profile = build_text_learning_profile({"primary_her2"})
    field = profile["fields"][0]
    assert field["edit_count"] == 3
    assert field["corrections"][0]["count"] == 3
    assert imported_text_learning_status()["source_count"] == 1


def test_overlapping_imports_keep_highest_pattern_count(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_path", tmp_path / "database")
    monkeypatch.setattr(settings, "database_path", tmp_path / "missing" / "catalog.sqlite")

    import_text_learning_payload(sample_profile(3), source_name="a.json")
    import_text_learning_payload(sample_profile(8), source_name="b.json")

    profile = build_text_learning_profile({"primary_her2"})
    field = profile["fields"][0]
    assert field["corrections"][0]["count"] == 8
    assert field["edit_count"] == 8
    assert imported_text_learning_status()["source_count"] == 2


def test_import_frontend_and_supported_entrypoints_are_wired():
    import_script = (ROOT / "app/static/text_learning_import.js").read_text(encoding="utf-8")
    loader = (ROOT / "app/static/shutdown.js").read_text(encoding="utf-8")
    native = (ROOT / "app/native_entry.py").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    server = (ROOT / "app/server.py").read_text(encoding="utf-8")

    assert 'importButton.textContent = "导入学习JSON"' in import_script
    assert 'api("/api/text-learning/import"' in import_script
    assert 'api("/api/text-learning")' in import_script
    assert 'importScript.src = "/text_learning_import.js"' in loader
    assert "from app.server import app as downstream" in native
    assert '"app.server:app"' in dockerfile
    assert "app.include_router(text_learning_router)" in server
    assert "app.router.routes.extend(static_mounts)" in server
