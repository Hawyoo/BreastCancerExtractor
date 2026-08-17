import json
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import connect, init_db, rows_as_dicts, utc_now
from app.models import (
    DocumentTypeUpdate,
    ModelImportRequest,
    ObservationCreate,
    ObservationEdit,
    ObservationVerify,
    PatientCreate,
    RegionInput,
    SanitizationMetadata,
)
from app.ollama import import_gguf, list_models
from app.storage import resolve_gguf, safe_workspace_file, save_sanitized_image, scan_gguf_files


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    settings.workspace_path.mkdir(parents=True, exist_ok=True)
    settings.model_import_path.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
STATIC_DIR = Path(__file__).parent / "static"


@app.middleware("http")
async def privacy_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "offline_mode": settings.offline_mode,
        "external_api": "disabled" if settings.offline_mode else "configurable",
        "llm": "local-ollama",
    }


@app.get("/api/patients")
def get_patients() -> list[dict[str, object]]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT p.*, COUNT(DISTINCT d.id) AS document_count,
                   COUNT(DISTINCT CASE WHEN o.status = 'REVIEW_REQUIRED' THEN o.id END) AS review_count
            FROM patients p
            LEFT JOIN documents d ON d.patient_id = p.id
            LEFT JOIN observations o ON o.patient_id = p.id
            GROUP BY p.id
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
    return rows_as_dicts(rows)


@app.post("/api/patients", status_code=201)
def create_patient(payload: PatientCreate) -> dict[str, object]:
    now = utc_now()
    try:
        with connect() as db:
            cursor = db.execute(
                "INSERT INTO patients(patient_code,status,created_at,updated_at) VALUES(?,?,?,?)",
                (payload.patient_code, "UNPROCESSED", now, now),
            )
            patient_id = cursor.lastrowid
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise HTTPException(status_code=409, detail="Patient code already exists") from exc
        raise
    return {"id": patient_id, "patient_code": payload.patient_code, "status": "UNPROCESSED"}


def require_patient(patient_id: int) -> dict[str, object]:
    with connect() as db:
        row = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found")
    return dict(row)


@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: int) -> dict[str, object]:
    patient = require_patient(patient_id)
    with connect() as db:
        documents = rows_as_dicts(
            db.execute("SELECT * FROM documents WHERE patient_id=? ORDER BY created_at", (patient_id,)).fetchall()
        )
        observations = rows_as_dicts(
            db.execute("SELECT * FROM observations WHERE patient_id=? ORDER BY created_at", (patient_id,)).fetchall()
        )
        audit = rows_as_dicts(
            db.execute("SELECT * FROM audit_log WHERE patient_id=? ORDER BY id DESC", (patient_id,)).fetchall()
        )
        for document in documents:
            document["regions"] = rows_as_dicts(
                db.execute("SELECT * FROM regions WHERE document_id=?", (document["id"],)).fetchall()
            )
    return {**patient, "documents": documents, "observations": observations, "audit_log": audit}


