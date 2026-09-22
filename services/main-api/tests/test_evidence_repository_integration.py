from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.models.enums import OperationalDomain, RoleCode
from tests.test_evidence_integration import DOMAINS, PDF, _client, _draft, _upload
from tests.test_generic_submission_integration import _account, _login, _values


def _repository(client: TestClient, **parameters: object):
    return client.get(f"/api/admin/evidence?{urlencode(parameters)}")


@pytest.mark.parametrize("domain", DOMAINS)
def test_repository_domain_matrix_and_temporary_privacy(
    postgres_engine: Engine, tmp_path: Path, domain: OperationalDomain
) -> None:
    storage = tmp_path / f"repository-{domain.value}"
    manager = _account(postgres_engine, RoleCode.MANAGER, domain)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    year = 2110 + DOMAINS.index(domain)

    with _client(postgres_engine, storage) as manager_client, _client(
        postgres_engine, storage
    ) as admin_client, _client(postgres_engine, storage) as anonymous:
        manager_csrf = _login(manager_client, manager)
        _login(admin_client, admin)
        submission_id, period = _draft(
            manager_client, manager_csrf, postgres_engine, domain, year
        )
        temporary = _upload(
            manager_client,
            manager_csrf,
            domain,
            submission_id,
            filename=f"{domain.value}-temporary.pdf",
        ).json()
        filters = {
            "year": period.year,
            "month": period.month,
            "domain": domain.value,
            "submission_id": submission_id,
            "latest_revision": "false",
        }

        before_submit = _repository(admin_client, **filters)
        assert before_submit.status_code == 200
        assert before_submit.json()["items"] == []
        assert admin_client.get(
            f"/api/admin/evidence/{temporary['id']}/content"
        ).status_code == 404
        assert _repository(manager_client, **filters).status_code == 403
        assert _repository(anonymous, **filters).status_code == 401

        submitted = manager_client.post(
            f"/api/manager/{domain.value}/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": manager_csrf},
        )
        assert submitted.status_code == 200, submitted.text
        result = _repository(admin_client, **filters)
        assert result.status_code == 200, result.text
        payload = result.json()
        assert payload["total_items"] == 1
        item = payload["items"][0]
        assert item["evidence_id"] == temporary["id"]
        assert item["domain"] == domain.value
        assert item["reporting_period"] == {
            "id": str(period.id), "year": period.year, "month": period.month
        }
        assert item["is_latest_revision"] is True
        assert "storage_key" not in item and "path" not in item
        assert admin_client.get(
            f"/api/admin/evidence/{temporary['id']}/content"
        ).status_code == 200


