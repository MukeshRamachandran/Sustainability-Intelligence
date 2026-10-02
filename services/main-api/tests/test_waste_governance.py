"""Waste governance: owner-confirmed 2026 YTD, diverted-from-landfill and the year aggregate.

Owner decisions (2026-10-02):
  * the 2026 Waste Inventory covers 1 January - 30 June 2026 and its wet, dry
    and material figures are valid year-to-date values;
  * waste diverted from landfill IS the dry waste generated;
  * total = wet + dry; per person = total / the year's population;
  * waste is a year-aggregate domain: a historical Annual/YTD baseline plus
    the PUBLISHED months that start after it, shown for every selection in the
    year. Nothing is split into months and nothing is counted twice.
"""

from __future__ import annotations

import inspect
import json
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.historical import importer, resolver
from app.historical.validator import reconcile
from app.models.enums import ReleaseStatus, RoleCode
from app.models.history import HistoricalCalculationResult, HistoricalMetricValue, HistoricalPeriod
from app.models.publication import PublicRelease, PublicReleasePayload
from app.models.sustainability import InstitutionalPopulationReference
from app.services import sustainability_formulas as formulas
from app.services.publication import payload_checksum
from tests.test_historical_integration import _import, _mapping, _timeline, _write
from tests.test_publication_integration import _account as _db_account

MAPPING_FILE = importer.MAPPING_DIR / "waste_staging.json"
POPULATION = 5000
WET, DRY, TOTAL = "wet_waste_generated_kg", "dry_waste_generated_kg", "total_waste_generated_kg"
DIVERTED, PER_PERSON = "waste_diverted_from_landfill_kg", "waste_per_capita_kg"
MATERIALS_2026 = {
    "material:COLOUR_PAPER": "21174.1", "material:WHITE_PAPER": "5178.07", "material:IRON": "7726.75",
    "material:LITE_WEIGHT": "20226.25", "material:CARDBOARD": "1669.6", "material:PP_CARDBOARDS": "7759.33",
    "material:MIXED_PLASTICS": "3539.8", "material:BLACK_PLASTIC_PP": "5033.5", "material:PET": "1116.5",
    "material:ALUMINIUM": "838.4", "material:HDPE": "806.9", "material:LDPE": "784.1",
    "material:NEWS_PAPER": "719.1", "material:TYRE": "18.2",
}


def _repo_root() -> Path | None:
    configured = os.getenv("KCOSMOS_REPO_ROOT")
    parents = Path(__file__).resolve().parents
    candidate = Path(configured) if configured else (parents[3] if len(parents) > 3 else None)
    reference = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))["source_reference"]
    return candidate if candidate is not None and (candidate / reference).exists() else None


REPO_ROOT = _repo_root()
needs_source = pytest.mark.skipif(REPO_ROOT is None, reason="repository source files are not available")


# ---- The governed source and the owner confirmation (no database) -------------


@needs_source
def test_owner_confirmation_verifies_2026_wet_dry_and_materials_through_june() -> None:
    assert REPO_ROOT is not None
    mapping = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    sources = importer.load_sources(REPO_ROOT, [mapping])
    plan = reconcile(sources, importer.load_resolutions(), importer.load_coverage_confirmations())
    assert plan.conflicts == []
    current = {
        item.observation.metric_code: item for item in plan.values if item.observation.period.year == 2026
    }
    # Every 2026 value is one YTD period, 1 January - 30 June, with a stated end.
    assert {(item.observation.period.granularity, item.observation.period.coverage_start,
             item.observation.period.coverage_end) for item in current.values()} == {
        ("YTD", date(2026, 1, 1), date(2026, 6, 30))
    }
    assert {(item.verification_status, item.authority_status, item.coverage_end_stated)
            for item in current.values()} == {("VERIFIED", "AUTHORITATIVE", True)}
    assert current[WET].observation.value == Decimal("3000")
    assert current[DRY].observation.value == Decimal("76590.6")
    materials = {code: item.observation.value for code, item in current.items() if code.startswith("material:")}
    assert materials == {code: Decimal(value) for code, value in MATERIALS_2026.items()}  # the 14 supplied
    assert sum(materials.values()) == current[DRY].observation.value == Decimal("76590.6")
    assert formulas.waste_total_kg(current[WET].observation.value, current[DRY].observation.value) == Decimal(
        "79590.6"
    )
    assert current[TOTAL].observation.value == Decimal("79590.6")  # the source's own total agrees
    assert {item.confirmation["id"] for item in current.values() if item.confirmation} == {
        "waste-2026-ytd-jan-jun-confirmed"
    }
    # 2025 is untouched: annual, verified without any confirmation, 18 materials.
    previous = {item.observation.metric_code: item for item in plan.values if item.observation.period.year == 2025}
    assert all(item.confirmation is None and item.verification_status == "VERIFIED" for item in previous.values())
    materials_2025 = [item.observation.value for code, item in previous.items() if code.startswith("material:")]
    assert len(materials_2025) == 18 and sum(materials_2025) == previous[DRY].observation.value == Decimal("48762.55")
    assert previous[WET].observation.value + previous[DRY].observation.value == Decimal("55339.55")


