import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.environment.source import (
    AeronReadingsClient,
    AeronSession,
    AuthenticationError,
    UpstreamTimeoutError,
)
from app.environment.worker import run_cycle
from app.models.environment import EnvironmentIngestionRun, EnvironmentReading
from tests.environment_support import environment_sqlite_engine, real_latest_payload, real_station_id

STATION = real_station_id()
SECRET_COOKIE = "__session__0=do-not-leak-this-cookie-value"
NOW = datetime(2026, 9, 25, 3, 30, tzinfo=UTC)


class FakeTransport:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, str, bytes]:
        self.calls.append((url, headers))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response  # type: ignore[no-any-return]


def ok(payload: object) -> tuple[int, str, bytes]:
    return 200, "application/json; charset=utf-8", json.dumps(payload).encode()


class FakeLogin:
    def __init__(self, results: list[object] | None = None) -> None:
        self.results = results or [SECRET_COOKIE]
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        result = self.results.pop(0) if self.results else SECRET_COOKIE
        if isinstance(result, Exception):
            raise result
        return str(result)


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = environment_sqlite_engine()
    yield engine
    engine.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def client(transport: FakeTransport) -> AeronReadingsClient:
    return AeronReadingsClient("https://live3.aeronsystems.com/api", STATION, "india", 5.0, transport)


def cycle(factory: sessionmaker[Session], transport: FakeTransport, session: AeronSession) -> EnvironmentIngestionRun:
    return run_cycle(factory, client(transport), session, STATION, clock=lambda: NOW)


def readings(factory: sessionmaker[Session]) -> list[EnvironmentReading]:
    with factory() as db:
        return list(db.scalars(select(EnvironmentReading).order_by(EnvironmentReading.observed_at)))


def runs(factory: sessionmaker[Session]) -> list[EnvironmentIngestionRun]:
    with factory() as db:
        return list(db.scalars(select(EnvironmentIngestionRun).order_by(EnvironmentIngestionRun.id)))


def test_first_cycle_logs_in_once_and_persists_the_real_reading(factory: sessionmaker[Session]) -> None:
    login = FakeLogin()
    transport = FakeTransport([ok(real_latest_payload())])

    run = cycle(factory, transport, AeronSession(login, clock=lambda: NOW))

    assert (run.outcome, run.error_code, run.login_performed) == ("INSERTED", None, True)
    assert login.calls == 1
    url, headers = transport.calls[0]
    assert url == f"https://live3.aeronsystems.com/api/stations/{STATION}/readings?mode=latest&region=india"
    assert headers["Cookie"] == SECRET_COOKIE
    [row] = readings(factory)
    assert row.station_id == STATION
    assert row.observed_at.replace(tzinfo=UTC) == datetime(2026, 9, 24, 22, 34, tzinfo=UTC)
    assert row.ingested_at.replace(tzinfo=UTC) == NOW
    assert row.temperature_c == pytest.approx(27.113262)
    assert row.source_recorded_at_raw == "2026-09-24T22:34:00.000Z"


def test_unchanged_source_timestamp_is_not_stored_twice_and_session_is_reused(
    factory: sessionmaker[Session],
) -> None:
    login = FakeLogin()
    session = AeronSession(login, clock=lambda: NOW)
    transport = FakeTransport([ok(real_latest_payload()), ok(real_latest_payload())])

    first = cycle(factory, transport, session)
    second = cycle(factory, transport, session)

    assert (first.outcome, second.outcome) == ("INSERTED", "DUPLICATE")
    assert second.login_performed is False
    assert login.calls == 1
    assert len(readings(factory)) == 1


def test_new_source_timestamp_is_stored(factory: sessionmaker[Session]) -> None:
    newer = real_latest_payload()
    newer["recordedAt"] = "2026-09-24T22:39:00.000Z"
    newer["data"]["63d0dbfe0a111"] = 27.3
    session = AeronSession(FakeLogin(), clock=lambda: NOW)
    transport = FakeTransport([ok(real_latest_payload()), ok(newer)])

    cycle(factory, transport, session)
    run = cycle(factory, transport, session)

    assert run.outcome == "INSERTED"
    assert [row.temperature_c for row in readings(factory)] == [pytest.approx(27.113262), 27.3]


