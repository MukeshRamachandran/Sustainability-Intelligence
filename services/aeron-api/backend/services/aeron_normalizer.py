from typing import Dict, Any
import logging
from datetime import datetime, timedelta
from backend.config import settings
from backend.services.aeron_parameter_service import AERON_PARAMETER_MAP

logger = logging.getLogger(__name__)

def normalize_aeron_reading(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes a verified Aeron reading JSON payload into the database schema format.
    """
    recorded_at_str = payload.get("recordedAt")
    recorded_at = None
    if recorded_at_str:
        # Handle the trailing Z from Aeron payload
        source_recorded_at = datetime.fromisoformat(recorded_at_str.replace("Z", "+00:00"))
        # The device's clock is in UTC, but Aeron's backend assumes it's in IST (Asia/Kolkata),
        # so it erroneously subtracts 5.5 hours to convert it to UTC for the API.
        # We must add 5.5 hours back to get the correct absolute time.
        recorded_at = source_recorded_at + timedelta(minutes=settings.aeron_timestamp_correction_minutes)
    else:
        source_recorded_at = None

    normalized = {
        "source_recorded_at": source_recorded_at,
        "recorded_at": recorded_at,
        "raw_payload": payload
    }

    # Extract health metrics
    health = payload.get("health", {})
    normalized["network"] = health.get("network")
    normalized["battery"] = health.get("battery")
    normalized["charging"] = health.get("charging")
    normalized["device_temp"] = health.get("DeviceTemp")

    # We do not strictly use location in measurements table, but it's preserved in raw_payload

    # Iterate over data to resolve parameters
    data = payload.get("data", {})
    for param_id, value in data.items():
        if param_id in AERON_PARAMETER_MAP:
            field_name = AERON_PARAMETER_MAP[param_id]["normalized_name"]
            normalized[field_name] = value
        else:
            logger.warning(f"Unknown parameter ID in payload: {param_id} with value {value}")
            # Unknown parameters are retained in raw_payload, as it contains the full original payload

    return normalized