def test_repository_filters_and_removed_draft_exclusion(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    domain = OperationalDomain.TRANSPORT
    storage = tmp_path / "repository-filters"
    manager = _account(postgres_engine, RoleCode.MANAGER, domain)
    admin = _account(postgres_engine, RoleCode.ADMIN)

    with _client(postgres_engine, storage) as manager_client, _client(
        postgres_engine, storage
    ) as admin_client:
        manager_csrf = _login(manager_client, manager)
        _login(admin_client, admin)
        submission_id, period = _draft(
            manager_client, manager_csrf, postgres_engine, domain, 2120
        )
        wrong = _upload(
            manager_client, manager_csrf, domain, submission_id, filename="wrong.pdf"
        ).json()
        assert manager_client.delete(
            f"/api/manager/transport/submissions/{submission_id}/evidence/{wrong['id']}",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200

        metric_code = str(_values(postgres_engine, domain)[0]["metric_code"])
        correct = manager_client.post(
            f"/api/manager/transport/submissions/{submission_id}/evidence",
            files={"file": ("Correct-Proof.PDF", PDF, "application/pdf")},
            data={"metric_code": metric_code},
            headers={"X-CSRF-Token": manager_csrf},
        )
        assert correct.status_code == 201, correct.text
        assert manager_client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200

        filters = {
            "year": period.year,
            "month": period.month,
            "domain": "transport",
            "submission_id": submission_id,
            "submission_status": "submitted",
            "revision_number": 1,
            "metric_code": metric_code,
            "filename": "correct-proof",
        }
        result = _repository(admin_client, **filters).json()
        assert result["total_items"] == 1
        assert result["items"][0]["evidence_id"] == correct.json()["id"]
        assert result["items"][0]["metric_display_name"]
        assert _repository(admin_client, **{**filters, "filename": "wrong"}).json()[
            "total_items"
        ] == 0
        assert _repository(admin_client, **{**filters, "year": period.year + 1}).json()[
            "total_items"
        ] == 0
        other_month = 1 if period.month != 1 else 2
        assert _repository(admin_client, **{**filters, "month": other_month}).json()[
            "total_items"
        ] == 0
        assert _repository(
            admin_client, **{**filters, "submission_status": "approved"}
        ).json()["total_items"] == 0


def test_repository_latest_and_all_revision_history(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    domain = OperationalDomain.TRANSPORT
    storage = tmp_path / "repository-revisions"
    manager = _account(postgres_engine, RoleCode.MANAGER, domain)
    admin = _account(postgres_engine, RoleCode.ADMIN)

    with _client(postgres_engine, storage) as manager_client, _client(
        postgres_engine, storage
    ) as admin_client:
        manager_csrf = _login(manager_client, manager)
        admin_csrf = _login(admin_client, admin)
        submission_id, period = _draft(
            manager_client, manager_csrf, postgres_engine, domain, 2130
        )
        first = _upload(
            manager_client, manager_csrf, domain, submission_id, filename="revision-a.pdf"
        ).json()
        assert manager_client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/begin-review",
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 200
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/request-correction",
            json={"reason": "Replace supporting evidence."},
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 200

        mistake = _upload(
            manager_client,
            manager_csrf,
            domain,
            submission_id,
            content=b"%PDF-1.4\nrevision mistake\n%%EOF\n",
            filename="revision-b.pdf",
            replaces=first["id"],
        ).json()
        assert manager_client.delete(
            f"/api/manager/transport/submissions/{submission_id}/evidence/{mistake['id']}",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200
        corrected = _upload(
            manager_client,
            manager_csrf,
            domain,
            submission_id,
            content=b"%PDF-1.4\nrevision corrected\n%%EOF\n",
            filename="revision-c.pdf",
            replaces=first["id"],
        ).json()
        assert manager_client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200

        base = {
            "year": period.year,
            "month": period.month,
            "domain": "transport",
            "submission_id": submission_id,
        }
        latest = _repository(admin_client, **base).json()
        assert [item["evidence_id"] for item in latest["items"]] == [corrected["id"]]
        all_revisions = _repository(
            admin_client, **base, latest_revision="false"
        ).json()
        assert [item["evidence_id"] for item in all_revisions["items"]] == [
            corrected["id"], first["id"]
        ]
        assert [item["revision_number"] for item in all_revisions["items"]] == [2, 1]
        assert mistake["id"] not in {item["evidence_id"] for item in all_revisions["items"]}


def test_repository_pagination_is_stable(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    domain = OperationalDomain.ENERGY
    storage = tmp_path / "repository-pagination"
    manager = _account(postgres_engine, RoleCode.MANAGER, domain)
    admin = _account(postgres_engine, RoleCode.ADMIN)

    with _client(postgres_engine, storage) as manager_client, _client(
        postgres_engine, storage
    ) as admin_client:
        manager_csrf = _login(manager_client, manager)
        _login(admin_client, admin)
        submission_id, period = _draft(
            manager_client, manager_csrf, postgres_engine, domain, 2140
        )
        for suffix in ("a", "b", "c"):
            assert _upload(
                manager_client,
                manager_csrf,
                domain,
                submission_id,
                filename=f"page-proof-{suffix}.pdf",
            ).status_code == 201
        assert manager_client.post(
            f"/api/manager/energy/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200

        filters = {
            "year": period.year,
            "month": period.month,
            "domain": "energy",
            "submission_id": submission_id,
            "filename": "page-proof",
            "page_size": 2,
        }
        first_page = _repository(admin_client, **filters, page=1).json()
        repeated_page = _repository(admin_client, **filters, page=1).json()
        second_page = _repository(admin_client, **filters, page=2).json()
        assert first_page["total_items"] == 3
        assert first_page["total_pages"] == 2
        assert len(first_page["items"]) == 2 and len(second_page["items"]) == 1
        first_ids = [item["evidence_id"] for item in first_page["items"]]
        assert first_ids == [item["evidence_id"] for item in repeated_page["items"]]
        assert set(first_ids).isdisjoint(
            {item["evidence_id"] for item in second_page["items"]}
        )
