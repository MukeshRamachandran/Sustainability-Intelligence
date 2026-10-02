"""2026 Community Outreach year-to-date baseline and future Manager contributions.

The owner-supplied 2026 outreach source is cumulative ("till August 17, 2026"),
not monthly. It is stored as one YTD coverage-range record with lower-bound
qualifiers. The public year-to-date value is that baseline plus the published
months that START after its coverage end, counted once each; overlapping
months, drafts, submitted and approved-but-unpublished data never contribute.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.historical import importer
from app.historical.sources import parse_source
from app.models.enums import OperationalDomain, ReleaseStatus, RoleCode
from app.models.history import HistoricalMetricValue, HistoricalPeriod
from app.models.publication import PublicRelease, PublicReleasePayload
from app.models.sustainability import OutreachProgramme
from app.services.publication import payload_checksum
from tests.test_historical_integration import _free_year, _import, _timeline
from tests.test_outreach_integration import _account as _api_account
from tests.test_outreach_integration import _client, _login, _period, _programme
from tests.test_publication_integration import _account as _db_account

MAPPING_FILE = importer.MAPPING_DIR / "outreach_2026_ytd_owner_source.json"
SUMMARY = {
    "total_programs": 20, "volunteers_engaged": 364, "volunteer_hours": 1649, "experts_involved": 34,
    "total_participants": 2009, "partner_organizations": 25, "saplings_planted": 400,
}
THEMES = {
    "biodiversity_conservation": 6, "campus_sustainability": 4, "climate_smart_agriculture": 3,
    "water_conservation": 3, "waste_management": 3, "afforestation": 2, "climate_change": 1, "hwcc": 1,
    "livelihood_development": 1,
}
AUDIENCE = {
    "school_students": 3, "college_students": 15, "farmers_agriculture": 2, "government": 0, "media_press": 0,
    "researchers_experts": 8, "entrepreneurs_startup_founders": 1, "community_general": 2,
    "international_exchange": 1, "alumni": 0,
}


def _repo_root() -> Path | None:
    configured = os.getenv("KCOSMOS_REPO_ROOT")
    parents = Path(__file__).resolve().parents
    candidate = Path(configured) if configured else (parents[3] if len(parents) > 3 else None)
    reference = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))["source_reference"]
    return candidate if candidate is not None and (candidate / reference).exists() else None


REPO_ROOT = _repo_root()
needs_source = pytest.mark.skipif(REPO_ROOT is None, reason="repository source files are not available")


# ---- The real source artifact (no database) -----------------------------------


@needs_source
def test_owner_source_is_one_ytd_coverage_range_with_lower_bounds() -> None:
    assert REPO_ROOT is not None
    mapping = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    parsed = parse_source((REPO_ROOT / mapping["source_reference"]).read_bytes(), mapping)
    assert parsed.invalid == [] and parsed.ignored == []
    observations = {item.metric_code: item for item in parsed.observations}
    assert len(parsed.observations) == len(observations) == 7 + 9 + 10

    # One period only: YTD, 1 Jan - 17 Aug 2026. Never a month, never August.
    periods = {item.period for item in parsed.observations}
    assert len(periods) == 1
    period = periods.pop()
    assert (period.granularity, period.month) == ("YTD", None)
    assert (period.coverage_start, period.coverage_end) == (date(2026, 1, 1), date(2026, 8, 17))

    # "+" is a lower bound: the number is kept with the AT_LEAST qualifier.
    for code, value in SUMMARY.items():
        assert (observations[code].value, observations[code].qualifier) == (Decimal(value), "AT_LEAST"), code
    # The thematic table keeps its own counts: 24 in total, never overwriting 20+ programmes.
    themes = {code: observations[f"theme:{code}"] for code in THEMES}
    assert {code: int(item.value) for code, item in themes.items()} == THEMES
    assert sum(int(item.value) for item in themes.values()) == 24
    assert observations["total_programs"].value == Decimal(20)
    assert {item.unit for item in themes.values()} == {"programmes"}
    assert all("not the unique programme count" in " ".join(item.notes) for item in themes.values())
    # Audience values are source counts, not people reached; explicit zeros are kept.
    audience = {code: observations[f"audience:{code}"] for code in AUDIENCE}
    assert {code: int(item.value) for code, item in audience.items()} == AUDIENCE
    assert {item.unit for item in audience.values()} == {"count"}
    assert all("Not a participant count" in " ".join(item.notes) for item in audience.values())
    assert sum(int(item.value) for item in audience.values()) == 32
    # No gender figure exists in the source, so none is produced.
    assert not [code for code in observations if code.startswith("gender")]


# ---- Import and public timeline on an isolated year (PostgreSQL) --------------


def _baseline_mapping(year: int) -> dict[str, Any]:
    """The governed mapping, re-pointed at a free test year (same rows, same rules)."""
    mapping = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    suffix = uuid4().hex[:8]
    mapping["code"] = f"{mapping['code']}_{suffix}"
    mapping["source_reference"] = f"src/outreach_{suffix}.csv"
    mapping["year_rules"] = {
        str(year): {"granularity": "YTD", "coverage_start": f"{year}-01-01", "coverage_end": f"{year}-08-17"}
    }
    return mapping


def _source_text(year: int) -> str:
    lines = [f"Coverage,{year}-01-01 to {year}-08-17", "Summary,", "Metric,Reported figure", f",{year}",
             "Outreach Programs / Events,20+", "Volunteers Engaged,364+", 'Volunteering Hours,"1,649+"',
             "Experts Involved,34+", 'Total Participants / Reach,"2,009+"',
             "Partner Organizations / Collaborations,25+", "Saplings / Seedlings,400+", ",",
             "Thematic Counts,", "Category,Count", f",{year}", "Biodiversity Conservation,6",
             "Campus Sustainability,4", "Climate Smart Agriculture,3", "Water Conservation,3", "Waste Management,3",
             "Afforestation,2", "Climate Change,1", "Human-Wildlife Conflict,1", "Livelihood Development,1", ",",
             "Audience Counts,", "Audience category,Count", f",{year}", "School Students,3", "College Students,15",
             "Farmers / Agriculture,2", "Government / Forest,0", "Media / Press,0", "Researchers / Experts,8",
             "Entrepreneurs / Startup,1", "Community / General,2", "International / Exchange,1", "Alumni,0"]
    return "\n".join(lines) + "\n"


def _import_baseline(engine: Engine, tmp_path: Path, year: int) -> int:
    mapping = _baseline_mapping(year)
    path = tmp_path / mapping["source_reference"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_source_text(year), encoding="utf-8")
    summary, _ = _import(engine, tmp_path, [mapping])
    assert (summary.new_batches, summary.inserted_values, summary.inserted_conflicts) == (1, 26, 0)
    again, _ = _import(engine, tmp_path, [mapping])  # idempotent
    assert (again.new_batches, again.inserted_values, again.versioned_values, again.inserted_conflicts) == (0, 0, 0, 0)
    return year


@pytest.fixture
def baseline_year(postgres_engine: Engine, tmp_path: Path) -> int:
    with Session(postgres_engine) as db:
        year = _free_year(db)
    return _import_baseline(postgres_engine, tmp_path, year)


def _release(
    engine: Engine, year: int, month: int, outreach: dict[str, Any], *, hours_ago: int = 1
) -> None:
    """An official published month carrying the outreach aggregate a Manager release would."""
    payload: dict[str, Any] = {
        "schema_version": "1.5", "period": {"id": str(uuid4()), "year": year, "month": month}, "outreach": outreach,
    }
    with Session(engine) as db:
        admin = _db_account(db, RoleCode.ADMIN)
        release = PublicRelease(
            id=uuid4(), version=f"outreach-{year}-{month}-{uuid4().hex[:6]}", status=ReleaseStatus.SUPERSEDED,
            checksum_sha256=payload_checksum(payload), prepared_by=admin.id, published_by=admin.id,
            published_at=datetime.now(UTC) - timedelta(hours=hours_ago),
        )
        db.add(release)
        db.flush()
        db.add(PublicReleasePayload(release_id=release.id, payload=payload))
        db.commit()


def _month(programs: int, participants: int, *, gender: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "total_programs": programs, "total_participants": participants, "partner_organizations": 3,
        "saplings_planted": 50, "experts_involved": 4, "volunteers_engaged": 10, "volunteer_hours": 25.5,
        "themes": {"water_conservation": programs, "climate_change": 0},
        "participants_by_category": {"college_students": participants, "school_students": 0},
        "gender": {"available": gender is not None, **(gender or {"male": None, "female": None,
                                                                   "other_not_disclosed": None})},
    }


def _ytd(engine: Engine, year: int) -> dict[str, Any]:
    return _timeline(engine)["periods"][f"{year}-YTD"]


def test_baseline_alone_is_a_ytd_value_never_a_month(postgres_engine: Engine, baseline_year: int) -> None:
    year = baseline_year
    timeline = _timeline(postgres_engine)
    # No monthly period exists for the year: nothing was spread over months or put into August.
    assert not [key for key in timeline["periods"] if key.startswith(f"{year}-") and key[5:7].isdigit()]
    assert [option["key"] for item in timeline["selector"] if item["year"] == year for option in item["options"]] == [
        f"{year}-YTD"
    ]
    ytd = timeline["periods"][f"{year}-YTD"]
    assert ytd["granularity"] == "YTD"
    assert (ytd["coverage_start"], ytd["coverage_end"]) == (f"{year}-01-01", f"{year}-08-17")
    label = f"{year} YTD"  # public label; the exact coverage stays in the provenance
    for code, value in SUMMARY.items():
        item = ytd["values"][code]
        assert (item["value"], item["qualifier"], item["granularity"]) == (value, "AT_LEAST", "YTD"), code
        assert item["coverage_label"] == label and item["months_covered"] == []
        assert item["provenance"]["baseline_coverage_start"] == f"{year}-01-01"
        assert item["provenance"]["baseline_coverage_end"] == f"{year}-08-17"
        assert "17 Aug" not in item["coverage_label"]
        assert ytd["display"][code]["display_label"] == label
        assert ytd["display"][code]["qualifier"] == "AT_LEAST"
    assert {code: ytd["values"][f"theme:{code}"]["value"] for code in THEMES} == THEMES
    assert ytd["values"]["total_programs"]["value"] == 20  # not replaced by the thematic total of 24
    assert {ytd["values"][f"audience:{code}"]["unit"] for code in AUDIENCE} == {"count"}
    assert ytd["values"]["audience:government"]["value"] == 0  # an explicit zero is a reported value
    assert not [code for code in ytd["values"] if code.startswith("gender")]  # none supplied, none invented
    assert ytd["domains"]["outreach"]["state"] == "available"

    with Session(postgres_engine) as db:
        stored = db.execute(
            select(HistoricalPeriod.granularity, HistoricalPeriod.month, HistoricalPeriod.coverage_start,
                   HistoricalPeriod.coverage_end, func.count(HistoricalMetricValue.id))
            .join(HistoricalMetricValue, HistoricalMetricValue.period_id == HistoricalPeriod.id)
            .where(HistoricalPeriod.year == year)
            .group_by(HistoricalPeriod.id)
        ).all()
        # One YTD coverage-range period holding all 26 values, exactly once.
        assert stored == [("YTD", None, date(year, 1, 1), date(year, 8, 17), 26)]
        # No programme record was fabricated from the historical totals.
        fabricated = db.scalar(select(func.count(OutreachProgramme.id)).where(
            OutreachProgramme.programme_date >= date(year, 1, 1), OutreachProgramme.programme_date <= date(year, 12, 31)
        ))
        assert fabricated == 0


def test_later_months_extend_the_baseline_exactly_once(postgres_engine: Engine, baseline_year: int) -> None:
    year = baseline_year
    _release(postgres_engine, year, 9, _month(2, 300, gender={"male": 120, "female": 170, "other_not_disclosed": 10}))
    ytd = _ytd(postgres_engine, year)["values"]
    assert ytd["total_participants"]["value"] == 2009 + 300
    assert ytd["total_participants"]["qualifier"] == "AT_LEAST"  # still a lower bound
    assert ytd["total_participants"]["coverage_label"] == f"{year} YTD"
    assert ytd["total_participants"]["provenance"]["months_added"] == [f"{year}-09"]
    assert ytd["total_programs"]["value"] == 22
    assert ytd["volunteers_engaged"]["value"] == 374
    assert ytd["volunteer_hours"]["value"] == 1674.5
    assert ytd["experts_involved"]["value"] == 38
    assert ytd["saplings_planted"]["value"] == 450
    assert ytd["theme:water_conservation"]["value"] == 3 + 2  # a programme's theme extends its theme count
    # A distinct organisation count is not added to a cumulative baseline.
    assert ytd["partner_organizations"]["value"] == 25
    assert ytd["partner_organizations"]["provenance"]["months_not_combined"] == [f"{year}-09"]
    # Participant counts by category are people; the baseline audience table is not. Never mixed.
    assert (ytd["audience:college_students"]["value"], ytd["audience:college_students"]["unit"]) == (15, "count")
    assert ytd["audience:college_students"]["provenance"]["months_not_combined"] == [f"{year}-09"]
    # The release payload above carries a legacy gender block; it is never exposed.
    assert not [code for code in ytd if code.startswith("gender")]

    _release(postgres_engine, year, 10, _month(1, 150))
    ytd = _ytd(postgres_engine, year)["values"]
    assert ytd["total_participants"]["value"] == 2009 + 300 + 150
    assert ytd["total_programs"]["value"] == 23
    assert ytd["total_participants"]["coverage_label"] == f"{year} YTD"
    assert ytd["total_participants"]["provenance"]["months_added"] == [f"{year}-09", f"{year}-10"]
    assert _ytd(postgres_engine, year)["values"]["total_participants"]["value"] == 2459  # stable on re-read

    # The months themselves stay genuine monthly records.
    september = _timeline(postgres_engine)["periods"][f"{year}-09"]["values"]
    assert september["total_participants"]["value"] == 300
    assert september["total_participants"]["granularity"] == "MONTHLY"


def test_a_corrected_month_replaces_its_earlier_release(postgres_engine: Engine, baseline_year: int) -> None:
    year = baseline_year
    _release(postgres_engine, year, 9, _month(2, 300), hours_ago=5)  # original September
    _release(postgres_engine, year, 10, _month(1, 150), hours_ago=4)
    assert _ytd(postgres_engine, year)["values"]["total_participants"]["value"] == 2009 + 300 + 150
    _release(postgres_engine, year, 9, _month(3, 320), hours_ago=1)  # corrected September, published later
    ytd = _ytd(postgres_engine, year)["values"]
    # baseline + corrected September + October; the superseded September is not counted as well.
    assert ytd["total_participants"]["value"] == 2009 + 320 + 150
    assert ytd["total_programs"]["value"] == 20 + 3 + 1
    assert ytd["total_participants"]["provenance"]["months_added"] == [f"{year}-09", f"{year}-10"]


def test_a_month_overlapping_the_baseline_is_not_added(postgres_engine: Engine, baseline_year: int) -> None:
    year = baseline_year
    # A full-August release overlaps coverage that already runs through 17 August.
    _release(postgres_engine, year, 8, _month(5, 900))
    _release(postgres_engine, year, 3, _month(4, 700))  # so does any earlier month
    ytd = _ytd(postgres_engine, year)["values"]
    assert ytd["total_participants"]["value"] == 2009
    assert ytd["total_programs"]["value"] == 20
    assert ytd["total_participants"]["provenance"]["months_excluded_overlap"] == [f"{year}-03", f"{year}-08"]
    assert ytd["total_participants"]["provenance"]["months_added"] == []
    assert ytd["total_participants"]["coverage_label"] == f"{year} YTD"
    # The August month still exists as its own genuine monthly record.
    august = _timeline(postgres_engine)["periods"][f"{year}-08"]["values"]
    assert august["total_participants"]["value"] == 900


def test_draft_submitted_and_unpublished_approved_programmes_do_not_reach_the_public_ytd(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    # Manager reporting periods are limited to realistic years, so this scenario
    # takes its own September period and imports the baseline for that year.
    period = _period(postgres_engine, 2101 + int(uuid4().int % 60), 9)
    year = period.year
    with Session(postgres_engine) as db:
        assert db.scalar(select(func.count(HistoricalPeriod.id)).where(HistoricalPeriod.year == year)) == 0
    _import_baseline(postgres_engine, tmp_path, year)
    manager = _api_account(postgres_engine, RoleCode.MANAGER, OperationalDomain.OUTREACH)
    admin = _api_account(postgres_engine, RoleCode.ADMIN)

    def participants() -> Any:
        return _ytd(postgres_engine, year)["values"]["total_participants"]["value"]

    with _client(postgres_engine, period) as client:
        headers = {"X-CSRF-Token": _login(client, manager)}
        created = client.post("/api/manager/outreach/programmes", json=_programme(period), headers=headers)
        assert created.status_code == 201, created.text
        submission_id = created.json()["submission_id"]
        assert participants() == 2009  # draft
        submitted = client.post(f"/api/manager/outreach/submissions/{submission_id}/submit", headers=headers)
        assert submitted.status_code == 200, submitted.text
        assert participants() == 2009  # submitted, not approved
    with _client(postgres_engine) as admin_client:
        admin_headers = {"X-CSRF-Token": _login(admin_client, admin)}
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/begin-review", headers=admin_headers
        ).status_code == 200
        assert participants() == 2009  # under review
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/approve", headers=admin_headers
        ).status_code == 200
    # Approved but not published: the public timeline changes only through a published release.
    assert participants() == 2009
    assert f"{year}-09" not in _timeline(postgres_engine)["periods"]


# ---- Running YTD: every month of the year shows the same outreach dataset ------


def _energy_month(engine: Engine, year: int, month: int, grid_kwh: int, outreach: dict[str, Any] | None = None) -> None:
    """A published month with its own genuine energy value (and optionally outreach)."""
    payload: dict[str, Any] = {
        "schema_version": "1.5", "period": {"id": str(uuid4()), "year": year, "month": month},
        "energy": {"metrics": {"grid_total_kwh": {"value": grid_kwh, "unit": "kWh"}}, "calculations": []},
    }
    if outreach is not None:
        payload["outreach"] = outreach
    with Session(engine) as db:
        admin = _db_account(db, RoleCode.ADMIN)
        release = PublicRelease(
            id=uuid4(), version=f"running-{year}-{month}-{uuid4().hex[:6]}", status=ReleaseStatus.SUPERSEDED,
            checksum_sha256=payload_checksum(payload), prepared_by=admin.id, published_by=admin.id,
            published_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db.add(release)
        db.flush()
        db.add(PublicReleasePayload(release_id=release.id, payload=payload))
        db.commit()


def _outreach_display(period: dict[str, Any]) -> dict[str, Any]:
    return {code: item for code, item in period["display"].items() if item["domain"] == "outreach"}


def test_every_month_of_the_year_shows_the_same_running_outreach_ytd(
    postgres_engine: Engine, baseline_year: int
) -> None:
    year = baseline_year
    months = {1: 100, 4: 400, 7: 700, 8: 800, 12: 1200}
    for month, grid in months.items():
        _energy_month(postgres_engine, year, month, grid)
    periods = _timeline(postgres_engine)["periods"]
    ytd = periods[f"{year}-YTD"]
    expected = _outreach_display(ytd)
    assert expected["total_participants"]["value"] == 2009

    for month, grid in months.items():
        period = periods[f"{year}-{month:02d}"]
        # The month points at the year's YTD outreach instead of hiding outreach.
        assert period["domains"]["outreach"]["state"] == "year_to_date", month
        assert period["domains"]["outreach"]["alternative_key"] == f"{year}-YTD"
        shown = _outreach_display(period)
        assert set(shown) == set(expected), month
        for code, item in shown.items():
            assert item["value"] == expected[code]["value"], (month, code)
            assert item["qualifier"] == expected[code]["qualifier"], (month, code)
            assert item["display_label"] == f"{year} YTD"  # not "through 17 Aug", not the month
            assert item["display_context"] is True and item["source_key"] == f"{year}-YTD"
            assert item["source_granularity"] == "YTD"
        assert shown["total_programs"]["value"] == 20 and shown["total_programs"]["qualifier"] == "AT_LEAST"
        assert {code: shown[f"theme:{code}"]["value"] for code in THEMES} == THEMES
        assert shown["audience:college_students"]["unit"] == "count"
        assert not [code for code in shown if code.startswith("gender")]
        # No monthly outreach figure was created: the month's own values hold none.
        assert not [code for code, value in period["values"].items() if value["domain"] == "outreach"], month
        # Other domains stay selected-month sensitive.
        assert period["values"]["grid_total_kwh"]["value"] == grid
        assert period["display"]["grid_total_kwh"]["value"] == grid
        assert period["display"]["grid_total_kwh"]["display_context"] is False
    grid_shown = {periods[f"{year}-{month:02d}"]["display"]["grid_total_kwh"]["value"] for month in months}
    assert len(grid_shown) == len(months)

    with Session(postgres_engine) as db:
        # Still exactly one YTD coverage record in history, with its provenance intact.
        stored = db.execute(
            select(HistoricalPeriod.granularity, HistoricalPeriod.coverage_start, HistoricalPeriod.coverage_end)
            .where(HistoricalPeriod.year == year)
        ).all()
        assert stored == [("YTD", date(year, 1, 1), date(year, 8, 17))]
        qualifiers = dict(db.execute(
            select(HistoricalMetricValue.metric_code, HistoricalMetricValue.value_qualifier)
            .join(HistoricalPeriod, HistoricalPeriod.id == HistoricalMetricValue.period_id)
            .where(HistoricalPeriod.year == year, HistoricalMetricValue.metric_code.in_(list(SUMMARY)))
        ).all())
        assert set(qualifiers.values()) == {"AT_LEAST"} and len(qualifiers) == 7


def test_a_later_publication_changes_every_month_view_of_the_year(
    postgres_engine: Engine, baseline_year: int
) -> None:
    year = baseline_year
    for month in (1, 4, 7, 12):
        _energy_month(postgres_engine, year, month, month * 10)
    _energy_month(postgres_engine, year, 9, 90, _month(2, 300))

    def participants() -> dict[str, Any]:
        periods = _timeline(postgres_engine)["periods"]
        return {key[5:]: periods[key]["display"]["total_participants"] for key in periods if key.startswith(f"{year}-")}

    after_september = participants()
    assert set(after_september) == {"YTD", "01", "04", "07", "09", "12"}
    # Jan, Apr, Jul, Sep, Dec and the YTD view all show the same running figure.
    assert {item["value"] for item in after_september.values()} == {2309}
    assert {item["qualifier"] for item in after_september.values()} == {"AT_LEAST"}
    assert {item["display_label"] for item in after_september.values()} == {f"{year} YTD"}

    _energy_month(postgres_engine, year, 10, 100, _month(1, 150))
    after_october = participants()
    assert set(after_october) == {"YTD", "01", "04", "07", "09", "10", "12"}
    assert {item["value"] for item in after_october.values()} == {2459}

    periods = _timeline(postgres_engine)["periods"]
    september = periods[f"{year}-09"]
    # September SHOWS the running YTD, never its own 300 as if it were the year's figure...
    assert september["display"]["total_participants"]["value"] == 2459
    assert september["display"]["total_participants"]["display_context"] is True
    assert september["domains"]["outreach"]["state"] == "year_to_date"
    # ...while its genuine monthly record is kept as recorded.
    assert september["values"]["total_participants"]["value"] == 300
    assert september["values"]["total_participants"]["granularity"] == "MONTHLY"
    # The thematic distribution shown is the YTD one in every month.
    assert {periods[f"{year}-{m}"]["display"]["theme:water_conservation"]["value"] for m in ("01", "09", "12")} == {6}
    # Partner organisations stay at the conservative baseline.
    assert september["display"]["partner_organizations"]["value"] == 25


def test_running_ytd_never_leaks_into_another_year(postgres_engine: Engine, baseline_year: int) -> None:
    year = baseline_year
    _energy_month(postgres_engine, year, 3, 30)
    _energy_month(postgres_engine, year + 1, 3, 31)  # the next year has no outreach at all
    periods = _timeline(postgres_engine)["periods"]
    assert periods[f"{year}-03"]["domains"]["outreach"]["state"] == "year_to_date"
    other = periods[f"{year + 1}-03"]
    assert other["domains"]["outreach"]["state"] == "unavailable"
    assert not _outreach_display(other)
