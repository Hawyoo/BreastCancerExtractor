import io
import json
import shutil
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.main import app


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
    settings.data_path = root / "database"
    settings.config_path = root / "config"
    settings.runtime_path = root / "runtime"
    settings.database_path = settings.runtime_path / "catalog.sqlite"
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
            "field_name": "breast_laterality",
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
    assert not (tmp_path / "database" / "catalog.sqlite").exists()
    assert not (tmp_path / "database" / "runtime_config.json").exists()
    assert not (tmp_path / "database" / "instance.json").exists()
    assert (tmp_path / "runtime" / "test.db").is_file()
    assert (tmp_path / "config" / "instance.json").is_file()
    assert client.get(f"/api/patients/{patient['id']}").status_code == 200


def test_new_patient_package_rebuilds_catalog_automatically(tmp_path):
    machine_a = tmp_path / "machine-a"
    configure_machine(machine_a)
    with TestClient(app) as client:
        create_verified_patient(client, "2345678")
    source = machine_a / "database" / "patients" / "2345678"

    machine_b = tmp_path / "machine-b"
    destination = machine_b / "database" / "patients" / "2345678"
    shutil.copytree(source, destination)
    configure_machine(machine_b)
    assert not settings.database_path.exists()
    with TestClient(app) as client:
        # Startup scans database/patients and reconstructs the disposable catalog.
        patients = client.get("/api/patients").json()
        assert len(patients) == 1
        assert patients[0]["patient_code"] == "2345678"
        detail = client.get(f"/api/patients/{patients[0]['id']}").json()
        assert detail["patient_code"] == "2345678"
        assert detail["observations"][0]["current_value"] == "LEFT"
        assert client.get(f"/api/documents/{detail['documents'][0]['id']}/image").status_code == 200
        assert settings.database_path.is_file()


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
            {"field_name": "breast_laterality", "local_value": "RIGHT", "external_value": "LEFT"}
        ]
        merged = client.post(
            "/api/data-migration/import",
            json={"package_name": "3456789-from-machine-a", "action": "MERGE"},
        ).json()
        assert merged["conflicts"][0]["field_name"] == "breast_laterality"
        detail = client.get(f"/api/patients/{patient['id']}").json()
        observation = next(item for item in detail["observations"] if item["field_name"] == "breast_laterality")
        assert observation["current_value"] == "RIGHT"
        assert observation["status"] == "REVIEW_REQUIRED"
        assert {item["value"] for item in observation["candidate_values"]} == {"LEFT", "RIGHT"}
        assert client.get("/api/data-migration/scan").json()["conflicts"] == []
