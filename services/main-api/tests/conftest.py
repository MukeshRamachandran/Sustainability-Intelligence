from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.config import Settings
from app.main import create_app
from tests.integration_support import postgres_engine as postgres_engine


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+psycopg://test:test@localhost:5432/test",
        EVIDENCE_ROOT=tmp_path / "evidence",
    )


@pytest.fixture
def application(test_settings: Settings) -> FastAPI:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    return create_app(test_settings, engine)


@pytest.fixture
def client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(application) as test_client:
        yield test_client
