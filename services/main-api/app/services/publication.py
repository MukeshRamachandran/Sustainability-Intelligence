from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.enums import OperationalDomain, PublicationClass, SubmissionStatus
from app.models.sustainability import (
    InstitutionalPopulationReference,
    MetricDefinition,
    ReportingPeriod,
    Submission,
    SubmissionValue,
)
from app.schemas.emission_factors import CalculationResponse
from app.services import sustainability_formulas as formulas
from app.services import waste as waste_service
from app.services.emission_factors import calculation_responses
from app.services.outreach import aggregate_approved_outreach
from app.services.publication_readiness import REQUIRED_PUBLICATION_DOMAINS

# Older frozen payloads remain immutable and retain their stored schema version.
# 1.5: LPG activity is lpg_weight_kg (kg) x LPG_KG (kgCO2e/kg); the litre metric
# is never published (0013_lpg_kg_governance_v2).
RELEASE_SCHEMA_VERSION = "1.5"
# Schemas whose derived energy/water indicators must be complete to publish.
DERIVED_INDICATOR_SCHEMA_VERSIONS = frozenset({"1.4", "1.5"})
LPG_ACTIVITY_METRIC = "lpg_weight_kg"
LPG_ACTIVITY_UNIT = "kg"
LPG_FACTOR_UNIT = "kgCO2e/kg"
LEGACY_LPG_METRIC = "lpg_consumption_litres"
# LEGACY - kept only so frozen release payloads and older clients stay readable.
# It is NOT the waste-diversion methodology: waste diverted from landfill is the
# dry waste generated (sustainability_formulas.waste_diverted_from_landfill_kg).
# Never derive a quantity from this percentage or apply it to another year.
LANDFILL_DIVERSION_STATIC_REFERENCE_PCT = Decimal("88.1")
GENERIC_PUBLICATION_DOMAINS = (
    OperationalDomain.TRANSPORT,
    OperationalDomain.ENERGY,
    OperationalDomain.LPG,
    OperationalDomain.WATER,
    OperationalDomain.WASTE,
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
        # Only present for a derived activity (kWh-based DG): source kWh, the
        # governed SFC and the derived litres. Absent for every other result,
        # so litre-based calculations keep their exact shape.
        **({"derivation": item.derivation} if item.derivation else {}),
    }


def _waste_payload(db: Session, submission: Submission) -> dict[str, object]:
    """Freeze the waste inventory. Category totals are summed here, in the
    backend, so the browser is never the authoritative aggregator."""
    item = waste_service.summary(db, submission)
    return {
        "categories": [
            {
                "code": category.code,
                "display_name": category.display_name,
                "quantity_kg": _json_number(category.quantity_kg),
            }
            for category in sorted(item.categories, key=lambda entry: entry.code)
        ],
        "materials": [
            {
                "code": material.material_code,
                "display_name": material.material_display_name,
                "category_code": material.category_code,
                "category_display_name": material.category_display_name,
                "quantity_kg": _json_number(material.quantity_kg),
            }
            for material in item.items
        ],
    }


def waste_payload_blockers(payload: dict[str, object]) -> list[dict[str, str]]:
    """Refuse to freeze a waste payload whose parts disagree.

    sum(materials) must equal dry, and wet + dry must equal total. A mismatch
    means the derived metrics and the item rows have diverged, so the release
    is stopped rather than published with conflicting numbers.
    """
    waste = payload.get(OperationalDomain.WASTE.value)
    if not isinstance(waste, dict):
        return []
    metrics = waste.get("metrics")
    if not isinstance(metrics, dict):
        return [{"domain": "waste", "status": "invalid", "reason": "waste_metrics_missing"}]

    def metric(code: str) -> Decimal | None:
        entry = metrics.get(code)
        value = entry.get("value") if isinstance(entry, dict) else None
        return None if value is None else Decimal(str(value))

    wet = metric("wet_waste_generated_kg")
    dry = metric("dry_waste_generated_kg")
    total = metric("total_waste_generated_kg")
    if wet is None or dry is None or total is None:
        return [{"domain": "waste", "status": "invalid", "reason": "waste_metrics_incomplete"}]
    materials = waste.get("materials")
    material_sum = sum(
        (Decimal(str(row.get("quantity_kg") or 0)) for row in materials if isinstance(row, dict)),
        Decimal("0"),
    ) if isinstance(materials, list) else Decimal("0")
    blockers: list[dict[str, str]] = []
    if material_sum != dry:
        blockers.append({
            "domain": "waste", "status": "inconsistent",
            "reason": f"material_sum_{material_sum}_does_not_equal_dry_{dry}",
        })
    if wet + dry != total:
        blockers.append({
            "domain": "waste", "status": "inconsistent",
            "reason": f"wet_plus_dry_does_not_equal_total_{total}",
        })
    return blockers


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
    if submission.domain == OperationalDomain.WASTE:
        result.update(_waste_payload(db, submission))
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


