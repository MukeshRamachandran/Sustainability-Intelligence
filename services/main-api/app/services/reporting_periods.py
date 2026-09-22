from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.enums import SubmissionStatus
from app.models.sustainability import ReportingPeriod, Submission


def institutional_year_month(
    settings: Settings,
    clock: Callable[[], datetime] | None = None,
) -> tuple[int, int]:
    instant = (clock or (lambda: datetime.now(UTC)))()
    if instant.tzinfo is None:
        raise ValueError("institutional clock must return a timezone-aware datetime")
    local = instant.astimezone(ZoneInfo(settings.INSTITUTION_TIMEZONE))
    return local.year, local.month


def current_reporting_period(
    db: Session,
    settings: Settings,
    clock: Callable[[], datetime] | None = None,
) -> ReportingPeriod:
    year, month = institutional_year_month(settings, clock)
    period = db.scalar(
        select(ReportingPeriod).where(
            ReportingPeriod.year == year,
            ReportingPeriod.month == month,
        )
    )
    if period is None:
        raise HTTPException(status_code=503, detail="Current reporting period is not configured.")
    return period


def require_current_period_for_create(
    requested_period_id: object,
    current_period: ReportingPeriod,
) -> None:
    if requested_period_id != current_period.id:
        raise HTTPException(
            status_code=409,
            detail="Managers may create submissions only for the current reporting month.",
        )
    if not current_period.is_open:
        raise HTTPException(
            status_code=409,
            detail="This reporting period is closed for normal manager entry.",
        )


def require_manager_mutation(
    submission: Submission,
    current_period: ReportingPeriod,
) -> None:
    if submission.status == SubmissionStatus.CORRECTION_REQUESTED:
        return
    if submission.status != SubmissionStatus.DRAFT:
        raise HTTPException(
            status_code=409,
            detail="This monthly submission has already been submitted and is read-only.",
        )
    if submission.reporting_period_id != current_period.id or not current_period.is_open:
        raise HTTPException(
            status_code=409,
            detail="This reporting period is closed for normal manager entry.",
        )
