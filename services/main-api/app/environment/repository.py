"""Persistence for environment readings and ingestion runs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.environment.normalizer import NORMALIZER_VERSION, NormalizedReading
from app.models.environment import EnvironmentIngestionRun, EnvironmentReading

SOURCE = "aeron-live3"
SOURCE_ROUTE = "GET /api/stations/{station_id}/readings?mode=latest&region=india"


def insert_reading(db: Session, reading: NormalizedReading, ingested_at: datetime) -> bool:
    """Store a reading once per station + observation instant. Returns True when a row was added."""
    values: dict[str, Any] = {
        "station_id": reading.station_id,
        "observed_at": reading.observed_at,
        "ingested_at": ingested_at,
        "source_recorded_at_raw": reading.source_recorded_at_raw,
        "source": SOURCE,
        "source_route": SOURCE_ROUTE,
        "normalizer_version": NORMALIZER_VERSION,
        "quality_flags": reading.quality_flags,
        "raw_payload": reading.raw_payload,
        **reading.metrics,
        **reading.health,
    }
    dialect = db.get_bind().dialect.name
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    statement = (
        insert(EnvironmentReading)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["station_id", "observed_at"])
        .returning(EnvironmentReading.id)
    )
    inserted = db.execute(statement).scalar_one_or_none()
    return inserted is not None


def latest_reading(db: Session, station_id: str | None = None) -> EnvironmentReading | None:
    query = select(EnvironmentReading)
    if station_id:
        query = query.where(EnvironmentReading.station_id == station_id)
    return db.scalars(query.order_by(EnvironmentReading.observed_at.desc()).limit(1)).first()


def reading_history(
    db: Session,
    *,
    station_id: str | None,
    start: datetime | None,
    end: datetime | None,
    limit: int,
) -> Sequence[EnvironmentReading]:
    query = select(EnvironmentReading)
    if station_id:
        query = query.where(EnvironmentReading.station_id == station_id)
    if start is not None:
        query = query.where(EnvironmentReading.observed_at >= start)
    if end is not None:
        query = query.where(EnvironmentReading.observed_at <= end)
    return db.scalars(query.order_by(EnvironmentReading.observed_at.desc()).limit(limit)).all()


def record_run(db: Session, run: EnvironmentIngestionRun) -> None:
    db.add(run)


def latest_run(db: Session, *, successful: bool = False) -> EnvironmentIngestionRun | None:
    query = select(EnvironmentIngestionRun)
    if successful:
        query = query.where(EnvironmentIngestionRun.outcome != "FAILED")
    return db.scalars(query.order_by(EnvironmentIngestionRun.started_at.desc()).limit(1)).first()
