import logging
from ..aeron_client import aeron_client
from ..database import SessionLocal
from .data_processor import process_aeron_data

logger = logging.getLogger(__name__)

async def sync_device_data(device_id: str):
    """
    Fetch latest data for a device and process it into the database.
    Can be run as a background task.
    """
    try:
        raw_data = await aeron_client.get_latest_data(device_id)
        
        db = SessionLocal()
        try:
            process_aeron_data(db, raw_data, device_id)
            db.commit()
            logger.info(f"Successfully synced data for {device_id}")
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error syncing data for {device_id}: {str(e)}")
