from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.bootstrap import AccountSpec, create_account
from app.core.config import Settings
from app.main import create_app
from app.models.enums import OperationalDomain, RoleCode
from app.models.sustainability import ReportingPeriod
from tests.integration_support import unique_username

PASSWORD = "Outreach-Test-Local!"


def _account(engine: Engine, role: RoleCode, domain: OperationalDomain | None = None) -> str:
    username = unique_username(f"outreach-{role.value}")
    with Session(engine) as db:
        create_account(db, AccountSpec(username, "Outreach Test", role, domain), PASSWORD, must_change=False)
        db.commit()
    return username


def _period(engine: Engine, year: int = 2035, month: int = 4) -> ReportingPeriod:
    with Session(engine) as db:
        while db.scalar(select(ReportingPeriod.id).where(ReportingPeriod.year == year, ReportingPeriod.month == month)):
            year += 1
        period = ReportingPeriod(
            year=year,
            month=month,
            period_start=date(year, month, 1),
            period_end=date(year, month, 30),
            is_open=True,
        )
        db.add(period)
        db.commit()
        db.refresh(period)
        db.expunge(period)
        return period


def _client(engine: Engine, period: ReportingPeriod | None = None) -> TestClient:
    settings = Settings(APP_ENV="test", DATABASE_URL=str(engine.url), EVIDENCE_ROOT=".local/test-evidence")
    clock = (
        (lambda: datetime(period.year, period.month, 15, tzinfo=UTC))
        if period is not None
        else None
    )
    return TestClient(create_app(settings, engine, clock))


def _login(client: TestClient, username: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return response.headers["x-csrf-token"]


def _programme(period: ReportingPeriod, name: str = "Programme A") -> dict[str, object]:
    return {
        "reporting_period_id": str(period.id),
        "programme_name": name,
        "programme_date": date(period.year, period.month, 10).isoformat(),
        "theme": "climate_change",
        "other_theme": None,
        "partner_organisation": "Partner One",
        "programme_location": None,
        "programme_description": None,
        "school_students": 100,
        "college_students": 50,
        "farmers_agriculture": None,
        "industrial_experts": None,
        "researchers_experts": None,
        "government_participants": None,
        "saplings_planted": 5,
        "waste_collected_kg": "12.50",
        "species_identified_count": 2,
        "species_details": [
            {"species_name": "Neem", "count": 1},
            {"species_name": "Peepal", "count": 1},
        ],
        "species_verification_notes": "Verified by the Outreach manager.",
        "experts_involved": 2,
        "volunteers_engaged": 4,
        "volunteer_hours": "2.50",
        "remarks": None,
    }


@pytest.mark.parametrize(
    "domain",
    [
        OperationalDomain.TRANSPORT,
        OperationalDomain.ENERGY,
        OperationalDomain.LPG,
        OperationalDomain.WATER,
    ],
)
def test_non_outreach_managers_are_denied(postgres_engine: Engine, domain: OperationalDomain) -> None:
    username = _account(postgres_engine, RoleCode.MANAGER, domain)
    with _client(postgres_engine) as client:
        _login(client, username)
        assert client.get("/api/manager/outreach/programmes").status_code == 403


def test_outreach_security_and_validation(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2070, 5)
    outreach = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.OUTREACH)
    other_outreach = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.OUTREACH)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    with _client(postgres_engine) as anonymous:
        assert anonymous.get("/api/manager/outreach/programmes").status_code == 401
    with _client(postgres_engine, period) as client:
        csrf = _login(client, outreach)
        payload = _programme(period)
        forged = {**payload, "domain": "outreach", "manager_user_id": str(uuid4()), "status": "approved"}
        assert (
            client.post("/api/manager/outreach/programmes", json=forged, headers={"X-CSRF-Token": csrf}).status_code
            == 422
        )
        # Gender is no longer an outreach field: a request carrying one is rejected.
        with_gender = {**payload, "male_participants": 10}
        assert (
            client.post(
                "/api/manager/outreach/programmes", json=with_gender, headers={"X-CSRF-Token": csrf}
            ).status_code
            == 422
        )
        assert client.post("/api/manager/outreach/programmes", json=payload).status_code == 403
        created = client.post("/api/manager/outreach/programmes", json=payload, headers={"X-CSRF-Token": csrf})
        assert created.status_code == 201
        assert created.json()["participant_total"] == 150
        assert created.json()["waste_collected_kg"] == "12.50"
        assert created.json()["species_details"][0] == {"species_name": "Neem", "count": 1}
        programme_id = created.json()["id"]
    with _client(postgres_engine) as outsider:
        _login(outsider, other_outreach)
        assert outsider.get(f"/api/manager/outreach/programmes/{programme_id}").status_code == 404
    with _client(postgres_engine) as admin_client:
        admin_csrf = _login(admin_client, admin)
        assert (
            admin_client.post(
                "/api/manager/outreach/programmes",
                json=payload,
                headers={"X-CSRF-Token": admin_csrf},
            ).status_code
            == 403
        )


