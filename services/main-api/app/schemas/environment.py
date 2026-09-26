from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.environment.freshness import Freshness


class EnvironmentReadingResponse(BaseModel):
    """Flat reading shape consumed by the existing Weather UI.

    ``recorded_at`` and ``source_recorded_at`` are kept for UI compatibility and
    equal ``observed_at``: the source timestamp is already true UTC, so no
    corrected/uncorrected pair exists any more.
    """

    model_config = ConfigDict(from_attributes=True)

    station_id: str
    observed_at: datetime
    ingested_at: datetime
    recorded_at: datetime
    source_recorded_at: datetime
    freshness: Freshness | None = None

    co_mg_m3: float | None = None
    no2_ug_m3: float | None = None
    so2_ug_m3: float | None = None
    o3_ug_m3: float | None = None
    no_ug_m3: float | None = None
    pm25_ug_m3: float | None = None
    pm10_ug_m3: float | None = None
    temperature_c: float | None = None
    relative_humidity_percent: float | None = None
    rain_mm: float | None = None
    wind_speed_kmph: float | None = None
    wind_direction_deg: float | None = None
    noise_average_db: float | None = None
    noise_min_db: float | None = None
    noise_max_db: float | None = None
    uv_index: float | None = None
    co2_ppm: float | None = None
    co_we_mv: float | None = None
    co_aux_mv: float | None = None
    no2_we_mv: float | None = None
    no2_aux_mv: float | None = None
    so2_we_mv: float | None = None
    so2_aux_mv: float | None = None
    o3_we_mv: float | None = None
    o3_aux_mv: float | None = None
    no_we_mv: float | None = None
    no_aux_mv: float | None = None
    barometric_pressure_mba: float | None = None
    molecular_volume_ltr: float | None = None
    co_ppb: float | None = None
    no2_ppb: float | None = None
    so2_ppb: float | None = None
    o3_ppb: float | None = None
    no_ppb: float | None = None
    air_quality_index: float | None = None

    network: int | None = None
    battery: int | None = None
    charging: int | None = None
    device_temp: int | None = None


class FreshnessThresholds(BaseModel):
    live_before_minutes: int
    stale_until_minutes: int


class EnvironmentStatusResponse(BaseModel):
    source: str
    station: str | None
    server_time: datetime
    latest_timestamp: datetime | None
    observed_at: datetime | None
    ingested_at: datetime | None
    age_seconds: int | None
    freshness: Freshness
    thresholds: FreshnessThresholds
    last_sync: datetime | None
    last_sync_outcome: str | None
    last_sync_error_code: str | None
    last_successful_sync: datetime | None
    data_availability: str
    connection_status: str
