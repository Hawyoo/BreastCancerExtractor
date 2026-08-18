import asyncio
import csv
import io
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import connect, init_db, rows_as_dicts, utc_now
from app.knowledge import extraction_prompt, questionnaire_catalog, questionnaire_field_index, source_priority
from app.models import (
    DocumentTypeUpdate,
    ModelImportRequest,
    ObservationCreate,
    ObservationEdit,
    ObservationVerify,
    OllamaModelUpdate,
    OllamaProviderUpdate,
    PatientPackageImport,
    PatientCreate,
    RegionInput,
    SanitizationMetadata,
)
from app.ocr import ocr_health, recognize_image
from app.ollama import (
    cached_file_sha256,
    extract_structured,
    import_gguf,
    list_extraction_models,
    list_model_groups,
    list_models,
    model_source_digests,
    ollama_health,
    ollama_runtime_status,
    supports_structured_extraction,
)
from app.runtime_config import (
    get_ollama_provider,
    get_selected_ollama_model,
    ollama_provider_endpoints,
    save_ollama_provider,
    save_selected_ollama_model,
)


CONFIDENCE_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "VERIFIED": 3}
RESERVED_METADATA_VALUES = {"RECORDED", "INFERRED"}
PATHOLOGY_GRADE_FIELDS = {
    "primary_pathology_grade",
    "node_pathology_grade",
    "metastasis_pathology_grade",
    "postop_tumor_pathology_grade",
}
POSTOP_TUMOR_OTHER_IHC_FIELD = "postop_tumor_other_ihc"
MAMMOGRAPHY_BIRADS_FIELD = "pre_mmg_birads"
HER2_IHC_FIELDS = {
    "primary_her2", "node_her2", "metastasis_her2", "postop_tumor_her2", "postop_node_her2",
}
TNM_FIELDS = {"clinical_stage", "pathological_stage"}
IMMUNOTHERAPY_FIELDS = {
    "postoperative_immunotherapy",
    "postoperative_immunotherapy_regimen",
    "postoperative_immunotherapy_cycles",
}
SUPPORTIVE_IMMUNE_PATTERNS = (
    "免疫及对症支持治疗",
    "免疫支持治疗",
    "升白",
    "粒细胞集落刺激因子",
    "重组人粒细胞刺激因子",
)
ANTITUMOR_IMMUNOTHERAPY_MARKERS = (
    "抗肿瘤免疫治疗",
    "免疫检查点抑制剂",
    "PD-1",
    "PD-L1",
    "帕博利珠单抗",
    "阿替利珠单抗",
    "卡瑞利珠单抗",
    "特瑞普利单抗",
    "信迪利单抗",
)
CORE_IHC_PREFIX = re.compile(r"^\s*(?:ER|PR|HER\s*-?\s*2|KI\s*-?\s*67)\b", re.IGNORECASE)
CHINESE_VALUE_LABELS = {
    "YES": "是", "NO": "否", "UNKNOWN": "不详", "NOT_APPLICABLE": "NA",
    "FEMALE": "女", "MALE": "男", "OTHER": "其他",
    "LEFT": "左侧", "RIGHT": "右侧", "BILATERAL": "双侧",
    "POSITIVE": "阳性", "NEGATIVE": "阴性",
}


def normalize_pathology_grade(value: object) -> str:
    text = str(value).strip().upper().replace(" ", "")
    if text in {"UNKNOWN", "GX", "X", "不详", "未知"}:
        return "UNKNOWN"
    if text == "NOT_APPLICABLE":
        return text
    normalized = (
        text.replace("Ⅲ", "III").replace("Ⅱ", "II").replace("Ⅰ", "I")
        .replace("三级", "III").replace("二级", "II").replace("一级", "I")
        .replace("3级", "III").replace("2级", "II").replace("1级", "I")
    )
    normalized = re.sub(r"^(WHO|NOTTINGHAM|组织学|病理|分级|GRADE|G)", "", normalized)
    normalized = re.sub(r"(?:级|GRADE)$", "", normalized)
    if normalized in {"1", "I"}:
        return "1"
    if normalized in {"2", "II"}:
        return "2"
    if normalized in {"3", "III"}:
        return "3"
    return str(value).strip()


