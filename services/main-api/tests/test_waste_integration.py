"""Waste domain integration tests (isolated PostgreSQL only).

Covers the controlled catalog, backend-authoritative totals, duplicate
protection, optimistic concurrency, current-month security and readiness.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.bootstrap import AccountSpec, create_account
from app.core.config import Settings
from app.main import create_app
from app.models.enums import OperationalDomain, RoleCode
from app.models.sustainability import (
    ReportingPeriod,
    Submission,
    SubmissionValue,
    WasteSubmissionItem,
)
from tests.integration_support import unique_username

PASSWORD = "Waste-Workflow-Test!"

CATEGORY_CODES = {
    "PAPER_CARDBOARD", "PLASTIC", "METAL",
    "ORGANIC_BIOMASS", "E_WASTE", "RUBBER", "OTHER_MIXED",
}
MATERIAL_TO_CATEGORY = {
    "COLOUR_PAPER": "PAPER_CARDBOARD", "WHITE_PAPER": "PAPER_CARDBOARD",
    "CARDBOARD": "PAPER_CARDBOARD", "NEWS_PAPER": "PAPER_CARDBOARD",
    "PP_CARDBOARDS": "PLASTIC", "MIXED_PLASTICS": "PLASTIC", "PVC_PIPE": "PLASTIC",
    "BLACK_PLASTIC_PP": "PLASTIC", "PET": "PLASTIC", "HDPE": "PLASTIC", "LDPE": "PLASTIC",
    "IRON": "METAL", "STAINLESS_STEEL": "METAL", "ALUMINIUM": "METAL",
    "COCONUT_SHELL": "ORGANIC_BIOMASS",
    "E_WASTE": "E_WASTE",
    "TYRE": "RUBBER",
    "LITE_WEIGHT": "OTHER_MIXED", "UNCLASSIFIED": "OTHER_MIXED",
}


def _account(engine: Engine, role: RoleCode, domain: OperationalDomain | None = None) -> str:
    username = unique_username(f"waste-{role.value}-{domain.value if domain else 'all'}")
    with Session(engine) as db:
        create_account(db, AccountSpec(username, "Waste Test", role, domain), PASSWORD, must_change=False)
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
            raise RuntimeError("No free reporting period is available.")
        period = ReportingPeriod(
            year=year, month=month,
            period_start=date(year, month, 1), period_end=date(year, month, 28),
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
        (lambda: datetime(period.year, period.month, 15, tzinfo=UTC)) if period is not None else None
    )
    return TestClient(create_app(settings, engine, clock))


def _login(client: TestClient, username: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return str(response.headers["x-csrf-token"])


def _save(client: TestClient, csrf: str, period_id: str, wet: str, items: list[dict[str, str]],
          row_version: int | None = None) -> dict:
    body: dict[str, object] = {
        "reporting_period_id": period_id,
        "remarks": None,
        "values": [{"metric_code": "wet_waste_generated_kg", "value": wet, "quality_note": None}],
        "waste_items": items,
    }
    if row_version is not None:
        body["expected_row_version"] = row_version
    response = client.post(
        "/api/manager/waste/submissions", json=body, headers={"X-CSRF-Token": csrf}
    )
    return {"status": response.status_code, "body": response.json(), "text": response.text}


def test_waste_catalog_is_complete_and_only_active(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    with _client(postgres_engine) as client:
        _login(client, manager)
        catalog = client.get("/api/manager/waste/catalog")
        assert catalog.status_code == 200, catalog.text
        data = catalog.json()

    assert {item["code"] for item in data["categories"]} == CATEGORY_CODES
    assert len(data["categories"]) == 7
    assert len(data["materials"]) == 19
    # Each material belongs to exactly one category, and to the right one.
    assert {item["code"]: item["category_code"] for item in data["materials"]} == MATERIAL_TO_CATEGORY
    assert len({item["code"] for item in data["materials"]}) == 19
    # Category filtering: every material's category is a real seeded category.
    for material in data["materials"]:
        assert material["category_code"] in CATEGORY_CODES
    plastic = [m["code"] for m in data["materials"] if m["category_code"] == "PLASTIC"]
    assert set(plastic) == {
        "PP_CARDBOARDS", "MIXED_PLASTICS", "PVC_PIPE", "BLACK_PLASTIC_PP", "PET", "HDPE", "LDPE"
    }


def test_waste_manager_cannot_reach_other_domains(postgres_engine: Engine) -> None:
    waste_manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    other_manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WATER)
    with _client(postgres_engine) as client:
        csrf = _login(client, waste_manager)
        assert client.get("/api/manager/water/metrics").status_code == 403
        assert client.post(
            "/api/manager/water/submissions",
            json={"reporting_period_id": str(_period(postgres_engine, 2071).id),
                  "remarks": None, "values": []},
            headers={"X-CSRF-Token": csrf},
        ).status_code == 403
    with _client(postgres_engine) as client:
        _login(client, other_manager)
        # A non-waste manager may not read the waste catalog or waste metrics.
        assert client.get("/api/manager/waste/catalog").status_code == 403
        assert client.get("/api/manager/waste/metrics").status_code == 403


def test_waste_totals_are_backend_authoritative_and_exact(postgres_engine: Engine) -> None:
    """Deterministic case: 300 wet + (100.25 + 50.50 + 25.25) dry = 476.00 kg."""
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    period = _period(postgres_engine, 2072)
    items = [
        {"material_code": "COLOUR_PAPER", "quantity_kg": "100.25"},
        {"material_code": "PET", "quantity_kg": "50.50"},
        {"material_code": "IRON", "quantity_kg": "25.25"},
    ]
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        saved = _save(client, csrf, str(period.id), "300", items)
        assert saved["status"] == 201, saved["text"]
        body = saved["body"]
        waste = body["waste"]
        assert Decimal(waste["dry_waste_generated_kg"]) == Decimal("176.000000")
        assert Decimal(waste["wet_waste_generated_kg"]) == Decimal("300.000000")
        assert Decimal(waste["total_waste_generated_kg"]) == Decimal("476.000000")
        # Diverted from landfill is calculated (= dry waste), never entered.
        assert Decimal(waste["waste_diverted_from_landfill_kg"]) == Decimal("176.000000")
        assert waste["waste_per_capita_kg"] is None  # no population reference for this test year
        # Backend category totals, grouped from the material rows.
        by_category = {c["code"]: Decimal(c["quantity_kg"]) for c in waste["categories"]}
        assert by_category == {
            "PAPER_CARDBOARD": Decimal("100.25"),
            "PLASTIC": Decimal("50.50"),
            "METAL": Decimal("25.25"),
        }
        # Derived metrics are stored as submission values, not just computed.
        values = {item["metric_code"]: item["value"] for item in body["values"]}
        assert Decimal(values["dry_waste_generated_kg"]) == Decimal("176.000000")
        assert Decimal(values["total_waste_generated_kg"]) == Decimal("476.000000")
        submission_id = body["id"]

    with Session(postgres_engine) as db:
        stored = {
            row.metric_code: row.value
            for row in db.scalars(
                select(SubmissionValue).where(SubmissionValue.submission_id == submission_id)
            ).all()
        }
        assert stored["dry_waste_generated_kg"] == Decimal("176.000000")
        assert stored["total_waste_generated_kg"] == Decimal("476.000000")
        rows = db.scalars(
            select(WasteSubmissionItem).where(WasteSubmissionItem.submission_id == submission_id)
        ).all()
        assert len(rows) == 3
        assert sum((row.quantity_kg for row in rows), Decimal("0")) == Decimal("176.000000")


def test_manager_cannot_write_derived_waste_metrics(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    period = _period(postgres_engine, 2073)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        for derived in ("dry_waste_generated_kg", "total_waste_generated_kg"):
            response = client.post(
                "/api/manager/waste/submissions",
                json={
                    "reporting_period_id": str(period.id), "remarks": None,
                    "values": [
                        {"metric_code": "wet_waste_generated_kg", "value": "10", "quality_note": None},
                        {"metric_code": derived, "value": "99999", "quality_note": None},
                    ],
                    "waste_items": [],
                },
                headers={"X-CSRF-Token": csrf},
            )
            assert response.status_code == 422, response.text
            assert "calculated and cannot be written" in response.text


def test_empty_dry_inventory_is_zero_not_a_fake_row(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    period = _period(postgres_engine, 2074)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        saved = _save(client, csrf, str(period.id), "120.5", [])
        assert saved["status"] == 201, saved["text"]
        waste = saved["body"]["waste"]
        assert Decimal(waste["dry_waste_generated_kg"]) == Decimal("0")
        assert Decimal(waste["total_waste_generated_kg"]) == Decimal("120.500000")
        assert waste["items"] == []
        # An empty inventory still submits: no fake material row is required.
        submit = client.post(
            f"/api/manager/waste/submissions/{saved['body']['id']}/submit",
            headers={"X-CSRF-Token": csrf},
        )
        assert submit.status_code == 200, submit.text


def test_duplicate_material_is_rejected(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    period = _period(postgres_engine, 2075)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        duplicate = _save(client, csrf, str(period.id), "10", [
            {"material_code": "PET", "quantity_kg": "50"},
            {"material_code": "PET", "quantity_kg": "20"},
        ])
        # Rejected by request validation before it can reach the database.
        assert duplicate["status"] == 422, duplicate["text"]

    # The database constraint protects against a race or a service-layer bug.
    with Session(postgres_engine) as db:
        existing = db.scalar(
            select(Submission).where(
                Submission.domain == OperationalDomain.WASTE,
                Submission.reporting_period_id == period.id,
            )
        )
        if existing is not None:
            db.add(WasteSubmissionItem(
                submission_id=existing.id, material_code="PET", quantity_kg=Decimal("50")
            ))
            db.commit()
            db.add(WasteSubmissionItem(
                submission_id=existing.id, material_code="PET", quantity_kg=Decimal("20")
            ))
            try:
                db.commit()
                raise AssertionError("uq_waste_item_submission_material did not prevent a duplicate")
            except Exception as exc:  # noqa: BLE001 - asserting the constraint fires
                assert "uq_waste_item_submission_material" in str(exc)
                db.rollback()


def test_invalid_and_non_positive_quantities_are_rejected(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    period = _period(postgres_engine, 2076)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        for quantity in ("-5", "0", "NaN", "Infinity", "abc"):
            response = _save(client, csrf, str(period.id), "10",
                             [{"material_code": "PET", "quantity_kg": quantity}])
            assert response["status"] == 422, f"{quantity}: {response['text']}"
        unknown = _save(client, csrf, str(period.id), "10",
                        [{"material_code": "NOT_A_MATERIAL", "quantity_kg": "5"}])
        assert unknown["status"] == 422
        assert "not a valid active material" in unknown["text"]


def test_stale_waste_edit_returns_409_and_does_not_mutate_items(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    period = _period(postgres_engine, 2077)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        first = _save(client, csrf, str(period.id), "10",
                      [{"material_code": "PET", "quantity_kg": "50"}])
        assert first["status"] == 201, first["text"]
        submission_id = first["body"]["id"]
        stale_version = first["body"]["row_version"]

        second = client.put(
            f"/api/manager/waste/submissions/{submission_id}",
            json={
                "reporting_period_id": None, "remarks": None,
                "values": [{"metric_code": "wet_waste_generated_kg", "value": "20",
                            "quality_note": None}],
                "waste_items": [{"material_code": "IRON", "quantity_kg": "11"}],
                "expected_row_version": stale_version,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert second.status_code == 200, second.text

        third = client.put(
            f"/api/manager/waste/submissions/{submission_id}",
            json={
                "reporting_period_id": None, "remarks": None,
                "values": [{"metric_code": "wet_waste_generated_kg", "value": "999",
                            "quality_note": None}],
                "waste_items": [{"material_code": "HDPE", "quantity_kg": "77"}],
                "expected_row_version": stale_version,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert third.status_code == 409, third.text
        assert third.json()["error"]["code"] == "stale_submission"

    # The rejected save left nothing behind: still the second save's state.
    with Session(postgres_engine) as db:
        rows = db.scalars(
            select(WasteSubmissionItem).where(WasteSubmissionItem.submission_id == submission_id)
        ).all()
        assert {row.material_code for row in rows} == {"IRON"}
        wet = db.scalar(
            select(SubmissionValue.value).where(
                SubmissionValue.submission_id == submission_id,
                SubmissionValue.metric_code == "wet_waste_generated_kg",
            )
        )
        assert wet == Decimal("20.000000")


def test_waste_current_month_security_matches_other_domains(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    period = _period(postgres_engine, 2078)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        saved = _save(client, csrf, str(period.id), "10",
                      [{"material_code": "PET", "quantity_kg": "5"}])
        submission_id = saved["body"]["id"]
        assert client.post(
            f"/api/manager/waste/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        # Submitted is locked.
        locked = client.put(
            f"/api/manager/waste/submissions/{submission_id}",
            json={"reporting_period_id": None, "remarks": None,
                  "values": [{"metric_code": "wet_waste_generated_kg", "value": "11",
                              "quality_note": None}],
                  "waste_items": [], "expected_row_version": saved["body"]["row_version"] + 1},
            headers={"X-CSRF-Token": csrf},
        )
        assert locked.status_code == 409

    # Approved is locked too.
    with _client(postgres_engine, period) as admin_client:
        admin_csrf = _login(admin_client, admin)
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/begin-review",
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 200
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/approve",
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 200

    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        approved_edit = client.put(
            f"/api/manager/waste/submissions/{submission_id}",
            json={"reporting_period_id": None, "remarks": None,
                  "values": [{"metric_code": "wet_waste_generated_kg", "value": "12",
                              "quality_note": None}],
                  "waste_items": [], "expected_row_version": 99},
            headers={"X-CSRF-Token": csrf},
        )
        assert approved_edit.status_code == 409


def test_waste_correction_cycle_increments_revision(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    period = _period(postgres_engine, 2079)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        saved = _save(client, csrf, str(period.id), "10",
                      [{"material_code": "PET", "quantity_kg": "5"}])
        submission_id = saved["body"]["id"]
        assert client.post(
            f"/api/manager/waste/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200

    with _client(postgres_engine, period) as admin_client:
        admin_csrf = _login(admin_client, admin)
        admin_client.post(f"/api/admin/submissions/{submission_id}/begin-review",
                          headers={"X-CSRF-Token": admin_csrf})
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/request-correction",
            json={"reason": "Please confirm the PET weighing record."},
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 200

    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        detail = client.get(f"/api/manager/waste/submissions/{submission_id}").json()
        assert detail["status"] == "correction_requested"
        assert detail["revision_number"] == 1
        corrected = client.put(
            f"/api/manager/waste/submissions/{submission_id}",
            json={"reporting_period_id": None, "remarks": "Corrected.",
                  "values": [{"metric_code": "wet_waste_generated_kg", "value": "15",
                              "quality_note": None}],
                  "waste_items": [{"material_code": "PET", "quantity_kg": "8"}],
                  "expected_row_version": detail["row_version"]},
            headers={"X-CSRF-Token": csrf},
        )
        assert corrected.status_code == 200, corrected.text
        assert client.post(
            f"/api/manager/waste/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        resubmitted = client.get(f"/api/manager/waste/submissions/{submission_id}").json()
        assert resubmitted["revision_number"] == 2
        assert Decimal(resubmitted["waste"]["dry_waste_generated_kg"]) == Decimal("8.000000")
        assert Decimal(resubmitted["waste"]["total_waste_generated_kg"]) == Decimal("23.000000")


def test_waste_evidence_lifecycle_matches_other_domains(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    period = _period(postgres_engine, 2081)
    pdf = b"%PDF-1.4\n% waste register\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        saved = _save(client, csrf, str(period.id), "50",
                      [{"material_code": "CARDBOARD", "quantity_kg": "12"}])
        submission_id = saved["body"]["id"]

        upload = client.post(
            f"/api/manager/waste/submissions/{submission_id}/evidence",
            files={"file": ("waste-register.pdf", pdf, "application/pdf")},
            data={"evidence_category": "waste_register"},
            headers={"X-CSRF-Token": csrf},
        )
        assert upload.status_code == 201, upload.text
        first_id = upload.json()["id"]

        listed = client.get(f"/api/manager/waste/submissions/{submission_id}/evidence")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [first_id]
        # Temporary: not yet committed.
        assert listed.json()[0]["committed_at"] is None

        # A temporary mistake can be removed, then replaced.
        removed = client.delete(
            f"/api/manager/waste/submissions/{submission_id}/evidence/{first_id}",
            headers={"X-CSRF-Token": csrf},
        )
        assert removed.status_code == 200, removed.text
        assert client.get(
            f"/api/manager/waste/submissions/{submission_id}/evidence"
        ).json() == []

        replacement = client.post(
            f"/api/manager/waste/submissions/{submission_id}/evidence",
            files={"file": ("weighing-record.png", png, "image/png")},
            data={"evidence_category": "weighing_record"},
            headers={"X-CSRF-Token": csrf},
        )
        assert replacement.status_code == 201, replacement.text
        replacement_id = replacement.json()["id"]

        # Established MIME/magic validation is unchanged for waste.
        bad = client.post(
            f"/api/manager/waste/submissions/{submission_id}/evidence",
            files={"file": ("notes.txt", b"plain text", "text/plain")},
            headers={"X-CSRF-Token": csrf},
        )
        assert bad.status_code in {415, 422}, bad.text
        disguised = client.post(
            f"/api/manager/waste/submissions/{submission_id}/evidence",
            files={"file": ("fake.pdf", b"not really a pdf", "application/pdf")},
            headers={"X-CSRF-Token": csrf},
        )
        assert disguised.status_code in {415, 422}, disguised.text

        assert client.post(
            f"/api/manager/waste/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200

        # Committed on submit, and immutable afterwards.
        after = client.get(f"/api/manager/waste/submissions/{submission_id}/evidence").json()
        assert [item["id"] for item in after] == [replacement_id]
        assert after[0]["committed_at"] is not None
        blocked = client.delete(
            f"/api/manager/waste/submissions/{submission_id}/evidence/{replacement_id}",
            headers={"X-CSRF-Token": csrf},
        )
        assert blocked.status_code == 409, blocked.text

    with _client(postgres_engine, period) as admin_client:
        _login(admin_client, admin)
        # Admin can see waste evidence and download it.
        admin_list = admin_client.get("/api/admin/evidence?domain=waste")
        assert admin_list.status_code == 200, admin_list.text
        repository = admin_list.json()["items"]
        assert any(item["evidence_id"] == replacement_id for item in repository), admin_list.text
        assert all(item["domain"] == "waste" for item in repository)
        content = admin_client.get(f"/api/admin/evidence/{replacement_id}/content")
        assert content.status_code == 200
        assert content.content == png


def test_waste_items_are_frozen_once_approved(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WASTE)
    admin = _account(postgres_engine, RoleCode.ADMIN)
    period = _period(postgres_engine, 2082)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        saved = _save(client, csrf, str(period.id), "10",
                      [{"material_code": "PET", "quantity_kg": "5"}])
        submission_id = saved["body"]["id"]
        client.post(f"/api/manager/waste/submissions/{submission_id}/submit",
                    headers={"X-CSRF-Token": csrf})
    with _client(postgres_engine, period) as admin_client:
        admin_csrf = _login(admin_client, admin)
        admin_client.post(f"/api/admin/submissions/{submission_id}/begin-review",
                          headers={"X-CSRF-Token": admin_csrf})
        admin_client.post(f"/api/admin/submissions/{submission_id}/approve",
                          headers={"X-CSRF-Token": admin_csrf})

    # guard_frozen_submission protects the derived totals, so an item written
    # around the API cannot silently change an approved submission.
    with Session(postgres_engine) as db:
        db.add(WasteSubmissionItem(
            submission_id=submission_id, material_code="IRON", quantity_kg=Decimal("99")
        ))
        try:
            db.commit()
            raise AssertionError("approved waste submission accepted a new item")
        except Exception as exc:  # noqa: BLE001 - asserting the guard fires
            assert "immutable" in str(exc)
            db.rollback()


def test_readiness_requires_all_six_domains(postgres_engine: Engine) -> None:
    admin = _account(postgres_engine, RoleCode.ADMIN)
    period = _period(postgres_engine, 2080)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, admin)
        readiness = client.get(
            f"/api/admin/reporting-periods/{period.id}/publication-readiness"
        ).json()
        assert readiness["required_domains"] == 6
        assert readiness["approved_domains"] == 0
        assert readiness["ready_to_publish"] is False
        assert "waste" in readiness["domains"]
        assert any(item["domain"] == "waste" for item in readiness["blockers"])
        # Prepare must refuse while any required domain is unapproved.
        prepare = client.post(
            "/api/admin/releases/prepare",
            json={"reporting_period_id": str(period.id), "version": f"waste-readiness-{period.id}"},
            headers={"X-CSRF-Token": csrf},
        )
        assert prepare.status_code == 409
        assert prepare.json()["error"]["code"] == "publication_not_ready"
