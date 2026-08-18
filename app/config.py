from pathlib import Path
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Breast Cancer Extractor"
    offline_mode: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    ocr_url: str = "http://127.0.0.1:8001"
    default_llm_model: str = ""
    database_path: Path = Path("database/extractor.db")
    workspace_path: Path = Path("workspace")
    model_import_path: Path = Path("models/llm")
    max_sanitized_image_mb: int = 25

    @model_validator(mode="after")
    def enforce_offline_llm_endpoint(self) -> "Settings":
        hostname = urlparse(self.ollama_url).hostname
        allowed = {"ollama", "ocr", "host.docker.internal", "localhost", "127.0.0.1", "::1"}
        ocr_hostname = urlparse(self.ocr_url).hostname
        if self.offline_mode and hostname not in allowed:
            raise ValueError("OFFLINE_MODE only permits an in-process or local Ollama endpoint")
        if self.offline_mode and ocr_hostname not in allowed:
            raise ValueError("OFFLINE_MODE only permits a local OCR endpoint")
        return self


settings = Settings()
