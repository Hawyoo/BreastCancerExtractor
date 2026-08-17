from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client(tmp_path: Path):
    settings.database_path = tmp_path / "database" / "test.db"
    settings.workspace_path = tmp_path / "workspace"
    settings.model_import_path = tmp_path / "models"
    with TestClient(app) as test_client:
        yield test_client

