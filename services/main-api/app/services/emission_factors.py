from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import FactorCode, FactorSetStatus, SubmissionStatus
from app.models.identity import User
from app.models.sustainability import (
    CalculationResult,
    EmissionFactor,
    EmissionFactorSet,
    MetricDefinition,
    ReportingPeriod,
    Submission,
    SubmissionValue,
)
from app.schemas.emission_factors import (
    CalculationResponse,
    FactorResponse,
    FactorSetResponse,
    FactorSetWrite,
)
from app.services import dg_methodology as dg
from app.services import sustainability_formulas as formulas

CORE_FACTORS = {FactorCode.PETROL, FactorCode.DIESEL, FactorCode.GRID_ELECTRICITY}
EXPECTED_UNITS = {
    FactorCode.PETROL: "L",
    FactorCode.DIESEL: "L",
    FactorCode.GRID_ELECTRICITY: "kWh",
    # Legacy: only a retired set can still hold it (writes reject the code).
    FactorCode.LPG: "L",
    FactorCode.LPG_KG: "kg",
}
# The governed activity metric for each calculation. LPG is weight-based
# (0013_lpg_kg_governance_v2): lpg_weight_kg x LPG_KG. The deprecated
# litre metric is not an activity and must never appear here.
CALCULATION_CODES = {
    "transport_petrol_litres": "transport_petrol_emissions",
    "transport_diesel_litres": "transport_diesel_emissions",
    "dg_diesel_litres": "dg_diesel_emissions",
    "grid_total_kwh": "grid_electricity_emissions",
    "lpg_weight_kg": "lpg_emissions",
}
FORMULA_VERSION = "activity_x_factor_kgco2e_v1"
# DG from the governed SFC's effective date: generation (kWh) x SFC -> derived
# litres x DIESEL factor (0015_dg_kwh_methodology).
DG_KWH_FORMULA_VERSION = "dg_kwh_x_sfc_x_factor_kgco2e_v1"
EDITABLE_STATUSES = {SubmissionStatus.DRAFT, SubmissionStatus.CORRECTION_REQUESTED}


def _factors(db: Session, set_id: UUID) -> list[EmissionFactor]:
    return list(
        db.scalars(
            select(EmissionFactor)
            .where(EmissionFactor.factor_set_id == set_id)
            .order_by(EmissionFactor.code)
        ).all()
    )


def serialize_factor_set(db: Session, item: EmissionFactorSet) -> FactorSetResponse:
    created = db.get(User, item.created_by) if item.created_by else None
    activated = db.get(User, item.activated_by) if item.activated_by else None
    return FactorSetResponse(
        id=item.id,
        version=item.version,
        status=item.status,
        effective_from=item.effective_from,
        source_note=item.source_note,
        created_by=item.created_by,
        created_by_name=created.display_name if created else None,
        activated_by=item.activated_by,
        activated_by_name=activated.display_name if activated else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
        activated_at=item.activated_at,
        row_version=item.row_version,
        factors=[
            FactorResponse(
                id=factor.id,
                code=FactorCode(factor.code),
                factor_value=factor.factor_value,
                activity_unit=factor.activity_unit,
                result_unit=factor.result_unit,
                source_reference=factor.source_reference,
                source_url=factor.source_url,
                notes=factor.notes,
            )
            for factor in _factors(db, item.id)
        ],
    )


def replace_factors(db: Session, item: EmissionFactorSet, payload: FactorSetWrite) -> None:
    db.execute(delete(EmissionFactor).where(EmissionFactor.factor_set_id == item.id))
    for factor in payload.factors:
        db.add(
            EmissionFactor(
                factor_set_id=item.id,
                code=factor.code.value,
                factor_value=factor.factor_value,
                activity_unit=factor.activity_unit,
                result_unit=factor.result_unit,
                source_reference=factor.source_reference or None,
                source_url=str(factor.source_url) if factor.source_url else None,
                notes=factor.notes or None,
            )
        )


