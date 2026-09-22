import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models.enums import OperationalDomain, RoleCode
from app.models.sustainability import Submission
from tests.test_generic_submission_integration import _account, _client, _login, _period, _values

GENERIC_DOMAINS = [
    OperationalDomain.TRANSPORT,
    OperationalDomain.ENERGY,
    OperationalDomain.LPG,
    OperationalDomain.WATER,
]


@pytest.mark.parametrize("domain", GENERIC_DOMAINS)
def test_save_refresh_update_submit_keeps_one_authoritative_submission(
    postgres_engine: Engine, domain: OperationalDomain
) -> None:
    period = _period(postgres_engine, 2188 + GENERIC_DOMAINS.index(domain))
    manager = _account(postgres_engine, RoleCode.MANAGER, domain)
    values = _values(postgres_engine, domain, include_optional_zero=True)
    first_metric = values[0]["metric_code"]
    payload = {
        "reporting_period_id": str(period.id),
        "remarks": "Save refresh regression draft",
        "values": values,
    }

    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        created = client.post(
            f"/api/manager/{domain.value}/submissions",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201, created.text
        submission_id = created.json()["id"]
        current_url = (
            f"/api/manager/{domain.value}/submissions/current?reporting_period_id={period.id}"
        )
        after_create = client.get(current_url)
        assert after_create.status_code == 200
        assert after_create.json()["id"] == submission_id
        assert after_create.json()["status"] == "draft"

        updated_values = [
            {**item, "value": "17"} if item["metric_code"] == first_metric else item
            for item in values
        ]
        updated = client.put(
            f"/api/manager/{domain.value}/submissions/{submission_id}",
            json={
                "remarks": "Updated draft",
                "values": updated_values,
                "expected_row_version": after_create.json()["row_version"],
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["id"] == submission_id
        after_update = client.get(current_url).json()
        assert after_update["id"] == submission_id
        assert next(
            item["value"] for item in after_update["values"] if item["metric_code"] == first_metric
        ) == "17.000000"

        duplicate_save = client.post(
            f"/api/manager/{domain.value}/submissions",
            json={
                **payload,
                "remarks": "Repeated create-path save",
                "values": updated_values,
                "expected_row_version": updated.json()["row_version"],
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert duplicate_save.status_code == 201
        assert duplicate_save.json()["id"] == submission_id

        submitted = client.post(
            f"/api/manager/{domain.value}/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        )
        assert submitted.status_code == 200, submitted.text
        after_submit = client.get(current_url).json()
        assert after_submit["id"] == submission_id
        assert after_submit["status"] == "submitted"
        assert next(
            item["value"] for item in after_submit["values"] if item["metric_code"] == first_metric
        ) == "17.000000"
        assert client.put(
            f"/api/manager/{domain.value}/submissions/{submission_id}",
            json={
                "remarks": "Forbidden",
                "values": updated_values,
                "expected_row_version": after_submit["row_version"],
            },
            headers={"X-CSRF-Token": csrf},
        ).status_code == 409

    with Session(postgres_engine) as db:
        active_count = db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.manager_user_id == created.json()["manager_user_id"],
                Submission.domain == domain,
                Submission.reporting_period_id == period.id,
            )
        )
        assert active_count == 1


@pytest.mark.parametrize(
    ("domain", "year"),
    [
        (OperationalDomain.ENERGY, 2150),
        (OperationalDomain.LPG, 2160),
        (OperationalDomain.WATER, 2170),
    ],
)
def test_generic_domain_complete_review_lifecycle(
    postgres_engine: Engine, domain: OperationalDomain, year: int
) -> None:
    period = _period(postgres_engine, year)
    manager = _account(postgres_engine, RoleCode.MANAGER, domain)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    values = _values(postgres_engine, domain, include_optional_zero=True)
    payload = {"reporting_period_id": str(period.id), "remarks": "Domain matrix draft", "values": values}

    with _client(postgres_engine, period) as manager_client, _client(postgres_engine) as admin_client:
        manager_csrf = _login(manager_client, manager)
        admin_csrf = _login(admin_client, admin)

        created = manager_client.post(
            f"/api/manager/{domain.value}/submissions",
            json=payload,
            headers={"X-CSRF-Token": manager_csrf},
        )
        assert created.status_code == 201
        submission_id = created.json()["id"]
        current_url = (
            f"/api/manager/{domain.value}/submissions/current?reporting_period_id={period.id}"
        )
        assert manager_client.get(current_url).json()["id"] == submission_id

        assert (
            manager_client.post(
                f"/api/manager/{domain.value}/submissions/{submission_id}/submit",
                headers={"X-CSRF-Token": manager_csrf},
            ).status_code
            == 200
        )
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
                json={"reason": f"Verify {domain.value} values."},
                headers={"X-CSRF-Token": admin_csrf},
            ).status_code
            == 200
        )

        corrected = manager_client.put(
            f"/api/manager/{domain.value}/submissions/{submission_id}",
            json={
                "remarks": "Corrected",
                "values": values,
                "expected_row_version": manager_client.get(current_url).json()["row_version"],
            },
            headers={"X-CSRF-Token": manager_csrf},
        )
        assert corrected.status_code == 200
        assert corrected.json()["status"] == "correction_requested"
        assert (
            manager_client.post(
                f"/api/manager/{domain.value}/submissions/{submission_id}/submit",
                headers={"X-CSRF-Token": manager_csrf},
            ).status_code
            == 200
        )
        assert manager_client.get(current_url).json()["revision_number"] == 2

        assert (
            admin_client.post(
                f"/api/admin/submissions/{submission_id}/approve",
                headers={"X-CSRF-Token": admin_csrf},
            ).status_code
            == 200
        )
        assert manager_client.get(current_url).json()["status"] == "approved"
        assert (
            manager_client.put(
                f"/api/manager/{domain.value}/submissions/{submission_id}",
                json={
                    "remarks": "Forbidden",
                    "values": values,
                    "expected_row_version": manager_client.get(current_url).json()["row_version"],
                },
                headers={"X-CSRF-Token": manager_csrf},
            ).status_code
            == 409
        )
