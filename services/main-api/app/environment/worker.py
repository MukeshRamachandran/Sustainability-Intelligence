"""Aeron ingestion worker.

    python -m app.environment.worker          # every AERON_POLL_INTERVAL_SECONDS
    python -m app.environment.worker --once   # one cycle, then exit

Each cycle: reuse the in-memory session -> GET latest reading over HTTP ->
(on missing/expired session only) Playwright login and one retry ->
normalize -> validate -> insert if the observation instant is new -> record
the run. Public API requests never trigger any of this. A PostgreSQL advisory
lock keeps a single worker active per database.
"""

from __future__ import annotations

import argparse
import signal
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from types import FrameType

import structlog
from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import create_database_engine, create_session_factory
from app.environment.config import AeronWorkerSettings
from app.environment.normalizer import InvalidReadingError, normalize_reading
from app.environment.repository import insert_reading, record_run
from app.environment.source import (
    AeronReadingsClient,
    AeronSession,
    AeronSourceError,
    PlaywrightLogin,
    SessionExpiredError,
)
from app.models.environment import EnvironmentIngestionRun

# Arbitrary constant identifying the environment-ingestion advisory lock.
ADVISORY_LOCK_KEY = 0x4B434F534D4F5301

logger = structlog.get_logger("app.environment.worker")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def run_cycle(
    session_factory: sessionmaker[Session],
    client: AeronReadingsClient,
    aeron_session: AeronSession,
    station_id: str,
    clock: Callable[[], datetime] = _utc_now,
) -> EnvironmentIngestionRun:
    started_at = clock()
    login_performed = False
    run = EnvironmentIngestionRun(station_id=station_id, started_at=started_at, login_performed=False)
    try:
        cookie = aeron_session.cookie
        if cookie is None:
            cookie = aeron_session.refresh()
            login_performed = True
        try:
            payload = client.fetch_latest(cookie)
        except SessionExpiredError:
            if login_performed:
                raise
            aeron_session.invalidate()
            cookie = aeron_session.refresh()
            login_performed = True
            payload = client.fetch_latest(cookie)
        reading = normalize_reading(payload, station_id)
        with session_factory() as db:
            inserted = insert_reading(db, reading, ingested_at=clock())
            db.commit()
        run.outcome = "INSERTED" if inserted else "DUPLICATE"
        run.observed_at = reading.observed_at
        if reading.quality_flags:
            run.detail = ", ".join(reading.quality_flags)[:1000]
    except AeronSourceError as exc:
        run.outcome, run.error_code = "FAILED", exc.code
    except InvalidReadingError:
        run.outcome, run.error_code = "FAILED", "INVALID_READING"
    except Exception as exc:  # noqa: BLE001 -- never let one cycle kill the worker; never log its text
        run.outcome, run.error_code = "FAILED", "UNEXPECTED_ERROR"
        run.detail = type(exc).__name__
    run.login_performed = login_performed
    run.finished_at = clock()
    try:
        with session_factory() as db:
            record_run(db, run)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("environment_run_not_recorded", error_type=type(exc).__name__)
    logger.info(
        "environment_ingestion_cycle",
        outcome=run.outcome,
        error_code=run.error_code,
        observed_at=run.observed_at.isoformat() if run.observed_at else None,
        login_performed=login_performed,
    )
    return run


def acquire_single_worker_lock(engine: Engine) -> Connection | None:
    """Hold a session-level advisory lock for the worker's lifetime."""
    connection = engine.connect()
    acquired = connection.execute(text("select pg_try_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY}).scalar()
    connection.commit()
    if not acquired:
        connection.close()
        return None
    return connection


def build_components(
    settings: AeronWorkerSettings,
) -> tuple[AeronReadingsClient, AeronSession]:
    client = AeronReadingsClient(
        base_url=settings.AERON_INTERNAL_BASE_URL,
        station_id=settings.AERON_STATION_ID,
        region=settings.AERON_REGION,
        timeout=settings.AERON_HTTP_TIMEOUT_SECONDS,
    )
    login = None
    if settings.login_configured and settings.AERON_USERNAME and settings.AERON_PASSWORD:
        login = PlaywrightLogin(
            dashboard_url=settings.AERON_DASHBOARD_URL,
            cookie_url=settings.AERON_INTERNAL_BASE_URL,
            username=settings.AERON_USERNAME,
            password=settings.AERON_PASSWORD,
            timeout_seconds=settings.AERON_LOGIN_TIMEOUT_SECONDS,
        )
    initial = settings.AERON_SESSION_COOKIE.get_secret_value() if settings.AERON_SESSION_COOKIE else None
    return client, AeronSession(login=login, clock=_utc_now, initial_cookie=initial)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="K-COSMOS Aeron environment ingestion worker")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = parser.parse_args(argv)

    app_settings = get_settings()
    configure_logging(app_settings.LOG_LEVEL)
    settings = AeronWorkerSettings()
    engine = create_database_engine(app_settings.DATABASE_URL)
    lock = acquire_single_worker_lock(engine)
    if lock is None:
        logger.warning("environment_worker_already_running")
        return 2
    session_factory = create_session_factory(engine)
    client, aeron_session = build_components(settings)

    stop = threading.Event()

    def _stop(_signum: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    logger.info("environment_worker_started", interval_seconds=settings.AERON_POLL_INTERVAL_SECONDS)
    try:
        while True:
            cycle_started = _utc_now()
            run = run_cycle(session_factory, client, aeron_session, settings.AERON_STATION_ID)
            if args.once:
                return 0 if run.outcome != "FAILED" else 1
            elapsed = (_utc_now() - cycle_started).total_seconds()
            if stop.wait(max(1.0, settings.AERON_POLL_INTERVAL_SECONDS - elapsed)):
                return 0
    finally:
        lock.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
