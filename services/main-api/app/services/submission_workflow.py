from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import OperationalDomain, ReviewActionType, SubmissionStatus
from app.models.identity import User
from app.models.sustainability import (
    MetricDefinition,
    ReportingPeriod,
    ReviewAction,
    Submission,
    SubmissionValue,
)
from app.schemas.submissions import (
    GenericSubmissionResponse,
    MetricValueResponse,
    MetricValueWrite,
    ReviewActionResponse,
)
from app.services.emission_factors import calculation_responses

GENERIC_DOMAINS = {
    OperationalDomain.TRANSPORT,
    OperationalDomain.ENERGY,
    OperationalDomain.LPG,
    OperationalDomain.WATER,
}
EDITABLE_STATUSES = {SubmissionStatus.DRAFT, SubmissionStatus.CORRECTION_REQUESTED}


def correction_reason(db: Session, submission_id: UUID) -> str | None:
    return db.scalar(
        select(ReviewAction.comment)
        .where(
            ReviewAction.submission_id == submission_id,
            ReviewAction.action == ReviewActionType.REQUEST_CORRECTION,
        )
        .order_by(ReviewAction.created_at.desc())
        .limit(1)
    )


def get_submission(
    db: Session,
    submission_id: UUID,
    *,
    domain: OperationalDomain | None = None,
    for_update: bool = False,
) -> Submission:
    query = select(Submission).where(Submission.id == submission_id)
    if domain is not None:
        query = query.where(Submission.domain == domain)
    submission = db.scalar(query.with_for_update() if for_update else query)
    if submission is None or submission.domain not in GENERIC_DOMAINS:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return submission


def get_owned_submission(
    db: Session,
    submission_id: UUID,
    user_id: UUID,
    domain: OperationalDomain,
    *,
    for_update: bool = False,
) -> Submission:
    query = select(Submission).where(
            Submission.id == submission_id,
            Submission.manager_user_id == user_id,
            Submission.domain == domain,
        )
    submission = db.scalar(query.with_for_update() if for_update else query)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return submission


def submission_snapshot(db: Session, submission: Submission) -> dict[str, object]:
    values = db.scalars(
        select(SubmissionValue)
        .where(SubmissionValue.submission_id == submission.id)
        .order_by(SubmissionValue.metric_code)
    ).all()
    return {
        "submission_id": str(submission.id),
        "domain": submission.domain.value,
        "reporting_period_id": str(submission.reporting_period_id),
        "revision_number": submission.revision_number,
        "values": [
            {
                "metric_code": item.metric_code,
                "value": str(item.value) if item.value is not None else None,
                "canonical_unit": item.canonical_unit,
                "quality_note": item.quality_note,
            }
            for item in values
        ],
    }


def serialize_submission(
    db: Session, submission: Submission, *, include_actions: bool = True
) -> GenericSubmissionResponse:
    period = db.get(ReportingPeriod, submission.reporting_period_id)
    if period is None:
        raise HTTPException(status_code=500, detail="Submission reporting period is missing.")
    manager = db.get(User, submission.manager_user_id)
    values = db.scalars(
        select(SubmissionValue)
        .join(MetricDefinition, MetricDefinition.code == SubmissionValue.metric_code)
        .where(SubmissionValue.submission_id == submission.id)
        .order_by(MetricDefinition.display_order, SubmissionValue.metric_code)
    ).all()
    actions = (
        db.scalars(
            select(ReviewAction)
            .where(ReviewAction.submission_id == submission.id)
            .order_by(ReviewAction.created_at, ReviewAction.id)
        ).all()
        if include_actions
        else []
    )
    return GenericSubmissionResponse(
        id=submission.id,
        domain=submission.domain,
        manager_user_id=submission.manager_user_id,
        manager_display_name=manager.display_name if manager else None,
        reporting_period_id=period.id,
        reporting_period_label=f"{period.year}-{period.month:02d}",
        status=submission.status,
        revision_number=submission.revision_number,
        row_version=submission.row_version,
        remarks=submission.remarks,
        submitted_at=submission.submitted_at,
        approved_at=submission.approved_at,
        correction_reason=correction_reason(db, submission.id),
        created_at=submission.created_at,
        updated_at=submission.updated_at,
        values=[
            MetricValueResponse(
                metric_code=item.metric_code,
                value=item.value,
                canonical_unit=item.canonical_unit,
                quality_note=item.quality_note,
            )
            for item in values
        ],
        review_actions=[
            ReviewActionResponse(
                action=item.action,
                from_status=item.from_status,
                to_status=item.to_status,
                comment=item.comment,
                created_at=item.created_at,
            )
            for item in actions
        ],
        calculations=calculation_responses(db, submission),
    )


