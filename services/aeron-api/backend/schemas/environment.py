from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class AeronMeasurementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    station_id: str
    source_recorded_at: datetime
    recorded_at: datetime
    
    co_mg_m3: Optional[float] = None
    no2_ug_m3: Optional[float] = None
    so2_ug_m3: Optional[float] = None
    o3_ug_m3: Optional[float] = None
    no_ug_m3: Optional[float] = None

    pm25_ug_m3: Optional[float] = None
    pm10_ug_m3: Optional[float] = None

    temperature_c: Optional[float] = None
    relative_humidity_percent: Optional[float] = None
    rain_mm: Optional[float] = None

    wind_speed_kmph: Optional[float] = None
    wind_direction_deg: Optional[float] = None

    noise_average_db: Optional[float] = None
    noise_min_db: Optional[float] = None
    noise_max_db: Optional[float] = None

    uv_index: Optional[float] = None
    co2_ppm: Optional[float] = None

    co_we_mv: Optional[float] = None
    co_aux_mv: Optional[float] = None
    no2_we_mv: Optional[float] = None
    no2_aux_mv: Optional[float] = None
    so2_we_mv: Optional[float] = None
    so2_aux_mv: Optional[float] = None
    o3_we_mv: Optional[float] = None
    o3_aux_mv: Optional[float] = None
    no_we_mv: Optional[float] = None
    no_aux_mv: Optional[float] = None

    barometric_pressure_mba: Optional[float] = None
    molecular_volume_ltr: Optional[float] = None

    co_ppb: Optional[float] = None
    no2_ppb: Optional[float] = None
    so2_ppb: Optional[float] = None
    o3_ppb: Optional[float] = None
    no_ppb: Optional[float] = None

    air_quality_index: Optional[float] = None

    network: Optional[int] = None
    battery: Optional[int] = None
    charging: Optional[int] = None
    device_temp: Optional[int] = None

class SyncLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    records_received: int
    records_inserted: int
    records_skipped: int
    error_message: Optional[str]

