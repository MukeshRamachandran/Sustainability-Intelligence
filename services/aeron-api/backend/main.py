import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.config import settings
from backend.database.connection import SessionLocal
from backend.routes import environment, sync
from backend.services.aeron_sync_service import sync_aeron_station

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


async def _sync_loop(stop: asyncio.Event) -> None:
    interval = max(settings.aeron_sync_interval_seconds, 60)
    while not stop.is_set():
        if settings.aeron_station_id:
            try:
                await asyncio.to_thread(_run_scheduled_sync)
            except Exception:
                logger.exception("Scheduled Aeron sync failed without stopping the service.")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass


def _run_scheduled_sync() -> None:
    with SessionLocal() as db:
        sync_aeron_station(db, settings.aeron_station_id)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    stop = asyncio.Event()
    task = None
    if settings.aeron_sync_enabled:
        task = asyncio.create_task(_sync_loop(stop))
    yield
    stop.set()
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    app = FastAPI(
        title="Aeron Environment Dashboard API",
        description="Internal environmental collection and public read API for K-COSMOS",
        version="1.1.0",
        lifespan=lifespan,
    )

    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "X-Internal-Sync-Token"],
        )

    app.include_router(environment.router, prefix="/api/environment", tags=["Environment"])
    app.include_router(sync.router, prefix="/api/environment", tags=["Environment sync"])

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def health_ready() -> dict[str, object]:
        missing = []
        if not settings.aeron_station_id:
            missing.append("AERON_STATION_ID")
        if not settings.public_api_url and not (
            settings.aeron_fallback_enabled and settings.fallback_api_url
        ):
            missing.append("AERON_PUBLIC_API_URL or enabled fallback URL")
        if settings.public_api_url and not settings.aeron_api_key:
            missing.append("AERON_API_KEY")
        if not settings.public_api_url and settings.fallback_api_url and not settings.aeron_session_cookie:
            missing.append("AERON_SESSION_COOKIE")
        try:
            with SessionLocal() as db:
                db.execute(text("select 1"))
        except Exception as exc:
            logger.warning("Aeron readiness database check failed: %s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Database is not ready.") from None
        if missing:
            raise HTTPException(status_code=503, detail={"missing_configuration": missing})
        return {"status": "ready", "database": "connected", "upstream_required": False}

    return app


app = create_app()
