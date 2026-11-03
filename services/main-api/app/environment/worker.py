"""Aeron ingestion worker (REST API v1, Bearer API key).

    python -m app.environment.worker          # every AERON_POLL_INTERVAL_SECONDS
    python -m app.environment.worker --once   # one cycle, then exit

Each cycle: GET /timeseries?station= -> normalize -> validate -> insert if the
observation instant is new -> record the run. Public API requests never
trigger any of this. A PostgreSQL advisory lock keeps a single worker active
per database, and the loop is single-threaded, so cycles never overlap.

When to poll next is decided by ``PollScheduler``: the normal interval after
success or a transient failure; ``Retry-After`` after HTTP 429; a pause of 5
minutes doubling to 1 hour after 401/403/404, which retrying cannot fix; and
30 minutes while Aeron reports fewer than 500 requests left for the day.
After a restart the first poll waits until one interval has passed since the
last recorded run, so restarts and redeploys never add extra Aeron calls.
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import FrameType

import structlog
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import create_database_engine, create_session_factory
from app.environment.config import AeronWorkerSettings
from app.environment.normalizer import InvalidReadingError, StationMismatchError, normalize_timeseries
from app.environment.parameters import AERON_PARAMETERS
from app.environment.repository import insert_reading, latest_run, record_run
from app.environment.source import AeronApiClient, AeronSourceError, RateLimitedError
from app.models.environment import EnvironmentIngestionRun

# Arbitrary constant identifying the environment-ingestion advisory lock.
ADVISORY_LOCK_KEY = 0x4B434F534D4F5301
# Failures that will not fix themselves by retrying: wrong key, no access, wrong station.
PERSISTENT_ERROR_CODES = frozenset({"AUTH_FAILED", "FORBIDDEN", "NOT_FOUND", "STATION_MISMATCH"})
PERSISTENT_BACKOFF_BASE_SECONDS = 300.0
PERSISTENT_BACKOFF_MAX_SECONDS = 3600.0
# Below this many requests left for the day, poll at most every LOW_BUDGET_DELAY_SECONDS.
LOW_DAILY_BUDGET = 500
LOW_BUDGET_DELAY_SECONDS = 1800.0

logger = structlog.get_logger("app.environment.worker")


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class CycleResult:
    run: EnvironmentIngestionRun
    retry_after_seconds: float | None = None
    remaining_day: int | None = None


def run_cycle(
    session_factory: sessionmaker[Session],
    client: AeronApiClient,
    station_id: str,
    clock: Callable[[], datetime] = _utc_now,
) -> CycleResult:
    started_at = clock()
    run = EnvironmentIngestionRun(station_id=station_id, started_at=started_at, login_performed=False)
    retry_after: float | None = None
    try:
        payload = client.latest_timeseries()
        fetched_at = clock()
        reading = normalize_timeseries(payload, station_id)
        with session_factory() as db:
            inserted = insert_reading(db, reading, ingested_at=clock(), fetched_at=fetched_at)
            db.commit()
        run.outcome = "INSERTED" if inserted else "DUPLICATE"
        run.observed_at = reading.observed_at
        if reading.quality_flags:
            run.detail = ", ".join(reading.quality_flags)[:1000]
    except RateLimitedError as exc:
        run.outcome, run.error_code = "FAILED", exc.code
        retry_after = exc.retry_after_seconds
    except AeronSourceError as exc:
        run.outcome, run.error_code = "FAILED", exc.code
    except StationMismatchError:
        run.outcome, run.error_code = "FAILED", "STATION_MISMATCH"
    except InvalidReadingError:
        run.outcome, run.error_code = "FAILED", "INVALID_READING"
    except SQLAlchemyError as exc:
        run.outcome, run.error_code = "FAILED", "DATABASE_ERROR"
        run.detail = type(exc).__name__
    except Exception as exc:  # noqa: BLE001 -- never let one cycle kill the worker; never log its text
        run.outcome, run.error_code = "FAILED", "UNEXPECTED_ERROR"
        run.detail = type(exc).__name__
    run.finished_at = clock()
    try:
        with session_factory() as db:
            record_run(db, run)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("environment_run_not_recorded", error_type=type(exc).__name__)
    rate = client.rate_limit
    logger.info(
        "environment_ingestion_cycle",
        outcome=run.outcome,
        error_code=run.error_code,
        observed_at=run.observed_at.isoformat() if run.observed_at else None,
        rate_limit_remaining_minute=rate.remaining_minute if rate else None,
        rate_limit_remaining_day=rate.remaining_day if rate else None,
    )
    return CycleResult(run=run, retry_after_seconds=retry_after, remaining_day=rate.remaining_day if rate else None)


class PollScheduler:
    """Seconds to wait before the next cycle, from the outcome of the last one."""

    def __init__(self, interval_seconds: float) -> None:
        self._interval = interval_seconds
        self._persistent_failures = 0

    def next_delay(self, result: CycleResult, elapsed_seconds: float) -> float:
        code = result.run.error_code
        if code in PERSISTENT_ERROR_CODES:
            self._persistent_failures += 1
            return min(
                PERSISTENT_BACKOFF_BASE_SECONDS * 2.0 ** (self._persistent_failures - 1),
                PERSISTENT_BACKOFF_MAX_SECONDS,
            )
        self._persistent_failures = 0
        if code == "RATE_LIMITED":
            return max(self._interval, result.retry_after_seconds or 0.0)
        if result.remaining_day is not None and result.remaining_day < LOW_DAILY_BUDGET:
            return max(self._interval, LOW_BUDGET_DELAY_SECONDS)
        return max(1.0, self._interval - elapsed_seconds)


def initial_delay(session_factory: sessionmaker[Session], interval_seconds: float, now: datetime) -> float:
    """Seconds to wait before the first poll so a restart never polls sooner than one interval."""
    try:
        with session_factory() as db:
            last = latest_run(db)
    except SQLAlchemyError:
        return 0.0
    if last is None:
        return 0.0
    started = last.started_at if last.started_at.tzinfo else last.started_at.replace(tzinfo=UTC)
    elapsed = (now - started).total_seconds()
    return min(max(0.0, interval_seconds - elapsed), interval_seconds)


def check_parameter_metadata(client: AeronApiClient) -> None:
    """Log (IDs only) any drift between Aeron's parameter metadata and the K-COSMOS map. Never fatal."""
    try:
        payload = client.parameters()
    except AeronSourceError as exc:
        logger.warning("environment_parameter_metadata_unavailable", error_code=exc.code)
        return
    items = payload.get("parameters")
    if not isinstance(items, list):
        logger.warning("environment_parameter_metadata_unrecognised")
        return
    source = {item.get("code"): item.get("unit") for item in items if isinstance(item, dict)}
    unmapped = sorted(str(code) for code in source if code not in AERON_PARAMETERS)
    absent = sorted(code for code in AERON_PARAMETERS if code not in source)
    unit_differs = sorted(
        code for code, parameter in AERON_PARAMETERS.items() if code in source and source[code] != parameter.unit
    )
    logger.info(
        "environment_parameter_metadata",
        source_count=len(source),
        unmapped=unmapped,
        absent=absent,
        unit_differs=unit_differs,
    )


