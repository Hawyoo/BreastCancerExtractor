from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from app.config import settings
from app.db import SCHEMA, utc_now
from app.derived_fields import refresh_derived_observations

PACKAGE_SCHEMA_VERSION = 1
PACKAGE_DB_NAME = "patient.sqlite"
MANIFEST_NAME = "manifest.json"
IMPORTED_MARKER_NAME = ".imported.json"
PACKAGE_TABLES = (
    "patients",
    "documents",
    "regions",
    "ocr_results",
    "observations",
    "audit_log",
    "model_runs",
)


@contextmanager
def _connection(path: Path):
    connection = sqlite3.connect(path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patient_packages_root() -> Path:
    return settings.data_path / "patients"


def patient_package_dir(patient_code: str) -> Path:
    return patient_packages_root() / patient_code


def delete_patient_package(patient_code: str) -> None:
    directory = patient_package_dir(patient_code).resolve()
    if directory.parent != patient_packages_root().resolve():
        raise ValueError("无效病案号目录")
    if directory.is_dir():
        shutil.rmtree(directory)


def _instance_id() -> str:
    path = settings.config_path / "instance.json"
    legacy = settings.data_path / "instance.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if legacy.is_file():
        if not path.exists():
            legacy.replace(path)
        else:
            legacy.unlink(missing_ok=True)
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("instance_id")
            if isinstance(value, str) and value:
                return value
        except (OSError, ValueError, TypeError):
            pass
    value = uuid.uuid4().hex
    path.write_text(
        json.dumps({"instance_id": value, "created_at": utc_now()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return value


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")]


def _insert_rows(connection: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = [column for column in _table_columns(connection, table) if column in rows[0]]
    placeholders = ",".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
        [[row.get(column) for column in columns] for row in rows],
    )


def _patient_rows(connection: sqlite3.Connection, patient_id: int) -> dict[str, list[dict[str, Any]]]:
    connection.row_factory = sqlite3.Row
    documents = [
        dict(row) for row in connection.execute("SELECT * FROM documents WHERE patient_id=?", (patient_id,)).fetchall()
    ]
    document_ids = [str(row["id"]) for row in documents]

    def by_documents(table: str) -> list[dict[str, Any]]:
        if not document_ids:
            return []
        placeholders = ",".join("?" for _ in document_ids)
        return [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM {table} WHERE document_id IN ({placeholders})", document_ids
            ).fetchall()
        ]

    patient = connection.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if patient is None:
        raise ValueError("Patient not found")
    return {
        "patients": [dict(patient)],
        "documents": documents,
        "regions": by_documents("regions"),
        "ocr_results": by_documents("ocr_results"),
        "observations": [
            dict(row)
            for row in connection.execute("SELECT * FROM observations WHERE patient_id=?", (patient_id,)).fetchall()
        ],
        "audit_log": [
            dict(row)
            for row in connection.execute("SELECT * FROM audit_log WHERE patient_id=?", (patient_id,)).fetchall()
        ],
        "model_runs": [
            dict(row)
            for row in connection.execute("SELECT * FROM model_runs WHERE patient_id=?", (patient_id,)).fetchall()
        ],
    }


def _copy_patient_images(rows: dict[str, list[dict[str, Any]]], package_dir: Path) -> list[dict[str, Any]]:
    sanitized = package_dir / "sanitized"
    sanitized.mkdir(parents=True, exist_ok=True)
    images = []
    for document in rows["documents"]:
        source = (settings.data_path / str(document["relative_path"])).resolve()
        if not source.is_file():
            continue
        destination = sanitized / source.name
        if source != destination.resolve():
            shutil.copy2(source, destination)
        images.append({"file": destination.name, "sha256": _sha256(destination), "bytes": destination.stat().st_size})
    return sorted(images, key=lambda item: str(item["file"]))


def sync_patient_package(patient_id: int) -> dict[str, Any]:
    package_dir: Path
    with _connection(settings.database_path) as source:
        source.row_factory = sqlite3.Row
        rows = _patient_rows(source, patient_id)
    patient = rows["patients"][0]
    patient_code = str(patient["patient_code"])
    package_dir = patient_package_dir(patient_code)
    package_dir.mkdir(parents=True, exist_ok=True)
    temporary = package_dir / ".patient-building.sqlite"
    for suffix in ("", "-wal", "-shm"):
        Path(f"{temporary}{suffix}").unlink(missing_ok=True)
    with _connection(temporary) as target:
        target.executescript(SCHEMA.replace("PRAGMA journal_mode=WAL;", "PRAGMA journal_mode=DELETE;"))
        target.execute("PRAGMA foreign_keys=OFF")
        for table in PACKAGE_TABLES:
            _insert_rows(target, table, rows[table])
        target.execute("DELETE FROM patient_sync_state")
        target.commit()
    package_db = package_dir / PACKAGE_DB_NAME
    temporary.replace(package_db)
    images = _copy_patient_images(rows, package_dir)
    manifest = {
        "format": "BreastCancerExtractor.PatientPackage",
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "patient_code": patient_code,
        "patient_updated_at": patient["updated_at"],
        "exported_at": utc_now(),
        "source_instance_id": _instance_id(),
        "patient_db": {"file": PACKAGE_DB_NAME, "sha256": _sha256(package_db)},
        "counts": {table: len(rows[table]) for table in PACKAGE_TABLES},
        "images": images,
    }
    _write_json_atomic(package_dir / MANIFEST_NAME, manifest)
    with _connection(settings.database_path) as connection:
        connection.execute(
            "UPDATE patient_sync_state SET dirty=0,last_synced_at=? WHERE patient_id=?",
            (utc_now(), patient_id),
        )
    return manifest


def sync_dirty_patient_packages() -> list[str]:
    if not settings.database_path.is_file():
        return []
    with _connection(settings.database_path) as connection:
        rows = connection.execute(
            """SELECT p.id,p.patient_code FROM patient_sync_state s
               JOIN patients p ON p.id=s.patient_id WHERE s.dirty=1 ORDER BY p.id"""
        ).fetchall()
    synced = []
    for patient_id, patient_code in rows:
        sync_patient_package(int(patient_id))
        synced.append(str(patient_code))
    return synced


def sync_missing_patient_packages() -> list[str]:
    """Reconcile database/patients into the disposable runtime catalog.

    New patient directories are imported automatically on startup. Existing
    same-code conflicts remain explicit and are never silently overwritten.
    The catalog can therefore be deleted and rebuilt entirely from patient
    folders.
    """
    patient_packages_root().mkdir(parents=True, exist_ok=True)
    imported: list[str] = []
    scan = scan_patient_packages()
    for package in scan["new"]:
        result = import_patient_package(str(package["package_name"]), "IMPORT_NEW")
        imported.append(str(result["patient_code"]))

    with _connection(settings.database_path) as connection:
        connection.row_factory = sqlite3.Row
        refresh_derived_observations(connection)
        rows = connection.execute("SELECT id,patient_code FROM patients ORDER BY id").fetchall()

    synced = []
    for patient_id, patient_code in rows:
        if not (patient_package_dir(str(patient_code)) / PACKAGE_DB_NAME).is_file():
            sync_patient_package(int(patient_id))
            synced.append(str(patient_code))

    # Newly materialized derived fields must also travel with patient.sqlite.
    dirty = sync_dirty_patient_packages()
    return sorted(set(imported + synced + dirty))


def _read_package(directory: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    manifest_path = directory / MANIFEST_NAME
    package_db = directory / PACKAGE_DB_NAME
    if not manifest_path.is_file() or not package_db.is_file():
        raise ValueError("缺少 manifest.json 或 patient.sqlite")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "BreastCancerExtractor.PatientPackage":
        raise ValueError("不是 BreastCancerExtractor 患者数据包")
    if int(manifest.get("schema_version", 0)) > PACKAGE_SCHEMA_VERSION:
        raise ValueError("患者数据包版本高于当前软件支持版本")
    expected = manifest.get("patient_db", {}).get("sha256")
    if expected and expected != _sha256(package_db):
        raise ValueError("patient.sqlite 校验失败")
    with _connection(package_db) as connection:
        connection.row_factory = sqlite3.Row
        patient = connection.execute("SELECT * FROM patients").fetchall()
        if len(patient) != 1:
            raise ValueError("患者数据包必须且只能包含一名患者")
        patient_id = int(patient[0]["id"])
        rows = _patient_rows(connection, patient_id)
    code = str(rows["patients"][0]["patient_code"])
    if code != str(manifest.get("patient_code")):
        raise ValueError("manifest 与 patient.sqlite 病案号不一致")
    for image in manifest.get("images", []):
        path = directory / "sanitized" / str(image.get("file", ""))
        if not path.is_file() or (image.get("sha256") and _sha256(path) != image["sha256"]):
            raise ValueError(f"脱敏图片校验失败：{path.name}")
    return manifest, rows


def scan_patient_packages() -> dict[str, list[dict[str, Any]]]:
    root = patient_packages_root()
    root.mkdir(parents=True, exist_ok=True)
    with _connection(settings.database_path) as connection:
        existing = {
            str(row[1]): {"id": int(row[0]), "updated_at": str(row[2])}
            for row in connection.execute("SELECT id,patient_code,updated_at FROM patients")
        }
    result: dict[str, list[dict[str, Any]]] = {"new": [], "current": [], "conflicts": [], "invalid": []}
    local_instance = _instance_id()
    for directory in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name):
        if (directory / IMPORTED_MARKER_NAME).is_file():
            continue
        if not (directory / PACKAGE_DB_NAME).is_file() and not (directory / MANIFEST_NAME).is_file():
            continue
        try:
            manifest, rows = _read_package(directory)
            code = str(manifest["patient_code"])
            summary = {
                "package_name": directory.name,
                "patient_code": code,
                "source_instance_id": manifest.get("source_instance_id", ""),
                "patient_updated_at": manifest.get("patient_updated_at", ""),
                "counts": manifest.get("counts", {}),
            }
            if code not in existing:
                result["new"].append(summary)
            elif (
                manifest.get("source_instance_id") == local_instance
                and str(manifest.get("patient_updated_at")) == existing[code]["updated_at"]
            ):
                result["current"].append(summary)
            else:
                summary["local_patient_id"] = existing[code]["id"]
                summary["local_updated_at"] = existing[code]["updated_at"]
                summary["local_counts"] = _local_counts(existing[code]["id"])
                summary["verified_conflicts"] = _verified_conflicts(existing[code]["id"], rows)
                result["conflicts"].append(summary)
        except Exception as exc:
            result["invalid"].append({"package_name": directory.name, "error": str(exc)})
    return result


def _local_counts(patient_id: int) -> dict[str, int]:
    with _connection(settings.database_path) as connection:
        return {
            "documents": int(
                connection.execute("SELECT COUNT(*) FROM documents WHERE patient_id=?", (patient_id,)).fetchone()[0]
            ),
            "observations": int(
                connection.execute("SELECT COUNT(*) FROM observations WHERE patient_id=?", (patient_id,)).fetchone()[0]
            ),
            "verified": int(
                connection.execute(
                    "SELECT COUNT(*) FROM observations WHERE patient_id=? AND status='VERIFIED'", (patient_id,)
                ).fetchone()[0]
            ),
        }


def _verified_conflicts(patient_id: int, rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, str]]:
    with _connection(settings.database_path) as connection:
        local = {
            str(row[0]): str(row[1] or "")
            for row in connection.execute(
                """SELECT field_name,current_value FROM observations
                   WHERE patient_id=? AND status='VERIFIED' AND source_mode!='DERIVED'""",
                (patient_id,),
            ).fetchall()
        }
    conflicts = []
    for observation in rows["observations"]:
        if observation.get("source_mode") == "DERIVED":
            continue
        field = str(observation["field_name"])
        external = str(observation.get("current_value") or "")
        if observation.get("status") == "VERIFIED" and field in local and local[field] != external:
            conflicts.append({"field_name": field, "local_value": local[field], "external_value": external})
    return conflicts


def _package_path(package_name: str) -> Path:
    if Path(package_name).name != package_name:
        raise ValueError("无效患者目录名")
    directory = (patient_packages_root() / package_name).resolve()
    if directory.parent != patient_packages_root().resolve() or not directory.is_dir():
        raise ValueError("患者目录不存在")
    return directory


def _mark_external_package_handled(directory: Path, patient_code: str, action: str) -> None:
    if directory == patient_package_dir(patient_code):
        return
    _write_json_atomic(
        directory / IMPORTED_MARKER_NAME,
        {
            "patient_code": patient_code,
            "action": action,
            "handled_at": utc_now(),
            "destination": patient_code,
        },
    )


def import_patient_package(
    package_name: str,
    action: Literal["IMPORT_NEW", "KEEP_LOCAL", "USE_EXTERNAL", "MERGE"],
) -> dict[str, Any]:
    directory = _package_path(package_name)
    manifest, rows = _read_package(directory)
    patient = rows["patients"][0]
    patient_code = str(patient["patient_code"])
    with _connection(settings.database_path) as connection:
        connection.row_factory = sqlite3.Row
        local = connection.execute("SELECT * FROM patients WHERE patient_code=?", (patient_code,)).fetchone()
    if action == "KEEP_LOCAL":
        if local is None:
            raise ValueError("本机不存在该患者")
        sync_patient_package(int(local["id"]))
        _mark_external_package_handled(directory, patient_code, action)
        return {"patient_code": patient_code, "action": action, "conflicts": []}
    if action == "IMPORT_NEW" and local is not None:
        raise ValueError("本机已存在该患者，请选择冲突处理方式")
    if action in {"USE_EXTERNAL", "MERGE"} and local is None:
        action = "IMPORT_NEW"

    canonical = patient_package_dir(patient_code)
    if directory != canonical:
        canonical.mkdir(parents=True, exist_ok=True)
        shutil.copytree(directory / "sanitized", canonical / "sanitized", dirs_exist_ok=True)
    conflicts: list[dict[str, str]] = []
    with _connection(settings.database_path) as target:
        target.row_factory = sqlite3.Row
        target.execute("PRAGMA foreign_keys=ON")
        if local is None:
            cursor = target.execute(
                "INSERT INTO patients(patient_code,status,created_at,updated_at) VALUES(?,?,?,?)",
                (patient_code, patient["status"], patient["created_at"], patient["updated_at"]),
            )
            patient_id = int(cursor.lastrowid)
        else:
            patient_id = int(local["id"])
            if action == "USE_EXTERNAL":
                target.execute("DELETE FROM model_runs WHERE patient_id=?", (patient_id,))
                target.execute("DELETE FROM audit_log WHERE patient_id=?", (patient_id,))
                target.execute("DELETE FROM observations WHERE patient_id=?", (patient_id,))
                target.execute("DELETE FROM documents WHERE patient_id=?", (patient_id,))
                target.execute(
                    "UPDATE patients SET status=?,created_at=?,updated_at=? WHERE id=?",
                    (patient["status"], patient["created_at"], patient["updated_at"], patient_id),
                )

        document_map: dict[str, str] = {}
        region_map: dict[str, str] = {}
        inserted_documents: set[str] = set()
        for document in rows["documents"]:
            external_id = str(document["id"])
            duplicate = target.execute(
                "SELECT id FROM documents WHERE patient_id=? AND sha256=?", (patient_id, document["sha256"])
            ).fetchone()
            if duplicate and action == "MERGE":
                document_map[external_id] = str(duplicate["id"])
                continue
            document_id = external_id
            if target.execute("SELECT 1 FROM documents WHERE id=?", (document_id,)).fetchone():
                document_id = uuid.uuid4().hex
            document_map[external_id] = document_id
            inserted_documents.add(document_id)
            filename = Path(str(document["relative_path"])).name
            source_image = directory / "sanitized" / filename
            destination = canonical / "sanitized" / f"{document_id}.png"
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source_image.is_file() and source_image.resolve() != destination.resolve():
                shutil.copy2(source_image, destination)
            target.execute(
                """INSERT INTO documents
                   (id,patient_id,display_name,document_type,status,relative_path,sha256,width,height,
                    sanitization_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    document_id,
                    patient_id,
                    document["display_name"],
                    document["document_type"],
                    document["status"],
                    f"patients/{patient_code}/sanitized/{document_id}.png",
                    document["sha256"],
                    document["width"],
                    document["height"],
                    document["sanitization_json"],
                    document["created_at"],
                ),
            )
        for region in rows["regions"]:
            mapped_document = document_map.get(str(region["document_id"]))
            if mapped_document not in inserted_documents:
                continue
            region_id = str(region["id"])
            if target.execute("SELECT 1 FROM regions WHERE id=?", (region_id,)).fetchone():
                region_id = uuid.uuid4().hex
            region_map[str(region["id"])] = region_id
            target.execute(
                "INSERT INTO regions VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    region_id,
                    mapped_document,
                    region["region_type"],
                    region["label"],
                    region["x"],
                    region["y"],
                    region["width"],
                    region["height"],
                    region["created_at"],
                ),
            )
        for ocr in rows["ocr_results"]:
            mapped_document = document_map.get(str(ocr["document_id"]))
            if not mapped_document:
                continue
            target.execute(
                """INSERT OR IGNORE INTO ocr_results
                   (document_id,engine,version,full_text,result_json,created_at) VALUES(?,?,?,?,?,?)""",
                (
                    mapped_document,
                    ocr["engine"],
                    ocr["version"],
                    ocr["full_text"],
                    ocr["result_json"],
                    ocr["created_at"],
                ),
            )
        for observation in rows["observations"]:
            # Derived rows travel inside patient.sqlite for portability, but the
            # destination regenerates them from verified masters after merge.
            if observation.get("source_mode") == "DERIVED":
                continue
            mapped_document = (
                document_map.get(str(observation.get("document_id"))) if observation.get("document_id") else None
            )
            same = target.execute(
                """SELECT id FROM observations WHERE patient_id=? AND field_name=?
                   AND COALESCE(current_value,'')=COALESCE(?,'') AND COALESCE(document_id,'')=COALESCE(?,'')""",
                (patient_id, observation["field_name"], observation.get("current_value"), mapped_document),
            ).fetchone()
            if same and action == "MERGE":
                continue
            status = observation["status"]
            confidence = observation["confidence"]
            if action == "MERGE" and status == "VERIFIED":
                local_verified = target.execute(
                    """SELECT current_value FROM observations WHERE patient_id=? AND field_name=?
                       AND status='VERIFIED' AND source_mode!='DERIVED' LIMIT 1""",
                    (patient_id, observation["field_name"]),
                ).fetchone()
                if local_verified and str(local_verified["current_value"] or "") != str(
                    observation.get("current_value") or ""
                ):
                    conflicts.append(
                        {
                            "field_name": str(observation["field_name"]),
                            "local_value": str(local_verified["current_value"] or ""),
                            "external_value": str(observation.get("current_value") or ""),
                        }
                    )
                    status, confidence = "REVIEW_REQUIRED", "LOW"
            observation_id = str(observation["id"])
            if target.execute("SELECT 1 FROM observations WHERE id=?", (observation_id,)).fetchone():
                observation_id = uuid.uuid4().hex
            target.execute(
                """INSERT INTO observations
                   (id,patient_id,document_id,region_id,field_name,ai_value,current_value,raw_text,confidence,status,
                    source_mode,derivation_json,ruleset_version,model_name,model_digest,prompt_version,ocr_version,
                    created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    observation_id,
                    patient_id,
                    mapped_document,
                    region_map.get(str(observation.get("region_id"))),
                    observation["field_name"],
                    observation["ai_value"],
                    observation["current_value"],
                    observation["raw_text"],
                    confidence,
                    status,
                    observation["source_mode"],
                    observation["derivation_json"],
                    observation["ruleset_version"],
                    observation["model_name"],
                    observation["model_digest"],
                    observation["prompt_version"],
                    observation["ocr_version"],
                    observation["created_at"],
                    observation["updated_at"],
                ),
            )
        for audit in rows["audit_log"]:
            target.execute(
                """INSERT INTO audit_log
                   (patient_id,document_id,field_name,operation,old_value,new_value,operator,reason,model_name,model_digest,timestamp)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    patient_id,
                    document_map.get(str(audit.get("document_id"))) if audit.get("document_id") else None,
                    audit["field_name"],
                    audit["operation"],
                    audit["old_value"],
                    audit["new_value"],
                    audit["operator"],
                    audit["reason"],
                    audit["model_name"],
                    audit["model_digest"],
                    audit["timestamp"],
                ),
            )
        for run in rows["model_runs"]:
            run_id = str(run["id"])
            if target.execute("SELECT 1 FROM model_runs WHERE id=?", (run_id,)).fetchone():
                run_id = uuid.uuid4().hex
            target.execute(
                """INSERT INTO model_runs
                   (id,patient_id,model_name,model_digest,prompt_version,ocr_engine,ocr_version,status,started_at,finished_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    patient_id,
                    run["model_name"],
                    run["model_digest"],
                    run["prompt_version"],
                    run["ocr_engine"],
                    run["ocr_version"],
                    run["status"],
                    run["started_at"],
                    run["finished_at"],
                ),
            )

        refresh_derived_observations(target)
        target.execute(
            """INSERT INTO audit_log(patient_id,operation,new_value,operator,reason,timestamp)
               VALUES(?,?,?,?,?,?)""",
            (
                patient_id,
                "DATA_IMPORT",
                action,
                "system",
                f"来源实例：{manifest.get('source_instance_id', 'unknown')}",
                utc_now(),
            ),
        )
        if conflicts:
            target.execute(
                "UPDATE patients SET status='REVIEW_REQUIRED',updated_at=? WHERE id=?", (utc_now(), patient_id)
            )
    sync_patient_package(patient_id)
    _mark_external_package_handled(directory, patient_code, action)
    return {"patient_code": patient_code, "patient_id": patient_id, "action": action, "conflicts": conflicts}
