import hashlib
import io
import json
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.models import SanitizationMetadata

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


async def save_sanitized_image(
    patient_code: str,
    upload: UploadFile,
    metadata: SanitizationMetadata,
) -> dict[str, str | int]:
    """Persist only a browser-reencoded, sanitized image.

    The browser sends a PNG created from a canvas after crop/redaction. The API has no
    raw-image upload endpoint. Pillow decodes and re-encodes it once more, dropping metadata.
    """
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
    document_id = uuid.uuid4().hex
    patient_dir = settings.workspace_path / "patients" / patient_code / "sanitized"
    patient_dir.mkdir(parents=True, exist_ok=True)
    destination = patient_dir / f"{document_id}.png"
    destination.write_bytes(clean_bytes)

    relative_path = destination.relative_to(settings.workspace_path).as_posix()
    return {
        "id": document_id,
        "relative_path": relative_path,
        "sha256": digest,
        "width": width,
        "height": height,
        "sanitization_json": json.dumps(metadata.model_dump(), ensure_ascii=False),
    }


def safe_workspace_file(relative_path: str) -> Path:
    root = settings.workspace_path.resolve()
    candidate = (root / relative_path).resolve()
    if root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return candidate


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