def _validated_values(
    db: Session, domain: OperationalDomain, values: list[MetricValueWrite]
) -> list[tuple[MetricDefinition, MetricValueWrite]]:
    codes = [item.metric_code for item in values]
    definitions = {
        item.code: item
        for item in db.scalars(
            select(MetricDefinition).where(MetricDefinition.code.in_(codes), MetricDefinition.is_active.is_(True))
        ).all()
    }
    validated: list[tuple[MetricDefinition, MetricValueWrite]] = []
    for item in values:
        definition = definitions.get(item.metric_code)
        if definition is None or definition.operational_domain != domain:
            raise HTTPException(status_code=422, detail=f"Metric '{item.metric_code}' is not valid for {domain.value}.")
        if not definition.manager_editable:
            raise HTTPException(
                status_code=422, detail=f"Metric '{item.metric_code}' is calculated and cannot be written."
            )
        if item.value is not None:
            value = Decimal(item.value)
            if definition.canonical_unit.casefold() == "count" and value != value.to_integral_value():
                raise HTTPException(status_code=422, detail=f"Metric '{item.metric_code}' must be a whole number.")
            if value == 0 and not definition.zero_allowed:
                raise HTTPException(status_code=422, detail=f"Metric '{item.metric_code}' does not allow zero.")
            if definition.min_value is not None and value < definition.min_value:
                raise HTTPException(status_code=422, detail=f"Metric '{item.metric_code}' is below its minimum.")
            if definition.max_value is not None and value > definition.max_value:
                raise HTTPException(status_code=422, detail=f"Metric '{item.metric_code}' is above its maximum.")
        validated.append((definition, item))
    return validated


def save_values(
    db: Session,
    submission: Submission,
    values: list[MetricValueWrite],
    remarks: str | None,
) -> None:
    if submission.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409, detail="Submitted, under-review, or approved submissions cannot be edited."
        )
    validated = _validated_values(db, submission.domain, values)
    editable_codes = db.scalars(
        select(MetricDefinition.code).where(
            MetricDefinition.operational_domain == submission.domain,
            MetricDefinition.manager_editable.is_(True),
        )
    ).all()
    db.execute(
        delete(SubmissionValue).where(
            SubmissionValue.submission_id == submission.id,
            SubmissionValue.metric_code.in_(editable_codes),
        )
    )
    for definition, item in validated:
        if item.value is None:
            continue
        db.add(
            SubmissionValue(
                submission_id=submission.id,
                metric_code=definition.code,
                value=item.value,
                canonical_unit=definition.canonical_unit,
                quality_note=item.quality_note or None,
            )
        )
    submission.remarks = remarks or None
    submission.row_version += 1
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=422, detail="One or more metric values are invalid.") from exc


def validate_complete(db: Session, submission: Submission) -> None:
    required = set(
        db.scalars(
            select(MetricDefinition.code).where(
                MetricDefinition.operational_domain == submission.domain,
                MetricDefinition.required_for_complete.is_(True),
                MetricDefinition.manager_editable.is_(True),
                MetricDefinition.is_active.is_(True),
            )
        ).all()
    )
    supplied = set(
        db.scalars(
            select(SubmissionValue.metric_code).where(
                SubmissionValue.submission_id == submission.id,
                SubmissionValue.value.is_not(None),
            )
        ).all()
    )
    missing = sorted(required - supplied)
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Required metrics are missing.", "metrics": missing})


def submit(db: Session, submission: Submission, actor_user_id: UUID) -> None:
    if submission.status not in EDITABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Submission is not editable.")
    validate_complete(db, submission)
    previous = submission.status
    if previous == SubmissionStatus.CORRECTION_REQUESTED:
        submission.revision_number += 1
    submission.status = SubmissionStatus.SUBMITTED
    submission.submitted_at = datetime.now(UTC)
    submission.row_version += 1
    db.add(
        ReviewAction(
            submission_id=submission.id,
            actor_user_id=actor_user_id,
            action=ReviewActionType.SUBMIT,
            from_status=previous,
            to_status=SubmissionStatus.SUBMITTED,
            snapshot=submission_snapshot(db, submission),
        )
    )


def json_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
