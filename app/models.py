from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.derived_fields import is_derived_field

PatientStatus = Literal["UNPROCESSED", "AI_PROCESSED", "REVIEW_REQUIRED", "VERIFIED"]
Confidence = Literal["LOW", "MEDIUM", "HIGH", "VERIFIED"]


class PatientCreate(BaseModel):
    patient_code: str = Field(min_length=7, max_length=7, pattern=r"^\d{7}$")


class RegionInput(BaseModel):
    region_type: str = Field(default="OTHER", max_length=80)
    label: str = Field(default="信息区域", max_length=120)
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


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

    @field_validator("field_name")
    @classmethod
    def derived_fields_are_system_owned(cls, value: str) -> str:
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


class ObservationVerify(BaseModel):
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
