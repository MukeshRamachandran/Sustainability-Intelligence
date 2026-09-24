from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models.enums import OperationalDomain, ReleaseStatus, RoleCode, SubmissionStatus
from app.models.identity import User
from app.models.publication import PublicRelease, PublicReleasePayload
from app.models.sustainability import InstitutionalPopulationReference, ReportingPeriod, Submission
from app.services.publication import build_release_payload, payload_checksum
from tests.test_publication_integration import (
    _account,
    _approve,
    _client,
    _frozen_calculation,
    _login,
    _outreach_programme,
    _period,
    _submission,
)


def _domain_submissions(
    db: Session,
    period: ReportingPeriod,
    admin: User,
    statuses: dict[OperationalDomain, SubmissionStatus],
) -> dict[OperationalDomain, Submission]:
    result: dict[OperationalDomain, Submission] = {}
    db.add(InstitutionalPopulationReference(
        effective_year=period.year,
        population=1000,
        unit="people",
        source_reference="Synthetic readiness-test reference",
    ))
    for domain, status in statuses.items():
        manager = _account(db, RoleCode.MANAGER, domain)
        initial_status = SubmissionStatus.DRAFT if domain == OperationalDomain.OUTREACH else status
        # Waste needs its wet value so the database trigger derives dry/total;
        # a payload missing them is correctly refused at prepare.
        values = {
            OperationalDomain.WASTE: {"wet_waste_generated_kg": Decimal("40")},
            OperationalDomain.ENERGY: {
                "grid_ht_kwh": Decimal("40"),
                "grid_commercial_kwh": Decimal("50"),
                "grid_temporary_kwh": Decimal("10"),
                "renewable_on_campus_kwh": Decimal("20"),
                "renewable_procured_kwh": Decimal("30"),
                "solar_water_heater_kwh": Decimal("5"),
            },
            OperationalDomain.WATER: {
                "water_twad_kl": Decimal("20"),
                "water_borewell_kl": Decimal("30"),
                "water_private_kl": Decimal("50"),
            },
        }.get(domain)
        submission = _submission(
            db,
            period,
            manager,
            domain,
            initial_status,
            values,
            approved_by=admin if initial_status == SubmissionStatus.APPROVED else None,
        )
        if domain == OperationalDomain.OUTREACH:
            _outreach_programme(db, submission, period)
            if status == SubmissionStatus.APPROVED:
                _approve(submission, admin)
            else:
                submission.status = status
            db.flush()
        if domain == OperationalDomain.ENERGY:
            db.add(_frozen_calculation(
                submission, "grid_electricity_emissions", "grid_total_kwh",
                Decimal("100"), "kWh", Decimal("0.07"),
            ))
            db.flush()
        result[domain] = submission
    return result


