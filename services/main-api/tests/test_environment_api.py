from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.environment.normalizer import normalize_timeseries
from app.environment.parameters import PARAMETER_MAP
from app.environment.repository import insert_reading
from app.main import create_app
from app.models.environment import EnvironmentIngestionRun, EnvironmentReading
from app.schemas.environment import EnvironmentReadingResponse
from tests.environment_support import environment_sqlite_engine, real_station_id, timeseries_payload_at

OBSERVED = datetime(2026, 11, 2, 10, 58, 1, tzinfo=UTC)
STATION = real_station_id()


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock(OBSERVED + timedelta(minutes=5))


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = environment_sqlite_engine()
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def api(tmp_path: Path, factory: sessionmaker[Session], clock: Clock) -> Iterator[TestClient]:
    settings = Settings(APP_ENV="test", DATABASE_URL="sqlite://", EVIDENCE_ROOT=tmp_path / "evidence")
    engine = factory.kw["bind"]
    with TestClient(create_app(settings, engine, institutional_clock=clock)) as client:
        yield client


def store(factory: sessionmaker[Session], minutes_after: int = 0, temperature: float | None = None) -> None:
    observed_at = OBSERVED + timedelta(minutes=minutes_after)
    payload = timeseries_payload_at(observed_at)
    if temperature is not None:
        payload["reading"]["values"]["63d0dbfe0a111"] = temperature
    ingested_at = observed_at + timedelta(seconds=40)
    with factory() as db:
        insert_reading(
            db,
            normalize_timeseries(payload, STATION),
            ingested_at=ingested_at,
            fetched_at=observed_at + timedelta(seconds=39),
        )
        db.commit()


def parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def test_latest_is_404_before_any_reading(api: TestClient) -> None:
    response = api.get("/api/environment/latest")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "No environment readings stored yet."


def test_latest_returns_the_ui_contract_with_server_side_freshness(
    api: TestClient, factory: sessionmaker[Session]
) -> None:
    store(factory)
    response = api.get("/api/environment/latest")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(EnvironmentReadingResponse.model_fields) == set(body)
    assert body["station_id"] == STATION
    assert parse(body["observed_at"]) == parse(body["recorded_at"]) == parse(body["source_recorded_at"]) == OBSERVED
    assert parse(body["ingested_at"]) == OBSERVED + timedelta(seconds=40)
    assert parse(body["fetched_at"]) == OBSERVED + timedelta(seconds=39)
    assert body["freshness"] == "LIVE"
    assert body["temperature_c"] == pytest.approx(33.312846)
    assert body["air_quality_index"] == 107.0
    assert body["barometric_pressure_mba"] == 150.0
    assert body["network"] is None
    for private in ("raw_payload", "quality_flags", "unmapped_values", "source_epoch_ms"):
        assert private not in body


@pytest.mark.parametrize(("minutes", "expected"), [(19, "LIVE"), (20, "STALE"), (60, "STALE"), (61, "OFFLINE")])
def test_latest_freshness_uses_server_time(
    api: TestClient, factory: sessionmaker[Session], clock: Clock, minutes: int, expected: str
) -> None:
    store(factory)
    clock.now = OBSERVED + timedelta(minutes=minutes)
    assert api.get("/api/environment/latest").json()["freshness"] == expected


def test_latest_prefers_the_newest_observation(api: TestClient, factory: sessionmaker[Session]) -> None:
    store(factory, 0, 20.0)
    store(factory, 5, 21.0)
    assert api.get("/api/environment/latest").json()["temperature_c"] == 21.0


def test_history_is_bounded_ordered_and_filtered(api: TestClient, factory: sessionmaker[Session]) -> None:
    for minute in (0, 5, 10, 15):
        store(factory, minute, 20.0 + minute)

    newest_first = api.get("/api/environment/history?limit=500").json()
    assert [row["temperature_c"] for row in newest_first] == [35.0, 30.0, 25.0, 20.0]
    assert all(row["freshness"] is None for row in newest_first)
    assert len(api.get("/api/environment/history?limit=2").json()) == 2

    start = (OBSERVED + timedelta(minutes=5)).isoformat()
    end = (OBSERVED + timedelta(minutes=10)).isoformat()
    ranged = api.get("/api/environment/history", params={"start": start, "end": end}).json()
    assert [row["temperature_c"] for row in ranged] == [30.0, 25.0]
    assert api.get("/api/environment/history", params={"station_id": "other"}).json() == []


