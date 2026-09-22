from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.models.audit import AuditLog
from app.models.enums import OperationalDomain, RoleCode
from app.models.sustainability import ReportingPeriod, SubmissionEvidence
from app.services.publication import build_release_payload
from tests.test_generic_submission_integration import _account, _login, _period, _values
from tests.test_outreach_integration import _programme

PDF = b"%PDF-1.4\n% private test evidence\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"private-test-png"
JPEG = b"\xff\xd8\xff\xe0" + b"private-test-jpeg" + b"\xff\xd9"
DOMAINS = list(OperationalDomain)


def _client(engine: Engine, storage: Path) -> TestClient:
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=str(engine.url),
        EVIDENCE_ROOT=storage.parent / "evidence-root",
        EVIDENCE_STORAGE_DIR=storage,
    )
    return TestClient(create_app(settings, engine))


def _draft(
    client: TestClient,
    csrf: str,
    engine: Engine,
    domain: OperationalDomain,
    year: int,
) -> tuple[str, ReportingPeriod]:
    period = _period(engine, year)
    client.app.state.institutional_clock = lambda: datetime(
        period.year, period.month, 15, tzinfo=UTC
    )
    if domain == OperationalDomain.OUTREACH:
        response = client.post(
            "/api/manager/outreach/programmes",
            json=_programme(period, f"Evidence programme {year}"),
            headers={"X-CSRF-Token": csrf},
        )
    else:
        response = client.post(
            f"/api/manager/{domain.value}/submissions",
            json={
                "reporting_period_id": str(period.id),
                "remarks": "Evidence workflow draft",
                "values": _values(engine, domain, include_optional_zero=True),
            },
            headers={"X-CSRF-Token": csrf},
        )
    assert response.status_code == 201, response.text
    return response.json()["submission_id" if domain == OperationalDomain.OUTREACH else "id"], period


def _upload(
    client: TestClient,
    csrf: str,
    domain: OperationalDomain,
    submission_id: str,
    *,
    content: bytes = PDF,
    filename: str = "evidence.pdf",
    mime_type: str = "application/pdf",
    replaces: str | None = None,
) -> Response:
    data = {"evidence_category": "supporting_document"}
    if replaces:
        data["replaces_evidence_id"] = replaces
    return client.post(
        f"/api/manager/{domain.value}/submissions/{submission_id}/evidence",
        files={"file": (filename, content, mime_type)},
        data=data,
        headers={"X-CSRF-Token": csrf},
    )


