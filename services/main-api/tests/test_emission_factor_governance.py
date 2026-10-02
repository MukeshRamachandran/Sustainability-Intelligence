from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models.enums import FactorCode, FactorSetStatus, OperationalDomain, RoleCode
from app.models.sustainability import CalculationResult, EmissionFactorSet, ReportingPeriod
from app.schemas.emission_factors import FactorWrite
from app.services.emission_factors import applicable_factor_set
from tests.test_generic_submission_integration import _account, _client, _login, _period, _values


def _factor_payload(
    version: str, effective_from: str, grid: str = "0.727", lpg: str | None = None
) -> dict[str, object]:
    factors: list[dict[str, object]] = [
        {
            "code": "PETROL",
            "factor_value": "2.388",
            "activity_unit": "L",
            "result_unit": "kgCO2e",
            "source_reference": "Test petrol source",
            "source_url": "https://example.test/petrol",
            "notes": None,
        },
        {
            "code": "DIESEL",
            "factor_value": "2.701",
            "activity_unit": "L",
            "result_unit": "kgCO2e",
            "source_reference": "Test diesel source",
            "source_url": "https://example.test/diesel",
            "notes": None,
        },
        {
            "code": "GRID_ELECTRICITY",
            "factor_value": grid,
            "activity_unit": "kWh",
            "result_unit": "kgCO2e",
            "source_reference": "Test grid source",
            "source_url": "https://example.test/grid",
            "notes": None,
        },
    ]
    if lpg is not None:
        factors.append(
            {
                "code": "LPG_KG",
                "factor_value": lpg,
                "activity_unit": "kg",
                "result_unit": "kgCO2e",
                "source_reference": "Synthetic isolated-test LPG source",
                "source_url": "https://example.test/lpg",
                "notes": None,
            }
        )
    return {
        "version": version,
        "effective_from": effective_from,
        "source_note": "Institutional test methodology; isolated test database only.",
        "factors": factors,
    }


def _create_and_activate(client: TestClient, csrf: str, payload: dict[str, object]) -> dict[str, object]:
    created = client.post(
        "/api/admin/emission-factor-sets", json=payload, headers={"X-CSRF-Token": csrf}
    )
    assert created.status_code == 201, created.text
    activated = client.post(
        f"/api/admin/emission-factor-sets/{created.json()['id']}/activate",
        headers={"X-CSRF-Token": csrf},
    )
    assert activated.status_code == 200, activated.text
    return activated.json()


