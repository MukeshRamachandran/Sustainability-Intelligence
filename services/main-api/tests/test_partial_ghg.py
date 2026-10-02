"""Available-data GHG methodology (project-owner decision).

Scope 1, Scope 2, Operational GHG and its per-capita value are calculated from
every verified contributor that exists. A missing contributor is excluded from
the sum - never treated as zero - and the result is labelled PARTIAL with the
contributors that produced it and the ones that are missing. An explicit zero
is a contributor. Official release preparation keeps its stricter rule.
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.historical.calculator import (
    AVAILABLE_DATA_METHODOLOGY_VERSION,
    METHODOLOGY_VERSION,
    PeriodCalculator,
    completeness,
    ghg_completeness,
)
from app.historical.resolver import build_timeline
from app.models.history import (
    HistoricalCalculationResult,
    HistoricalImportBatch,
    HistoricalMetricValue,
    HistoricalPeriod,
)
from app.models.sustainability import InstitutionalPopulationReference
from app.services import sustainability_formulas as formulas
from tests.test_historical_integration import _free_year
from tests.test_lpg_kg_methodology import LPG_FACTOR, _governed_factor_set

ZERO = Decimal("0")
PETROL_FACTOR, DIESEL_FACTOR, GRID_FACTOR = Decimal("2.388"), Decimal("2.701"), Decimal("0.727")
POPULATION = 6991
SCOPE1 = "scope1_tco2e"
SCOPE2 = "scope2_tco2e"
OPERATIONAL = "operational_ghg_tco2e"
PER_CAPITA = "operational_ghg_per_capita_kgco2e"

# metric -> (domain, unit)
METRICS = {
    "transport_petrol_litres": ("transport", "L"),
    "transport_diesel_litres": ("transport", "L"),
    "dg_diesel_litres": ("transport", "L"),
    "lpg_weight_kg": ("lpg", "kg"),
    "grid_ht_kwh": ("energy", "kWh"),
    "grid_commercial_kwh": ("energy", "kWh"),
    "grid_temporary_kwh": ("energy", "kWh"),
}
FUELS = {"transport_petrol_litres": "100", "transport_diesel_litres": "200", "dg_diesel_litres": "300"}
LPG = {"lpg_weight_kg": "400"}
GRID = {"grid_ht_kwh": "1000", "grid_commercial_kwh": "100", "grid_temporary_kwh": "10"}


def tco2e(activity: str, factor: Decimal) -> Decimal:
    result = formulas.activity_emissions_tco2e(Decimal(activity), factor)
    assert result is not None
    return result


# ---- Formulas (no database) ---------------------------------------------------


def test_available_total_excludes_missing_and_never_substitutes_zero() -> None:
    assert formulas.available_total((Decimal("1"), None, Decimal("2"))) == Decimal("3")
    assert formulas.available_total((None, None)) is None  # nothing available: missing, not 0
    assert formulas.available_total((ZERO, None)) == ZERO  # an explicit zero is a value
    assert formulas.available_total(()) is None


def test_scope1_available_formula() -> None:
    one, two, three, four = (Decimal(n) for n in ("1", "2", "3", "4"))
    # All four: identical to the strict (official) rule.
    assert formulas.scope1_available_tco2e(one, two, three, four) == formulas.scope1_tco2e(one, two, three, four)
    assert formulas.scope1_available_tco2e(None, None, three, None) == three  # DG only
    assert formulas.scope1_available_tco2e(None, None, None, four) == four  # LPG only
    assert formulas.scope1_available_tco2e(one, None, None, four) == Decimal("5")  # Petrol + LPG
    assert formulas.scope1_available_tco2e(ZERO, None, None, four) == four  # explicit zero contributes 0
    assert formulas.scope1_available_tco2e(ZERO, None, None, None) == ZERO
    assert formulas.scope1_available_tco2e(None, None, None, None) is None
    # The strict rule used by official release preparation is unchanged.
    assert formulas.scope1_tco2e(one, None, three, four) is None


def test_grid_and_operational_available_formulas() -> None:
    ht, comm, temp = Decimal("100"), Decimal("20"), Decimal("5")
    assert formulas.grid_available_kwh(ht, comm, temp) == formulas.grid_total_kwh(ht, comm, temp)
    assert formulas.grid_available_kwh(ht, None, None) == ht  # HT meter only
    assert formulas.grid_available_kwh(ZERO, ZERO, ZERO) == ZERO
    assert formulas.grid_available_kwh(None, None, None) is None
    assert formulas.grid_total_kwh(ht, None, None) is None  # the complete total still needs all three
    five, seven = Decimal("5"), Decimal("7")
    assert formulas.operational_ghg_available_tco2e(five, None) == five
    assert formulas.operational_ghg_available_tco2e(None, seven) == seven
    assert formulas.operational_ghg_available_tco2e(five, seven) == formulas.operational_ghg_tco2e(five, seven)
    assert formulas.operational_ghg_available_tco2e(None, None) is None
    assert formulas.operational_ghg_tco2e(five, None) is None  # strict rule unchanged


def test_per_capita_needs_population_and_never_divides_by_zero() -> None:
    partial_operational = Decimal("35.276749")
    assert formulas.operational_ghg_per_capita_kgco2e(partial_operational, POPULATION) == (
        partial_operational * 1000 / POPULATION
    )
    assert formulas.operational_ghg_per_capita_kgco2e(partial_operational, None) is None
    assert formulas.operational_ghg_per_capita_kgco2e(partial_operational, 0) is None
    assert formulas.operational_ghg_per_capita_kgco2e(None, POPULATION) is None


def test_completeness_states() -> None:
    full = completeness({"lpg_emissions": Decimal("2"), "dg_diesel_emissions": ZERO}, "tCO2e")
    assert full["status"] == "COMPLETE" and full["missing_contributors"] == []
    # An explicit zero is listed as a contributor with value 0.
    zero = {"code": "dg_diesel_emissions", "label": "DG Diesel", "value": "0", "unit": "tCO2e", "status": "COMPLETE"}
    assert zero in full["contributors"]
    partial = completeness({"lpg_emissions": Decimal("2"), "dg_diesel_emissions": None}, "tCO2e")
    assert partial["status"] == "PARTIAL"
    assert [item["code"] for item in partial["contributors"]] == ["lpg_emissions"]
    assert partial["missing_contributors"] == [{"code": "dg_diesel_emissions", "label": "DG Diesel"}]
    nothing = completeness({"lpg_emissions": None}, "tCO2e")
    assert nothing["status"] == "UNAVAILABLE" and nothing["contributors"] == []


def test_ghg_completeness_follows_a_partial_grid_into_scope2_and_operational() -> None:
    emissions = {
        "transport_petrol_emissions": Decimal("1"),
        "transport_diesel_emissions": Decimal("1"),
        "dg_diesel_emissions": Decimal("1"),
        "lpg_emissions": Decimal("1"),
        "grid_electricity_emissions": Decimal("3"),
    }
    all_meters = {"grid_ht_kwh": Decimal("9"), "grid_commercial_kwh": ZERO, "grid_temporary_kwh": Decimal("1")}
    complete = ghg_completeness(emissions, all_meters)
    assert {code: item["status"] for code, item in complete.items()} == {
        "grid_electricity_emissions": "COMPLETE", SCOPE1: "COMPLETE", SCOPE2: "COMPLETE", OPERATIONAL: "COMPLETE",
    }
    ht_only = ghg_completeness(emissions, {**all_meters, "grid_commercial_kwh": None, "grid_temporary_kwh": None})
    assert ht_only[SCOPE1]["status"] == "COMPLETE"  # Scope 1 does not depend on the grid
    for code in ("grid_electricity_emissions", SCOPE2, OPERATIONAL):
        assert ht_only[code]["status"] == "PARTIAL"
        assert {item["code"] for item in ht_only[code]["missing_contributors"]} == {
            "grid_commercial_kwh", "grid_temporary_kwh",
        }
    # Meters not itemised (a published release): an available grid result is complete.
    assert ghg_completeness(emissions, None)[OPERATIONAL]["status"] == "COMPLETE"


# ---- Historical calculator (PostgreSQL) ---------------------------------------


@pytest.fixture
def ghg_year(postgres_engine: Engine) -> int:
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


def _calculate(
    db: Session, year: int, activity: dict[str, str], population: Decimal | None = Decimal(POPULATION)
) -> dict[str, tuple[Decimal | None, str | None, str, dict[str, Any]]]:
    period = _period(year, 1)
    values = {
        (METRICS[code][0], code): HistoricalMetricValue(
            id=uuid4(), period_id=period.id, domain=METRICS[code][0], metric_code=code,
            value_numeric=Decimal(value), unit=METRICS[code][1],
            verification_status="VERIFIED", authority_status="AUTHORITATIVE",
        )
        for code, value in activity.items()
    }
    calculator = PeriodCalculator(db, period, values=values, population=(population, {"kind": "test"}))
    calculator.calculate()
    return calculator.results


def _status(results: dict[str, Any], code: str) -> str:
    return str(results[code][3]["completeness"]["status"])


def _contributors(results: dict[str, Any], code: str) -> dict[str, Decimal]:
    return {item["code"]: Decimal(item["value"]) for item in results[code][3]["completeness"]["contributors"]}


def _missing(results: dict[str, Any], code: str) -> set[str]:
    return {item["code"] for item in results[code][3]["completeness"]["missing_contributors"]}


def test_all_components_give_the_same_complete_result_as_the_strict_rule(
    postgres_engine: Engine, ghg_year: int
) -> None:
    with Session(postgres_engine) as db:
        results = _calculate(db, ghg_year, {**FUELS, **LPG, **GRID})
        petrol, diesel, dg, lpg = (
            tco2e("100", PETROL_FACTOR), tco2e("200", DIESEL_FACTOR), tco2e("300", DIESEL_FACTOR),
            tco2e("400", LPG_FACTOR),
        )
        grid = tco2e("1110", GRID_FACTOR)
        strict_scope1 = formulas.scope1_tco2e(petrol, diesel, dg, lpg)
        strict_operational = formulas.operational_ghg_tco2e(strict_scope1, grid)
        assert results[SCOPE1][0] == strict_scope1
        assert results[SCOPE2][0] == grid
        assert results[OPERATIONAL][0] == strict_operational
        assert strict_operational is not None
        assert results[PER_CAPITA][0] == strict_operational * 1000 / POPULATION
        for code in (SCOPE1, SCOPE2, OPERATIONAL, PER_CAPITA, "grid_electricity_emissions"):
            assert _status(results, code) == "COMPLETE", code
            assert _missing(results, code) == set(), code
        assert _contributors(results, OPERATIONAL) == {
            "transport_petrol_emissions": petrol, "transport_diesel_emissions": diesel,
            "dg_diesel_emissions": dg, "lpg_emissions": lpg, "grid_electricity_emissions": grid,
        }


@pytest.mark.parametrize(
    ("activity", "expected_codes"),
    [
        ({"dg_diesel_litres": "300"}, {"dg_diesel_emissions"}),  # only DG
        (LPG, {"lpg_emissions"}),  # only LPG
        ({"transport_petrol_litres": "100", **LPG}, {"transport_petrol_emissions", "lpg_emissions"}),
    ],
)
def test_partial_scope1_sums_only_what_exists(
    postgres_engine: Engine, ghg_year: int, activity: dict[str, str], expected_codes: set[str]
) -> None:
    all_scope1 = {
        "transport_petrol_emissions", "transport_diesel_emissions", "dg_diesel_emissions", "lpg_emissions",
    }
    with Session(postgres_engine) as db:
        results = _calculate(db, ghg_year, activity)
        contributors = _contributors(results, SCOPE1)
        assert set(contributors) == expected_codes
        assert results[SCOPE1][0] == sum(contributors.values(), ZERO)
        assert all(results[code][0] == value for code, value in contributors.items())
        assert _status(results, SCOPE1) == "PARTIAL"
        assert _missing(results, SCOPE1) == all_scope1 - expected_codes
        # Scope 1 alone, no Scope 2: Operational GHG is that Scope 1, PARTIAL.
        assert SCOPE2 not in results
        assert results[OPERATIONAL][0] == results[SCOPE1][0]
        assert _status(results, OPERATIONAL) == "PARTIAL"
        assert "grid_electricity_emissions" in _missing(results, OPERATIONAL)
        operational = results[OPERATIONAL][0]
        assert operational is not None
        assert results[PER_CAPITA][0] == operational * 1000 / POPULATION
        assert _status(results, PER_CAPITA) == "PARTIAL"


def test_explicit_zero_contributor_is_included_and_missing_is_not_zero(
    postgres_engine: Engine, ghg_year: int
) -> None:
    with Session(postgres_engine) as db:
        results = _calculate(db, ghg_year, {"transport_petrol_litres": "0", **LPG})
        assert results["transport_petrol_emissions"][0] == ZERO
        assert _contributors(results, SCOPE1)["transport_petrol_emissions"] == ZERO
        # Missing fuels have no result at all - they were never turned into 0.
        assert "transport_diesel_emissions" not in results and "dg_diesel_emissions" not in results
        assert _missing(results, SCOPE1) == {"transport_diesel_emissions", "dg_diesel_emissions"}
        assert _status(results, SCOPE1) == "PARTIAL"
        # Four explicit zeros are a complete Scope 1 of zero.
        zeros = _calculate(db, ghg_year, {**dict.fromkeys(FUELS, "0"), "lpg_weight_kg": "0"})
        assert zeros[SCOPE1][0] == ZERO and _status(zeros, SCOPE1) == "COMPLETE"


def test_no_contributor_at_all_stays_unavailable(postgres_engine: Engine, ghg_year: int) -> None:
    with Session(postgres_engine) as db:
        results = _calculate(db, ghg_year, {})
        for code in (SCOPE1, SCOPE2, OPERATIONAL, PER_CAPITA, "grid_electricity_emissions"):
            assert code not in results


def test_grid_meters_complete_partial_zero_and_absent(postgres_engine: Engine, ghg_year: int) -> None:
    with Session(postgres_engine) as db:
        full = _calculate(db, ghg_year, GRID)
        assert full[SCOPE2][0] == tco2e("1110", GRID_FACTOR)
        assert _status(full, SCOPE2) == "COMPLETE"
        assert full["grid_total_kwh"][0] == Decimal("1110")

        ht_only = _calculate(db, ghg_year, {"grid_ht_kwh": "1000"})
        assert ht_only[SCOPE2][0] == tco2e("1000", GRID_FACTOR)  # HT alone, others not assumed zero
        assert _status(ht_only, SCOPE2) == "PARTIAL"
        assert _missing(ht_only, SCOPE2) == {"grid_commercial_kwh", "grid_temporary_kwh"}
        assert _contributors(ht_only, "grid_electricity_emissions") == {"grid_ht_kwh": Decimal("1000")}
        assert ht_only["grid_total_kwh"][0] is None  # the complete kWh total is still not claimed
        # Scope 2 alone, no Scope 1: Operational GHG is that Scope 2, PARTIAL.
        assert SCOPE1 not in ht_only
        assert ht_only[OPERATIONAL][0] == ht_only[SCOPE2][0]
        assert _status(ht_only, OPERATIONAL) == "PARTIAL"

        zero = _calculate(db, ghg_year, dict.fromkeys(GRID, "0"))
        assert zero[SCOPE2][0] == ZERO and _status(zero, SCOPE2) == "COMPLETE"

        assert SCOPE2 not in _calculate(db, ghg_year, LPG)


def test_complete_scope2_without_scope1_is_a_partial_operational(postgres_engine: Engine, ghg_year: int) -> None:
    with Session(postgres_engine) as db:
        results = _calculate(db, ghg_year, GRID)
        assert _status(results, SCOPE2) == "COMPLETE"
        assert results[OPERATIONAL][0] == results[SCOPE2][0]
        assert _status(results, OPERATIONAL) == "PARTIAL"
        assert _contributors(results, OPERATIONAL) == {"grid_electricity_emissions": tco2e("1110", GRID_FACTOR)}
        assert _missing(results, OPERATIONAL) == {
            "transport_petrol_emissions", "transport_diesel_emissions", "dg_diesel_emissions", "lpg_emissions",
        }


def test_partial_scope1_plus_partial_scope2_sum_what_exists(postgres_engine: Engine, ghg_year: int) -> None:
    with Session(postgres_engine) as db:
        results = _calculate(db, ghg_year, {**LPG, "grid_ht_kwh": "1000"})
        lpg, grid = tco2e("400", LPG_FACTOR), tco2e("1000", GRID_FACTOR)
        assert results[OPERATIONAL][0] == lpg + grid
        assert _status(results, OPERATIONAL) == "PARTIAL"
        assert _contributors(results, OPERATIONAL) == {"lpg_emissions": lpg, "grid_electricity_emissions": grid}
        assert _missing(results, OPERATIONAL) == {
            "transport_petrol_emissions", "transport_diesel_emissions", "dg_diesel_emissions",
            "grid_commercial_kwh", "grid_temporary_kwh",
        }


def test_per_capita_population_rules(postgres_engine: Engine, ghg_year: int) -> None:
    with Session(postgres_engine) as db:
        missing = _calculate(db, ghg_year, LPG, None)
        assert missing[PER_CAPITA][0] is None and missing[PER_CAPITA][1] == "inputs_missing:population"
        assert _status(missing, PER_CAPITA) == "UNAVAILABLE"
        assert missing[OPERATIONAL][0] is not None  # Operational GHG itself is unaffected
        zero = _calculate(db, ghg_year, LPG, ZERO)
        assert zero[PER_CAPITA][0] is None and _status(zero, PER_CAPITA) == "UNAVAILABLE"


# ---- Persistence and the public timeline (PostgreSQL) -------------------------

# The current real May-Jul 2026 shape: May has LPG and all three grid meters,
# July has LPG only. January is a complete month.
JANUARY = {**FUELS, **LPG, **GRID}
MAY = {"lpg_weight_kg": "782.8", "grid_ht_kwh": "43460", "grid_commercial_kwh": "1537", "grid_temporary_kwh": "318"}
JULY = {"lpg_weight_kg": "1453.5"}


def _store_year(db: Session, year: int, months: dict[int, dict[str, str]]) -> None:
    batch = HistoricalImportBatch(
        id=uuid4(), batch_name=f"partial-ghg-test-{year}", original_filename="synthetic.csv",
        source_reference="tests/synthetic.csv", source_sha256=hashlib.sha256(uuid4().bytes).hexdigest(),
        source_domain="ghg", mapping_code=f"partial_ghg_test_{year}", mapping_version=1, status="VERIFIED",
    )
    db.add(batch)
    db.add(InstitutionalPopulationReference(
        effective_year=year, population=POPULATION, unit="people", source_reference="Partial GHG test population",
    ))
    db.flush()
    for month, activity in months.items():
        period = _period(year, month)
        db.add(period)
        db.flush()
        for code, value in activity.items():
            db.add(HistoricalMetricValue(
                id=uuid4(), period_id=period.id, domain=METRICS[code][0], metric_code=code,
                value_numeric=Decimal(value), unit=METRICS[code][1], source_batch_id=batch.id,
                source_column=code, verification_status="VERIFIED", authority_status="AUTHORITATIVE",
            ))
        db.flush()
        calculator = PeriodCalculator(db, period)
        calculator.calculate()
        calculator.persist()


@pytest.fixture
def stored_year(postgres_engine: Engine, ghg_year: int) -> int:
    with Session(postgres_engine) as db:
        _store_year(db, ghg_year, {1: JANUARY, 5: MAY, 7: JULY})
        db.commit()
    return ghg_year


def test_completeness_is_stored_in_existing_provenance_without_schema_change(
    postgres_engine: Engine, stored_year: int
) -> None:
    with Session(postgres_engine) as db:
        rows = {
            (month, row.calculation_code): row
            for row, month in db.execute(
                select(HistoricalCalculationResult, HistoricalPeriod.month)
                .join(HistoricalPeriod, HistoricalPeriod.id == HistoricalCalculationResult.period_id)
                .where(HistoricalPeriod.year == stored_year, HistoricalCalculationResult.is_current.is_(True))
            ).all()
        }
        may = rows[(5, OPERATIONAL)]
        assert may.status == "available"  # the stored status vocabulary is unchanged
        assert may.provenance["completeness"]["status"] == "PARTIAL"  # type: ignore[index]
        assert may.methodology_version == AVAILABLE_DATA_METHODOLOGY_VERSION
        assert rows[(1, OPERATIONAL)].provenance["completeness"]["status"] == "COMPLETE"  # type: ignore[index]
        # Results outside the GHG totals keep their methodology version.
        assert rows[(5, "lpg_emissions")].methodology_version == METHODOLOGY_VERSION
        assert rows[(5, "grid_total_kwh")].methodology_version == METHODOLOGY_VERSION
        # Recalculating identical inputs appends nothing (append-only history).
        period = db.get(HistoricalPeriod, may.period_id)
        assert period is not None
        calculator = PeriodCalculator(db, period)
        calculator.calculate()
        assert calculator.persist()[0] == 0
        db.rollback()


def test_timeline_exposes_partial_months_with_contributors(postgres_engine: Engine, stored_year: int) -> None:
    with Session(postgres_engine) as db:
        periods = build_timeline(db)["periods"]
    january, may, july = (periods[f"{stored_year}-{month:02d}"] for month in (1, 5, 7))

    for code in (SCOPE1, SCOPE2, OPERATIONAL, PER_CAPITA):
        assert january["values"][code]["calculation_status"] == "COMPLETE", code
        assert january["values"][code]["missing_contributors"] == [], code
    assert {item["code"] for item in january["values"][OPERATIONAL]["contributors"]} == {
        "transport_petrol_emissions", "transport_diesel_emissions", "dg_diesel_emissions", "lpg_emissions",
        "grid_electricity_emissions",
    }

    lpg_may = float(tco2e("782.8", LPG_FACTOR))
    grid_may = float(tco2e(str(43460 + 1537 + 318), GRID_FACTOR))
    values = may["values"]
    assert values[SCOPE1]["value"] == pytest.approx(lpg_may)
    assert values[SCOPE1]["calculation_status"] == "PARTIAL"
    assert [(item["code"], item["label"]) for item in values[SCOPE1]["contributors"]] == [("lpg_emissions", "LPG")]
    assert [item["label"] for item in values[SCOPE1]["missing_contributors"]] == ["Petrol", "Fleet Diesel", "DG Diesel"]
    assert values[SCOPE2]["value"] == pytest.approx(grid_may)
    assert values[SCOPE2]["calculation_status"] == "COMPLETE"  # all three meters reported
    assert values[OPERATIONAL]["value"] == pytest.approx(lpg_may + grid_may)
    assert values[OPERATIONAL]["calculation_status"] == "PARTIAL"
    assert {item["code"]: item["value"] for item in values[OPERATIONAL]["contributors"]} == pytest.approx(
        {"lpg_emissions": lpg_may, "grid_electricity_emissions": grid_may}
    )
    assert values[PER_CAPITA]["value"] == pytest.approx((lpg_may + grid_may) * 1000 / POPULATION)
    assert values[PER_CAPITA]["calculation_status"] == "PARTIAL"
    # A missing contributor is absent - it is never published as a zero value.
    for code in ("transport_petrol_emissions", "transport_diesel_emissions", "dg_diesel_emissions"):
        assert code not in values
    # The card layer shows the same partial value with the same metadata.
    for code in (SCOPE1, OPERATIONAL, PER_CAPITA):
        assert may["display"][code]["value"] == values[code]["value"]
        assert may["display"][code]["calculation_status"] == "PARTIAL"
        assert may["display"][code]["contributors"] == values[code]["contributors"]
        assert may["display"][code]["display_context"] is False

    lpg_july = float(tco2e("1453.5", LPG_FACTOR))
    values = july["values"]
    assert SCOPE2 not in values  # no grid activity: Scope 2 stays unavailable
    assert values[SCOPE1]["value"] == pytest.approx(lpg_july)
    assert values[OPERATIONAL]["value"] == pytest.approx(lpg_july)  # does not require the grid
    assert values[PER_CAPITA]["value"] == pytest.approx(lpg_july * 1000 / POPULATION)
    for code in (SCOPE1, OPERATIONAL, PER_CAPITA):
        assert values[code]["calculation_status"] == "PARTIAL"
    assert "Grid electricity" in [item["label"] for item in values[OPERATIONAL]["missing_contributors"]]


def test_year_to_date_sums_available_months_and_states_coverage(postgres_engine: Engine, stored_year: int) -> None:
    with Session(postgres_engine) as db:
        periods = build_timeline(db)["periods"]
    months = [periods[f"{stored_year}-{month:02d}"]["values"] for month in (1, 5, 7)]
    ytd = periods[f"{stored_year}-YTD"]
    keys = [f"{stored_year}-{month:02d}" for month in (1, 5, 7)]

    operational = ytd["values"][OPERATIONAL]
    assert operational["value"] == pytest.approx(sum(item[OPERATIONAL]["value"] for item in months))
    assert operational["calculation_status"] == "PARTIAL"
    assert operational["months_covered"] == keys
    by_code = {item["code"]: item for item in operational["contributors"]}
    assert by_code["lpg_emissions"]["months_covered"] == keys
    assert by_code["lpg_emissions"]["value"] == pytest.approx(sum(item["lpg_emissions"]["value"] for item in months))
    assert by_code["transport_petrol_emissions"]["months_covered"] == keys[:1]
    assert f"{stored_year}-05" in by_code["transport_petrol_emissions"]["months_missing"]
    assert by_code["grid_electricity_emissions"]["months_covered"] == keys[:2]
    # Months with no record at all (Feb-Apr, Jun) are missing coverage, not zeros.
    assert f"{stored_year}-02" in by_code["lpg_emissions"]["months_missing"]

    per_capita = ytd["values"][PER_CAPITA]
    assert per_capita["value"] == pytest.approx(operational["value"] * 1000 / POPULATION)
    assert per_capita["calculation_status"] == "PARTIAL"
    # The YTD cards show the partial totals instead of hiding them.
    for code in (SCOPE1, SCOPE2, OPERATIONAL, PER_CAPITA):
        assert ytd["display"][code]["calculation_status"] == "PARTIAL", code
        assert ytd["display"][code]["contributors"], code


def test_fully_reported_window_is_complete(postgres_engine: Engine, ghg_year: int) -> None:
    with Session(postgres_engine) as db:
        _store_year(db, ghg_year, {1: JANUARY, 2: JANUARY})
        db.commit()
        ytd = build_timeline(db)["periods"][f"{ghg_year}-YTD"]
    one_month = formulas.operational_ghg_tco2e(
        formulas.scope1_tco2e(
            tco2e("100", PETROL_FACTOR), tco2e("200", DIESEL_FACTOR), tco2e("300", DIESEL_FACTOR),
            tco2e("400", LPG_FACTOR),
        ),
        tco2e("1110", GRID_FACTOR),
    )
    assert one_month is not None
    assert ytd["values"][OPERATIONAL]["value"] == pytest.approx(float(one_month * 2))
    for code in (SCOPE1, SCOPE2, OPERATIONAL, PER_CAPITA):
        assert ytd["values"][code]["calculation_status"] == "COMPLETE", code
        assert ytd["values"][code]["missing_contributors"] == [], code
        assert all(not item["months_missing"] for item in ytd["values"][code]["contributors"]), code
