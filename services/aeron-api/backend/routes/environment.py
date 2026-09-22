from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone

from backend.database.connection import get_db
from backend.database.models import AeronMeasurement
from backend.schemas.environment import AeronMeasurementResponse

router = APIRouter()


def classify_freshness(recorded_at: datetime | None, now: datetime | None = None) -> str:
    if recorded_at is None:
        return "OFFLINE"
    current = now or datetime.now(timezone.utc)
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    age_seconds = max(0.0, (current - recorded_at).total_seconds())
    if age_seconds < 10 * 60:
        return "LIVE"
    if age_seconds <= 30 * 60:
        return "STALE"
    return "OFFLINE"

@router.get("/latest", response_model=AeronMeasurementResponse)
def get_latest_environment(db: Session = Depends(get_db)):
    """
    Returns the latest normalized KCT measurement.
    """
    measurement = db.query(AeronMeasurement).order_by(AeronMeasurement.recorded_at.desc()).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="No measurements found")
    return measurement

@router.get("/history", response_model=List[AeronMeasurementResponse])
def get_environment_history(
    station_id: Optional[str] = None,
    start: Optional[datetime] = Query(None, description="Start time (ISO 8601)"),
    end: Optional[datetime] = Query(None, description="End time (ISO 8601)"),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db)
):
    """
    Returns historical normalized measurements based on filters.
    """
    query = db.query(AeronMeasurement)
    
    if station_id:
        query = query.filter(AeronMeasurement.station_id == station_id)
    if start:
        query = query.filter(AeronMeasurement.recorded_at >= start)
    if end:
        query = query.filter(AeronMeasurement.recorded_at <= end)
        
    measurements = query.order_by(AeronMeasurement.recorded_at.desc()).limit(limit).all()
    return measurements

@router.get("/status")
def get_environment_status(db: Session = Depends(get_db)):
    """
    Returns API config status, database status, last successful sync, and last reading timestamp.
    """
    from backend.config import settings
    from backend.database.models import AeronSyncLog
    
    try:
        last_sync = db.query(AeronSyncLog).order_by(AeronSyncLog.started_at.desc()).first()
        last_measurement = db.query(AeronMeasurement).order_by(AeronMeasurement.recorded_at.desc()).first()
        db_status = "connected"
    except Exception:
        last_sync = None
        last_measurement = None
        db_status = "error"
        
    return {
        "station": settings.aeron_station_id,
        "latest_timestamp": last_measurement.recorded_at if last_measurement else None,
        "freshness": classify_freshness(last_measurement.recorded_at if last_measurement else None),
        "last_sync": last_sync.started_at if last_sync else None,
        "data_availability": "available" if last_measurement else "unavailable",
        "connection_status": db_status
    }
