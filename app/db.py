import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings


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

CREATE INDEX IF NOT EXISTS idx_documents_patient ON documents(patient_id);
CREATE INDEX IF NOT EXISTS idx_regions_document ON regions(document_id);
CREATE INDEX IF NOT EXISTS idx_observations_patient ON observations(patient_id);
CREATE INDEX IF NOT EXISTS idx_audit_patient ON audit_log(patient_id);
"""


def init_db(path: Path | None = None) -> None:
    db_path = path or settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA)
        existing = {row[1] for row in connection.execute("PRAGMA table_info(observations)")}
        migrations = {
            "source_mode": "ALTER TABLE observations ADD COLUMN source_mode TEXT NOT NULL DEFAULT 'RECORDED'",
            "derivation_json": "ALTER TABLE observations ADD COLUMN derivation_json TEXT",
            "ruleset_version": "ALTER TABLE observations ADD COLUMN ruleset_version TEXT",
        }
        for column, statement in migrations.items():
            if column not in existing:
                connection.execute(statement)


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = path or settings.database_path
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def rows_as_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
