CREATE SCHEMA IF NOT EXISTS environmental;

CREATE TABLE IF NOT EXISTS environmental.aeron_stations (
    id SERIAL PRIMARY KEY,
    aeron_station_id VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    imei VARCHAR(100),
    station_type VARCHAR(100),
    location VARCHAR(255),
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    timezone VARCHAR(100),
    status VARCHAR(50),
    last_data_at TIMESTAMPTZ,
    organization_id VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS environmental.aeron_parameters (
    id SERIAL PRIMARY KEY,
    aeron_parameter_id VARCHAR(100) UNIQUE NOT NULL,
    legacy_key VARCHAR(100),
    caption VARCHAR(255),
    unit VARCHAR(100),
    normalized_name VARCHAR(255),
    display_order INTEGER,
    hidden BOOLEAN DEFAULT FALSE,
    retired BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS environmental.aeron_measurements (
    id BIGSERIAL PRIMARY KEY,
    station_id VARCHAR(100) NOT NULL REFERENCES environmental.aeron_stations(aeron_station_id) ON DELETE CASCADE,
    source_recorded_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    
    co_mg_m3 DECIMAL(10, 4),
    no2_ug_m3 DECIMAL(10, 4),
    so2_ug_m3 DECIMAL(10, 4),
    o3_ug_m3 DECIMAL(10, 4),
    no_ug_m3 DECIMAL(10, 4),

    pm25_ug_m3 DECIMAL(10, 4),
    pm10_ug_m3 DECIMAL(10, 4),

    temperature_c DECIMAL(10, 4),
    relative_humidity_percent DECIMAL(10, 4),
    rain_mm DECIMAL(10, 4),

    wind_speed_kmph DECIMAL(10, 4),
    wind_direction_deg DECIMAL(10, 4),

    noise_average_db DECIMAL(10, 4),
    noise_min_db DECIMAL(10, 4),
    noise_max_db DECIMAL(10, 4),

    uv_index DECIMAL(10, 4),
    co2_ppm DECIMAL(10, 4),

    co_we_mv DECIMAL(10, 4),
    co_aux_mv DECIMAL(10, 4),

    no2_we_mv DECIMAL(10, 4),
    no2_aux_mv DECIMAL(10, 4),

    so2_we_mv DECIMAL(10, 4),
    so2_aux_mv DECIMAL(10, 4),

    o3_we_mv DECIMAL(10, 4),
    o3_aux_mv DECIMAL(10, 4),

    no_we_mv DECIMAL(10, 4),
    no_aux_mv DECIMAL(10, 4),

    barometric_pressure_mba DECIMAL(10, 4),
    molecular_volume_ltr DECIMAL(10, 4),

    co_ppb DECIMAL(10, 4),
    no2_ppb DECIMAL(10, 4),
    so2_ppb DECIMAL(10, 4),
    o3_ppb DECIMAL(10, 4),
    no_ppb DECIMAL(10, 4),

    air_quality_index DECIMAL(10, 4),

    network INTEGER,
    battery INTEGER,
    charging INTEGER,
    device_temp INTEGER,

    raw_payload JSONB,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (station_id, recorded_at)
);

CREATE INDEX IF NOT EXISTS idx_aeron_measurements_station ON environmental.aeron_measurements(station_id);
CREATE INDEX IF NOT EXISTS idx_aeron_measurements_recorded_at ON environmental.aeron_measurements(recorded_at);

CREATE TABLE IF NOT EXISTS environmental.aeron_sync_logs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status VARCHAR(50) NOT NULL,
    records_received INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_skipped INTEGER DEFAULT 0,
    error_message TEXT
);