@pytest.mark.parametrize("domain", DOMAINS)
def test_evidence_complete_domain_workflow(
    postgres_engine: Engine, tmp_path: Path, domain: OperationalDomain
) -> None:
    storage = tmp_path / domain.value
    manager = _account(postgres_engine, RoleCode.MANAGER, domain)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    year = 2050 + DOMAINS.index(domain)

    with _client(postgres_engine, storage) as manager_client, _client(postgres_engine, storage) as admin_client:
        manager_csrf = _login(manager_client, manager)
        admin_csrf = _login(admin_client, admin)
        submission_id, _period_record = _draft(manager_client, manager_csrf, postgres_engine, domain, year)

        uploaded = _upload(manager_client, manager_csrf, domain, submission_id)
        assert uploaded.status_code == 201, uploaded.text
        first = uploaded.json()
        assert first["revision_number"] == 1 and first["is_current"] is True
        assert first["lifecycle_state"] == "temporary" and first["committed_at"] is None
        assert "storage_key" not in first and "path" not in first
        assert manager_client.get(
            f"/api/manager/{domain.value}/submissions/{submission_id}/evidence"
        ).json()[0]["id"] == first["id"]

        content = manager_client.get(f"/api/manager/{domain.value}/evidence/{first['id']}/content")
        assert content.status_code == 200 and content.content == PDF
        assert content.headers["content-type"].startswith("application/pdf")
        assert content.headers["x-content-type-options"] == "nosniff"
        assert "inline" in content.headers["content-disposition"]
        assert admin_client.get(f"/api/admin/submissions/{submission_id}/evidence").json() == []
        assert admin_client.get(f"/api/admin/evidence/{first['id']}/content").status_code == 404

        assert manager_client.post(
            f"/api/manager/{domain.value}/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200
        committed = manager_client.get(
            f"/api/manager/{domain.value}/submissions/{submission_id}/evidence"
        ).json()[0]
        assert committed["lifecycle_state"] == "committed"
        assert committed["committed_at"] is not None
        assert _upload(manager_client, manager_csrf, domain, submission_id).status_code == 409
        assert manager_client.delete(
            f"/api/manager/{domain.value}/submissions/{submission_id}/evidence/{first['id']}",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 409

        queue = admin_client.get(
            "/api/admin/review-queue",
            params={"domain": domain.value, "reporting_period_id": str(_period_record.id)},
        )
        assert queue.status_code == 200, queue.text
        assert [item["id"] for item in queue.json()] == [submission_id]
        admin_evidence = admin_client.get(f"/api/admin/submissions/{submission_id}/evidence")
        assert admin_evidence.status_code == 200
        assert [item["id"] for item in admin_evidence.json()] == [first["id"]]
        inline = admin_client.get(f"/api/admin/evidence/{first['id']}/content")
        assert inline.status_code == 200 and inline.content == PDF
        assert inline.headers["content-type"].startswith("application/pdf")
        assert "inline" in inline.headers["content-disposition"]
        download = admin_client.get(f"/api/admin/evidence/{first['id']}/content?download=true")
        assert download.status_code == 200 and download.content == PDF
        assert "attachment" in download.headers["content-disposition"]
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/begin-review",
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 200
        assert _upload(manager_client, manager_csrf, domain, submission_id).status_code == 409
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/request-correction",
            json={"reason": "Replace the supporting document."},
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 200
        assert manager_client.delete(
            f"/api/manager/{domain.value}/submissions/{submission_id}/evidence/{first['id']}",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 409

        correction_mistake = _upload(
            manager_client,
            manager_csrf,
            domain,
            submission_id,
            content=b"%PDF-1.4\ncorrection mistake\n%%EOF\n",
            filename="correction-mistake.pdf",
            replaces=first["id"],
        )
        assert correction_mistake.status_code == 201, correction_mistake.text
        assert manager_client.delete(
            f"/api/manager/{domain.value}/submissions/{submission_id}/evidence/"
            f"{correction_mistake.json()['id']}",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200
        after_correction_remove = manager_client.get(
            f"/api/manager/{domain.value}/submissions/{submission_id}/evidence"
        ).json()
        assert [item["id"] for item in after_correction_remove] == [first["id"]]
        assert len(list(storage.iterdir())) == 1

        replacement = _upload(
            manager_client,
            manager_csrf,
            domain,
            submission_id,
            content=b"%PDF-1.4\ncorrected final\n%%EOF\n",
            filename="corrected-final.pdf",
            replaces=first["id"],
        )
        assert replacement.status_code == 201, replacement.text
        assert replacement.json()["revision_number"] == 2
        assert replacement.json()["lifecycle_state"] == "temporary"
        evidence = manager_client.get(
            f"/api/manager/{domain.value}/submissions/{submission_id}/evidence"
        ).json()
        assert len(evidence) == 2
        assert sum(item["is_current"] for item in evidence) == 2
        previous = next(item for item in evidence if item["id"] == first["id"])
        assert previous["lifecycle_state"] == "committed"
        assert previous["replaced_by_evidence_id"] is None
        admin_during_correction = admin_client.get(
            f"/api/admin/submissions/{submission_id}/evidence"
        ).json()
        assert [item["id"] for item in admin_during_correction] == [first["id"]]

        assert manager_client.post(
            f"/api/manager/{domain.value}/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200
        admin_after_resubmit = admin_client.get(
            f"/api/admin/submissions/{submission_id}/evidence"
        ).json()
        assert {item["id"] for item in admin_after_resubmit} == {
            first["id"], replacement.json()["id"]
        }
        assert {item["revision_number"] for item in admin_after_resubmit} == {1, 2}
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/approve",
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 200
        assert _upload(manager_client, manager_csrf, domain, submission_id).status_code == 409


@pytest.mark.parametrize("domain", DOMAINS)
def test_evidence_remove_and_reupload_domain_matrix(
    postgres_engine: Engine, tmp_path: Path, domain: OperationalDomain
) -> None:
    storage = tmp_path / f"remove-reupload-{domain.value}"
    manager = _account(postgres_engine, RoleCode.MANAGER, domain)
    year = 2070 + DOMAINS.index(domain)

    with _client(postgres_engine, storage) as client:
        csrf = _login(client, manager)
        submission_id, _period_record = _draft(client, csrf, postgres_engine, domain, year)
        evidence_url = f"/api/manager/{domain.value}/submissions/{submission_id}/evidence"

        first_response = _upload(
            client, csrf, domain, submission_id, content=PDF, filename="diesel_bill.pdf"
        )
        assert first_response.status_code == 201, first_response.text
        first = first_response.json()
        assert first["is_current"] is True and first["lifecycle_state"] == "temporary"
        assert len(list(storage.iterdir())) == 1

        removed = client.delete(
            f"{evidence_url}/{first['id']}", headers={"X-CSRF-Token": csrf}
        )
        assert removed.status_code == 200, removed.text
        assert removed.json() == {"message": "Temporary evidence removed."}
        after_remove = client.get(evidence_url)
        assert after_remove.status_code == 200
        assert after_remove.json() == []
        assert list(storage.iterdir()) == []

        # An identical file is intentionally accepted as a new record. Historical
        # checksum equality must not act as deduplication or reactivate the old row.
        same_response = _upload(
            client, csrf, domain, submission_id, content=PDF, filename="diesel_bill.pdf"
        )
        assert same_response.status_code == 201, same_response.text
        same = same_response.json()
        assert same["id"] != first["id"]
        assert same["sha256"] == first["sha256"]
        assert same["is_current"] is True

        assert client.delete(
            f"{evidence_url}/{same['id']}", headers={"X-CSRF-Token": csrf}
        ).status_code == 200
        different_response = _upload(
            client,
            csrf,
            domain,
            submission_id,
            content=b"%PDF-1.4\nnew evidence B\n%%EOF\n",
            filename="different_bill.pdf",
        )
        assert different_response.status_code == 201, different_response.text
        different = different_response.json()
        final_list = client.get(evidence_url).json()
        active = [item for item in final_list if item["is_current"] and item["removed_at"] is None]
        assert [item["id"] for item in active] == [different["id"]]
        assert {item["id"] for item in final_list} == {different["id"]}

        # Deleted temporary metadata is no longer addressable.
        assert client.delete(
            f"{evidence_url}/{first['id']}", headers={"X-CSRF-Token": csrf}
        ).status_code == 404

    with Session(postgres_engine) as db:
        rows = {
            str(record.id): record
            for record in db.scalars(
                select(SubmissionEvidence).where(
                    SubmissionEvidence.submission_id == submission_id
                )
            ).all()
        }
        different_row = rows[different["id"]]
        assert set(rows) == {different["id"]}
        assert different_row.is_current is True and different_row.removed_at is None
        assert different_row.committed_at is None
        assert all((storage / row.storage_key).is_file() for row in rows.values())
        temporary_events = list(
            db.scalars(
                select(AuditLog.event_type).where(
                    AuditLog.target_type == "submission_evidence",
                    AuditLog.target_reference.in_([first["id"], same["id"], different["id"]]),
                )
            ).all()
        )
        assert temporary_events == []


def test_evidence_replace_remove_and_reinsert_chain(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    domain = OperationalDomain.TRANSPORT
    storage = tmp_path / "replace-remove-reinsert"
    manager = _account(postgres_engine, RoleCode.MANAGER, domain)

    with _client(postgres_engine, storage) as client:
        csrf = _login(client, manager)
        submission_id, _period_record = _draft(client, csrf, postgres_engine, domain, 2080)
        evidence_url = f"/api/manager/transport/submissions/{submission_id}/evidence"
        first = _upload(client, csrf, domain, submission_id, filename="a.pdf").json()
        second_response = _upload(
            client,
            csrf,
            domain,
            submission_id,
            content=b"%PDF-1.4\nreplacement B\n%%EOF\n",
            filename="b.pdf",
            replaces=first["id"],
        )
        assert second_response.status_code == 201, second_response.text
        second = second_response.json()
        third_response = _upload(
            client,
            csrf,
            domain,
            submission_id,
            content=b"%PDF-1.4\nreplacement C\n%%EOF\n",
            filename="c.pdf",
            replaces=second["id"],
        )
        assert third_response.status_code == 201, third_response.text
        third = third_response.json()

        assert client.delete(
            f"{evidence_url}/{third['id']}", headers={"X-CSRF-Token": csrf}
        ).status_code == 200
        removed_list = client.get(evidence_url).json()
        assert removed_list == []
        assert list(storage.iterdir()) == []

        fourth_response = _upload(
            client,
            csrf,
            domain,
            submission_id,
            content=b"%PDF-1.4\nnew evidence D\n%%EOF\n",
            filename="d.pdf",
        )
        assert fourth_response.status_code == 201, fourth_response.text
        fourth = fourth_response.json()
        final_list = client.get(evidence_url).json()
        assert [item["id"] for item in final_list if item["is_current"]] == [fourth["id"]]

    with Session(postgres_engine) as db:
        rows = {
            str(record.id): record
            for record in db.scalars(
                select(SubmissionEvidence).where(
                    SubmissionEvidence.submission_id == submission_id
                )
            ).all()
        }
        assert set(rows) == {fourth["id"]}
        assert rows[fourth["id"]].is_current is True
        assert all((storage / row.storage_key).is_file() for row in rows.values())
        events = list(
            db.scalars(
                select(AuditLog.event_type).where(
                    AuditLog.target_type == "submission_evidence",
                    AuditLog.target_reference.in_(list(rows)),
                )
            ).all()
        )
        assert events == []


def test_failed_submit_keeps_evidence_temporary_and_editable(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    domain = OperationalDomain.TRANSPORT
    storage = tmp_path / "failed-submit"
    manager = _account(postgres_engine, RoleCode.MANAGER, domain)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    period = _period(postgres_engine, 2090)

    with _client(postgres_engine, storage) as manager_client, _client(
        postgres_engine, storage
    ) as admin_client:
        manager_client.app.state.institutional_clock = lambda: datetime(
            period.year, period.month, 15, tzinfo=UTC
        )
        manager_csrf = _login(manager_client, manager)
        _login(admin_client, admin)
        draft = manager_client.post(
            "/api/manager/transport/submissions",
            json={"reporting_period_id": str(period.id), "remarks": None, "values": []},
            headers={"X-CSRF-Token": manager_csrf},
        )
        assert draft.status_code == 201, draft.text
        submission_id = draft.json()["id"]
        uploaded = _upload(manager_client, manager_csrf, domain, submission_id).json()

        failed = manager_client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": manager_csrf},
        )
        assert failed.status_code == 422
        assert manager_client.get(
            f"/api/manager/transport/submissions/{submission_id}"
        ).json()["status"] == "draft"
        current = manager_client.get(
            f"/api/manager/transport/submissions/{submission_id}/evidence"
        ).json()
        assert current[0]["id"] == uploaded["id"]
        assert current[0]["lifecycle_state"] == "temporary"
        assert current[0]["committed_at"] is None
        assert admin_client.get(f"/api/admin/submissions/{submission_id}/evidence").json() == []
        assert manager_client.delete(
            f"/api/manager/transport/submissions/{submission_id}/evidence/{uploaded['id']}",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200
        assert list(storage.iterdir()) == []

        retried_upload = _upload(manager_client, manager_csrf, domain, submission_id).json()
        assert retried_upload["sha256"] == uploaded["sha256"]
        saved = manager_client.put(
            f"/api/manager/transport/submissions/{submission_id}",
            json={
                "remarks": "Complete after validation failure",
                "values": _values(postgres_engine, domain, include_optional_zero=True),
                "expected_row_version": manager_client.get(
                    f"/api/manager/transport/submissions/{submission_id}"
                ).json()["row_version"],
            },
            headers={"X-CSRF-Token": manager_csrf},
        )
        assert saved.status_code == 200, saved.text
        assert manager_client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200
        after_retry = manager_client.get(
            f"/api/manager/transport/submissions/{submission_id}/evidence"
        ).json()
        assert [item["id"] for item in after_retry] == [retried_upload["id"]]
        assert after_retry[0]["lifecycle_state"] == "committed"
        assert [item["id"] for item in admin_client.get(
            f"/api/admin/submissions/{submission_id}/evidence"
        ).json()] == [retried_upload["id"]]


def test_evidence_security_validation_audit_and_publication_privacy(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    storage = tmp_path / "security"
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    wrong_manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.ENERGY)
    admin = _account(postgres_engine, RoleCode.ADMIN)

    with _client(postgres_engine, storage) as manager_client, _client(
        postgres_engine, storage
    ) as wrong_client, _client(postgres_engine, storage) as admin_client, _client(
        postgres_engine, storage
    ) as anonymous:
        manager_csrf = _login(manager_client, manager)
        _login(wrong_client, wrong_manager)
        admin_csrf = _login(admin_client, admin)
        submission_id, period = _draft(
            manager_client, manager_csrf, postgres_engine, OperationalDomain.TRANSPORT, 2060
        )
        upload_url = f"/api/manager/transport/submissions/{submission_id}/evidence"

        assert anonymous.post(
            upload_url,
            files={"file": ("evidence.pdf", PDF, "application/pdf")},
        ).status_code == 401
        assert manager_client.post(
            upload_url,
            files={"file": ("evidence.pdf", PDF, "application/pdf")},
        ).status_code == 403
        assert wrong_client.get(
            f"/api/manager/transport/submissions/{submission_id}/evidence"
        ).status_code == 403

        traversed = _upload(
            manager_client,
            manager_csrf,
            OperationalDomain.TRANSPORT,
            submission_id,
            filename="../../private-invoice.pdf",
        )
        assert traversed.status_code == 201
        evidence_id = traversed.json()["id"]
        assert traversed.json()["original_filename"] == "private-invoice.pdf"
        assert wrong_client.get(f"/api/manager/energy/evidence/{evidence_id}/content").status_code == 403
        assert wrong_client.get(f"/api/admin/evidence/{evidence_id}/content").status_code == 403
        assert admin_client.get(f"/api/admin/evidence/{evidence_id}/content").status_code == 404
        assert anonymous.get(f"/api/public/evidence/{evidence_id}/content").status_code == 404

        assert _upload(
            manager_client,
            manager_csrf,
            OperationalDomain.TRANSPORT,
            submission_id,
            content=b"MZ executable",
        ).status_code == 422
        assert _upload(
            manager_client,
            manager_csrf,
            OperationalDomain.TRANSPORT,
            submission_id,
            mime_type="text/plain",
        ).status_code == 422
        assert _upload(
            manager_client,
            manager_csrf,
            OperationalDomain.TRANSPORT,
            submission_id,
            content=b"%PDF-" + b"x" * 10_485_760,
            filename="too-large.pdf",
        ).status_code == 413
        assert _upload(
            manager_client,
            manager_csrf,
            OperationalDomain.TRANSPORT,
            submission_id,
            content=PNG,
            filename="meter.png",
            mime_type="image/png",
        ).status_code == 201
        jpeg = _upload(
            manager_client,
            manager_csrf,
            OperationalDomain.TRANSPORT,
            submission_id,
            content=JPEG,
            filename="photo.jpeg",
            mime_type="image/jpeg",
        )
        assert jpeg.status_code == 201
        assert manager_client.delete(
            f"{upload_url}/{jpeg.json()['id']}", headers={"X-CSRF-Token": manager_csrf}
        ).status_code == 200

        assert manager_client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": manager_csrf},
        ).status_code == 200
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/approve",
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 200

    with Session(postgres_engine) as db:
        records = db.scalars(
            select(SubmissionEvidence).where(SubmissionEvidence.submission_id == submission_id)
        ).all()
        assert len(records) == 2
        assert all(record.committed_at is not None for record in records)
        assert all((storage / record.storage_key).is_file() for record in records)
        events = list(
            db.scalars(
                select(AuditLog.event_type).where(
                    AuditLog.target_type == "submission",
                    AuditLog.target_reference == submission_id,
                )
            ).all()
        )
        assert events.count("evidence.committed") == 1
        payload = build_release_payload(db, period)
        serialized = json.dumps(payload, sort_keys=True).casefold()
        for private_key in (
            "evidence",
            "original_filename",
            "storage_key",
            "sha256",
            "uploaded_by_user_id",
        ):
            assert private_key not in serialized
