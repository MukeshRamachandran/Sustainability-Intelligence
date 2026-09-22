import calendar
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.bootstrap import AccountSpec, create_account
from app.core.config import Settings
from app.main import create_app
from app.models.enums import OperationalDomain, ReleaseStatus, RoleCode, SubmissionStatus
from app.models.identity import User
from app.models.publication import PublicRelease
from app.models.sustainability import (
    CalculationResult,
    MetricDefinition,
    OutreachProgramme,
    ReportingPeriod,
    Submission,
    SubmissionValue,
)
from app.services.publication import build_release_payload, payload_checksum
from tests.integration_support import unique_username

PASSWORD = "Publication-Test-Local!"


def _account(db: Session, role: RoleCode, domain: OperationalDomain | None = None) -> User:
    username = unique_username(f"publication-{role.value}-{domain or 'admin'}")
    user = create_account(
        db,
        AccountSpec(username, f"PRIVATE {domain or 'admin'} user", role, domain, email=f"{username}@private.invalid"),
        PASSWORD,
        must_change=False,
    )
    db.flush()
    return user


def _period(db: Session, year: int = 2200, month: int = 5) -> ReportingPeriod:
    while db.scalar(select(ReportingPeriod.id).where(ReportingPeriod.year == year, ReportingPeriod.month == month)):
        year += 1
    period = ReportingPeriod(
        year=year,
        month=month,
        period_start=date(year, month, 1),
        period_end=date(year, month, calendar.monthrange(year, month)[1]),
        is_open=True,
    )
    db.add(period)
    db.flush()
    return period


def _submission(
    db: Session,
    period: ReportingPeriod,
    manager: User,
    domain: OperationalDomain,
    status: SubmissionStatus,
    values: dict[str, Decimal | int] | None = None,
    *,
    approved_by: User | None = None,
) -> Submission:
    submission = Submission(
        domain=domain,
        manager_user_id=manager.id,
        reporting_period_id=period.id,
        status=SubmissionStatus.DRAFT,
        remarks="PRIVATE manager note",
    )
    db.add(submission)
    db.flush()
    definitions = {
        item.code: item
        for item in db.scalars(
            select(MetricDefinition).where(MetricDefinition.code.in_(list((values or {}).keys())))
        ).all()
    }
    for code, value in (values or {}).items():
        db.add(
            SubmissionValue(
                submission_id=submission.id,
                metric_code=code,
                value=value,
                canonical_unit=definitions[code].canonical_unit,
                quality_note="PRIVATE quality note",
            )
        )
    db.flush()
    submission.status = status
    if status == SubmissionStatus.APPROVED:
        if approved_by is None:
            raise ValueError("approved submissions require an approving admin")
        _approve(submission, approved_by)
    db.flush()
    return submission


def _approve(submission: Submission, admin: User) -> None:
    submission.status = SubmissionStatus.APPROVED
    submission.approved_at = datetime.now(UTC)
    submission.approved_by = admin.id


def _outreach_programme(db: Session, submission: Submission, period: ReportingPeriod) -> None:
    db.add(
        OutreachProgramme(
            submission_id=submission.id,
            programme_name="Public programme",
            programme_date=date(period.year, period.month, 10),
            theme="climate_change",
            partner_organisation="Partner One",
            programme_location="PRIVATE location",
            programme_description="PRIVATE evidence path /files/evidence.pdf",
            school_students=12,
            college_students=8,
            male_participants=10,
            female_participants=10,
            saplings_planted=3,
            waste_collected_kg=Decimal("9.50"),
            species_identified_count=1,
            species_details=[{"species_name": "PRIVATE species", "count": 1}],
            species_verification_notes="PRIVATE verification",
            experts_involved=2,
            volunteers_engaged=4,
            volunteer_hours=Decimal("2.50"),
            remarks="PRIVATE outreach note",
        )
    )
    db.flush()


def _client(engine: Engine) -> TestClient:
    settings = Settings(APP_ENV="test", DATABASE_URL=str(engine.url), EVIDENCE_ROOT=".local/test-evidence")
    return TestClient(create_app(settings, engine))