def validate_activation(db: Session, item: EmissionFactorSet) -> None:
    if item.effective_from is None:
        raise HTTPException(status_code=422, detail="Effective date is required before activation.")
    factors = _factors(db, item.id)
    by_code = {FactorCode(factor.code): factor for factor in factors}
    missing = sorted(code.value for code in CORE_FACTORS - set(by_code))
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Core factors are missing.", "factors": missing})
    for code, factor in by_code.items():
        if factor.factor_value < 0 or not factor.factor_value.is_finite():
            raise HTTPException(status_code=422, detail=f"{code.value} has an invalid value.")
        if factor.activity_unit != EXPECTED_UNITS[code] or factor.result_unit != "kgCO2e":
            raise HTTPException(status_code=422, detail=f"{code.value} has an incompatible unit.")
        if not factor.source_reference or not factor.source_reference.strip():
            raise HTTPException(status_code=422, detail=f"{code.value} requires a source reference.")
    conflicting = db.scalar(
        select(EmissionFactorSet.id).where(
            EmissionFactorSet.id != item.id,
            EmissionFactorSet.status == FactorSetStatus.ACTIVE,
            EmissionFactorSet.effective_from == item.effective_from,
        )
    )
    if conflicting is not None:
        raise HTTPException(status_code=409, detail="An active factor set already has this effective date.")


def applicable_factor_set(db: Session, period: ReportingPeriod) -> EmissionFactorSet | None:
    return db.scalar(
        select(EmissionFactorSet)
        .where(
            EmissionFactorSet.status == FactorSetStatus.ACTIVE,
            EmissionFactorSet.effective_from.is_not(None),
            EmissionFactorSet.effective_from <= period.period_start,
        )
        .order_by(EmissionFactorSet.effective_from.desc(), EmissionFactorSet.id)
        .limit(1)
    )


def _unavailable(
    submission: Submission, reason: str, dg_metric: str = dg.DG_LITRES_METRIC
) -> list[CalculationResponse]:
    if submission.domain.value == "transport":
        codes = [
            (dg_metric if calculation == dg.DG_EMISSIONS else metric, calculation)
            for metric, calculation in list(CALCULATION_CODES.items())[:3]
        ]
    elif submission.domain.value == "energy":
        codes = [("grid_total_kwh", CALCULATION_CODES["grid_total_kwh"])]
    elif submission.domain.value == "lpg":
        codes = [("lpg_weight_kg", CALCULATION_CODES["lpg_weight_kg"])]
    else:
        return []
    return [
        CalculationResponse(
            status="unavailable", reason=reason, calculation_code=calculation_code,
            activity_metric_code=metric_code, formula_version=FORMULA_VERSION,
        )
        for metric_code, calculation_code in codes
    ]


def _unavailable_with_activity(
    db: Session, submission: Submission, reason: str
) -> list[CalculationResponse]:
    values = {
        row.metric_code: row
        for row in db.scalars(
            select(SubmissionValue).where(SubmissionValue.submission_id == submission.id)
        ).all()
    }
    period = db.get(ReportingPeriod, submission.reporting_period_id)
    dg_metric = (
        dg.DG_GENERATION_METRIC
        if dg.DG_GENERATION_METRIC in values
        or (
            dg.DG_LITRES_METRIC not in values
            and period is not None
            and dg.manager_source_metric(db, period.period_start) == dg.DG_GENERATION_METRIC
        )
        else dg.DG_LITRES_METRIC
    )
    return [
        item.model_copy(
            update={
                "activity_value": values[item.activity_metric_code].value,
                "activity_unit": values[item.activity_metric_code].canonical_unit,
            }
        )
        if item.activity_metric_code in values
        else item
        for item in _unavailable(submission, reason, dg_metric)
    ]


