"""Public certificate registry: Admin-managed, publicly read-only.

Certificates are supporting documents. Nothing here reads or writes a
sustainability metric: ``quantity_value`` is document metadata only.

Admin: upload (creates a DRAFT), edit metadata, publish, archive, preview.
Public: years that have published certificates, the published certificates of a
year, and a published certificate's file. Drafts and archived documents are
never visible publicly.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.publication import Certificate
from app.schemas.certificates import (
    TEXT_FIELDS,
    AdminCertificateResponse,
    CertificateStatus,
    CertificateUpdate,
    PublicCertificate,
    PublicCertificateList,
    PublicCertificateYear,
    PublicCertificateYears,
    normalize_domain,
)
from app.security.dependencies import AdminUser, CsrfUser, DbSession, require_admin
from app.services.audit import add_audit_log
from app.storage.certificates import certificate_path, remove_new_certificate_file, store_certificate_upload

admin_router = APIRouter(prefix="/api/admin/certificates", tags=["admin certificates"])
public_router = APIRouter(prefix="/api/public/certificates", tags=["public certificates"])
logger = logging.getLogger(__name__)

DRAFT, PUBLISHED, ARCHIVED = "DRAFT", "PUBLISHED", "ARCHIVED"
PUBLIC_FILE_CACHE = "public, max-age=300"


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


def _domain(value: str) -> str:
    try:
        return normalize_domain(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Domain is invalid.") from exc


def _certificate(db: DbSession, certificate_id: UUID, *, lock: bool = False) -> Certificate:
    query = select(Certificate).where(Certificate.id == certificate_id)
    certificate = db.scalar(query.with_for_update() if lock else query)
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate not found.")
    return certificate


def _audit(db: DbSession, request: Request, current: CsrfUser, event: str, certificate: Certificate,
           metadata: dict[str, object] | None = None) -> None:
    add_audit_log(
        db,
        actor_user_id=current.user_id,
        actor_type="user",
        event_type=event,
        target_type="certificate",
        target_reference=str(certificate.id),
        outcome="succeeded",
        request_id=_request_id(request),
        metadata={"domain": certificate.domain, "reporting_year": certificate.reporting_year, **(metadata or {})},
    )


def _file_response(request: Request, certificate: Certificate, *, download: bool, cache: str) -> FileResponse:
    path = certificate_path(request.app.state.settings, certificate.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Certificate file is unavailable.")
    response = FileResponse(
        path,
        media_type=certificate.mime_type,
        filename=certificate.original_filename,
        content_disposition_type="attachment" if download else "inline",
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = cache
    return response


# ---- Admin -----------------------------------------------------------------------


@admin_router.get("", response_model=list[AdminCertificateResponse])
def list_certificates(
    current: AdminUser,
    db: DbSession,
    domain: Annotated[str | None, Query(max_length=40)] = None,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    status: Annotated[CertificateStatus | None, Query()] = None,
) -> list[Certificate]:
    query = select(Certificate)
    if domain:
        query = query.where(Certificate.domain == _domain(domain))
    if year is not None:
        query = query.where(Certificate.reporting_year == year)
    if status is not None:
        query = query.where(Certificate.status == status)
    return list(
        db.scalars(
            query.order_by(
                Certificate.reporting_year.desc(), Certificate.display_order, Certificate.received_date,
                Certificate.created_at, Certificate.id,
            )
        ).all()
    )


@admin_router.post("", response_model=AdminCertificateResponse, status_code=201)
async def upload_certificate(
    request: Request,
    current: CsrfUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    domain: Annotated[str, Form(max_length=40)],
    certificate_type: Annotated[str, Form(min_length=1, max_length=200)],
    reporting_year: Annotated[int, Form(ge=2000, le=2100)],
    title: Annotated[str, Form(min_length=1, max_length=300)],
    issuer: Annotated[str | None, Form(max_length=300)] = None,
    registration_id: Annotated[str | None, Form(max_length=100)] = None,
    authorization_no: Annotated[str | None, Form(max_length=100)] = None,
    serial_no: Annotated[str | None, Form(max_length=100)] = None,
    certificate_date: Annotated[date | None, Form()] = None,
    received_date: Annotated[date | None, Form()] = None,
    invoice_no: Annotated[str | None, Form(max_length=200)] = None,
    manifest_doc_no: Annotated[str | None, Form(max_length=200)] = None,
    quantity_value: Annotated[Decimal | None, Form(ge=0, max_digits=14, decimal_places=3)] = None,
    quantity_unit: Annotated[str | None, Form(max_length=20)] = None,
    display_order: Annotated[int, Form(ge=0, le=100000)] = 0,
    notes: Annotated[str | None, Form(max_length=4000)] = None,
) -> Certificate:
    require_admin(current)
    normalized_domain = _domain(domain)
    text = {
        "certificate_type": certificate_type, "title": title, "issuer": issuer, "registration_id": registration_id,
        "authorization_no": authorization_no, "serial_no": serial_no, "invoice_no": invoice_no,
        "manifest_doc_no": manifest_doc_no, "quantity_unit": quantity_unit, "notes": notes,
    }
    cleaned = {key: (value.strip() or None) if value is not None else None for key, value in text.items()}
    if not cleaned["certificate_type"] or not cleaned["title"]:
        raise HTTPException(status_code=422, detail="Certificate type and title are required.")

    stored = await store_certificate_upload(file, request.app.state.settings)
    try:
        existing = db.scalar(select(Certificate).where(Certificate.sha256 == stored.sha256))
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate_certificate",
                    "message": f"This document is already registered as '{existing.title}' ({existing.status}).",
                    "certificate_id": str(existing.id),
                },
            )
        certificate = Certificate(
            domain=normalized_domain,
            reporting_year=reporting_year,
            certificate_date=certificate_date,
            received_date=received_date,
            quantity_value=quantity_value,
            display_order=display_order,
            original_filename=stored.original_filename,
            storage_key=stored.storage_key,
            mime_type=stored.mime_type,
            byte_size=stored.byte_size,
            sha256=stored.sha256,
            status=DRAFT,
            created_by=current.user_id,
            **cleaned,
        )
        db.add(certificate)
        db.flush()
        _audit(db, request, current, "certificate.created", certificate,
               {"sha256": stored.sha256, "mime_type": stored.mime_type, "byte_size": stored.byte_size})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        remove_new_certificate_file(stored.path)
        raise HTTPException(
            status_code=409, detail={"code": "duplicate_certificate", "message": "This document is already registered."}
        ) from exc
    except Exception:
        db.rollback()
        remove_new_certificate_file(stored.path)
        raise
    db.refresh(certificate)
    return certificate


@admin_router.patch("/{certificate_id}", response_model=AdminCertificateResponse)
def update_certificate(
    certificate_id: UUID, payload: CertificateUpdate, request: Request, current: CsrfUser, db: DbSession
) -> Certificate:
    require_admin(current)
    certificate = _certificate(db, certificate_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    for required in ("domain", "certificate_type", "reporting_year", "title", "display_order"):
        if required in changes and changes[required] is None:
            raise HTTPException(status_code=422, detail=f"{required} cannot be empty.")
    changed: list[str] = []
    for field, value in changes.items():
        if field in TEXT_FIELDS and isinstance(value, str):
            value = value.strip() or None
        if getattr(certificate, field) != value:
            setattr(certificate, field, value)
            changed.append(field)
    if changed:
        certificate.updated_at = datetime.now(UTC)
        # Field names only: the audit log records what changed, not document contents.
        _audit(db, request, current, "certificate.updated", certificate, {"fields": sorted(changed)})
        db.commit()
        db.refresh(certificate)
    return certificate


@admin_router.post("/{certificate_id}/publish", response_model=AdminCertificateResponse)
def publish_certificate(certificate_id: UUID, request: Request, current: CsrfUser, db: DbSession) -> Certificate:
    require_admin(current)
    certificate = _certificate(db, certificate_id, lock=True)
    if certificate.status == PUBLISHED:
        return certificate
    if not certificate_path(request.app.state.settings, certificate.storage_key).is_file():
        raise HTTPException(status_code=409, detail="The certificate file is missing from storage.")
    previous = certificate.status
    now = datetime.now(UTC)
    certificate.status, certificate.published_at, certificate.archived_at = PUBLISHED, now, None
    certificate.updated_at = now
    _audit(db, request, current, "certificate.published", certificate, {"from_status": previous})
    db.commit()
    db.refresh(certificate)
    return certificate


@admin_router.post("/{certificate_id}/archive", response_model=AdminCertificateResponse)
def archive_certificate(certificate_id: UUID, request: Request, current: CsrfUser, db: DbSession) -> Certificate:
    require_admin(current)
    certificate = _certificate(db, certificate_id, lock=True)
    if certificate.status == ARCHIVED:
        return certificate
    previous = certificate.status
    now = datetime.now(UTC)
    certificate.status, certificate.archived_at, certificate.updated_at = ARCHIVED, now, now
    _audit(db, request, current, "certificate.archived", certificate, {"from_status": previous})
    db.commit()
    db.refresh(certificate)
    return certificate


@admin_router.get("/{certificate_id}/file")
def admin_certificate_file(
    certificate_id: UUID, request: Request, current: AdminUser, db: DbSession, download: bool = False
) -> FileResponse:
    return _file_response(request, _certificate(db, certificate_id), download=download, cache="private, no-store")


# ---- Public (read-only, PUBLISHED only) -------------------------------------------


@public_router.get("/years", response_model=PublicCertificateYears)
def public_certificate_years(db: DbSession, domain: Annotated[str, Query(max_length=40)]) -> PublicCertificateYears:
    normalized = _domain(domain)
    rows = db.execute(
        select(Certificate.reporting_year, func.count(Certificate.id))
        .where(Certificate.domain == normalized, Certificate.status == PUBLISHED)
        .group_by(Certificate.reporting_year)
        .order_by(Certificate.reporting_year.desc())
    ).all()
    types: dict[int, list[str]] = {}
    for year, certificate_type in db.execute(
        select(Certificate.reporting_year, Certificate.certificate_type)
        .where(Certificate.domain == normalized, Certificate.status == PUBLISHED)
        .distinct()
    ).all():
        types.setdefault(year, []).append(certificate_type)
    return PublicCertificateYears(
        domain=normalized,
        years=[
            PublicCertificateYear(year=year, certificate_count=count, certificate_types=sorted(types.get(year, [])))
            for year, count in rows
        ],
    )


@public_router.get("", response_model=PublicCertificateList)
def public_certificates(
    db: DbSession,
    domain: Annotated[str, Query(max_length=40)],
    year: Annotated[int, Query(ge=2000, le=2100)],
) -> PublicCertificateList:
    normalized = _domain(domain)
    rows = db.scalars(
        select(Certificate)
        .where(Certificate.domain == normalized, Certificate.reporting_year == year, Certificate.status == PUBLISHED)
        .order_by(Certificate.display_order, Certificate.received_date, Certificate.certificate_date, Certificate.id)
    ).all()
    try:
        certificates = [PublicCertificate.model_validate(row) for row in rows]
    except ValidationError as exc:  # pragma: no cover - a stored row always satisfies the public shape
        logger.error("Certificate row could not be serialized.", exc_info=True)
        raise HTTPException(status_code=500, detail="Certificate list is unavailable.") from exc
    return PublicCertificateList(domain=normalized, reporting_year=year, certificates=certificates)


@public_router.get("/{certificate_id}/file")
def public_certificate_file(
    certificate_id: UUID, request: Request, db: DbSession, download: bool = False
) -> FileResponse:
    certificate = db.scalar(
        select(Certificate).where(Certificate.id == certificate_id, Certificate.status == PUBLISHED)
    )
    if certificate is None:
        # Draft, archived and unknown documents are indistinguishable to the public.
        raise HTTPException(status_code=404, detail="Certificate not found.")
    return _file_response(request, certificate, download=download, cache=PUBLIC_FILE_CACHE)