def normalize_postop_other_ihc(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    parts = [part.strip() for part in re.split(r"[；;，,\n]+", text) if part.strip()]
    remaining = [part for part in parts if not CORE_IHC_PREFIX.match(part)]
    return "；".join(remaining)


def normalize_birads_category(value: object) -> str:
    text = str(value).strip().upper().replace("－", "-").replace("—", "-")
    text = re.sub(r"^BI\s*-?\s*RADS\s*[:：-]?\s*", "", text)
    text = text.replace("级", "").strip()
    if text in {"OTHER", "其他"}:
        return "OTHER"
    match = re.fullmatch(r"([0-6])\s*([ABC])?", text)
    return "".join(part for part in match.groups() if part) if match else str(value).strip()


def normalize_her2_ihc(value: object) -> str:
    text = str(value).strip().upper().replace("＋", "+")
    text = re.sub(r"^HER\s*-?\s*2\s*[:：]?\s*", "", text)
    text = text.strip("()（） ")
    if text in {"-", "0", "0+", "NEGATIVE", "阴性", "NEG"}:
        return "0"
    if text in {"UNKNOWN", "不详", "未知", "无法判断"}:
        return "UNKNOWN"
    match = re.fullmatch(r"([123])\s*\+", text)
    return f"{match.group(1)}+" if match else str(value).strip()


def normalize_tnm(value: object) -> str:
    text = str(value).strip().upper()
    text = re.sub(r"[\s,，;；]+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    prefix_match = re.match(r"^(YC|YP|C|P)", text)
    if not prefix_match:
        return str(value).strip()
    prefix = prefix_match.group(1).lower()
    body = text[prefix_match.end():]
    # Canonical compact notation uses the classification prefix once: cT2N1M0 / ypT1N0M0.
    body = re.sub(r"(?:YC|YP|C|P)(?=N)", "", body)
    body = re.sub(r"(?:YC|YP|C|P)(?=M)", "", body)
    return prefix + body


def normalize_observation_value(field_name: str, value: object) -> str:
    if field_name in PATHOLOGY_GRADE_FIELDS:
        return normalize_pathology_grade(value)
    if field_name == POSTOP_TUMOR_OTHER_IHC_FIELD:
        return normalize_postop_other_ihc(value)
    if field_name == MAMMOGRAPHY_BIRADS_FIELD:
        return normalize_birads_category(value)
    if field_name in HER2_IHC_FIELDS:
        return normalize_her2_ihc(value)
    if field_name in TNM_FIELDS:
        return normalize_tnm(value)
    return str(value).strip()


def observation_value_is_valid(field_name: str, value: object) -> bool:
    text = normalize_observation_value(field_name, value)
    if not text or text.upper() in RESERVED_METADATA_VALUES:
        return False
    if field_name in TNM_FIELDS:
        prefix_pattern = r"^(?:c|yc)T" if field_name == "clinical_stage" else r"^(?:p|yp)T"
        return bool(re.search(prefix_pattern, text, re.IGNORECASE) and re.search(r"N", text, re.IGNORECASE)
                    and re.search(r"M", text, re.IGNORECASE))
    metadata = questionnaire_field_index().get(field_name, {})
    allowed = metadata.get("allowed_values")
    if metadata.get("field_type") == "yes_no_unknown":
        allowed = ["YES", "NO", "UNKNOWN"]
    if allowed:
        return text.upper() in {str(item).upper() for item in allowed}
    return True


def consolidate_patient_observations(observations: list[dict], documents: list[dict]) -> list[dict]:
    document_names = {item["id"]: item["display_name"] for item in documents}
    document_types = {item["id"]: item["document_type"] for item in documents}
    grouped: dict[str, list[dict]] = {}
    for observation in observations:
        if observation["status"] == "SUPERSEDED":
            continue
        normalized = observation.copy()
        normalized["current_value"] = normalize_observation_value(
            observation["field_name"], observation["current_value"]
        )
        normalized["ai_value"] = normalize_observation_value(
            observation["field_name"], observation.get("ai_value") or observation["current_value"]
        )
        grouped.setdefault(observation["field_name"], []).append(normalized)

    consolidated = []
    for candidates in grouped.values():
        valid = [item for item in candidates if observation_value_is_valid(item["field_name"], item["current_value"])]
        selectable = valid or candidates
        winner = max(
            selectable,
            key=lambda item: (
                item["status"] == "VERIFIED",
                item.get("source_mode") == "RECORDED",
                source_priority(
                    item["field_name"], document_types.get(item.get("document_id"))
                ),
                CONFIDENCE_RANK.get(item["confidence"], -1),
                len(item.get("raw_text") or ""),
                item["updated_at"],
            ),
        ).copy()
        valid_values = {str(item["current_value"]).strip().upper() for item in valid}
        winner["candidate_count"] = len(candidates)
        winner["discarded_candidate_count"] = len(candidates) - len(valid)
        winner["candidate_conflict"] = len(valid_values) > 1
        winner["invalid_only"] = not valid
        winner["candidate_values"] = [
            {
                "id": item["id"],
                "document_id": item.get("document_id"),
                "value": item["current_value"],
                "source": document_names.get(item.get("document_id"), "未知来源"),
                "document_type": document_types.get(item.get("document_id")),
                "raw_text": item.get("raw_text"),
                "valid": observation_value_is_valid(item["field_name"], item["current_value"]),
                "selected": item["id"] == winner["id"],
            }
            for item in candidates
        ]
        if winner["candidate_conflict"] or winner["invalid_only"]:
            winner["status"] = "REVIEW_REQUIRED"
        consolidated.append(winner)
    return consolidated


def immunotherapy_evidence_is_valid(ocr_text: str) -> bool:
    compact = re.sub(r"\s+", "", ocr_text or "")
    has_supportive_context = any(marker in compact for marker in SUPPORTIVE_IMMUNE_PATTERNS)
    has_antitumor_context = any(marker.upper() in compact.upper() for marker in ANTITUMOR_IMMUNOTHERAPY_MARKERS)
    return has_antitumor_context or not has_supportive_context


def preview_value(value: object) -> object:
    if value is None:
        return ""
    text = str(value).strip()
    return CHINESE_VALUE_LABELS.get(text.upper(), value)


def dependency_is_satisfied(value: object, dependency: dict[str, object]) -> bool:
    text = str(value).strip()
    if "equals" in dependency:
        return text.upper() == str(dependency["equals"]).upper()
    if "contains" in dependency:
        expected = str(dependency["contains"]).upper()
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = re.split(r"[；;，,|]+", text)
        values = parsed if isinstance(parsed, list) else [parsed]
        return expected in {str(item).strip().upper() for item in values}
    return True


def filter_conditionally_applicable_observations(
    observations: list[dict], field_index: dict[str, dict]
) -> tuple[list[dict], list[str]]:
    by_field = {item["field_name"]: item for item in observations}
    applicability_cache: dict[str, bool] = {}

    def is_applicable(field_name: str, stack: set[str] | None = None) -> bool:
        if field_name in applicability_cache:
            return applicability_cache[field_name]
        stack = set(stack or ())
        if field_name in stack:
            return True
        stack.add(field_name)
        dependency = field_index.get(field_name, {}).get("depends_on")
        if not dependency:
            applicability_cache[field_name] = True
            return True
        parent_name = str(dependency["field"])
        if not is_applicable(parent_name, stack):
            applicability_cache[field_name] = False
            return False
        parent = by_field.get(parent_name)
        if parent is None:
            applicability_cache[field_name] = True
            return True
        result = dependency_is_satisfied(parent["current_value"], dependency)
        applicability_cache[field_name] = result
        return result

    visible = [item for item in observations if is_applicable(item["field_name"])]
    hidden = [field_name for field_name in field_index if not is_applicable(field_name)]
    return visible, hidden


def build_data_preview(*, verified_only: bool = False) -> dict[str, object]:
    fields = questionnaire_catalog()
    with connect() as db:
        patients = rows_as_dicts(db.execute("SELECT id,patient_code FROM patients ORDER BY patient_code").fetchall())
    rows = []
    for patient in patients:
        detail = get_patient(patient["id"])
        observations = {
            item["field_name"]: item
            for item in detail["observations"]
            if not verified_only or item["status"] == "VERIFIED"
        }
        values: dict[str, object] = {}
        statuses: dict[str, str] = {}
        for field in fields:
            key = field["key"]
            if key == "record_number":
                values[key] = patient["patient_code"]
                statuses[key] = "VERIFIED"
            elif key == "contact":
                values[key] = ""
                statuses[key] = "UNAVAILABLE"
            elif field.get("depends_on"):
                dependency = field["depends_on"]
                prerequisite = observations.get(dependency["field"])
                if prerequisite and not dependency_is_satisfied(prerequisite["current_value"], dependency):
                    values[key] = "NA"
                    statuses[key] = prerequisite["status"]
                elif key in observations:
                    values[key] = preview_value(observations[key]["current_value"])
                    statuses[key] = observations[key]["status"]
                else:
                    values[key] = ""
                    statuses[key] = "EMPTY"
            elif key in observations:
                values[key] = preview_value(observations[key]["current_value"])
                statuses[key] = observations[key]["status"]
            else:
                values[key] = ""
                statuses[key] = "EMPTY"
        rows.append({"patient_id": patient["id"], "patient_code": patient["patient_code"],
                     "values": values, "statuses": statuses})
    return {
        "columns": [
            {"key": field["key"], "label": field["label"], "group": field.get("group", "other"), "order": index}
            for index, field in enumerate(fields)
        ],
        "rows": rows,
        "verified_only": verified_only,
    }
from app.storage import (
    replace_sanitized_image,
    resolve_gguf,
    safe_data_file,
    save_sanitized_image,
    scan_gguf_files,
)
from app.patient_store import (
    delete_patient_package,
    import_patient_package,
    scan_patient_packages,
    sync_dirty_patient_packages,
    sync_missing_patient_packages,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.model_import_path.mkdir(parents=True, exist_ok=True)
    sync_missing_patient_packages()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
STATIC_DIR = Path(__file__).parent / "static"
_EXTRACTION_PROGRESS: dict[str, dict[str, object]] = {}
_OCR_IN_PROGRESS: set[str] = set()
STAGING_FIELDS = {"clinical_stage", "pathological_stage"}
LOGGER = logging.getLogger(__name__)


def update_extraction_progress(document_id: str, **values: object) -> None:
    state = _EXTRACTION_PROGRESS.setdefault(document_id, {})
    state.update(values)
    if values.get("generated_tokens") and "generation_started_monotonic" not in state:
        state["generation_started_monotonic"] = time.monotonic()


@app.middleware("http")
async def privacy_headers(request, call_next):
    response = await call_next(request)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
        try:
            synced = sync_dirty_patient_packages()
            response.headers["X-Patient-Packages-Synced"] = str(len(synced))
        except Exception:
            LOGGER.exception("Patient package synchronization is pending")
            response.headers["X-Patient-Packages-Synced"] = "pending"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "offline_mode": settings.offline_mode,
        "external_api": "disabled" if settings.offline_mode else "configurable",
        "ollama": await ollama_health(),
        "ocr": await ocr_health(),
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
    results = rows_as_dicts(rows)
    for item in results:
        detail = get_patient(item["id"])
        item["review_count"] = sum(obs["status"] != "VERIFIED" for obs in detail["observations"])
        item["status"] = detail["status"]
    return results


@app.get("/api/data-preview")
def data_preview(verified_only: bool = False) -> dict[str, object]:
    return build_data_preview(verified_only=verified_only)


@app.get("/api/data-migration/scan")
def scan_data_migration() -> dict[str, list[dict[str, object]]]:
    return scan_patient_packages()


@app.post("/api/data-migration/import")
def import_data_migration(payload: PatientPackageImport) -> dict[str, object]:
    try:
        return import_patient_package(payload.package_name, payload.action)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/data-preview.csv")
def export_data_preview_csv(verified_only: bool = False) -> Response:
    dataset = build_data_preview(verified_only=verified_only)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    columns = dataset["columns"]
    writer.writerow([column["label"] for column in columns])
    for row in dataset["rows"]:
        values = []
        for column in columns:
            value = row["values"].get(column["key"], "")
            if column["key"] == "record_number" and re.fullmatch(r"\d{7}", str(value)):
                value = f'="{value}"'
            values.append(value)
        writer.writerow(values)
    filename = "乳腺癌患者数据_仅人工确认.csv" if verified_only else "乳腺癌患者数据_全部当前结果.csv"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


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


@app.delete("/api/patients/{patient_id}", status_code=204)
def delete_patient(patient_id: int) -> None:
    patient = require_patient(patient_id)
    patient_code = str(patient["patient_code"])
    with connect() as db:
        document_ids = [
            str(row["id"])
            for row in db.execute("SELECT id FROM documents WHERE patient_id=?", (patient_id,)).fetchall()
        ]
    # Remove managed files first; if this fails, the database is left intact.
    delete_patient_package(patient_code)
    with connect() as db:
        db.execute("DELETE FROM model_runs WHERE patient_id=?", (patient_id,))
        db.execute("DELETE FROM patients WHERE id=?", (patient_id,))
    for document_id in document_ids:
        _EXTRACTION_PROGRESS.pop(document_id, None)
        _OCR_IN_PROGRESS.discard(document_id)


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
        document_types = {document["id"]: document["document_type"] for document in documents}
        observations = [
            observation for observation in observations
            if not (
                observation["field_name"] == "sex"
                and document_types.get(observation.get("document_id")) == "MEDICAL_RECORD_COVER"
            )
        ]
        field_index = questionnaire_field_index()
        fallback_order = len(field_index)
        for observation in observations:
            metadata = field_index.get(observation["field_name"], {})
            try:
                inference_basis = json.loads(observation.get("derivation_json") or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                inference_basis = []
            observation.update({
                "field_order": metadata.get("field_order", fallback_order),
                "field_label": metadata.get("field_label", observation["field_name"]),
                "field_group": metadata.get("field_group", "other"),
                "field_type": metadata.get("field_type", "string"),
                "field_options": metadata.get("field_options", []),
                "depends_on": metadata.get("depends_on"),
                "inference_basis": inference_basis if isinstance(inference_basis, list) else [],
            })
        observations = consolidate_patient_observations(observations, documents)
        observations, conditional_na_fields = filter_conditionally_applicable_observations(
            observations, field_index
        )
        observations.sort(key=lambda item: (
            item["status"] == "VERIFIED",
            item["field_order"],
            item["created_at"],
            item["id"],
        ))
        for document in documents:
            document["regions"] = rows_as_dicts(
                db.execute("SELECT * FROM regions WHERE document_id=?", (document["id"],)).fetchall()
            )
            ocr_row = db.execute("SELECT * FROM ocr_results WHERE document_id=?", (document["id"],)).fetchone()
            document["ocr"] = dict(ocr_row) if ocr_row else None
    if any(item["status"] == "REVIEW_REQUIRED" for item in observations):
        effective_status = "REVIEW_REQUIRED"
    elif any(item["status"] != "VERIFIED" for item in observations):
        effective_status = "AI_PROCESSED"
    elif observations:
        effective_status = "VERIFIED"
    else:
        effective_status = patient["status"]
    return {
        **patient,
        "status": effective_status,
        "documents": documents,
        "observations": observations,
        "conditional_na_fields": conditional_na_fields,
        "audit_log": audit,
    }


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


@app.put("/api/documents/{document_id}")
async def revise_sanitized_document(
    document_id: str,
    image: UploadFile = File(...),
    display_name: str = Form(...),
    document_type: str = Form("OTHER"),
    sanitization: str = Form(...),
    regions: str = Form("[]"),
) -> dict[str, object]:
    document = require_document(document_id)
    if document_id in _OCR_IN_PROGRESS or _EXTRACTION_PROGRESS.get(document_id, {}).get("status") == "RUNNING":
        raise HTTPException(status_code=409, detail="该图片正在识别，暂时不能修改")
    try:
        metadata = SanitizationMetadata.model_validate_json(sanitization)
        region_list = [RegionInput.model_validate(item) for item in json.loads(regions)]
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid sanitization metadata: {exc}") from exc

    replaced = await replace_sanitized_image(str(document["relative_path"]), image, metadata)
    now = utc_now()
    with connect() as db:
        existing_regions = [
            (row["region_type"], round(float(row["x"]), 3), round(float(row["y"]), 3),
             round(float(row["width"]), 3), round(float(row["height"]), 3))
            for row in db.execute(
                "SELECT region_type,x,y,width,height FROM regions WHERE document_id=? ORDER BY region_type,x,y",
                (document_id,),
            ).fetchall()
        ]
        submitted_regions = sorted(
            (region.region_type, round(region.x, 3), round(region.y, 3),
             round(region.width, 3), round(region.height, 3))
            for region in region_list
        )
        if replaced["sha256"] == document["sha256"] and submitted_regions == existing_regions:
            raise HTTPException(status_code=409, detail="图片和ROI没有变化，不能重新OCR")
        invalidated = db.execute(
            "SELECT COUNT(*) FROM observations WHERE document_id=?", (document_id,)
        ).fetchone()[0]
        had_ocr = bool(db.execute(
            "SELECT 1 FROM ocr_results WHERE document_id=?", (document_id,)
        ).fetchone())
        db.execute("DELETE FROM observations WHERE document_id=?", (document_id,))
        db.execute("DELETE FROM ocr_results WHERE document_id=?", (document_id,))
        db.execute("DELETE FROM regions WHERE document_id=?", (document_id,))
        created_regions = []
        for region in region_list:
            region_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO regions VALUES(?,?,?,?,?,?,?,?,?)",
                (region_id, document_id, region.region_type, region.label, region.x, region.y,
                 region.width, region.height, now),
            )
            created_regions.append({"id": region_id, **region.model_dump()})
        status = "ANNOTATED" if region_list else "SANITIZED"
        db.execute(
            """UPDATE documents SET display_name=?,document_type=?,status=?,sha256=?,width=?,height=?,
               sanitization_json=? WHERE id=?""",
            (display_name, document_type, status, replaced["sha256"], replaced["width"], replaced["height"],
             replaced["sanitization_json"], document_id),
        )
        db.execute(
            """INSERT INTO audit_log
               (patient_id,document_id,operation,old_value,new_value,operator,reason,timestamp)
               VALUES(?,?,?,?,?,?,?,?)""",
            (document["patient_id"], document_id, "USER_REVISE_DOCUMENT", document["sha256"],
             replaced["sha256"], "local-user",
             f"脱敏图片已修改；旧OCR={had_ocr}；失效AI字段={invalidated}", now),
        )
        counts = db.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status='REVIEW_REQUIRED' THEN 1 ELSE 0 END) AS review,
                      SUM(CASE WHEN status NOT IN ('VERIFIED','SUPERSEDED') THEN 1 ELSE 0 END) AS unverified
               FROM observations WHERE patient_id=?""",
            (document["patient_id"],),
        ).fetchone()
        if counts["review"]:
            patient_status = "REVIEW_REQUIRED"
        elif counts["unverified"]:
            patient_status = "AI_PROCESSED"
        elif counts["total"]:
            patient_status = "VERIFIED"
        else:
            patient_status = "UNPROCESSED"
        db.execute(
            "UPDATE patients SET status=?,updated_at=? WHERE id=?",
            (patient_status, now, document["patient_id"]),
        )
    _EXTRACTION_PROGRESS.pop(document_id, None)
    return {
        "id": document_id,
        "display_name": display_name,
        "document_type": document_type,
        "status": status,
        **replaced,
        "regions": created_regions,
        "invalidated_ocr": had_ocr,
        "invalidated_observations": invalidated,
    }


@app.get("/api/documents/{document_id}/image")
def get_document_image(document_id: str) -> FileResponse:
    with connect() as db:
        row = db.execute("SELECT relative_path FROM documents WHERE id=?", (document_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(safe_data_file(row["relative_path"]), media_type="image/png")


def require_document(document_id: str) -> dict[str, object]:
    with connect() as db:
        row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: str) -> None:
    document = require_document(document_id)
    image_path = safe_data_file(str(document["relative_path"]))
    image_path.unlink(missing_ok=True)
    now = utc_now()
    patient_id = int(document["patient_id"])
    with connect() as db:
        db.execute(
            """INSERT INTO audit_log
               (patient_id,document_id,operation,old_value,operator,reason,timestamp)
               VALUES(?,?,?,?,?,?,?)""",
            (patient_id, document_id, "USER_DELETE_DOCUMENT", document["display_name"], "local-user",
             "删除脱敏图片及其ROI、OCR和AI抽取字段", now),
        )
        db.execute("DELETE FROM observations WHERE document_id=?", (document_id,))
        db.execute("DELETE FROM documents WHERE id=?", (document_id,))
        counts = db.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status='REVIEW_REQUIRED' THEN 1 ELSE 0 END) AS review,
                      SUM(CASE WHEN status NOT IN ('VERIFIED','SUPERSEDED') THEN 1 ELSE 0 END) AS unverified
               FROM observations WHERE patient_id=?""",
            (patient_id,),
        ).fetchone()
        document_count = db.execute("SELECT COUNT(*) FROM documents WHERE patient_id=?", (patient_id,)).fetchone()[0]
        if counts["review"]:
            patient_status = "REVIEW_REQUIRED"
        elif counts["unverified"]:
            patient_status = "AI_PROCESSED"
        elif counts["total"]:
            patient_status = "VERIFIED"
        else:
            patient_status = "UNPROCESSED"
        if document_count and not counts["total"]:
            patient_status = "UNPROCESSED"
        db.execute("UPDATE patients SET status=?,updated_at=? WHERE id=?", (patient_status, now, patient_id))


@app.post("/api/documents/{document_id}/ocr")
async def process_document_ocr(document_id: str) -> dict[str, object]:
    document = require_document(document_id)
    with connect() as db:
        if db.execute("SELECT 1 FROM ocr_results WHERE document_id=?", (document_id,)).fetchone():
            raise HTTPException(status_code=409, detail="当前图片版本已完成OCR；只有修改并覆盖图片后才能重新识别")
    if document_id in _OCR_IN_PROGRESS:
        raise HTTPException(status_code=409, detail="该图片正在进行OCR")
    _OCR_IN_PROGRESS.add(document_id)
    try:
        result = await recognize_image(safe_data_file(str(document["relative_path"])))
    finally:
        _OCR_IN_PROGRESS.discard(document_id)
    now = utc_now()
    with connect() as db:
        db.execute(
            """INSERT INTO ocr_results(document_id,engine,version,full_text,result_json,created_at)
               VALUES(?,?,?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET
               engine=excluded.engine,version=excluded.version,full_text=excluded.full_text,
               result_json=excluded.result_json,created_at=excluded.created_at""",
            (document_id, result["engine"], result.get("version"), result["full_text"],
             json.dumps(result, ensure_ascii=False), now),
        )
        db.execute("UPDATE documents SET status='OCR_PROCESSED' WHERE id=?", (document_id,))
        db.execute("UPDATE patients SET updated_at=? WHERE id=?", (now, document["patient_id"]))
    return {"document_id": document_id, "engine": result["engine"], "version": result.get("version"),
            "full_text": result["full_text"], "line_count": len(result.get("lines", []))}


@app.post("/api/documents/{document_id}/extract")
async def extract_document(document_id: str) -> dict[str, object]:
    document = require_document(document_id)
    running = _EXTRACTION_PROGRESS.get(document_id, {}).get("status") == "RUNNING"
    if running:
        raise HTTPException(status_code=409, detail="该图片的AI提取正在运行")
    with connect() as db:
        ocr_row = db.execute("SELECT * FROM ocr_results WHERE document_id=?", (document_id,)).fetchone()
        existing = db.execute("SELECT COUNT(*) FROM observations WHERE document_id=?", (document_id,)).fetchone()[0]
    if not ocr_row:
        raise HTTPException(status_code=409, detail="请先完成OCR识别")
    if document["status"] == "AI_PROCESSED" or existing:
        raise HTTPException(status_code=409, detail="当前OCR版本已完成AI提取；只有图片修改并产生新OCR后才能再次提取")

    models = await list_extraction_models()
    if not models:
        raise HTTPException(status_code=409, detail="Ollama中尚无可用模型，请先下载或导入GGUF模型")
    model_name = get_selected_ollama_model() or models[0].get("name") or models[0].get("model")
    selected = next((item for item in models if (item.get("name") or item.get("model")) == model_name), None)
    if selected is None:
        model_name = models[0].get("name") or models[0].get("model")
        selected = models[0]
        save_selected_ollama_model(str(model_name))
    model_digest = selected.get("digest")
    document_type = str(document["document_type"])
    regular_prompt, regular_fields = extraction_prompt(
        document_type,
        ocr_row["full_text"],
        exclude_fields=STAGING_FIELDS,
    )
    staging_prompt, staging_fields = extraction_prompt(
        document_type,
        ocr_row["full_text"],
        include_fields=STAGING_FIELDS,
    )
    allowed_fields = regular_fields | staging_fields
    _EXTRACTION_PROGRESS[document_id] = {
        "status": "RUNNING",
        "stage": "MODEL_LOADING",
        "model": str(model_name),
        "generated_tokens": 0,
        "started_monotonic": time.monotonic(),
        "started_at": utc_now(),
    }
    try:
        regular_result = await extract_structured(
            str(model_name),
            regular_prompt,
            lambda values: update_extraction_progress(document_id, **values),
            think=False,
        )
        regular_metrics = regular_result.pop("_ollama_metrics", {})
        results = list(regular_result.get("observations", []))
        metrics_list = [regular_metrics]
        token_offset = int(regular_metrics.get("eval_count") or 0)
        if staging_fields:
            update_extraction_progress(document_id, stage="TNM_MODEL_LOADING", generated_tokens=token_offset)

            def staging_progress(values: dict[str, object]) -> None:
                stage = str(values.get("stage") or "TNM_THINKING")
                stage = {
                    "THINKING": "TNM_THINKING",
                    "GENERATING_JSON": "TNM_GENERATING_JSON",
                    "VALIDATING": "TNM_VALIDATING",
                }.get(stage, stage)
                generated = token_offset + int(values.get("generated_tokens") or 0)
                update_extraction_progress(document_id, stage=stage, generated_tokens=generated)

            staging_result = await extract_structured(
                str(model_name),
                staging_prompt,
                staging_progress,
                think=True,
            )
            metrics_list.append(staging_result.pop("_ollama_metrics", {}))
            results.extend(staging_result.get("observations", []))
        result = {"observations": results}
    except Exception as exc:
        update_extraction_progress(document_id, status="FAILED", stage="FAILED", error=str(exc))
        raise
    update_extraction_progress(document_id, stage="SAVING")
    metrics = {
        "eval_count": sum(int(item.get("eval_count") or 0) for item in metrics_list),
        "eval_duration": sum(int(item.get("eval_duration") or 0) for item in metrics_list),
    }
    now = utc_now()
    created: list[dict[str, str]] = []
    with connect() as db:
        seen_fields: set[str] = set()
        for item in result.get("observations", []):
            field_name = item.get("field_name")
            value = item.get("value")
            if field_name not in allowed_fields or value in (None, "") or field_name in seen_fields:
                continue
            value = normalize_observation_value(field_name, value)
            if not value:
                continue
            if (
                field_name in IMMUNOTHERAPY_FIELDS
                and str(value).upper() not in {"NO", "NOT_APPLICABLE"}
                and not immunotherapy_evidence_is_valid(str(ocr_row["full_text"]))
            ):
                db.execute(
                    """INSERT INTO audit_log
                       (patient_id,document_id,field_name,operation,new_value,operator,reason,timestamp)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (document["patient_id"], document_id, field_name, "AI_REJECT_CONTEXT", str(value),
                     "AI", "支持治疗/升白语境不属于抗肿瘤免疫治疗", now),
                )
                continue
            if not observation_value_is_valid(field_name, value):
                db.execute(
                    """INSERT INTO audit_log
                       (patient_id,document_id,field_name,operation,new_value,operator,reason,timestamp)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (document["patient_id"], document_id, field_name, "AI_REJECT_INVALID_VALUE", str(value),
                     "AI", "模型输出不符合问卷字段值域", now),
                )
                continue
            seen_fields.add(field_name)
            source_mode = item.get("source_mode", "RECORDED")
            confidence = item.get("confidence", "LOW")
            basis = item.get("inference_basis", [])
            if source_mode == "INFERRED":
                confidence = "MEDIUM" if confidence == "HIGH" else confidence
                if not basis:
                    continue
            status = (
                "REVIEW_REQUIRED"
                if source_mode == "INFERRED" or confidence in {"LOW", "MEDIUM"}
                else "AI_PROCESSED"
            )
            observation_id = uuid.uuid4().hex
            db.execute(
                """INSERT INTO observations
                   (id,patient_id,document_id,field_name,ai_value,current_value,raw_text,confidence,status,
                    source_mode,derivation_json,ruleset_version,model_name,model_digest,prompt_version,
                    ocr_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (observation_id, document["patient_id"], document_id, field_name, str(value), str(value),
                 item.get("raw_text"), confidence, status, source_mode, json.dumps(basis, ensure_ascii=False),
                 "AJCC-breast-8-local-v1" if source_mode == "INFERRED" else None, model_name, model_digest,
                 "document-extraction-v2", ocr_row["version"], now, now),
            )
            db.execute(
                """INSERT INTO audit_log
                   (patient_id,document_id,field_name,operation,new_value,operator,model_name,model_digest,timestamp)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (document["patient_id"], document_id, field_name,
                 "AI_INFER" if source_mode == "INFERRED" else "AI_EXTRACT", str(value), "AI",
                 model_name, model_digest, now),
            )
            created.append({"id": observation_id, "field_name": field_name, "status": status})
        default_field = "metastatic_at_presentation"
        if (
            document["document_type"] in {"ADMISSION", "DISCHARGE"}
            and default_field in allowed_fields
            and default_field not in seen_fields
            and not db.execute(
                """SELECT 1 FROM observations
                   WHERE patient_id=? AND field_name=? AND status!='SUPERSEDED' LIMIT 1""",
                (document["patient_id"], default_field),
            ).fetchone()
        ):
            observation_id = uuid.uuid4().hex
            basis = [{"rule": "metastatic_at_presentation_default", "fact": "本页未见明确来院时远处转移记录"}]
            db.execute(
                """INSERT INTO observations
                   (id,patient_id,document_id,field_name,ai_value,current_value,raw_text,confidence,status,
                    source_mode,derivation_json,ruleset_version,model_name,model_digest,prompt_version,
                    ocr_version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (observation_id, document["patient_id"], document_id, default_field, "NO", "NO",
                 "未见明确来院时远处转移记录", "MEDIUM", "REVIEW_REQUIRED", "INFERRED",
                 json.dumps(basis, ensure_ascii=False), "cohort-preferences-v1", model_name, model_digest,
                 "document-extraction-v2", ocr_row["version"], now, now),
            )
            db.execute(
                """INSERT INTO audit_log
                   (patient_id,document_id,field_name,operation,new_value,operator,reason,model_name,model_digest,timestamp)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (document["patient_id"], document_id, default_field, "AI_DEFAULT", "NO", "AI",
                 "队列口径：未明确提及来院时远处转移时默认否", model_name, model_digest, now),
            )
            created.append({"id": observation_id, "field_name": default_field, "status": "REVIEW_REQUIRED"})
        status_counts = db.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status='REVIEW_REQUIRED' THEN 1 ELSE 0 END) AS review,
                      SUM(CASE WHEN status NOT IN ('VERIFIED','SUPERSEDED') THEN 1 ELSE 0 END) AS unverified
               FROM observations WHERE patient_id=?""",
            (document["patient_id"],),
        ).fetchone()
        if status_counts["review"]:
            patient_status = "REVIEW_REQUIRED"
        elif status_counts["unverified"]:
            patient_status = "AI_PROCESSED"
        elif status_counts["total"]:
            patient_status = "VERIFIED"
        else:
            patient_status = "UNPROCESSED"
        db.execute("UPDATE documents SET status='AI_PROCESSED' WHERE id=?", (document_id,))
        db.execute(
            "UPDATE patients SET status=?,updated_at=? WHERE id=?",
            (patient_status, now, document["patient_id"]),
        )
    eval_count = int(metrics.get("eval_count") or 0)
    eval_duration = int(metrics.get("eval_duration") or 0)
    token_rate = eval_count / (eval_duration / 1_000_000_000) if eval_duration else 0
    update_extraction_progress(
        document_id,
        status="COMPLETED",
        stage="COMPLETED",
        generated_tokens=eval_count,
        token_rate=round(token_rate, 2),
        finished_at=utc_now(),
    )
    return {"document_id": document_id, "model": model_name, "model_digest": model_digest,
            "observation_count": len(created), "observations": created,
            "performance": {"eval_count": eval_count, "token_rate": round(token_rate, 2)}}


@app.get("/api/documents/{document_id}/extract-progress")
async def get_extract_progress(document_id: str) -> dict[str, object]:
    require_document(document_id)
    state = dict(_EXTRACTION_PROGRESS.get(document_id, {"status": "IDLE", "stage": "IDLE"}))
    started = state.pop("started_monotonic", None)
    generation_started = state.pop("generation_started_monotonic", None)
    now = time.monotonic()
    state["elapsed_seconds"] = round(now - float(started), 1) if started else 0
    generated = int(state.get("generated_tokens") or 0)
    if not state.get("token_rate") and generation_started and now > float(generation_started):
        state["token_rate"] = round(generated / (now - float(generation_started)), 2)
    try:
        state.update(await ollama_runtime_status())
    except HTTPException:
        state.update({"processor": "UNAVAILABLE", "vram_bytes": 0})
    return state


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
    normalized_value = normalize_observation_value(payload.field_name, payload.value)
    status = (
        "REVIEW_REQUIRED"
        if payload.source_mode == "INFERRED" or payload.confidence in {"LOW", "MEDIUM"}
        else "AI_PROCESSED"
    )
    with connect() as db:
        db.execute(
            """INSERT INTO observations
               (id,patient_id,document_id,region_id,field_name,ai_value,current_value,raw_text,
                confidence,status,source_mode,derivation_json,ruleset_version,model_name,model_digest,
                prompt_version,ocr_version,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (observation_id, patient_id, payload.document_id, payload.region_id, payload.field_name,
             normalized_value, normalized_value, payload.raw_text, payload.confidence, status, payload.source_mode,
             json.dumps(payload.inference_basis, ensure_ascii=False), payload.ruleset_version,
             payload.model_name, payload.model_digest, payload.prompt_version, payload.ocr_version,
             now, now),
        )
        db.execute(
            """INSERT INTO audit_log
               (patient_id,document_id,field_name,operation,new_value,operator,model_name,model_digest,timestamp)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (patient_id, payload.document_id, payload.field_name,
             "AI_INFER" if payload.source_mode == "INFERRED" else "AI_EXTRACT", normalized_value, "AI",
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
    normalized_value = normalize_observation_value(observation["field_name"], payload.value)
    was_verified = observation["status"] == "VERIFIED"
    next_status = "VERIFIED" if was_verified else "REVIEW_REQUIRED"
    next_confidence = "VERIFIED" if was_verified else "LOW"
    with connect() as db:
        db.execute(
            "UPDATE observations SET current_value=?,status=?,confidence=?,updated_at=? WHERE id=?",
            (normalized_value, next_status, next_confidence, now, observation_id),
        )
        db.execute(
            """INSERT INTO audit_log
               (patient_id,document_id,field_name,operation,old_value,new_value,operator,reason,timestamp)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (observation["patient_id"], observation["document_id"], observation["field_name"],
             "USER_EDIT_VERIFIED" if was_verified else "USER_EDIT",
             observation["current_value"], normalized_value, payload.operator, payload.reason, now),
        )
        if not was_verified:
            db.execute(
                "UPDATE patients SET status='REVIEW_REQUIRED',updated_at=? WHERE id=?",
                (now, observation["patient_id"]),
            )
        else:
            remaining = db.execute(
                "SELECT COUNT(*) FROM observations WHERE patient_id=? AND status NOT IN ('VERIFIED','SUPERSEDED')",
                (observation["patient_id"],),
            ).fetchone()[0]
            db.execute(
                "UPDATE patients SET status=?,updated_at=? WHERE id=?",
                ("VERIFIED" if remaining == 0 else "REVIEW_REQUIRED", now, observation["patient_id"]),
            )
    return {"id": observation_id, "value": normalized_value, "status": next_status}


