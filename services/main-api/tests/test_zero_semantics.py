"""Zero is a measured value; missing is not zero.

Project-owner rule: an explicit numeric 0 means "reported, and nothing was
consumed" and is a complete, available input. None (no row, conflict,
rejected, unverified) stays missing and is never turned into 0.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.historical.calculator import PeriodCalculator, population_for
from app.models.history import HistoricalMetricValue, HistoricalPeriod
from app.models.sustainability import InstitutionalPopulationReference
from app.services import sustainability_formulas as formulas
from tests.test_historical_integration import _energy_csv, _free_year, _import, _mapping, _timeline, _write
from tests.test_lpg_kg_methodology import _governed_factor_set

ZERO = Decimal("0")
GRID_FACTOR = Decimal("0.727")


# ---- Formulas (no database) ---------------------------------------------------


def test_grid_total_counts_zero_meters_and_refuses_a_missing_one() -> None:
    assert formulas.grid_total_kwh(Decimal("100"), ZERO, Decimal("50")) == Decimal("150")
    assert formulas.grid_total_kwh(ZERO, ZERO, ZERO) == ZERO
    assert formulas.grid_total_kwh(Decimal("100"), None, Decimal("50")) is None
    assert formulas.activity_emissions_tco2e(ZERO, GRID_FACTOR) == ZERO


def test_scope1_operational_and_per_capita_accept_zero() -> None:
    assert formulas.scope1_tco2e(ZERO, Decimal("1"), ZERO, Decimal("2")) == Decimal("3")
    assert formulas.scope1_tco2e(ZERO, ZERO, ZERO, ZERO) == ZERO
    assert formulas.scope1_tco2e(ZERO, Decimal("1"), None, Decimal("2")) is None
    assert formulas.operational_ghg_tco2e(ZERO, ZERO) == ZERO
    assert formulas.operational_ghg_tco2e(Decimal("5"), None) is None
    assert formulas.operational_ghg_per_capita_kgco2e(ZERO, 6991) == ZERO
    assert formulas.operational_ghg_per_capita_kgco2e(Decimal("5"), None) is None
    # A zero population is invalid: never divide by it.
    assert formulas.operational_ghg_per_capita_kgco2e(Decimal("5"), 0) is None


def test_renewables_and_avoided_emissions_accept_zero() -> None:
    assert formulas.renewable_electricity_kwh(ZERO, Decimal("1000")) == Decimal("1000")
    assert formulas.renewable_electricity_kwh(ZERO, ZERO) == ZERO
    assert formulas.renewable_electricity_kwh(ZERO, None) is None
    assert formulas.estimated_avoided_grid_emissions_tco2e(ZERO, GRID_FACTOR) == ZERO


# ---- Historical calculator and resolver (PostgreSQL) --------------------------


@pytest.fixture
def zero_year(postgres_engine: Engine) -> int:
    with Session(postgres_engine) as db:
        chosen = _free_year(db)
        _governed_factor_set(db, chosen)
        db.commit()
    return chosen


def _period(year: int, month: int) -> HistoricalPeriod:
    return HistoricalPeriod(
        id=uuid4(), year=year, month=month, granularity="MONTHLY",
        coverage_start=date(year, month, 1), coverage_end=date(year, month, 28), display_label=f"{month}/{year}",
    )


def _values(period: HistoricalPeriod, metrics: dict[str, tuple[str, str, str]]) -> dict[tuple[str, str], Any]:
    return {
        (domain, code): HistoricalMetricValue(
            id=uuid4(), period_id=period.id, domain=domain, metric_code=code, value_numeric=Decimal(value),
            unit=unit, verification_status="VERIFIED", authority_status="AUTHORITATIVE",
        )
        for code, (domain, value, unit) in metrics.items()
    }


ALL_ZERO = {
    "transport_petrol_litres": ("transport", "0", "L"),
    "transport_diesel_litres": ("transport", "0", "L"),
    "dg_diesel_litres": ("transport", "0", "L"),
    "lpg_weight_kg": ("lpg", "0", "kg"),
    "grid_ht_kwh": ("energy", "0", "kWh"),
    "grid_commercial_kwh": ("energy", "0", "kWh"),
    "grid_temporary_kwh": ("energy", "0", "kWh"),
    "renewable_on_campus_kwh": ("energy", "0", "kWh"),
    "renewable_procured_kwh": ("energy", "0", "kWh"),
}


def _calculate(db: Session, year: int, metrics: dict[str, tuple[str, str, str]], population: Decimal | None):
    period = _period(year, 1)
    calculator = PeriodCalculator(
        db, period, values=_values(period, metrics), population=(population, {"kind": "test"})
    )
    calculator.calculate()
    return {code: (item[0], item[1]) for code, item in calculator.results.items()}


def test_all_zero_month_is_complete_and_calculates_zero(postgres_engine: Engine, zero_year: int) -> None:
    with Session(postgres_engine) as db:
        result = _calculate(db, zero_year, ALL_ZERO, Decimal("6991"))
        for code in (
            "grid_total_kwh", "grid_electricity_emissions", "scope2_tco2e", "transport_petrol_emissions",
            "transport_diesel_emissions", "dg_diesel_emissions", "lpg_emissions", "scope1_tco2e",
            "operational_ghg_tco2e", "operational_ghg_per_capita_kgco2e", "renewable_electricity_kwh",
            "estimated_avoided_grid_emissions_tco2e",
        ):
            assert result[code] == (ZERO, None), code


def test_zero_meter_counts_but_a_missing_meter_does_not(postgres_engine: Engine, zero_year: int) -> None:
    with Session(postgres_engine) as db:
        mixed = {
            **ALL_ZERO,
            "grid_ht_kwh": ("energy", "100", "kWh"),
            "grid_temporary_kwh": ("energy", "50", "kWh"),
            "transport_diesel_litres": ("transport", "1000", "L"),
            "lpg_weight_kg": ("lpg", "1000", "kg"),
        }
        result = _calculate(db, zero_year, mixed, Decimal("6991"))
        assert result["grid_total_kwh"][0] == Decimal("150")
        assert result["scope2_tco2e"][0] == Decimal("0.109050")  # 150 kWh x 0.727 / 1000
        # 0 petrol + 2.701 fleet diesel + 0 DG + 2.98 LPG.
        assert result["scope1_tco2e"][0] == Decimal("5.681000")
        assert result["operational_ghg_tco2e"][0] == Decimal("5.790050")

        missing = {code: item for code, item in mixed.items() if code != "grid_commercial_kwh"}
        result = _calculate(db, zero_year, missing, Decimal("6991"))
        # The complete three-meter total still refuses a missing meter...
        assert result["grid_total_kwh"] == (None, "inputs_missing:grid_commercial_kwh")
        # ...while GHG follows the available-data rule: the two meters that
        # reported are used, and the missing one is excluded, never zero.
        assert result["scope2_tco2e"] == (Decimal("0.109050"), None)
        assert result["operational_ghg_tco2e"] == (Decimal("5.790050"), None)
        assert result["operational_ghg_per_capita_kgco2e"][0] == Decimal("5.790050") * 1000 / 6991


def test_per_capita_needs_a_valid_population(postgres_engine: Engine, zero_year: int) -> None:
    with Session(postgres_engine) as db:
        assert _calculate(db, zero_year, ALL_ZERO, None)["operational_ghg_per_capita_kgco2e"] == (
            None, "inputs_missing:population",
        )
        assert _calculate(db, zero_year, ALL_ZERO, ZERO)["operational_ghg_per_capita_kgco2e"][0] is None
        # Governed population is read from the database; 0 is invalid, never a divisor.
        assert population_for(db, zero_year)[0] is None
        db.add(InstitutionalPopulationReference(
            effective_year=zero_year, population=0, unit="people", source_reference="Zero-population test",
        ))
        db.flush()
        assert population_for(db, zero_year)[0] is None
        db.rollback()


def test_zero_months_count_toward_aggregate_coverage(postgres_engine: Engine, tmp_path: Path, zero_year: int) -> None:
    energy = _mapping("energy_staging", uuid4().hex[:8])
    _write(tmp_path, energy, _energy_csv(zero_year, [
        ("January", "100", "0", "50", "0", "10", "0"),
        ("February", "0", "0", "0", "0", "0", "0"),
    ]))
    _import(postgres_engine, tmp_path, [energy])
    timeline = _timeline(postgres_engine)
    february = timeline["periods"][f"{zero_year}-02"]["values"]
    assert february["grid_total_kwh"]["status"] == "available" and february["grid_total_kwh"]["value"] == 0
    assert february["scope2_tco2e"]["value"] == 0
    assert february["estimated_avoided_grid_emissions_tco2e"]["value"] == 0
    ytd = timeline["periods"][f"{zero_year}-YTD"]["values"]
    assert ytd["grid_total_kwh"]["value"] == 150
    assert ytd["grid_total_kwh"]["coverage_status"] == "complete"
    assert ytd["grid_total_kwh"]["months_covered"] == [f"{zero_year}-01", f"{zero_year}-02"]
    assert ytd["scope2_tco2e"]["months_covered"] == [f"{zero_year}-01", f"{zero_year}-02"]
    # The zero month is still displayed as that month's own genuine value.
    assert timeline["periods"][f"{zero_year}-02"]["display"]["grid_total_kwh"]["value"] == 0
