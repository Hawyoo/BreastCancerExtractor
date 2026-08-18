import hashlib
import io
import json
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.models import SanitizationMetadata

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


async def prepare_sanitized_image(
    upload: UploadFile,
    metadata: SanitizationMetadata,
) -> dict[str, str | int]:
    max_bytes = settings.max_sanitized_image_mb * 1024 * 1024
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="Sanitized image is too large")
    if not content.startswith(PNG_SIGNATURE):
        raise HTTPException(status_code=415, detail="Only canvas-reencoded PNG is accepted")

    try:
        with Image.open(io.BytesIO(content)) as source:
            source.verify()
        with Image.open(io.BytesIO(content)) as source:
            clean = source.convert("RGB")
            width, height = clean.size
            output = io.BytesIO()
            clean.save(output, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=415, detail="Invalid sanitized image") from exc

    clean_bytes = output.getvalue()
    digest = hashlib.sha256(clean_bytes).hexdigest()
    return {
        "content": clean_bytes,
        "sha256": digest,
        "width": width,
        "height": height,
        "sanitization_json": json.dumps(metadata.model_dump(), ensure_ascii=False),
    }


async def save_sanitized_image(
    patient_code: str,
    upload: UploadFile,
    metadata: SanitizationMetadata,
) -> dict[str, str | int]:
    """Persist only a browser-reencoded, sanitized image."""
    prepared = await prepare_sanitized_image(upload, metadata)
    document_id = uuid.uuid4().hex
    patient_dir = settings.workspace_path / "patients" / patient_code / "sanitized"
    patient_dir.mkdir(parents=True, exist_ok=True)
    destination = patient_dir / f"{document_id}.png"
    destination.write_bytes(prepared.pop("content"))

    relative_path = destination.relative_to(settings.workspace_path).as_posix()
    return {
        "id": document_id,
        "relative_path": relative_path,
        **prepared,
    }


async def replace_sanitized_image(
    relative_path: str,
    upload: UploadFile,
    metadata: SanitizationMetadata,
) -> dict[str, str | int]:
    """Replace an existing sanitized image with a newly edited sanitized PNG."""
    prepared = await prepare_sanitized_image(upload, metadata)
    destination = safe_workspace_file(relative_path)
    temporary = destination.with_suffix(".updating.png")
    temporary.write_bytes(prepared.pop("content"))
    temporary.replace(destination)
    return prepared


def safe_workspace_file(relative_path: str) -> Path:
    root = settings.workspace_path.resolve()
    candidate = (root / relative_path).resolve()
    if root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return candidate


def delete_patient_workspace(patient_code: str) -> None:
    """Delete only the exact managed workspace directory for one patient."""
    patients_root = (settings.workspace_path / "patients").resolve()
    patient_dir = (patients_root / patient_code).resolve()
    if patient_dir.parent != patients_root:
        raise HTTPException(status_code=400, detail="Invalid patient workspace path")
    if patient_dir.is_dir():
        shutil.rmtree(patient_dir)


def scan_gguf_files() -> list[dict[str, str | int]]:
    root = settings.model_import_path
    root.mkdir(parents=True, exist_ok=True)
    return [
        {"filename": item.name, "size": item.stat().st_size}
        for item in sorted(root.glob("*.gguf"))
        if item.is_file()
    ]


def resolve_gguf(filename: str) -> Path:
    root = settings.model_import_path.resolve()
    candidate = (root / filename).resolve()
    if candidate.parent != root or candidate.suffix.lower() != ".gguf" or not candidate.is_file():
        raise HTTPException(status_code=404, detail="GGUF file not found")
    return candidate
