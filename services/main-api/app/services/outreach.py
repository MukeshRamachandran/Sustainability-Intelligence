from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import OperationalDomain, ReviewActionType, SubmissionStatus
from app.models.sustainability import OutreachProgramme, ReviewAction, Submission

THEMES = (
    "climate_smart_agriculture",
    "climate_change",
    "afforestation",
    "water_conservation",
    "waste_management",
    "biodiversity_conservation",
    "hwcc",
    "livelihood_development",
    "campus_sustainability",
)


def json_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def programme_snapshot(programme: OutreachProgramme) -> dict[str, object]:
    excluded = {"created_at", "updated_at"}
    return {
        column.name: json_value(getattr(programme, column.name))
        for column in OutreachProgramme.__table__.columns
        if column.name not in excluded
    }


def submission_snapshot(db: Session, submission: Submission) -> dict[str, object]:
    programmes = db.scalars(
        select(OutreachProgramme)
        .where(OutreachProgramme.submission_id == submission.id)
        .order_by(OutreachProgramme.programme_date, OutreachProgramme.id)
    ).all()
    return {
        "submission_id": str(submission.id),
        "domain": submission.domain.value,
        "reporting_period_id": str(submission.reporting_period_id),
        "revision_number": submission.revision_number,
        "programmes": [programme_snapshot(item) for item in programmes],
    }


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


def aggregate_approved_outreach(
    db: Session, period_id: UUID, *, submission_id: UUID | None = None
) -> dict[str, object]:
    conditions = [
        Submission.domain == OperationalDomain.OUTREACH,
        Submission.reporting_period_id == period_id,
        Submission.status == SubmissionStatus.APPROVED,
    ]
    if submission_id is not None:
        conditions.append(Submission.id == submission_id)
    programmes = db.scalars(
        select(OutreachProgramme)
        .join(Submission, Submission.id == OutreachProgramme.submission_id)
        .where(*conditions)
    ).all()

    def total(field: str) -> int | float:
        values = [getattr(item, field) for item in programmes]
        result = sum(value or 0 for value in values)
        return float(result) if isinstance(result, Decimal) else result

    partners = {
        " ".join(item.partner_organisation.split()).casefold()
        for item in programmes
        if item.partner_organisation and item.partner_organisation.strip()
    }
    theme_counts = Counter(item.theme for item in programmes if item.theme in THEMES)
    return {
        "total_programs": len(programmes),
        "total_participants": total("participant_total"),
        "partner_organizations": len(partners),
        "saplings_planted": total("saplings_planted"),
        "experts_involved": total("experts_involved"),
        "volunteers_engaged": total("volunteers_engaged"),
        "volunteer_hours": total("volunteer_hours"),
        "participants_by_category": {
            "school_students": total("school_students"),
            "college_students": total("college_students"),
            "farmers_agriculture": total("farmers_agriculture"),
            "industrial_experts": total("industrial_experts"),
            "researchers_experts": total("researchers_experts"),
            "government": total("government_participants"),
        },
        "themes": {theme: theme_counts[theme] for theme in THEMES},
    }
