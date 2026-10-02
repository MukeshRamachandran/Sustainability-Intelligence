"""LPG kg methodology (0013_lpg_kg_governance_v2).

Project-owner correction of 2026-09-30: LPG activity is weight in kg,
governed by the LPG_KG factor (2.98 kgCO2e/kg). Historical values that were
normalized as litres are the same numbers in kg - they are reinterpreted,
never converted. Integration tests use synthetic far-future years and their
own active factor set, so they never touch real institutional data.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.historical import importer
from app.historical.calculator import ACTIVITY_EMISSIONS, DOMAIN_OF_INPUT, PeriodCalculator
from app.historical.sources import parse_source
from app.historical.validator import LoadedSource, reconcile
from app.models.enums import FactorSetStatus, ReleaseStatus, RoleCode
from app.models.history import (
    HistoricalCalculationResult,
    HistoricalConflict,
    HistoricalMetricValue,
    HistoricalPeriod,
)
from app.models.publication import PublicRelease, PublicReleaseMetadata, PublicReleasePayload
from app.models.sustainability import EmissionFactor, EmissionFactorSet
from app.services import sustainability_formulas as formulas
from app.services.emission_factors import CALCULATION_CODES, EXPECTED_UNITS
from app.services.publication import RELEASE_SCHEMA_VERSION, lpg_payload_blockers, payload_checksum
from tests.test_historical_integration import _energy_csv, _free_year, _mapping, _timeline, _value, _write
from tests.test_publication_integration import _account


def _repo_root() -> Path | None:
    """The repository checkout holding the institutional source files.

    Inside the API container only services/main-api is present; mount the
    checkout and set KCOSMOS_REPO_ROOT to run the source-file tests there.
    """
    configured = os.getenv("KCOSMOS_REPO_ROOT")
    parents = Path(__file__).resolve().parents
    candidate = Path(configured) if configured else (parents[3] if len(parents) > 3 else None)
    return candidate if candidate is not None and (candidate / "apps").is_dir() else None


REPO_ROOT = _repo_root()
needs_sources = pytest.mark.skipif(REPO_ROOT is None, reason="repository source files are not available")
APP_ROOT = Path(__file__).resolve().parents[1] / "app"
LPG_FACTOR = Decimal("2.98")
# Owner-supplied Jan-Jul 2026: (month, kg, source-reported tCO2e).
OWNER_2026 = (
    (1, "7429", "22.13842"),
    (2, "9082", "27.06436"),
    (3, "769.5", "2.29311"),
    (4, "798", "2.37804"),
    (5, "782.8", "2.332744"),
    (6, "769.5", "2.29311"),
    (7, "1453.5", "4.33143"),
)
UNIT_CORRECTION = {
    "id": "synthetic-lpg-litres-are-kg",
    "from_mapping_version": 1,
    "to_mapping_version": 2,
    "domain": "lpg",
    "from_metric_code": "lpg_consumption_litres",
    "from_unit": "L",
    "to_metric_code": "lpg_weight_kg",
    "to_unit": "kg",
    "numeric_values_unchanged": True,
    "reason": "Synthetic test: source LPG values are kilograms; numbers unchanged.",
    "approved_by": "Project owner",
    "approved_at": "2026-09-30",
}


# ---- Pure methodology (no database) -----------------------------------------


def test_owner_2026_values_use_decimal_kg_times_factor() -> None:
    total_kg, total_t = Decimal("0"), Decimal("0")
    for _, kg, reported in OWNER_2026:
        result = formulas.activity_emissions_tco2e(Decimal(kg), LPG_FACTOR)
        assert result == Decimal(reported)
        total_kg += Decimal(kg)
        assert result is not None
        total_t += result
    assert total_kg == Decimal("21084.3")
    assert total_t == Decimal("62.831214")
    assert formulas.activity_emissions_tco2e(total_kg, LPG_FACTOR) == Decimal("62.831214")


def test_active_calculators_use_weight_and_the_lpg_kg_factor() -> None:
    assert ("lpg_emissions", "lpg_weight_kg", "LPG_KG") in ACTIVITY_EMISSIONS
    assert "lpg_consumption_litres" not in DOMAIN_OF_INPUT
    assert CALCULATION_CODES["lpg_weight_kg"] == "lpg_emissions"
    assert "lpg_consumption_litres" not in CALCULATION_CODES
    assert EXPECTED_UNITS["LPG_KG"] == "kg"  # type: ignore[index]
    assert RELEASE_SCHEMA_VERSION == "1.5"


def test_no_active_code_hardcodes_a_factor_or_reads_the_litre_metric() -> None:
    litre_users, hardcoded = set(), set()
    for path in APP_ROOT.rglob("*"):
        if path.suffix not in {".py", ".json"}:
            continue
        body = path.read_text(encoding="utf-8")
        if "lpg_consumption_litres" in body:
            litre_users.add(path.relative_to(APP_ROOT).as_posix())
        if path.suffix == ".py" and ("1.5571" in body or "2.98" in body):
            hardcoded.add(path.relative_to(APP_ROOT).as_posix())
    # Only the release blocker (to refuse it), the owner-approved unit
    # correction and the reinterpreting mapping's description (to name what
    # they supersede) may mention the litre metric.
    assert litre_users == {
        "services/publication.py",
        "historical/mappings/resolutions.json",
        "historical/mappings/lpg_staging.json",
    }
    assert hardcoded == set()


def test_lpg_release_blockers_refuse_litre_era_payloads() -> None:
    kg_calc = {
        "calculation_code": "lpg_emissions", "status": "available", "activity_metric_code": "lpg_weight_kg",
        "activity_unit": "kg", "factor_code": "LPG_KG", "factor_unit": "kgCO2e/kg",
    }
    governed = {"lpg": {"metrics": {"lpg_weight_kg": {"value": 7429, "unit": "kg"}}, "calculations": [kg_calc]}}
    assert lpg_payload_blockers(governed) == []
    unavailable = {"lpg": {"metrics": {}, "calculations": [
        {"calculation_code": "lpg_emissions", "status": "unavailable", "activity_metric_code": "lpg_weight_kg"}
    ]}}
    assert lpg_payload_blockers(unavailable) == []
    assert lpg_payload_blockers({"lpg": None}) == []
    litre_metric = {"lpg": {"metrics": {"lpg_consumption_litres": {"value": 52, "unit": "L"}}, "calculations": []}}
    assert [item["reason"] for item in lpg_payload_blockers(litre_metric)] == ["lpg_litre_metric_superseded_by_kg"]
    litre_calc = {"lpg": {"metrics": {}, "calculations": [
        {**kg_calc, "activity_metric_code": "lpg_consumption_litres", "activity_unit": "L", "factor_unit": "kgCO2e/L"}
    ]}}
    assert [item["reason"] for item in lpg_payload_blockers(litre_calc)] == ["lpg_activity_is_not_governed_kg"]
    litre_factor = {"lpg": {"metrics": {}, "calculations": [{**kg_calc, "factor_unit": "kgCO2e/L"}]}}
    assert [item["reason"] for item in lpg_payload_blockers(litre_factor)] == ["lpg_factor_is_not_governed_kg"]


def _real_mapping(name: str) -> dict[str, Any]:
    return json.loads((importer.MAPPING_DIR / f"{name}.json").read_text(encoding="utf-8"))


@needs_sources
def test_2025_mapping_reinterprets_the_same_numbers_as_kg() -> None:
    assert REPO_ROOT is not None
    mapping = _real_mapping("lpg_staging")
    assert mapping["version"] == 2
    assert mapping["reinterprets"] == {"unit_correction": "lpg-2025-source-values-are-kg"}
    content = (REPO_ROOT / mapping["source_reference"]).read_bytes()
    # The imported evidence bytes are untouched (lpg_staging v1 sha256).
    assert importer.sha256_bytes(content) == "5c7aedb0f10622a831064b61ae50163d92c421b93baf7b3b04b823bb0935efcb"
    parsed = parse_source(content, mapping)
    assert {(item.metric_code, item.unit) for item in parsed.observations} == {("lpg_weight_kg", "kg")}
    raw = {
        (int(row[0]), row[1]): Decimal(row[2].replace(",", ""))
        for row in parsed.rows[1:]
        if row and row[0].strip().isdigit()
    }
    # No litre -> kg conversion: every value equals the raw source number.
    for item in parsed.observations:
        from calendar import month_abbr

        assert item.value == raw[(item.period.year, month_abbr[item.period.month or 0])]
    assert sum(item.value for item in parsed.observations) == Decimal("102087")
    entry = next(
        item for item in importer.load_unit_corrections() if item["id"] == "lpg-2025-source-values-are-kg"
    )
    assert (entry["from_metric_code"], entry["from_unit"]) == ("lpg_consumption_litres", "L")
    assert (entry["to_metric_code"], entry["to_unit"]) == ("lpg_weight_kg", "kg")
    assert entry["numeric_values_unchanged"] is True
    assert entry["approved_by"] == "Project owner" and entry["approved_at"] == "2026-09-30"


@needs_sources
def test_2026_source_parses_kg_as_governed_and_keeps_stock_discrepancy_as_a_note() -> None:
    assert REPO_ROOT is not None
    mapping = _real_mapping("lpg_2026_owner_source")
    content = (REPO_ROOT / mapping["source_reference"]).read_bytes()
    parsed = parse_source(content, mapping)
    kg = {item.period.month: item for item in parsed.observations if item.metric_code == "lpg_weight_kg"}
    assert {month: item.value for month, item in kg.items()} == {
        month: Decimal(value) for month, value, _ in OWNER_2026
    }
    assert all(item.period.year == 2026 and item.period.granularity == "MONTHLY" for item in kg.values())
    # cylinders x 19 kg reproduces KG every month; the Feb stock arithmetic
    # (11 + 489 - 21 = 479) disagrees with the stated 478 and is advisory only.
    failed = [check for check in parsed.checks if not check.passed]
    assert len(failed) == 1 and failed[0].advisory
    assert (failed[0].expected, failed[0].actual) == (Decimal("478"), Decimal("479"))
    plan = reconcile([LoadedSource(mapping, parsed, "0" * 64, "lpg_2026_jan_jul.csv")], [])
    assert plan.conflicts == []
    by_metric: dict[str, list[Any]] = {}
    for value in plan.values:
        by_metric.setdefault(value.observation.metric_code, []).append(value)
    assert {(v.verification_status, v.authority_status) for v in by_metric["lpg_weight_kg"]} == {
        ("VERIFIED", "AUTHORITATIVE")
    }
    for reference in ("lpg_cylinder_count", "lpg_emissions_source_reported"):
        assert {v.authority_status for v in by_metric[reference]} == {"SOURCE_REPORTED"}
    february = next(v for v in by_metric["lpg_weight_kg"] if v.observation.period.month == 2)
    assert february.observation.value == Decimal("9082")
    assert any("source states 478, arithmetic gives 479" in note for note in february.notes)


# ---- Integration (PostgreSQL) -----------------------------------------------


def _governed_factor_set(db: Session, year: int) -> None:
    item = EmissionFactorSet(
        id=uuid4(),
        version=f"lpg-kg-test-{year}-{uuid4().hex[:6]}",
        status=FactorSetStatus.ACTIVE,
        source_note="Synthetic LPG kg methodology test factors",
        effective_from=date(year, 1, 1),
        activated_at=datetime.now(UTC),
    )
    db.add(item)
    db.flush()
    for code, value, unit in (
        ("PETROL", Decimal("2.388"), "L"),
        ("DIESEL", Decimal("2.701"), "L"),
        ("GRID_ELECTRICITY", Decimal("0.727"), "kWh"),
        ("LPG_KG", LPG_FACTOR, "kg"),
    ):
        db.add(
            EmissionFactor(
                factor_set_id=item.id, code=code, factor_value=value, activity_unit=unit,
                result_unit="kgCO2e", source_reference="Synthetic test factor",
            )
        )
    db.flush()


@pytest.fixture
def kg_year(postgres_engine: Engine) -> int:
    with Session(postgres_engine) as db:
        chosen = _free_year(db)
        _governed_factor_set(db, chosen)
        db.commit()
    return chosen


def _run(engine: Engine, root: Path, mappings: list[dict[str, Any]], corrections: list[dict[str, Any]]):
    sources = importer.load_sources(root, mappings)
    plan = importer.reconcile(sources, [])
    with Session(engine) as db:
        summary = importer.run(db, sources, plan, commit=True, unit_corrections=corrections)
        db.commit()
    return summary


def _litre_era_mappings(suffix: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    v2 = _mapping("lpg_staging", suffix)
    v1 = {
        **v2,
        "version": 1,
        "categories": {"_": {"metric_code": "lpg_consumption_litres", "unit": "L"}},
    }
    v1.pop("reinterprets")
    v2["reinterprets"] = {"unit_correction": f"{UNIT_CORRECTION['id']}-{suffix}"}
    correction = {**UNIT_CORRECTION, "id": f"{UNIT_CORRECTION['id']}-{suffix}", "mapping_code": v2["code"]}
    return v1, v2, correction


def test_2025_style_correction_supersedes_litres_with_kg_append_only(
    postgres_engine: Engine, tmp_path: Path, kg_year: int
) -> None:
    suffix = uuid4().hex[:8]
    v1, v2, correction = _litre_era_mappings(suffix)
    source = f'year,month,consumption_litre,,,,\n{kg_year},Jan,"8,778",,,,\n{kg_year},Feb,"8,816",,,,\n'
    _write(tmp_path, v1, source)
    _run(postgres_engine, tmp_path, [v1], [])
    with Session(postgres_engine) as db:
        litres = db.scalars(
            select(HistoricalMetricValue).join(HistoricalPeriod)
            .where(HistoricalPeriod.year == kg_year, HistoricalMetricValue.metric_code == "lpg_consumption_litres")
        ).all()
        assert sorted(row.value_numeric for row in litres) == [Decimal("8778"), Decimal("8816")]
        litre_ids = {row.id for row in litres}

    # No owner approval -> refused, nothing written.
    with pytest.raises(importer.ImportRefused, match="no owner-approved"):
        _run(postgres_engine, tmp_path, [v2], [])
    # A changed file is refused: a reinterpretation never pretends the source changed.
    _write(tmp_path, v2, source.replace("8,816", "8,817"))
    with pytest.raises(importer.ImportRefused, match="file changed"):
        _run(postgres_engine, tmp_path, [v2], [correction])
    _write(tmp_path, v2, source)

    summary = _run(postgres_engine, tmp_path, [v2], [correction])
    assert [item["to"] for item in summary.reinterpreted] == ["lpg_weight_kg 8778 kg", "lpg_weight_kg 8816 kg"]
    again = _run(postgres_engine, tmp_path, [v2], [correction])
    assert (again.new_batches, again.inserted_values, again.inserted_conflicts, again.inserted_calculations) == (
        0, 0, 0, 0,
    )
    assert again.unchanged_values == 2

    with Session(postgres_engine) as db:
        kg_rows = db.scalars(
            select(HistoricalMetricValue).join(HistoricalPeriod)
            .where(HistoricalPeriod.year == kg_year, HistoricalMetricValue.metric_code == "lpg_weight_kg")
        ).all()
        assert len(kg_rows) == 2
        assert {row.supersedes_id for row in kg_rows} == litre_ids
        assert all(row.unit == "kg" and row.version == 2 for row in kg_rows)
        assert sorted(row.value_numeric for row in kg_rows) == [Decimal("8778"), Decimal("8816")]
        # The old litre interpretation is retained, unchanged, for audit.
        retained = db.scalars(select(HistoricalMetricValue).where(HistoricalMetricValue.id.in_(litre_ids))).all()
        assert {(row.metric_code, row.unit) for row in retained} == {("lpg_consumption_litres", "L")}
        conflicts = db.scalars(
            select(HistoricalConflict).where(
                HistoricalConflict.conflict_type == "unit_reinterpretation",
                HistoricalConflict.period_id.in_([row.period_id for row in kg_rows]),
            )
        ).all()
        assert len(conflicts) == 2
        assert all(item.resolution_status == "RESOLVED" and "Project owner" in (item.resolution_reason or "")
                   for item in conflicts)
        calc = db.scalar(
            select(HistoricalCalculationResult).join(HistoricalPeriod).where(
                HistoricalPeriod.year == kg_year, HistoricalPeriod.month == 1,
                HistoricalCalculationResult.calculation_code == "lpg_emissions",
                HistoricalCalculationResult.is_current.is_(True),
            )
        )
        assert calc is not None
        assert calc.result_value == Decimal("26.158440")  # 8778 kg x 2.98 / 1000
        assert (calc.factor_code, calc.factor_value, calc.factor_unit) == ("LPG_KG", Decimal("2.98"), "kgCO2e/kg")
        assert calc.provenance["activity"] == {"metric_code": "lpg_weight_kg", "unit": "kg"}
        assert set(calc.input_snapshot) == {"lpg_weight_kg"}

    timeline = _timeline(postgres_engine)
    january = timeline["periods"][f"{kg_year}-01"]["values"]
    assert january["lpg_weight_kg"]["value"] == 8778 and january["lpg_weight_kg"]["unit"] == "kg"
    assert "lpg_consumption_litres" not in january
    assert _value(timeline, f"{kg_year}-01", "lpg_emissions") == 26.15844


def _values_for(period: HistoricalPeriod, **metrics: tuple[str, str, str]) -> dict[tuple[str, str], Any]:
    return {
        (domain, code): HistoricalMetricValue(
            id=uuid4(), period_id=period.id, domain=domain, metric_code=code, value_numeric=Decimal(value),
            unit=unit, verification_status="VERIFIED", authority_status="AUTHORITATIVE",
        )
        for code, (domain, value, unit) in metrics.items()
    }


def test_scope1_operational_and_per_capita_consume_kg_lpg(postgres_engine: Engine, kg_year: int) -> None:
    with Session(postgres_engine) as db:
        period = HistoricalPeriod(
            id=uuid4(), year=kg_year, month=1, granularity="MONTHLY",
            coverage_start=date(kg_year, 1, 1), coverage_end=date(kg_year, 1, 31), display_label="Jan",
        )
        values = _values_for(
            period,
            transport_petrol_litres=("transport", "1000", "L"),
            transport_diesel_litres=("transport", "1000", "L"),
            dg_diesel_litres=("transport", "1000", "L"),
            lpg_weight_kg=("lpg", "7429", "kg"),
            grid_ht_kwh=("energy", "10000", "kWh"),
            grid_commercial_kwh=("energy", "0", "kWh"),
            grid_temporary_kwh=("energy", "0", "kWh"),
        )
        calculator = PeriodCalculator(db, period, values=values, population=(Decimal("6991"), {"kind": "test"}))
        calculator.calculate()
        result = {code: item[0] for code, item in calculator.results.items()}
        assert result["lpg_emissions"] == Decimal("22.138420")
        scope1 = Decimal("2.388") + Decimal("2.701") + Decimal("2.701") + Decimal("22.138420")
        assert result["scope1_tco2e"] == scope1
        assert result["operational_ghg_tco2e"] == scope1 + Decimal("7.27")
        assert result["operational_ghg_per_capita_kgco2e"] == (scope1 + Decimal("7.27")) * 1000 / 6991

        # A kg activity is never multiplied by a factor of another unit.
        mislabeled = _values_for(period, lpg_weight_kg=("lpg", "7429", "L"))
        guarded = PeriodCalculator(db, period, values=mislabeled, population=(None, {"kind": "test"}))
        guarded.calculate()
        assert guarded.results["lpg_emissions"][0] is None
        assert guarded.results["lpg_emissions"][1] == "incompatible_unit"
        assert "scope1_tco2e" not in guarded.results or guarded.results["scope1_tco2e"][0] is None
        db.rollback()


def _owner_2026_mapping(suffix: str, year: int) -> dict[str, Any]:
    mapping = _mapping("lpg_2026_owner_source", suffix)
    mapping["options"] = {**mapping["options"], "fixed_year": year}
    return mapping


@needs_sources
def test_owner_2026_import_matches_backend_and_never_moves_the_default(
    postgres_engine: Engine, tmp_path: Path, kg_year: int
) -> None:
    suffix = uuid4().hex[:8]
    mapping = _owner_2026_mapping(suffix, kg_year)
    assert REPO_ROOT is not None
    source = (REPO_ROOT / "database/historical-sources/lpg/lpg_2026_jan_jul.csv").read_text(encoding="utf-8")
    _write(tmp_path, mapping, source)
    # June also has energy, so it is an institution-wide month; Jan-May and
    # July are LPG-only.
    energy = _mapping("energy_staging", suffix)
    _write(tmp_path, energy, _energy_csv(kg_year, [("June", "1", "2", "3", "4", "5", "6")]))
    summary = _run(postgres_engine, tmp_path, [mapping, energy], [])
    assert [item["status"] for item in summary.comparisons] == ["match"] * 7
    again = _run(postgres_engine, tmp_path, [mapping, energy], [])
    assert (again.new_batches, again.inserted_values, again.inserted_calculations) == (0, 0, 0)

    timeline = _timeline(postgres_engine)
    for month, kg, tonnes in OWNER_2026:
        key = f"{kg_year}-{month:02d}"
        values = timeline["periods"][key]["values"]
        assert values["lpg_weight_kg"]["unit"] == "kg"
        assert Decimal(str(values["lpg_weight_kg"]["value"])) == Decimal(kg)
        assert Decimal(str(values["lpg_emissions"]["value"])) == Decimal(tonnes)
        assert values["lpg_emissions"]["provenance"]["factor_code"] == "LPG_KG"
        # Reference-only source columns are never public or calculated.
        assert "lpg_cylinder_count" not in values
        assert "lpg_emissions_source_reported" not in values
    ytd = timeline["periods"][f"{kg_year}-YTD"]["values"]
    assert Decimal(str(ytd["lpg_weight_kg"]["value"])) == Decimal("21084.3")
    assert ytd["lpg_weight_kg"]["months_covered"] == [f"{kg_year}-{m:02d}" for m in range(1, 8)]
    assert Decimal(str(ytd["lpg_emissions"]["value"])) == Decimal("62.831214")
    # An LPG-only month is never the institution-wide default (July here).
    lpg_only = {f"{kg_year}-{month:02d}" for month in (1, 2, 3, 4, 5, 7)}
    assert timeline["default_key"] not in lpg_only
    assert timeline["periods"][f"{kg_year}-07"]["domains"]["lpg"]["state"] == "available"


def test_source_reported_emission_that_disagrees_is_a_conflict(
    postgres_engine: Engine, tmp_path: Path, kg_year: int
) -> None:
    suffix = uuid4().hex[:8]
    mapping = _owner_2026_mapping(suffix, kg_year + 1)
    header = (
        "MONTH,OPENING STOCK,PURCHASE,CLOSING STOCK,BRAND,NO OF CYLINDER USED,CYLINDER SIZE KG,KG,"
        "EMISSION FACTOR,EMISSIONS TCO2E\n"
    )
    _write(tmp_path, mapping, header + "JAN,,,,,391,19,7429,2.98,22.2\n")
    summary = _run(postgres_engine, tmp_path, [mapping], [])
    assert summary.comparisons[0]["status"] == "CONFLICT"
    with Session(postgres_engine) as db:
        conflict = db.scalar(
            select(HistoricalConflict).where(
                HistoricalConflict.conflict_type == "source_reported_vs_calculated",
                HistoricalConflict.conflict_key.contains(mapping["code"]),
            )
        )
        assert conflict is not None and conflict.resolution_status == "UNRESOLVED"
        assert (conflict.value_a, conflict.value_b) == (Decimal("22.200000"), Decimal("22.138420"))
    # The backend result stays authoritative; the source figure is never published.
    assert _value(_timeline(postgres_engine), f"{kg_year + 1}-01", "lpg_emissions") == 22.13842


def test_frozen_litre_era_release_stays_readable_and_is_never_rewritten(postgres_engine: Engine) -> None:
    payload = {
        "schema_version": "1.4",
        "period": {"id": str(uuid4()), "year": 2299, "month": 1},
        "lpg": {
            "metrics": {"lpg_consumption_litres": {"value": 52, "unit": "L"}},
            "calculations": [{
                "calculation_code": "lpg_emissions", "status": "available",
                "activity_metric_code": "lpg_consumption_litres", "activity_unit": "L",
                "factor_code": "LPG", "factor_value": 1.5571, "factor_unit": "kgCO2e/L", "result_value": 0.080969,
            }],
        },
    }
    checksum = payload_checksum(payload)
    with Session(postgres_engine) as db:
        admin = _account(db, RoleCode.ADMIN)
        release = PublicRelease(
            id=uuid4(), version=f"frozen-litre-{uuid4().hex[:8]}", status=ReleaseStatus.SUPERSEDED,
            checksum_sha256=checksum, prepared_by=admin.id, published_by=admin.id, published_at=datetime.now(UTC),
        )
        db.add(release)
        db.flush()
        db.add(PublicReleasePayload(release_id=release.id, payload=payload))
        db.add(PublicReleaseMetadata(
            release_id=release.id, classification="test", public_visible=False, reason="Synthetic frozen 1.4",
        ))
        db.commit()
        release_id = release.id
    _timeline(postgres_engine)
    with Session(postgres_engine) as db:
        stored = db.get(PublicReleasePayload, release_id)
        assert stored is not None and stored.payload == payload
        assert payload_checksum(stored.payload) == checksum
        # Readable as-is, but it could never be published again under 1.5.
        assert stored.payload["lpg"]["metrics"]["lpg_consumption_litres"]["value"] == 52
        assert lpg_payload_blockers(stored.payload)
