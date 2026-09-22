from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.enums import OperationalDomain, SubmissionStatus
from app.models.identity import User
from app.models.sustainability import (
    MetricDefinition,
    ReportingPeriod,
    Submission,
    SubmissionEvidence,
)
from app.schemas.evidence import (
    EvidenceRepositoryItem,
    EvidenceRepositoryPeriod,
    EvidenceRepositoryResponse,
    EvidenceRepositoryUploader,
)

REPOSITORY_STATUSES = (
    SubmissionStatus.SUBMITTED,
    SubmissionStatus.UNDER_REVIEW,
    SubmissionStatus.CORRECTION_REQUESTED,
    SubmissionStatus.APPROVED,
)


@dataclass(frozen=True)
class EvidenceRepositoryFilters:
    year: int | None = None
    month: int | None = None
    domain: OperationalDomain | None = None
    submission_status: SubmissionStatus | None = None
    submission_id: UUID | None = None
    revision_number: int | None = None
    metric_code: str | None = None
    evidence_category: str | None = None
    filename: str | None = None
    latest_revision: bool = True


def _escaped_contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _apply_filters(
    query: Select[Any], filters: EvidenceRepositoryFilters
) -> Select[Any]:
    query = query.where(
        SubmissionEvidence.committed_at.is_not(None),
        Submission.status.in_(REPOSITORY_STATUSES),
    )
    if filters.year is not None:
        query = query.where(ReportingPeriod.year == filters.year)
    if filters.month is not None:
        query = query.where(ReportingPeriod.month == filters.month)
    if filters.domain is not None:
        query = query.where(Submission.domain == filters.domain)
    if filters.submission_status is not None:
        query = query.where(Submission.status == filters.submission_status)
    if filters.submission_id is not None:
        query = query.where(Submission.id == filters.submission_id)
    if filters.revision_number is not None:
        query = query.where(SubmissionEvidence.revision_number == filters.revision_number)
    if filters.metric_code:
        query = query.where(SubmissionEvidence.metric_code == filters.metric_code)
    if filters.evidence_category:
        query = query.where(SubmissionEvidence.evidence_category == filters.evidence_category)
    if filters.filename:
        query = query.where(
            SubmissionEvidence.original_filename.ilike(
                _escaped_contains(filters.filename), escape="\\"
            )
        )
    if filters.latest_revision:
        query = query.where(SubmissionEvidence.revision_number == Submission.revision_number)
    return query


def search_committed_evidence(
    db: Session,
    filters: EvidenceRepositoryFilters,
    *,
    page: int,
    page_size: int,
) -> EvidenceRepositoryResponse:
    joined = (
        select(SubmissionEvidence)
        .join(Submission, Submission.id == SubmissionEvidence.submission_id)
        .join(ReportingPeriod, ReportingPeriod.id == Submission.reporting_period_id)
    )
    count_query = _apply_filters(
        select(func.count(SubmissionEvidence.id))
        .join(Submission, Submission.id == SubmissionEvidence.submission_id)
        .join(ReportingPeriod, ReportingPeriod.id == Submission.reporting_period_id),
        filters,
    )
    total_items = int(db.scalar(count_query) or 0)

    item_query = _apply_filters(
        joined.add_columns(Submission, ReportingPeriod, User, MetricDefinition.display_name)
        .join(User, User.id == SubmissionEvidence.uploaded_by_user_id)
        .outerjoin(MetricDefinition, MetricDefinition.code == SubmissionEvidence.metric_code),
        filters,
    ).order_by(
        ReportingPeriod.year.desc(),
        ReportingPeriod.month.desc(),
        Submission.domain,
        SubmissionEvidence.revision_number.desc(),
        SubmissionEvidence.committed_at.desc(),
        SubmissionEvidence.id,
    )
    rows = db.execute(item_query.offset((page - 1) * page_size).limit(page_size)).all()
    items = [
        EvidenceRepositoryItem(
            evidence_id=evidence.id,
            submission_id=submission.id,
            domain=submission.domain.value,
            reporting_period=EvidenceRepositoryPeriod(
                id=period.id,
                year=period.year,
                month=period.month,
            ),
            submission_status=submission.status.value,
            revision_number=evidence.revision_number,
            is_latest_revision=evidence.revision_number == submission.revision_number,
            metric_code=evidence.metric_code,
            metric_display_name=metric_display_name,
            evidence_category=evidence.evidence_category,
            original_filename=evidence.original_filename,
            mime_type=evidence.mime_type,
            file_size_bytes=evidence.file_size_bytes,
            sha256=evidence.sha256,
            uploaded_at=evidence.uploaded_at,
            committed_at=evidence.committed_at,
            uploaded_by=EvidenceRepositoryUploader(
                id=uploader.id,
                display_name=uploader.display_name,
            ),
        )
        for evidence, submission, period, uploader, metric_display_name in rows
        if evidence.committed_at is not None
    ]
    return EvidenceRepositoryResponse(
        items=items,
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=(total_items + page_size - 1) // page_size,
    )
