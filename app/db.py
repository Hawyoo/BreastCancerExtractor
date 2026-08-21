import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.derived_fields import refresh_derived_observations


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'UNPROCESSED',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    document_type TEXT NOT NULL DEFAULT 'OTHER',
    status TEXT NOT NULL DEFAULT 'SANITIZED',
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    sanitization_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS regions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    region_type TEXT NOT NULL,
    label TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    width REAL NOT NULL,
    height REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ocr_results (
    document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    engine TEXT NOT NULL,
    version TEXT,
    full_text TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
    region_id TEXT REFERENCES regions(id) ON DELETE SET NULL,
    field_name TEXT NOT NULL,
    ai_value TEXT,
    current_value TEXT,
    raw_text TEXT,
    confidence TEXT NOT NULL DEFAULT 'LOW',
    status TEXT NOT NULL DEFAULT 'AI_PROCESSED',
    source_mode TEXT NOT NULL DEFAULT 'RECORDED',
    derivation_json TEXT,
    ruleset_version TEXT,
    model_name TEXT,
    model_digest TEXT,
    prompt_version TEXT,
    ocr_version TEXT,
    evidence_status TEXT NOT NULL DEFAULT 'AUTO',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    document_id TEXT,
    field_name TEXT,
    operation TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    operator TEXT NOT NULL,
    reason TEXT,
    model_name TEXT,
    model_digest TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_runs (
    id TEXT PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id) ON DELETE SET NULL,
    model_name TEXT NOT NULL,
    model_digest TEXT,
    prompt_version TEXT,
    ocr_engine TEXT,
    ocr_version TEXT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS patient_sync_state (
    patient_id INTEGER PRIMARY KEY REFERENCES patients(id) ON DELETE CASCADE,
    dirty INTEGER NOT NULL DEFAULT 1,
    last_synced_at TEXT
);

CREATE TRIGGER IF NOT EXISTS sync_patient_insert AFTER INSERT ON patients BEGIN
    INSERT INTO patient_sync_state(patient_id,dirty) VALUES(NEW.id,1)
    ON CONFLICT(patient_id) DO UPDATE SET dirty=1;
END;
CREATE TRIGGER IF NOT EXISTS sync_patient_update AFTER UPDATE ON patients BEGIN
    INSERT INTO patient_sync_state(patient_id,dirty) VALUES(NEW.id,1)
    ON CONFLICT(patient_id) DO UPDATE SET dirty=1;
END;
CREATE TRIGGER IF NOT EXISTS sync_document_insert AFTER INSERT ON documents BEGIN
    INSERT INTO patient_sync_state(patient_id,dirty) VALUES(NEW.patient_id,1)
    ON CONFLICT(patient_id) DO UPDATE SET dirty=1;
END;
CREATE TRIGGER IF NOT EXISTS sync_document_update AFTER UPDATE ON documents BEGIN
    INSERT INTO patient_sync_state(patient_id,dirty) VALUES(NEW.patient_id,1)
    ON CONFLICT(patient_id) DO UPDATE SET dirty=1;
END;
CREATE TRIGGER IF NOT EXISTS sync_observation_insert AFTER INSERT ON observations BEGIN
    INSERT INTO patient_sync_state(patient_id,dirty) VALUES(NEW.patient_id,1)
    ON CONFLICT(patient_id) DO UPDATE SET dirty=1;
END;
CREATE TRIGGER IF NOT EXISTS sync_observation_update AFTER UPDATE ON observations BEGIN
    INSERT INTO patient_sync_state(patient_id,dirty) VALUES(NEW.patient_id,1)
    ON CONFLICT(patient_id) DO UPDATE SET dirty=1;
END;
CREATE TRIGGER IF NOT EXISTS sync_audit_insert AFTER INSERT ON audit_log BEGIN
    INSERT INTO patient_sync_state(patient_id,dirty) VALUES(NEW.patient_id,1)
    ON CONFLICT(patient_id) DO UPDATE SET dirty=1;
END;
CREATE TRIGGER IF NOT EXISTS sync_ocr_insert AFTER INSERT ON ocr_results BEGIN
    INSERT INTO patient_sync_state(patient_id,dirty)
    SELECT patient_id,1 FROM documents WHERE id=NEW.document_id
    ON CONFLICT(patient_id) DO UPDATE SET dirty=1;
END;
CREATE TRIGGER IF NOT EXISTS sync_ocr_update AFTER UPDATE ON ocr_results BEGIN
    INSERT INTO patient_sync_state(patient_id,dirty)
    SELECT patient_id,1 FROM documents WHERE id=NEW.document_id
    ON CONFLICT(patient_id) DO UPDATE SET dirty=1;
END;

CREATE INDEX IF NOT EXISTS idx_documents_patient ON documents(patient_id);
CREATE INDEX IF NOT EXISTS idx_regions_document ON regions(document_id);
CREATE INDEX IF NOT EXISTS idx_observations_patient ON observations(patient_id);
CREATE INDEX IF NOT EXISTS idx_audit_patient ON audit_log(patient_id);
"""


def _move_with_sidecars(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{source}{suffix}")
        if sidecar.exists():
            shutil.move(str(sidecar), str(Path(f"{destination}{suffix}")))


def _migrate_legacy_catalog(target: Path) -> None:
    legacy = settings.data_path / "catalog.sqlite"
    try:
        if legacy.resolve() == target.resolve() or not legacy.is_file():
            return
    except OSError:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        _move_with_sidecars(legacy, target)
        return

    # A runtime catalog already exists. Preserve the old cache outside
    # database/ rather than silently deleting a possibly newer legacy file.
    index = 1
    backup = settings.runtime_path / "catalog.legacy.sqlite"
    while backup.exists():
        index += 1
        backup = settings.runtime_path / f"catalog.legacy.{index}.sqlite"
    _move_with_sidecars(legacy, backup)


def init_db(path: Path | None = None) -> None:
    db_path = path or settings.database_path
    if path is None:
        _migrate_legacy_catalog(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA)
        connection.execute("DROP TRIGGER IF EXISTS sync_document_delete")
        connection.execute("DROP TRIGGER IF EXISTS sync_observation_delete")
        existing = {row[1] for row in connection.execute("PRAGMA table_info(observations)")}
        migrations = {
            "source_mode": "ALTER TABLE observations ADD COLUMN source_mode TEXT NOT NULL DEFAULT 'RECORDED'",
            "derivation_json": "ALTER TABLE observations ADD COLUMN derivation_json TEXT",
            "ruleset_version": "ALTER TABLE observations ADD COLUMN ruleset_version TEXT",
            "evidence_status": "ALTER TABLE observations ADD COLUMN evidence_status TEXT NOT NULL DEFAULT 'AUTO'",
        }
        for column, statement in migrations.items():
            if column not in existing:
                connection.execute(statement)
        connection.execute(
            """INSERT INTO patient_sync_state(patient_id,dirty)
               SELECT id,1 FROM patients WHERE id NOT IN (SELECT patient_id FROM patient_sync_state)"""
        )
        refresh_derived_observations(connection)
        connection.commit()


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = path or settings.database_path
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        refresh_derived_observations(connection)
        yield connection
        refresh_derived_observations(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def rows_as_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
