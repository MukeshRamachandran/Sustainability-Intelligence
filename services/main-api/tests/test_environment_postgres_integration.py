"""PostgreSQL behaviour of the environment schema (skipped without TEST_DATABASE_URL)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Engine, delete, inspect, select
from sqlalchemy.orm import Session

from app.environment.normalizer import normalize_reading
from app.environment.repository import insert_reading, latest_reading
from app.models.environment import EnvironmentReading
from tests.environment_support import real_latest_payload


@pytest.fixture
def station_id(postgres_engine: Engine) -> Iterator[str]:
    if "environment" not in inspect(postgres_engine).get_schema_names():
        pytest.fail("environment migration is not applied; run alembic upgrade head")
    station = f"test-{uuid4().hex[:12]}"
    yield station
    with Session(postgres_engine) as db:
        db.execute(delete(EnvironmentReading).where(EnvironmentReading.station_id == station))
        db.commit()


def test_duplicate_observation_is_ignored_and_utc_round_trips(postgres_engine: Engine, station_id: str) -> None:
    reading = normalize_reading(real_latest_payload(), station_id)
    ingested = datetime(2026, 9, 25, 3, 30, tzinfo=UTC)
    with Session(postgres_engine) as db:
        assert insert_reading(db, reading, ingested) is True
        assert insert_reading(db, reading, ingested) is False
        db.commit()
        rows = db.scalars(select(EnvironmentReading).where(EnvironmentReading.station_id == station_id)).all()
        stored = latest_reading(db, station_id)

    assert len(rows) == 1
    assert stored is not None
    assert stored.observed_at == datetime(2026, 9, 24, 22, 34, tzinfo=UTC)
    assert stored.ingested_at == ingested
    assert stored.no_ug_m3 == pytest.approx(0.000789)
    assert stored.raw_payload["recordedAt"] == "2026-09-24T22:34:00.000Z"