def _decimal_metric(domain_payload: object, code: str) -> Decimal | None:
    if not isinstance(domain_payload, dict):
        return None
    metrics = domain_payload.get("metrics")
    entry = metrics.get(code) if isinstance(metrics, dict) else None
    value = entry.get("value") if isinstance(entry, dict) else None
    return None if value is None else Decimal(str(value))


def _nonnegative_metric(domain_payload: object, code: str) -> Decimal | None:
    value = _decimal_metric(domain_payload, code)
    return value if value is not None and value.is_finite() and value >= 0 else None


def _decimal_calculation(domain_payload: object, code: str) -> Decimal | None:
    if not isinstance(domain_payload, dict):
        return None
    calculations = domain_payload.get("calculations")
    if not isinstance(calculations, list):
        return None
    for item in calculations:
        if not isinstance(item, dict) or item.get("calculation_code") != code:
            continue
        value = item.get("result_value")
        if item.get("status") != "available" or value is None:
            return None
        return Decimal(str(value))
    return None


def _indicator(value: Decimal | None, unit: str, reason: str, *, places: int = 6) -> dict[str, object]:
    if value is None:
        return {"status": "unavailable", "reason": reason, "value": None, "unit": unit}
    rounded = value.quantize(Decimal(1).scaleb(-places))
    return {"status": "available", "reason": None, "value": _json_number(rounded), "unit": unit}


