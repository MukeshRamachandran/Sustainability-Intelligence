from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import OperationalDomain, SubmissionStatus
from app.models.sustainability import MetricDefinition, Submission, SubmissionEvidence
from app.schemas.evidence import EvidenceResponse
from app.services.submission_workflow import EDITABLE_STATUSES

CATEGORY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")


def get_manager_submission(
    db: Session, submission_id: UUID, user_id: UUID, domain: OperationalDomain
) -> Submission:
    submission = db.scalar(
        select(Submission).where(
            Submission.id == submission_id,
            Submission.manager_user_id == user_id,
            Submission.domain == domain,
        )
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return submission


def get_admin_submission(db: Session, submission_id: UUID) -> Submission:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return submission


def require_evidence_editable(submission: Submission) -> None:
    if submission.status not in EDITABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Evidence is read-only for this submission status.")


def validate_attachment(
    db: Session,
    submission: Submission,
    metric_code: str | None,
    evidence_category: str | None,
) -> tuple[str | None, str | None]:
    normalized_metric = metric_code.strip() if metric_code else None
    normalized_category = evidence_category.strip().casefold() if evidence_category else None
    if normalized_metric:
        definition = db.get(MetricDefinition, normalized_metric)
        if (
            definition is None
            or not definition.is_active
            or definition.operational_domain != submission.domain
        ):
            raise HTTPException(status_code=422, detail="Evidence metric is not valid for this submission domain.")
    if normalized_category and not CATEGORY_PATTERN.fullmatch(normalized_category):
        raise HTTPException(status_code=422, detail="Evidence category is invalid.")
    if not normalized_metric and not normalized_category:
        normalized_category = "general"
    return normalized_metric, normalized_category


def evidence_revision(submission: Submission) -> int:
    return submission.revision_number + (submission.status == SubmissionStatus.CORRECTION_REQUESTED)


def get_evidence(db: Session, evidence_id: UUID) -> SubmissionEvidence:
    evidence = db.get(SubmissionEvidence, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found.")
    return evidence


def get_submission_evidence(db: Session, submission_id: UUID, evidence_id: UUID) -> SubmissionEvidence:
    evidence = db.scalar(
        select(SubmissionEvidence).where(
            SubmissionEvidence.id == evidence_id,
            SubmissionEvidence.submission_id == submission_id,
        )
    )
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found.")
    return evidence


def list_evidence(
    db: Session, submission_id: UUID, *, committed_only: bool = False
) -> list[SubmissionEvidence]:
    query = select(SubmissionEvidence).where(SubmissionEvidence.submission_id == submission_id)
    if committed_only:
        query = query.where(SubmissionEvidence.committed_at.is_not(None))
    return list(
        db.scalars(
            query.order_by(
                SubmissionEvidence.revision_number.desc(),
                SubmissionEvidence.committed_at.desc().nulls_first(),
                SubmissionEvidence.is_current.desc(),
                SubmissionEvidence.uploaded_at.desc(),
            )
        ).all()
    )


def create_evidence(
    *,
    submission: Submission,
    metric_code: str | None,
    evidence_category: str | None,
    original_filename: str,
    storage_key: str,
    mime_type: str,
    file_size_bytes: int,
    sha256: str,
    uploaded_by_user_id: UUID,
) -> SubmissionEvidence:
    return SubmissionEvidence(
        id=uuid4(),
        submission_id=submission.id,
        metric_code=metric_code,
        evidence_category=evidence_category,
        original_filename=original_filename,
        storage_key=storage_key,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        sha256=sha256,
        uploaded_by_user_id=uploaded_by_user_id,
        revision_number=evidence_revision(submission),
        is_current=True,
    )


def replace_temporary_evidence(
    db: Session, previous: SubmissionEvidence, replacement: SubmissionEvidence
) -> str | None:
    if not previous.is_current or previous.removed_at is not None:
        raise HTTPException(status_code=409, detail="Only current evidence can be replaced.")
    if previous.committed_at is not None:
        # A correction creates a new working candidate. The prior submitted row
        # remains untouched as permanent revision history.
        return None
    storage_key = previous.storage_key
    db.delete(previous)
    return storage_key


def remove_temporary_evidence(db: Session, evidence: SubmissionEvidence) -> str:
    if evidence.committed_at is not None:
        raise HTTPException(status_code=409, detail="Committed evidence cannot be removed.")
    if not evidence.is_current or evidence.removed_at is not None:
        raise HTTPException(status_code=409, detail="Evidence is already removed or superseded.")
    storage_key = evidence.storage_key
    db.delete(evidence)
    return storage_key


def commit_temporary_evidence(db: Session, submission: Submission) -> list[SubmissionEvidence]:
    evidence = list(
        db.scalars(
            select(SubmissionEvidence).where(
                SubmissionEvidence.submission_id == submission.id,
                SubmissionEvidence.revision_number == submission.revision_number,
                SubmissionEvidence.committed_at.is_(None),
                SubmissionEvidence.is_current.is_(True),
                SubmissionEvidence.removed_at.is_(None),
            )
        ).all()
    )
    committed_at = datetime.now(UTC)
    for item in evidence:
        item.committed_at = committed_at
    return evidence


def serialize_evidence(evidence: SubmissionEvidence) -> EvidenceResponse:
    return EvidenceResponse(
        id=evidence.id,
        submission_id=evidence.submission_id,
        metric_code=evidence.metric_code,
        evidence_category=evidence.evidence_category,
        original_filename=evidence.original_filename,
        mime_type=evidence.mime_type,
        file_size_bytes=evidence.file_size_bytes,
        sha256=evidence.sha256,
        uploaded_at=evidence.uploaded_at,
        committed_at=evidence.committed_at,
        lifecycle_state="committed" if evidence.committed_at is not None else "temporary",
        revision_number=evidence.revision_number,
        is_current=evidence.is_current,
        superseded_at=evidence.superseded_at,
        replaced_by_evidence_id=evidence.replaced_by_evidence_id,
        removed_at=evidence.removed_at,
    )
