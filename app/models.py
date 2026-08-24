import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.derived_fields import is_derived_field

PatientStatus = Literal["UNPROCESSED", "AI_PROCESSED", "REVIEW_REQUIRED", "VERIFIED"]
Confidence = Literal["LOW", "MEDIUM", "HIGH", "VERIFIED"]

ADDITIONAL_LESION_FIELD_PREFIX = "additional_malignant_lesion:"
ADDITIONAL_LESION_SCHEMA = "BCE_ADDITIONAL_MALIGNANT_LESION_V1"
MALIGNANCY_POSITIVE_PATTERN = re.compile(
    r"(乳腺癌|癌灶|癌组织|癌细胞|浸润性[^，。;；\n]{0,20}癌|原位癌|恶性病灶|恶性肿瘤|"
    r"明确恶性|\bcarcinoma\b|\bmalignan(?:t|cy)\b|BI\s*-?\s*RADS\s*6)",
    re.IGNORECASE,
)
MALIGNANCY_NEGATIVE_PATTERN = re.compile(
    r"(未见[^，。;；\n]{0,10}(?:恶性|癌)|无[^，。;；\n]{0,10}(?:恶性|癌)|"
    r"排除[^，。;；\n]{0,10}(?:恶性|癌)|倾向良性|考虑良性|明确良性)",
    re.IGNORECASE,
)

WINDOWS_RESERVED_PATIENT_IDS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
PATIENT_ID_INVALID_CHARS = set('<>:"/\\|?*')


def validate_patient_id(value: str) -> str:
    """Keep the user-provided folder name as the patient ID while remaining path-safe."""
    if not value or not value.strip():
        raise ValueError("Patient ID cannot be empty")
    if len(value) > 120:
        raise ValueError("Patient ID is too long")
    if value in {".", ".."}:
        raise ValueError("Patient ID cannot be . or ..")
    if value.endswith((" ", ".")):
        raise ValueError("Patient ID cannot end with a space or dot")
    if any(ord(char) < 32 for char in value) or any(char in PATIENT_ID_INVALID_CHARS for char in value):
        raise ValueError("Patient ID contains characters that cannot be used in a patient folder")
    if value.split(".", 1)[0].upper() in WINDOWS_RESERVED_PATIENT_IDS:
        raise ValueError("Patient ID is a reserved Windows folder name")
    return value


class PatientCreate(BaseModel):
    patient_code: str = Field(min_length=1, max_length=120)

    @field_validator("patient_code")
    @classmethod
    def patient_id_must_be_safe_folder_name(cls, value: str) -> str:
        return validate_patient_id(value)


class RegionInput(BaseModel):
    region_type: str = Field(default="OTHER", max_length=80)
    label: str = Field(default="信息区域", max_length=120)
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class DocumentRegionsUpdate(BaseModel):
    regions: list[RegionInput] = Field(default_factory=list, max_length=200)
    operator: str = Field(default="local-user", min_length=1, max_length=80)


class FieldReextractRequest(BaseModel):
    field_name: str = Field(min_length=1, max_length=160)
    region_ids: list[str] = Field(default_factory=list, max_length=20)
    operator: str = Field(default="local-user", min_length=1, max_length=80)

    @field_validator("field_name")
    @classmethod
    def derived_fields_cannot_be_reextracted(cls, value: str) -> str:
        if is_derived_field(value):
            raise ValueError("Derived fields are read-only; re-extract the complete source field instead")
        return value


