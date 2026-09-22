import os
from pathlib import Path

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from app.db.session import database_is_ready
from app.storage.evidence import evidence_directory

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    database: str
    evidence: str


def evidence_is_ready(path: Path) -> bool:
    try:
        return path.is_dir() and os.access(path, os.R_OK | os.W_OK | os.X_OK)
    except OSError:
        return False


@router.get("/live", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
def ready(request: Request, response: Response) -> ReadyResponse:
    database_ready = database_is_ready(request.app.state.engine)
    evidence_ready = evidence_is_ready(request.app.state.settings.EVIDENCE_ROOT) and evidence_is_ready(
        evidence_directory(request.app.state.settings)
    )
    if not database_ready or not evidence_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(
            status="unavailable",
            database="ready" if database_ready else "unavailable",
            evidence="ready" if evidence_ready else "unavailable",
        )
    return ReadyResponse(status="ready", database="ready", evidence="ready")