@app.post("/api/observations/{observation_id}/verify")
def verify_observation(observation_id: str, payload: ObservationVerify) -> dict[str, str]:
    observation = get_observation(observation_id)
    now = utc_now()
    with connect() as db:
        sibling_rows = db.execute(
            """SELECT id,current_value FROM observations
               WHERE patient_id=? AND field_name=? AND id!=? AND status!='SUPERSEDED'""",
            (observation["patient_id"], observation["field_name"], observation_id),
        ).fetchall()
        if sibling_rows:
            sibling_ids = [row["id"] for row in sibling_rows]
            placeholders = ",".join("?" for _ in sibling_ids)
            db.execute(
                f"UPDATE observations SET status='SUPERSEDED',updated_at=? WHERE id IN ({placeholders})",
                (now, *sibling_ids),
            )
            db.execute(
                """INSERT INTO audit_log
                   (patient_id,document_id,field_name,operation,old_value,new_value,operator,reason,timestamp)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (observation["patient_id"], observation["document_id"], observation["field_name"],
                 "USER_RESOLVE_FIELD_CANDIDATES",
                 json.dumps([row["current_value"] for row in sibling_rows], ensure_ascii=False),
                 observation["current_value"], payload.operator, "人工确认患者级字段，其他候选保留为已归并历史", now),
            )
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
            "SELECT COUNT(*) FROM observations WHERE patient_id=? AND status NOT IN ('VERIFIED','SUPERSEDED')",
            (observation["patient_id"],),
        ).fetchone()[0]
        if remaining == 0:
            db.execute(
                "UPDATE patients SET status='VERIFIED',updated_at=? WHERE id=?",
                (now, observation["patient_id"]),
            )
    return {"id": observation_id, "status": "VERIFIED", "confidence": "VERIFIED"}


@app.get("/api/models/local-files")
async def local_model_files() -> list[dict[str, object]]:
    source_digests = await model_source_digests()
    results = []
    for item in scan_gguf_files():
        digest = await asyncio.to_thread(cached_file_sha256, resolve_gguf(str(item["filename"])))
        results.append({**item, "sha256": digest, "imported": digest in source_digests,
                        "model_names": source_digests.get(digest, [])})
    return results


@app.get("/api/settings/ollama-provider")
async def get_ollama_provider_setting() -> dict[str, object]:
    runtime = get_ollama_provider()
    return {**runtime, "health": await ollama_health()}


@app.post("/api/settings/ollama-provider")
async def update_ollama_provider_setting(payload: OllamaProviderUpdate) -> dict[str, object]:
    endpoint = ollama_provider_endpoints()[payload.provider]
    health = await ollama_health(endpoint)
    if not health["available"]:
        description = (
            "Windows Ollama未启动或未允许Docker访问"
            if payload.provider == "WINDOWS_HOST"
            else "Docker Ollama未启动"
        )
        raise HTTPException(status_code=409, detail=f"{description}：{health.get('error', '连接失败')}")
    runtime = save_ollama_provider(payload.provider)
    return {**runtime, "health": {**health, "provider": payload.provider}}


@app.get("/api/models/installed")
async def installed_models() -> list[dict[str, object]]:
    selected = get_selected_ollama_model()
    models = await list_model_groups()
    selectable_names = {alias for model in models for alias in model.get("aliases", [])}
    if selected not in selectable_names and models:
        selected = str(models[0].get("name") or models[0].get("model"))
        save_selected_ollama_model(selected)
    return [
        {
            **model,
            "selected": selected in model.get("aliases", []),
            "selected_name": selected if selected in model.get("aliases", []) else None,
            "selectable": True,
        }
        for model in models
    ]


@app.get("/api/settings/ollama-model")
async def get_ollama_model_setting() -> dict[str, object]:
    runtime = get_ollama_provider()
    models = await list_extraction_models()
    names = [str(model.get("name") or model.get("model")) for model in models]
    selected = get_selected_ollama_model(runtime["provider"])
    if selected not in names:
        selected = names[0] if names else ""
        if selected:
            save_selected_ollama_model(selected, runtime["provider"])
    return {"provider": runtime["provider"], "model": selected, "models": names}


@app.post("/api/settings/ollama-model")
async def update_ollama_model_setting(payload: OllamaModelUpdate) -> dict[str, str]:
    runtime = get_ollama_provider()
    models = await list_extraction_models()
    names = {str(model.get("name") or model.get("model")) for model in models}
    if payload.model not in names:
        raise HTTPException(status_code=409, detail="所选模型不在当前 Ollama 中，请刷新模型列表")
    return save_selected_ollama_model(payload.model, runtime["provider"])


@app.post("/api/models/import")
async def import_model(payload: ModelImportRequest) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.gguf", payload.filename):
        raise HTTPException(status_code=422, detail="Invalid GGUF filename")
    resolve_gguf(payload.filename)
    result = await import_gguf(payload.filename, payload.model_name)
    return {"status": "imported", "model": payload.model_name, "ollama": result}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