def test_diverted_is_dry_waste_and_missing_is_not_zero() -> None:
    assert formulas.waste_diverted_from_landfill_kg(Decimal("76590.6")) == Decimal("76590.6")
    assert formulas.waste_diverted_from_landfill_kg(None) is None  # missing dry -> unavailable
    assert formulas.waste_diverted_from_landfill_kg(Decimal("0")) == Decimal("0")  # a reported zero stays zero
    assert formulas.waste_total_kg(Decimal("3000"), Decimal("76590.6")) == Decimal("79590.6")
    assert formulas.waste_total_kg(Decimal("3000"), None) is None
    assert formulas.waste_per_capita_kg(Decimal("79590.6"), 6991) == Decimal("79590.6") / Decimal(6991)
    assert formulas.waste_per_capita_kg(Decimal("79590.6"), None) is None


def test_diverted_waste_never_depends_on_the_legacy_static_percentage() -> None:
    assert "88" not in inspect.getsource(formulas.waste_diverted_from_landfill_kg)
    aggregate = inspect.getsource(resolver._waste_year_aggregate)
    assert "LANDFILL" not in aggregate and "88" not in aggregate
    # 2026: dry is 96.2 % of the total, so 88.1 % would give a different figure.
    assert formulas.waste_diverted_from_landfill_kg(Decimal("76590.6")) != Decimal("79590.6") * Decimal("0.881")


# ---- Year aggregate (database) -------------------------------------------------


def _baseline(
    engine: Engine, root: Path, year: int, *, end: str, wet: str | None, materials: dict[str, str],
    granularity: str = "YTD", dry: str | None = None,
) -> None:
    """A verified historical waste record for the year: 1 January to ``end``."""
    mapping = _mapping("waste_staging", uuid4().hex[:8])
    mapping["year_rules"] = {
        str(year): {"granularity": granularity, "coverage_start": f"{year}-01-01", "coverage_end": f"{year}-{end}"}
    }
    stated = dry if dry is not None else (str(sum(Decimal(v) for v in materials.values())) if materials else None)
    lines = ["Waste Inventory,,", "Item,Quantity (Kg),", f"year,{year},"]
    lines += [f"{name},{value}," for name, value in materials.items()]
    lines += [",,", f",{year},"]
    if wet is not None:
        lines.append(f"Wet Waste Generated ,{wet},")
    if stated is not None:
        lines.append(f"Dry waste Generared ,{stated},")
    _write(root, mapping, "\n".join(lines) + "\n")
    _import(engine, root, [mapping])


def _publish(
    engine: Engine, year: int, month: int, wet: str, materials: dict[str, str], *, hours_ago: int = 1,
    published: bool = True,
) -> None:
    """A Manager month as a release would freeze it: wet, dry (= materials) and total."""
    dry = sum((Decimal(value) for value in materials.values()), Decimal("0"))
    payload: dict[str, Any] = {
        "schema_version": "1.5",
        "period": {"id": str(uuid4()), "year": year, "month": month},
        "waste": {
            "metrics": {
                WET: {"value": float(wet), "unit": "kg"},
                DRY: {"value": float(dry), "unit": "kg"},
                TOTAL: {"value": float(Decimal(wet) + dry), "unit": "kg"},
            },
            "calculations": [],
            "materials": [{"code": code, "quantity_kg": float(value)} for code, value in materials.items()],
        },
    }
    with Session(engine) as db:
        admin = _db_account(db, RoleCode.ADMIN)
        release = PublicRelease(
            id=uuid4(), version=f"waste-{year}-{month}-{uuid4().hex[:6]}",
            status=ReleaseStatus.SUPERSEDED if published else ReleaseStatus.CANDIDATE,
            checksum_sha256=payload_checksum(payload), prepared_by=admin.id,
            published_by=admin.id if published else None,
            published_at=datetime.now(UTC) - timedelta(hours=hours_ago) if published else None,
        )
        db.add(release)
        db.flush()
        db.add(PublicReleasePayload(release_id=release.id, payload=payload))
        db.commit()