def _dg_generation_result(
    db: Session,
    period: ReportingPeriod,
    generation: SubmissionValue,
    factor_set: EmissionFactorSet,
    factors: dict[str, EmissionFactor],
) -> CalculationResponse:
    """DG emission from generation (kWh): governed SFC -> derived litres -> governed DIESEL factor.

    The Manager supplies only the kWh. Litres and emissions are derived here,
    and the derivation (source kWh, SFC, derived litres) is returned so it can
    be shown read-only and frozen with the result.
    """

    def unavailable(reason: str) -> CalculationResponse:
        return CalculationResponse(
            status="unavailable", reason=reason, calculation_code=dg.DG_EMISSIONS,
            activity_metric_code=dg.DG_GENERATION_METRIC, activity_value=generation.value,
            activity_unit=generation.canonical_unit, formula_version=DG_KWH_FORMULA_VERSION, provisional=True,
        )

    if generation.canonical_unit != dg.GENERATION_UNIT:
        return unavailable("incompatible_unit")
    derivation = dg.derive_litres(db, generation.value, period.period_start)
    if derivation is None:
        return unavailable("dg_sfc_not_effective")
    factor = factors.get(dg.DG_FACTOR)
    if factor is None:
        return unavailable("factor_not_configured")
    if factor.activity_unit != dg.LITRES_UNIT:
        return unavailable("incompatible_unit")
    kgco2e = formulas.activity_emissions_kgco2e(derivation.litres, factor.factor_value)
    tonnes_co2e = formulas.activity_emissions_tco2e(derivation.litres, factor.factor_value)
    if kgco2e is None or tonnes_co2e is None:
        return unavailable("not_calculable")
    return CalculationResponse(
        status="available", calculation_code=dg.DG_EMISSIONS,
        activity_metric_code=dg.DG_GENERATION_METRIC, activity_value=generation.value,
        activity_unit=generation.canonical_unit, factor_set_id=factor_set.id,
        factor_set_version=factor_set.version, factor_code=FactorCode(factor.code),
        factor_value=factor.factor_value, factor_unit=f"{factor.result_unit}/{factor.activity_unit}",
        result_kgco2e=kgco2e.quantize(Decimal("0.000001")), result_value=tonnes_co2e, result_unit="tCO2e",
        formula_version=DG_KWH_FORMULA_VERSION, provisional=True, derivation=derivation.as_json(),
    )


def calculate_provisional(db: Session, submission: Submission) -> list[CalculationResponse]:
    period = db.get(ReportingPeriod, submission.reporting_period_id)
    if period is None:
        raise HTTPException(status_code=500, detail="Submission reporting period is missing.")
    factor_set = applicable_factor_set(db, period)
    if factor_set is None:
        reason = "factor_not_configured" if submission.domain.value == "lpg" else "no_applicable_factor"
        return _unavailable_with_activity(db, submission, reason)
    factors = {factor.code: factor for factor in _factors(db, factor_set.id)}
    rows = db.execute(
        select(SubmissionValue, MetricDefinition)
        .join(MetricDefinition, MetricDefinition.code == SubmissionValue.metric_code)
        .where(
            SubmissionValue.submission_id == submission.id,
            MetricDefinition.factor_code.is_not(None),
        )
    ).all()
    # A kWh DG source is authoritative for its period: any litre value beside
    # it is not used, so DG is never counted through both pathways.
    generation = db.scalar(
        select(SubmissionValue).where(
            SubmissionValue.submission_id == submission.id,
            SubmissionValue.metric_code == dg.DG_GENERATION_METRIC,
            SubmissionValue.value.is_not(None),
        )
    )
    results: list[CalculationResponse] = []
    for value, definition in rows:
        calculation_code = CALCULATION_CODES.get(definition.code)
        if not calculation_code or value.value is None:
            continue
        if generation is not None and definition.code == dg.DG_LITRES_METRIC:
            continue
        factor = factors.get(definition.factor_code or "")
        if factor is None:
            results.append(CalculationResponse(
                status="unavailable", reason="factor_not_configured", calculation_code=calculation_code,
                activity_metric_code=definition.code, activity_value=value.value,
                activity_unit=value.canonical_unit, formula_version=FORMULA_VERSION, provisional=True,
            ))
            continue
        if value.canonical_unit != factor.activity_unit:
            results.append(CalculationResponse(
                status="unavailable", reason="incompatible_unit", calculation_code=calculation_code,
                activity_metric_code=definition.code, activity_value=value.value,
                activity_unit=value.canonical_unit, formula_version=FORMULA_VERSION, provisional=True,
            ))
            continue
        kgco2e = formulas.activity_emissions_kgco2e(value.value, factor.factor_value)
        tonnes_co2e = formulas.activity_emissions_tco2e(value.value, factor.factor_value)
        if kgco2e is None or tonnes_co2e is None:
            continue
        results.append(CalculationResponse(
            status="available", calculation_code=calculation_code,
            activity_metric_code=definition.code, activity_value=value.value,
            activity_unit=value.canonical_unit, factor_set_id=factor_set.id,
            factor_set_version=factor_set.version, factor_code=FactorCode(factor.code),
            factor_value=factor.factor_value,
            factor_unit=f"{factor.result_unit}/{factor.activity_unit}",
            result_kgco2e=kgco2e.quantize(Decimal("0.000001")),
            result_value=tonnes_co2e,
            result_unit="tCO2e", formula_version=FORMULA_VERSION,
            provisional=True,
        ))
    if generation is not None:
        results.append(_dg_generation_result(db, period, generation, factor_set, factors))
    return results or _unavailable_with_activity(db, submission, "activity_not_submitted")


