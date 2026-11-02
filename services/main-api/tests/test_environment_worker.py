import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.environment.config import AeronWorkerSettings
from app.environment.source import AeronApiClient
from app.environment.worker import CycleResult, PollScheduler, build_client, run_cycle
from app.models.environment import EnvironmentIngestionRun, EnvironmentReading
from tests.environment_support import (
    environment_sqlite_engine,
    real_station_id,
    real_timeseries_payload,
    timeseries_payload_at,
)

STATION = real_station_id()
API_KEY = "worker-key-do-not-leak-987654321"
OBSERVED = datetime(2026, 11, 2, 10, 58, 1, tzinfo=UTC)
NOW = OBSERVED + timedelta(seconds=45)


class Upstream:
    """Mock Aeron: replies in order; an Exception entry is raised as a transport failure."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, httpx.Response):
            return response
        return httpx.Response(200, json=response)


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = environment_sqlite_engine()
    yield engine
    engine.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def client(upstream: Upstream) -> AeronApiClient:
    return AeronApiClient(
        "https://live3.aeronsystems.com/api/v1",
        SecretStr(API_KEY),
        STATION,
        transport=httpx.MockTransport(upstream),
        sleep=lambda _seconds: None,
    )


def cycle(factory: sessionmaker[Session], upstream: Upstream) -> CycleResult:
    return run_cycle(factory, client(upstream), STATION, clock=lambda: NOW)


def readings(factory: sessionmaker[Session]) -> list[EnvironmentReading]:
    with factory() as db:
        return list(db.scalars(select(EnvironmentReading).order_by(EnvironmentReading.observed_at)))


def runs(factory: sessionmaker[Session]) -> list[EnvironmentIngestionRun]:
    with factory() as db:
        return list(db.scalars(select(EnvironmentIngestionRun).order_by(EnvironmentIngestionRun.id)))


def test_cycle_persists_the_real_v1_reading_with_provenance(factory: sessionmaker[Session]) -> None:
    upstream = Upstream([real_timeseries_payload()])

    result = cycle(factory, upstream)

    assert (result.run.outcome, result.run.error_code, result.run.login_performed) == ("INSERTED", None, False)
    assert upstream.requests[0].headers["Authorization"] == f"Bearer {API_KEY}"
    [row] = readings(factory)
    assert row.station_id == STATION
    assert row.observed_at.replace(tzinfo=UTC) == OBSERVED
    assert row.fetched_at is not None and row.fetched_at.replace(tzinfo=UTC) == NOW
    assert row.ingested_at.replace(tzinfo=UTC) == NOW
    assert row.source_epoch_ms == 1793617081000
    assert row.source_route == "GET /api/v1/timeseries?station={station_id}"
    assert row.normalizer_version == 2
    assert row.air_quality_index == 107.0
    assert row.pm25_ug_m3 == pytest.approx(44.372241)
    assert row.unmapped_values == {}
    assert row.network is None  # v1 has no device-health block; nothing is invented


def test_same_observation_twice_is_stored_once(factory: sessionmaker[Session]) -> None:
    upstream = Upstream([real_timeseries_payload(), real_timeseries_payload()])

    first, second = cycle(factory, upstream), cycle(factory, upstream)

    assert (first.run.outcome, second.run.outcome) == ("INSERTED", "DUPLICATE")
    assert len(readings(factory)) == 1


def test_duplicate_does_not_overwrite_the_first_stored_values(factory: sessionmaker[Session]) -> None:
    changed = real_timeseries_payload()
    changed["reading"]["values"]["63d0dbfe0a111"] = 99.0
    cycle(factory, Upstream([real_timeseries_payload()]))
    cycle(factory, Upstream([changed]))

    [row] = readings(factory)
    assert row.temperature_c == pytest.approx(33.312846)


def test_new_observation_is_stored(factory: sessionmaker[Session]) -> None:
    newer = timeseries_payload_at(OBSERVED + timedelta(minutes=1), **{"63d0dbfe0a111": 33.5})
    upstream = Upstream([real_timeseries_payload(), newer])

    cycle(factory, upstream)
    result = cycle(factory, upstream)

    assert result.run.outcome == "INSERTED"
    assert [row.temperature_c for row in readings(factory)] == [pytest.approx(33.312846), 33.5]


def test_worker_restart_does_not_duplicate(factory: sessionmaker[Session]) -> None:
    # A restarted worker is a new process with a new client; the database is the only memory.
    cycle(factory, Upstream([real_timeseries_payload()]))
    restarted = run_cycle(factory, client(Upstream([real_timeseries_payload()])), STATION, clock=lambda: NOW)

    assert restarted.run.outcome == "DUPLICATE"
    assert len(readings(factory)) == 1


def test_unknown_parameter_is_kept_and_flagged(factory: sessionmaker[Session]) -> None:
    payload = real_timeseries_payload()
    payload["reading"]["values"]["99aa00new0001"] = 4.2

    result = cycle(factory, Upstream([payload]))

    [row] = readings(factory)
    assert row.unmapped_values == {"99aa00new0001": 4.2}
    assert result.run.detail is not None and "unknown_parameter:99aa00new0001" in result.run.detail


def test_missing_parameters_are_stored_as_null_not_zero(factory: sessionmaker[Session]) -> None:
    payload = real_timeseries_payload()
    del payload["reading"]["values"]["63d0db8f77ecb"]

    cycle(factory, Upstream([payload]))

    [row] = readings(factory)
    assert row.pm25_ug_m3 is None
    assert "missing:pm25_ug_m3" in row.quality_flags


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(401, json={"error": "bad key"}), "AUTH_FAILED"),
        (httpx.Response(403, json={"error": "no"}), "FORBIDDEN"),
        (httpx.Response(404, json={"error": "no"}), "NOT_FOUND"),
        (httpx.Response(429, json={}, headers={"Retry-After": "90"}), "RATE_LIMITED"),
        (httpx.Response(200, text="<html/>", headers={"Content-Type": "text/html"}), "MALFORMED_RESPONSE"),
        ({"station": STATION, "resolution": "latest"}, "INVALID_READING"),
        (
            {"station": "other", "reading": {"timestamp": "2026-11-02T10:58:01Z", "values": {"x": 1}}},
            "STATION_MISMATCH",
        ),
    ],
)
def test_failures_are_recorded_with_fixed_codes_and_store_nothing(
    factory: sessionmaker[Session], response: Any, code: str
) -> None:
    result = cycle(factory, Upstream([response]))

    assert (result.run.outcome, result.run.error_code) == ("FAILED", code)
    assert readings(factory) == []
    assert runs(factory)[-1].error_code == code


def test_rate_limit_passes_retry_after_to_the_scheduler(factory: sessionmaker[Session]) -> None:
    result = cycle(factory, Upstream([httpx.Response(429, json={}, headers={"Retry-After": "90"})]))
    assert result.retry_after_seconds == 90.0
    assert PollScheduler(60).next_delay(result, elapsed_seconds=1) == 90.0


def test_timeouts_exhaust_retries_then_fail_the_cycle(factory: sessionmaker[Session]) -> None:
    upstream = Upstream([httpx.ReadTimeout("x")] * 3)

    result = cycle(factory, upstream)

    assert (result.run.outcome, result.run.error_code) == ("FAILED", "TIMEOUT")
    assert len(upstream.requests) == 3


def test_database_failure_is_recorded_as_a_fixed_code(engine: Engine) -> None:
    calls = {"n": 0}
    real = sessionmaker(bind=engine, expire_on_commit=False)

    def flaky() -> Session:
        calls["n"] += 1
        if calls["n"] == 1:  # the insert fails; recording the run still works
            raise OperationalError("insert", {}, Exception("database down"))
        return real()

    result = run_cycle(flaky, client(Upstream([real_timeseries_payload()])), STATION, clock=lambda: NOW)  # type: ignore[arg-type]

    assert (result.run.outcome, result.run.error_code) == ("FAILED", "DATABASE_ERROR")
    assert readings(real) == []


def test_runs_and_rows_never_contain_the_api_key(factory: sessionmaker[Session]) -> None:
    cycle(factory, Upstream([real_timeseries_payload()]))
    cycle(factory, Upstream([httpx.Response(401, json={"error": API_KEY})]))

    stored = json.dumps([[run.error_code, run.detail] for run in runs(factory)]) + json.dumps(
        [[row.raw_payload, row.quality_flags, row.unmapped_values] for row in readings(factory)]
    )
    assert API_KEY not in stored


def failed(code: str) -> CycleResult:
    started = NOW
    return CycleResult(
        EnvironmentIngestionRun(
            station_id=STATION, started_at=started, finished_at=started, outcome="FAILED", error_code=code
        )
    )


def ok() -> CycleResult:
    return CycleResult(EnvironmentIngestionRun(station_id=STATION, started_at=NOW, finished_at=NOW, outcome="INSERTED"))


def test_scheduler_keeps_the_interval_after_success_and_transient_failures() -> None:
    scheduler = PollScheduler(60)
    assert scheduler.next_delay(ok(), elapsed_seconds=2.5) == 57.5
    assert scheduler.next_delay(failed("TIMEOUT"), elapsed_seconds=40) == 20
    assert scheduler.next_delay(failed("HTTP_ERROR"), elapsed_seconds=90) == 1.0


def test_scheduler_backs_off_auth_failures_instead_of_retrying_every_minute() -> None:
    scheduler = PollScheduler(60)
    delays = [scheduler.next_delay(failed("AUTH_FAILED"), 0) for _ in range(6)]
    assert delays == [300, 600, 1200, 2400, 3600, 3600]
    assert scheduler.next_delay(ok(), 0) == 60  # a success resets the backoff
    assert scheduler.next_delay(failed("FORBIDDEN"), 0) == 300


def test_worker_is_not_built_without_an_api_key() -> None:
    settings = AeronWorkerSettings(_env_file=None, AERON_STATION_ID=STATION, AERON_API_KEY="  ")
    assert build_client(settings) is None


def test_settings_hide_the_key_and_require_https() -> None:
    settings = AeronWorkerSettings(_env_file=None, AERON_STATION_ID=STATION, AERON_API_KEY=API_KEY)
    assert API_KEY not in repr(settings) and API_KEY not in str(settings.model_dump())
    assert settings.AERON_POLL_INTERVAL_SECONDS == 60
    with pytest.raises(ValueError):
        AeronWorkerSettings(
            _env_file=None, AERON_STATION_ID=STATION, AERON_API_BASE_URL="http://live3.aeronsystems.com/api/v1"
        )
