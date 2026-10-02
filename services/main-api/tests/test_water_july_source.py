"""July 2026 water consumption source (owner-supplied, July only).

Only the three source components are imported: TWAD, borewell and
procured/private water. Total water consumed is calculated by the backend from
them; the spreadsheet's total is a reference figure and is never stored as
source data. Metrics the source does not supply stay missing, never zero.
"""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.historical import importer
from app.historical.sources import parse_source
from app.models.history import HistoricalCalculationResult, HistoricalMetricValue, HistoricalPeriod
from app.models.sustainability import InstitutionalPopulationReference
from app.services import sustainability_formulas as formulas
from tests.test_historical_integration import _free_year, _import, _timeline

MAPPING_FILE = importer.MAPPING_DIR / "water_2026_july_owner_source.json"
# Jan-Jun 2026 as already governed: (TWAD, borewell, private) -> 122905 KL in total.
JAN_TO_JUN = [("January", 3157, 17050, 8), ("February", 3410, 18876, 46), ("March", 3558, 17050, 0),
              ("April", 3568, 16500, 108), ("May", 3136, 17050, 0), ("June", 2888, 16500, 0)]
JULY = ("July", "3293", "17050", "124.27")
POPULATION = 6991


def _repo_root() -> Path | None:
    configured = os.getenv("KCOSMOS_REPO_ROOT")
    parents = Path(__file__).resolve().parents
    candidate = Path(configured) if configured else (parents[3] if len(parents) > 3 else None)
    reference = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))["source_reference"]
    return candidate if candidate is not None and (candidate / reference).exists() else None


REPO_ROOT = _repo_root()
needs_source = pytest.mark.skipif(REPO_ROOT is None, reason="repository source files are not available")


def test_total_consumption_formula_is_exact_and_treats_missing_as_missing() -> None:
    twad, borewell, private = Decimal("3293"), Decimal("17050"), Decimal("124.27")
    assert formulas.water_consumed_kl(twad, borewell, private) == Decimal("20467.27")  # 124.27 is not rounded
    assert formulas.water_consumed_kl(twad, borewell, Decimal("0")) == Decimal("20343")  # zero is a reported value
    assert formulas.water_consumed_kl(twad, borewell, None) is None  # a missing source is not zero


@needs_source
def test_owner_source_holds_only_the_three_july_components() -> None:
    assert REPO_ROOT is not None
    mapping = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    parsed = parse_source((REPO_ROOT / mapping["source_reference"]).read_bytes(), mapping)
    assert parsed.invalid == [] and parsed.ignored == []
    observed = {item.metric_code: item for item in parsed.observations}
    assert {code: item.value for code, item in observed.items()} == {
        "water_twad_kl": Decimal("3293"), "water_borewell_kl": Decimal("17050"), "water_private_kl": Decimal("124.27"),
    }
    assert {item.unit for item in observed.values()} == {"KL"}
    assert {item.qualifier for item in observed.values()} == {"EXACT"}
    # July 2026 only, as one monthly period; no August, no Jan-Jun.
    periods = {item.period for item in parsed.observations}
    assert len(periods) == 1
    period = periods.pop()
    assert (period.granularity, period.year, period.month) == ("MONTHLY", 2026, 7)
    assert (period.coverage_start, period.coverage_end) == (date(2026, 7, 1), date(2026, 7, 31))
    # The reported total, recycled water, wastewater and quality metrics are not source columns.
    assert set(mapping["columns"]) == {"water_twad_kl", "water_borewell_kl", "water_private_kl"}
    assert "20467" not in (REPO_ROOT / mapping["source_reference"]).read_text(encoding="utf-8")


def _mapping(year: int, name: str) -> dict[str, Any]:
    mapping = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    suffix = uuid4().hex[:8]
    mapping["code"] = f"{mapping['code']}_{name}_{suffix}"
    mapping["source_reference"] = f"src/water_{name}_{suffix}.csv"
    return mapping


def _write(root: Path, mapping: dict[str, Any], year: int, rows: list[tuple[Any, ...]]) -> None:
    path = root / mapping["source_reference"]
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "year,month,water_twad_kl,water_borewell_kl,water_private_kl\n"
    body = "".join(f"{year},{','.join(str(cell) for cell in row)}\n" for row in rows)
    path.write_text(header + body, encoding="utf-8")


