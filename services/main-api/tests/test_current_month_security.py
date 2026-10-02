from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.models.enums import OperationalDomain, RoleCode
from app.models.sustainability import ReportingPeriod
from app.services.reporting_periods import institutional_year_month
from tests.test_generic_submission_integration import _account, _login, _values
from tests.test_outreach_integration import _programme


def _three_periods(engine: Engine) -> tuple[ReportingPeriod, ReportingPeriod, ReportingPeriod]:
    with Session(engine) as db:
        year = 2000
        while db.scalar(
            select(ReportingPeriod.id).where(
                ReportingPeriod.year == year,
                ReportingPeriod.month.in_([5, 6, 7]),
            )
        ):
            year += 1
            if year > 2200:
                raise RuntimeError("No three-month test period is available.")
        periods = [
            ReportingPeriod(
                year=year,
                month=month,
                period_start=date(year, month, 1),
                period_end=date(year, month, 28),
                is_open=True,
            )
            for month in (5, 6, 7)
        ]
        db.add_all(periods)
        db.commit()
        for period in periods:
            db.refresh(period)
            db.expunge(period)
        return periods[0], periods[1], periods[2]


def _client(engine: Engine, current: ReportingPeriod) -> TestClient:
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=str(engine.url),
        EVIDENCE_ROOT=".local/test-evidence",
    )
    def clock() -> datetime:
        return datetime(current.year, current.month, 15, tzinfo=UTC)

    return TestClient(create_app(settings, engine, clock))


def test_asia_kolkata_month_boundary_uses_injected_clock() -> None:
    settings = Settings(APP_ENV="test", INSTITUTION_TIMEZONE="Asia/Kolkata")
    def before() -> datetime:
        return datetime(2026, 9, 30, 18, 29, tzinfo=UTC)

    def after() -> datetime:
        return datetime(2026, 9, 30, 18, 30, tzinfo=UTC)

    assert institutional_year_month(settings, before) == (2026, 9)
    assert institutional_year_month(settings, after) == (2026, 10)


def test_current_month_submit_once_and_historical_correction(
    postgres_engine: Engine,
) -> None:
    previous, current, future = _three_periods(postgres_engine)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    values = _values(postgres_engine, OperationalDomain.TRANSPORT, include_optional_zero=True, period=current)

    with _client(postgres_engine, current) as manager_client:
        csrf = _login(manager_client, manager)
        period_response = manager_client.get("/api/manager/transport/current-period")
        assert period_response.status_code == 200
        assert period_response.json() == {
            "id": str(current.id),
            "year": current.year,
            "month": current.month,
            "label": f"June {current.year}",
            "is_open": True,
            "is_current": True,
        }

        for forbidden in (previous, future):
            response = manager_client.post(
                "/api/manager/transport/submissions",
                json={"reporting_period_id": str(forbidden.id), "remarks": None, "values": values},
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status_code == 409

        payload = {
            "reporting_period_id": str(current.id),
            "remarks": "Current month draft",
            "values": values,
        }
        created = manager_client.post(
            "/api/manager/transport/submissions",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201, created.text
        submission_id = created.json()["id"]
        repeated = manager_client.post(
            "/api/manager/transport/submissions",
            json={
                **payload,
                "remarks": "Saved again",
                "expected_row_version": created.json()["row_version"],
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert repeated.status_code == 201
        assert repeated.json()["id"] == submission_id
        assert manager_client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        assert manager_client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 409

        with _client(postgres_engine, future) as future_client:
            future_csrf = _login(future_client, manager)
            assert future_client.put(
                f"/api/manager/transport/submissions/{submission_id}",
                json={
                    "remarks": "Forbidden old edit",
                    "values": values,
                    "expected_row_version": future_client.get(
                        f"/api/manager/transport/submissions/{submission_id}"
                    ).json()["row_version"],
                },
                headers={"X-CSRF-Token": future_csrf},
            ).status_code == 409

            with _client(postgres_engine, future) as admin_client:
                admin_csrf = _login(admin_client, admin)
                assert admin_client.post(
                    f"/api/admin/submissions/{submission_id}/request-correction",
                    json={"reason": "Historical correction required."},
                    headers={"X-CSRF-Token": admin_csrf},
                ).status_code == 200

            corrected = future_client.put(
                f"/api/manager/transport/submissions/{submission_id}",
                json={
                    "remarks": "Historical correction",
                    "values": values,
                    "expected_row_version": future_client.get(
                        f"/api/manager/transport/submissions/{submission_id}"
                    ).json()["row_version"],
                },
                headers={"X-CSRF-Token": future_csrf},
            )
            assert corrected.status_code == 200
            assert future_client.post(
                f"/api/manager/transport/submissions/{submission_id}/submit",
                headers={"X-CSRF-Token": future_csrf},
            ).status_code == 200
            detail = future_client.get(
                f"/api/manager/transport/submissions/{submission_id}"
            ).json()
            assert detail["revision_number"] == 2
            assert detail["status"] == "submitted"


@pytest.mark.parametrize("domain", list(OperationalDomain))
def test_current_period_create_is_enforced_for_all_manager_domains(
    postgres_engine: Engine,
    domain: OperationalDomain,
) -> None:
    previous, current, _future = _three_periods(postgres_engine)
    manager = _account(postgres_engine, RoleCode.MANAGER, domain)
    with _client(postgres_engine, current) as client:
        csrf = _login(client, manager)
        if domain == OperationalDomain.OUTREACH:
            assert client.get("/api/manager/outreach/current-period").json()["id"] == str(current.id)
            denied = client.post(
                "/api/manager/outreach/programmes",
                json=_programme(previous),
                headers={"X-CSRF-Token": csrf},
            )
            allowed = client.post(
                "/api/manager/outreach/programmes",
                json=_programme(current),
                headers={"X-CSRF-Token": csrf},
            )
        else:
            assert client.get(f"/api/manager/{domain.value}/current-period").json()["id"] == str(current.id)
            values = _values(postgres_engine, domain, period=current)
            denied = client.post(
                f"/api/manager/{domain.value}/submissions",
                json={"reporting_period_id": str(previous.id), "remarks": None, "values": values},
                headers={"X-CSRF-Token": csrf},
            )
            allowed = client.post(
                f"/api/manager/{domain.value}/submissions",
                json={"reporting_period_id": str(current.id), "remarks": None, "values": values},
                headers={"X-CSRF-Token": csrf},
            )
        assert denied.status_code == 409
        assert allowed.status_code == 201, allowed.text