_USED_YEARS: set[int] = set()


def _unused_year(db: Session) -> int:
    """A year no other test uses.

    These tests publish synthetic months, and a published month outranks
    history for that month. The shared ``_free_year`` helper (2300+) does not
    look at releases, so a separate range keeps them out of other tests' years.
    """
    year = 3000 + int(uuid4().int % 2000)
    while (
        year in _USED_YEARS
        or db.scalar(select(HistoricalPeriod.id).where(HistoricalPeriod.year == year))
        or db.get(InstitutionalPopulationReference, year) is not None
    ):
        year += 1
    _USED_YEARS.add(year)
    return year


@pytest.fixture
def year(postgres_engine: Engine) -> int:
    with Session(postgres_engine) as db:
        free = _unused_year(db)
        db.add(InstitutionalPopulationReference(
            effective_year=free, population=POPULATION, unit="people", source_reference="Waste governance test",
        ))
        db.commit()
    return free


def _waste(period: dict[str, Any]) -> dict[str, Any]:
    return {code: item["value"] for code, item in period["values"].items()
            if item["domain"] == "waste" and item["status"] == "available"}


def _shown(period: dict[str, Any]) -> dict[str, tuple[Any, str, bool]]:
    return {code: (item["value"], item["display_label"], item["display_context"])
            for code, item in period["display"].items()
            if item.get("domain") == "waste" and item.get("source_granularity") != "STATIC"}


JAN_JUN = {"PET": "100", "Iron": "50.5"}