def freeze_calculations(db: Session, submission: Submission) -> None:
    for result in calculate_provisional(db, submission):
        db.add(CalculationResult(
            submission_id=submission.id,
            submission_revision=submission.revision_number,
            calculation_code=result.calculation_code,
            calculation_status=result.status,
            unavailable_reason=result.reason,
            metric_code=result.activity_metric_code,
            activity_value=result.activity_value,
            activity_unit=result.activity_unit,
            factor_id=(
                _factor_id(db, result.factor_set_id, result.factor_code)
                if result.status == "available"
                else None
            ),
            factor_set_id=result.factor_set_id,
            factor_set_version=result.factor_set_version,
            factor_code=result.factor_code.value if result.factor_code else None,
            factor_value=result.factor_value,
            factor_unit=result.factor_unit,
            result_kgco2e=result.result_kgco2e,
            result_value=result.result_value,
            result_unit=result.result_unit,
            formula_version=result.formula_version or FORMULA_VERSION,
            derivation=result.derivation,
        ))
    db.flush()


def _factor_id(db: Session, set_id: UUID | None, code: FactorCode | None) -> UUID:
    factor_id = db.scalar(select(EmissionFactor.id).where(
        EmissionFactor.factor_set_id == set_id, EmissionFactor.code == (code.value if code else "")
    ))
    if factor_id is None:
        raise HTTPException(status_code=500, detail="Calculation factor is missing.")
    return factor_id


def calculation_responses(db: Session, submission: Submission) -> list[CalculationResponse]:
    if submission.status in EDITABLE_STATUSES:
        return calculate_provisional(db, submission)
    rows = db.scalars(select(CalculationResult).where(
        CalculationResult.submission_id == submission.id,
        CalculationResult.submission_revision == submission.revision_number,
    ).order_by(CalculationResult.calculation_code)).all()
    if not rows:
        return _unavailable(submission, "legacy_not_snapshotted")
    return [CalculationResponse(
        status=row.calculation_status, reason=row.unavailable_reason,
        calculation_code=row.calculation_code,
        activity_metric_code=row.metric_code, activity_value=row.activity_value,
        activity_unit=row.activity_unit, factor_set_id=row.factor_set_id,
        factor_set_version=row.factor_set_version,
        factor_code=FactorCode(row.factor_code) if row.factor_code else None,
        factor_value=row.factor_value, factor_unit=row.factor_unit,
        result_kgco2e=row.result_kgco2e, result_value=row.result_value,
        result_unit=row.result_unit, formula_version=row.formula_version, provisional=False,
        derivation=row.derivation,
    ) for row in rows]


def flush_governance(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Factor version or effective date conflicts with existing data."
        ) from exc
