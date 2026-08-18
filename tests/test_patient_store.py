import io
import json
import shutil
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.main import app
from app.patient_store import migrate_legacy_catalog, migrate_legacy_workspace


def make_image() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (24, 18), "white").save(output, format="PNG")
    return output.getvalue()


def metadata() -> str:
    return json.dumps(
        {
            "source_width": 100,
            "source_height": 80,
            "crop": {"x": 5, "y": 4, "width": 24, "height": 18},
            "redaction_count": 1,
            "client_reencoded": True,
        }
    )


def configure_machine(root: Path) -> None:
    settings.database_path = root / "database" / "catalog.sqlite"
    settings.workspace_path = root / "database"
    settings.legacy_workspace_path = root / "workspace"
    settings.model_import_path = root / "models" / "llm"


def create_verified_patient(client: TestClient, code: str, value: str = "LEFT") -> dict:
    patient = client.post("/api/patients", json={"patient_code": code}).json()
    uploaded = client.post(
        f"/api/patients/{patient['id']}/documents",
        files={"image": ("sanitized.png", make_image(), "image/png")},
        data={
            "display_name": "入院记录-第1页",
            "document_type": "ADMISSION",
            "sanitization": metadata(),
            "regions": "[]",
        },
    ).json()
    observation = client.post(
        f"/api/patients/{patient['id']}/observations",
        json={
            "field_name": "laterality",
            "value": value,
            "confidence": "HIGH",
            "document_id": uploaded["id"],
        },
    ).json()
    client.post(f"/api/observations/{observation['id']}/verify", json={"operator": "reviewer"})
    return patient


def test_patient_directory_is_self_contained(client, tmp_path):
    patient = create_verified_patient(client, "1234567")
    package = tmp_path / "database" / "patients" / "1234567"
    assert (package / "patient.sqlite").is_file()
    assert (package / "manifest.json").is_file()
    assert len(list((package / "sanitized").glob("*.png"))) == 1
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["patient_code"] == "1234567"
    assert manifest["counts"]["observations"] == 1
    with sqlite3.connect(package / "patient.sqlite") as connection:
        assert connection.execute("SELECT patient_code FROM patients").fetchone()[0] == "1234567"
        assert connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] >= 2
    assert client.get(f"/api/patients/{patient['id']}").status_code == 200


def test_new_patient_package_can_rebuild_catalog(tmp_path):
    machine_a = tmp_path / "machine-a"
    configure_machine(machine_a)
    with TestClient(app) as client:
        create_verified_patient(client, "2345678")
    source = machine_a / "database" / "patients" / "2345678"

    machine_b = tmp_path / "machine-b"
    destination = machine_b / "database" / "patients" / "2345678"
    shutil.copytree(source, destination)
    configure_machine(machine_b)
    with TestClient(app) as client:
        scan = client.get("/api/data-migration/scan").json()
        assert [item["patient_code"] for item in scan["new"]] == ["2345678"]
        imported = client.post(
            "/api/data-migration/import",
            json={"package_name": "2345678", "action": "IMPORT_NEW"},
        )
        assert imported.status_code == 200
        patients = client.get("/api/patients").json()
        assert len(patients) == 1
        detail = client.get(f"/api/patients/{patients[0]['id']}").json()
        assert detail["patient_code"] == "2345678"
        assert detail["observations"][0]["current_value"] == "LEFT"
        assert client.get(f"/api/documents/{detail['documents'][0]['id']}/image").status_code == 200


def test_same_patient_verified_conflict_requires_review(tmp_path):
    machine_a = tmp_path / "machine-a"
    configure_machine(machine_a)
    with TestClient(app) as client:
        create_verified_patient(client, "3456789", "LEFT")
    external = tmp_path / "external"
    shutil.copytree(machine_a / "database" / "patients" / "3456789", external)

    machine_b = tmp_path / "machine-b"
    configure_machine(machine_b)
    with TestClient(app) as client:
        patient = create_verified_patient(client, "3456789", "RIGHT")
        shutil.copytree(external, machine_b / "database" / "patients" / "3456789-from-machine-a")
        scan = client.get("/api/data-migration/scan").json()
        assert scan["conflicts"][0]["verified_conflicts"] == [
            {"field_name": "laterality", "local_value": "RIGHT", "external_value": "LEFT"}
        ]
        merged = client.post(
            "/api/data-migration/import",
            json={"package_name": "3456789-from-machine-a", "action": "MERGE"},
        ).json()
        assert merged["conflicts"][0]["field_name"] == "laterality"
        detail = client.get(f"/api/patients/{patient['id']}").json()
        observation = detail["observations"][0]
        assert observation["current_value"] == "RIGHT"
        assert observation["status"] == "REVIEW_REQUIRED"
        assert {item["value"] for item in observation["candidate_values"]} == {"LEFT", "RIGHT"}
        assert client.get("/api/data-migration/scan").json()["conflicts"] == []


def test_legacy_catalog_and_workspace_are_copied_without_deleting_source(tmp_path):
    root = tmp_path / "portable"
    database = root / "database"
    database.mkdir(parents=True)
    legacy_db = database / "extractor.db"
    with sqlite3.connect(legacy_db) as connection:
        connection.execute("CREATE TABLE marker(value TEXT)")
        connection.execute("INSERT INTO marker VALUES('legacy')")
    legacy_image = root / "workspace" / "patients" / "4567890" / "sanitized" / "image.png"
    legacy_image.parent.mkdir(parents=True)
    legacy_image.write_bytes(make_image())
    settings.database_path = database / "catalog.sqlite"
    settings.workspace_path = database
    settings.legacy_workspace_path = root / "workspace"

    assert migrate_legacy_catalog() is True
    assert migrate_legacy_workspace() == 1
    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone()[0] == "legacy"
    assert legacy_db.is_file()
    assert legacy_image.is_file()
    assert (database / "patients" / "4567890" / "sanitized" / "image.png").is_file()