def test_readiness_auth_zero_approved_and_partial_prepare_block(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db:
        empty_period = _period(db, 2000, 11)
        partial_period = _period(db, 2001, 11)
        admin = _account(db, RoleCode.ADMIN)
        manager = _account(db, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
        statuses = {domain: SubmissionStatus.APPROVED for domain in OperationalDomain}
        statuses[OperationalDomain.LPG] = SubmissionStatus.UNDER_REVIEW
        _domain_submissions(db, partial_period, admin, statuses)
        db.commit()
        empty_period_id = empty_period.id
        partial_period_id = partial_period.id
        admin_username = admin.username
        manager_username = manager.username

    with _client(postgres_engine) as client:
        endpoint = f"/api/admin/reporting-periods/{empty_period_id}/publication-readiness"
        assert client.get(endpoint).status_code == 401
        _login(client, manager_username)
        assert client.get(endpoint).status_code == 403

    with _client(postgres_engine) as client:
        csrf = _login(client, admin_username)
        empty = client.get(endpoint)
        assert empty.status_code == 200
        assert empty.json()["approved_domains"] == 0
        assert empty.json()["required_domains"] == 6
        assert empty.json()["ready_to_publish"] is False
        assert set(empty.json()["domains"]) == {domain.value for domain in OperationalDomain}
        assert all(item["status"] == "missing" for item in empty.json()["domains"].values())
        serialized = json.dumps(empty.json()).casefold()
        for private_field in ("evidence", "filename", "storage", "checksum", "sha256"):
            assert private_field not in serialized

        with Session(postgres_engine) as db:
            before = db.scalar(select(func.count()).select_from(PublicRelease))
        blocked = client.post(
            "/api/admin/releases/prepare",
            json={"reporting_period_id": str(partial_period_id), "version": f"blocked-{uuid4().hex}"},
            headers={"X-CSRF-Token": csrf},
        )
        assert blocked.status_code == 409
        error = blocked.json()["error"]
        assert error["code"] == "publication_not_ready"
        assert error["approved_domains"] == 5
        assert error["required_domains"] == 6
        assert error["blockers"] == [
            {"domain": "lpg", "reason": "not_approved", "status": "under_review"}
        ]
        with Session(postgres_engine) as db:
            assert db.scalar(select(func.count()).select_from(PublicRelease)) == before


def test_six_of_six_prepare_is_explicit_and_frozen_candidate_remains_publishable(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db:
        period = _period(db, 2002, 11)
        admin = _account(db, RoleCode.ADMIN)
        statuses = {domain: SubmissionStatus.APPROVED for domain in OperationalDomain}
        statuses[OperationalDomain.TRANSPORT] = SubmissionStatus.UNDER_REVIEW
        submissions = _domain_submissions(db, period, admin, statuses)
        db.commit()
        period_id = period.id
        period_year = period.year
        period_month = period.month
        admin_username = admin.username
        transport_id = submissions[OperationalDomain.TRANSPORT].id
        before_releases = db.scalar(select(func.count()).select_from(PublicRelease))

    with _client(postgres_engine) as client:
        csrf = _login(client, admin_username)
        before_approval = client.get(
            f"/api/admin/reporting-periods/{period_id}/publication-readiness"
        ).json()
        assert before_approval["approved_domains"] == 5
        assert before_approval["ready_to_publish"] is False
        assert client.post(
            f"/api/admin/submissions/{transport_id}/approve",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        readiness = client.get(
            f"/api/admin/reporting-periods/{period_id}/publication-readiness"
        ).json()
        assert readiness["approved_domains"] == 6
        assert readiness["ready_to_publish"] is True
        assert readiness["blockers"] == []
        with Session(postgres_engine) as db:
            assert db.scalar(select(func.count()).select_from(PublicRelease)) == before_releases

        prepared = client.post(
            "/api/admin/releases/prepare",
            json={"reporting_period_id": str(period_id), "version": f"ready-{uuid4().hex}"},
            headers={"X-CSRF-Token": csrf},
        )
        assert prepared.status_code == 201
        candidate = prepared.json()
        assert candidate["status"] == "candidate"
        assert candidate["payload"]["publication_status"] == {
            domain.value: "approved" for domain in OperationalDomain
        }
        assert client.get(
            f"/api/public/dashboard?year={period_year}&month={period_month}"
        ).json().get("release") is None

        with Session(postgres_engine) as db:
            transport = db.get(Submission, transport_id)
            assert transport is not None
            transport.status = SubmissionStatus.CORRECTION_REQUESTED
            transport.revision_number = 2
            db.commit()

        changed = client.get(
            f"/api/admin/reporting-periods/{period_id}/publication-readiness"
        ).json()
        assert changed["approved_domains"] == 5
        assert changed["domains"]["transport"]["status"] == "correction_requested"
        assert changed["domains"]["transport"]["revision_number"] == 2
        assert changed["ready_to_publish"] is False

        published = client.post(
            f"/api/admin/releases/{candidate['id']}/publish",
            headers={"X-CSRF-Token": csrf},
        )
        assert published.status_code == 200


def test_period_isolation_and_legacy_partial_candidate_cannot_publish(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as db:
        ready_period = _period(db, 2003, 11)
        blocked_period = _period(db, 2004, 11)
        admin = _account(db, RoleCode.ADMIN)
        _domain_submissions(
            db,
            ready_period,
            admin,
            {domain: SubmissionStatus.APPROVED for domain in OperationalDomain},
        )
        blocked_statuses = {domain: SubmissionStatus.APPROVED for domain in OperationalDomain}
        blocked_statuses[OperationalDomain.OUTREACH] = SubmissionStatus.SUBMITTED
        _domain_submissions(db, blocked_period, admin, blocked_statuses)
        legacy_payload = build_release_payload(db, blocked_period)
        legacy = PublicRelease(
            version=f"legacy-partial-{uuid4().hex}",
            status=ReleaseStatus.CANDIDATE,
            checksum_sha256=payload_checksum(legacy_payload),
            prepared_by=admin.id,
            reporting_period_id=blocked_period.id,
        )
        db.add(legacy)
        db.flush()
        db.add(PublicReleasePayload(release_id=legacy.id, payload=legacy_payload))
        db.commit()
        ready_period_id = ready_period.id
        blocked_period_id = blocked_period.id
        legacy_id = legacy.id
        admin_username = admin.username

    with _client(postgres_engine) as client:
        csrf = _login(client, admin_username)
        ready = client.get(
            f"/api/admin/reporting-periods/{ready_period_id}/publication-readiness"
        ).json()
        blocked = client.get(
            f"/api/admin/reporting-periods/{blocked_period_id}/publication-readiness"
        ).json()
        assert ready["ready_to_publish"] is True
        assert blocked["ready_to_publish"] is False
        assert blocked["approved_domains"] == 5
        assert blocked["domains"]["outreach"]["status"] == "submitted"
        response = client.post(
            f"/api/admin/releases/{legacy_id}/publish",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "publication_not_ready"
