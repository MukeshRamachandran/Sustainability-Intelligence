from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_database_engine, create_session_factory
from app.routers.access import router as access_router
from app.routers.admin_outreach import router as admin_outreach_router
from app.routers.admin_users import router as admin_users_router
from app.routers.audit import router as audit_router
from app.routers.auth import router as auth_router
from app.routers.certificates import admin_router as certificate_admin_router
from app.routers.certificates import public_router as certificate_public_router
from app.routers.emission_factors import router as emission_factor_router
from app.routers.environment import router as environment_router
from app.routers.evidence import admin_router as evidence_admin_router
from app.routers.evidence import manager_router as evidence_manager_router
from app.routers.health import router as health_router
from app.routers.manager_outreach import router as manager_outreach_router
from app.routers.manager_submissions import router as manager_submissions_router
from app.routers.releases import admin_router as release_admin_router
from app.routers.releases import public_router as release_public_router
from app.routers.releases import readiness_router as publication_readiness_router
from app.storage.evidence import evidence_directory

API_VERSION = "0.1.0"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("x-request-id")
        try:
            request_id = str(UUID(supplied)) if supplied else str(uuid4())
        except ValueError:
            request_id = str(uuid4())
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.url.path.startswith(("/api/auth", "/api/admin", "/api/manager")):
            response.headers["Cache-Control"] = "private, no-store"
        return response


def error_payload(request: Request, code: str, message: str) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    institutional_clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    configured = settings or get_settings()
    configure_logging(configured.LOG_LEVEL)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configured.EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
        evidence_directory(configured).mkdir(parents=True, exist_ok=True)
        configured.CERTIFICATE_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        yield
        application.state.engine.dispose()

    application = FastAPI(
        title="K-COSMOS Backend API",
        version=API_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if configured.APP_ENV != "production" else None,
        redoc_url=None,
    )
    application.state.settings = configured
    application.state.institutional_clock = institutional_clock or (lambda: datetime.now(UTC))
    application.state.engine = engine or create_database_engine(configured.DATABASE_URL)
    application.state.session_factory = create_session_factory(application.state.engine)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)

    @application.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        code = "http_error"
        metadata: dict[str, object] = {}
        if isinstance(detail, str):
            message = detail
        elif isinstance(detail, dict):
            message = str(detail.get("message", "Request failed."))
            code = str(detail.get("code", code))
            metadata = {
                str(key): value
                for key, value in detail.items()
                if key not in {"code", "message"}
            }
        else:
            message = "Request failed."
        content = error_payload(request, code, message)
        error = content["error"]
        if isinstance(error, dict):
            error.update(metadata)
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(request, "validation_error", "Request validation failed."),
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
        structlog.get_logger().exception("unhandled_request_error")
        return JSONResponse(
            status_code=500,
            content=error_payload(request, "internal_error", "An internal error occurred."),
        )

    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(access_router)
    application.include_router(manager_outreach_router)
    application.include_router(manager_submissions_router)
    application.include_router(evidence_manager_router)
    application.include_router(admin_outreach_router)
    application.include_router(admin_users_router)
    application.include_router(audit_router)
    application.include_router(evidence_admin_router)
    application.include_router(emission_factor_router)
    application.include_router(release_admin_router)
    application.include_router(publication_readiness_router)
    application.include_router(release_public_router)
    application.include_router(certificate_admin_router)
    application.include_router(certificate_public_router)
    application.include_router(environment_router)
    return application


app = create_app()