@app.post("/api/patients/{patient_id}/documents", status_code=201)
async def upload_sanitized_document(
    patient_id: int,
    image: UploadFile = File(...),
    display_name: str = Form(...),
    document_type: str = Form("OTHER"),
    sanitization: str = Form(...),
    regions: str = Form("[]"),
) -> dict[str, object]:
    patient = require_patient(patient_id)
    try:
        metadata = SanitizationMetadata.model_validate_json(sanitization)
        region_list = [RegionInput.model_validate(item) for item in json.loads(regions)]
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid sanitization metadata: {exc}") from exc

    saved = await save_sanitized_image(str(patient["patient_code"]), image, metadata)
    now = utc_now()
    with connect() as db:
        db.execute(
            """INSERT INTO documents
               (id,patient_id,display_name,document_type,status,relative_path,sha256,width,height,
                sanitization_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                saved["id"], patient_id, display_name, document_type, "ANNOTATED" if region_list else "SANITIZED",
                saved["relative_path"], saved["sha256"], saved["width"], saved["height"],
                saved["sanitization_json"], now,
            ),
        )
        created_regions = []
        for region in region_list:
            region_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO regions VALUES(?,?,?,?,?,?,?,?,?)",
                (region_id, saved["id"], region.region_type, region.label, region.x, region.y,
                 region.width, region.height, now),
            )
            created_regions.append({"id": region_id, **region.model_dump()})
        db.execute("UPDATE patients SET updated_at=? WHERE id=?", (now, patient_id))
    return {**saved, "regions": created_regions}


@app.get("/api/documents/{document_id}/image")
def get_document_image(document_id: str) -> FileResponse:
    with connect() as db:
        row = db.execute("SELECT relative_path FROM documents WHERE id=?", (document_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(safe_workspace_file(row["relative_path"]), media_type="image/png")


@app.patch("/api/documents/{document_id}/type")
def update_document_type(document_id: str, payload: DocumentTypeUpdate) -> dict[str, str]:
    with connect() as db:
        row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        db.execute("UPDATE documents SET document_type=? WHERE id=?", (payload.document_type, document_id))
        db.execute(
            """INSERT INTO audit_log(patient_id,document_id,operation,old_value,new_value,operator,timestamp)
               VALUES(?,?,?,?,?,?,?)""",
            (row["patient_id"], document_id, "USER_EDIT_DOCUMENT_TYPE", row["document_type"],
             payload.document_type, payload.operator, utc_now()),
        )
    return {"document_type": payload.document_type}


@app.post("/api/patients/{patient_id}/observations", status_code=201)
def create_observation(patient_id: int, payload: ObservationCreate) -> dict[str, object]:
    require_patient(patient_id)
    observation_id = uuid.uuid4().hex
    now = utc_now()
    status = "REVIEW_REQUIRED" if payload.confidence in {"LOW", "MEDIUM"} else "AI_PROCESSED"
    with connect() as db:
        db.execute(
            """INSERT INTO observations
               (id,patient_id,document_id,region_id,field_name,ai_value,current_value,raw_text,
                confidence,status,model_name,model_digest,prompt_version,ocr_version,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (observation_id, patient_id, payload.document_id, payload.region_id, payload.field_name,
             payload.value, payload.value, payload.raw_text, payload.confidence, status,
             payload.model_name, payload.model_digest, payload.prompt_version, payload.ocr_version,
             now, now),
        )
        db.execute(
            """INSERT INTO audit_log
               (patient_id,document_id,field_name,operation,new_value,operator,model_name,model_digest,timestamp)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (patient_id, payload.document_id, payload.field_name, "AI_EXTRACT", payload.value, "AI",
             payload.model_name, payload.model_digest, now),
        )
        db.execute("UPDATE patients SET status=?,updated_at=? WHERE id=?", (status, now, patient_id))
    return {"id": observation_id, "status": status, "confidence": payload.confidence}


def get_observation(observation_id: str) -> dict[str, object]:
    with connect() as db:
        row = db.execute("SELECT * FROM observations WHERE id=?", (observation_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Observation not found")
    return dict(row)


@app.patch("/api/observations/{observation_id}")
def edit_observation(observation_id: str, payload: ObservationEdit) -> dict[str, object]:
    observation = get_observation(observation_id)
    now = utc_now()
    with connect() as db:
        db.execute(
            "UPDATE observations SET current_value=?,status='REVIEW_REQUIRED',confidence='LOW',updated_at=? WHERE id=?",
            (payload.value, now, observation_id),
        )
        db.execute(
            """INSERT INTO audit_log
               (patient_id,document_id,field_name,operation,old_value,new_value,operator,reason,timestamp)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (observation["patient_id"], observation["document_id"], observation["field_name"],
             "USER_EDIT", observation["current_value"], payload.value, payload.operator, payload.reason, now),
        )
    return {"id": observation_id, "value": payload.value, "status": "REVIEW_REQUIRED"}


@app.post("/api/observations/{observation_id}/verify")
def verify_observation(observation_id: str, payload: ObservationVerify) -> dict[str, str]:
    observation = get_observation(observation_id)
    now = utc_now()
    with connect() as db:
        db.execute(
            "UPDATE observations SET status='VERIFIED',confidence='VERIFIED',updated_at=? WHERE id=?",
            (now, observation_id),
        )
        db.execute(
            """INSERT INTO audit_log
               (patient_id,document_id,field_name,operation,old_value,new_value,operator,reason,timestamp)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (observation["patient_id"], observation["document_id"], observation["field_name"],
             "USER_VERIFY", observation["current_value"], observation["current_value"],
             payload.operator, payload.note, now),
        )
        remaining = db.execute(
            "SELECT COUNT(*) FROM observations WHERE patient_id=? AND status!='VERIFIED'",
            (observation["patient_id"],),
        ).fetchone()[0]
        if remaining == 0:
            db.execute(
                "UPDATE patients SET status='VERIFIED',updated_at=? WHERE id=?",
                (now, observation["patient_id"]),
            )
    return {"id": observation_id, "status": "VERIFIED", "confidence": "VERIFIED"}


@app.get("/api/models/local-files")
def local_model_files() -> list[dict[str, object]]:
    return scan_gguf_files()


@app.get("/api/models/installed")
async def installed_models() -> list[dict[str, object]]:
    return await list_models()


@app.post("/api/models/import")
async def import_model(payload: ModelImportRequest) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.gguf", payload.filename):
        raise HTTPException(status_code=422, detail="Invalid GGUF filename")
    resolve_gguf(payload.filename)
    result = await import_gguf(payload.filename, payload.model_name)
    return {"status": "imported", "model": payload.model_name, "ollama": result}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
