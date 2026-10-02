"""Community Outreach no longer has a gender breakdown.

Owner decision (2026-10-02): the institution has no sufficiently reliable
gender-disaggregated outreach data, so gender is removed from the active
product - Manager entry, Admin review, aggregation, publication and the public
timeline. Nothing is destroyed: the three legacy columns stay in the database
for older programme rows, and frozen release payloads are never rewritten.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.historical.resolver import build_timeline
from app.models.enums import OperationalDomain, RoleCode, SubmissionStatus
from app.models.sustainability import OutreachProgramme, Submission
from app.schemas.outreach import OutreachProgrammeResponse, OutreachProgrammeWrite
from app.services.outreach import aggregate_approved_outreach
from tests.test_outreach_integration import _account, _client, _login, _period, _programme
from tests.test_outreach_ytd_baseline import _month, _release, baseline_year  # noqa: F401  (fixture)

GENDER_FIELDS = ("male_participants", "female_participants", "other_not_disclosed_participants")


def _has_gender(value: Any) -> bool:
    """True when any key or string anywhere in a JSON-like structure mentions gender."""
    if isinstance(value, dict):
        return any(
            "gender" in str(key).lower() or key in GENDER_FIELDS or _has_gender(item) for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_has_gender(item) for item in value)
    return False


def test_gender_is_not_part_of_the_active_outreach_contract() -> None:
    for model in (OutreachProgrammeWrite, OutreachProgrammeResponse):
        assert not set(GENDER_FIELDS) & set(model.model_fields), model.__name__
        assert not [name for name in model.model_fields if "gender" in name]
    # The legacy columns still exist on the table - kept for audit, not used.
    assert set(GENDER_FIELDS) <= set(OutreachProgramme.__table__.columns.keys())


def test_programme_without_gender_goes_from_draft_to_approved_with_the_right_total(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2073, 3)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.OUTREACH)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    payload = _programme(period)
    assert not set(GENDER_FIELDS) & set(payload)  # nothing about gender is sent, not even nulls or zeros
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        created = client.post("/api/manager/outreach/programmes", json=payload, headers={"X-CSRF-Token": csrf})
        assert created.status_code == 201, created.text
        body = created.json()
        # The participant total is the sum of the participant categories (100 + 50).
        assert body["participant_total"] == 150
        assert not _has_gender(body)
        # A request that still carries a gender field is not accepted as programme data.
        legacy = client.post(
            "/api/manager/outreach/programmes",
            json={**_programme(period, "Programme with gender"), "male_participants": 10},
            headers={"X-CSRF-Token": csrf},
        )
        assert legacy.status_code == 422
        submission_id = body["submission_id"]
        submitted = client.post(
            f"/api/manager/outreach/submissions/{submission_id}/submit", headers={"X-CSRF-Token": csrf}
        )
        assert submitted.status_code == 200, submitted.text
        assert not _has_gender(client.get("/api/manager/outreach/programmes").json())
        assert not _has_gender(client.get("/api/manager/outreach/submissions").json())
    with _client(postgres_engine, period) as admin_client:
        admin_csrf = _login(admin_client, admin)
        queue = admin_client.get("/api/admin/review-queue?domain=outreach").json()
        assert any(item["id"] == submission_id for item in queue)
        detail = admin_client.get(f"/api/admin/submissions/{submission_id}")
        assert detail.status_code == 200 and not _has_gender(detail.json())
        approved = admin_client.post(
            f"/api/admin/submissions/{submission_id}/approve", headers={"X-CSRF-Token": admin_csrf}
        )
        assert approved.status_code == 200, approved.text
    with Session(postgres_engine) as db:
        submission = db.get(Submission, submission_id)
        assert submission is not None and submission.status is SubmissionStatus.APPROVED
        stored = db.scalar(select(OutreachProgramme).where(OutreachProgramme.submission_id == submission.id))
        assert stored is not None and stored.participant_total == 150
        # No placeholder values were written for the removed fields.
        assert [getattr(stored, name) for name in GENDER_FIELDS] == [None, None, None]
        # What a future release would freeze for this month has no gender block.
        aggregate = aggregate_approved_outreach(db, period.id)
        assert aggregate["total_participants"] == 150
        assert aggregate["participants_by_category"]["school_students"] == 100
        assert not _has_gender(aggregate)


def test_an_old_programme_with_gender_stays_readable_and_is_never_rewritten(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2073, 4)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.OUTREACH)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        created = client.post(
            "/api/manager/outreach/programmes", json=_programme(period), headers={"X-CSRF-Token": csrf}
        ).json()
        # Simulate a programme recorded before the removal: it carries a gender split.
        with Session(postgres_engine) as db:
            row = db.get(OutreachProgramme, created["id"])
            assert row is not None
            row.male_participants, row.female_participants, row.other_not_disclosed_participants = 60, 80, 10
            db.commit()
        fetched = client.get(f"/api/manager/outreach/programmes/{created['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["participant_total"] == 150 and not _has_gender(fetched.json())
        # Editing the programme today leaves the stored legacy values exactly as they were.
        update = {key: value for key, value in _programme(period).items() if key != "reporting_period_id"}
        update["programme_description"] = "Edited after the gender breakdown was removed."
        update["expected_row_version"] = fetched.json()["row_version"]
        edited = client.put(
            f"/api/manager/outreach/programmes/{created['id']}", json=update, headers={"X-CSRF-Token": csrf}
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["participant_total"] == 150
    with Session(postgres_engine) as db:
        row = db.get(OutreachProgramme, created["id"])
        assert row is not None
        assert (row.male_participants, row.female_participants, row.other_not_disclosed_participants) == (60, 80, 10)
        assert row.programme_description == "Edited after the gender breakdown was removed."
        # (test_publication_integration covers an approved legacy row: its release has no gender block.)


def test_a_legacy_release_gender_block_never_reaches_the_public_timeline(
    postgres_engine: Engine, baseline_year: int  # noqa: F811
) -> None:
    year = baseline_year
    # A release frozen before the removal carries a gender block in its payload.
    _release(postgres_engine, year, 9, _month(2, 300, gender={"male": 120, "female": 170, "other_not_disclosed": 10}))
    with Session(postgres_engine) as db:
        timeline = build_timeline(db)
    periods = {key: period for key, period in timeline["periods"].items() if period["year"] == year}
    assert f"{year}-09" in periods
    for key, period in periods.items():
        assert not [code for code in period["values"] if "gender" in code], key
        assert not [code for code in period.get("display", {}) if "gender" in code], key
    # The outreach figures themselves are unaffected: baseline + the published month.
    ytd = periods[f"{year}-YTD"]["values"]
    assert ytd["total_participants"]["value"] == 2009 + 300
    assert ytd["total_programs"]["value"] == 20 + 2
