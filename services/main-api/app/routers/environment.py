"""Public, read-only Aeron environment API.

Serves persisted readings only. Nothing here contacts Aeron or starts a
browser; ingestion belongs to ``app.environment.worker``.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.environment.freshness import LIVE_BEFORE, STALE_UNTIL, classify_freshness, reading_age
from app.environment.repository import SOURCE, latest_reading, latest_run, reading_history
from app.models.environment import EnvironmentReading
from app.schemas.environment import EnvironmentReadingResponse, EnvironmentStatusResponse, FreshnessThresholds
from app.security.dependencies import DbSession

router = APIRouter(prefix="/api/environment", tags=["environment"])

StationFilter = Annotated[str | None, Query(max_length=100)]


def _now(request: Request) -> datetime:
    clock = request.app.state.institutional_clock
    return clock()  # type: ignore[no-any-return]


def _reading(row: EnvironmentReading, freshness: str | None = None) -> EnvironmentReadingResponse:
    return EnvironmentReadingResponse.model_validate(
        {
            **{column.key: getattr(row, column.key) for column in EnvironmentReading.__table__.columns},
            "recorded_at": row.observed_at,
            "source_recorded_at": row.observed_at,
            "freshness": freshness,
        }
    )


@router.get("/latest", response_model=EnvironmentReadingResponse)
def environment_latest(
    request: Request, response: Response, db: DbSession, station_id: StationFilter = None
) -> EnvironmentReadingResponse:
    response.headers["Cache-Control"] = "no-store"
    row = latest_reading(db, station_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No environment readings stored yet.")
    return _reading(row, classify_freshness(row.observed_at, _now(request)))


@router.get("/history", response_model=list[EnvironmentReadingResponse])
def environment_history(
    response: Response,
    db: DbSession,
    station_id: StationFilter = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[EnvironmentReadingResponse]:
    response.headers["Cache-Control"] = "no-store"
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="start must not be after end.")
    rows = reading_history(db, station_id=station_id, start=start, end=end, limit=limit)
    return [_reading(row) for row in rows]


@router.get("/status", response_model=EnvironmentStatusResponse)
def environment_status(request: Request, response: Response, db: DbSession) -> EnvironmentStatusResponse:
    response.headers["Cache-Control"] = "no-store"
    now = _now(request)
    try:
        latest = latest_reading(db)
        last_run = latest_run(db)
        last_success = latest_run(db, successful=True)
        connection = "connected"
    except SQLAlchemyError:
        db.rollback()
        latest = last_run = last_success = None
        connection = "error"
    observed_at = latest.observed_at if latest else None
    return EnvironmentStatusResponse(
        source=SOURCE,
        station=latest.station_id if latest else None,
        server_time=now,
        latest_timestamp=observed_at,
        observed_at=observed_at,
        ingested_at=latest.ingested_at if latest else None,
        age_seconds=int(reading_age(observed_at, now).total_seconds()) if observed_at else None,
        freshness=classify_freshness(observed_at, now),
        thresholds=FreshnessThresholds(
            live_before_minutes=int(LIVE_BEFORE.total_seconds() // 60),
            stale_until_minutes=int(STALE_UNTIL.total_seconds() // 60),
        ),
        last_sync=last_run.started_at if last_run else None,
        last_sync_outcome=last_run.outcome if last_run else None,
        last_sync_error_code=last_run.error_code if last_run else None,
        last_successful_sync=last_success.started_at if last_success else None,
        data_availability="available" if latest else "unavailable",
        connection_status=connection,
    )
