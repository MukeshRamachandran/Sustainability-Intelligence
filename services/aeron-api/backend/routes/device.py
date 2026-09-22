from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db

router = APIRouter()

@router.get("/", response_model=List[schemas.Device])
def get_devices(db: Session = Depends(get_db)):
    """Get all registered devices."""
    return db.query(models.Device).all()

@router.get("/{device_id}", response_model=schemas.Device)
def get_device(device_id: str, db: Session = Depends(get_db)):
    """Get a specific device by its ID."""
    device = db.query(models.Device).filter(models.Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device
