from sqlalchemy import BigInteger, Column, Integer, String, Boolean, Numeric, ForeignKey, DateTime, Text, UniqueConstraint, Index, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

class AeronStation(Base):
    __tablename__ = 'aeron_stations'
    __table_args__ = {'schema': 'environmental'}

    id = Column(Integer, primary_key=True)
    aeron_station_id = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    imei = Column(String(100))
    station_type = Column(String(100))
    location = Column(String(255))
    latitude = Column(Numeric(10, 6))
    longitude = Column(Numeric(10, 6))
    timezone = Column(String(100))
    status = Column(String(50))
    last_data_at = Column(DateTime(timezone=True))
    organization_id = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    measurements = relationship("AeronMeasurement", back_populates="station", cascade="all, delete-orphan")

class AeronParameter(Base):
    __tablename__ = 'aeron_parameters'
    __table_args__ = {'schema': 'environmental'}

    id = Column(Integer, primary_key=True)
    aeron_parameter_id = Column(String(100), unique=True, nullable=False)
    legacy_key = Column(String(100))
    caption = Column(String(255))
    unit = Column(String(100))
    normalized_name = Column(String(255))
    display_order = Column(Integer)
    hidden = Column(Boolean, default=False)
    retired = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AeronMeasurement(Base):
    __tablename__ = 'aeron_measurements'

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    station_id = Column(String(100), ForeignKey('environmental.aeron_stations.aeron_station_id', ondelete="CASCADE"), nullable=False)
    source_recorded_at = Column(DateTime(timezone=True), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False)
    
    co_mg_m3 = Column(Numeric(10, 4))
    no2_ug_m3 = Column(Numeric(10, 4))
    so2_ug_m3 = Column(Numeric(10, 4))
    o3_ug_m3 = Column(Numeric(10, 4))
    no_ug_m3 = Column(Numeric(10, 4))

    pm25_ug_m3 = Column(Numeric(10, 4))
    pm10_ug_m3 = Column(Numeric(10, 4))

    temperature_c = Column(Numeric(10, 4))
    relative_humidity_percent = Column(Numeric(10, 4))
    rain_mm = Column(Numeric(10, 4))

    wind_speed_kmph = Column(Numeric(10, 4))
    wind_direction_deg = Column(Numeric(10, 4))

    noise_average_db = Column(Numeric(10, 4))
    noise_min_db = Column(Numeric(10, 4))
    noise_max_db = Column(Numeric(10, 4))

    uv_index = Column(Numeric(10, 4))
    co2_ppm = Column(Numeric(10, 4))

    co_we_mv = Column(Numeric(10, 4))
    co_aux_mv = Column(Numeric(10, 4))

    no2_we_mv = Column(Numeric(10, 4))
    no2_aux_mv = Column(Numeric(10, 4))

    so2_we_mv = Column(Numeric(10, 4))
    so2_aux_mv = Column(Numeric(10, 4))

    o3_we_mv = Column(Numeric(10, 4))
    o3_aux_mv = Column(Numeric(10, 4))

    no_we_mv = Column(Numeric(10, 4))
    no_aux_mv = Column(Numeric(10, 4))

    barometric_pressure_mba = Column(Numeric(10, 4))
    molecular_volume_ltr = Column(Numeric(10, 4))

    co_ppb = Column(Numeric(10, 4))
    no2_ppb = Column(Numeric(10, 4))
    so2_ppb = Column(Numeric(10, 4))
    o3_ppb = Column(Numeric(10, 4))
    no_ppb = Column(Numeric(10, 4))

    air_quality_index = Column(Numeric(10, 4))

    network = Column(Integer)
    battery = Column(Integer)
    charging = Column(Integer)
    device_temp = Column(Integer)

    raw_payload = Column(JSON().with_variant(JSONB, 'postgresql'))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    station = relationship("AeronStation", back_populates="measurements")

    __table_args__ = (
        UniqueConstraint('station_id', 'recorded_at', name='uq_aeron_measurements_station_recorded_at'),
        Index('idx_aeron_measurements_station', 'station_id'),
        Index('idx_aeron_measurements_recorded_at', 'recorded_at'),
        {'schema': 'environmental'},
    )

class AeronSyncLog(Base):
    __tablename__ = 'aeron_sync_logs'
    __table_args__ = {'schema': 'environmental'}

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    status = Column(String(50), nullable=False)
    records_received = Column(Integer, default=0)
    records_inserted = Column(Integer, default=0)
    records_skipped = Column(Integer, default=0)
    error_message = Column(Text)
