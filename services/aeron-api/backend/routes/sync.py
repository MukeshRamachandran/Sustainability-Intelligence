import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.schemas.environment import SyncLogResponse
from backend.services.aeron_sync_service import sync_aeron_station
from backend.config import settings

router = APIRouter()


def require_internal_sync_token(
    token: str | None = Header(default=None, alias="X-Internal-Sync-Token"),
) -> None:
    configured = settings.aeron_internal_sync_token
    if not configured:
        raise HTTPException(status_code=503, detail="Manual sync is not configured.")
    if token is None or not hmac.compare_digest(token, configured):
        raise HTTPException(status_code=403, detail="Manual sync authorization required.")


@router.post("/sync", response_model=SyncLogResponse, dependencies=[Depends(require_internal_sync_token)])
def trigger_sync(db: Session = Depends(get_db)):
    """
    Triggers a manual sync operation from Aeron API to Database.
    """
    station_id = settings.aeron_station_id
    if not station_id:
        raise HTTPException(status_code=500, detail="AERON_STATION_ID not configured")
        
    sync_log = sync_aeron_station(db, station_id)
    if sync_log.status == "FAILED":
        raise HTTPException(status_code=502, detail="Aeron upstream sync failed.")
        
    return sync_log

