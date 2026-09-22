from __future__ import annotations

from calendar import month_name
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import OperationalDomain, SubmissionStatus
from app.models.sustainability import ReportingPeriod, Submission
from app.schemas.publication import (
    DomainPublicationStatus,
    PublicationBlocker,
    PublicationPeriod,
    PublicationReadinessResponse,
)

REQUIRED_PUBLICATION_DOMAINS = (
    OperationalDomain.TRANSPORT,
    OperationalDomain.ENERGY,
    OperationalDomain.LPG,
    OperationalDomain.WATER,
    OperationalDomain.OUTREACH,
    OperationalDomain.WASTE,
)


def evaluate_publication_readiness(
    db: Session,
    period: ReportingPeriod,
) -> PublicationReadinessResponse:
    submissions = db.scalars(
        select(Submission).where(
            Submission.reporting_period_id == period.id,
            Submission.domain.in_(REQUIRED_PUBLICATION_DOMAINS),
            Submission.status != SubmissionStatus.SUPERSEDED,
        )
    ).all()
    by_domain = {submission.domain: submission for submission in submissions}
    domains: dict[str, DomainPublicationStatus] = {}
    blockers: list[PublicationBlocker] = []
    approved_domains = 0

    for domain in REQUIRED_PUBLICATION_DOMAINS:
        submission = by_domain.get(domain)
        if submission is None:
            domains[domain.value] = DomainPublicationStatus(status="missing")
            blockers.append(
                PublicationBlocker(
                    domain=domain.value,
                    reason="missing_submission",
                    status="missing",
                )
            )
            continue
        domains[domain.value] = DomainPublicationStatus(
            status=submission.status.value,
            submission_id=submission.id,
            revision_number=submission.revision_number,
        )
        if submission.status == SubmissionStatus.APPROVED:
            approved_domains += 1
        else:
            blockers.append(
                PublicationBlocker(
                    domain=domain.value,
                    reason="not_approved",
                    status=submission.status.value,
                )
            )

    return PublicationReadinessResponse(
        reporting_period=PublicationPeriod(
            id=period.id,
            year=period.year,
            month=period.month,
            label=f"{month_name[period.month]} {period.year}",
        ),
        required_domains=len(REQUIRED_PUBLICATION_DOMAINS),
        approved_domains=approved_domains,
        ready_to_publish=approved_domains == len(REQUIRED_PUBLICATION_DOMAINS),
        domains=domains,
        blockers=blockers,
    )


def frozen_payload_blockers(payload: dict[str, Any]) -> list[dict[str, str]]:
    publication_status = payload.get("publication_status")
    statuses = publication_status if isinstance(publication_status, dict) else {}
    blockers: list[dict[str, str]] = []
    for domain in REQUIRED_PUBLICATION_DOMAINS:
        status = str(statuses.get(domain.value, "missing"))
        has_payload = payload.get(domain.value) is not None
        if status != "approved" or not has_payload:
            blockers.append(
                {
                    "domain": domain.value,
                    "status": str(status),
                    "reason": (
                        "missing_submission"
                        if status in {"missing", "missing_approved_submission"}
                        else "not_approved"
                    ),
                }
            )
    return blockers