def test_factor_admin_authorization_lifecycle_and_immutability(postgres_engine: Engine) -> None:
    admin = _account(postgres_engine, RoleCode.ADMIN)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    payload = _factor_payload("governance-2055-v1", "2055-01-01")

    with _client(postgres_engine) as anonymous, _client(postgres_engine) as manager_client, _client(
        postgres_engine
    ) as admin_client:
        assert anonymous.get("/api/admin/emission-factor-sets").status_code == 401
        manager_csrf = _login(manager_client, manager)
        assert manager_client.get("/api/admin/emission-factor-sets").status_code == 403
        assert manager_client.post(
            "/api/admin/emission-factor-sets", json=payload, headers={"X-CSRF-Token": manager_csrf}
        ).status_code == 403

        admin_csrf = _login(admin_client, admin)
        assert admin_client.post("/api/admin/emission-factor-sets", json=payload).status_code == 403
        created = admin_client.post(
            "/api/admin/emission-factor-sets", json=payload, headers={"X-CSRF-Token": admin_csrf}
        )
        assert created.status_code == 201, created.text
        draft = created.json()
        stale = {**payload, "expected_row_version": draft["row_version"] + 1}
        assert admin_client.put(
            f"/api/admin/emission-factor-sets/{draft['id']}",
            json=stale,
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 409
        activated = admin_client.post(
            f"/api/admin/emission-factor-sets/{draft['id']}/activate",
            headers={"X-CSRF-Token": admin_csrf},
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["status"] == "active"
        update = {**payload, "expected_row_version": activated.json()["row_version"]}
        assert admin_client.put(
            f"/api/admin/emission-factor-sets/{draft['id']}",
            json=update,
            headers={"X-CSRF-Token": admin_csrf},
        ).status_code == 409
        detail = admin_client.get(f"/api/admin/emission-factor-sets/{draft['id']}").json()
        assert detail["factors"][0]["factor_value"] in {"2.7010000000", "0.7270000000", "2.3880000000"}


def test_effective_date_resolution_and_grid_snapshot(postgres_engine: Engine) -> None:
    admin = _account(postgres_engine, RoleCode.ADMIN)
    energy_manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.ENERGY)
    period_2026 = _period(postgres_engine, 2026, 11)
    period_2027 = _period(postgres_engine, 2027, 2)

    with _client(postgres_engine) as admin_client:
        csrf = _login(admin_client, admin)
        factor_2026 = _create_and_activate(
            admin_client, csrf, _factor_payload("calculation-2026-v1", "2026-01-01")
        )
        factor_2027 = _create_and_activate(
            admin_client, csrf, _factor_payload("calculation-2027-v1", "2027-01-01", "0.800")
        )

    with Session(postgres_engine) as db:
        selected_2026 = applicable_factor_set(db, db.get(ReportingPeriod, period_2026.id))  # type: ignore[arg-type]
        selected_2027 = applicable_factor_set(db, db.get(ReportingPeriod, period_2027.id))  # type: ignore[arg-type]
        assert selected_2026 is not None and str(selected_2026.id) == factor_2026["id"]
        assert selected_2027 is not None and str(selected_2027.id) == factor_2027["id"]

    with _client(postgres_engine, period_2026) as manager_client:
        csrf = _login(manager_client, energy_manager)
        values = _values(postgres_engine, OperationalDomain.ENERGY)
        for item in values:
            if item["metric_code"] == "grid_ht_kwh":
                item["value"] = "1877147"
            elif str(item["metric_code"]).startswith("grid_"):
                item["value"] = "0"
        created = manager_client.post(
            "/api/manager/energy/submissions",
            json={"reporting_period_id": str(period_2026.id), "remarks": None, "values": values},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201, created.text
        submission_id = created.json()["id"]
        assert manager_client.post(
            f"/api/manager/energy/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        frozen = manager_client.get(f"/api/manager/energy/submissions/{submission_id}").json()
        calculation = frozen["calculations"][0]
        assert calculation["factor_set_version"] == "calculation-2026-v1"
        assert Decimal(calculation["result_value"]) == Decimal("1364.685869")
        assert calculation["provisional"] is False

        with _client(postgres_engine) as review_client:
            admin_csrf = _login(review_client, admin)
            assert review_client.post(
                f"/api/admin/submissions/{submission_id}/begin-review",
                headers={"X-CSRF-Token": admin_csrf},
            ).status_code == 200
            assert review_client.post(
                f"/api/admin/submissions/{submission_id}/request-correction",
                json={"reason": "Recheck grid activity."},
                headers={"X-CSRF-Token": admin_csrf},
            ).status_code == 200
        correction = manager_client.get(f"/api/manager/energy/submissions/{submission_id}").json()
        values[0]["value"] = "2"
        updated = manager_client.put(
            f"/api/manager/energy/submissions/{submission_id}",
            json={
                "remarks": "Corrected calculation revision",
                "values": values,
                "expected_row_version": correction["row_version"],
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert updated.status_code == 200, updated.text
        assert manager_client.post(
            f"/api/manager/energy/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200

    with Session(postgres_engine) as db:
        rows = db.scalars(
            select(CalculationResult)
            .where(CalculationResult.submission_id == submission_id)
            .order_by(CalculationResult.submission_revision)
        ).all()
        assert [item.submission_revision for item in rows] == [1, 2]
        row = rows[0]
        assert row is not None
        assert row.submission_revision == 1
        assert row.factor_set_version == "calculation-2026-v1"
        assert row.factor_code == FactorCode.GRID_ELECTRICITY.value
        assert row.factor_value == Decimal("0.7270000000")
        assert row.result_kgco2e == Decimal("1364685.869000")
        assert row.result_value == Decimal("1364.685869")
        assert row.result_unit == "tCO2e"


def test_missing_lpg_factor_is_explicitly_unavailable_with_kg_activity(postgres_engine: Engine) -> None:
    lpg_manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.LPG)
    period = _period(postgres_engine, 2031, 4)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, lpg_manager)
        values = _values(postgres_engine, OperationalDomain.LPG)
        # lpg_weight_kg is the only required LPG metric; litres are no longer collected.
        assert [item["metric_code"] for item in values] == ["lpg_weight_kg"]
        created = client.post(
            "/api/manager/lpg/submissions",
            json={"reporting_period_id": str(period.id), "remarks": None, "values": values},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201, created.text
        submission_id = created.json()["id"]
        calculation = created.json()["calculations"][0]
        assert calculation["status"] == "unavailable"
        assert calculation["reason"] == "factor_not_configured"
        assert calculation["activity_metric_code"] == "lpg_weight_kg"
        assert Decimal(calculation["activity_value"]) == Decimal("1")
        assert calculation["activity_unit"] == "kg"
        assert calculation["result_value"] is None
        assert client.post(
            f"/api/manager/lpg/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        submitted = client.get(f"/api/manager/lpg/submissions/{submission_id}").json()
        assert submitted["calculations"][0]["status"] == "unavailable"
        assert submitted["calculations"][0]["reason"] == "factor_not_configured"


def test_lpg_kg_factor_is_optional_but_if_present_must_use_kg(postgres_engine: Engine) -> None:
    admin = _account(postgres_engine, RoleCode.ADMIN)
    payload = _factor_payload("lpg-invalid-unit-2041", "2041-01-01", lpg="3.000")
    lpg_factor = next(item for item in payload["factors"] if item["code"] == "LPG_KG")  # type: ignore[union-attr]
    # Litres are the retired basis; activation must reject them for LPG_KG.
    lpg_factor["activity_unit"] = "L"
    with _client(postgres_engine) as client:
        csrf = _login(client, admin)
        created = client.post(
            "/api/admin/emission-factor-sets", json=payload, headers={"X-CSRF-Token": csrf}
        )
        assert created.status_code == 201, created.text
        denied = client.post(
            f"/api/admin/emission-factor-sets/{created.json()['id']}/activate",
            headers={"X-CSRF-Token": csrf},
        )
        assert denied.status_code == 422
        assert "LPG_KG has an incompatible unit" in denied.text


def test_retired_litre_lpg_factor_code_cannot_be_written(postgres_engine: Engine) -> None:
    admin = _account(postgres_engine, RoleCode.ADMIN)
    payload = _factor_payload("lpg-litre-refused-2042", "2042-01-01", lpg="1.5571")
    lpg_factor = next(item for item in payload["factors"] if item["code"] == "LPG_KG")  # type: ignore[union-attr]
    lpg_factor["code"] = "LPG"
    lpg_factor["activity_unit"] = "L"
    with _client(postgres_engine) as client:
        csrf = _login(client, admin)
        refused = client.post(
            "/api/admin/emission-factor-sets", json=payload, headers={"X-CSRF-Token": csrf}
        )
        assert refused.status_code == 422
    with Session(postgres_engine) as db:
        assert db.scalar(
            select(EmissionFactorSet.id).where(EmissionFactorSet.version == "lpg-litre-refused-2042")
        ) is None
    # The API hides validation detail; the schema names the reason.
    with pytest.raises(ValidationError, match="litre-based LPG factor is retired"):
        FactorWrite.model_validate(lpg_factor)


def test_lpg_kg_calculation_uses_weight_and_freezes_provenance(postgres_engine: Engine) -> None:
    """Owner case, Jan 2026: 7429 kg x 2.98 kgCO2e/kg = 22138.42 kgCO2e = 22.13842 tCO2e.

    The kg value is the governed activity and is never converted; the
    cylinder count is reference metadata and must not influence the result.
    """
    admin = _account(postgres_engine, RoleCode.ADMIN)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.LPG)
    period = _period(postgres_engine, 2043, 5)
    with _client(postgres_engine) as admin_client:
        csrf = _login(admin_client, admin)
        factor_set = _create_and_activate(
            admin_client, csrf, _factor_payload("lpg-kg-2043-v1", "2043-01-01", lpg="2.98")
        )
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        values = [
            {"metric_code": "lpg_weight_kg", "value": "7429", "quality_note": None},
            {"metric_code": "lpg_cylinder_count", "value": "391", "quality_note": None},
        ]
        # The deprecated litre metric is inactive: a write is refused.
        refused = client.post(
            "/api/manager/lpg/submissions",
            json={
                "reporting_period_id": str(period.id),
                "remarks": None,
                "values": [*values, {"metric_code": "lpg_consumption_litres", "value": "1", "quality_note": None}],
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert refused.status_code == 422
        created = client.post(
            "/api/manager/lpg/submissions",
            json={"reporting_period_id": str(period.id), "remarks": None, "values": values},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201, created.text
        submission_id = created.json()["id"]
        assert client.post(
            f"/api/manager/lpg/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        calculations = client.get(f"/api/manager/lpg/submissions/{submission_id}").json()["calculations"]
        assert len(calculations) == 1
        calculation = calculations[0]
        assert calculation["status"] == "available"
        assert calculation["activity_metric_code"] == "lpg_weight_kg"
        assert Decimal(calculation["activity_value"]) == Decimal("7429")
        assert calculation["activity_unit"] == "kg"
        assert calculation["factor_code"] == "LPG_KG"
        assert calculation["factor_set_version"] == factor_set["version"]
        assert calculation["factor_unit"] == "kgCO2e/kg"
        assert Decimal(calculation["factor_value"]) == Decimal("2.98")
        assert Decimal(calculation["result_kgco2e"]) == Decimal("22138.420000")
        assert Decimal(calculation["result_value"]) == Decimal("22.138420")
        assert calculation["result_unit"] == "tCO2e"

    with Session(postgres_engine) as db:
        frozen = db.scalar(
            select(CalculationResult).where(CalculationResult.submission_id == submission_id)
        )
        assert frozen is not None
        assert frozen.metric_code == "lpg_weight_kg"
        assert frozen.activity_value == Decimal("7429.000000")
        assert frozen.activity_unit == "kg"
        assert frozen.factor_code == "LPG_KG"
        assert frozen.factor_value == Decimal("2.9800000000")
        assert frozen.factor_unit == "kgCO2e/kg"
        assert frozen.result_kgco2e == Decimal("22138.420000")
        assert frozen.result_value == Decimal("22.138420")


def test_activation_rejects_incomplete_core_set(postgres_engine: Engine) -> None:
    admin = _account(postgres_engine, RoleCode.ADMIN)
    payload = _factor_payload("incomplete-core-v1", date(2040, 1, 1).isoformat())
    payload["factors"] = list(payload["factors"])[:-1]  # type: ignore[arg-type]
    with _client(postgres_engine) as client:
        csrf = _login(client, admin)
        created = client.post(
            "/api/admin/emission-factor-sets", json=payload, headers={"X-CSRF-Token": csrf}
        )
        assert created.status_code == 201
        denied = client.post(
            f"/api/admin/emission-factor-sets/{created.json()['id']}/activate",
            headers={"X-CSRF-Token": csrf},
        )
        assert denied.status_code == 422
        with Session(postgres_engine) as db:
            item = db.get(EmissionFactorSet, created.json()["id"])
            assert item is not None and item.status == FactorSetStatus.DRAFT


def test_transport_petrol_and_diesel_calculations_share_governed_provenance(
    postgres_engine: Engine,
) -> None:
    admin = _account(postgres_engine, RoleCode.ADMIN)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    period = _period(postgres_engine, 2042, 5)
    with _client(postgres_engine) as admin_client:
        admin_csrf = _login(admin_client, admin)
        factor_set = _create_and_activate(
            admin_client, admin_csrf, _factor_payload("transport-2042-v1", "2042-01-01")
        )
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        values = _values(postgres_engine, OperationalDomain.TRANSPORT)
        # DG is entered as generation (kWh) under the kWh methodology.
        activity = {
            "transport_petrol_litres": "10",
            "transport_diesel_litres": "20",
            "dg_generation_kwh": "30",
        }
        for item in values:
            if item["metric_code"] in activity:
                item["value"] = activity[str(item["metric_code"])]
        created = client.post(
            "/api/manager/transport/submissions",
            json={"reporting_period_id": str(period.id), "remarks": None, "values": values},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201, created.text
        submission_id = created.json()["id"]
        assert client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        calculations = {
            item["calculation_code"]: item
            for item in client.get(f"/api/manager/transport/submissions/{submission_id}").json()["calculations"]
        }
        assert Decimal(calculations["transport_petrol_emissions"]["result_value"]) == Decimal("0.023880")
        assert Decimal(calculations["transport_diesel_emissions"]["result_value"]) == Decimal("0.054020")
        # 30 kWh x 0.33 L/kWh = 9.9 L; 9.9 L x 2.701 kgCO2e/L / 1000 = 0.0267399 tCO2e.
        assert Decimal(calculations["dg_diesel_emissions"]["result_value"]) == Decimal("0.026740")
        assert calculations["dg_diesel_emissions"]["activity_metric_code"] == "dg_generation_kwh"
        assert calculations["dg_diesel_emissions"]["derivation"]["derived_value"] == "9.9"
        assert calculations["transport_diesel_emissions"]["factor_code"] == "DIESEL"
        assert calculations["dg_diesel_emissions"]["factor_code"] == "DIESEL"
        assert calculations["transport_diesel_emissions"]["factor_set_id"] == factor_set["id"]
        assert calculations["dg_diesel_emissions"]["factor_set_id"] == factor_set["id"]


def test_submission_without_applicable_factor_freezes_unavailable_state(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    period = _period(postgres_engine, 2001, 3)
    with _client(postgres_engine, period) as client:
        csrf = _login(client, manager)
        created = client.post(
            "/api/manager/transport/submissions",
            json={
                "reporting_period_id": str(period.id),
                "remarks": None,
                "values": _values(postgres_engine, OperationalDomain.TRANSPORT, period=period),
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201, created.text
        submission_id = created.json()["id"]
        assert client.post(
            f"/api/manager/transport/submissions/{submission_id}/submit",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        calculations = client.get(f"/api/manager/transport/submissions/{submission_id}").json()[
            "calculations"
        ]
        assert calculations
        assert {item["status"] for item in calculations} == {"unavailable"}
        assert {item["reason"] for item in calculations} == {"no_applicable_factor"}
        with Session(postgres_engine) as db:
            rows = db.scalars(
                select(CalculationResult).where(CalculationResult.submission_id == submission_id)
            ).all()
            assert rows and {item.calculation_status for item in rows} == {"unavailable"}
            assert {item.unavailable_reason for item in rows} == {"no_applicable_factor"}
            assert all(item.factor_value is None and item.result_value is None for item in rows)
