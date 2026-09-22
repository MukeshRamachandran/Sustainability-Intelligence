import sys
import logging
from backend.database.connection import SessionLocal
from backend.services.aeron_sync_service import sync_aeron_station
from backend.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)

db = SessionLocal()
try:
    print("Testing sync...")
    log = sync_aeron_station(db, settings.aeron_station_id)
    print(f"Status: {log.status}")
    if log.status == 'FAILED':
        print(f"Error: {log.error_message}")
        sys.exit(1)
    
    # check latest
    from backend.database.models import AeronMeasurement
    latest = db.query(AeronMeasurement).order_by(AeronMeasurement.recorded_at.desc()).first()
    if latest:
        print(f"Latest Measurement at: {latest.recorded_at}")
        print(f"PM2.5: {latest.pm25_ug_m3}")
        print(f"Temperature: {latest.temperature_c}")
    else:
        print("No measurements found")
finally:
    db.close()
