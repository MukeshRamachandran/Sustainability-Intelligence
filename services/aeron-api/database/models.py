from sqlalchemy import Column, Integer, String, Boolean, Numeric, ForeignKey, DateTime, Text, UniqueConstraint, Index
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

class AeronStation(Base):
    __tablename__ = 'aeron_stations'

    id = Column(Integer, primary_key=True)
    station_id = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    measurements = relationship("AeronMeasurement", back_populates="station", cascade="all, delete-orphan")
    sync_logs = relationship("AeronSyncLog", back_populates="station", cascade="all, delete-orphan")

class AeronMeasurement(Base):
    __tablename__ = 'aeron_measurements'

    id = Column(Integer, primary_key=True)
    station_id = Column(String(100), ForeignKey('aeron_stations.station_id', ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    
    # Air Quality
    co_mg_m3 = Column(Numeric(10, 4))
    no2_ug_m3 = Column(Numeric(10, 4))
    so2_ug_m3 = Column(Numeric(10, 4))
    o3_ug_m3 = Column(Numeric(10, 4))
    no_ug_m3 = Column(Numeric(10, 4))
    pm25_ug_m3 = Column(Numeric(10, 4))
    pm10_ug_m3 = Column(Numeric(10, 4))
    co2_ppm = Column(Numeric(10, 4))

    # Weather
    temperature_c = Column(Numeric(10, 4))
    humidity_pct = Column(Numeric(10, 4))
    rain_mm = Column(Numeric(10, 4))
    wind_speed_kmph = Column(Numeric(10, 4))
    wind_direction_deg = Column(Numeric(10, 4))
    uv_index = Column(Numeric(10, 4))
    pressure_mbar = Column(Numeric(10, 4))
    molecular_volume_ltr = Column(Numeric(10, 4))

    # Noise
    noise_avg_db = Column(Numeric(10, 4))
    noise_min_db = Column(Numeric(10, 4))
    noise_max_db = Column(Numeric(10, 4))

    # Sensor Diagnostics
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

    # Derived values
    co_ppm = Column(Numeric(10, 4))
    no2_ppb = Column(Numeric(10, 4))
    so2_ppb = Column(Numeric(10, 4))
    o3_ppb = Column(Numeric(10, 4))
    no_ppb = Column(Numeric(10, 4))
    aqi = Column(Integer)

    # Device Health
    network_status = Column(String(50))
    battery_v = Column(Numeric(10, 4))
    charging_status = Column(Boolean)
    device_temp_c = Column(Numeric(10, 4))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    station = relationship("AeronStation", back_populates="measurements")

    __table_args__ = (
        UniqueConstraint('station_id', 'timestamp', name='uq_station_timestamp'),
        Index('idx_measurements_station', 'station_id'),
        Index('idx_measurements_timestamp', 'timestamp'),
        Index('idx_measurements_station_timestamp', 'station_id', 'timestamp'),
    )

class AeronSyncLog(Base):
    __tablename__ = 'aeron_sync_logs'

    id = Column(Integer, primary_key=True)
    station_id = Column(String(100), ForeignKey('aeron_stations.station_id', ondelete="CASCADE"), nullable=False)
    sync_timestamp = Column(DateTime(timezone=True), nullable=False)
    records_synced = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    station = relationship("AeronStation", back_populates="sync_logs")
