from typing import Literal

from pydantic import BaseModel, Field, field_validator

PatientStatus = Literal["UNPROCESSED", "AI_PROCESSED", "REVIEW_REQUIRED", "VERIFIED"]
Confidence = Literal["LOW", "MEDIUM", "HIGH", "VERIFIED"]


class PatientCreate(BaseModel):
    patient_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")


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
    document_id: str | None = None
    region_id: str | None = None
    model_name: str | None = None
    model_digest: str | None = None
    prompt_version: str | None = None
    ocr_version: str | None = None


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

