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
    InstitutionalPopulationReference,
    MetricDefinition,
    OutreachProgramme,
    ReportingPeriod,
    Submission,
    SubmissionValue,
    WasteSubmissionItem,
)
from app.services.publication import build_release_payload, lpg_payload_blockers, payload_checksum
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
        db.add(InstitutionalPopulationReference(
            effective_year=period.year,
            population=1000,
            unit="people",
            source_reference="Synthetic publication contract reference",
        ))
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
            {"lpg_cylinder_count": 2, "lpg_weight_kg": 52},
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
                    metric_code="lpg_weight_kg",
                    activity_value=Decimal("52"),
                    activity_unit="kg",
                    factor_set_version="synthetic-publication-test-v1",
                    factor_code="LPG_KG",
                    factor_value=Decimal("2.98"),
                    factor_unit="kgCO2e/kg",
                    result_kgco2e=Decimal("154.96"),
                    result_value=Decimal("0.15496"),
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
        # Built as a draft first: guard_frozen_submission correctly refuses to
        # let the derived-total trigger touch an already-approved submission,
        # which mirrors the real Manager -> Submit -> Approve order.
        waste = _submission(
            db,
            period,
            managers[OperationalDomain.WASTE],
            OperationalDomain.WASTE,
            SubmissionStatus.DRAFT,
            {"wet_waste_generated_kg": Decimal("300")},
        )
        # Dry inventory: 100.25 + 50.50 + 25.25 = 176.00, so total = 476.00.
        # The database trigger derives dry/total from these rows.
        for material_code, quantity in (
            ("COLOUR_PAPER", "100.25"),
            ("PET", "50.50"),
            ("IRON", "25.25"),
        ):
            db.add(
                WasteSubmissionItem(
                    submission_id=waste.id,
                    material_code=material_code,
                    quantity_kg=Decimal(quantity),
                )
            )
        db.flush()
        _approve(waste, admin)
        db.flush()
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

        assert payload["schema_version"] == "1.5"
        assert payload["period"] == {"id": str(period_id), "year": period.year, "month": period.month}
        assert payload["publication_status"] == {domain.value: "approved" for domain in OperationalDomain}
        assert set(payload["transport"]["metrics"]) == {
            "transport_petrol_litres",
            "transport_diesel_litres",
            "dg_generation_kwh",
            "dg_diesel_litres",
        }
        assert payload["energy"]["metrics"]["grid_total_kwh"]["value"] == 30
        # The deprecated total that included the solar water heater (2 + 3 + 5)
        # is no longer published; the governed indicator is on-campus + procured.
        assert "renewable_total_kwh" not in payload["energy"]["metrics"]
        assert payload["energy"]["metrics"]["solar_water_heater_kwh"]["value"] == 5
        assert payload["indicators"]["renewable_electricity_kwh"]["value"] == 5
        assert payload["indicators"]["total_electricity_consumption_kwh"]["value"] == 35
        assert payload["indicators"]["estimated_avoided_grid_emissions_tco2e"]["value"] == 0.003635
        assert payload["indicators"]["water_per_capita_l"]["value"] == 11
        # Schema 1.5: LPG is published as governed kg; litres and the
        # admin-only cylinder count never appear.
        assert payload["lpg"]["metrics"] == {"lpg_weight_kg": {"value": 52, "unit": "kg"}}
        assert payload["lpg"]["emissions"] == {
            "status": "available",
            "reason": None,
            "value": 0.15496,
            "unit": "tCO2e",
        }
        assert payload["lpg"]["calculations"][0]["factor_code"] == "LPG_KG"
        assert payload["lpg"]["calculations"][0]["factor_unit"] == "kgCO2e/kg"
        assert payload["lpg"]["calculations"][0]["activity_metric_code"] == "lpg_weight_kg"
        assert payload["lpg"]["calculations"][0]["activity_unit"] == "kg"
        assert "lpg_consumption_litres" not in json.dumps(payload)
        assert payload["transport"]["calculations"][0]["factor_code"] == "PETROL"
        assert payload["energy"]["calculations"][0]["calculation_code"] == "grid_electricity_emissions"
        assert payload["indicators"]["total_ghg_tco2e"]["status"] == "unavailable"
        assert payload["indicators"]["scope1_tco2e"]["status"] == "unavailable"
        assert payload["indicators"]["operational_ghg_tco2e"]["status"] == "unavailable"
        legacy_avoided = payload["indicators"]["avoided_emissions_tco2e"]
        assert legacy_avoided["reason"] == "superseded_by_estimated_avoided_grid_emissions_tco2e"
        assert payload["water"]["metrics"]["water_consumed_kl"]["value"] == 11
        assert payload["water"]["metrics"]["water_recycled_kl"]["value"] == 4
        assert payload["outreach"]["total_programs"] == 1
        assert payload["outreach"]["total_participants"] == 20
        # The programme row above still holds legacy gender values; a new release never freezes them.
        assert "gender" not in payload["outreach"]  # type: ignore[operator]

        # Schema 1.2 waste payload: metrics, backend category totals and rows.
        waste_payload = payload["waste"]
        assert waste_payload["metrics"] == {
            "wet_waste_generated_kg": {"value": 300, "unit": "kg"},
            "dry_waste_generated_kg": {"value": 176, "unit": "kg"},
            "total_waste_generated_kg": {"value": 476, "unit": "kg"},
        }
        assert waste_payload["categories"] == [
            {"code": "METAL", "display_name": "Metal", "quantity_kg": 25.25},
            {"code": "PAPER_CARDBOARD", "display_name": "Paper & Cardboard", "quantity_kg": 100.25},
            {"code": "PLASTIC", "display_name": "Plastic", "quantity_kg": 50.5},
        ]
        assert [row["code"] for row in waste_payload["materials"]] == [
            "COLOUR_PAPER", "PET", "IRON",
        ]
        assert waste_payload["materials"][0] == {
            "code": "COLOUR_PAPER",
            "display_name": "Colour Paper",
            "category_code": "PAPER_CARDBOARD",
            "category_display_name": "Paper & Cardboard",
            "quantity_kg": 100.25,
        }
        # Category totals equal the material rows, and wet + dry equals total.
        assert sum(row["quantity_kg"] for row in waste_payload["categories"]) == 176.0
        assert waste_payload["calculations"] == []  # waste has no emissions

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
            "private_note",
            "private_data",
            "inlet_ph",
            "petrol_vehicle_count",
            # Reference-only LPG metadata and the deprecated litre metric must
            # never reach a public payload.
            "lpg_cylinder_count",
            "lpg_consumption_litres",
        ):
            assert forbidden not in serialized

        assert candidate_same["payload"] == payload
        assert candidate_same["checksum_sha256"] == candidate_one["checksum_sha256"]
        assert payload_checksum(payload) == candidate_one["checksum_sha256"]

        # After a page reload the Admin UI rediscovers candidates from the
        # database: metadata only, real release ids, no payload.
        listed = client.get(f"/api/admin/releases?reporting_period_id={period_id}")
        assert listed.status_code == 200
        listed_by_version = {item["version"]: item for item in listed.json()}
        assert set(listed_by_version) == {version_one, candidate_same["version"]}
        rediscovered = listed_by_version[version_one]
        assert rediscovered["id"] == candidate_one["id"]
        assert rediscovered["status"] == "candidate"
        assert rediscovered["checksum_sha256"] == candidate_one["checksum_sha256"]
        assert rediscovered["reporting_period_id"] == str(period_id)
        assert rediscovered["published_at"] is None
        assert set(rediscovered) == {
            "id", "version", "status", "checksum_sha256", "reporting_period_id", "created_at", "published_at",
        }

        # A duplicate Prepare is still refused and creates nothing; the
        # existing candidate stays discoverable and previewable by its real id.
        duplicate = client.post(
            "/api/admin/releases/prepare",
            json={"reporting_period_id": str(period_id), "version": version_one},
            headers={"X-CSRF-Token": csrf},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["message"] == "Release version already exists."
        assert duplicate.json()["error"]["request_id"] != candidate_one["id"]
        assert len(client.get(f"/api/admin/releases?reporting_period_id={period_id}").json()) == 2
        assert client.get(f"/api/admin/releases/{rediscovered['id']}/preview").json()["payload"] == payload

        before_publish = client.get(f"/api/public/dashboard?year={period.year}&month={period.month}").json()
        assert before_publish["release"] is None
        assert client.post(
            f"/api/admin/releases/{candidate_one['id']}/publish", headers={"X-CSRF-Token": csrf}
        ).status_code == 200
        first_published = client.get(f"/api/public/dashboard?year={period.year}&month={period.month}").json()
        assert first_published["release"]["version"] == version_one
        assert first_published["transport"] == payload["transport"]
        after_publish = {
            item["version"]: item
            for item in client.get(f"/api/admin/releases?reporting_period_id={period_id}").json()
        }
        assert after_publish[version_one]["status"] == "active"
        assert after_publish[version_one]["published_at"] is not None

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


def test_release_listing_is_admin_only_metadata(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db:
        period = _period(db, 2180)
        other_period = _period(db, 2181)
        admin = _account(db, RoleCode.ADMIN)
        manager = _account(db, RoleCode.MANAGER, OperationalDomain.WASTE)
        release = PublicRelease(
            version=f"listing-{uuid4().hex}",
            status=ReleaseStatus.CANDIDATE,
            checksum_sha256="0" * 64,
            prepared_by=admin.id,
            reporting_period_id=period.id,
        )
        db.add(release)
        db.commit()
        admin_username, manager_username = admin.username, manager.username
        period_id, other_period_id, release_id = period.id, other_period.id, release.id

    with _client(postgres_engine) as client:
        url = f"/api/admin/releases?reporting_period_id={period_id}"
        assert client.get(url).status_code == 401
        _login(client, manager_username)
        assert client.get(url).status_code == 403

    with _client(postgres_engine) as client:
        _login(client, admin_username)
        body = client.get(url).json()
        assert [item["id"] for item in body] == [str(release_id)]
        serialized = json.dumps(body).casefold()
        for forbidden in ("payload", "prepared_by", "published_by", "username", "email", "evidence", "session"):
            assert forbidden not in serialized
        assert client.get(f"/api/admin/releases?reporting_period_id={other_period_id}").json() == []
        assert client.get(f"/api/admin/releases?reporting_period_id={uuid4()}").status_code == 404
        assert client.get("/api/admin/releases").status_code == 422


def _frozen_calculation(
    submission: Submission,
    calculation_code: str,
    metric_code: str,
    activity: Decimal,
    activity_unit: str,
    result_tco2e: Decimal,
) -> CalculationResult:
    factor_code = {
        "transport_petrol_emissions": "PETROL",
        "transport_diesel_emissions": "DIESEL",
        "dg_diesel_emissions": "DIESEL",
        "lpg_emissions": "LPG_KG",
        "grid_electricity_emissions": "GRID_ELECTRICITY",
    }[calculation_code]
    return CalculationResult(
        submission_id=submission.id,
        submission_revision=submission.revision_number,
        calculation_code=calculation_code,
        calculation_status="available",
        metric_code=metric_code,
        activity_value=activity,
        activity_unit=activity_unit,
        factor_set_version="publication-contract-test",
        factor_code=factor_code,
        factor_value=result_tco2e * Decimal("1000") / activity,
        factor_unit=f"kgCO2e/{activity_unit}",
        result_kgco2e=result_tco2e * Decimal("1000"),
        result_value=result_tco2e,
        result_unit="tCO2e",
        formula_version="publication-contract-test",
    )


def test_schema_1_4_publishes_governed_aggregates_and_backend_indicators(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db:
        period = _period(db, 2190, 9)
        admin = _account(db, RoleCode.ADMIN)
        managers = {domain: _account(db, RoleCode.MANAGER, domain) for domain in OperationalDomain}
        db.add(
            InstitutionalPopulationReference(
                effective_year=period.year,
                population=1000,
                unit="people",
                source_reference="Owner-approved integration-test population reference",
            )
        )

        transport = _submission(
            db,
            period,
            managers[OperationalDomain.TRANSPORT],
            OperationalDomain.TRANSPORT,
            SubmissionStatus.APPROVED,
            {
                "transport_petrol_litres": 1,
                "transport_diesel_litres": 2,
                "dg_diesel_litres": 3,
            },
            approved_by=admin,
        )
        lpg = _submission(
            db,
            period,
            managers[OperationalDomain.LPG],
            OperationalDomain.LPG,
            SubmissionStatus.APPROVED,
            {"lpg_weight_kg": 4},
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
                "renewable_on_campus_kwh": 50,
                "renewable_procured_kwh": 60,
                "solar_water_heater_kwh": 70,
            },
            approved_by=admin,
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
                "wastewater_generated_kl": 2,
                "water_recycled_kl": 4,
            },
            approved_by=admin,
        )
        waste = _submission(
            db,
            period,
            managers[OperationalDomain.WASTE],
            OperationalDomain.WASTE,
            SubmissionStatus.DRAFT,
            {"wet_waste_generated_kg": 100},
        )
        db.add(
            WasteSubmissionItem(
                submission_id=waste.id,
                material_code="PET",
                quantity_kg=Decimal("50"),
            )
        )
        db.flush()
        _approve(waste, admin)

        db.add_all(
            [
                _frozen_calculation(
                    transport, "transport_petrol_emissions", "transport_petrol_litres",
                    Decimal("1"), "L", Decimal("0.1"),
                ),
                _frozen_calculation(
                    transport, "transport_diesel_emissions", "transport_diesel_litres",
                    Decimal("2"), "L", Decimal("0.2"),
                ),
                _frozen_calculation(
                    transport, "dg_diesel_emissions", "dg_diesel_litres",
                    Decimal("3"), "L", Decimal("0.3"),
                ),
                _frozen_calculation(
                    lpg, "lpg_emissions", "lpg_weight_kg",
                    Decimal("4"), "kg", Decimal("0.4"),
                ),
                _frozen_calculation(
                    energy, "grid_electricity_emissions", "grid_total_kwh",
                    Decimal("30"), "kWh", Decimal("0.5"),
                ),
            ]
        )
        db.flush()

        payload = build_release_payload(db, period)
        assert payload["schema_version"] == "1.5"
        assert lpg_payload_blockers(payload) == []
        assert payload["energy"]["metrics"]["grid_ht_kwh"] == {"value": 10, "unit": "kWh"}  # type: ignore[index]
        assert payload["energy"]["metrics"]["grid_total_kwh"] == {"value": 30, "unit": "kWh"}  # type: ignore[index]
        assert payload["energy"]["metrics"]["renewable_on_campus_kwh"]["value"] == 50  # type: ignore[index]
        assert "renewable_total_kwh" not in payload["energy"]["metrics"]  # type: ignore[operator]
        assert payload["indicators"]["renewable_electricity_kwh"]["value"] == 110  # type: ignore[index]
        assert payload["indicators"]["total_electricity_consumption_kwh"]["value"] == 140  # type: ignore[index]
        assert payload["indicators"]["renewable_share_pct"]["value"] == 78.571428571429  # type: ignore[index]
        assert payload["indicators"]["estimated_avoided_grid_emissions_tco2e"]["value"] == 1.833333333337  # type: ignore[index]
        assert payload["indicators"]["water_per_capita_l"]["value"] == 11  # type: ignore[index]
        assert payload["water"]["metrics"]["water_twad_kl"]["value"] == 5  # type: ignore[index]
        assert payload["water"]["metrics"]["water_borewell_kl"]["value"] == 6  # type: ignore[index]
        assert payload["water"]["metrics"]["water_private_kl"]["value"] == 0  # type: ignore[index]
        assert payload["water"]["metrics"]["wastewater_generated_kl"]["value"] == 2  # type: ignore[index]
        assert payload["population"] == {
            "status": "available",
            "reason": None,
            "value": 1000,
            "unit": "people",
            "effective_year": period.year,
            "source_reference": "Owner-approved integration-test population reference",
        }
        assert payload["indicators"]["scope1_tco2e"]["value"] == 1.0  # type: ignore[index]
        assert payload["indicators"]["scope2_tco2e"]["value"] == 0.5  # type: ignore[index]
        assert payload["indicators"]["operational_ghg_tco2e"]["value"] == 1.5  # type: ignore[index]
        assert payload["indicators"]["operational_ghg_per_capita_kgco2e"]["value"] == 1.5  # type: ignore[index]
        assert payload["indicators"]["waste_per_capita_kg"]["value"] == 0.15  # type: ignore[index]
        # Diverted from landfill is frozen with the release and equals the dry waste.
        diverted = payload["indicators"]["waste_diverted_from_landfill_kg"]  # type: ignore[index]
        dry = payload["waste"]["metrics"]["dry_waste_generated_kg"]  # type: ignore[index]
        assert (diverted["status"], diverted["unit"], diverted["value"]) == ("available", "kg", dry["value"])
        legacy_avoided = payload["indicators"]["avoided_emissions_tco2e"]  # type: ignore[index]
        assert legacy_avoided["reason"] == "superseded_by_estimated_avoided_grid_emissions_tco2e"  # type: ignore[index]
        assert payload["indicators"]["renewable_share_percent"]["reason"] == "superseded_by_renewable_share_pct"  # type: ignore[index]
        serialized = json.dumps(payload, sort_keys=True).casefold()
        assert "username" not in serialized
        assert "created_by" not in serialized

        zero_period = _period(db, period.year + 1, 9)
        db.add(
            InstitutionalPopulationReference(
                effective_year=zero_period.year,
                population=0,
                unit="people",
                source_reference="Owner-approved zero-population boundary test",
            )
        )
        db.flush()
        zero_payload = build_release_payload(db, zero_period)
        assert zero_payload["population"]["reason"] == "population_is_zero"  # type: ignore[index]
        assert zero_payload["indicators"]["operational_ghg_per_capita_kgco2e"]["status"] == "unavailable"  # type: ignore[index]
        assert zero_payload["indicators"]["waste_per_capita_kg"]["status"] == "unavailable"  # type: ignore[index]