def _login(client: TestClient, username: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return response.headers["x-csrf-token"]


def _prepare(client: TestClient, csrf: str, period: ReportingPeriod, version: str) -> dict[str, object]:
    response = client.post(
        "/api/admin/releases/prepare",
        json={"reporting_period_id": str(period.id), "version": version},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize(
    "status",
    [
        SubmissionStatus.DRAFT,
        SubmissionStatus.SUBMITTED,
        SubmissionStatus.UNDER_REVIEW,
        SubmissionStatus.CORRECTION_REQUESTED,
        SubmissionStatus.SUPERSEDED,
    ],
)
def test_unapproved_submission_statuses_are_missing(postgres_engine: Engine, status: SubmissionStatus) -> None:
    with Session(postgres_engine) as db:
        period = _period(db, 2150 + list(SubmissionStatus).index(status))
        manager = _account(db, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
        _submission(
            db,
            period,
            manager,
            OperationalDomain.TRANSPORT,
            status,
            {"transport_petrol_litres": 999},
        )
        payload = build_release_payload(db, period)
        assert payload["transport"] is None
        assert payload["publication_status"]["transport"] == "missing_approved_submission"  # type: ignore[index]


def test_multidomain_release_snapshot_privacy_checksum_and_publish(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db:
        period = _period(db, 2160)
        admin = _account(db, RoleCode.ADMIN)
        managers = {domain: _account(db, RoleCode.MANAGER, domain) for domain in OperationalDomain}
        transport = _submission(
            db,
            period,
            managers[OperationalDomain.TRANSPORT],
            OperationalDomain.TRANSPORT,
            SubmissionStatus.APPROVED,
            {
                "transport_petrol_litres": 10,
                "transport_diesel_litres": 20,
                "petrol_vehicle_count": 99,
                "dg_diesel_litres": 30,
            },
            approved_by=admin,
        )
        energy = _submission(
            db,
            period,
            managers[OperationalDomain.ENERGY],
            OperationalDomain.ENERGY,
            SubmissionStatus.APPROVED,
            {
                "grid_ht_kwh": 10,
                "grid_commercial_kwh": 20,
                "grid_temporary_kwh": 0,
                "renewable_on_campus_kwh": 2,
                "renewable_procured_kwh": 3,
                "solar_water_heater_kwh": 5,
            },
            approved_by=admin,
        )
        lpg = _submission(
            db,
            period,
            managers[OperationalDomain.LPG],
            OperationalDomain.LPG,
            SubmissionStatus.APPROVED,
            {"lpg_cylinder_count": 2, "lpg_weight_kg": 28, "lpg_consumption_litres": 52},
            approved_by=admin,
        )
        db.add_all(
            [
                CalculationResult(
                    submission_id=transport.id,
                    submission_revision=1,
                    calculation_code="transport_petrol_emissions",
                    calculation_status="available",
                    metric_code="transport_petrol_litres",
                    activity_value=Decimal("10"),
                    activity_unit="L",
                    factor_set_version="synthetic-publication-test-v1",
                    factor_code="PETROL",
                    factor_value=Decimal("2.388"),
                    factor_unit="kgCO2e/L",
                    result_kgco2e=Decimal("23.88"),
                    result_value=Decimal("0.02388"),
                    result_unit="tCO2e",
                    formula_version="activity_x_factor_kgco2e_v1",
                ),
                CalculationResult(
                    submission_id=energy.id,
                    submission_revision=1,
                    calculation_code="grid_electricity_emissions",
                    calculation_status="available",
                    metric_code="grid_total_kwh",
                    activity_value=Decimal("30"),
                    activity_unit="kWh",
                    factor_set_version="synthetic-publication-test-v1",
                    factor_code="GRID_ELECTRICITY",
                    factor_value=Decimal("0.727"),
                    factor_unit="kgCO2e/kWh",
                    result_kgco2e=Decimal("21.81"),
                    result_value=Decimal("0.02181"),
                    result_unit="tCO2e",
                    formula_version="activity_x_factor_kgco2e_v1",
                ),
                CalculationResult(
                    submission_id=lpg.id,
                    submission_revision=1,
                    calculation_code="lpg_emissions",
                    calculation_status="available",
                    metric_code="lpg_consumption_litres",
                    activity_value=Decimal("52"),
                    activity_unit="L",
                    factor_set_version="synthetic-publication-test-v1",
                    factor_code="LPG",
                    factor_value=Decimal("1.5571"),
                    factor_unit="kgCO2e/L",
                    result_kgco2e=Decimal("80.9692"),
                    result_value=Decimal("0.080969"),
                    result_unit="tCO2e",
                    formula_version="activity_x_factor_kgco2e_v1",
                ),
            ]
        )
        _submission(
            db,
            period,
            managers[OperationalDomain.WATER],
            OperationalDomain.WATER,
            SubmissionStatus.APPROVED,
            {
                "water_twad_kl": 5,
                "water_borewell_kl": 6,
                "water_private_kl": 0,
                "water_recycled_kl": 4,
                "inlet_ph": Decimal("7.2"),
            },
            approved_by=admin,
        )
        outreach = _submission(
            db,
            period,
            managers[OperationalDomain.OUTREACH],
            OperationalDomain.OUTREACH,
            SubmissionStatus.DRAFT,
        )
        _outreach_programme(db, outreach, period)
        _approve(outreach, admin)
        db.commit()
        db.refresh(period)
        admin_username = admin.username
        period_id = period.id
        transport_id = transport.id
        admin_id = admin.id
        db.expunge(period)

    with _client(postgres_engine) as client:
        csrf = _login(client, admin_username)
        version_one = f"publication-{uuid4().hex}"
        candidate_one = _prepare(client, csrf, period, version_one)
        candidate_same = _prepare(client, csrf, period, f"publication-{uuid4().hex}")
        payload = candidate_one["payload"]

        assert payload["schema_version"] == "1.1"
        assert payload["period"] == {"id": str(period_id), "year": period.year, "month": period.month}
        assert payload["publication_status"] == {domain.value: "approved" for domain in OperationalDomain}
        assert set(payload["transport"]["metrics"]) == {
            "transport_petrol_litres",
            "transport_diesel_litres",
            "dg_diesel_litres",
        }
        assert payload["energy"]["metrics"]["grid_total_kwh"]["value"] == 30
        assert payload["energy"]["metrics"]["renewable_total_kwh"]["value"] == 10
        assert payload["lpg"]["metrics"] == {"lpg_consumption_litres": {"value": 52, "unit": "L"}}
        assert payload["lpg"]["emissions"] == {
            "status": "available",
            "reason": None,
            "value": 0.080969,
            "unit": "tCO2e",
        }
        assert payload["lpg"]["calculations"][0]["factor_unit"] == "kgCO2e/L"
        assert payload["lpg"]["calculations"][0]["activity_metric_code"] == "lpg_consumption_litres"
        assert payload["lpg"]["calculations"][0]["activity_unit"] == "L"
        assert payload["transport"]["calculations"][0]["factor_code"] == "PETROL"
        assert payload["energy"]["calculations"][0]["calculation_code"] == "grid_electricity_emissions"
        assert payload["indicators"]["total_ghg_tco2e"]["status"] == "unavailable"
        assert payload["indicators"]["avoided_emissions_tco2e"]["reason"] == "methodology_under_review"
        assert payload["water"]["metrics"]["water_consumed_kl"]["value"] == 11
        assert payload["water"]["metrics"]["water_recycled_kl"]["value"] == 4
        assert payload["outreach"]["total_programs"] == 1
        assert payload["outreach"]["total_participants"] == 20

        serialized = json.dumps(payload, sort_keys=True).casefold()
        for forbidden in (
            "manager_user_id",
            "username",
            "email",
            "quality_note",
            "correction_reason",
            "review_actions",
            "audit",
            "evidence",
            "species_details",
            "verification",
            "private",
            "inlet_ph",
            "petrol_vehicle_count",
            # Reference-only LPG metadata must never reach a public payload.
            "lpg_weight_kg",
        ):
            assert forbidden not in serialized

        assert candidate_same["payload"] == payload
        assert candidate_same["checksum_sha256"] == candidate_one["checksum_sha256"]
        assert payload_checksum(payload) == candidate_one["checksum_sha256"]

        before_publish = client.get(f"/api/public/dashboard?year={period.year}&month={period.month}").json()
        assert before_publish["release"] is None
        assert client.post(
            f"/api/admin/releases/{candidate_one['id']}/publish", headers={"X-CSRF-Token": csrf}
        ).status_code == 200
        first_published = client.get(f"/api/public/dashboard?year={period.year}&month={period.month}").json()
        assert first_published["release"]["version"] == version_one
        assert first_published["transport"] == payload["transport"]

        with Session(postgres_engine) as db:
            old_transport = db.get(Submission, transport_id)
            assert old_transport is not None
            old_transport.status = SubmissionStatus.SUPERSEDED
            manager = db.get(User, old_transport.manager_user_id)
            assert manager is not None
            period_record = db.get(ReportingPeriod, period_id)
            approving_admin = db.get(User, admin_id)
            assert period_record is not None and approving_admin is not None
            _submission(
                db,
                period_record,
                manager,
                OperationalDomain.TRANSPORT,
                SubmissionStatus.APPROVED,
                {
                    "transport_petrol_litres": 100,
                    "transport_diesel_litres": 200,
                    "dg_diesel_litres": 300,
                },
                approved_by=approving_admin,
            )
            db.commit()

        assert client.get(f"/api/public/dashboard?year={period.year}&month={period.month}").json() == first_published
        preview_one = client.get(f"/api/admin/releases/{candidate_one['id']}/preview").json()
        assert preview_one["payload"] == payload

        candidate_two = _prepare(client, csrf, period, f"publication-{uuid4().hex}")
        assert candidate_two["checksum_sha256"] != candidate_one["checksum_sha256"]
        assert candidate_two["payload"]["transport"]["metrics"]["transport_petrol_litres"]["value"] == 100
        assert client.post(
            f"/api/admin/releases/{candidate_two['id']}/publish", headers={"X-CSRF-Token": csrf}
        ).status_code == 200
        second_published = client.get(f"/api/public/dashboard?year={period.year}&month={period.month}").json()
        assert second_published["release"]["version"] == candidate_two["version"]
        assert second_published["transport"] == candidate_two["payload"]["transport"]
        matching_history = [
            item
            for item in client.get("/api/public/dashboard/history").json()
            if item["period"]["id"] == str(period_id)
        ]
        assert len(matching_history) == 1
        assert matching_history[0]["release"]["version"] == candidate_two["version"]
        wrong_period = client.get(
            f"/api/public/dashboard?year={period.year + 1}&month={period.month}"
        ).json()
        assert wrong_period["release"] is None

    with Session(postgres_engine) as db:
        first_release = db.get(PublicRelease, candidate_one["id"])
        second_release = db.get(PublicRelease, candidate_two["id"])
        assert first_release is not None and first_release.status == ReleaseStatus.SUPERSEDED
        assert second_release is not None and second_release.status == ReleaseStatus.ACTIVE


def test_missing_approved_domains_are_null_not_zero(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db:
        period = _period(db, 2170)
        admin = _account(db, RoleCode.ADMIN)
        manager = _account(db, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
        _submission(
            db,
            period,
            manager,
            OperationalDomain.TRANSPORT,
            SubmissionStatus.APPROVED,
            {"transport_petrol_litres": 0, "transport_diesel_litres": 0, "dg_diesel_litres": 0},
            approved_by=admin,
        )
        payload = build_release_payload(db, period)
        assert payload["transport"]["metrics"]["transport_petrol_litres"]["value"] == 0  # type: ignore[index]
        for domain in (
            OperationalDomain.ENERGY,
            OperationalDomain.LPG,
            OperationalDomain.WATER,
            OperationalDomain.OUTREACH,
        ):
            assert payload[domain.value] is None
            assert payload["publication_status"][domain.value] == "missing_approved_submission"  # type: ignore[index]
