"""Public certificate registry (migration 0017).

Certificates are supporting public documents: Admin-managed, publicly
read-only once PUBLISHED, and never an input to any sustainability metric.
Every test uses its own throwaway domain and unique file bytes, so the
registry's global duplicate protection never couples two tests.
"""

from __future__ import annotations

import hashlib
import inspect as python_inspect
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.historical import calculator, resolver
from app.historical.resolver import build_timeline
from app.main import create_app
from app.models.audit import AuditLog
from app.models.enums import OperationalDomain, RoleCode
from app.models.publication import Certificate
from app.services import publication, sustainability_formulas
from app.storage.certificates import STORAGE_KEY_PATTERN, certificate_path
from tests.test_outreach_integration import _account, _login

COUNTS_SQL = (
    "select (select count(*) from history.metric_values),"
    " (select count(*) from history.calculation_results),"
    " (select count(*) from sustainability.submission_values),"
    " (select count(*) from publication.public_releases)"
)


def _jpeg() -> bytes:
    return b"\xff\xd8\xff\xe0" + f"certificate-{uuid4().hex}".encode() + b"\xff\xd9"


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + f"certificate-{uuid4().hex}".encode()


def _pdf() -> bytes:
    return b"%PDF-1.4\n% " + uuid4().hex.encode() + b"\n%%EOF\n"


def _domain() -> str:
    return f"t{uuid4().hex[:12]}"


def _client(engine: Engine, storage: Path, **overrides: Any) -> TestClient:
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=str(engine.url),
        EVIDENCE_ROOT=storage.parent / "evidence-root",
        CERTIFICATE_STORAGE_ROOT=storage,
        **overrides,
    )
    return TestClient(create_app(settings, engine))


def _fields(domain: str, year: int = 2025, **overrides: Any) -> dict[str, str]:
    fields = {
        "domain": domain,
        "certificate_type": "E-Waste Disposal Certificate",
        "reporting_year": str(year),
        "title": "E-Waste Disposal Certificate - test",
        "issuer": "Test Recyclers",
        "registration_id": "REG-1",
        "authorization_no": "AUTH-1",
        "serial_no": "S-1",
        "certificate_date": "2026-01-23",
        "received_date": "2025-11-28",
        "invoice_no": "INV/1",
        "manifest_doc_no": "MAN/1",
        "quantity_value": "1640",
        "quantity_unit": "kg",
        "display_order": "0",
        "notes": "internal note",
    }
    fields.update({key: str(value) for key, value in overrides.items()})
    return fields


def _upload(
    client: TestClient,
    csrf: str | None,
    domain: str,
    *,
    content: bytes | None = None,
    filename: str = "certificate.jpeg",
    mime_type: str = "image/jpeg",
    year: int = 2025,
    **overrides: Any,
) -> Response:
    return client.post(
        "/api/admin/certificates",
        data=_fields(domain, year, **overrides),
        files={"file": (filename, _jpeg() if content is None else content, mime_type)},
        headers={"X-CSRF-Token": csrf} if csrf else {},
    )


def _admin(engine: Engine, client: TestClient) -> str:
    return _login(client, _account(engine, RoleCode.ADMIN))


def _post(client: TestClient, csrf: str, certificate_id: str, action: str) -> Response:
    return client.post(f"/api/admin/certificates/{certificate_id}/{action}", headers={"X-CSRF-Token": csrf})


# ---- Schema ---------------------------------------------------------------------


