from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db

router = APIRouter()

@router.get("/latest", response_model=schemas.AirQualityData)
def get_latest_aqi(db: Session = Depends(get_db)):
    """Get the most recent air quality data reading."""
    data = db.query(models.AirQualityData).order_by(models.AirQualityData.timestamp.desc()).first()
    if not data:
        raise HTTPException(status_code=404, detail="No air quality data found")
    return data

@router.get("/history", response_model=List[schemas.AirQualityData])
def get_aqi_history(limit: int = 24, db: Session = Depends(get_db)):
    """Get historical air quality data."""
    return db.query(models.AirQualityData).order_by(models.AirQualityData.timestamp.desc()).limit(limit).all()
