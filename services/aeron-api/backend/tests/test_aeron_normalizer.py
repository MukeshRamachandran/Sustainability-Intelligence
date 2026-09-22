from backend.services.aeron_normalizer import normalize_aeron_reading
from backend.config import settings

def test_normalize_aeron_reading_with_verified_payload(monkeypatch):
    monkeypatch.setattr(settings, "aeron_timestamp_correction_minutes", 0)
    payload = {
        "recordedAt": "2023-10-25T14:30:00Z",
        "health": {
            "fuse": 0,
            "gpsfix": 1,
            "supply": 12,
            "battery": 100,
            "network": 4,
            "charging": 1,
            "DeviceTemp": 35,
            "network_reg": 1
        },
        "location": {
            "Altitude": 100,
            "Latitude": 11.0168,
            "Longitude": 76.9558
        },
        "data": {
            "63d0da020016a": 0.5,     # CO
            "63d0da885f1a0": 20.1,    # NO2
            "63d0daa4740ba": 5.2,     # SO2
            "63d0daf2bcb74": 45.3,    # O3
            "63d0db066e993": 10.1,    # NO
            "63d0db8f77ecb": 15.2,    # PM2.5
            "63d0dbb867a7c": 30.5,    # PM10
            "63d0dbfe0a111": 25.4,    # Temp
            "63d0dc28f109d": 60.2,    # Humidity
            "63d0dc5164112": 0.0,     # Rain
            "63d0dd3721886": 12.5,    # Wind Speed
            "63d0dd4ff30c9": 180,     # Wind Dir
            "63d0ddf115956": 55.2,    # Noise Avg
            "63d0de104027f": 45.1,    # Noise Min
            "63d0de34a0b72": 75.3,    # Noise Max
            "63d0de7568a3b": 5,       # UV
            "63d0ea1253e8f": 410.2,   # CO2
            "63d0ee3fcd99a": 1012.3,  # Pressure
            "63d0eeb2aaeef": 24.45,   # Mol Vol
            "6422ae0f8147e": 42,      # AQI
            "unknown_param_xyz": 999  # Unknown
        }
    }

    normalized = normalize_aeron_reading(payload)
    
    assert normalized["recorded_at"].isoformat() == "2023-10-25T14:30:00+00:00"
    assert normalized["source_recorded_at"].isoformat() == "2023-10-25T14:30:00+00:00"
    
    # Test Mappings
    assert normalized["co_mg_m3"] == 0.5
    assert normalized["no2_ug_m3"] == 20.1
    assert normalized["so2_ug_m3"] == 5.2
    assert normalized["o3_ug_m3"] == 45.3
    assert normalized["no_ug_m3"] == 10.1
    assert normalized["pm25_ug_m3"] == 15.2
    assert normalized["pm10_ug_m3"] == 30.5
    assert normalized["temperature_c"] == 25.4
    assert normalized["relative_humidity_percent"] == 60.2
    assert normalized["rain_mm"] == 0.0
    assert normalized["wind_speed_kmph"] == 12.5
    assert normalized["wind_direction_deg"] == 180
    assert normalized["noise_average_db"] == 55.2
    assert normalized["noise_min_db"] == 45.1
    assert normalized["noise_max_db"] == 75.3
    assert normalized["uv_index"] == 5
    assert normalized["co2_ppm"] == 410.2
    assert normalized["barometric_pressure_mba"] == 1012.3
    assert normalized["molecular_volume_ltr"] == 24.45
    assert normalized["air_quality_index"] == 42
    
    # Test Health Fields
    assert normalized["network"] == 4
    assert normalized["battery"] == 100
    assert normalized["charging"] == 1
    assert normalized["device_temp"] == 35
    
    # Test Raw Payload preservation
    assert "unknown_param_xyz" in normalized["raw_payload"]["data"]
    
def test_normalize_preserves_nulls(monkeypatch):
    monkeypatch.setattr(settings, "aeron_timestamp_correction_minutes", 0)
    payload = {
        "recordedAt": "2023-10-25T14:30:00Z",
        "health": {},
        "location": {},
        "data": {
            "63d0da020016a": None, # Should be preserved as None, not 0
        }
    }
    
    normalized = normalize_aeron_reading(payload)
    
    assert normalized["co_mg_m3"] is None
    assert "no2_ug_m3" not in normalized  # Missing values are omitted in the normalized dict, leading to NULL in DB
