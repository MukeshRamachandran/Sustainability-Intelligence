from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.enums import OperationalDomain, RoleCode
from app.models.identity import User
from app.security.passwords import verify_password
from tests.integration_support import unique_username
from tests.test_generic_submission_integration import (
    _account,
    _client,
    _login,
    _period,
    _values,
)

TEMP_PASSWORD = "Temporary-Manager-1!"
CHANGED_PASSWORD = "Changed-Manager-2!"
RESET_PASSWORD = "Reset-Manager-3!"
ALL_DOMAINS = list(OperationalDomain)


def _login_with_password(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return str(response.headers["x-csrf-token"])


def test_admin_user_lifecycle_csrf_sessions_and_audit(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2195)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    existing_manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.ENERGY)
    username = unique_username("managed-transport")

    with _client(postgres_engine, period) as anonymous_client:
        assert anonymous_client.get("/api/admin/users").status_code == 401
        assert anonymous_client.get("/api/admin/audit-logs").status_code == 401

    with _client(postgres_engine, period) as manager_client:
        _login(manager_client, existing_manager)
        assert manager_client.get("/api/admin/users").status_code == 403
        assert manager_client.get("/api/admin/audit-logs").status_code == 403

    with _client(postgres_engine, period) as admin_client:
        admin_csrf = _login(admin_client, admin)
        create_payload = {
            "username": username,
            "display_name": "Managed Transport User",
            "temporary_password": TEMP_PASSWORD,
            "manager_domain": "transport",
        }
        assert admin_client.post(
            "/api/admin/users",
            json={**create_payload, "manager_domain": "invalid-domain"},
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 422
        assert admin_client.post("/api/admin/users", json=create_payload).status_code == 403
        created = admin_client.post(
            "/api/admin/users",
            json=create_payload,
            headers={"X-CSRF-Token": admin_csrf},
        )
        assert created.status_code == 201, created.text
        created_user = created.json()
        assert created_user["role"] == "manager"
        assert created_user["manager_domain"] == "transport"
        assert created_user["must_change_password"] is True
        assert TEMP_PASSWORD not in created.text
        user_id = created_user["id"]
        with Session(postgres_engine) as db:
            stored_user = db.scalar(select(User).where(User.id == UUID(user_id)))
            assert stored_user is not None
            assert stored_user.password_hash != TEMP_PASSWORD
            assert verify_password(stored_user.password_hash, TEMP_PASSWORD)

        duplicate = admin_client.post(
            "/api/admin/users",
            json=create_payload,
            headers={"X-CSRF-Token": admin_csrf},
        )
        assert duplicate.status_code == 409

        with _client(postgres_engine, period) as managed_client:
            manager_csrf = _login_with_password(managed_client, username, TEMP_PASSWORD)
            assert managed_client.get("/api/manager/transport/periods").status_code == 403
            changed = managed_client.post(
                "/api/auth/change-password",
                json={"current_password": TEMP_PASSWORD, "new_password": CHANGED_PASSWORD},
                headers={"X-CSRF-Token": manager_csrf},
            )
            assert changed.status_code == 200
            assert managed_client.get("/api/manager/transport/periods").status_code == 200

            revoked = admin_client.post(
                f"/api/admin/users/{user_id}/revoke-sessions",
                headers={"X-CSRF-Token": admin_csrf},
            )
            assert revoked.status_code == 200
            assert managed_client.get("/api/auth/session").status_code == 401

            _login_with_password(managed_client, username, CHANGED_PASSWORD)
            reset = admin_client.post(
                f"/api/admin/users/{user_id}/reset-password",
                json={"temporary_password": RESET_PASSWORD},
                headers={"X-CSRF-Token": admin_csrf},
            )
            assert reset.status_code == 200
            assert managed_client.get("/api/auth/session").status_code == 401

        with _client(postgres_engine, period) as old_password_client:
            assert old_password_client.post(
                "/api/auth/login",
                json={"username": username, "password": CHANGED_PASSWORD},
            ).status_code == 401

        with _client(postgres_engine, period) as reset_client:
            _login_with_password(reset_client, username, RESET_PASSWORD)
            assert reset_client.get("/api/manager/transport/periods").status_code == 403
            deactivated = admin_client.post(
                f"/api/admin/users/{user_id}/deactivate",
                headers={"X-CSRF-Token": admin_csrf},
            )
            assert deactivated.status_code == 200
            assert reset_client.get("/api/auth/session").status_code == 401
        with _client(postgres_engine, period) as inactive_client:
            login = inactive_client.post(
                "/api/auth/login",
                json={"username": username, "password": RESET_PASSWORD},
            )
            assert login.status_code == 401
            assert login.json()["error"]["message"] == "Invalid username or password."

        activated = admin_client.post(
            f"/api/admin/users/{user_id}/activate",
            headers={"X-CSRF-Token": admin_csrf},
        )
        assert activated.status_code == 200
        assert admin_client.post(
            f"/api/admin/users/{created_user['id']}/deactivate"
        ).status_code == 403
        own_deactivation = admin_client.post(
            f"/api/admin/users/{admin_client.get('/api/auth/session').json()['user']['id']}/deactivate",
            headers={"X-CSRF-Token": admin_csrf},
        )
        assert own_deactivation.status_code == 409

        with Session(postgres_engine) as db:
            db.add(
                AuditLog(
                    actor_user_id=UUID(admin_client.get("/api/auth/session").json()["user"]["id"]),
                    actor_type="user",
                    event_type="security.sanitization_test",
                    target_type="test",
                    target_reference="safe-reference",
                    outcome="succeeded",
                    safe_metadata={
                        "safe_note": "visible-safe-note",
                        "password": "must-not-appear",
                        "session_token": "must-not-appear",
                        "evidence_path": "must-not-appear",
                    },
                )
            )
            db.commit()

        audit = admin_client.get("/api/admin/audit-logs?page_size=100")
        assert audit.status_code == 200, audit.text
        actions = {item["action"] for item in audit.json()["items"]}
        assert {
            "admin.user_created",
            "admin.password_reset",
            "admin.user_deactivated",
            "admin.user_activated",
            "admin.sessions_revoked",
        }.issubset(actions)
        assert TEMP_PASSWORD not in audit.text
        assert CHANGED_PASSWORD not in audit.text
        assert RESET_PASSWORD not in audit.text
        assert "visible-safe-note" in audit.text
        assert "must-not-appear" not in audit.text
        assert audit.headers["cache-control"] == "private, no-store"
        assert audit.headers["x-content-type-options"] == "nosniff"


def test_submission_optimistic_concurrency_and_numeric_validation(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2196)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    values = _values(postgres_engine, OperationalDomain.TRANSPORT, include_optional_zero=True)

    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        created = client.post(
            "/api/manager/transport/submissions",
            json={"reporting_period_id": str(period.id), "remarks": "Initial", "values": values},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201, created.text
        submission = created.json()
        stale_version = submission["row_version"]

        first = client.put(
            f"/api/manager/transport/submissions/{submission['id']}",
            json={"remarks": "Fresh edit", "values": values, "expected_row_version": stale_version},
            headers={"X-CSRF-Token": csrf},
        )
        assert first.status_code == 200
        stale = client.put(
            f"/api/manager/transport/submissions/{submission['id']}",
            json={"remarks": "Stale edit", "values": values, "expected_row_version": stale_version},
            headers={"X-CSRF-Token": csrf},
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "stale_submission"
        assert client.get(f"/api/manager/transport/submissions/{submission['id']}").json()["remarks"] == "Fresh edit"

        assert client.put(
            f"/api/manager/transport/submissions/{submission['id']}",
            json={"remarks": "Missing version", "values": values},
            headers={"X-CSRF-Token": csrf},
        ).status_code == 422

        for invalid_value in ("NaN", "Infinity", "-Infinity", "not-a-number", "-1"):
            invalid_values = [dict(item) for item in values]
            invalid_values[0]["value"] = invalid_value
            response = client.put(
                f"/api/manager/transport/submissions/{submission['id']}",
                json={
                    "remarks": "Invalid numeric value",
                    "values": invalid_values,
                    "expected_row_version": first.json()["row_version"],
                },
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status_code == 422, invalid_value

        fractional_count = [dict(item) for item in values]
        count_metric = next(
            (item for item in fractional_count if item["metric_code"] == "petrol_vehicle_count"),
            None,
        )
        if count_metric is None:
            fractional_count.append({"metric_code": "petrol_vehicle_count", "value": "1.5"})
        else:
            count_metric["value"] = "1.5"
        invalid = client.put(
            f"/api/manager/transport/submissions/{submission['id']}",
            json={
                "remarks": "Invalid fractional count",
                "values": fractional_count,
                "expected_row_version": first.json()["row_version"],
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert invalid.status_code == 422

        oversized = client.put(
            f"/api/manager/transport/submissions/{submission['id']}",
            json={
                "remarks": "x" * 4001,
                "values": values,
                "expected_row_version": first.json()["row_version"],
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert oversized.status_code == 422


def test_complete_role_domain_authorization_matrix(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2197)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    managers = {domain: _account(postgres_engine, RoleCode.MANAGER, domain) for domain in ALL_DOMAINS}
    generic_domains = [
        OperationalDomain.TRANSPORT,
        OperationalDomain.ENERGY,
        OperationalDomain.LPG,
        OperationalDomain.WATER,
    ]

    with _client(postgres_engine, period) as anonymous:
        assert anonymous.get("/api/manager/transport/periods").status_code == 401
        assert anonymous.get("/api/manager/outreach/current-period").status_code == 401
        assert anonymous.get("/api/admin/review-queue?domain=transport").status_code == 401
        assert anonymous.get("/api/admin/evidence").status_code == 401
        assert anonymous.get("/api/admin/users").status_code == 401
        assert anonymous.get("/api/admin/audit-logs").status_code == 401
        assert anonymous.get(
            f"/api/admin/reporting-periods/{period.id}/publication-readiness"
        ).status_code == 401

    with _client(postgres_engine, period) as admin_client:
        admin_csrf = _login(admin_client, admin)
        assert admin_client.get("/api/admin/review-queue?domain=transport").status_code == 200
        assert admin_client.get("/api/admin/evidence").status_code == 200
        assert admin_client.get("/api/admin/users").status_code == 200
        assert admin_client.get("/api/admin/audit-logs").status_code == 200
        assert admin_client.get(
            f"/api/admin/reporting-periods/{period.id}/publication-readiness"
        ).status_code == 200
        assert admin_client.get("/api/manager/transport/periods").status_code == 403
        assert admin_client.get("/api/manager/outreach/current-period").status_code == 403
        assert admin_client.put(
            f"/api/manager/transport/submissions/{uuid4()}",
            json={"remarks": None, "values": [], "expected_row_version": 1},
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 403

    for own_domain, username in managers.items():
        with _client(postgres_engine, period) as manager_client:
            _login(manager_client, username)
            if own_domain == OperationalDomain.OUTREACH:
                assert manager_client.get("/api/manager/outreach/current-period").status_code == 200
            else:
                assert manager_client.get(f"/api/manager/{own_domain.value}/periods").status_code == 200
            for other_domain in generic_domains:
                if other_domain != own_domain:
                    assert manager_client.get(
                        f"/api/manager/{other_domain.value}/periods"
                    ).status_code == 403
            if own_domain != OperationalDomain.OUTREACH:
                assert manager_client.get("/api/manager/outreach/current-period").status_code == 403
            assert manager_client.get("/api/admin/review-queue?domain=transport").status_code == 403
            assert manager_client.get("/api/admin/evidence").status_code == 403
            assert manager_client.get("/api/admin/users").status_code == 403
            assert manager_client.get("/api/admin/audit-logs").status_code == 403
            assert manager_client.get(
                f"/api/admin/reporting-periods/{period.id}/publication-readiness"
            ).status_code == 403