@pytest.mark.parametrize("query", ["limit=0", "limit=1001", "start=not-a-date"])
def test_history_rejects_invalid_ranges(api: TestClient, query: str) -> None:
    assert api.get(f"/api/environment/history?{query}").status_code == 422


def test_history_rejects_inverted_range(api: TestClient) -> None:
    response = api.get(
        "/api/environment/history",
        params={"start": "2026-09-25T00:00:00Z", "end": "2026-09-24T00:00:00Z"},
    )
    assert response.status_code == 422


def test_status_without_data_is_offline(api: TestClient) -> None:
    body = api.get("/api/environment/status").json()
    assert body["freshness"] == "OFFLINE"
    assert body["data_availability"] == "unavailable"
    assert body["connection_status"] == "connected"
    assert body["thresholds"] == {"live_before_minutes": 20, "stale_until_minutes": 60}


def test_status_reports_freshness_and_worker_health(
    api: TestClient, factory: sessionmaker[Session], clock: Clock
) -> None:
    store(factory)
    with factory() as db:
        for offset, outcome, code in ((1, "INSERTED", None), (6, "FAILED", "TIMEOUT")):
            started = OBSERVED + timedelta(minutes=offset)
            db.add(
                EnvironmentIngestionRun(
                    station_id=STATION, started_at=started, finished_at=started, outcome=outcome, error_code=code
                )
            )
        db.commit()
    clock.now = OBSERVED + timedelta(minutes=25)

    body = api.get("/api/environment/status").json()

    assert body["station"] == STATION
    assert body["freshness"] == "STALE"
    assert body["age_seconds"] == 25 * 60
    assert parse(body["observed_at"]) == OBSERVED
    assert body["last_sync_outcome"] == "FAILED"
    assert body["last_sync_error_code"] == "TIMEOUT"
    assert parse(body["last_successful_sync"]) == OBSERVED + timedelta(minutes=1)


def test_environment_routes_are_read_only(api: TestClient) -> None:
    for path in ("/api/environment/latest", "/api/environment/sync", "/api/sync/aeron"):
        assert api.post(path).status_code in (404, 405)


def test_parameters_route_serves_the_static_map_with_verification_notes(api: TestClient) -> None:
    response = api.get("/api/environment/parameters")

    assert response.status_code == 200
    rows = {row["parameter_id"]: row for row in response.json()}
    assert set(rows) == set(PARAMETER_MAP)
    assert rows["6422ae0f8147e"] == {
        "parameter_id": "6422ae0f8147e",
        "field": "air_quality_index",
        "name": "AQI",
        "unit": "index",
        "category": "air_quality",
        "note": "AQI calculation standard unconfirmed; no health category is assigned.",
    }
    assert rows["63d0dc28f109d"]["unit"] == "Per" and rows["63d0dc28f109d"]["note"]


def test_rows_from_the_retired_cookie_worker_are_still_served_unchanged(
    api: TestClient, factory: sessionmaker[Session]
) -> None:
    legacy_at = OBSERVED - timedelta(days=38)
    with factory() as db:
        db.add(
            EnvironmentReading(
                station_id=STATION,
                observed_at=legacy_at,
                ingested_at=legacy_at + timedelta(minutes=1),
                source_recorded_at_raw="2026-09-24T22:34:00.000Z",
                source="aeron-live3",
                source_route="GET /api/stations/{station_id}/readings?mode=latest&region=india",
                normalizer_version=1,
                quality_flags=[],
                raw_payload={"recordedAt": "2026-09-24T22:34:00.000Z"},
                temperature_c=27.113262,
                network=4,
            )
        )
        db.commit()
    store(factory)

    history = api.get("/api/environment/history?limit=10").json()

    assert [row["temperature_c"] for row in history] == [pytest.approx(33.312846), 27.113262]
    legacy = history[1]
    assert parse(legacy["observed_at"]) == legacy_at
    assert legacy["fetched_at"] is None and legacy["network"] == 4
