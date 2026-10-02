"""Historical data layer: granularity, reconciliation, provenance, resolver.

Every test uses synthetic source files in a free far-future year and its own
active factor set, so it never touches real institutional data.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.historical import importer
from app.historical.resolver import build_timeline
from app.historical.sources import parse_source
from app.historical.validator import LoadedSource, reconcile
from app.models.enums import FactorSetStatus, ReleaseStatus, RoleCode
from app.models.history import (
    HistoricalCalculationResult,
    HistoricalConflict,
    HistoricalImportBatch,
    HistoricalMetricValue,
    HistoricalPeriod,
    HistoricalSourceRow,
)
from app.models.publication import PublicRelease, PublicReleaseMetadata, PublicReleasePayload
from app.models.sustainability import EmissionFactor, EmissionFactorSet
from app.services.publication import payload_checksum
from tests.test_publication_integration import _account, _client

GRID, PETROL, DIESEL, LPG_KG = Decimal("0.5"), Decimal("2"), Decimal("3"), Decimal("1.5")


def _free_year(db: Session) -> int:
    year = 2300 + int(uuid4().int % 500)
    while db.scalar(select(HistoricalPeriod.id).where(HistoricalPeriod.year.in_((year, year + 1)))) or db.scalar(
        select(EmissionFactorSet.id).where(
            EmissionFactorSet.effective_from >= date(year, 1, 1),
            EmissionFactorSet.effective_from <= date(year + 1, 12, 31),
        )
    ):
        year += 2
    return year


def _factor_set(db: Session, year: int) -> None:
    item = EmissionFactorSet(
        id=uuid4(),
        version=f"historical-test-{year}-{uuid4().hex[:6]}",
        status=FactorSetStatus.ACTIVE,
        source_note="Synthetic historical test factors",
        effective_from=date(year, 1, 1),
        activated_at=datetime.now(UTC),
    )
    db.add(item)
    db.flush()
    for code, value, unit in (
        ("GRID_ELECTRICITY", GRID, "kWh"),
        ("PETROL", PETROL, "L"),
        ("DIESEL", DIESEL, "L"),
        ("LPG_KG", LPG_KG, "kg"),
    ):
        db.add(
            EmissionFactor(
                factor_set_id=item.id,
                code=code,
                factor_value=value,
                activity_unit=unit,
                result_unit="kgCO2e",
                source_reference="Synthetic test factor",
            )
        )
    db.flush()


def _mapping(name: str, suffix: str) -> dict[str, Any]:
    body = json.loads((importer.MAPPING_DIR / f"{name}.json").read_text(encoding="utf-8"))
    body["code"] = f"{body['code']}_{suffix}"
    body["source_reference"] = f"src/{name}_{suffix}.csv"
    return body


def _write(root: Path, mapping: dict[str, Any], content: str) -> None:
    path = root / mapping["source_reference"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode())


def _energy_csv(year: int, rows: list[tuple[str, str, str, str, str, str, str]]) -> str:
    header = (
        "Year,Month,Grid HT (kWh),Grid Commercial (kWh),Grid Temporary (kWh),Renewable On Campus (kWh),"
        "Procured Renewable (kWh),Solar Water Heater(same for all month)\n"
    )
    return header + "".join(f"{year},{','.join(row)}\n" for row in rows)


def _import(
    engine: Engine, root: Path, mappings: list[dict[str, Any]], resolutions: list[dict[str, Any]] | None = None
):
    sources = importer.load_sources(root, mappings)
    plan = reconcile(sources, resolutions or [])
    with Session(engine) as db:
        summary = importer.run(db, sources, plan, commit=True)
        db.commit()
    return summary, plan


def _timeline(engine: Engine) -> dict[str, Any]:
    with Session(engine) as db:
        return build_timeline(db)


def _value(timeline: dict[str, Any], key: str, code: str) -> Any:
    item = timeline["periods"][key]["values"].get(code)
    return None if item is None else item["value"]


@pytest.fixture
def year(postgres_engine: Engine) -> int:
    with Session(postgres_engine) as db:
        chosen = _free_year(db)
        _factor_set(db, chosen)
        db.commit()
    return chosen


def test_monthly_stays_monthly_with_formulas_and_provenance(postgres_engine: Engine, tmp_path: Path, year: int) -> None:
    suffix = uuid4().hex[:8]
    energy = _mapping("energy_staging", suffix)
    _write(
        tmp_path,
        energy,
        _energy_csv(
            year,
            [
                ("January", "100", "200", "50", "40", "60", "500"),
                ("February", "10", "20", "0", "0", "0", "1000000"),
            ],
        ),
    )
    _import(postgres_engine, tmp_path, [energy])
    timeline = _timeline(postgres_engine)
    jan, feb = f"{year}-01", f"{year}-02"
    # Synthetic second-month contract: grid 350, renewable 100, total 450, share 22.2%.
    assert _value(timeline, jan, "grid_total_kwh") == 350
    assert _value(timeline, jan, "renewable_electricity_kwh") == 100
    assert _value(timeline, jan, "total_electricity_consumption_kwh") == 450
    assert _value(timeline, jan, "renewable_share_pct") == pytest.approx(100 / 450 * 100)
    assert _value(timeline, jan, "estimated_avoided_grid_emissions_tco2e") == pytest.approx(100 * 0.5 / 1000)
    assert _value(timeline, jan, "scope2_tco2e") == pytest.approx(350 * 0.5 / 1000)
    # Explicit zeros stay zeros: February renewable is 0, not missing.
    assert _value(timeline, feb, "renewable_electricity_kwh") == 0
    assert _value(timeline, feb, "grid_temporary_kwh") == 0
    # Solar water heater is never electricity (and is unverified reference).
    assert _value(timeline, feb, "total_electricity_consumption_kwh") == 30
    assert "solar_water_heater_kwh" not in timeline["periods"][jan]["values"]

    with Session(postgres_engine) as db:
        batch = db.scalar(select(HistoricalImportBatch).where(HistoricalImportBatch.mapping_code == energy["code"]))
        assert batch is not None
        periods = db.scalars(select(HistoricalPeriod).where(HistoricalPeriod.year == year)).all()
        assert {item.granularity for item in periods} == {"MONTHLY"}
        assert sorted(item.month for item in periods) == [1, 2]
        ht = db.scalar(
            select(HistoricalMetricValue).where(
                HistoricalMetricValue.source_batch_id == batch.id,
                HistoricalMetricValue.metric_code == "grid_ht_kwh",
                HistoricalMetricValue.value_numeric == 100,
            )
        )
        assert ht is not None and ht.authority_status == "AUTHORITATIVE"
        raw = db.get(HistoricalSourceRow, ht.source_row_id)
        assert raw is not None and raw.raw_payload[2] == "100" and ht.source_column == "Grid HT (kWh)"
        grid = db.scalar(
            select(HistoricalCalculationResult).where(
                HistoricalCalculationResult.calculation_code == "grid_electricity_emissions",
                HistoricalCalculationResult.period_id.in_([item.id for item in periods if item.month == 1]),
            )
        )
        assert grid is not None and grid.factor_code == "GRID_ELECTRICITY" and grid.factor_value == GRID
        assert grid.factor_set_version and grid.factor_set_version.startswith(f"historical-test-{year}")
        swh = db.scalar(
            select(HistoricalMetricValue).where(
                HistoricalMetricValue.source_batch_id == batch.id,
                HistoricalMetricValue.metric_code == "solar_water_heater_kwh",
            )
        )
        assert swh is not None and swh.verification_status == "UNVERIFIED"


def test_procured_renewable_included_and_aggregate_share_is_ratio_of_sums(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    suffix = uuid4().hex[:8]
    energy = _mapping("energy_staging", suffix)
    months = [
        (name, "100", "0", "0", "0", "100" if name == "January" else "900", "5")
        for name in (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        )
    ]
    _write(tmp_path, energy, _energy_csv(year, months))
    _import(postgres_engine, tmp_path, [energy])
    timeline = _timeline(postgres_engine)
    assert _value(timeline, f"{year}-01", "renewable_share_pct") == 50
    assert _value(timeline, f"{year}-02", "renewable_share_pct") == 90
    full_year = timeline["periods"][f"{year}-FY"]
    # 100 + 11 x 900 renewable over 12 x 100 grid: ratio of sums, not the mean of 50/90/...
    renewable, grid = 100 + 11 * 900, 1200
    assert full_year["values"]["renewable_electricity_kwh"]["value"] == renewable
    assert full_year["values"]["renewable_share_pct"]["value"] == pytest.approx(renewable / (renewable + grid) * 100)
    assert full_year["values"]["renewable_share_pct"]["value"] != pytest.approx((50 + 11 * 90) / 12)
    assert full_year["values"]["grid_total_kwh"]["coverage_status"] == "complete"


def test_annual_and_ytd_never_become_monthly(postgres_engine: Engine, tmp_path: Path, year: int) -> None:
    suffix = uuid4().hex[:8]
    energy, waste, outreach = (
        _mapping(name, suffix) for name in ("energy_staging", "waste_staging", "outreach_staging")
    )
    waste["year_rules"] = {
        str(year): {"granularity": "ANNUAL", "coverage_start": f"{year}-01-01", "coverage_end": f"{year}-12-31"},
    }
    outreach["year_rules"] = waste["year_rules"]
    _write(tmp_path, energy, _energy_csv(year, [("March", "1", "1", "1", "1", "1", "1")]))
    _write(
        tmp_path,
        waste,
        f"Waste Inventory,,\nItem,Quantity (Kg),\nyear,{year},\nPET,100,\nIron,50,\n,,\n,{year},\n"
        "Total waste Approximate ,1150,\nWet Waste Generated ,1000,\nDry waste Generared ,150,\n",
    )
    _write(
        tmp_path,
        outreach,
        f"Overall Metrix,,\nMetric,Count / Reported Figure,\n,{year},\nNumber of Outreach Programs / Events,20+,\n"
        'Total participants / reach,"4,000+",\n',
    )
    _import(postgres_engine, tmp_path, [energy, waste, outreach])
    timeline = _timeline(postgres_engine)
    march = timeline["periods"][f"{year}-03"]
    # The annual waste/outreach figures are NOT a March value.
    for code in ("total_waste_generated_kg", "wet_waste_generated_kg", "total_programs", "total_participants"):
        assert code not in march["values"]
    # Waste is a year-aggregate domain: March points at the year's record.
    assert march["domains"]["waste"]["state"] == "year_aggregate"
    assert "the selected month does not filter it" in march["domains"]["waste"]["message"]
    assert march["domains"]["outreach"]["state"] == "aggregate_only"
    annual_key = march["domains"]["waste"]["alternative_key"]
    annual = timeline["periods"][annual_key]
    assert annual["values"]["total_waste_generated_kg"]["value"] == 1150
    assert annual["values"]["total_waste_generated_kg"]["granularity"] == "ANNUAL"
    assert annual["values"]["total_programs"]["value"] == 20
    assert annual["values"]["total_programs"]["qualifier"] == "AT_LEAST"
    assert annual["values"]["total_participants"]["value"] == 4000
    with Session(postgres_engine) as db:
        waste_periods = db.scalars(
            select(HistoricalPeriod)
            .join(HistoricalMetricValue, HistoricalMetricValue.period_id == HistoricalPeriod.id)
            .where(HistoricalMetricValue.domain.in_(("waste", "outreach")), HistoricalPeriod.year == year)
        ).all()
        assert {item.granularity for item in waste_periods} == {"ANNUAL"}
        assert len({item.id for item in waste_periods}) == 1


def test_unconfirmed_ytd_coverage_is_unverified_and_not_public(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    suffix = uuid4().hex[:8]
    waste = _mapping("waste_staging", suffix)
    waste["year_rules"] = {
        str(year): {
            "granularity": "YTD",
            "coverage_start": f"{year}-01-01",
            "coverage_end": f"{year}-06-30",
            "coverage_confirmed": False,
        }
    }
    _write(tmp_path, waste, f"Waste Inventory,,\n,{year},\nWet Waste Generated ,10,\nDry waste Generared ,5,\n")
    _import(postgres_engine, tmp_path, [waste])
    with Session(postgres_engine) as db:
        rows = db.scalars(
            select(HistoricalMetricValue).join(HistoricalPeriod).where(HistoricalPeriod.year == year)
        ).all()
        assert rows and {row.verification_status for row in rows} == {"UNVERIFIED"}
        assert {db.get(HistoricalPeriod, row.period_id).granularity for row in rows} == {"YTD"}  # type: ignore[union-attr]
    timeline = _timeline(postgres_engine)
    assert not any(key.startswith(f"{year}-") for key in timeline["periods"])


def test_missing_is_not_zero_and_water_total_without_sources(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    suffix = uuid4().hex[:8]
    water = _mapping("water_staging", suffix)
    water["year_rules"] = {
        str(year): {
            "recycled_period": {
                "granularity": "ANNUAL",
                "coverage_start": f"{year}-01-01",
                "coverage_end": f"{year}-12-31",
            },
            "annual_period": {
                "granularity": "ANNUAL",
                "coverage_start": f"{year}-01-01",
                "coverage_end": f"{year}-12-31",
            },
        }
    }
    _write(
        tmp_path,
        water,
        f"Water Consumption {year},,,,\nMonth,Water Consumption (KL),,,\nJan,300,,,\nFeb,,,,\nMar,0,,,\n",
    )
    _import(postgres_engine, tmp_path, [water])
    timeline = _timeline(postgres_engine)
    assert _value(timeline, f"{year}-01", "water_consumed_kl") == 300
    assert _value(timeline, f"{year}-03", "water_consumed_kl") == 0  # explicit zero
    assert f"{year}-02" not in timeline["periods"]  # blank month stays missing
    for code in ("water_twad_kl", "water_borewell_kl", "water_private_kl"):
        assert code not in timeline["periods"][f"{year}-01"]["values"]  # never invented
    ytd = timeline["periods"][f"{year}-YTD"]
    assert ytd["values"]["water_consumed_kl"]["value"] == 300
    assert ytd["values"]["water_consumed_kl"]["coverage_status"] == "partial"
    assert ytd["values"]["water_consumed_kl"]["months_covered"] == [f"{year}-01", f"{year}-03"]


def test_conflicting_copies_do_not_silently_resolve(postgres_engine: Engine, tmp_path: Path, year: int) -> None:
    suffix = uuid4().hex[:8]
    primary, competing = _mapping("energy_staging", suffix), _mapping("energy_manager_electricity", suffix)
    _write(tmp_path, primary, _energy_csv(year, [("January", "100", "20", "0", "1", "1", "0")]))
    _write(
        tmp_path,
        competing,
        f"year,month,connection_type,consumption_kwh\n{year},Jan,HT,999\n{year},Jan,Commercial,20\n{year},Jan,Temporary,0\n",
    )
    summary, plan = _import(postgres_engine, tmp_path, [primary, competing])
    timeline = _timeline(postgres_engine)
    jan = timeline["periods"][f"{year}-01"]["values"]
    assert "grid_ht_kwh" not in jan  # neither 100 nor 999 is published
    assert jan["grid_total_kwh"]["value"] is None
    assert jan["grid_commercial_kwh"]["value"] == 20  # uncontested and corroborated
    with Session(postgres_engine) as db:
        conflict = db.scalar(
            select(HistoricalConflict).where(
                HistoricalConflict.metric_code == "grid_ht_kwh", HistoricalConflict.conflict_key.contains(suffix)
            )
        )
        assert conflict is not None and conflict.resolution_status == "UNRESOLVED"
        assert {conflict.value_a, conflict.value_b} == {Decimal(100), Decimal(999)}

    # An owner-approved resolution appends new versions; nothing is overwritten.
    resolution = {
        "granularity": "MONTHLY",
        "coverage_start": f"{year}-01-01",
        "coverage_end": f"{year}-01-31",
        "domain": "energy",
        "metric_code": "grid_ht_kwh",
        "chosen_mapping_code": primary["code"],
        "reason": "Meter reading verified",
        "approved_by": "Project owner",
        "approved_at": "2026-09-24",
    }
    summary, _ = _import(postgres_engine, tmp_path, [primary, competing], [resolution])
    assert summary.versioned_values == 2 and summary.updated_conflicts == 1 and summary.inserted_values == 0
    timeline = _timeline(postgres_engine)
    assert _value(timeline, f"{year}-01", "grid_ht_kwh") == 100
    assert _value(timeline, f"{year}-01", "grid_total_kwh") == 120
    with Session(postgres_engine) as db:
        versions = db.scalars(
            select(HistoricalMetricValue)
            .join(HistoricalImportBatch, HistoricalImportBatch.id == HistoricalMetricValue.source_batch_id)
            .where(
                HistoricalImportBatch.mapping_code == primary["code"],
                HistoricalMetricValue.metric_code == "grid_ht_kwh",
            )
            .order_by(HistoricalMetricValue.version)
        ).all()
        assert [(item.version, item.verification_status) for item in versions] == [(1, "CONFLICT"), (2, "VERIFIED")]
        assert versions[1].supersedes_id == versions[0].id


def test_precision_only_difference_is_recorded_and_resolved() -> None:
    mapping_a = {"code": "a", "priority": 1, "domain": "transport"}
    mapping_b = {"code": "b", "priority": 2, "domain": "transport"}
    long = {
        "parser": "long_monthly",
        "options": {
            "year_column": "year",
            "month_column": "month",
            "category_column": "fuel_type",
            "value_column": "consumption_litre",
        },
        "categories": {"diesel": {"metric_code": "dg_diesel_litres", "unit": "L"}},
    }
    source_a = LoadedSource(
        {**mapping_a, **long},
        parse_source(b"year,month,fuel_type,consumption_litre\n2026,Apr,diesel,2136.83\n", {**mapping_a, **long}),
        "a" * 64,
        "a.csv",
    )
    source_b = LoadedSource(
        {**mapping_b, **long},
        parse_source(b"year,month,fuel_type,consumption_litre\n2026,Apr,diesel,2136.8\n", {**mapping_b, **long}),
        "b" * 64,
        "b.csv",
    )
    plan = reconcile([source_a, source_b], [])
    assert [conflict.resolution_status for conflict in plan.conflicts] == ["RESOLVED"]
    chosen = [value for value in plan.values if value.authority_status == "AUTHORITATIVE"]
    assert len(chosen) == 1 and chosen[0].observation.value == Decimal("2136.83")


def test_reported_aggregate_mismatch_is_conflict(postgres_engine: Engine, tmp_path: Path, year: int) -> None:
    suffix = uuid4().hex[:8]
    water = _mapping("water_staging", suffix)
    water["year_rules"] = {
        str(year): {
            "recycled_period": {
                "granularity": "ANNUAL",
                "coverage_start": f"{year}-01-01",
                "coverage_end": f"{year}-12-31",
            },
            "annual_period": {
                "granularity": "ANNUAL",
                "coverage_start": f"{year}-01-01",
                "coverage_end": f"{year}-12-31",
            },
        }
    }
    monthly = "".join(
        f"{name},10,,,\n"
        for name in ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    )
    _write(
        tmp_path,
        water,
        f"Water Consumption {year},,,,\nMonth,Water Consumption (KL),,,\n{monthly}Total,120,,,\n,,,,\n"
        "TWAD Consumption KL,Borewell Consumption (KL):,Total Consumption,,\n100,900,1000,,\n",
    )
    _, plan = _import(postgres_engine, tmp_path, [water])
    assert any(
        item.conflict_type == "aggregate_vs_monthly" and item.resolution_status == "UNRESOLVED"
        for item in plan.conflicts
    )
    timeline = _timeline(postgres_engine)
    assert f"{year}-01" not in timeline["periods"]  # contested monthly totals are not published
    assert timeline["periods"][f"{year}-FY"]["values"].get("water_consumed_kl", {}).get("value") is None
    assert timeline["periods"][f"{year}-FY"]["values"]["water_twad_kl"]["value"] == 100


def test_import_is_idempotent_and_changed_source_is_refused(postgres_engine: Engine, tmp_path: Path, year: int) -> None:
    suffix = uuid4().hex[:8]
    energy = _mapping("energy_staging", suffix)
    _write(tmp_path, energy, _energy_csv(year, [("January", "1", "2", "3", "4", "5", "6")]))
    first, _ = _import(postgres_engine, tmp_path, [energy])
    second, _ = _import(postgres_engine, tmp_path, [energy])
    assert first.new_batches == 1 and first.inserted_values == 6
    assert (second.new_batches, second.inserted_values, second.inserted_calculations) == (0, 0, 0)
    assert second.unchanged_values == 6
    _write(tmp_path, energy, _energy_csv(year, [("January", "9", "2", "3", "4", "5", "6")]))
    with pytest.raises(importer.ImportRefused):
        _import(postgres_engine, tmp_path, [energy])


def test_history_is_append_only(postgres_engine: Engine, tmp_path: Path, year: int) -> None:
    suffix = uuid4().hex[:8]
    energy = _mapping("energy_staging", suffix)
    _write(tmp_path, energy, _energy_csv(year, [("January", "1", "2", "3", "4", "5", "6")]))
    _import(postgres_engine, tmp_path, [energy])
    with Session(postgres_engine) as db:
        row = db.scalar(
            select(HistoricalMetricValue).join(HistoricalPeriod).where(HistoricalPeriod.year == year).limit(1)
        )
        assert row is not None
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text("update history.metric_values set value_numeric = 0 where id = :id"), {"id": row.id})
        db.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text("delete from history.source_rows where id = :id"), {"id": row.source_row_id})
        db.rollback()


def test_per_capita_uses_that_years_population(postgres_engine: Engine, tmp_path: Path, year: int) -> None:
    suffix = uuid4().hex[:8]
    water, population = _mapping("water_staging", suffix), _mapping("population_staging", suffix)
    water["year_rules"] = {
        str(year): {
            "recycled_period": {
                "granularity": "ANNUAL",
                "coverage_start": f"{year}-01-01",
                "coverage_end": f"{year}-12-31",
            },
            "annual_period": {
                "granularity": "ANNUAL",
                "coverage_start": f"{year}-01-01",
                "coverage_end": f"{year}-12-31",
            },
        }
    }
    _write(tmp_path, water, f"Water Consumption {year},,,,\nMonth,Water Consumption (KL),,,\nJan,700,,,\n")
    _write(tmp_path, population, f"year,population\n{year},7000\n")
    _import(postgres_engine, tmp_path, [water, population])
    timeline = _timeline(postgres_engine)
    assert _value(timeline, f"{year}-01", "water_per_capita_l") == 100  # 700 KL x 1000 / 7000
    assert timeline["periods"][f"{year}-01"]["population"]["value"] == 7000
    # The next year has no population reference: per-capita stays unavailable.
    _write(tmp_path, water, f"Water Consumption {year + 1},,,,\nMonth,Water Consumption (KL),,,\nJan,700,,,\n")
    water2 = {
        **water,
        "code": f"{water['code']}_next",
        "source_reference": f"src/water_next_{suffix}.csv",
        "year_rules": {str(year + 1): water["year_rules"][str(year)]},
    }
    _write(tmp_path, water2, f"Water Consumption {year + 1},,,,\nMonth,Water Consumption (KL),,,\nJan,700,,,\n")
    _import(postgres_engine, tmp_path, [water2])
    timeline = _timeline(postgres_engine)
    assert _value(timeline, f"{year + 1}-01", "water_per_capita_l") is None


def _release(
    db: Session, year: int, month: int, version: str, admin_id: Any, *, published_hours_ago: int
) -> PublicRelease:
    payload = {
        "schema_version": "1.4",
        "period": {"id": str(uuid4()), "year": year, "month": month},
        "energy": {"metrics": {"grid_total_kwh": {"value": 777, "unit": "kWh"}}, "calculations": []},
        "indicators": {},
    }
    release = PublicRelease(
        id=uuid4(),
        version=version,
        status=ReleaseStatus.SUPERSEDED,
        checksum_sha256=payload_checksum(payload),
        prepared_by=admin_id,
        published_by=admin_id,
        published_at=datetime.now(UTC).replace(microsecond=0) - timedelta(hours=published_hours_ago),
    )
    db.add(release)
    db.flush()
    db.add(PublicReleasePayload(release_id=release.id, payload=payload))
    db.flush()
    return release


def test_official_release_beats_history_and_test_release_is_excluded(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    suffix = uuid4().hex[:8]
    energy = _mapping("energy_staging", suffix)
    _write(
        tmp_path,
        energy,
        _energy_csv(year, [("January", "1", "2", "3", "4", "5", "6"), ("February", "1", "2", "3", "4", "5", "6")]),
    )
    _import(postgres_engine, tmp_path, [energy])
    with Session(postgres_engine) as db:
        admin = _account(db, RoleCode.ADMIN)
        official = _release(db, year, 1, f"official-{suffix}", admin.id, published_hours_ago=2)
        test_release = _release(db, year, 2, f"test-{suffix}", admin.id, published_hours_ago=1)
        test_release_payload = db.get(PublicReleasePayload, test_release.id)
        db.add(
            PublicReleaseMetadata(
                release_id=test_release.id,
                classification="test",
                public_visible=False,
                reason="Workflow acceptance data",
            )
        )
        db.commit()
        official_version, test_version = official.version, test_release.version
        test_checksum = test_release.checksum_sha256
        assert test_release_payload is not None
    timeline = _timeline(postgres_engine)
    jan, feb = timeline["periods"][f"{year}-01"], timeline["periods"][f"{year}-02"]
    assert jan["source_kind"] == "published_release" and jan["release_version"] == official_version
    assert jan["values"]["grid_total_kwh"]["value"] == 777  # official release, not the historical 6
    assert feb["source_kind"] == "historical_verified"  # the TEST release never replaces history
    assert all(item.get("release_version") != test_version for item in timeline["periods"].values())
    with _client(postgres_engine) as client:
        history = client.get("/api/public/dashboard/history").json()
        assert all(item["release"]["version"] != test_version for item in history)
        assert any(item["release"]["version"] == official_version for item in history)
        api_timeline = client.get("/api/public/dashboard/timeline").json()
        assert api_timeline["periods"][f"{year}-01"]["release_version"] == official_version
    with Session(postgres_engine) as db:
        stored = db.scalar(select(PublicRelease).where(PublicRelease.version == test_version))
        payload = db.get(PublicReleasePayload, stored.id) if stored else None
        assert stored is not None and payload is not None
        assert payload_checksum(payload.payload) == stored.checksum_sha256 == test_checksum  # preserved intact


def test_active_test_release_is_not_served_as_the_public_dashboard(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db:
        active = db.scalar(select(PublicRelease).where(PublicRelease.status == ReleaseStatus.ACTIVE))
        if active is None:
            admin = _account(db, RoleCode.ADMIN)
            active = _release(db, 2299, 9, f"active-test-{uuid4().hex[:8]}", admin.id, published_hours_ago=0)
            active.status = ReleaseStatus.ACTIVE
            db.add(
                PublicReleaseMetadata(
                    release_id=active.id, classification="test", public_visible=False, reason="Workflow acceptance"
                )
            )
            db.commit()
        metadata = db.get(PublicReleaseMetadata, active.id)
        expected_public = metadata is None or metadata.public_visible
        version = active.version
    with _client(postgres_engine) as client:
        body = client.get("/api/public/dashboard").json()
    assert (body["release"] is not None) == expected_public
    if not expected_public:
        assert body["period"] is None and body["transport"] is None
    else:
        assert body["release"]["version"] == version


def _reporting_domains(period: dict[str, Any]) -> int:
    return sum(1 for state in period["domains"].values() if state["state"] == "available")


def test_default_period_is_latest_official_month(postgres_engine: Engine, tmp_path: Path, year: int) -> None:
    suffix = uuid4().hex[:8]
    energy = _mapping("energy_staging", suffix)
    _write(tmp_path, energy, _energy_csv(year + 1, [("June", "1", "2", "3", "4", "5", "6")]))
    _import(postgres_engine, tmp_path, [energy])
    timeline = _timeline(postgres_engine)
    monthly = [item for item in timeline["periods"].values() if item["granularity"] == "MONTHLY"]
    # The default is the latest month reported by at least two domains; a
    # single-domain month stays selectable but never becomes the default.
    institution_wide = [item for item in monthly if _reporting_domains(item) >= 2]
    latest = max(institution_wide or monthly, key=lambda item: (item["year"], item["month"]))
    assert timeline["default_key"] == latest["key"]
    options = next(item for item in timeline["selector"] if item["year"] == year + 1)["options"]
    assert [option["key"] for option in options] == [f"{year + 1}-YTD", f"{year + 1}-06"]
    assert options[0]["label"].startswith("YTD")


# ---- Display resolution (presentation only) --------------------------------


def _water_mapping(suffix: str, year: int, *, recycled: dict[str, Any], annual: dict[str, Any]) -> dict[str, Any]:
    water = _mapping("water_staging", suffix)
    water["year_rules"] = {str(year): {"recycled_period": recycled, "annual_period": annual}}
    return water


def test_month_display_uses_annual_context_without_creating_monthly_data(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    suffix = uuid4().hex[:8]
    energy, waste, outreach = (
        _mapping(name, suffix) for name in ("energy_staging", "waste_staging", "outreach_staging")
    )
    rules = {str(year): {"granularity": "ANNUAL", "coverage_start": f"{year}-01-01", "coverage_end": f"{year}-12-31"}}
    waste["year_rules"] = outreach["year_rules"] = rules
    _write(tmp_path, energy, _energy_csv(year, [("March", "1", "1", "1", "1", "1", "1")]))
    _write(
        tmp_path,
        waste,
        f"Waste Inventory,,\n,{year},\nWet Waste Generated ,1000,\nDry waste Generared ,150,\nPET,150,\n",
    )
    _write(
        tmp_path,
        outreach,
        f'Overall Metrix,,\n,{year},\nTotal participants / reach,"4,000+",\n',
    )
    _import(postgres_engine, tmp_path, [energy, waste, outreach])
    timeline = _timeline(postgres_engine)
    march = timeline["periods"][f"{year}-03"]
    shown = march["display"]["total_waste_generated_kg"]
    assert shown["value"] == 1150
    assert shown["display_label"] == f"{year} Full Year"  # waste is a year aggregate
    assert shown["display_context"] is True and shown["source_granularity"] == "ANNUAL"
    assert shown["source_key"] == f"{year}-FY" and shown["source_month"] is None
    assert march["display"]["total_participants"]["qualifier"] == "AT_LEAST"
    assert march["display"]["landfill_diversion_pct"] == {
        **march["display"]["landfill_diversion_pct"],
        "value": 88.1,
        "source_granularity": "STATIC",
        "display_label": "Institutional Reference",
    }
    # The month's own data is untouched: no March waste value, no monthly waste rows.
    assert "total_waste_generated_kg" not in march["values"]
    assert march["display"]["grid_ht_kwh"]["display_label"] == f"March {year}"
    assert march["display"]["grid_ht_kwh"]["display_context"] is False
    with Session(postgres_engine) as db:
        monthly_waste = db.scalar(
            select(HistoricalMetricValue.id)
            .join(HistoricalPeriod, HistoricalPeriod.id == HistoricalMetricValue.period_id)
            .where(
                HistoricalPeriod.year == year,
                HistoricalPeriod.granularity == "MONTHLY",
                HistoricalMetricValue.domain == "waste",
            )
        )
        assert monthly_waste is None
    # The Full Year view shows the annual record as its own data, not as context.
    full_year = timeline["periods"][f"{year}-FY"]["display"]["total_waste_generated_kg"]
    assert full_year["display_context"] is False and full_year["display_label"] == f"{year} Full Year"


def test_exact_month_beats_annual_and_ytd_context_is_labelled(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    suffix = uuid4().hex[:8]
    water = _water_mapping(
        suffix,
        year,
        recycled={"granularity": "YTD", "coverage_start": f"{year}-01-01", "coverage_end": f"{year}-06-30"},
        annual={"granularity": "ANNUAL", "coverage_start": f"{year}-01-01", "coverage_end": f"{year}-12-31"},
    )
    _write(
        tmp_path,
        water,
        f"Water Consumption {year},,,,\nTotal Water Recyled ,470,,,\nMonth,Water Consumption (KL),,,\nJan,300,,,\n"
        ",,,,\nTWAD Consumption KL,Borewell Consumption (KL):,Total Consumption,,\n400,600,1000,,\n",
    )
    _import(postgres_engine, tmp_path, [water])
    jan = _timeline(postgres_engine)["periods"][f"{year}-01"]["display"]
    assert jan["water_consumed_kl"]["value"] == 300  # exact month wins over the annual 1000
    assert jan["water_consumed_kl"]["display_label"] == f"January {year}"
    assert jan["water_twad_kl"]["value"] == 400 and jan["water_twad_kl"]["display_label"] == f"{year} Annual Data"
    assert jan["water_recycled_kl"]["value"] == 470
    assert jan["water_recycled_kl"]["display_label"] == f"{year} YTD · Jan–Jun"
    assert jan["water_recycled_kl"]["display_context"] is True


def test_partial_ghg_is_labelled_and_missing_is_omitted(postgres_engine: Engine, tmp_path: Path, year: int) -> None:
    suffix = uuid4().hex[:8]
    energy = _mapping("energy_staging", suffix)
    _write(
        tmp_path,
        energy,
        _energy_csv(year, [("January", "100", "20", "5", "1", "1", "0"), ("February", "100", "20", "", "1", "1", "0")]),
    )
    _import(postgres_engine, tmp_path, [energy])
    timeline = _timeline(postgres_engine)
    feb = timeline["periods"][f"{year}-02"]["display"]
    for code in ("grid_total_kwh", "grid_temporary_kwh"):
        assert code not in feb  # no value, no fallback: omitted, never zero
    jan = timeline["periods"][f"{year}-01"]["display"]
    assert jan["scope2_tco2e"]["calculation_status"] == "COMPLETE"
    # Available-data rule: the two meters that reported produce a Scope 2
    # value that is labelled PARTIAL and names the missing meter.
    assert feb["scope2_tco2e"]["calculation_status"] == "PARTIAL"
    assert [item["code"] for item in feb["scope2_tco2e"]["missing_contributors"]] == ["grid_temporary_kwh"]
    ytd = timeline["periods"][f"{year}-YTD"]["display"]
    for code in ("scope2_tco2e", "grid_electricity_emissions"):
        assert ytd[code]["calculation_status"] == "PARTIAL"  # shown, but never as a complete total
    assert ytd["grid_total_kwh"]["value"] == 125
    assert ytd["grid_total_kwh"]["display_label"] == f"{year} · 1 of 2 months"
    assert ytd["renewable_electricity_kwh"]["display_label"] == f"{year} YTD · Jan–Feb"


def test_owner_approved_annual_water_total_is_annual_only(postgres_engine: Engine, tmp_path: Path, year: int) -> None:
    suffix = uuid4().hex[:8]
    water, energy, population = (
        _mapping(name, suffix) for name in ("water_staging", "energy_staging", "population_staging")
    )
    annual_rule = {"granularity": "ANNUAL", "coverage_start": f"{year}-01-01", "coverage_end": f"{year}-12-31"}
    water["year_rules"] = {
        str(year): {"recycled_period": annual_rule, "annual_period": annual_rule},
        str(year + 1): {
            "recycled_period": {
                "granularity": "YTD",
                "coverage_start": f"{year + 1}-01-01",
                "coverage_end": f"{year + 1}-06-30",
                "coverage_confirmed": False,
            },
            "annual_period": {
                "granularity": "YTD",
                "coverage_start": f"{year + 1}-01-01",
                "coverage_end": f"{year + 1}-06-30",
                "coverage_confirmed": False,
            },
        },
    }
    months = "".join(
        f"{name},10,,,\n"
        for name in ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    )
    _write(
        tmp_path,
        water,
        f"Water Consumption {year},,,,\nMonth,Water Consumption (KL),,,\n{months}Total,120,,,\n,,,,\n"
        "TWAD Consumption KL,Borewell Consumption (KL):,Total Consumption,,\n400,600,1000,,\n,,,,\n"
        f"Water Consumption {year + 1},,,,\n"
        "Month,TWAD Consumption KL,Borewell Consumption (KL):,Quantity of Water Procured KL,Total Consumption\n"
        "January,3,5,2,10\n",
    )
    _write(tmp_path, energy, _energy_csv(year, [("March", "1", "1", "1", "1", "1", "1")]))
    _write(tmp_path, population, f"year,population\n{year},500\n")
    resolution = {
        "granularity": "ANNUAL",
        "coverage_start": f"{year}-01-01",
        "coverage_end": f"{year}-12-31",
        "domain": "water",
        "metric_code": "water_consumed_kl",
        "chosen_mapping_code": water["code"],
        "reason": "Owner-approved annual total",
        "approved_by": "Project owner",
        "approved_at": "2026-09-25",
    }
    _, plan = _import(postgres_engine, tmp_path, [water, energy, population], [resolution])
    conflict = next(item for item in plan.conflicts if item.conflict_type == "aggregate_vs_monthly")
    assert conflict.resolution_status == "RESOLVED" and conflict.chosen_source == water["code"]

    timeline = _timeline(postgres_engine)
    full_year = timeline["periods"][f"{year}-FY"]
    assert full_year["values"]["water_consumed_kl"]["value"] == 1000
    assert full_year["values"]["water_consumed_kl"]["granularity"] == "ANNUAL"
    assert full_year["display"]["water_consumed_kl"]["display_label"] == f"{year} Annual Data"
    assert full_year["display"]["water_per_capita_l"]["value"] == pytest.approx(1000 * 1000 / 500)
    march = timeline["periods"][f"{year}-03"]
    assert "water_consumed_kl" not in march["values"]  # never a March value
    shown = march["display"]["water_consumed_kl"]
    assert (shown["value"], shown["display_label"], shown["display_context"]) == (1000, f"{year} Annual Data", True)
    with Session(postgres_engine) as db:
        monthly = db.scalars(
            select(HistoricalMetricValue)
            .join(HistoricalPeriod, HistoricalPeriod.id == HistoricalMetricValue.period_id)
            .where(
                HistoricalPeriod.year == year,
                HistoricalPeriod.granularity == "MONTHLY",
                HistoricalMetricValue.metric_code == "water_consumed_kl",
            )
        ).all()
        assert len(monthly) == 12 and {row.verification_status for row in monthly} == {"REJECTED"}
        assert all(row.value_numeric == 10 for row in monthly)  # the annual total was never split
    # The next year's monthly total is still TWAD + Borewell + Private.
    assert _value(timeline, f"{year + 1}-01", "water_consumed_kl") == 10