def test_certificate_table_exists_with_its_constraints(postgres_engine: Engine) -> None:
    inspector = inspect(postgres_engine)
    assert "certificates" in inspector.get_table_names(schema="publication")
    columns = {column["name"]: column for column in inspector.get_columns("certificates", schema="publication")}
    assert {
        "id",
        "domain",
        "certificate_type",
        "reporting_year",
        "title",
        "issuer",
        "registration_id",
        "authorization_no",
        "serial_no",
        "certificate_date",
        "received_date",
        "invoice_no",
        "manifest_doc_no",
        "quantity_value",
        "quantity_unit",
        "original_filename",
        "storage_key",
        "mime_type",
        "byte_size",
        "sha256",
        "status",
        "display_order",
        "notes",
        "created_by",
        "created_at",
        "updated_at",
        "published_at",
        "archived_at",
    } == set(columns)
    assert "bytea" not in {str(column["type"]).lower() for column in columns.values()}  # no file bytes in the database
    uniques = {
        tuple(item["column_names"]) for item in inspector.get_unique_constraints("certificates", schema="publication")
    }
    assert {("storage_key",), ("sha256",)} <= uniques

    def insert(**overrides: Any) -> None:
        values = {
            "domain": _domain(),
            "certificate_type": "T",
            "reporting_year": 2025,
            "title": "t",
            "original_filename": "a.jpg",
            "storage_key": f"{uuid4().hex}.jpg",
            "mime_type": "image/jpeg",
            "byte_size": 10,
            "sha256": hashlib.sha256(uuid4().bytes).hexdigest(),
            "status": "DRAFT",
            **overrides,
        }
        with Session(postgres_engine) as db:
            db.add(Certificate(**values))
            try:
                db.commit()
            finally:
                db.rollback()

    for bad in (
        {"status": "DELETED"},
        {"domain": "Waste Dept"},
        {"reporting_year": 1999},
        {"title": "   "},
        {"quantity_value": -1},
        {"byte_size": 0},
        {"sha256": "x" * 64},
        {"mime_type": "text/html"},
        {"status": "PUBLISHED"},  # published without a published_at timestamp
    ):
        try:
            insert(**bad)
        except IntegrityError:
            continue
        raise AssertionError(f"constraint did not reject {bad}")


# ---- Admin API: access ----------------------------------------------------------


def test_certificate_management_requires_an_admin_session_and_csrf(postgres_engine: Engine, tmp_path: Path) -> None:
    domain = _domain()
    with _client(postgres_engine, tmp_path / "c") as anonymous:
        assert anonymous.get("/api/admin/certificates").status_code == 401
        assert _upload(anonymous, None, domain).status_code == 401
    with _client(postgres_engine, tmp_path / "c") as manager_client:
        csrf = _login(manager_client, _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE))
        assert manager_client.get("/api/admin/certificates").status_code == 403
        assert _upload(manager_client, csrf, domain).status_code == 403  # a Manager cannot upload
    with _client(postgres_engine, tmp_path / "c") as admin_client:
        csrf = _admin(postgres_engine, admin_client)
        assert _upload(admin_client, None, domain).status_code == 403  # no CSRF token
        created = _upload(admin_client, csrf, domain)
        assert created.status_code == 201, created.text
        certificate_id = created.json()["id"]
        for action in ("publish", "archive"):
            assert admin_client.post(f"/api/admin/certificates/{certificate_id}/{action}").status_code == 403
        assert admin_client.patch(f"/api/admin/certificates/{certificate_id}", json={"title": "x"}).status_code == 403
        # There is no delete: a published document is archived, never removed.
        assert (
            admin_client.delete(f"/api/admin/certificates/{certificate_id}", headers={"X-CSRF-Token": csrf}).status_code
            == 405
        )
    with _client(postgres_engine, tmp_path / "c") as manager_client:
        _login(manager_client, _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE))
        assert manager_client.get(f"/api/admin/certificates/{certificate_id}/file").status_code == 403


# ---- Admin API: upload validation ------------------------------------------------


def test_upload_accepts_jpeg_png_and_pdf_and_stores_hash_and_safe_key(postgres_engine: Engine, tmp_path: Path) -> None:
    storage, domain = tmp_path / "c", _domain()
    with _client(postgres_engine, storage) as client:
        csrf = _admin(postgres_engine, client)
        for content, filename, mime in (
            (_jpeg(), "../../evil name.JPEG", "image/jpeg"),
            (_png(), "scan.png", "image/png"),
            (_pdf(), "C:\\Users\\x\\cert.pdf", "application/pdf"),
        ):
            response = _upload(client, csrf, domain, content=content, filename=filename, mime_type=mime)
            assert response.status_code == 201, response.text
            body = response.json()
            assert body["status"] == "DRAFT" and body["published_at"] is None
            assert body["sha256"] == hashlib.sha256(content).hexdigest()
            assert body["byte_size"] == len(content) and body["mime_type"] == mime
            assert "/" not in body["original_filename"] and "\\" not in body["original_filename"]
            assert "storage_key" not in body and "created_by" not in body
            with Session(postgres_engine) as db:
                row = db.get(Certificate, body["id"])
                assert row is not None and STORAGE_KEY_PATTERN.fullmatch(row.storage_key)
                assert row.storage_key != row.original_filename
                stored = storage / row.storage_key
                assert stored.is_file() and stored.read_bytes() == content
                assert stored.resolve().parent == storage.resolve()
            preview = client.get(f"/api/admin/certificates/{body['id']}/file")
            assert preview.status_code == 200 and preview.content == content
            assert preview.headers["content-type"].startswith(mime)
            assert "no-store" in preview.headers["cache-control"]
        assert sorted(path.suffix for path in storage.iterdir()) == [".jpg", ".pdf", ".png"]  # nothing else was written


