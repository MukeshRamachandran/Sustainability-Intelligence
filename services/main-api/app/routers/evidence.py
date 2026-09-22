from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.models.enums import OperationalDomain, SubmissionStatus
from app.schemas.auth import MessageResponse
from app.schemas.evidence import EvidenceRepositoryResponse, EvidenceResponse
from app.security.dependencies import (
    AdminUser,
    CsrfUser,
    DbSession,
    ManagerUser,
    enforce_manager_domain,
)
from app.services.evidence import (
    create_evidence,
    get_admin_submission,
    get_evidence,
    get_manager_submission,
    get_submission_evidence,
    list_evidence,
    remove_temporary_evidence,
    replace_temporary_evidence,
    require_evidence_editable,
    serialize_evidence,
    validate_attachment,
)
from app.services.evidence_repository import EvidenceRepositoryFilters, search_committed_evidence
from app.services.reporting_periods import current_reporting_period, require_manager_mutation
from app.storage.evidence import evidence_path, remove_new_file, store_upload

manager_router = APIRouter(prefix="/api/manager", tags=["manager evidence"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin evidence"])
logger = logging.getLogger(__name__)


def _file_response(request: Request, storage_key: str, mime_type: str, filename: str, download: bool) -> FileResponse:
    path = evidence_path(request.app.state.settings, storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Evidence content is unavailable.")
    response = FileResponse(
        path,
        media_type=mime_type,
        filename=filename,
        content_disposition_type="attachment" if download else "inline",
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _cleanup_temporary_file(request: Request, storage_key: str, evidence_id: UUID) -> None:
    try:
        remove_new_file(evidence_path(request.app.state.settings, storage_key))
    except Exception:
        # The metadata transaction is authoritative. A filesystem failure leaves
        # an unreferenced private object for controlled orphan cleanup.
        logger.error(
            "Temporary evidence file cleanup failed; orphan cleanup is required.",
            extra={"evidence_id": str(evidence_id)},
            exc_info=True,
        )


@manager_router.post(
    "/{domain}/submissions/{submission_id}/evidence",
    response_model=EvidenceResponse,
    status_code=201,
)
async def upload_manager_evidence(
    domain: OperationalDomain,
    submission_id: UUID,
    request: Request,
    current: CsrfUser,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    metric_code: Annotated[str | None, Form(max_length=100)] = None,
    evidence_category: Annotated[str | None, Form(max_length=100)] = None,
    replaces_evidence_id: Annotated[UUID | None, Form()] = None,
) -> EvidenceResponse:
    enforce_manager_domain(current, domain)
    submission = get_manager_submission(db, submission_id, current.user_id, domain)
    require_evidence_editable(submission)
    period = current_reporting_period(
        db, request.app.state.settings, request.app.state.institutional_clock
    )
    require_manager_mutation(submission, period)
    replaced = None
    if replaces_evidence_id is not None:
        replaced = get_submission_evidence(db, submission.id, replaces_evidence_id)
        metric_code = metric_code or replaced.metric_code
        evidence_category = evidence_category or replaced.evidence_category
    normalized_metric, normalized_category = validate_attachment(
        db, submission, metric_code, evidence_category
    )
    if replaced is not None and (
        normalized_metric != replaced.metric_code or normalized_category != replaced.evidence_category
    ):
        raise HTTPException(status_code=422, detail="Replacement evidence must retain its metric or category.")

    stored = await store_upload(file, request.app.state.settings)
    evidence = create_evidence(
        submission=submission,
        metric_code=normalized_metric,
        evidence_category=normalized_category,
        original_filename=stored.original_filename,
        storage_key=stored.storage_key,
        mime_type=stored.mime_type,
        file_size_bytes=stored.file_size_bytes,
        sha256=stored.sha256,
        uploaded_by_user_id=current.user_id,
    )
    replaced_storage_key = None
    replaced_evidence_id = replaced.id if replaced is not None else None
    try:
        db.add(evidence)
        db.flush()
        if replaced is not None:
            replaced_storage_key = replace_temporary_evidence(db, replaced, evidence)
        db.commit()
        db.refresh(evidence)
    except Exception:
        db.rollback()
        remove_new_file(stored.path)
        raise
    if replaced_storage_key is not None and replaced_evidence_id is not None:
        _cleanup_temporary_file(request, replaced_storage_key, replaced_evidence_id)
    return serialize_evidence(evidence)


@manager_router.get(
    "/{domain}/submissions/{submission_id}/evidence", response_model=list[EvidenceResponse]
)
def list_manager_evidence(
    domain: OperationalDomain,
    submission_id: UUID,
    current: ManagerUser,
    db: DbSession,
) -> list[EvidenceResponse]:
    enforce_manager_domain(current, domain)
    submission = get_manager_submission(db, submission_id, current.user_id, domain)
    return [serialize_evidence(item) for item in list_evidence(db, submission.id)]


@manager_router.get("/{domain}/evidence/{evidence_id}/content", response_class=FileResponse)
def manager_evidence_content(
    domain: OperationalDomain,
    evidence_id: UUID,
    request: Request,
    current: ManagerUser,
    db: DbSession,
    download: bool = Query(default=False),
) -> FileResponse:
    enforce_manager_domain(current, domain)
    evidence = get_evidence(db, evidence_id)
    submission = get_admin_submission(db, evidence.submission_id)
    if submission.domain != domain:
        raise HTTPException(status_code=403, detail="Manager domain access denied.")
    get_manager_submission(db, evidence.submission_id, current.user_id, domain)
    return _file_response(
        request, evidence.storage_key, evidence.mime_type, evidence.original_filename, download
    )


@manager_router.delete(
    "/{domain}/submissions/{submission_id}/evidence/{evidence_id}", response_model=MessageResponse
)
def delete_manager_evidence(
    domain: OperationalDomain,
    submission_id: UUID,
    evidence_id: UUID,
    request: Request,
    current: CsrfUser,
    db: DbSession,
) -> MessageResponse:
    enforce_manager_domain(current, domain)
    submission = get_manager_submission(db, submission_id, current.user_id, domain)
    require_evidence_editable(submission)
    period = current_reporting_period(
        db, request.app.state.settings, request.app.state.institutional_clock
    )
    require_manager_mutation(submission, period)
    evidence = get_submission_evidence(db, submission.id, evidence_id)
    storage_key = remove_temporary_evidence(db, evidence)
    db.commit()
    _cleanup_temporary_file(request, storage_key, evidence_id)
    return MessageResponse(message="Temporary evidence removed.")


@admin_router.get("/submissions/{submission_id}/evidence", response_model=list[EvidenceResponse])
def list_admin_evidence(
    submission_id: UUID, current: AdminUser, db: DbSession
) -> list[EvidenceResponse]:
    submission = get_admin_submission(db, submission_id)
    return [
        serialize_evidence(item)
        for item in list_evidence(db, submission.id, committed_only=True)
    ]


@admin_router.get("/evidence", response_model=EvidenceRepositoryResponse)
def evidence_repository(
    current: AdminUser,
    db: DbSession,
    year: int | None = Query(default=None, ge=2000, le=9999),
    month: int | None = Query(default=None, ge=1, le=12),
    domain: OperationalDomain | None = None,
    submission_status: SubmissionStatus | None = None,
    submission_id: UUID | None = None,
    revision_number: int | None = Query(default=None, ge=1),
    metric_code: str | None = Query(default=None, min_length=1, max_length=100),
    evidence_category: str | None = Query(default=None, min_length=1, max_length=100),
    filename: str | None = Query(default=None, min_length=1, max_length=255),
    latest_revision: bool = True,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> EvidenceRepositoryResponse:
    return search_committed_evidence(
        db,
        EvidenceRepositoryFilters(
            year=year,
            month=month,
            domain=domain,
            submission_status=submission_status,
            submission_id=submission_id,
            revision_number=revision_number,
            metric_code=metric_code.strip() if metric_code else None,
            evidence_category=evidence_category.strip().casefold() if evidence_category else None,
            filename=filename.strip() if filename else None,
            latest_revision=latest_revision,
        ),
        page=page,
        page_size=page_size,
    )


@admin_router.get("/evidence/{evidence_id}/content", response_class=FileResponse)
def admin_evidence_content(
    evidence_id: UUID,
    request: Request,
    current: AdminUser,
    db: DbSession,
    download: bool = Query(default=False),
) -> FileResponse:
    evidence = get_evidence(db, evidence_id)
    if evidence.committed_at is None:
        raise HTTPException(status_code=404, detail="Evidence not found.")
    return _file_response(
        request, evidence.storage_key, evidence.mime_type, evidence.original_filename, download
    )
