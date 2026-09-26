"""Aeron environmental readings (0012_environment_readings).

Append-only time series. ``observed_at`` is when Aeron measured the reading
(true UTC from the source); ``ingested_at`` is when K-COSMOS stored it. A
station can hold at most one reading per observation instant.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

INGESTION_OUTCOMES = ("INSERTED", "DUPLICATE", "FAILED")

_JSON = JSON().with_variant(JSONB(), "postgresql")
_BIGINT_ID = BigInteger().with_variant(Integer(), "sqlite")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(value) for value in values)})"


class EnvironmentReading(Base):
    __tablename__ = "readings"
    __table_args__ = (
        UniqueConstraint("station_id", "observed_at", name="uq_readings_station_observed_at"),
        Index("ix_readings_station_observed_at", "station_id", "observed_at"),
        {"schema": "environment"},
    )

    id: Mapped[int] = mapped_column(_BIGINT_ID, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(100), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source_recorded_at_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_route: Mapped[str] = mapped_column(String(200), nullable=False)
    normalizer_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    quality_flags: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)

    co_mg_m3: Mapped[float | None] = mapped_column(Double)
    no2_ug_m3: Mapped[float | None] = mapped_column(Double)
    so2_ug_m3: Mapped[float | None] = mapped_column(Double)
    o3_ug_m3: Mapped[float | None] = mapped_column(Double)
    no_ug_m3: Mapped[float | None] = mapped_column(Double)
    pm25_ug_m3: Mapped[float | None] = mapped_column(Double)
    pm10_ug_m3: Mapped[float | None] = mapped_column(Double)
    temperature_c: Mapped[float | None] = mapped_column(Double)
    relative_humidity_percent: Mapped[float | None] = mapped_column(Double)
    rain_mm: Mapped[float | None] = mapped_column(Double)
    wind_speed_kmph: Mapped[float | None] = mapped_column(Double)
    wind_direction_deg: Mapped[float | None] = mapped_column(Double)
    noise_average_db: Mapped[float | None] = mapped_column(Double)
    noise_min_db: Mapped[float | None] = mapped_column(Double)
    noise_max_db: Mapped[float | None] = mapped_column(Double)
    uv_index: Mapped[float | None] = mapped_column(Double)
    co2_ppm: Mapped[float | None] = mapped_column(Double)
    co_we_mv: Mapped[float | None] = mapped_column(Double)
    co_aux_mv: Mapped[float | None] = mapped_column(Double)
    no2_we_mv: Mapped[float | None] = mapped_column(Double)
    no2_aux_mv: Mapped[float | None] = mapped_column(Double)
    so2_we_mv: Mapped[float | None] = mapped_column(Double)
    so2_aux_mv: Mapped[float | None] = mapped_column(Double)
    o3_we_mv: Mapped[float | None] = mapped_column(Double)
    o3_aux_mv: Mapped[float | None] = mapped_column(Double)
    no_we_mv: Mapped[float | None] = mapped_column(Double)
    no_aux_mv: Mapped[float | None] = mapped_column(Double)
    barometric_pressure_mba: Mapped[float | None] = mapped_column(Double)
    molecular_volume_ltr: Mapped[float | None] = mapped_column(Double)
    co_ppb: Mapped[float | None] = mapped_column(Double)
    no2_ppb: Mapped[float | None] = mapped_column(Double)
    so2_ppb: Mapped[float | None] = mapped_column(Double)
    o3_ppb: Mapped[float | None] = mapped_column(Double)
    no_ppb: Mapped[float | None] = mapped_column(Double)
    air_quality_index: Mapped[float | None] = mapped_column(Double)

    network: Mapped[int | None] = mapped_column(Integer)
    battery: Mapped[int | None] = mapped_column(Integer)
    charging: Mapped[int | None] = mapped_column(Integer)
    device_temp: Mapped[int | None] = mapped_column(Integer)


class EnvironmentIngestionRun(Base):
    """One worker cycle. Error codes are fixed identifiers, never upstream text."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(_in("outcome", INGESTION_OUTCOMES), name="outcome_allowed"),
        Index("ix_ingestion_runs_started_at", "started_at"),
        {"schema": "environment"},
    )

    id: Mapped[int] = mapped_column(_BIGINT_ID, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    login_performed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detail: Mapped[str | None] = mapped_column(Text)
