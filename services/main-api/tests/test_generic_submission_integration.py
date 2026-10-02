from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.bootstrap import AccountSpec, create_account
from app.core.config import Settings
from app.main import create_app
from app.models.enums import OperationalDomain, RoleCode
from app.models.sustainability import MetricDefinition, ReportingPeriod
from app.services import dg_methodology as dg
from tests.integration_support import unique_username

PASSWORD = "Generic-Workflow-Test!"
GENERIC_DOMAINS = [
    OperationalDomain.TRANSPORT,
    OperationalDomain.ENERGY,
    OperationalDomain.LPG,
    OperationalDomain.WATER,
    OperationalDomain.WASTE,
]


def _account(engine: Engine, role: RoleCode, domain: OperationalDomain | None = None) -> str:
    username = unique_username(f"generic-{role.value}-{domain.value if domain else 'all'}")
    with Session(engine) as db:
        create_account(db, AccountSpec(username, "Generic Workflow Test", role, domain), PASSWORD, must_change=False)
        db.commit()
    return username


def _period(engine: Engine, year: int, month: int = 6) -> ReportingPeriod:
    with Session(engine) as db:
        for _attempt in range(201 * 12):
            exists = db.scalar(
                select(ReportingPeriod.id).where(
                    ReportingPeriod.year == year, ReportingPeriod.month == month
                )
            )
            if exists is None:
                break
            month += 1
            if month > 12:
                month = 1
                year = 2000 if year >= 2200 else year + 1
        else:
            raise RuntimeError("No free reporting period is available for integration testing.")
        period = ReportingPeriod(
            year=year,
            month=month,
            period_start=date(year, month, 1),
            period_end=date(year, month, 28),
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
    return str(response.headers["x-csrf-token"])


def _values(
    engine: Engine,
    domain: OperationalDomain,
    *,
    include_optional_zero: bool = False,
    period: ReportingPeriod | None = None,
) -> list[dict[str, object]]:
    """Required Manager values for a domain.

    DG has one source metric per period (0015_dg_kwh_methodology): generation
    in kWh once the governed SFC is in force, litres before it. ``period``
    selects it; without one the current (kWh) methodology is assumed.
    """
    with Session(engine) as db:
        dg_source = (
            dg.manager_source_metric(db, period.period_start) if period is not None else dg.DG_GENERATION_METRIC
        )
        not_entered = dg.DG_LITRES_METRIC if dg_source == dg.DG_GENERATION_METRIC else dg.DG_GENERATION_METRIC
        definitions = db.scalars(
            select(MetricDefinition)
            .where(
                MetricDefinition.operational_domain == domain,
                MetricDefinition.manager_editable.is_(True),
                MetricDefinition.is_active.is_(True),
            )
            .order_by(MetricDefinition.display_order)
        ).all()
        values: list[dict[str, object]] = []
        optional_added = False
        for definition in definitions:
            if definition.code == not_entered:
                continue
            if definition.required_for_complete:
                values.append({"metric_code": definition.code, "value": "1", "quality_note": None})
            elif include_optional_zero and definition.zero_allowed and not optional_added:
                values.append({"metric_code": definition.code, "value": "0", "quality_note": "Confirmed zero"})
                optional_added = True
        return values


@pytest.mark.parametrize("domain", GENERIC_DOMAINS)
def test_manager_domain_authorization(postgres_engine: Engine, domain: OperationalDomain) -> None:
    username = _account(postgres_engine, RoleCode.MANAGER, domain)
    period = _period(postgres_engine, 2120 + GENERIC_DOMAINS.index(domain))
    other = OperationalDomain.ENERGY if domain != OperationalDomain.ENERGY else OperationalDomain.WATER
    with _client(postgres_engine, period) as client:
        csrf = _login(client, username)
        assert client.get(f"/api/manager/{domain.value}/periods").status_code == 200
        assert client.get(f"/api/manager/{other.value}/periods").status_code == 403
        cross_payload = {
            "reporting_period_id": str(period.id),
            "remarks": None,
            "values": _values(postgres_engine, other),
        }
        assert (
            client.post(
                f"/api/manager/{other.value}/submissions",
                json=cross_payload,
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 403
        )


def test_transport_complete_review_workflow(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2130)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    payload = {
        "reporting_period_id": str(period.id),
        "remarks": "Initial transport draft",
        "values": _values(postgres_engine, OperationalDomain.TRANSPORT, include_optional_zero=True),
    }

    with _client(postgres_engine, period) as manager_client:
        csrf = _login(manager_client, manager)
        created = manager_client.post(
            "/api/manager/transport/submissions", json=payload, headers={"X-CSRF-Token": csrf}
        )
        assert created.status_code == 201
        submission = created.json()
        submission_id = submission["id"]
        assert submission["status"] == "draft"
        assert any(item["value"] == "0.000000" for item in submission["values"])
        assert all(item["value"] is not None for item in submission["values"])

        current = manager_client.get(f"/api/manager/transport/submissions/current?reporting_period_id={period.id}")
        assert current.status_code == 200 and current.json()["id"] == submission_id
        assert manager_client.get(f"/api/manager/transport/submissions/{submission_id}").status_code == 200
        assert manager_client.get("/api/manager/transport/submissions").json()[0]["id"] == submission_id

        submitted = manager_client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        )
        assert submitted.status_code == 200
        assert (
            manager_client.put(
                f"/api/manager/transport/submissions/{submission_id}",
                json={
                    "remarks": "Forbidden edit",
                    "values": payload["values"],
                    "expected_row_version": manager_client.get(
                        f"/api/manager/transport/submissions/{submission_id}"
                    ).json()["row_version"],
                },
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 409
        )

        with _client(postgres_engine) as admin_client:
            admin_csrf = _login(admin_client, admin)
            queue = admin_client.get("/api/admin/review-queue?domain=transport")
            assert queue.status_code == 200 and any(item["id"] == submission_id for item in queue.json())
            detail = admin_client.get(f"/api/admin/submissions/{submission_id}")
            assert detail.status_code == 200 and detail.json()["domain"] == "transport"
            assert (
                admin_client.post(
                    f"/api/admin/submissions/{submission_id}/begin-review",
                    headers={"X-CSRF-Token": admin_csrf},
                ).status_code
                == 200
            )
            assert (
                admin_client.post(
                    f"/api/admin/submissions/{submission_id}/request-correction",
                    json={"reason": "Confirm the transport totals."},
                    headers={"X-CSRF-Token": admin_csrf},
                ).status_code
                == 200
            )

            corrected_values = [dict(item) for item in payload["values"]]  # type: ignore[union-attr]
            corrected_values[0]["value"] = "2"
            corrected = manager_client.put(
                f"/api/manager/transport/submissions/{submission_id}",
                json={
                    "remarks": "Corrected",
                    "values": corrected_values,
                    "expected_row_version": manager_client.get(
                        f"/api/manager/transport/submissions/{submission_id}"
                    ).json()["row_version"],
                },
                headers={"X-CSRF-Token": csrf},
            )
            assert corrected.status_code == 200
            assert corrected.json()["revision_number"] == 1
            assert corrected.json()["correction_reason"] == "Confirm the transport totals."
            assert (
                manager_client.post(
                    f"/api/manager/transport/submissions/{submission_id}/submit",
                    headers={"X-CSRF-Token": csrf},
                ).status_code
                == 200
            )
            assert (
                manager_client.get(f"/api/manager/transport/submissions/{submission_id}").json()["revision_number"] == 2
            )
            assert (
                admin_client.post(
                    f"/api/admin/submissions/{submission_id}/approve",
                    headers={"X-CSRF-Token": admin_csrf},
                ).status_code
                == 200
            )
            approved = manager_client.get(f"/api/manager/transport/submissions/{submission_id}").json()
            assert approved["status"] == "approved"
            assert (
                manager_client.put(
                    f"/api/manager/transport/submissions/{submission_id}",
                    json={
                        "remarks": None,
                        "values": corrected_values,
                        "expected_row_version": approved["row_version"],
                    },
                    headers={"X-CSRF-Token": csrf},
                ).status_code
                == 409
            )


def test_admin_review_queue_isolated_by_reporting_period(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    older_period = _period(postgres_engine, 2108)
    selected_period = _period(postgres_engine, 2109)
    submission_ids: dict[str, str] = {}

    for label, period in (("older", older_period), ("selected", selected_period)):
        with _client(postgres_engine, period) as manager_client:
            csrf = _login(manager_client, manager)
            created = manager_client.post(
                "/api/manager/transport/submissions",
                json={
                    "reporting_period_id": str(period.id),
                    "remarks": f"{label} period queue isolation",
                    "values": _values(postgres_engine, OperationalDomain.TRANSPORT),
                },
                headers={"X-CSRF-Token": csrf},
            )
            assert created.status_code == 201, created.text
            submission_ids[label] = created.json()["id"]
            submitted = manager_client.post(
                f"/api/manager/transport/submissions/{submission_ids[label]}/submit",
                headers={"X-CSRF-Token": csrf},
            )
            assert submitted.status_code == 200, submitted.text

    with _client(postgres_engine) as admin_client:
        _login(admin_client, admin)
        selected = admin_client.get(
            "/api/admin/review-queue",
            params={"domain": "transport", "reporting_period_id": str(selected_period.id)},
        )
        assert selected.status_code == 200, selected.text
        assert [item["id"] for item in selected.json()] == [submission_ids["selected"]]
        assert selected.json()[0]["reporting_period_id"] == str(selected_period.id)
        assert selected.json()[0]["reporting_period_label"] == (
            f"{selected_period.year}-{selected_period.month:02d}"
        )
        assert selected.json()[0]["status"] == "submitted"
        assert selected.json()[0]["revision_number"] == 1

        older = admin_client.get(
            "/api/admin/review-queue",
            params={"domain": "transport", "reporting_period_id": str(older_period.id)},
        )
        assert older.status_code == 200, older.text
        assert [item["id"] for item in older.json()] == [submission_ids["older"]]


def test_metric_domain_calculated_and_blank_protection(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2140)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.ENERGY)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        base = {"reporting_period_id": str(period.id), "remarks": None}
        cross_domain = {**base, "values": [{"metric_code": "water_twad_kl", "value": "1"}]}
        assert (
            client.post(
                "/api/manager/energy/submissions", json=cross_domain, headers={"X-CSRF-Token": csrf}
            ).status_code
            == 422
        )
        calculated = {**base, "values": [{"metric_code": "grid_total_kwh", "value": "3"}]}
        assert (
            client.post("/api/manager/energy/submissions", json=calculated, headers={"X-CSRF-Token": csrf}).status_code
            == 422
        )
        blank = {
            **base,
            "values": [
                {"metric_code": "grid_ht_kwh", "value": None},
                {"metric_code": "grid_commercial_kwh", "value": "0"},
            ],
        }
        saved = client.post("/api/manager/energy/submissions", json=blank, headers={"X-CSRF-Token": csrf})
        assert saved.status_code == 201
        values = {item["metric_code"]: item["value"] for item in saved.json()["values"]}
        assert "grid_ht_kwh" not in values
        assert values["grid_commercial_kwh"] == "0.000000"