def test_upload_rejects_wrong_types_bad_signatures_oversize_and_bad_metadata(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    storage, domain = tmp_path / "c", _domain()
    with _client(postgres_engine, storage, MAX_UPLOAD_BYTES=2048) as client:
        csrf = _admin(postgres_engine, client)
        assert (
            _upload(
                client, csrf, domain, content=b"<html></html>", filename="a.html", mime_type="text/html"
            ).status_code
            == 422
        )
        assert (
            _upload(client, csrf, domain, content=b"GIF89a....", filename="a.gif", mime_type="image/gif").status_code
            == 422
        )
        # The browser-declared type is not trusted: the content must really be that type.
        assert (
            _upload(client, csrf, domain, content=_pdf(), filename="a.jpg", mime_type="image/jpeg").status_code == 422
        )
        assert (
            _upload(
                client, csrf, domain, content=b"MZ-executable", filename="a.pdf", mime_type="application/pdf"
            ).status_code
            == 422
        )
        assert (
            _upload(client, csrf, domain, content=_jpeg(), filename="a.pdf", mime_type="image/jpeg").status_code == 422
        )
        assert _upload(client, csrf, domain, content=b"", filename="a.jpg").status_code == 422
        assert (
            _upload(client, csrf, domain, content=b"\xff\xd8\xff" + b"x" * 4096, filename="big.jpg").status_code == 413
        )
        assert _upload(client, csrf, "Not A Domain").status_code == 422
        for bad in (
            {"reporting_year": 1890},
            {"title": "   "},
            {"quantity_value": "-5"},
            {"certificate_date": "23-01-2026"},
        ):
            assert _upload(client, csrf, domain, **bad).status_code == 422, bad
        assert client.get(f"/api/admin/certificates?domain={domain}").json() == []
        assert not storage.exists() or list(storage.iterdir()) == []  # no rejected upload leaves a file behind


def test_the_same_document_cannot_be_registered_twice(postgres_engine: Engine, tmp_path: Path) -> None:
    domain, content = _domain(), _jpeg()
    with _client(postgres_engine, tmp_path / "c") as client:
        csrf = _admin(postgres_engine, client)
        first = _upload(client, csrf, domain, content=content)
        assert first.status_code == 201
        again = _upload(client, csrf, domain, content=content, filename="renamed.jpg", title="Another title", year=2026)
        assert again.status_code == 409
        error = again.json()["error"]
        assert error["code"] == "duplicate_certificate" and error["certificate_id"] == first.json()["id"]
        # Still a duplicate after archiving: the archived record is the one to republish.
        _post(client, csrf, first.json()["id"], "archive")
        assert _upload(client, csrf, domain, content=content).status_code == 409
        assert len(client.get(f"/api/admin/certificates?domain={domain}").json()) == 1
        assert len(list((tmp_path / "c").iterdir())) == 1  # the duplicate's file was not kept


# ---- Lifecycle and public visibility ---------------------------------------------


def test_only_published_certificates_are_public_and_years_follow_the_data(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    domain = _domain()
    years = f"/api/public/certificates/years?domain={domain}"
    with _client(postgres_engine, tmp_path / "c") as client, _client(postgres_engine, tmp_path / "c") as public:
        csrf = _admin(postgres_engine, client)
        content = _jpeg()
        first = _upload(client, csrf, domain, content=content, title="First", received_date="2025-11-28").json()
        second = _upload(
            client, csrf, domain, title="Second", received_date="2025-11-29", display_order=1, quantity_value="1390"
        ).json()

        # DRAFT: the Admin sees it, the public does not.
        assert {item["status"] for item in client.get(f"/api/admin/certificates?domain={domain}").json()} == {"DRAFT"}
        assert public.get(years).json() == {"domain": domain, "years": []}
        assert public.get(f"/api/public/certificates?domain={domain}&year=2025").json()["certificates"] == []
        assert public.get(f"/api/public/certificates/{first['id']}/file").status_code == 404

        published = _post(client, csrf, first["id"], "publish")
        assert published.status_code == 200 and published.json()["status"] == "PUBLISHED"
        assert published.json()["published_at"] is not None
        assert public.get(years).json()["years"] == [
            {"year": 2025, "certificate_count": 1, "certificate_types": ["E-Waste Disposal Certificate"]}
        ]
        _post(client, csrf, second["id"], "publish")
        listing = public.get(f"/api/public/certificates?domain={domain}&year=2025").json()
        assert (listing["domain"], listing["reporting_year"]) == (domain, 2025)
        assert [item["title"] for item in listing["certificates"]] == ["First", "Second"]  # display order
        shown = listing["certificates"][0]
        assert shown == {
            "id": first["id"],
            "title": "First",
            "certificate_type": "E-Waste Disposal Certificate",
            "reporting_year": 2025,
            "issuer": "Test Recyclers",
            "registration_id": "REG-1",
            "authorization_no": "AUTH-1",
            "serial_no": "S-1",
            "received_date": "2025-11-28",
            "certificate_date": "2026-01-23",
            "invoice_no": "INV/1",
            "manifest_doc_no": "MAN/1",
            "quantity_value": 1640,
            "quantity_unit": "kg",
            "mime_type": "image/jpeg",
        }
        # Nothing internal is exposed: no storage key, path, hash, uploader, notes or filename.
        assert not {"storage_key", "created_by", "sha256", "notes", "original_filename", "byte_size", "status"} & set(
            shown
        )
        assert "certificate-storage" not in str(listing) and str(tmp_path) not in str(listing)

        # The reporting year is the stored one - not the year of the certificate date (2026).
        assert public.get(f"/api/public/certificates?domain={domain}&year=2026").json()["certificates"] == []

        served = public.get(f"/api/public/certificates/{first['id']}/file")
        assert served.status_code == 200 and served.content == content
        assert served.headers["content-type"].startswith("image/jpeg")
        assert served.headers["x-content-type-options"] == "nosniff"
        assert served.headers["content-disposition"].startswith("inline")
        assert "set-cookie" not in served.headers
        download = public.get(f"/api/public/certificates/{first['id']}/file?download=1")
        assert download.headers["content-disposition"].startswith("attachment")

        # A later year appears by itself once a certificate for it is published...
        future = _upload(client, csrf, domain, year=2026, title="Future").json()
        assert [item["year"] for item in public.get(years).json()["years"]] == [2025]
        _post(client, csrf, future["id"], "publish")
        assert [(item["year"], item["certificate_count"]) for item in public.get(years).json()["years"]] == [
            (2026, 1),
            (2025, 2),
        ]
        # ...and disappears again when its only certificate is archived.
        archived = _post(client, csrf, future["id"], "archive")
        assert archived.json()["status"] == "ARCHIVED" and archived.json()["archived_at"] is not None
        assert [item["year"] for item in public.get(years).json()["years"]] == [2025]
        assert public.get(f"/api/public/certificates/{future['id']}/file").status_code == 404
        assert client.get(f"/api/admin/certificates/{future['id']}/file").status_code == 200  # Admin still can

        # Archiving one published certificate leaves the other readable.
        _post(client, csrf, second["id"], "archive")
        assert [
            item["id"]
            for item in public.get(f"/api/public/certificates?domain={domain}&year=2025").json()["certificates"]
        ] == [first["id"]]
        assert public.get(f"/api/public/certificates/{first['id']}/file").status_code == 200
        # An archived record can be published again; no second upload is needed.
        assert _post(client, csrf, second["id"], "publish").json()["status"] == "PUBLISHED"
        assert public.get(years).json()["years"][0]["certificate_count"] == 2
        # Another domain never sees these documents.
        assert public.get(f"/api/public/certificates/years?domain={_domain()}").json()["years"] == []
        # Admin filters.
        assert len(client.get(f"/api/admin/certificates?domain={domain}&status=ARCHIVED").json()) == 1
        assert len(client.get(f"/api/admin/certificates?domain={domain}&year=2025&status=PUBLISHED").json()) == 2


def test_metadata_edit_and_audit_trail(postgres_engine: Engine, tmp_path: Path) -> None:
    domain = _domain()
    with _client(postgres_engine, tmp_path / "c") as client:
        csrf = _admin(postgres_engine, client)
        created = _upload(client, csrf, domain).json()
        edited = client.patch(
            f"/api/admin/certificates/{created['id']}",
            json={"title": "  Corrected title ", "serial_no": "S-2", "reporting_year": 2024, "issuer": ""},
            headers={"X-CSRF-Token": csrf},
        )
        assert edited.status_code == 200, edited.text
        body = edited.json()
        assert (body["title"], body["serial_no"], body["reporting_year"], body["issuer"]) == (
            "Corrected title",
            "S-2",
            2024,
            None,
        )
        assert body["sha256"] == created["sha256"] and body["status"] == "DRAFT"  # the file is never replaced
        for bad in (
            {"title": None},
            {"reporting_year": 1500},
            {"sha256": "0" * 64},
            {"status": "PUBLISHED"},
            {"storage_key": "x.jpg"},
        ):
            assert (
                client.patch(
                    f"/api/admin/certificates/{created['id']}", json=bad, headers={"X-CSRF-Token": csrf}
                ).status_code
                == 422
            ), bad
        _post(client, csrf, created["id"], "publish")
        _post(client, csrf, created["id"], "archive")
        assert _post(client, csrf, str(uuid4()), "publish").status_code == 404
    with Session(postgres_engine) as db:
        events = db.scalars(
            select(AuditLog)
            .where(AuditLog.target_type == "certificate", AuditLog.target_reference == created["id"])
            .order_by(AuditLog.created_at, AuditLog.id)
        ).all()
        assert [event.event_type for event in events] == [
            "certificate.created",
            "certificate.updated",
            "certificate.published",
            "certificate.archived",
        ]
        assert all(event.actor_user_id is not None and event.outcome == "succeeded" for event in events)
        assert events[1].safe_metadata["fields"] == ["issuer", "reporting_year", "serial_no", "title"]
        # The audit log names the document and the change, never file contents or a path.
        for event in events:
            assert "storage_key" not in event.safe_metadata and str(tmp_path) not in str(event.safe_metadata)


# ---- File serving safety ---------------------------------------------------------


def test_public_file_route_cannot_reach_outside_the_certificate_store(postgres_engine: Engine, tmp_path: Path) -> None:
    storage = tmp_path / "c"
    secret = tmp_path / "secret.txt"
    secret.write_text("not a certificate", encoding="utf-8")
    settings = Settings(APP_ENV="test", DATABASE_URL=str(postgres_engine.url), CERTIFICATE_STORAGE_ROOT=storage)
    for key in ("../secret.txt", "..\\secret.txt", str(secret), "/etc/passwd", "a/b.jpg", "x.exe", ""):
        try:
            certificate_path(settings, key)
        except Exception as error:  # noqa: BLE001
            assert getattr(error, "status_code", None) == 500
            continue
        raise AssertionError(f"storage key {key!r} was accepted")
    with _client(postgres_engine, storage) as public:
        for attempt in ("../secret.txt", "..%2Fsecret.txt", "%2e%2e%2fsecret.txt", "secret.txt", "etc/passwd"):
            response = public.get(f"/api/public/certificates/{attempt}/file")
            assert response.status_code in (404, 422), attempt
            assert b"not a certificate" not in response.content
        assert public.get(f"/api/public/certificates/{uuid4()}/file").status_code == 404
        # The storage directory itself is not browsable.
        assert public.get("/api/public/certificates/").status_code in (404, 405, 422)
        assert public.get("/api/public/certificates?domain=waste").status_code == 422  # a year is required
        # The public routes are read-only.
        assert public.post("/api/public/certificates?domain=waste&year=2025").status_code == 405


# ---- Governance: certificates never touch sustainability metrics ------------------


def test_certificates_never_change_a_sustainability_value(postgres_engine: Engine, tmp_path: Path) -> None:
    with Session(postgres_engine) as db:
        before = build_timeline(db)
        counts_before = db.execute(text(COUNTS_SQL)).one()
    with _client(postgres_engine, tmp_path / "c") as client:
        csrf = _admin(postgres_engine, client)
        created = _upload(client, csrf, "waste", quantity_value="987654.321").json()
        _post(client, csrf, created["id"], "publish")
        public_dashboard = client.get("/api/public/dashboard/timeline").json()
        _post(client, csrf, created["id"], "archive")  # leave no published test document under the real domain
    with Session(postgres_engine) as db:
        assert build_timeline(db) == before
        assert db.execute(text(COUNTS_SQL)).one() == counts_before
    assert "987654" not in str(public_dashboard) and "certificate" not in str(public_dashboard).lower()
    # No calculation, resolver, formula or release code reads the certificate registry.
    for module in (calculator, resolver, publication, sustainability_formulas):
        assert "certificate" not in python_inspect.getsource(module).lower(), module.__name__
