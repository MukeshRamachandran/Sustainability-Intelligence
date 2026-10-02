from datetime import UTC, date, datetime
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
    EnergySummaryResponse,
    GenericSubmissionResponse,
    MetricValueResponse,
    MetricValueWrite,
    ReviewActionResponse,
)
from app.schemas.waste import WasteItemWrite
from app.services import dg_methodology as dg
from app.services import waste as waste_service
from app.services.emission_factors import calculation_responses
from app.services.publication import electricity_indicators

GENERIC_DOMAINS = {
    OperationalDomain.TRANSPORT,
    OperationalDomain.ENERGY,
    OperationalDomain.LPG,
    OperationalDomain.WATER,
    OperationalDomain.WASTE,
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
        waste=(
            waste_service.summary(db, submission)
            if submission.domain is OperationalDomain.WASTE
            else None
        ),
        energy=(
            EnergySummaryResponse.model_validate(
                {
                    **electricity_indicators(db, submission),
                    "provisional": submission.status in EDITABLE_STATUSES,
                }
            )
            if submission.domain is OperationalDomain.ENERGY
            else None
        ),
    )


def _period_start(db: Session, submission: Submission) -> date:
    period = db.get(ReportingPeriod, submission.reporting_period_id)
    if period is None:
        raise HTTPException(status_code=500, detail="Submission reporting period is missing.")
    return period.period_start


def _validated_values(
    db: Session, domain: OperationalDomain, values: list[MetricValueWrite], period_start: date
) -> list[tuple[MetricDefinition, MetricValueWrite]]:
    # The DG activity a Manager may not enter for this period: litres once the
    # governed SFC is in force (they are derived from kWh), kWh before it.
    superseded = dg.superseded_manager_metric(db, period_start) if domain is OperationalDomain.TRANSPORT else None
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
        if item.metric_code == superseded and item.value is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Metric '{item.metric_code}' is not the DG source for this reporting period; "
                    f"enter '{dg.manager_source_metric(db, period_start)}' instead."
                ),
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
    waste_items: list[WasteItemWrite] | None = None,
) -> None:
    """Save metric values, remarks and (for waste) the dry-material inventory.

    Everything happens in the caller's single transaction, so a waste save can
    never persist the wet value while the item rows fail, or the reverse.
    """
    if submission.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409, detail="Submitted, under-review, or approved submissions cannot be edited."
        )
    if waste_items is not None and submission.domain is not OperationalDomain.WASTE:
        raise HTTPException(
            status_code=422, detail="waste_items is only valid for a waste submission."
        )
    validated = _validated_values(db, submission.domain, values, _period_start(db, submission))
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
    if submission.domain is OperationalDomain.WASTE and waste_items is not None:
        # Items are replaced inside this same transaction, so the wet value,
        # remarks and inventory move together or not at all. The database
        # trigger refreshes dry/total from the resulting rows.
        waste_service.replace_items(db, submission, waste_items)


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
    if submission.domain is OperationalDomain.TRANSPORT:
        required.discard(dg.superseded_manager_metric(db, _period_start(db, submission)))
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
    # Waste consistency runs first so a stale derived total is corrected before
    # the required-metric check reads it.
    waste_service.validate_waste_complete(db, submission)
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