@pytest.fixture
def water_year(postgres_engine: Engine, tmp_path: Path) -> tuple[int, dict[str, Any]]:
    """A free year holding Jan-Jun as already governed; returns the July mapping to import."""
    with Session(postgres_engine) as db:
        year = _free_year(db)
        db.add(InstitutionalPopulationReference(
            effective_year=year, population=POPULATION, unit="people", source_reference="Water July test population",
        ))
        db.commit()
    earlier = _mapping(year, "janjun")
    _write(tmp_path, earlier, year, JAN_TO_JUN)
    _import(postgres_engine, tmp_path, [earlier])
    july = _mapping(year, "july")
    _write(tmp_path, july, year, [JULY])
    return year, july


def _snapshot(engine: Engine, year: int) -> list[tuple[Any, ...]]:
    with Session(engine) as db:
        return [tuple(row) for row in db.execute(
            select(HistoricalPeriod.month, HistoricalMetricValue.metric_code, HistoricalMetricValue.value_numeric,
                   HistoricalMetricValue.version, HistoricalMetricValue.id)
            .join(HistoricalPeriod, HistoricalPeriod.id == HistoricalMetricValue.period_id)
            .where(HistoricalPeriod.year == year, HistoricalPeriod.month <= 6)
            .order_by(HistoricalPeriod.month, HistoricalMetricValue.metric_code)
        ).all()]


def test_july_import_derives_the_total_and_leaves_earlier_months_alone(
    postgres_engine: Engine, tmp_path: Path, water_year: tuple[int, dict[str, Any]]
) -> None:
    year, july = water_year
    before_rows = _snapshot(postgres_engine, year)
    before = _timeline(postgres_engine)["periods"]
    assert before[f"{year}-YTD"]["values"]["water_consumed_kl"]["value"] == 122905
    assert f"{year}-07" not in before

    summary, _ = _import(postgres_engine, tmp_path, [july])
    assert (summary.new_batches, summary.inserted_values, summary.versioned_values, summary.inserted_conflicts) == (
        1, 3, 0, 0,
    )
    again, _ = _import(postgres_engine, tmp_path, [july])  # idempotent
    assert (again.new_batches, again.inserted_values, again.versioned_values, again.inserted_conflicts) == (0, 0, 0, 0)
    assert again.inserted_calculations == 0

    periods = _timeline(postgres_engine)["periods"]
    month = periods[f"{year}-07"]["values"]
    assert (month["water_twad_kl"]["value"], month["water_twad_kl"]["kind"]) == (3293, "metric")
    assert month["water_borewell_kl"]["value"] == 17050
    assert month["water_private_kl"]["value"] == 124.27
    # The total is a backend calculation of the three components.
    assert (month["water_consumed_kl"]["value"], month["water_consumed_kl"]["kind"]) == (20467.27, "calculation")
    assert month["water_per_capita_l"]["value"] == pytest.approx(20467.27 * 1000 / POPULATION)
    # Nothing was created for metrics the source does not supply.
    for code in ("water_recycled_kl", "wastewater_generated_kl"):
        assert code not in month
    assert f"{year}-08" not in periods

    ytd = periods[f"{year}-YTD"]["values"]
    assert ytd["water_consumed_kl"]["value"] == 143372.27
    assert ytd["water_consumed_kl"]["coverage_status"] == "complete"
    assert len(ytd["water_consumed_kl"]["months_covered"]) == 7
    assert (ytd["water_twad_kl"]["value"], ytd["water_borewell_kl"]["value"], ytd["water_private_kl"]["value"]) == (
        23010, 120076, 286.27,
    )
    # Jan-Jun: same rows, same versions, same values in the public timeline.
    assert _snapshot(postgres_engine, year) == before_rows
    for month_number in range(1, 7):
        key = f"{year}-{month_number:02d}"
        assert periods[key]["values"] == before[key]["values"], key

    with Session(postgres_engine) as db:
        july_period = db.scalar(
            select(HistoricalPeriod).where(HistoricalPeriod.year == year, HistoricalPeriod.month == 7)
        )
        assert july_period is not None
        stored = set(db.scalars(
            select(HistoricalMetricValue.metric_code).where(HistoricalMetricValue.period_id == july_period.id)
        ).all())
        # The total is never stored as source data; only the three components are.
        assert stored == {"water_twad_kl", "water_borewell_kl", "water_private_kl"}
        result = db.scalar(select(HistoricalCalculationResult).where(
            HistoricalCalculationResult.period_id == july_period.id,
            HistoricalCalculationResult.calculation_code == "water_consumed_kl",
            HistoricalCalculationResult.is_current.is_(True),
        ))
        assert result is not None and result.result_value == Decimal("20467.27")
        assert {code: item["value"] for code, item in result.input_snapshot.items()} == {  # type: ignore[index]
            "water_twad_kl": "3293", "water_borewell_kl": "17050", "water_private_kl": "124.27",
        }
