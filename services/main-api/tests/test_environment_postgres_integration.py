"""PostgreSQL behaviour of the environment schema (skipped without TEST_DATABASE_URL)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Engine, delete, inspect, select
from sqlalchemy.orm import Session

from app.environment.normalizer import normalize_timeseries
from app.environment.repository import insert_reading, latest_reading
from app.environment.worker import acquire_single_worker_lock, release_single_worker_lock
from app.models.environment import EnvironmentReading
from tests.environment_support import real_timeseries_payload


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
    payload = real_timeseries_payload()
    payload["station"] = station_id
    payload["reading"]["values"]["99aa00new0001"] = 1.25
    reading = normalize_timeseries(payload, station_id)
    fetched = datetime(2026, 11, 2, 10, 59, 29, tzinfo=UTC)
    ingested = datetime(2026, 11, 2, 10, 59, 30, tzinfo=UTC)
    with Session(postgres_engine) as db:
        assert insert_reading(db, reading, ingested, fetched) is True
        assert insert_reading(db, reading, ingested, fetched) is False
        db.commit()
        rows = db.scalars(select(EnvironmentReading).where(EnvironmentReading.station_id == station_id)).all()
        stored = latest_reading(db, station_id)

    assert len(rows) == 1
    assert stored is not None
    assert stored.observed_at == datetime(2026, 11, 2, 10, 58, 1, tzinfo=UTC)
    assert stored.ingested_at == ingested
    assert stored.fetched_at == fetched
    assert stored.source_epoch_ms == 1793617081000
    assert stored.unmapped_values == {"99aa00new0001": 1.25}
    assert stored.no_ug_m3 == pytest.approx(2.563264)
    assert stored.raw_payload["reading"]["timestamp"] == "2026-11-02T10:58:01.000Z"


def test_a_second_worker_cannot_take_the_advisory_lock(postgres_engine: Engine) -> None:
    first = acquire_single_worker_lock(postgres_engine)
    assert first is not None, "another environment worker holds the lock on the test database"
    try:
        assert acquire_single_worker_lock(postgres_engine) is None
    finally:
        release_single_worker_lock(first)
    again = acquire_single_worker_lock(postgres_engine)
    assert again is not None  # a restarted worker can take over once the first has stopped
    release_single_worker_lock(again)