def test_expired_session_triggers_one_login_and_retry(factory: sessionmaker[Session]) -> None:
    login = FakeLogin()
    session = AeronSession(login, clock=lambda: NOW, initial_cookie="stale=1")
    transport = FakeTransport([(401, "application/json", b'{"error":"x"}'), ok(real_latest_payload())])

    run = cycle(factory, transport, session)

    assert (run.outcome, run.login_performed) == ("INSERTED", True)
    assert login.calls == 1
    assert transport.calls[0][1]["Cookie"] == "stale=1"
    assert transport.calls[1][1]["Cookie"] == SECRET_COOKIE


def test_session_rejected_after_fresh_login_fails_without_looping(factory: sessionmaker[Session]) -> None:
    login = FakeLogin()
    transport = FakeTransport([(403, "application/json", b"{}")])

    run = cycle(factory, transport, AeronSession(login, clock=lambda: NOW))

    assert (run.outcome, run.error_code) == ("FAILED", "SESSION_EXPIRED")
    assert login.calls == 1
    assert readings(factory) == []


def test_upstream_timeout_is_recorded_without_a_reading(factory: sessionmaker[Session]) -> None:
    transport = FakeTransport([UpstreamTimeoutError()])

    run = cycle(factory, transport, AeronSession(FakeLogin(), clock=lambda: NOW, initial_cookie="c=1"))

    assert (run.outcome, run.error_code) == ("FAILED", "TIMEOUT")
    assert readings(factory) == []


@pytest.mark.parametrize(
    ("response", "code"),
    [
        ((200, "text/html", b"<html>login</html>"), "MALFORMED_RESPONSE"),
        ((200, "application/json", b"not json"), "MALFORMED_RESPONSE"),
        ((200, "application/json", b"{}"), "MALFORMED_RESPONSE"),
        ((200, "application/json", b"[]"), "MALFORMED_RESPONSE"),
        ((200, "application/json", b"null"), "MALFORMED_RESPONSE"),
        ((200, "application/json", b'{"recordedAt": "2026-09-24T22:34:00Z"}'), "INVALID_READING"),
        ((502, "text/html", b"bad gateway"), "HTTP_ERROR"),
    ],
)
def test_malformed_upstream_responses_are_rejected(
    factory: sessionmaker[Session], response: tuple[int, str, bytes], code: str
) -> None:
    transport = FakeTransport([response])

    run = cycle(factory, transport, AeronSession(FakeLogin(), clock=lambda: NOW, initial_cookie="c=1"))

    assert (run.outcome, run.error_code) == ("FAILED", code)
    assert readings(factory) == []


def test_failed_login_backs_off_instead_of_retrying_every_cycle(factory: sessionmaker[Session]) -> None:
    now = [NOW]
    login = FakeLogin([AuthenticationError(), SECRET_COOKIE])
    session = AeronSession(login, clock=lambda: now[0])

    first = cycle(factory, FakeTransport([]), session)
    second = cycle(factory, FakeTransport([]), session)
    now[0] = NOW + timedelta(minutes=6)
    third = run_cycle(
        factory, client(FakeTransport([ok(real_latest_payload())])), session, STATION, clock=lambda: now[0]
    )

    assert (first.error_code, second.error_code, third.outcome) == ("AUTH_FAILED", "AUTH_BACKOFF", "INSERTED")
    assert login.calls == 2


def test_missing_credentials_are_reported_not_attempted(factory: sessionmaker[Session]) -> None:
    run = cycle(factory, FakeTransport([]), AeronSession(None, clock=lambda: NOW))
    assert (run.outcome, run.error_code) == ("FAILED", "AUTH_NOT_CONFIGURED")


def test_runs_are_recorded_without_secrets(factory: sessionmaker[Session]) -> None:
    session = AeronSession(FakeLogin(), clock=lambda: NOW)
    cycle(factory, FakeTransport([ok(real_latest_payload())]), session)
    cycle(factory, FakeTransport([(401, "application/json", b"{}"), (401, "application/json", b"{}")]), session)

    recorded = runs(factory)
    assert [run.outcome for run in recorded] == ["INSERTED", "FAILED"]
    stored = json.dumps([[run.error_code, run.detail] for run in recorded]) + json.dumps(
        [row.raw_payload for row in readings(factory)]
    )
    assert "do-not-leak" not in stored