class SanitizationMetadata(BaseModel):
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    crop: dict[str, float]
    redaction_count: int = Field(ge=0)
    client_reencoded: bool
    enhancement_mode: Literal["ORIGINAL", "ENHANCED"] = "ORIGINAL"
    enhancement_version: str | None = None
    # Optional editor-only geometry metadata. The sanitized bitmap remains the
    # authoritative privacy artifact; this merely restores rotated ROI handles.
    transforms: dict[str, object] | None = None

    @field_validator("client_reencoded")
    @classmethod
    def must_be_reencoded(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Only client-reencoded sanitized images may be imported")
        return value


class ObservationCreate(BaseModel):
    field_name: str = Field(min_length=1, max_length=160)
    value: str | None = None
    raw_text: str | None = None
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    source_mode: Literal["RECORDED", "INFERRED"] = "RECORDED"
    inference_basis: list[dict[str, str | None]] = Field(default_factory=list)
    ruleset_version: str | None = None
    document_id: str | None = None
    region_id: str | None = None
    model_name: str | None = None
    model_digest: str | None = None
    prompt_version: str | None = None
    ocr_version: str | None = None
    operator: str = Field(default="AI", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("field_name")
    @classmethod
    def derived_fields_are_system_owned(cls, value: str) -> str:
        if value.startswith(ADDITIONAL_LESION_FIELD_PREFIX):
            raise ValueError("Additional lesions must be created through the dedicated lesion API")
        if is_derived_field(value):
            raise ValueError("Derived fields are read-only; edit and verify the complete source field instead")
        return value

    @model_validator(mode="after")
    def validate_inference_provenance(self) -> "ObservationCreate":
        if self.source_mode == "INFERRED":
            if not self.inference_basis or not self.ruleset_version:
                raise ValueError("Inferred values require inference_basis and ruleset_version")
            if self.confidence == "HIGH":
                raise ValueError("Inferred values cannot be HIGH before human verification")
        return self


class ObservationEdit(BaseModel):
    value: str | None = None
    operator: str = Field(default="local-user", min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=500)


class ObservationEvidenceLocation(BaseModel):
    document_id: str = Field(min_length=1, max_length=80)
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    operator: str = Field(default="local-user", min_length=1, max_length=80)


class AdditionalLesionWrite(BaseModel):
    """Human-reviewed, lesion-specific fields kept outside the patient-wide questionnaire."""

    active: bool = True
    lesion_label: str = Field(default="", max_length=120)
    laterality: Literal["LEFT", "RIGHT"]
    location: str = Field(default="", max_length=300)
    size_text: str = Field(default="", max_length=300)
    ultrasound_detail: str = Field(default="", max_length=2000)
    mammography_detail: str = Field(default="", max_length=2000)
    mri_detail: str = Field(default="", max_length=2000)
    pathology_type: str = Field(default="", max_length=500)
    pathology_grade: str = Field(default="", max_length=120)
    er: str = Field(default="", max_length=300)
    pr: str = Field(default="", max_length=300)
    her2: str = Field(default="", max_length=300)
    ki67: str = Field(default="", max_length=300)
    other_ihc: str = Field(default="", max_length=2000)
    malignancy_basis: str = Field(min_length=1, max_length=2000)
    document_id: str | None = Field(default=None, max_length=160)
    region_id: str | None = Field(default=None, max_length=160)
    operator: str = Field(default="local-user", min_length=1, max_length=80)

    @field_validator(
        "lesion_label", "location", "size_text", "ultrasound_detail", "mammography_detail",
        "mri_detail", "pathology_type", "pathology_grade", "er", "pr", "her2", "ki67",
        "other_ihc", "malignancy_basis",
    )
    @classmethod
    def trim_text_fields(cls, value: str) -> str:
        return value.strip()

    @field_validator("malignancy_basis")
    @classmethod
    def require_explicit_malignancy(cls, value: str) -> str:
        if MALIGNANCY_NEGATIVE_PATTERN.search(value) or not MALIGNANCY_POSITIVE_PATTERN.search(value):
            raise ValueError("附加病灶必须提供明确恶性依据；多发良性结节、囊肿或纤维腺瘤不能添加")
        return value


class ObservationVerify(BaseModel):
    value: str | None = None
    candidate_id: str | None = Field(default=None, max_length=80)
    evidence_location: ObservationEvidenceLocation | None = None
    operator: str = Field(default="local-user", min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class DocumentTypeUpdate(BaseModel):
    document_type: str = Field(min_length=1, max_length=80)
    operator: str = Field(default="local-user", min_length=1, max_length=80)


class ModelImportRequest(BaseModel):
    filename: str
    model_name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")


class OllamaProviderUpdate(BaseModel):
    provider: Literal["DISABLED", "DOCKER", "WINDOWS_HOST"]


class OllamaModelUpdate(BaseModel):
    model: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:/-]+$")


class PatientPackageImport(BaseModel):
    package_name: str = Field(min_length=1, max_length=160, pattern=r"^[^/\\]+$")
    action: Literal["IMPORT_NEW", "KEEP_LOCAL", "USE_EXTERNAL", "MERGE"]
