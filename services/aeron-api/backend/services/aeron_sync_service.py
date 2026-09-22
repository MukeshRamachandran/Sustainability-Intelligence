import logging
import time
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.services.aeron_client import aeron_client
from backend.services.aeron_normalizer import normalize_aeron_reading
from backend.database.models import AeronMeasurement, AeronSyncLog, AeronStation
from backend.config import settings

logger = logging.getLogger(__name__)

def sync_aeron_station(db: Session, station_id: str):
    """
    Syncs the latest reading for a given station from the Aeron API into the database.
    """
    start_time = datetime.now(timezone.utc)
    sync_log = AeronSyncLog(started_at=start_time, status="IN_PROGRESS")
    db.add(sync_log)
    db.commit()
    db.refresh(sync_log)

    try:
        max_retries = max(1, settings.aeron_retry_count)
        base_delay = 2

        for attempt in range(max_retries):
            try:
                # Fetch data
                try:
                    raw_payload = aeron_client.get_latest_reading(station_id)
                    logger.info("Successfully fetched data from public Aeron API.")
                except Exception as e:
                    if not settings.aeron_fallback_enabled or not aeron_client.internal_base_url:
                        raise
                    logger.warning(
                        "Public API failed for station %s (%s); attempting fallback.",
                        station_id,
                        type(e).__name__,
                    )
                    raw_payload = aeron_client.get_latest_reading_internal(station_id)
                    logger.info("Successfully fetched data from internal Aeron API fallback.")

                sync_log.records_received = 1
                
                if not raw_payload or "recordedAt" not in raw_payload:
                    raise ValueError("Invalid payload from Aeron API: missing recordedAt")

                # Normalize data
                normalized_data = normalize_aeron_reading(raw_payload)
                
                # Ensure station exists
                station = db.query(AeronStation).filter(AeronStation.aeron_station_id == station_id).first()
                if not station:
                    station = AeronStation(aeron_station_id=station_id, name=f"Station {station_id}")
                    db.add(station)
                    db.commit()

                # Keep the database uniqueness constraint authoritative while
                # avoiding dialect-specific SQL in the service layer.
                normalized_data['station_id'] = station_id
                duplicate = db.query(AeronMeasurement.id).filter(
                    AeronMeasurement.station_id == station_id,
                    AeronMeasurement.recorded_at == normalized_data['recorded_at'],
                ).first()
                if duplicate is None:
                    db.add(AeronMeasurement(**normalized_data))
                    db.commit()
                    sync_log.records_inserted = 1
                else:
                    sync_log.records_skipped = 1
                    
                sync_log.status = "SUCCESS"
                break  # Success, exit the retry loop

            except Exception as e:
                db.rollback()
                logger.error(
                    "Sync attempt %s/%s failed for station %s (%s)",
                    attempt + 1,
                    max_retries,
                    station_id,
                    type(e).__name__,
                )
                if attempt < max_retries - 1:
                    sleep_time = base_delay * (2 ** attempt)
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    sync_log.status = "FAILED"
                    sync_log.error_message = f"Failed after {max_retries} attempts ({type(e).__name__})."
    
    finally:
        sync_log.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sync_log)
        
    return sync_log
