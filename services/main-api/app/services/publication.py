from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.enums import OperationalDomain, PublicationClass, SubmissionStatus
from app.models.sustainability import MetricDefinition, ReportingPeriod, Submission, SubmissionValue
from app.schemas.emission_factors import CalculationResponse
from app.services.emission_factors import calculation_responses
from app.services.outreach import aggregate_approved_outreach
from app.services.publication_readiness import REQUIRED_PUBLICATION_DOMAINS

RELEASE_SCHEMA_VERSION = "1.1"
GENERIC_PUBLICATION_DOMAINS = (
    OperationalDomain.TRANSPORT,
    OperationalDomain.ENERGY,
    OperationalDomain.LPG,
    OperationalDomain.WATER,
)


def _json_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _approved_submission(db: Session, period_id: UUID, domain: OperationalDomain) -> Submission | None:
    return db.scalar(
        select(Submission)
        .where(
            Submission.reporting_period_id == period_id,
            Submission.domain == domain,
            Submission.status == SubmissionStatus.APPROVED,
        )
        .order_by(Submission.approved_at.desc().nullslast(), Submission.id)
        .limit(1)
    )


def _public_calculation(item: CalculationResponse) -> dict[str, object]:
    return {
        "status": item.status,
        "reason": item.reason,
        "calculation_code": item.calculation_code,
        "activity_metric_code": item.activity_metric_code,
        "activity_value": _json_number(item.activity_value),
        "activity_unit": item.activity_unit,
        "factor_set_version": item.factor_set_version,
        "factor_code": item.factor_code.value if item.factor_code else None,
        "factor_value": _json_number(item.factor_value),
        "factor_unit": item.factor_unit,
        "result_kgco2e": _json_number(item.result_kgco2e),
        "result_value": _json_number(item.result_value),
        "result_unit": item.result_unit,
        "formula_version": item.formula_version,
    }


def _generic_domain_payload(db: Session, submission: Submission) -> dict[str, object]:
    rows = db.execute(
        select(MetricDefinition, SubmissionValue)
        .outerjoin(
            SubmissionValue,
            and_(
                SubmissionValue.metric_code == MetricDefinition.code,
                SubmissionValue.submission_id == submission.id,
            ),
        )
        .where(
            MetricDefinition.operational_domain == submission.domain,
            MetricDefinition.publication_class == PublicationClass.PUBLIC_AGGREGATE,
        )
        .order_by(MetricDefinition.display_order, MetricDefinition.code)
    ).all()
    metrics: dict[str, object] = {
        definition.code: {
            "value": _json_number(value.value) if value is not None else None,
            "unit": definition.canonical_unit,
        }
        for definition, value in rows
    }
    calculations = [_public_calculation(item) for item in calculation_responses(db, submission)]
    result: dict[str, object] = {"metrics": metrics, "calculations": calculations}
    if submission.domain == OperationalDomain.LPG:
        lpg = next(
            (item for item in calculations if item["calculation_code"] == "lpg_emissions"),
            {"status": "unavailable", "reason": "not_published", "result_value": None, "result_unit": "tCO2e"},
        )
        result["emissions"] = {
            "status": lpg["status"],
            "reason": lpg["reason"],
            "value": lpg["result_value"],
            "unit": lpg["result_unit"],
        }
    return result


def build_release_payload(db: Session, period: ReportingPeriod) -> dict[str, object]:
    approved = {
        domain: _approved_submission(db, period.id, domain)
        for domain in REQUIRED_PUBLICATION_DOMAINS
    }
    payload: dict[str, object] = {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "period": {"id": str(period.id), "year": period.year, "month": period.month},
    }
    for domain in GENERIC_PUBLICATION_DOMAINS:
        submission = approved[domain]
        payload[domain.value] = _generic_domain_payload(db, submission) if submission is not None else None
    outreach_submission = approved[OperationalDomain.OUTREACH]
    payload[OperationalDomain.OUTREACH.value] = (
        aggregate_approved_outreach(db, period.id, submission_id=outreach_submission.id)
        if outreach_submission is not None
        else None
    )
    payload["publication_status"] = {
        domain.value: "approved" if approved[domain] is not None else "missing_approved_submission"
        for domain in REQUIRED_PUBLICATION_DOMAINS
    }
    payload["indicators"] = {
        "total_ghg_tco2e": {
            "status": "unavailable",
            "reason": "methodology_under_review",
            "value": None,
            "unit": "tCO2e",
        },
        "avoided_emissions_tco2e": {
            "status": "unavailable",
            "reason": "methodology_under_review",
            "value": None,
            "unit": "tCO2e",
        },
        "renewable_share_percent": {
            "status": "unavailable",
            "reason": "methodology_under_review",
            "value": None,
            "unit": "%",
        },
    }
    return payload


def empty_public_dashboard(*, year: int | None = None, month: int | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "release": None,
        "schema_version": RELEASE_SCHEMA_VERSION,
        "period": {"year": year, "month": month} if year is not None or month is not None else None,
    }
    payload.update({domain.value: None for domain in REQUIRED_PUBLICATION_DOMAINS})
    payload["publication_status"] = {
        domain.value: "not_published" for domain in REQUIRED_PUBLICATION_DOMAINS
    }
    payload["indicators"] = {
        code: {"status": "unavailable", "reason": "not_published", "value": None, "unit": unit}
        for code, unit in (
            ("total_ghg_tco2e", "tCO2e"),
            ("avoided_emissions_tco2e", "tCO2e"),
            ("renewable_share_percent", "%"),
        )
    }
    return payload


def payload_checksum(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()