def test_complete_outreach_review_release_workflow(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2090, 4)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.OUTREACH)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    with _client(postgres_engine, period) as manager_client:
        csrf = _login(manager_client, manager)
        session = manager_client.get("/api/auth/session").json()["user"]
        assert session["role"] == "manager" and session["manager_domain"] == "outreach"
        assert any(item["id"] == str(period.id) for item in manager_client.get("/api/manager/periods").json())

        first = manager_client.post(
            "/api/manager/outreach/programmes",
            json=_programme(period),
            headers={"X-CSRF-Token": csrf},
        )
        assert first.status_code == 201 and first.json()["participant_total"] == 150
        second_payload = {
            **_programme(period, "Programme B"),
            "theme": "water_conservation",
            "partner_organisation": "  partner   one ",
            "school_students": None,
            "college_students": None,
            "farmers_agriculture": 20,
            "researchers_experts": 10,
            "saplings_planted": 7,
            "experts_involved": 3,
            "volunteers_engaged": 6,
            "volunteer_hours": "3.75",
        }
        second = manager_client.post(
            "/api/manager/outreach/programmes",
            json=second_payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert second.status_code == 201 and second.json()["participant_total"] == 30
        submission_id = first.json()["submission_id"]
        assert manager_client.post(f"/api/manager/outreach/submissions/{submission_id}/submit").status_code == 403
        assert (
            manager_client.post(
                f"/api/manager/outreach/submissions/{submission_id}/submit",
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 200
        )
        assert (
            manager_client.put(
                f"/api/manager/outreach/programmes/{first.json()['id']}",
                json={
                    **{k: v for k, v in _programme(period).items() if k != "reporting_period_id"},
                    "expected_row_version": manager_client.get(
                        f"/api/manager/outreach/programmes/{first.json()['id']}"
                    ).json()["row_version"],
                },
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 409
        )

        with _client(postgres_engine) as admin_client:
            admin_csrf = _login(admin_client, admin)
            before = admin_client.get("/api/public/dashboard").json()
            queue = admin_client.get("/api/admin/review-queue?domain=outreach").json()
            assert any(item["id"] == submission_id for item in queue)
            assert (
                admin_client.post(
                    f"/api/admin/submissions/{submission_id}/request-correction",
                    json={"reason": "Clarify the programme description."},
                    headers={"X-CSRF-Token": admin_csrf},
                ).status_code
                == 200
            )

            history = manager_client.get("/api/manager/outreach/submissions").json()
            assert history[0]["status"] == "correction_requested"
            assert history[0]["correction_reason"] == "Clarify the programme description."
            update_payload = {k: v for k, v in _programme(period).items() if k != "reporting_period_id"}
            update_payload["programme_description"] = "Clarified."
            update_payload["expected_row_version"] = manager_client.get(
                f"/api/manager/outreach/programmes/{first.json()['id']}"
            ).json()["row_version"]
            assert (
                manager_client.put(
                    f"/api/manager/outreach/programmes/{first.json()['id']}",
                    json={
                        **update_payload,
                        "expected_row_version": manager_client.get(
                            f"/api/manager/outreach/programmes/{first.json()['id']}"
                        ).json()["row_version"],
                    },
                    headers={"X-CSRF-Token": csrf},
                ).status_code
                == 200
            )
            assert (
                manager_client.post(
                    f"/api/manager/outreach/submissions/{submission_id}/submit",
                    headers={"X-CSRF-Token": csrf},
                ).status_code
                == 200
            )
            assert (
                admin_client.post(
                    f"/api/admin/submissions/{submission_id}/approve",
                    headers={"X-CSRF-Token": admin_csrf},
                ).status_code
                == 200
            )
            assert admin_client.get("/api/public/dashboard").json() == before
            release = admin_client.post(
                "/api/admin/releases/prepare",
                json={"reporting_period_id": str(period.id), "version": f"test-{uuid4().hex}"},
                headers={"X-CSRF-Token": admin_csrf},
            )
            assert release.status_code == 409
            assert release.json()["error"]["code"] == "publication_not_ready"
            assert release.json()["error"]["approved_domains"] == 1
            assert admin_client.get("/api/public/dashboard").json() == before
            assert (
                manager_client.put(
                    f"/api/manager/outreach/programmes/{first.json()['id']}",
                    json=update_payload,
                    headers={"X-CSRF-Token": csrf},
                ).status_code
                == 409
            )
