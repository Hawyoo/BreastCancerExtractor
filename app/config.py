from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.paths import portable_path, portable_root, resource_root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=portable_root() / ".env", extra="ignore")

    app_name: str = "Breast Cancer Extractor"
    runtime_mode: Literal["docker", "windows_native"] = "windows_native"
    offline_mode: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    ocr_url: str = "http://127.0.0.1:8001"
    default_llm_model: str = ""
    database_path: Path = Field(default_factory=lambda: portable_root() / "database" / "extractor.db")
    workspace_path: Path = Field(default_factory=lambda: portable_root() / "workspace")
    model_import_path: Path = Field(default_factory=lambda: portable_root() / "models" / "llm")
    knowledge_path: Path = Field(default_factory=lambda: resource_root() / "knowledge")
    max_sanitized_image_mb: int = 25

    @model_validator(mode="after")
    def enforce_offline_llm_endpoint(self) -> "Settings":
        self.database_path = portable_path(self.database_path)
        self.workspace_path = portable_path(self.workspace_path)
        self.model_import_path = portable_path(self.model_import_path)
        if not self.knowledge_path.is_absolute():
            self.knowledge_path = resource_root() / self.knowledge_path
        hostname = urlparse(self.ollama_url).hostname
        allowed = {"ollama", "ocr", "host.docker.internal", "localhost", "127.0.0.1", "::1"}
        ocr_hostname = urlparse(self.ocr_url).hostname
        if self.offline_mode and hostname not in allowed:
            raise ValueError("OFFLINE_MODE only permits an in-process or local Ollama endpoint")
        if self.offline_mode and ocr_hostname not in allowed:
            raise ValueError("OFFLINE_MODE only permits a local OCR endpoint")
        return self


settings = Settings()
