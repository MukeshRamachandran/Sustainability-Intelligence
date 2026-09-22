from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db

router = APIRouter()

@router.get("/latest", response_model=schemas.WeatherData)
def get_latest_weather(db: Session = Depends(get_db)):
    """Get the most recent weather data reading."""
    data = db.query(models.WeatherData).order_by(models.WeatherData.timestamp.desc()).first()
    if not data:
        raise HTTPException(status_code=404, detail="No weather data found")
    return data

@router.get("/history", response_model=List[schemas.WeatherData])
def get_weather_history(limit: int = 24, db: Session = Depends(get_db)):
    """Get historical weather data."""
    return db.query(models.WeatherData).order_by(models.WeatherData.timestamp.desc()).limit(limit).all()
