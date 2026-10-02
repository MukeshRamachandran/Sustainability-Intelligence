"""Reproducible calculations over verified, authoritative historical values.

Every formula comes from app.services.sustainability_formulas - the same
functions release preparation uses. Emission factors come from the governed
factor sets applicable to each period (never a "current" factor). Each stored
result records its inputs, factor, factor-set version and population source.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import FactorSetStatus
from app.models.history import HistoricalCalculationResult, HistoricalMetricValue, HistoricalPeriod
from app.models.sustainability import EmissionFactor, EmissionFactorSet, InstitutionalPopulationReference
from app.services import dg_methodology as dg
from app.services import sustainability_formulas as formulas

METHODOLOGY_VERSION = "kcosmos-schema-1.4-formulas-v1"
FULL_PRECISION = Decimal("0.000000000001")

# (calculation_code, activity metric, factor code). LPG is weight-based
# (0013_lpg_kg_governance_v2); the deprecated litre metric is never an input.
ACTIVITY_EMISSIONS = (
    ("transport_petrol_emissions", "transport_petrol_litres", "PETROL"),
    ("transport_diesel_emissions", "transport_diesel_litres", "DIESEL"),
    ("dg_diesel_emissions", "dg_diesel_litres", "DIESEL"),
    ("lpg_emissions", "lpg_weight_kg", "LPG_KG"),
)
DOMAIN_OF_INPUT = {
    "transport_petrol_litres": "transport",
    "transport_diesel_litres": "transport",
    "dg_diesel_litres": "transport",
    "lpg_weight_kg": "lpg",
}
# DG has two legitimate activity pathways (0015_dg_kwh_methodology): legacy
# source-reported litres, and - once the governed SFC is in force - generation
# (kWh) from which litres are derived. Only the kWh pathway carries this
# methodology version; legacy litre results are untouched.
DG_KWH_METHODOLOGY_VERSION = "kcosmos-schema-1.4-formulas-v3-dg-kwh"

# Owner-approved available-data methodology: a GHG total is the sum of the
# verified contributors that exist. A missing contributor is excluded (never
# zero) and the result is labelled PARTIAL with what contributed and what did
# not. Only these results carry the newer methodology version.
AVAILABLE_DATA_METHODOLOGY_VERSION = "kcosmos-schema-1.4-formulas-v2-available-data"
GRID_EMISSIONS = "grid_electricity_emissions"
SCOPE1_CONTRIBUTORS = tuple(code for code, _, _ in ACTIVITY_EMISSIONS)
GRID_METERS = ("grid_ht_kwh", "grid_commercial_kwh", "grid_temporary_kwh")
# Scope 1 / Scope 2 / Operational totals -> the emission contributors they sum.
GHG_TOTAL_CONTRIBUTORS = {
    "scope1_tco2e": SCOPE1_CONTRIBUTORS,
    "scope2_tco2e": (GRID_EMISSIONS,),
    "operational_ghg_tco2e": (*SCOPE1_CONTRIBUTORS, GRID_EMISSIONS),
}
PER_CAPITA_GHG = "operational_ghg_per_capita_kgco2e"
AVAILABLE_DATA_CODES = frozenset({GRID_EMISSIONS, PER_CAPITA_GHG, *GHG_TOTAL_CONTRIBUTORS})
CONTRIBUTOR_LABELS = {
    "transport_petrol_emissions": "Petrol",
    "transport_diesel_emissions": "Fleet Diesel",
    "dg_diesel_emissions": "DG Diesel",
    "lpg_emissions": "LPG",
    GRID_EMISSIONS: "Grid electricity",
    "grid_ht_kwh": "Grid HT meter",
    "grid_commercial_kwh": "Grid Commercial meter",
    "grid_temporary_kwh": "Grid Temporary meter",
}
COMPLETE, PARTIAL, UNAVAILABLE = "COMPLETE", "PARTIAL", "UNAVAILABLE"


def methodology_for(code: str, detail: dict[str, Any] | None = None) -> str:
    if (detail or {}).get("derivation") and code not in AVAILABLE_DATA_CODES:
        return DG_KWH_METHODOLOGY_VERSION
    return AVAILABLE_DATA_METHODOLOGY_VERSION if code in AVAILABLE_DATA_CODES else METHODOLOGY_VERSION


def _named(code: str) -> dict[str, Any]:
    return {"code": code, "label": CONTRIBUTOR_LABELS.get(code, code)}


def completeness(
    parts: dict[str, Decimal | None],
    unit: str,
    *,
    part_status: dict[str, str] | None = None,
    also_missing: tuple[str, ...] = (),
) -> dict[str, Any]:
    """COMPLETE / PARTIAL / UNAVAILABLE plus what contributed and what is missing.

    ``parts`` maps every expected contributor to its value; ``None`` is missing
    (excluded, never zero) and an explicit zero is a contributor. A contributor
    that is itself partial (``part_status``) makes the result PARTIAL, and
    ``also_missing`` names what that contributor lacks.
    """
    statuses = part_status or {}
    contributors = [
        {**_named(code), "value": canonical(value), "unit": unit, "status": statuses.get(code, COMPLETE)}
        for code, value in parts.items()
        if value is not None
    ]
    missing = [_named(code) for code, value in parts.items() if value is None]
    missing += [_named(code) for code in also_missing]
    if not contributors:
        status = UNAVAILABLE
    elif missing or any(item["status"] != COMPLETE for item in contributors):
        status = PARTIAL
    else:
        status = COMPLETE
    return {"status": status, "contributors": contributors, "missing_contributors": missing}


def ghg_completeness(
    emissions: dict[str, Decimal | None],
    grid_meters: dict[str, Decimal | None] | None,
) -> dict[str, dict[str, Any]]:
    """Completeness of grid emissions, Scope 1, Scope 2 and Operational GHG.

    ``emissions`` holds the four Scope 1 results and the grid result (``None``
    = missing). ``grid_meters`` holds the meter readings behind the grid
    result; ``None`` means the meters are not itemised and an available grid
    result is complete (a published release, prepared under the strict rule).
    """
    grid = emissions.get(GRID_EMISSIONS)
    if grid is None:
        grid_meta = completeness(dict.fromkeys(GRID_METERS), "kWh")
    elif grid_meters is None:
        # Complete, but the meter split behind it is not itemised.
        grid_meta = {"status": COMPLETE, "contributors": [], "missing_contributors": []}
    else:
        grid_meta = completeness(grid_meters, "kWh")
    grid_status = {GRID_EMISSIONS: grid_meta["status"]} if grid is not None else {}
    meters_missing = tuple(item["code"] for item in grid_meta["missing_contributors"]) if grid is not None else ()
    result = {GRID_EMISSIONS: grid_meta}
    for total, codes in GHG_TOTAL_CONTRIBUTORS.items():
        has_grid = GRID_EMISSIONS in codes
        result[total] = completeness(
            {code: emissions.get(code) for code in codes},
            "tCO2e",
            part_status=grid_status if has_grid else None,
            also_missing=meters_missing if has_grid else (),
        )
    return result


@dataclass
class Input:
    value: Decimal
    row: HistoricalMetricValue | None = None
    source: str | None = None


@dataclass
class FactorChoice:
    factor_set: EmissionFactorSet | None
    reason: str | None


def current_authoritative_values(db: Session, period_id: UUID) -> dict[tuple[str, str], HistoricalMetricValue]:
    rows = db.scalars(select(HistoricalMetricValue).where(HistoricalMetricValue.period_id == period_id)).all()
    superseded = {row.supersedes_id for row in rows if row.supersedes_id is not None}
    result: dict[tuple[str, str], HistoricalMetricValue] = {}
    for row in rows:
        if row.id in superseded:
            continue
        if row.verification_status == "VERIFIED" and row.authority_status == "AUTHORITATIVE":
            result[(row.domain, row.metric_code)] = row
    return result


def applicable_factor_set_for(db: Session, start: date, end: date) -> FactorChoice:
    """One governed factor set must cover the whole period; otherwise refuse."""
    active = db.scalars(
        select(EmissionFactorSet)
        .where(EmissionFactorSet.status == FactorSetStatus.ACTIVE, EmissionFactorSet.effective_from.is_not(None))
        .order_by(EmissionFactorSet.effective_from.desc(), EmissionFactorSet.id)
    ).all()
    covering = next((item for item in active if item.effective_from is not None and item.effective_from <= start), None)
    if covering is None:
        return FactorChoice(None, "no_applicable_factor_set")
    if any(item.effective_from is not None and start < item.effective_from <= end for item in active):
        return FactorChoice(None, "multiple_factor_sets_in_period")
    return FactorChoice(covering, None)


def population_for(db: Session, year: int) -> tuple[Decimal | None, dict[str, object]]:
    governed = db.get(InstitutionalPopulationReference, year)
    if governed is not None and governed.population > 0:
        return Decimal(governed.population), {
            "kind": "governed_population_reference",
            "effective_year": year,
            "source_reference": governed.source_reference,
        }
    period = db.scalar(
        select(HistoricalPeriod).where(HistoricalPeriod.granularity == "ANNUAL", HistoricalPeriod.year == year)
    )
    if period is not None:
        row = current_authoritative_values(db, period.id).get(("population", "population"))
        if row is not None and row.value_numeric > 0:
            return row.value_numeric, {
                "kind": "historical_verified",
                "effective_year": year,
                "metric_value_id": str(row.id),
                "source_batch_id": str(row.source_batch_id),
                "source_column": row.source_column,
            }
    return None, {"kind": "unavailable", "effective_year": year}


def canonical(value: Decimal) -> str:
    """Scale-independent text: 8778, 8778.0 and 8778.000000 hash identically."""
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _snapshot(inputs: dict[str, Input | None]) -> dict[str, object]:
    return {
        code: (
            None
            if item is None
            else {
                "value": canonical(item.value),
                "metric_value_id": str(item.row.id) if item.row is not None else None,
                "source": item.source,
            }
        )
        for code, item in sorted(inputs.items())
    }


def _hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class PeriodCalculator:
    def __init__(
        self,
        db: Session,
        period: HistoricalPeriod,
        *,
        values: dict[tuple[str, str], HistoricalMetricValue] | None = None,
        population: tuple[Decimal | None, dict[str, object]] | None = None,
    ) -> None:
        # ``values``/``population`` let a dry run calculate from the in-memory
        # reconciliation plan without writing anything.
        self.db = db
        self.period = period
        self.values = values if values is not None else current_authoritative_values(db, period.id)
        self.population = population
        self.results: dict[str, tuple[Decimal | None, str | None, str, dict[str, Any]]] = {}

    def value(self, domain: str, metric: str) -> Input | None:
        row = self.values.get((domain, metric))
        return None if row is None else Input(row.value_numeric, row, f"{domain}.{metric}")

    def result(self, code: str) -> Input | None:
        stored = self.results.get(code)
        if stored is None or stored[0] is None:
            return None
        return Input(stored[0], None, f"calculation.{code}")

    def record(
        self,
        code: str,
        unit: str,
        inputs: dict[str, Input | None],
        value: Decimal | None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if all(item is None for item in inputs.values()) and not extra:
            return
        missing = sorted(name for name, item in inputs.items() if item is None)
        stated = (extra or {}).get("reason")
        reason = (
            None
            if value is not None
            else (stated or (f"inputs_missing:{','.join(missing)}" if missing else "not_calculable"))
        )
        self.results[code] = (value, reason, unit, {"inputs": _snapshot(inputs), **(extra or {})})

    def calculate(self) -> None:
        start, end = self.period.coverage_start, self.period.coverage_end
        choice = applicable_factor_set_for(self.db, start, end)
        factors: dict[str, EmissionFactor] = {}
        if choice.factor_set is not None:
            factors = {
                item.code: item
                for item in self.db.scalars(
                    select(EmissionFactor).where(EmissionFactor.factor_set_id == choice.factor_set.id)
                ).all()
            }

        def factor_extra(code: str) -> dict[str, Any]:
            factor = factors.get(code)
            if choice.factor_set is None or factor is None:
                return {"reason": choice.reason or "factor_not_configured", "factor": None}
            return {
                "factor": {
                    "code": code,
                    "value": str(factor.factor_value),
                    "unit": f"{factor.result_unit}/{factor.activity_unit}",
                    "factor_set_id": str(choice.factor_set.id),
                    "factor_set_version": choice.factor_set.version,
                    "effective_from": str(choice.factor_set.effective_from),
                }
            }

        def factor_value(code: str) -> Decimal | None:
            factor = factors.get(code)
            return None if choice.factor_set is None or factor is None else factor.factor_value

        # DG from generation (kWh): authoritative once the governed SFC is in
        # force for the period. Litres are then DERIVED (never a second source),
        # and any source-reported litres for the same period are not used, so DG
        # is never counted through both pathways. Without a kWh source, or
        # before the SFC's effective date, the legacy litre pathway below applies.
        generation = self.value(DOMAIN_OF_INPUT[dg.DG_LITRES_METRIC], dg.DG_GENERATION_METRIC)
        derivation = None
        if generation is not None and generation.row is not None and generation.row.unit == dg.GENERATION_UNIT:
            derivation = dg.derive_litres(self.db, generation.value, start)
        if derivation is not None and generation is not None:
            self._record_dg_from_generation(generation, derivation, factors.get(dg.DG_FACTOR), factor_extra)

        for calc_code, metric, factor_code in ACTIVITY_EMISSIONS:
            activity = self.value(DOMAIN_OF_INPUT[metric], metric)
            if activity is None or (derivation is not None and metric == dg.DG_LITRES_METRIC):
                continue
            extra = factor_extra(factor_code)
            factor = factors.get(factor_code)
            activity_unit = activity.row.unit if activity.row is not None else None
            extra["activity"] = {"metric_code": metric, "unit": activity_unit}
            if factor is not None and activity_unit != factor.activity_unit:
                # Never multiply an activity by a factor of another unit.
                extra = {**extra, "reason": "incompatible_unit", "factor": None}
                self.record(calc_code, "tCO2e", {metric: activity}, None, extra)
                continue
            self.record(
                calc_code,
                "tCO2e",
                {metric: activity},
                formulas.activity_emissions_tco2e(activity.value, factor_value(factor_code)),
                extra,
            )

        ht, comm, temp = (
            self.value("energy", code) for code in ("grid_ht_kwh", "grid_commercial_kwh", "grid_temporary_kwh")
        )
        self.record(
            "grid_total_kwh",
            "kWh",
            {"grid_ht_kwh": ht, "grid_commercial_kwh": comm, "grid_temporary_kwh": temp},
            formulas.grid_total_kwh(*(item.value if item else None for item in (ht, comm, temp))),
        )
        grid = self.result("grid_total_kwh")
        # Grid emissions use every meter that reported (available-data rule);
        # grid_total_kwh above stays the complete three-meter total.
        meters: dict[str, Input | None] = dict(zip(GRID_METERS, (ht, comm, temp), strict=True))
        if any(meters.values()):
            metered_kwh = formulas.grid_available_kwh(*(item.value if item else None for item in meters.values()))
            self.record(
                GRID_EMISSIONS,
                "tCO2e",
                meters,
                formulas.activity_emissions_tco2e(metered_kwh, factor_value("GRID_ELECTRICITY")),
                factor_extra("GRID_ELECTRICITY"),
            )
        on_campus, procured = (
            self.value("energy", "renewable_on_campus_kwh"),
            self.value("energy", "renewable_procured_kwh"),
        )
        self.record(
            "renewable_electricity_kwh",
            "kWh",
            {"renewable_on_campus_kwh": on_campus, "renewable_procured_kwh": procured},
            formulas.renewable_electricity_kwh(
                on_campus.value if on_campus else None, procured.value if procured else None
            ),
        )
        renewable = self.result("renewable_electricity_kwh")
        self.record(
            "total_electricity_consumption_kwh",
            "kWh",
            {"grid_total_kwh": grid, "renewable_electricity_kwh": renewable},
            formulas.total_electricity_consumption_kwh(
                grid.value if grid else None, renewable.value if renewable else None
            ),
        )
        total = self.result("total_electricity_consumption_kwh")
        self.record(
            "renewable_share_pct",
            "%",
            {"renewable_electricity_kwh": renewable, "total_electricity_consumption_kwh": total},
            formulas.renewable_share_pct(renewable.value if renewable else None, total.value if total else None),
        )
        if renewable is not None:
            self.record(
                "estimated_avoided_grid_emissions_tco2e",
                "tCO2e",
                {"renewable_electricity_kwh": renewable},
                formulas.estimated_avoided_grid_emissions_tco2e(renewable.value, factor_value("GRID_ELECTRICITY")),
                factor_extra("GRID_ELECTRICITY"),
            )

        # Scope 1 / Scope 2 / Operational GHG: sum of the contributors that exist.
        # A missing contributor is excluded (never zero) and named in the
        # result's completeness, which also marks it COMPLETE or PARTIAL.
        parts = {code: self.result(code) for code in SCOPE1_CONTRIBUTORS}
        scope2 = self.result(GRID_EMISSIONS)
        coverage = ghg_completeness(
            {
                **{code: item.value if item else None for code, item in parts.items()},
                GRID_EMISSIONS: scope2.value if scope2 else None,
            },
            {code: item.value if item else None for code, item in meters.items()},
        )
        if GRID_EMISSIONS in self.results:
            self.results[GRID_EMISSIONS][3]["completeness"] = coverage[GRID_EMISSIONS]
        if any(parts.values()):
            self.record(
                "scope1_tco2e",
                "tCO2e",
                parts,
                formulas.scope1_available_tco2e(*(item.value if item else None for item in parts.values())),
                {"completeness": coverage["scope1_tco2e"]},
            )
        if scope2 is not None:
            self.record(
                "scope2_tco2e",
                "tCO2e",
                {GRID_EMISSIONS: scope2},
                scope2.value,
                {"completeness": coverage["scope2_tco2e"]},
            )
        scope1 = self.result("scope1_tco2e")
        if scope1 is not None or scope2 is not None:
            self.record(
                "operational_ghg_tco2e",
                "tCO2e",
                {"scope1_tco2e": scope1, "scope2_tco2e": self.result("scope2_tco2e")},
                formulas.operational_ghg_available_tco2e(
                    scope1.value if scope1 else None, scope2.value if scope2 else None
                ),
                {"completeness": coverage["operational_ghg_tco2e"]},
            )

        population, population_source = self.population or population_for(self.db, self.period.year)
        people = Input(population, None, "population") if population is not None else None
        operational = self.result("operational_ghg_tco2e")
        if operational is not None and self.period.granularity == "MONTHLY":
            per_capita = formulas.operational_ghg_per_capita_kgco2e(operational.value, population)
            self.record(
                PER_CAPITA_GHG,
                "kgCO2e/person",
                {"operational_ghg_tco2e": operational, "population": people},
                per_capita,
                {
                    "population": population_source,
                    # The emissions behind the per-person figure, so it is never
                    # shown as complete when Operational GHG is partial.
                    "completeness": coverage["operational_ghg_tco2e"]
                    if per_capita is not None
                    else {"status": UNAVAILABLE, "contributors": [], "missing_contributors": []},
                },
            )

        twad, bore, private = (
            self.value("water", code) for code in ("water_twad_kl", "water_borewell_kl", "water_private_kl")
        )
        if any((twad, bore, private)):
            self.record(
                "water_consumed_kl",
                "KL",
                {"water_twad_kl": twad, "water_borewell_kl": bore, "water_private_kl": private},
                formulas.water_consumed_kl(*(item.value if item else None for item in (twad, bore, private))),
            )
        water = self.result("water_consumed_kl") or self.value("water", "water_consumed_kl")
        if water is not None:
            self.record(
                "water_per_capita_l",
                "L/person",
                {"water_consumed_kl": water, "population": people},
                formulas.water_per_capita_l(water.value, population),
                {"population": population_source},
            )

        wet, dry = self.value("waste", "wet_waste_generated_kg"), self.value("waste", "dry_waste_generated_kg")
        if wet is not None or dry is not None:
            self.record(
                "total_waste_generated_kg",
                "kg",
                {"wet_waste_generated_kg": wet, "dry_waste_generated_kg": dry},
                formulas.waste_total_kg(wet.value if wet else None, dry.value if dry else None),
            )
            # Owner-approved methodology: diverted from landfill = dry waste.
            self.record(
                "waste_diverted_from_landfill_kg",
                "kg",
                {"dry_waste_generated_kg": dry},
                formulas.waste_diverted_from_landfill_kg(dry.value if dry else None),
                {"methodology": "diverted_from_landfill_equals_dry_waste"},
            )
            waste_total = self.result("total_waste_generated_kg")
            self.record(
                "waste_per_capita_kg",
                "kg/person",
                {"total_waste_generated_kg": waste_total, "population": people},
                formulas.waste_per_capita_kg(waste_total.value if waste_total else None, population),
                {"population": population_source},
            )

    def _record_dg_from_generation(
        self,
        generation: Input,
        derivation: dg.DgDerivation,
        factor: EmissionFactor | None,
        factor_extra: Any,
    ) -> None:
        detail = derivation.as_json()
        if (dg.DOMAIN_KEY, dg.DG_LITRES_METRIC) in self.values:
            # Stated, not hidden: a litre value also exists and was not used.
            detail["source_litres_not_used"] = True
        inputs: dict[str, Input | None] = {dg.DG_GENERATION_METRIC: generation}
        self.record(dg.DG_LITRES_METRIC, dg.LITRES_UNIT, inputs, derivation.litres, {"derivation": detail})
        extra = {**factor_extra(dg.DG_FACTOR), "derivation": detail}
        extra["activity"] = {"metric_code": dg.DG_GENERATION_METRIC, "unit": dg.GENERATION_UNIT}
        if factor is not None and factor.activity_unit != dg.LITRES_UNIT:
            extra = {**extra, "reason": "incompatible_unit", "factor": None}
            self.record(dg.DG_EMISSIONS, "tCO2e", inputs, None, extra)
            return
        self.record(
            dg.DG_EMISSIONS,
            "tCO2e",
            inputs,
            formulas.activity_emissions_tco2e(derivation.litres, factor.factor_value if factor else None),
            extra,
        )

    def persist(self) -> tuple[int, int]:
        """Insert new/changed results; retire replaced ones. Returns (inserted, unchanged)."""
        inserted = unchanged = 0
        current = {
            row.calculation_code: row
            for row in self.db.scalars(
                select(HistoricalCalculationResult).where(
                    HistoricalCalculationResult.period_id == self.period.id,
                    HistoricalCalculationResult.is_current.is_(True),
                )
            ).all()
        }
        for code, (value, reason, unit, detail) in sorted(self.results.items()):
            stored_value = None if value is None else value.quantize(FULL_PRECISION)
            factor = detail.get("factor") or {}
            input_hash = _hash(
                {
                    "value": None if stored_value is None else canonical(stored_value),
                    "reason": reason,
                    "detail": detail,
                    "methodology": methodology_for(code, detail),
                }
            )
            existing = current.get(code)
            if existing is not None and existing.input_hash == input_hash:
                unchanged += 1
                continue
            if existing is not None:
                existing.is_current = False
                self.db.flush()
            self.db.add(
                HistoricalCalculationResult(
                    period_id=self.period.id,
                    calculation_code=code,
                    status="available" if stored_value is not None else "unavailable",
                    unavailable_reason=reason,
                    result_value=stored_value,
                    result_unit=unit,
                    methodology_version=methodology_for(code, detail),
                    factor_code=factor.get("code"),
                    factor_value=Decimal(factor["value"]) if factor.get("value") else None,
                    factor_unit=factor.get("unit"),
                    factor_set_id=UUID(factor["factor_set_id"]) if factor.get("factor_set_id") else None,
                    factor_set_version=factor.get("factor_set_version"),
                    input_hash=input_hash,
                    input_snapshot=detail.get("inputs", {}),
                    provenance={key: item for key, item in detail.items() if key != "inputs"},
                )
            )
            inserted += 1
        self.db.flush()
        return inserted, unchanged


def calculate_all(db: Session) -> tuple[int, int]:
    inserted = unchanged = 0
    for period in db.scalars(select(HistoricalPeriod).order_by(HistoricalPeriod.coverage_start)).all():
        calculator = PeriodCalculator(db, period)
        calculator.calculate()
        added, same = calculator.persist()
        inserted += added
        unchanged += same
    return inserted, unchanged
