"""Current-year water-recycled and total-waste KPIs.

Owner-confirmed "<year> / to date" figures whose source does not state an end
month are published as "<year> YTD" - never with a guessed month range. Genuine
monthly records always win, and the two representations are never added
together. Every test uses a synthetic far-future year.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.historical import importer
from app.historical.sources import parse_source
from app.historical.validator import LoadedSource, _apply_coverage_confirmations, reconcile
from app.models.enums import ReleaseStatus, RoleCode
from app.models.history import HistoricalConflict, HistoricalMetricValue, HistoricalPeriod
from app.models.publication import PublicRelease, PublicReleasePayload
from app.services.publication import payload_checksum
from tests.test_historical_integration import _energy_csv, _factor_set, _free_year, _mapping, _timeline, _write
from tests.test_publication_integration import _account

WATER, WASTE = "water_recycled_kl", "total_waste_generated_kg"


def _waste(suffix: str, year: int, end_month: int = 6) -> dict[str, Any]:
    mapping = _mapping("waste_staging", suffix)
    mapping["year_rules"] = {
        str(year): {
            "granularity": "YTD",
            "coverage_start": f"{year}-01-01",
            "coverage_end": f"{year}-{end_month:02d}-28",
            "coverage_confirmed": False,
        }
    }
    return mapping


def _water(suffix: str, year: int, end_month: int = 6) -> dict[str, Any]:
    mapping = _mapping("water_staging", suffix)
    rule = {
        "granularity": "YTD",
        "coverage_start": f"{year}-01-01",
        "coverage_end": f"{year}-{end_month:02d}-28",
        "coverage_confirmed": False,
    }
    mapping["year_rules"] = {str(year): {"recycled_period": rule, "annual_period": rule}}
    return mapping


def _confirmation(mapping: dict[str, Any], metric: str, domain: str) -> dict[str, Any]:
    rule = mapping["year_rules"][next(iter(mapping["year_rules"]))]
    rule = rule.get("recycled_period", rule)
    return {
        "id": f"confirm-{mapping['code']}-{metric}",
        "mapping_code": mapping["code"],
        "granularity": rule["granularity"],
        "coverage_start": rule["coverage_start"],
        "coverage_end": rule["coverage_end"],
        "domain": domain,
        "metric_codes": [metric],
        "coverage_end_stated": False,
        "reason": "Synthetic owner confirmation: valid current-year total; end month not stated.",
        "approved_by": "Project owner",
        "approved_at": "2026-09-30",
    }


def _import(
    engine: Engine, root: Path, mappings: list[dict[str, Any]], confirmations: list[dict[str, Any]]
) -> importer.ImportSummary:
    sources = importer.load_sources(root, mappings)
    plan = reconcile(sources, [], confirmations)
    with Session(engine) as db:
        summary = importer.run(db, sources, plan, commit=True, unit_corrections=[])
        db.commit()
    return summary


def _write_sources(root: Path, water: dict[str, Any] | None, waste: dict[str, Any] | None, year: int) -> None:
    if water is not None:
        _write(root, water, f"Water Consumption {year},,,,\nTotal Water Recyled ,470,,,\n")
    if waste is not None:
        _write(
            root,
            waste,
            f"Waste Inventory,,\n,{year},\nTotal waste Approximate ,1150,\nWet Waste Generated ,1000,\n"
            "Dry waste Generared ,150,\n",
        )


def _release(engine: Engine, year: int, month: int, water: Decimal | None, waste: Decimal | None) -> None:
    """An official published month carrying genuine monthly values (as a Manager release would)."""
    payload: dict[str, Any] = {"schema_version": "1.5", "period": {"id": str(uuid4()), "year": year, "month": month}}
    if water is not None:
        payload["water"] = {"metrics": {WATER: {"value": float(water), "unit": "KL"}}, "calculations": []}
    if waste is not None:
        payload["waste"] = {"metrics": {WASTE: {"value": float(waste), "unit": "kg"}}, "calculations": []}
    with Session(engine) as db:
        admin = _account(db, RoleCode.ADMIN)
        release = PublicRelease(
            id=uuid4(), version=f"cy-{year}-{month}-{uuid4().hex[:6]}", status=ReleaseStatus.SUPERSEDED,
            checksum_sha256=payload_checksum(payload), prepared_by=admin.id, published_by=admin.id,
            published_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db.add(release)
        db.flush()
        db.add(PublicReleasePayload(release_id=release.id, payload=payload))
        db.commit()


@pytest.fixture
def kpi_year(postgres_engine: Engine) -> int:
    with Session(postgres_engine) as db:
        chosen = _free_year(db)
        _factor_set(db, chosen)
        db.commit()
    return chosen


# ---- Governed confirmation ----------------------------------------------------


def test_confirmation_is_append_only_audited_and_never_touches_conflicts(
    postgres_engine: Engine, tmp_path: Path, kpi_year: int
) -> None:
    year = kpi_year
    suffix = uuid4().hex[:8]
    water = _water(suffix, year)
    _write_sources(tmp_path, water, None, year)
    first = _import(postgres_engine, tmp_path, [water], [])
    assert first.inserted_values >= 1
    timeline = _timeline(postgres_engine)
    assert f"{year}-YTD" not in timeline["periods"]  # unconfirmed: never public

    confirmed = _import(postgres_engine, tmp_path, [water], [_confirmation(water, WATER, "water")])
    assert (confirmed.versioned_values, confirmed.inserted_conflicts) == (1, 1)
    again = _import(postgres_engine, tmp_path, [water], [_confirmation(water, WATER, "water")])
    assert (again.versioned_values, again.inserted_conflicts, again.inserted_values) == (0, 0, 0)
    with Session(postgres_engine) as db:
        rows = db.scalars(
            select(HistoricalMetricValue).join(HistoricalPeriod)
            .where(HistoricalPeriod.year == year, HistoricalMetricValue.metric_code == WATER)
            .order_by(HistoricalMetricValue.version)
        ).all()
        assert [(row.verification_status, row.coverage_end_stated) for row in rows] == [
            ("UNVERIFIED", True), ("VERIFIED", False),
        ]
        assert rows[1].supersedes_id == rows[0].id and rows[1].source_row_id == rows[0].source_row_id
        assert rows[1].value_numeric == rows[0].value_numeric == Decimal("470")
        audit = db.scalar(
            select(HistoricalConflict).where(
                HistoricalConflict.conflict_type == "coverage_confirmation",
                HistoricalConflict.conflict_key.contains(water["code"]),
            )
        )
        assert audit is not None and audit.resolution_status == "RESOLVED"
        assert "end month not stated" in (audit.detail or "")


def test_confirmation_requires_owner_fields_and_skips_conflicted_values() -> None:
    mapping = _water("unit", 2999)
    parsed = parse_source(b"Water Consumption 2999,,,,\nTotal Water Recyled ,470,,,\n", mapping)
    source = LoadedSource(mapping, parsed, "0" * 64, "water.csv")
    incomplete = {**_confirmation(mapping, WATER, "water"), "approved_by": ""}
    with pytest.raises(ValueError, match="approved_by"):
        reconcile([source], [], [incomplete])
    plan = reconcile([source], [], [_confirmation(mapping, WATER, "water")])
    value = next(item for item in plan.values if item.observation.metric_code == WATER)
    assert (value.verification_status, value.authority_status, value.coverage_end_stated) == (
        "VERIFIED", "AUTHORITATIVE", False,
    )
    # A CONFLICT value is never confirmed away.
    conflicted = reconcile([source], [], [])
    item = next(v for v in conflicted.values if v.observation.metric_code == WATER)
    item.verification_status = "CONFLICT"
    _apply_coverage_confirmations([item], [_confirmation(mapping, WATER, "water")])
    assert item.verification_status == "CONFLICT"


# ---- Resolution ---------------------------------------------------------------


def test_confirmed_ytd_is_public_as_year_ytd_with_no_month_range(
    postgres_engine: Engine, tmp_path: Path, kpi_year: int
) -> None:
    year = kpi_year
    suffix = uuid4().hex[:8]
    # Placeholder ends differ (Jun vs Mar): neither may leak into the public label.
    water, waste = _water(suffix, year, end_month=6), _waste(suffix, year, end_month=3)
    _write_sources(tmp_path, water, waste, year)
    _import(
        postgres_engine, tmp_path, [water, waste],
        [_confirmation(water, WATER, "water"), _confirmation(waste, WASTE, "waste")],
    )
    timeline = _timeline(postgres_engine)
    options = next(item for item in timeline["selector"] if item["year"] == year)["options"]
    assert options == [{"key": f"{year}-YTD", "label": "YTD", "granularity": "YTD"}]
    ytd = timeline["periods"][f"{year}-YTD"]
    for code, expected in ((WATER, 470), (WASTE, 1150)):
        value, shown = ytd["values"][code], ytd["display"][code]
        assert value["value"] == expected and value["granularity"] == "YTD"
        assert value["coverage_label"] == f"{year} YTD" and value["months_covered"] == []
        assert value["provenance"]["coverage_end_stated"] is False
        assert shown["display_label"] == f"{year} YTD" and shown["source_granularity"] == "YTD"
        assert shown["display_context"] is False
        assert not any(month in shown["display_label"] for month in ("Jan", "Mar", "Jun", "Jul", "Full Year"))
    assert not [key for key in timeline["periods"] if key.startswith(f"{year}-YTD-")]
    # Only the two confirmed metrics became public; the rest of the source stays unverified.
    assert "wet_waste_generated_kg" not in ytd["values"] and "dry_waste_generated_kg" not in ytd["values"]


def test_month_without_monthly_value_shows_labelled_ytd_context(
    postgres_engine: Engine, tmp_path: Path, kpi_year: int
) -> None:
    year = kpi_year
    suffix = uuid4().hex[:8]
    water, waste = _water(suffix, year), _waste(suffix, year)
    energy = _mapping("energy_staging", suffix)
    _write_sources(tmp_path, water, waste, year)
    _write(tmp_path, energy, _energy_csv(year, [("March", "1", "1", "1", "1", "1", "1")]))
    _import(
        postgres_engine, tmp_path, [water, waste, energy],
        [_confirmation(water, WATER, "water"), _confirmation(waste, WASTE, "waste")],
    )
    march = _timeline(postgres_engine)["periods"][f"{year}-03"]
    assert WATER not in march["values"] and WASTE not in march["values"]  # never the month's own data
    for code, expected in ((WATER, 470), (WASTE, 1150)):
        shown = march["display"][code]
        assert (shown["value"], shown["display_label"], shown["display_context"]) == (expected, f"{year} YTD", True)


def test_exact_monthly_wins_and_is_never_added_to_the_source_ytd(
    postgres_engine: Engine, tmp_path: Path, kpi_year: int
) -> None:
    year = kpi_year
    suffix = uuid4().hex[:8]
    water, waste = _water(suffix, year), _waste(suffix, year)
    energy = _mapping("energy_staging", suffix)
    _write_sources(tmp_path, water, waste, year)
    _write(tmp_path, energy, _energy_csv(year, [("April", "1", "1", "1", "1", "1", "1")]))
    _import(
        postgres_engine, tmp_path, [water, waste, energy],
        [_confirmation(water, WATER, "water"), _confirmation(waste, WASTE, "waste")],
    )
    # Genuine monthly water: Jan 10, Feb 0 (explicit zero), no March. Waste has no monthly record.
    _release(postgres_engine, year, 1, Decimal("10"), None)
    _release(postgres_engine, year, 2, Decimal("0"), None)
    timeline = _timeline(postgres_engine)
    jan, feb = timeline["periods"][f"{year}-01"], timeline["periods"][f"{year}-02"]
    assert jan["display"][WATER]["value"] == 10 and jan["display"][WATER]["display_context"] is False
    assert feb["display"][WATER]["value"] == 0 and feb["display"][WATER]["display_label"] == f"February {year}"
    ytd = timeline["periods"][f"{year}-YTD"]
    water_ytd = ytd["values"][WATER]
    # Monthly sum through the genuine months only: 10 + 0, never + 470.
    assert water_ytd["value"] == 10
    assert water_ytd["months_covered"] == [f"{year}-01", f"{year}-02"]  # the zero month counts
    assert water_ytd["coverage_status"] == "partial"  # March/April missing, never zero
    assert water_ytd["provenance"]["source_reported_ytd_not_combined"] == 470
    assert ytd["display"][WATER]["display_label"] == f"Jan–Feb {year}"  # no 12/12 requirement
    # Water and waste resolve independently: waste has no monthly data, so its confirmed YTD shows.
    assert ytd["values"][WASTE]["value"] == 1150
    assert ytd["display"][WASTE]["display_label"] == f"{year} YTD"
    # A month without its own water value gets no partial-sum context and no source YTD (one representation).
    march = timeline["periods"].get(f"{year}-03")
    assert march is None or WATER not in march["display"]


def test_annual_context_still_applies_when_no_monthly_or_ytd_exists(
    postgres_engine: Engine, tmp_path: Path, kpi_year: int
) -> None:
    year = kpi_year
    suffix = uuid4().hex[:8]
    water = _mapping("water_staging", suffix)
    annual = {"granularity": "ANNUAL", "coverage_start": f"{year}-01-01", "coverage_end": f"{year}-12-31"}
    water["year_rules"] = {str(year): {"recycled_period": annual, "annual_period": annual}}
    energy = _mapping("energy_staging", suffix)
    _write(tmp_path, water, f"Water Consumption {year},,,,\nTotal Water Recyled ,900,,,\n")
    _write(tmp_path, energy, _energy_csv(year, [("May", "1", "1", "1", "1", "1", "1")]))
    _import(postgres_engine, tmp_path, [water, energy], [])
    may = _timeline(postgres_engine)["periods"][f"{year}-05"]["display"][WATER]
    assert (may["value"], may["display_label"], may["display_context"]) == (900, f"{year} Annual Data", True)
    assert may["source_granularity"] == "ANNUAL"
