import os
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, inspect


def postgres_url() -> str:
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL", "")


@pytest.fixture(scope="session")
def postgres_engine() -> Engine:
    url = postgres_url()
    if not url.startswith("postgresql"):
        pytest.skip("PostgreSQL integration database is not configured")
    engine = create_engine(url, pool_pre_ping=True)
    if "identity" not in inspect(engine).get_schema_names():
        pytest.fail("business migration is not applied; run alembic upgrade head")
    yield engine
    engine.dispose()


def unique_username(prefix: str) -> str:
    return f"{prefix}.{uuid4().hex[:12]}"
