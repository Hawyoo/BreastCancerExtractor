from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client(tmp_path: Path):
    settings.data_path = tmp_path / "database"
    settings.config_path = tmp_path / "config"
    settings.runtime_path = tmp_path / "runtime"
    settings.database_path = settings.runtime_path / "test.db"
    settings.model_import_path = tmp_path / "models"
    with TestClient(app) as test_client:
        yield test_client
