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
from app.services import sustainability_formulas as formulas

METHODOLOGY_VERSION = "kcosmos-schema-1.4-formulas-v1"
FULL_PRECISION = Decimal("0.000000000001")

# (calculation_code, unit, factor code or None)
ACTIVITY_EMISSIONS = (
    ("transport_petrol_emissions", "transport_petrol_litres", "PETROL"),
    ("transport_diesel_emissions", "transport_diesel_litres", "DIESEL"),
    ("dg_diesel_emissions", "dg_diesel_litres", "DIESEL"),
    ("lpg_emissions", "lpg_consumption_litres", "LPG"),
)
DOMAIN_OF_INPUT = {
    "transport_petrol_litres": "transport",
    "transport_diesel_litres": "transport",
    "dg_diesel_litres": "transport",
    "lpg_consumption_litres": "lpg",
}


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
        reason = (
            None
            if value is not None
            else (f"inputs_missing:{','.join(missing)}" if missing else (extra or {}).get("reason", "not_calculable"))
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

        for calc_code, metric, factor_code in ACTIVITY_EMISSIONS:
            activity = self.value(DOMAIN_OF_INPUT[metric], metric)
            if activity is None:
                continue
            extra = factor_extra(factor_code)
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
        if grid is not None or any((ht, comm, temp)):
            self.record(
                "grid_electricity_emissions",
                "tCO2e",
                {"grid_total_kwh": grid},
                formulas.activity_emissions_tco2e(grid.value if grid else None, factor_value("GRID_ELECTRICITY")),
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

        parts = {code: self.result(code) for code, _, _ in ACTIVITY_EMISSIONS}
        if any(parts.values()):
            self.record(
                "scope1_tco2e",
                "tCO2e",
                parts,
                formulas.scope1_tco2e(*(item.value if item else None for item in parts.values())),
            )
        scope2 = self.result("grid_electricity_emissions")
        if scope2 is not None:
            self.record("scope2_tco2e", "tCO2e", {"grid_electricity_emissions": scope2}, scope2.value)
        scope1 = self.result("scope1_tco2e")
        if scope1 is not None or scope2 is not None:
            self.record(
                "operational_ghg_tco2e",
                "tCO2e",
                {"scope1_tco2e": scope1, "scope2_tco2e": self.result("scope2_tco2e")},
                formulas.operational_ghg_tco2e(scope1.value if scope1 else None, scope2.value if scope2 else None),
            )

        population, population_source = self.population or population_for(self.db, self.period.year)
        people = Input(population, None, "population") if population is not None else None
        operational = self.result("operational_ghg_tco2e")
        if operational is not None and self.period.granularity == "MONTHLY":
            self.record(
                "operational_ghg_per_capita_kgco2e",
                "kgCO2e/person",
                {"operational_ghg_tco2e": operational, "population": people},
                formulas.operational_ghg_per_capita_kgco2e(operational.value, population),
                {"population": population_source},
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
            waste_total = self.result("total_waste_generated_kg")
            self.record(
                "waste_per_capita_kg",
                "kg/person",
                {"total_waste_generated_kg": waste_total, "population": people},
                formulas.waste_per_capita_kg(waste_total.value if waste_total else None, population),
                {"population": population_source},
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
                    "methodology": METHODOLOGY_VERSION,
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
                    methodology_version=METHODOLOGY_VERSION,
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