def test_ytd_baseline_alone_resolves_total_diverted_and_per_person(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    _baseline(postgres_engine, tmp_path, year, end="06-30", wet="1000", materials=JAN_JUN)
    periods = _timeline(postgres_engine)["periods"]
    ytd = periods[f"{year}-YTD"]
    assert _waste(ytd) == {
        WET: 1000, DRY: 150.5, "material:PET": 100, "material:IRON": 50.5,
        TOTAL: 1150.5, DIVERTED: 150.5, PER_PERSON: pytest.approx(1150.5 / POPULATION),
    }
    values = ytd["values"]
    assert (values[TOTAL]["kind"], values[DIVERTED]["kind"], values[PER_PERSON]["kind"]) == ("calculation",) * 3
    assert values[WET]["provenance"]["verification_status"] == "VERIFIED"
    assert values[TOTAL]["coverage_label"] == f"{year} YTD"
    provenance = values[DIVERTED]["provenance"]
    assert (provenance["aggregation"], provenance["baseline_coverage_start"], provenance["baseline_coverage_end"]) == (
        "waste_year_aggregate", f"{year}-01-01", f"{year}-06-30",
    )
    assert provenance["months_added"] == []
    # The baseline is one YTD record: no month exists and nothing was split.
    assert not any(key.startswith(f"{year}-0") or key.startswith(f"{year}-1") for key in periods)
    with Session(postgres_engine) as db:
        granularities = set(db.scalars(select(HistoricalPeriod.granularity).where(HistoricalPeriod.year == year)).all())
        assert granularities == {"YTD"}
        stored = db.scalar(
            select(HistoricalCalculationResult).join(HistoricalPeriod).where(
                HistoricalPeriod.year == year, HistoricalCalculationResult.calculation_code == DIVERTED,
                HistoricalCalculationResult.is_current.is_(True),
            )
        )
        assert stored is not None and stored.result_value == Decimal("150.5")
        assert set(stored.input_snapshot) == {DRY}


def test_missing_dry_gives_no_diverted_value_and_zero_dry_gives_zero(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    _baseline(postgres_engine, tmp_path, year, end="06-30", wet="40", materials={})
    ytd = _timeline(postgres_engine)["periods"][f"{year}-YTD"]["values"]
    assert ytd[WET]["value"] == 40
    assert (ytd[DIVERTED]["status"], ytd[DIVERTED]["value"], ytd[DIVERTED]["reason"]) == (
        "unavailable", None, "dry_waste_unavailable",
    )
    assert (ytd[TOTAL]["status"], ytd[PER_PERSON]["status"]) == ("unavailable", "unavailable")

    with Session(postgres_engine) as db:
        other = _unused_year(db)
    _baseline(postgres_engine, tmp_path, other, end="06-30", wet="40", materials={}, dry="0")
    zero = _timeline(postgres_engine)["periods"][f"{other}-YTD"]["values"]
    assert (zero[DRY]["value"], zero[DIVERTED]["status"], zero[DIVERTED]["value"]) == (0, "available", 0)
    assert zero[TOTAL]["value"] == 40


def test_annual_baseline_is_the_year_and_overlapping_months_are_not_added(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    _baseline(postgres_engine, tmp_path, year, end="12-31", wet="1000", materials=JAN_JUN, granularity="ANNUAL")
    _publish(postgres_engine, year, 3, "7", {"PET": "9"})  # inside the annual coverage
    periods = _timeline(postgres_engine)["periods"]
    aggregate = next(period for key, period in periods.items()
                     if period["year"] == year and period["granularity"] != "MONTHLY" and TOTAL in _waste(period))
    assert _waste(aggregate)[TOTAL] == 1150.5 and _waste(aggregate)[DIVERTED] == 150.5
    assert aggregate["values"][TOTAL]["coverage_label"] == f"{year} Full Year"
    assert aggregate["values"][TOTAL]["provenance"]["months_excluded_overlap"] == [f"{year}-03"]
    # March keeps its own published values, but SHOWS the year's aggregate.
    march = periods[f"{year}-03"]
    assert march["values"][WET]["value"] == 7
    assert march["domains"]["waste"]["state"] == "year_aggregate"
    assert _shown(march)[TOTAL] == (1150.5, f"{year} Full Year", True)
    assert _shown(march)[WET] == (1000, f"{year} Full Year", True)


def test_ytd_baseline_plus_published_months_after_it_for_every_selection(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    _baseline(postgres_engine, tmp_path, year, end="06-30", wet="1000", materials=JAN_JUN)
    _publish(postgres_engine, year, 5, "999", {"PET": "999"})  # May: inside the baseline, never added
    _publish(postgres_engine, year, 7, "10", {"PET": "5", "HDPE": "7"})  # HDPE is new this year
    periods = _timeline(postgres_engine)["periods"]
    ytd = periods[f"{year}-YTD"]
    assert _waste(ytd) == {
        WET: 1010, DRY: 162.5, "material:PET": 105, "material:IRON": 50.5, "material:HDPE": 7,
        TOTAL: 1172.5, DIVERTED: 162.5, PER_PERSON: pytest.approx(1172.5 / POPULATION),
    }
    provenance = ytd["values"][TOTAL]["provenance"]
    assert provenance["months_added"] == [f"{year}-07"]
    assert provenance["months_excluded_overlap"] == [f"{year}-05"]
    assert ytd["values"][TOTAL]["source_kind"] == "mixed_aggregate"
    # May and July both show the same current YTD - the month does not filter waste.
    expected = _shown(periods[f"{year}-07"])
    assert expected[TOTAL] == (1172.5, f"{year} YTD", True)
    assert expected["material:HDPE"] == (7, f"{year} YTD", True)
    assert _shown(periods[f"{year}-05"]) == expected
    assert periods[f"{year}-07"]["values"][WET]["value"] == 10  # the month's own record is untouched

    _publish(postgres_engine, year, 8, "20", {"IRON": "30"})
    periods = _timeline(postgres_engine)["periods"]
    after = _waste(periods[f"{year}-YTD"])
    assert (after[WET], after[DRY], after[TOTAL], after[DIVERTED]) == (1030, 192.5, 1222.5, 192.5)
    assert after["material:IRON"] == 80.5
    assert periods[f"{year}-YTD"]["values"][TOTAL]["provenance"]["months_added"] == [f"{year}-07", f"{year}-08"]
    for month in ("05", "07", "08"):
        assert _shown(periods[f"{year}-{month}"])[TOTAL] == (1222.5, f"{year} YTD", True)


def test_approved_but_unpublished_month_does_not_change_the_public_aggregate(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    _baseline(postgres_engine, tmp_path, year, end="06-30", wet="1000", materials=JAN_JUN)
    before = _timeline(postgres_engine)["periods"][f"{year}-YTD"]
    _publish(postgres_engine, year, 7, "10", {"PET": "5"}, published=False)  # prepared, never published
    after = _timeline(postgres_engine)["periods"]
    assert f"{year}-07" not in after
    assert after[f"{year}-YTD"] == before


def test_a_corrected_month_counts_once_using_its_latest_published_revision(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    _baseline(postgres_engine, tmp_path, year, end="06-30", wet="1000", materials=JAN_JUN)
    _publish(postgres_engine, year, 7, "10", {"PET": "5"}, hours_ago=5)
    _publish(postgres_engine, year, 7, "12", {"PET": "8"}, hours_ago=1)  # the correction
    ytd = _waste(_timeline(postgres_engine)["periods"][f"{year}-YTD"])
    assert (ytd[WET], ytd[DRY], ytd[TOTAL]) == (1012, 158.5, 1170.5)  # not baseline + old July + new July
    assert ytd["material:PET"] == 108


def test_a_newer_baseline_supersedes_the_older_one_and_the_months_it_covers(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    _baseline(postgres_engine, tmp_path, year, end="06-30", wet="1000", materials=JAN_JUN)
    for month, wet in ((7, "10"), (8, "20"), (9, "30")):
        _publish(postgres_engine, year, month, wet, {"PET": "5"})
    older = _waste(_timeline(postgres_engine)["periods"][f"{year}-YTD"])
    assert older[TOTAL] == 1150.5 + 15 + 25 + 35

    # A later authoritative dump now covers 1 January - 31 August.
    _baseline(postgres_engine, tmp_path, year, end="08-31", wet="2000", materials={"PET": "300", "Iron": "60"})
    periods = _timeline(postgres_engine)["periods"]
    ytd = periods[f"{year}-YTD"]
    # Jan-Aug baseline + September only: never Jan-Jun + Jul + Aug + Jan-Aug.
    assert _waste(ytd) == {
        WET: 2030, DRY: 365, "material:PET": 305, "material:IRON": 60,
        TOTAL: 2395, DIVERTED: 365, PER_PERSON: pytest.approx(2395 / POPULATION),
    }
    provenance = ytd["values"][TOTAL]["provenance"]
    assert provenance["baseline_coverage_end"] == f"{year}-08-31"
    assert provenance["baselines_superseded"] == [f"{year}-01-01..{year}-06-30"]
    assert provenance["months_added"] == [f"{year}-09"]
    assert provenance["months_excluded_overlap"] == [f"{year}-07", f"{year}-08"]
    # The superseded baseline is not offered as a second waste view either.
    views = [key for key, period in periods.items() if period["year"] == year and TOTAL in _waste(period)
             and period["granularity"] != "MONTHLY"]
    assert views == [f"{year}-YTD"]
    with Session(postgres_engine) as db:  # both baselines stay stored and verified
        rows = db.execute(
            select(HistoricalPeriod.coverage_end, HistoricalMetricValue.value_numeric)
            .join(HistoricalMetricValue, HistoricalMetricValue.period_id == HistoricalPeriod.id)
            .where(HistoricalPeriod.year == year, HistoricalMetricValue.metric_code == WET)
            .order_by(HistoricalPeriod.coverage_end)
        ).all()
        assert [(end.isoformat(), value) for end, value in rows] == [
            (f"{year}-06-30", Decimal("1000")), (f"{year}-08-31", Decimal("2000")),
        ]


def test_label_becomes_full_year_once_coverage_reaches_december(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    _baseline(postgres_engine, tmp_path, year, end="06-30", wet="1000", materials=JAN_JUN)
    for month in range(7, 12):
        _publish(postgres_engine, year, month, "1", {"PET": "1"})
    periods = _timeline(postgres_engine)["periods"]
    assert _shown(periods[f"{year}-11"])[TOTAL][1] == f"{year} YTD"  # through November only
    _publish(postgres_engine, year, 12, "1", {"PET": "1"})
    periods = _timeline(postgres_engine)["periods"]
    shown = _shown(periods[f"{year}-12"])
    assert shown[TOTAL] == (1150.5 + 12, f"{year} Full Year", True)
    assert _shown(periods[f"{year}-07"]) == shown


def test_a_year_with_only_published_months_sums_them_and_never_leaks_across_years(
    postgres_engine: Engine, tmp_path: Path, year: int
) -> None:
    _baseline(postgres_engine, tmp_path, year, end="06-30", wet="1000", materials=JAN_JUN)
    with Session(postgres_engine) as db:
        other = _unused_year(db)
    _publish(postgres_engine, other, 1, "3", {"PET": "4"})
    _publish(postgres_engine, other, 2, "5", {"PET": "6"})
    periods = _timeline(postgres_engine)["periods"]
    months_only = _waste(periods[f"{other}-YTD"])
    assert (months_only[WET], months_only[DRY], months_only[TOTAL], months_only[DIVERTED]) == (8, 10, 18, 10)
    assert PER_PERSON not in months_only  # no population reference for that year: unavailable, not guessed
    assert _shown(periods[f"{other}-01"])[TOTAL] == (18, f"{other} YTD", True)
    assert _waste(periods[f"{year}-YTD"])[TOTAL] == 1150.5