def acquire_single_worker_lock(engine: Engine) -> Connection | None:
    """Hold a session-level advisory lock for the worker's lifetime."""
    connection = engine.connect()
    acquired = connection.execute(text("select pg_try_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY}).scalar()
    connection.commit()
    if not acquired:
        connection.close()
        return None
    return connection


def release_single_worker_lock(connection: Connection) -> None:
    """Unlock explicitly: closing a pooled connection keeps its session, and with it the lock."""
    try:
        connection.execute(text("select pg_advisory_unlock(:key)"), {"key": ADVISORY_LOCK_KEY})
        connection.commit()
    finally:
        connection.close()


def build_client(settings: AeronWorkerSettings) -> AeronApiClient | None:
    if not settings.api_key_configured or settings.AERON_API_KEY is None:
        return None
    return AeronApiClient(
        base_url=settings.AERON_API_BASE_URL,
        api_key=settings.AERON_API_KEY,
        station_id=settings.AERON_STATION_ID,
        connect_timeout=settings.AERON_CONNECT_TIMEOUT_SECONDS,
        read_timeout=settings.AERON_READ_TIMEOUT_SECONDS,
        max_attempts=settings.AERON_MAX_ATTEMPTS,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="K-COSMOS Aeron environment ingestion worker")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = parser.parse_args(argv)

    app_settings = get_settings()
    configure_logging(app_settings.LOG_LEVEL)
    # httpx logs every request URL at INFO; the cycle event already records the outcome.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = AeronWorkerSettings()
    client = build_client(settings)
    if client is None:
        logger.error("environment_worker_not_configured", missing="AERON_API_KEY")
        return 3
    engine = create_database_engine(app_settings.DATABASE_URL)
    lock = acquire_single_worker_lock(engine)
    if lock is None:
        logger.warning("environment_worker_already_running")
        client.close()
        engine.dispose()
        return 2
    session_factory = create_session_factory(engine)
    scheduler = PollScheduler(settings.AERON_POLL_INTERVAL_SECONDS)

    stop = threading.Event()

    def _stop(_signum: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    logger.info("environment_worker_started", interval_seconds=settings.AERON_POLL_INTERVAL_SECONDS)
    try:
        if not args.once:
            delay = initial_delay(session_factory, settings.AERON_POLL_INTERVAL_SECONDS, _utc_now())
            if delay > 0:
                logger.info("environment_worker_waiting_after_restart", seconds=round(delay))
                if stop.wait(delay):
                    return 0
            check_parameter_metadata(client)
        while True:
            cycle_started = _utc_now()
            result = run_cycle(session_factory, client, settings.AERON_STATION_ID)
            if args.once:
                return 0 if result.run.outcome != "FAILED" else 1
            elapsed = (_utc_now() - cycle_started).total_seconds()
            if stop.wait(scheduler.next_delay(result, elapsed)):
                return 0
    finally:
        client.close()
        release_single_worker_lock(lock)
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
