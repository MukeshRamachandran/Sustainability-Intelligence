"""DG generator methodology transition (0015_dg_kwh_methodology).

Two legitimate DG activity pathways feed the same DG emission:

* legacy periods - source-reported diesel litres x governed DIESEL factor;
* from the governed SFC's effective date - Manager-entered generation (kWh)
  x governed SFC -> derived litres x governed DIESEL factor.

Historical litre records are never rewritten or reverse-calculated into kWh, a
period never counts both pathways, and missing generation is never zero.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.historical.calculator import (
    DG_KWH_METHODOLOGY_VERSION,
    METHODOLOGY_VERSION,
    PeriodCalculator,
)
from app.historical.resolver import Entry, Value, _aggregates, build_timeline
from app.models.enums import FactorSetStatus, OperationalDomain, RoleCode
from app.models.history import (
    HistoricalCalculationResult,
    HistoricalImportBatch,
    HistoricalMetricValue,
    HistoricalPeriod,
)
from app.models.sustainability import (
    CalculationParameter,
    CalculationResult,
    EmissionFactor,
    EmissionFactorSet,
    InstitutionalPopulationReference,
    MetricDefinition,
)
from app.schemas.emission_factors import CalculationResponse
from app.services import dg_methodology as dg
from app.services import sustainability_formulas as formulas
from app.services.publication import _public_calculation
from tests.test_generic_submission_integration import _account, _client, _login, _period, _values
from tests.test_historical_integration import DIESEL as HISTORICAL_TEST_DIESEL
from tests.test_historical_integration import _free_year, _import, _mapping, _timeline, _write
from tests.test_historical_integration import year as year  # noqa: F401  (fixture)
from tests.test_lpg_kg_methodology import LPG_FACTOR, _governed_factor_set

SFC = Decimal("0.33")
DIESEL_FACTOR = Decimal("2.701")
GRID_FACTOR = Decimal("0.727")
POPULATION = 6991
EFFECTIVE = date(2026, 5, 1)

# Project-owner supplied generation (kWh) -> the litres and emissions it must derive.
OWNER_EXAMPLES = [
    ("9006", "2971.98", "8027.31798", "8.027318"),
    ("19890", "6563.70", "17728.5537", "17.728554"),
    ("6126", "2021.58", "5460.28758", "5.460288"),
]

METRICS = {
    "dg_generation_kwh": ("transport", "kWh"),
    "dg_diesel_litres": ("transport", "L"),
    "lpg_weight_kg": ("lpg", "kg"),
    "grid_ht_kwh": ("energy", "kWh"),
    "grid_commercial_kwh": ("energy", "kWh"),
    "grid_temporary_kwh": ("energy", "kWh"),
}


# ---- Formulas (no database) ---------------------------------------------------


@pytest.mark.parametrize(("kwh", "litres", "kgco2e", "tco2e"), OWNER_EXAMPLES)
def test_generation_derives_litres_then_emissions(kwh: str, litres: str, kgco2e: str, tco2e: str) -> None:
    derived = formulas.dg_diesel_litres(Decimal(kwh), SFC)
    assert derived == Decimal(litres)
    # Exact, unrounded: kWh x 0.33 x 2.701.
    assert formulas.activity_emissions_kgco2e(derived, DIESEL_FACTOR) == Decimal(kgco2e)
    assert Decimal(kwh) * SFC * DIESEL_FACTOR / 1000 == Decimal(kgco2e) / 1000
    # Stored tCO2e is quantized exactly like every other governed emission.
    assert formulas.activity_emissions_tco2e(derived, DIESEL_FACTOR) == Decimal(tco2e)


def test_zero_generation_is_valid_and_missing_is_not_zero() -> None:
    assert formulas.dg_diesel_litres(Decimal("0"), SFC) == Decimal("0")
    assert formulas.activity_emissions_tco2e(Decimal("0"), DIESEL_FACTOR) == Decimal("0")
    assert formulas.dg_diesel_litres(None, SFC) is None
    assert formulas.dg_diesel_litres(Decimal("9006"), None) is None


# ---- Governance (PostgreSQL) --------------------------------------------------


def test_sfc_is_a_governed_parameter_not_an_emission_factor(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db:
        parameter = db.scalar(select(CalculationParameter).where(CalculationParameter.code == dg.DG_SFC))
        assert parameter is not None
        assert parameter.parameter_value == SFC
        assert parameter.unit == "L/kWh"
        assert parameter.effective_from == EFFECTIVE
        assert parameter.source_reference.strip()
        # It is not stored as, or selectable as, an emission factor.
        assert db.scalar(select(EmissionFactor.id).where(EmissionFactor.code == dg.DG_SFC)) is None
        # Effective-dated: not in force the day before, in force from the day itself.
        assert dg.parameter_for(db, dg.DG_SFC, date(2026, 4, 30)) is None
        assert dg.parameter_for(db, dg.DG_SFC, EFFECTIVE) is not None
        assert dg.manager_source_metric(db, date(2026, 4, 1)) == "dg_diesel_litres"
        assert dg.manager_source_metric(db, EFFECTIVE) == "dg_generation_kwh"
        assert dg.manager_source_metric(db, date(2031, 8, 1)) == "dg_generation_kwh"  # future months too

        metric = db.get(MetricDefinition, "dg_generation_kwh")
        assert metric is not None
        assert metric.operational_domain is OperationalDomain.TRANSPORT  # DG entry stays where it was
        assert (metric.canonical_unit, metric.min_value, metric.zero_allowed) == ("kWh", Decimal("0"), True)
        assert metric.manager_editable and metric.required_for_complete and metric.factor_code is None
        legacy = db.get(MetricDefinition, "dg_diesel_litres")
        assert legacy is not None and legacy.is_active and legacy.canonical_unit == "L"


# ---- Historical calculator (PostgreSQL) ---------------------------------------


def _unused_year(db: Session, first: int, last: int) -> int:
    """A year with no history period, factor set or population reference.

    Other suites leave population references for years they never give a
    history period (publication tests), so all three are checked: a year is
    only free when ``_store`` can insert its own population row.
    """
    for candidate in range(first, last):
        taken = (
            db.scalar(select(HistoricalPeriod.id).where(HistoricalPeriod.year == candidate))
            or db.scalar(
                
                select(EmissionFactorSet.id).where(
                    EmissionFactorSet.effective_from >= date(candidate, 1, 1),
                    EmissionFactorSet.effective_from <= date(candidate, 12, 31),
                )
            )
            or db.get(InstitutionalPopulationReference, candidate)
        )
        if not taken:
            return candidate
    raise RuntimeError("no free test year")


@pytest.fixture
def new_year(postgres_engine: Engine) -> int:
    """A year after the SFC effective date, with governed factors (kWh methodology)."""
    with Session(postgres_engine) as db:
        chosen = _free_year(db)
        _governed_factor_set(db, chosen)
        db.commit()
    return chosen


@pytest.fixture
def legacy_year(postgres_engine: Engine) -> int:
    """A year before the SFC effective date, with governed factors (litre methodology)."""
    with Session(postgres_engine) as db:
        # 2010-2024: before the SFC, after the years other tests keep factor-free,
        # and clear of the low-2000s reporting periods the API suites create first.
        chosen = _unused_year(db, 2010 + int(uuid4().int % 8), 2025)
        _governed_factor_set(db, chosen)
        db.commit()
    return chosen


def _period_of(year_: int, month: int) -> HistoricalPeriod:
    return HistoricalPeriod(
        id=uuid4(), year=year_, month=month, granularity="MONTHLY",
        coverage_start=date(year_, month, 1), coverage_end=date(year_, month, 28), display_label=f"{month}/{year_}",
    )


def _calculate(db: Session, year_: int, activity: dict[str, str]) -> dict[str, tuple[Any, ...]]:
    period = _period_of(year_, 5)
    values = {
        (METRICS[code][0], code): HistoricalMetricValue(
            id=uuid4(), period_id=period.id, domain=METRICS[code][0], metric_code=code,
            value_numeric=Decimal(value), unit=METRICS[code][1],
            verification_status="VERIFIED", authority_status="AUTHORITATIVE",
        )
        for code, value in activity.items()
    }
    calculator = PeriodCalculator(db, period, values=values, population=(Decimal(POPULATION), {"kind": "test"}))
    calculator.calculate()
    return calculator.results


def test_legacy_litres_calculate_exactly_as_before_without_kwh(postgres_engine: Engine, legacy_year: int) -> None:
    with Session(postgres_engine) as db:
        results = _calculate(db, legacy_year, {"dg_diesel_litres": "1588.62"})
        # 1588.62 L x 2.701 / 1000, the stored January 2025 result.
        assert results["dg_diesel_emissions"][0] == Decimal("4.290863")
        assert results["dg_diesel_emissions"][1] is None
        detail = results["dg_diesel_emissions"][3]
        assert "derivation" not in detail  # source-reported, nothing derived
        assert detail["activity"] == {"metric_code": "dg_diesel_litres", "unit": "L"}
        # Litres stay a source value: no derived-litres calculation is produced.
        assert "dg_diesel_litres" not in results
        assert results["scope1_tco2e"][0] == Decimal("4.290863")


def test_a_legacy_period_is_never_pushed_through_the_kwh_pathway(postgres_engine: Engine, legacy_year: int) -> None:
    with Session(postgres_engine) as db:
        # kWh alone before the SFC's effective date: nothing is derived or invented.
        only_kwh = _calculate(db, legacy_year, {"dg_generation_kwh": "9006"})
        assert "dg_diesel_emissions" not in only_kwh and "dg_diesel_litres" not in only_kwh
        # With source litres present, the litres are used and the kWh is ignored.
        both = _calculate(db, legacy_year, {"dg_generation_kwh": "9006", "dg_diesel_litres": "1000"})
        assert both["dg_diesel_emissions"][0] == Decimal("2.701000")
        assert "derivation" not in both["dg_diesel_emissions"][3]


@pytest.mark.parametrize(("kwh", "litres", "kgco2e", "tco2e"), OWNER_EXAMPLES)
def test_new_methodology_derives_litres_and_emissions(
    postgres_engine: Engine, new_year: int, kwh: str, litres: str, kgco2e: str, tco2e: str
) -> None:
    with Session(postgres_engine) as db:
        results = _calculate(db, new_year, {"dg_generation_kwh": kwh})
        derived, _, unit, detail = results["dg_diesel_litres"]
        assert derived == Decimal(litres) and unit == "L"
        assert results["dg_diesel_emissions"][0] == Decimal(tco2e)
        for code in ("dg_diesel_litres", "dg_diesel_emissions"):
            derivation = results[code][3]["derivation"]
            assert derivation["activity_origin"] == "DERIVED_FROM_KWH"
            assert derivation["source_metric_code"] == "dg_generation_kwh"
            assert Decimal(derivation["source_value"]) == Decimal(kwh)
            assert (derivation["parameter_code"], derivation["parameter_unit"]) == ("DG_SFC", "L/kWh")
            assert Decimal(derivation["parameter_value"]) == SFC
            assert derivation["parameter_effective_from"] == "2026-05-01"
            assert Decimal(derivation["derived_value"]) == Decimal(litres)
        factor = results["dg_diesel_emissions"][3]["factor"]
        assert (factor["code"], Decimal(factor["value"]), factor["unit"]) == ("DIESEL", DIESEL_FACTOR, "kgCO2e/L")
        assert detail["inputs"]["dg_generation_kwh"]["value"] == kwh


def test_zero_missing_and_double_counting(postgres_engine: Engine, new_year: int) -> None:
    with Session(postgres_engine) as db:
        zero = _calculate(db, new_year, {"dg_generation_kwh": "0"})
        assert zero["dg_diesel_litres"][0] == Decimal("0")
        assert zero["dg_diesel_emissions"][0] == Decimal("0")  # explicit zero is a valid result

        missing = _calculate(db, new_year, {"lpg_weight_kg": "100"})
        assert "dg_diesel_emissions" not in missing and "dg_diesel_litres" not in missing
        completeness = missing["scope1_tco2e"][3]["completeness"]
        assert "dg_diesel_emissions" in {item["code"] for item in completeness["missing_contributors"]}

        # Both a kWh source and a litre value: kWh is authoritative, litres are not added.
        both = _calculate(db, new_year, {"dg_generation_kwh": "9006", "dg_diesel_litres": "5000"})
        assert both["dg_diesel_litres"][0] == Decimal("2971.98")
        assert both["dg_diesel_emissions"][0] == Decimal("8.027318")
        assert both["scope1_tco2e"][0] == Decimal("8.027318")  # counted once
        assert both["dg_diesel_emissions"][3]["derivation"]["source_litres_not_used"] is True


def test_dg_feeds_scope1_operational_and_per_capita(postgres_engine: Engine, new_year: int) -> None:
    activity = {
        "dg_generation_kwh": "9006", "lpg_weight_kg": "782.8",
        "grid_ht_kwh": "43460", "grid_commercial_kwh": "1537", "grid_temporary_kwh": "318",
    }
    with Session(postgres_engine) as db:
        results = _calculate(db, new_year, activity)
    dg_emission = Decimal("8.027318")
    lpg = formulas.activity_emissions_tco2e(Decimal("782.8"), LPG_FACTOR)
    grid = formulas.activity_emissions_tco2e(Decimal("45315"), GRID_FACTOR)
    assert lpg is not None and grid is not None
    assert results["scope1_tco2e"][0] == dg_emission + lpg
    assert results["operational_ghg_tco2e"][0] == dg_emission + lpg + grid
    assert results["operational_ghg_per_capita_kgco2e"][0] == (dg_emission + lpg + grid) * 1000 / POPULATION
    scope1 = results["scope1_tco2e"][3]["completeness"]
    assert scope1["status"] == "PARTIAL"  # petrol and fleet diesel are still not reported
    assert {item["code"]: Decimal(item["value"]) for item in scope1["contributors"]} == {
        "dg_diesel_emissions": dg_emission, "lpg_emissions": lpg,
    }


# ---- Persistence, import and the public timeline ------------------------------


def _store(db: Session, year_: int, months: dict[int, dict[str, str]], *, population: bool = True) -> None:
    """Store verified monthly values and persist their calculations.

    ``population=False`` leaves the governed population table untouched: the
    legacy-year tests assert nothing per capita, and other suites insert their
    own population rows for early-2000s years.
    """
    batch = HistoricalImportBatch(
        id=uuid4(), batch_name=f"dg-kwh-test-{year_}", original_filename="synthetic.csv",
        source_reference="tests/synthetic.csv", source_sha256=hashlib.sha256(uuid4().bytes).hexdigest(),
        source_domain="transport", mapping_code=f"dg_kwh_test_{year_}", mapping_version=1, status="VERIFIED",
    )
    db.add(batch)
    if population:
        db.add(InstitutionalPopulationReference(
            effective_year=year_, population=POPULATION, unit="people", source_reference="DG kWh test population",
        ))
    db.flush()
    for month, activity in months.items():
        period = _period_of(year_, month)
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


def test_timeline_shows_source_kwh_and_derived_litres_with_provenance(postgres_engine: Engine, new_year: int) -> None:
    with Session(postgres_engine) as db:
        _store(db, new_year, {5: {"dg_generation_kwh": "9006"}, 6: {"dg_generation_kwh": "19890"}})
        db.commit()
        rows = {
            row.calculation_code: row
            for row in db.scalars(
                select(HistoricalCalculationResult)
                .join(HistoricalPeriod, HistoricalPeriod.id == HistoricalCalculationResult.period_id)
                .where(HistoricalPeriod.year == new_year, HistoricalPeriod.month == 5)
            ).all()
        }
        assert rows["dg_diesel_litres"].result_value == Decimal("2971.98")
        assert rows["dg_diesel_litres"].methodology_version == DG_KWH_METHODOLOGY_VERSION
        assert rows["dg_diesel_emissions"].methodology_version == DG_KWH_METHODOLOGY_VERSION
        assert rows["dg_diesel_emissions"].factor_code == "DIESEL"
        # The source kWh is stored as source data; litres exist only as a derived result.
        stored_metrics = set(db.scalars(
            select(HistoricalMetricValue.metric_code)
            .join(HistoricalPeriod, HistoricalPeriod.id == HistoricalMetricValue.period_id)
            .where(HistoricalPeriod.year == new_year)
        ).all())
        assert stored_metrics == {"dg_generation_kwh"}
        periods = build_timeline(db)["periods"]

    may = periods[f"{new_year}-05"]
    generation, litres, emissions = (
        may["values"][code] for code in ("dg_generation_kwh", "dg_diesel_litres", "dg_diesel_emissions")
    )
    assert (generation["value"], generation["unit"], generation["kind"]) == (9006, "kWh", "metric")
    assert generation["provenance"]["verification_status"] == "VERIFIED"
    assert (litres["value"], litres["unit"], litres["kind"]) == (2971.98, "L", "calculation")
    assert litres["activity_origin"] == "DERIVED_FROM_KWH"
    assert litres["provenance"]["derivation"]["parameter_code"] == "DG_SFC"
    assert litres["provenance"]["derivation"]["parameter_value"] == "0.33"
    assert emissions["value"] == 8.027318 and emissions["activity_origin"] == "DERIVED_FROM_KWH"
    assert emissions["provenance"]["factor_value"] == "2.7010000000"
    assert may["values"]["scope1_tco2e"]["value"] == 8.027318
    for code in ("dg_generation_kwh", "dg_diesel_litres", "dg_diesel_emissions"):
        assert may["display"][code]["value"] == may["values"][code]["value"]
    assert may["display"]["dg_diesel_litres"]["activity_origin"] == "DERIVED_FROM_KWH"
    ytd = periods[f"{new_year}-YTD"]["values"]
    assert ytd["dg_generation_kwh"]["value"] == 9006 + 19890
    assert ytd["dg_diesel_litres"]["value"] == pytest.approx(2971.98 + 6563.70)
    assert ytd["dg_diesel_litres"]["activity_origin"] == "DERIVED_FROM_KWH"


def test_timeline_keeps_legacy_litres_source_reported_with_no_invented_kwh(
    postgres_engine: Engine, legacy_year: int
) -> None:
    with Session(postgres_engine) as db:
        _store(db, legacy_year, {1: {"dg_diesel_litres": "1588.62"}}, population=False)
        db.commit()
        rows = db.scalars(
            select(HistoricalCalculationResult)
            .join(HistoricalPeriod, HistoricalPeriod.id == HistoricalCalculationResult.period_id)
            .where(HistoricalPeriod.year == legacy_year)
        ).all()
        by_code = {row.calculation_code: row for row in rows}
        assert "dg_diesel_litres" not in by_code  # nothing derived for a legacy period
        assert by_code["dg_diesel_emissions"].methodology_version == METHODOLOGY_VERSION  # unchanged
        assert "derivation" not in by_code["dg_diesel_emissions"].provenance
        january = build_timeline(db)["periods"][f"{legacy_year}-01"]["values"]
    assert "dg_generation_kwh" not in january
    assert (january["dg_diesel_litres"]["value"], january["dg_diesel_litres"]["kind"]) == (1588.62, "metric")
    assert january["dg_diesel_litres"]["activity_origin"] == "SOURCE_REPORTED_LITRES"
    assert january["dg_diesel_emissions"]["value"] == 4.290863
    assert january["dg_diesel_emissions"]["activity_origin"] == "SOURCE_REPORTED_LITRES"


def test_kwh_source_imports_through_the_governed_importer(
    postgres_engine: Engine, tmp_path: Path, year: int  # noqa: F811
) -> None:
    """A kWh source file goes through the same governed import as every other
    source: only the kWh is stored, and litres/emissions are backend results."""
    mapping = _mapping("dg_staging", uuid4().hex[:8])
    mapping["description"] = "Synthetic DG generation source (kWh)."
    mapping["options"] = {
        "year_column": "year", "month_column": "month",
        "category_column": "activity", "value_column": "generation_kwh",
    }
    mapping["categories"] = {"generation": {"metric_code": "dg_generation_kwh", "unit": "kWh"}}
    _write(
        tmp_path,
        mapping,
        f"year,month,activity,generation_kwh\n{year},May,generation,9006\n{year},Jun,generation,19890\n"
        f"{year},Jul,generation,6126\n{year},Aug,generation,0\n",
    )
    _import(postgres_engine, tmp_path, [mapping])
    periods = _timeline(postgres_engine)["periods"]
    expected = {"05": ("9006", "2971.98"), "06": ("19890", "6563.70"), "07": ("6126", "2021.58"), "08": ("0", "0")}
    for month, (kwh, litres) in expected.items():
        values = periods[f"{year}-{month}"]["values"]
        assert values["dg_generation_kwh"]["value"] == float(kwh)
        assert values["dg_diesel_litres"]["value"] == float(litres)
        assert values["dg_diesel_litres"]["activity_origin"] == "DERIVED_FROM_KWH"
        emission = formulas.activity_emissions_tco2e(Decimal(litres), HISTORICAL_TEST_DIESEL)
        assert emission is not None
        assert values["dg_diesel_emissions"]["value"] == pytest.approx(float(emission))
    with Session(postgres_engine) as db:
        imported = set(db.scalars(
            select(HistoricalMetricValue.metric_code)
            .join(HistoricalPeriod, HistoricalPeriod.id == HistoricalMetricValue.period_id)
            .where(HistoricalPeriod.year == year)
        ).all())
    assert imported == {"dg_generation_kwh"}  # no litres or emissions were inserted as source data


def test_a_window_spanning_the_change_is_labelled_mixed(postgres_engine: Engine) -> None:
    """Litre months and kWh months in one year (the 2026 shape): the year-to-date
    litres are summed as litres but labelled MIXED, and no kWh is invented for
    the litre months."""

    def month(number: int, values: dict[str, tuple[str, str, str, str | None]]) -> Entry:
        entry = Entry(
            f"2026-{number:02d}", f"month {number}", 2026, number, "MONTHLY",
            date(2026, number, 1), date(2026, number, 28), "historical_verified",
        )
        for code, (kind, amount, unit, origin) in values.items():
            entry.values[code] = Value(code, "transport", kind, Decimal(amount), unit, activity_origin=origin)
        return entry

    april = month(4, {"dg_diesel_litres": ("metric", "2136.83", "L", "SOURCE_REPORTED_LITRES")})
    may = month(5, {
        "dg_generation_kwh": ("metric", "9006", "kWh", None),
        "dg_diesel_litres": ("calculation", "2971.98", "L", "DERIVED_FROM_KWH"),
    })
    with Session(postgres_engine) as db:
        ytd = _aggregates(db, 2026, [april, may], [])[0]
    litres = ytd.values["dg_diesel_litres"]
    assert litres.value == Decimal("5108.81") and litres.activity_origin == "MIXED"
    generation = ytd.values["dg_generation_kwh"]
    assert generation.value == Decimal("9006")  # only the kWh month; April gains none
    assert generation.months_covered == ["2026-05"]
    assert "dg_generation_kwh" not in april.values


# ---- Manager -> Admin -> calculation (API) ------------------------------------


def _factor_set_from(db: Session, start: date) -> None:
    item = EmissionFactorSet(
        id=uuid4(), version=f"dg-kwh-api-{start.isoformat()}-{uuid4().hex[:6]}", status=FactorSetStatus.ACTIVE,
        source_note="Synthetic DG kWh workflow factors", effective_from=start, activated_at=datetime.now(UTC),
    )
    db.add(item)
    db.flush()
    for code, value, unit in (("PETROL", "2.388", "L"), ("DIESEL", "2.701", "L"), ("GRID_ELECTRICITY", "0.727", "kWh")):
        db.add(EmissionFactor(
            factor_set_id=item.id, code=code, factor_value=Decimal(value), activity_unit=unit,
            result_unit="kgCO2e", source_reference="Synthetic test factor",
        ))
    db.flush()


def _dg(calculations: list[dict[str, Any]]) -> dict[str, Any]:
    return next(item for item in calculations if item["calculation_code"] == "dg_diesel_emissions")


def test_manager_enters_kwh_admin_approves_and_backend_derives(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2171)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    with Session(postgres_engine) as db:
        _factor_set_from(db, period.period_start)
        db.commit()
    values = _values(postgres_engine, OperationalDomain.TRANSPORT, period=period)
    assert "dg_generation_kwh" in {item["metric_code"] for item in values}
    assert "dg_diesel_litres" not in {item["metric_code"] for item in values}
    for item in values:
        if item["metric_code"] == "dg_generation_kwh":
            item["value"] = "9006"

    def with_metric(code: str, value: str) -> list[dict[str, object]]:
        return [*values, {"metric_code": code, "value": value, "quality_note": None}]

    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        headers = {"X-CSRF-Token": csrf}
        base = {"reporting_period_id": str(period.id), "remarks": None}

        # The Manager is offered kWh, not litres, for the current month.
        offered = {item["code"] for item in client.get("/api/manager/transport/metrics").json()}
        assert "dg_generation_kwh" in offered and "dg_diesel_litres" not in offered

        # Litres are derived in the new workflow: a client-supplied value is refused,
        # and so is any attempt to write a calculated result.
        refused = client.post(
            "/api/manager/transport/submissions",
            json={**base, "values": with_metric("dg_diesel_litres", "2971.98")}, headers=headers,
        )
        assert refused.status_code == 422 and "dg_generation_kwh" in refused.text
        assert client.post(
            "/api/manager/transport/submissions",
            json={**base, "values": with_metric("dg_diesel_emissions", "8.027318")}, headers=headers,
        ).status_code == 422
        negative = [dict(item) for item in values]
        for item in negative:
            if item["metric_code"] == "dg_generation_kwh":
                item["value"] = "-1"
        assert client.post(
            "/api/manager/transport/submissions", json={**base, "values": negative}, headers=headers
        ).status_code == 422

        # Save Draft without the kWh: saved, but it cannot be submitted (missing is not zero).
        without = [item for item in values if item["metric_code"] != "dg_generation_kwh"]
        created = client.post("/api/manager/transport/submissions", json={**base, "values": without}, headers=headers)
        assert created.status_code == 201, created.text
        submission_id = created.json()["id"]
        blocked = client.post(f"/api/manager/transport/submissions/{submission_id}/submit", headers=headers)
        assert blocked.status_code == 422
        assert "dg_generation_kwh" in blocked.text and "dg_diesel_litres" not in blocked.text

        # Save Draft with 9006 kWh: the backend returns the read-only derivation preview.
        saved = client.put(
            f"/api/manager/transport/submissions/{submission_id}",
            json={"remarks": None, "values": values, "expected_row_version": created.json()["row_version"]},
            headers=headers,
        )
        assert saved.status_code == 200, saved.text
        draft = _dg(saved.json()["calculations"])
        assert draft["provisional"] is True and draft["status"] == "available"
        assert (draft["activity_metric_code"], Decimal(draft["activity_value"]), draft["activity_unit"]) == (
            "dg_generation_kwh", Decimal("9006"), "kWh",
        )
        assert draft["derivation"]["derived_value"] == "2971.98"
        assert draft["derivation"]["parameter_value"] == "0.33"
        assert Decimal(draft["result_value"]) == Decimal("8.027318")
        assert Decimal(draft["result_kgco2e"]) == Decimal("8027.317980")
        assert (draft["factor_code"], Decimal(draft["factor_value"]), draft["factor_unit"]) == (
            "DIESEL", DIESEL_FACTOR, "kgCO2e/L",
        )
        # Only source activity was stored; no litres, no emissions.
        assert "dg_diesel_litres" not in {item["metric_code"] for item in saved.json()["values"]}

        assert client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit", headers=headers
        ).status_code == 200

    with _client(postgres_engine) as admin_client:
        admin_headers = {"X-CSRF-Token": _login(admin_client, admin)}
        detail = admin_client.get(f"/api/admin/submissions/{submission_id}").json()
        entered = {item["metric_code"]: item for item in detail["values"]}
        assert Decimal(entered["dg_generation_kwh"]["value"]) == Decimal("9006")
        assert entered["dg_generation_kwh"]["canonical_unit"] == "kWh"
        review = _dg(detail["calculations"])
        assert review["provisional"] is False  # frozen at submit
        assert review["derivation"]["derived_value"] == "2971.98"
        assert Decimal(review["result_value"]) == Decimal("8.027318")
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/begin-review", headers=admin_headers
        ).status_code == 200
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/approve", headers=admin_headers
        ).status_code == 200
        approved = admin_client.get(f"/api/admin/submissions/{submission_id}").json()
        assert approved["status"] == "approved"
        assert _dg(approved["calculations"])["derivation"]["source_value"] == "9006"

    with Session(postgres_engine) as db:
        frozen = db.scalar(select(CalculationResult).where(
            CalculationResult.submission_id == submission_id,
            CalculationResult.calculation_code == "dg_diesel_emissions",
        ))
        assert frozen is not None
        assert frozen.metric_code == "dg_generation_kwh" and frozen.activity_unit == "kWh"
        assert frozen.result_value == Decimal("8.027318") and frozen.factor_code == "DIESEL"
        assert frozen.derivation is not None
        assert frozen.derivation["activity_origin"] == "DERIVED_FROM_KWH"
        assert frozen.derivation["parameter_code"] == "DG_SFC"
        assert frozen.derivation["derived_value"] == "2971.98"
        # The published calculation keeps the derivation for a future release.
        published = _public_calculation(
            CalculationResponse(
                status="available", calculation_code="dg_diesel_emissions",
                activity_metric_code=frozen.metric_code, derivation=frozen.derivation,
            )
        )
        assert published["derivation"]["derived_value"] == "2971.98"  # type: ignore[index]


def test_legacy_period_still_takes_litres_through_the_manager_api(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2003, 2)
    assert period.period_start < EFFECTIVE
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    with Session(postgres_engine) as db:
        _factor_set_from(db, period.period_start)
        db.commit()
    values = _values(postgres_engine, OperationalDomain.TRANSPORT, period=period)
    assert "dg_diesel_litres" in {item["metric_code"] for item in values}
    for item in values:
        if item["metric_code"] == "dg_diesel_litres":
            item["value"] = "1000"
    with _client(postgres_engine, period) as client:
        headers = {"X-CSRF-Token": _login(client, manager)}
        base = {"reporting_period_id": str(period.id), "remarks": None}
        offered = {item["code"] for item in client.get("/api/manager/transport/metrics").json()}
        assert "dg_diesel_litres" in offered and "dg_generation_kwh" not in offered
        kwh = [*values, {"metric_code": "dg_generation_kwh", "value": "9006", "quality_note": None}]
        assert client.post(
            "/api/manager/transport/submissions", json={**base, "values": kwh}, headers=headers
        ).status_code == 422
        created = client.post("/api/manager/transport/submissions", json={**base, "values": values}, headers=headers)
        assert created.status_code == 201, created.text
        legacy = _dg(created.json()["calculations"])
        assert legacy["activity_metric_code"] == "dg_diesel_litres"
        assert Decimal(legacy["result_value"]) == Decimal("2.701000")
        assert legacy["derivation"] is None


def test_litre_based_published_calculations_keep_their_exact_shape() -> None:
    published = _public_calculation(
        CalculationResponse(
            status="available", calculation_code="dg_diesel_emissions", activity_metric_code="dg_diesel_litres",
            activity_value=Decimal("300"), activity_unit="L",
        )
    )
    assert "derivation" not in published  # an older or litre-based payload gains no key


def test_migration_adds_the_parameter_table_and_the_derivation_column(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as connection:
        columns = connection.execute(text(
            "select column_name from information_schema.columns "
            "where table_schema = 'sustainability' and table_name = 'calculation_results'"
        )).scalars().all()
        assert "derivation" in columns
        tables = connection.execute(text(
            "select count(*) from information_schema.tables "
            "where table_schema = 'sustainability' and table_name = 'calculation_parameters'"
        )).scalar_one()
        assert tables == 1
