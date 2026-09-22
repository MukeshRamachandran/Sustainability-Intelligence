import httpx
import logging
from typing import Dict, Any, List
from datetime import datetime
from backend.config import settings

logger = logging.getLogger(__name__)

class AeronClient:
    def __init__(self):
        self.base_url = settings.public_api_url
        self.internal_base_url = settings.fallback_api_url
        self.api_key = settings.aeron_api_key
        self.session_cookie = settings.aeron_session_cookie
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
    def get_stations(self):
        raise NotImplementedError("Public Aeron API endpoint not yet configured")
        
    def get_parameters(self):
        raise NotImplementedError("Public Aeron API endpoint not yet configured")
        
    def get_latest_reading(self, station_id: str) -> Dict[str, Any]:
        """
        Fetches the latest reading from the Aeron Live3 API.
        Uses the exact API request structure from the original project.
        """
        url = f"{self.base_url}/devices/{station_id}/latest"
        logger.info(f"Fetching live data from Aeron API for {station_id}")
        
        try:
            with httpx.Client(timeout=settings.aeron_request_timeout_seconds) as client:
                response = client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.error("Public Aeron API request failed: %s", type(exc).__name__)
            raise ValueError("Failed to fetch data from the public Aeron API") from None

    def get_latest_reading_internal(self, station_id: str) -> Dict[str, Any]:
        """
        Fetches the latest reading using the internal Live3 API as a fallback.
        """
        url = f"{self.internal_base_url}/stations/{station_id}/readings?mode=latest&region=india"
        logger.info(f"Fetching fallback live data from internal Aeron API for {station_id}")
        
        headers = {
            "Cookie": self.session_cookie
        }
        
        try:
            with httpx.Client(timeout=settings.aeron_request_timeout_seconds) as client:
                response = client.get(url, headers=headers)
                if response.status_code in (401, 403):
                    logger.error("Fallback Aeron API authorization failed")
                    raise ValueError("Fallback Aeron API authorization failed")
                
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.error("Fallback Aeron API request failed: %s", type(exc).__name__)
            raise ValueError("Failed to fetch data from the fallback Aeron API") from None
        
    def get_historical_readings(self, station_id: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        raise NotImplementedError("Historical endpoint not yet verified")

class MockAeronClient(AeronClient):
    def get_latest_reading(self, station_id: str) -> Dict[str, Any]:
        logger.info(f"Mock fetching latest reading for {station_id}")
        return {
            "recordedAt": datetime.utcnow().isoformat() + "Z",
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
                "63d0da020016a": 0.5,     # co_mg_m3
                "63d0da885f1a0": 20.1,    # no2_ug_m3
                "63d0daa4740ba": 5.2,     # so2_ug_m3
                "63d0daf2bcb74": 45.3,    # o3_ug_m3
                "63d0db066e993": 10.1,    # no_ug_m3
                "63d0db8f77ecb": 15.2,    # pm25_ug_m3
                "63d0dbb867a7c": 30.5,    # pm10_ug_m3
                "63d0dbfe0a111": 25.4,    # temperature_c
                "63d0dc28f109d": 60.2,    # relative_humidity_percent
                "63d0dc5164112": 0.0,     # rain_mm
                "63d0dd3721886": 12.5,    # wind_speed_kmph
                "63d0dd4ff30c9": 180,     # wind_direction_deg
                "63d0ddf115956": 55.2,    # noise_average_db
                "63d0de104027f": 45.1,    # noise_min_db
                "63d0de34a0b72": 75.3,    # noise_max_db
                "63d0de7568a3b": 5,       # uv_index
                "63d0ea1253e8f": 410.2,   # co2_ppm
                "63d0ee3fcd99a": 1012.3,  # barometric_pressure_mba
                "63d0eeb2aaeef": 24.45,   # molecular_volume_ltr
                "6422ae0f8147e": 42,      # air_quality_index
                "unknown_param_xyz": 999  # to test unknown handling
            }
        }

# Use the real AeronClient as requested
aeron_client = AeronClient()