def _schema_1_3_indicators(
    db: Session, period: ReportingPeriod, payload: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    transport = payload.get("transport")
    lpg = payload.get("lpg")
    energy = payload.get("energy")
    waste = payload.get("waste")

    scope1_parts = [
        _decimal_calculation(transport, "transport_petrol_emissions"),
        _decimal_calculation(transport, "transport_diesel_emissions"),
        _decimal_calculation(transport, "dg_diesel_emissions"),
        _decimal_calculation(lpg, "lpg_emissions"),
    ]
    scope1 = formulas.scope1_tco2e(*scope1_parts)
    scope2 = _decimal_calculation(energy, "grid_electricity_emissions")
    operational = formulas.operational_ghg_tco2e(scope1, scope2)

    reference = db.get(InstitutionalPopulationReference, period.year)
    population_is_usable = reference is not None and reference.population > 0
    population = reference.population if population_is_usable and reference is not None else None
    population_payload: dict[str, object] = {
        "status": "available" if population is not None else "unavailable",
        "reason": None if population is not None else (
            "population_is_zero" if reference is not None else "population_not_configured"
        ),
        "value": population,
        "unit": reference.unit if reference is not None else "people",
        "effective_year": period.year,
        "source_reference": reference.source_reference if reference is not None else None,
    }

    waste_total = _decimal_metric(waste, "total_waste_generated_kg")
    per_capita_ghg = formulas.operational_ghg_per_capita_kgco2e(operational, population)
    waste_per_capita = formulas.waste_per_capita_kg(waste_total, population)
    indicators: dict[str, object] = {
        "scope1_tco2e": _indicator(scope1, "tCO2e", "required_scope1_component_unavailable"),
        "scope2_tco2e": _indicator(scope2, "tCO2e", "grid_electricity_unavailable"),
        "operational_ghg_tco2e": _indicator(
            operational,
            "tCO2e",
            "scope1_or_scope2_unavailable",
        ),
        "operational_ghg_per_capita_kgco2e": _indicator(
            per_capita_ghg,
            "kgCO2e/person",
            "operational_ghg_or_population_unavailable",
        ),
        "waste_per_capita_kg": _indicator(
            waste_per_capita,
            "kg/person",
            "waste_or_population_unavailable",
        ),
        # Owner-approved methodology: diverted from landfill = dry waste.
        "waste_diverted_from_landfill_kg": _indicator(
            formulas.waste_diverted_from_landfill_kg(_decimal_metric(waste, "dry_waste_generated_kg")),
            "kg",
            "dry_waste_unavailable",
        ),
        # Retain the legacy broad-total key honestly; Operational GHG is the
        # explicitly bounded Scope 1 + Scope 2 indicator, not an all-scope total.
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
    return indicators, population_payload


DERIVED_INDICATOR_UNITS = {
    "renewable_electricity_kwh": "kWh",
    "total_electricity_consumption_kwh": "kWh",
    "renewable_share_pct": "%",
    "estimated_avoided_grid_emissions_tco2e": "tCO2e",
    "water_per_capita_l": "L/person",
}


def _grid_factor_provenance(energy: object) -> tuple[Decimal | None, dict[str, object]]:
    if not isinstance(energy, dict) or not isinstance(energy.get("calculations"), list):
        return None, {}
    for row in energy["calculations"]:
        if not isinstance(row, dict) or row.get("calculation_code") != "grid_electricity_emissions":
            continue
        if (
            row.get("status") != "available"
            or row.get("factor_code") != "GRID_ELECTRICITY"
            or row.get("factor_unit") != "kgCO2e/kWh"
            or row.get("factor_value") is None
            or not row.get("factor_set_version")
        ):
            return None, {}
        factor = Decimal(str(row["factor_value"]))
        if not factor.is_finite() or factor <= 0:
            return None, {}
        return factor, {
            "source_calculation_code": "grid_electricity_emissions",
            "factor_code": row["factor_code"],
            "factor_value": row["factor_value"],
            "factor_unit": row["factor_unit"],
            "factor_set_version": row["factor_set_version"],
            "formula_version": row.get("formula_version"),
        }
    return None, {}


def _schema_1_4_indicators(payload: dict[str, object]) -> dict[str, object]:
    energy = payload.get("energy")
    water = payload.get("water")
    population_block = payload.get("population")
    population_value = population_block.get("value") if isinstance(population_block, dict) else None
    population = Decimal(str(population_value)) if population_value is not None else None
    on_campus = _nonnegative_metric(energy, "renewable_on_campus_kwh")
    procured = _nonnegative_metric(energy, "renewable_procured_kwh")
    grid = _nonnegative_metric(energy, "grid_total_kwh")
    water_kl = _nonnegative_metric(water, "water_consumed_kl")
    renewable = formulas.renewable_electricity_kwh(on_campus, procured)
    total = formulas.total_electricity_consumption_kwh(grid, renewable)
    factor, provenance = _grid_factor_provenance(energy)
    share = formulas.renewable_share_pct(renewable, total)
    avoided = formulas.estimated_avoided_grid_emissions_tco2e(renewable, factor)
    per_capita = formulas.water_per_capita_l(water_kl, population)
    avoided_indicator = _indicator(avoided, "tCO2e", "renewable_or_governed_grid_factor_missing", places=12)
    if avoided is not None:
        avoided_indicator["provenance"] = provenance
    indicators: dict[str, object] = {
        "renewable_electricity_kwh": _indicator(renewable, "kWh", "renewable_electricity_source_missing"),
        "total_electricity_consumption_kwh": _indicator(total, "kWh", "electricity_source_missing"),
        "renewable_share_pct": _indicator(share, "%", "electricity_total_missing_or_zero", places=12),
        "estimated_avoided_grid_emissions_tco2e": avoided_indicator,
        "water_per_capita_l": _indicator(per_capita, "L/person", "water_or_population_missing_or_zero", places=12),
        # Legacy 1.3 keys are kept for compatibility but must not contradict
        # the governed 1.4 indicators that replace them.
        "avoided_emissions_tco2e": {
            "status": "unavailable",
            "reason": "superseded_by_estimated_avoided_grid_emissions_tco2e",
            "value": None,
            "unit": "tCO2e",
        },
        "renewable_share_percent": {
            "status": "unavailable",
            "reason": "superseded_by_renewable_share_pct",
            "value": None,
            "unit": "%",
        },
    }
    return indicators


ELECTRICITY_INDICATOR_CODES = (
    "renewable_electricity_kwh",
    "total_electricity_consumption_kwh",
    "renewable_share_pct",
    "estimated_avoided_grid_emissions_tco2e",
)
SOLAR_THERMAL_METRIC = "solar_water_heater_kwh"


def electricity_indicators(db: Session, submission: Submission) -> dict[str, object]:
    """Electrical indicators of one Energy submission, for the Manager and Admin.

    The same calculation a release freezes (``_schema_1_4_indicators``):
    renewable electricity = on-campus + procured, total electricity = grid
    total + renewable electricity, share and avoided grid emissions from those.
    The solar water heater is thermal: it is returned separately and is never
    an input here. Nothing is stored; the values are derived from the
    submission's source values each time.
    """
    energy = _generic_domain_payload(db, submission)
    indicators = _schema_1_4_indicators({OperationalDomain.ENERGY.value: energy})
    return {
        **{code: indicators[code] for code in ELECTRICITY_INDICATOR_CODES},
        "solar_thermal": {
            "metric_code": SOLAR_THERMAL_METRIC,
            "value": _json_number(_decimal_metric(energy, SOLAR_THERMAL_METRIC)),
            "unit": "kWh",
            "included_in_electricity": False,
        },
    }


def derived_payload_blockers(payload: dict[str, object]) -> list[dict[str, str]]:
    """Block newly prepared governed releases with incomplete derived sources."""
    if payload.get("schema_version") not in DERIVED_INDICATOR_SCHEMA_VERSIONS:
        return []
    indicators = payload.get("indicators")
    if not isinstance(indicators, dict):
        return [{"domain": "release", "status": "invalid", "reason": "indicators_missing"}]
    blockers = []
    for code in DERIVED_INDICATOR_UNITS:
        entry = indicators.get(code)
        if not isinstance(entry, dict) or entry.get("status") != "available":
            reason = entry.get("reason", "indicator_missing") if isinstance(entry, dict) else "indicator_missing"
            domain = "water" if code == "water_per_capita_l" else "energy"
            blockers.append({"domain": domain, "status": "invalid", "reason": f"{code}:{reason}"})
    return blockers


def lpg_payload_blockers(payload: dict[str, object]) -> list[dict[str, str]]:
    """Refuse to prepare or publish a release whose LPG block is not kg-based.

    Applied at prepare and at publish, so a litre-era candidate (or a period
    whose LPG submission was frozen against the litre factor) cannot become a
    new public release. Already-published releases are never re-validated.
    """
    lpg = payload.get(OperationalDomain.LPG.value)
    if not isinstance(lpg, dict):
        return []
    blockers: list[dict[str, str]] = []
    metrics = lpg.get("metrics")
    if isinstance(metrics, dict) and LEGACY_LPG_METRIC in metrics:
        blockers.append({"domain": "lpg", "status": "invalid", "reason": "lpg_litre_metric_superseded_by_kg"})
    calculations = lpg.get("calculations")
    for item in calculations if isinstance(calculations, list) else []:
        if not isinstance(item, dict) or item.get("calculation_code") != "lpg_emissions":
            continue
        if item.get("activity_metric_code") != LPG_ACTIVITY_METRIC or item.get("activity_unit") not in (
            LPG_ACTIVITY_UNIT,
            None,
        ):
            blockers.append({"domain": "lpg", "status": "invalid", "reason": "lpg_activity_is_not_governed_kg"})
        elif item.get("status") == "available" and item.get("factor_unit") != LPG_FACTOR_UNIT:
            blockers.append({"domain": "lpg", "status": "invalid", "reason": "lpg_factor_is_not_governed_kg"})
    return blockers


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
    indicators, population = _schema_1_3_indicators(db, period, payload)
    payload["indicators"] = indicators
    payload["population"] = population
    indicators.update(_schema_1_4_indicators(payload))
    payload["static_references"] = {
        "landfill_diversion_pct": {
            "value": _json_number(LANDFILL_DIVERSION_STATIC_REFERENCE_PCT),
            "unit": "%",
            "kind": "static_institutional_reference",
            "source_reference": "Legacy institutional dashboard reference; not derived from monthly waste",
        }
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
            ("scope1_tco2e", "tCO2e"),
            ("scope2_tco2e", "tCO2e"),
            ("operational_ghg_tco2e", "tCO2e"),
            ("operational_ghg_per_capita_kgco2e", "kgCO2e/person"),
            ("waste_per_capita_kg", "kg/person"),
            ("total_ghg_tco2e", "tCO2e"),
            ("avoided_emissions_tco2e", "tCO2e"),
            ("renewable_share_percent", "%"),
            *DERIVED_INDICATOR_UNITS.items(),
        )
    }
    payload["population"] = {
        "status": "unavailable",
        "reason": "not_published",
        "value": None,
        "unit": "people",
        "effective_year": year,
        "source_reference": None,
    }
    payload["static_references"] = None
    return payload


def payload_checksum(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()
