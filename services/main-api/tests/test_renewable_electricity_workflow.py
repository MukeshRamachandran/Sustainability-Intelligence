"""Manager/Admin renewable electricity excludes the solar water heater (0016).

Project-owner decision: the solar water heater is thermal energy. The
electrical renewable total is on-campus + procured renewable electricity, and
only that total feeds total electricity, renewable share and avoided grid
emissions. The solar water heater stays a separate Manager-entered value with
no emission impact calculated for it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.models.enums import FactorSetStatus, OperationalDomain, RoleCode
from app.models.sustainability import (
    EmissionFactor,
    EmissionFactorSet,
    MetricDefinition,
    ReportingPeriod,
    Submission,
    SubmissionValue,
)
from app.services import sustainability_formulas as formulas
from app.services.publication import _generic_domain_payload, _schema_1_4_indicators, electricity_indicators
from tests.test_generic_submission_integration import _account, _client, _login, _period

GRID_FACTOR = Decimal("0.727")
# The owner's acceptance example (July 2026 institutional figures).
GRID = {"grid_ht_kwh": "39366", "grid_commercial_kwh": "1261", "grid_temporary_kwh": "267"}
ON_CAMPUS, PROCURED, SOLAR_THERMAL = "18595", "286334", "62500"
LEGACY_COMBINED_TOTAL = 367429  # on-campus + procured + solar water heater: must never be the electrical total


def _factor_set_from(db: Session, start: date) -> None:
    item = EmissionFactorSet(
        id=uuid4(), version=f"renewable-workflow-{start.isoformat()}-{uuid4().hex[:6]}",
        status=FactorSetStatus.ACTIVE, source_note="Synthetic renewable workflow factors",
        effective_from=start, activated_at=datetime.now(UTC),
    )
    db.add(item)
    db.flush()
    for code, value, unit in (("PETROL", "2.388", "L"), ("DIESEL", "2.701", "L"), ("GRID_ELECTRICITY", "0.727", "kWh")):
        db.add(EmissionFactor(
            factor_set_id=item.id, code=code, factor_value=Decimal(value), activity_unit=unit,
            result_unit="kgCO2e", source_reference="Synthetic test factor",
        ))
    db.flush()


def _energy_values(on_campus: str | None, procured: str | None, solar: str | None) -> list[dict[str, object]]:
    values: dict[str, str | None] = {
        **GRID, "renewable_on_campus_kwh": on_campus, "renewable_procured_kwh": procured,
        "solar_water_heater_kwh": solar,
    }
    return [{"metric_code": code, "value": value, "quality_note": None} for code, value in values.items()]


@pytest.fixture
def energy(postgres_engine: Engine) -> tuple[ReportingPeriod, str]:
    period = _period(postgres_engine, 2176)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.ENERGY)
    with Session(postgres_engine) as db:
        _factor_set_from(db, period.period_start)
        db.commit()
    return period, manager


def _draft(
    client: TestClient, headers: dict[str, str], period: ReportingPeriod, values: list[dict[str, object]]
) -> Any:
    created = client.post(
        "/api/manager/energy/submissions",
        json={"reporting_period_id": str(period.id), "remarks": None, "values": values},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


def _value(indicators: dict[str, Any], code: str) -> Decimal | None:
    item = indicators[code]
    return None if item["value"] is None else Decimal(str(item["value"]))


# ---- Formula (no database) ----------------------------------------------------


def test_renewable_electricity_formula_has_no_thermal_input() -> None:
    assert formulas.renewable_electricity_kwh(Decimal(ON_CAMPUS), Decimal(PROCURED)) == Decimal("304929")
    assert formulas.renewable_electricity_kwh.__code__.co_argcount == 2  # on-campus and procured only
    assert formulas.total_electricity_consumption_kwh(Decimal("40894"), Decimal("304929")) == Decimal("345823")


# ---- Catalog and trigger (PostgreSQL) -----------------------------------------


def test_legacy_total_is_deprecated_and_no_longer_written(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as db:
        legacy = db.get(MetricDefinition, "renewable_total_kwh")
        assert legacy is not None  # kept so legacy submissions stay readable
        assert legacy.is_active is False and legacy.required_for_complete is False
        assert legacy.publication_class.value == "admin_only" and legacy.factor_code is None
        assert "deprecated" in legacy.display_name
        solar = db.get(MetricDefinition, "solar_water_heater_kwh")
        assert solar is not None and solar.is_active and solar.manager_editable
        assert solar.required_for_complete is True  # its requirement was not changed
        assert "thermal" in solar.display_name and "not electricity" in solar.display_name
        for code in ("renewable_on_campus_kwh", "renewable_procured_kwh"):
            definition = db.get(MetricDefinition, code)
            assert definition is not None and "electricity" in definition.display_name
        source = db.execute(
            text("select prosrc from pg_proc where proname = 'refresh_calculated_totals'")
        ).scalar_one()
        assert "renewable_total_kwh" not in source and "solar_water_heater_kwh" not in source
        assert "grid_total_kwh" in source and "water_consumed_kl" in source  # other totals untouched


# ---- Manager -> Admin (API) ---------------------------------------------------


def test_manager_example_derives_electrical_values_without_the_solar_water_heater(
    postgres_engine: Engine, energy: tuple[ReportingPeriod, str]
) -> None:
    period, manager = energy
    admin = _account(postgres_engine, RoleCode.ADMIN)
    with _client(postgres_engine, period) as client:
        headers = {"X-CSRF-Token": _login(client, manager)}
        offered = {item["code"] for item in client.get("/api/manager/energy/metrics").json()}
        assert {"renewable_on_campus_kwh", "renewable_procured_kwh", "solar_water_heater_kwh"} <= offered
        assert "renewable_total_kwh" not in offered

        # A client-supplied total is refused: derived values are backend-only.
        with_total = [*_energy_values(ON_CAMPUS, PROCURED, SOLAR_THERMAL),
                      {"metric_code": "renewable_total_kwh", "value": "367429", "quality_note": None}]
        assert client.post(
            "/api/manager/energy/submissions",
            json={"reporting_period_id": str(period.id), "remarks": None, "values": with_total}, headers=headers,
        ).status_code == 422

        draft = _draft(client, headers, period, _energy_values(ON_CAMPUS, PROCURED, SOLAR_THERMAL))
        submission_id = draft["id"]
        summary = draft["energy"]
        assert summary["provisional"] is True
        assert _value(summary, "renewable_electricity_kwh") == Decimal("304929")
        assert _value(summary, "total_electricity_consumption_kwh") == Decimal("345823")
        assert _value(summary, "renewable_share_pct") == Decimal("88.174875586644")
        assert _value(summary, "estimated_avoided_grid_emissions_tco2e") == Decimal("221.683383")
        assert summary["estimated_avoided_grid_emissions_tco2e"]["provenance"]["factor_code"] == "GRID_ELECTRICITY"
        avoided_provenance = summary["estimated_avoided_grid_emissions_tco2e"]["provenance"]
        assert Decimal(str(avoided_provenance["factor_value"])) == GRID_FACTOR
        # Solar thermal is reported apart and flagged as outside the electrical values.
        assert summary["solar_thermal"] == {
            "metric_code": "solar_water_heater_kwh", "value": 62500, "unit": "kWh", "included_in_electricity": False,
        }
        # The combined figure appears nowhere in the response.
        assert str(LEGACY_COMBINED_TOTAL) not in client.get(f"/api/manager/energy/submissions/{submission_id}").text
        stored = {item["metric_code"]: Decimal(item["value"]) for item in draft["values"]}
        assert stored["grid_total_kwh"] == Decimal("40894")
        assert stored["solar_water_heater_kwh"] == Decimal("62500")
        assert "renewable_total_kwh" not in stored
        assert client.post(
            f"/api/manager/energy/submissions/{submission_id}/submit", headers=headers
        ).status_code == 200

    with _client(postgres_engine) as admin_client:
        admin_headers = {"X-CSRF-Token": _login(admin_client, admin)}
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/begin-review", headers=admin_headers
        ).status_code == 200
        review = admin_client.get(f"/api/admin/submissions/{submission_id}").json()
        entered = {item["metric_code"]: Decimal(item["value"]) for item in review["values"]}
        assert entered["renewable_on_campus_kwh"] == Decimal("18595")
        assert entered["renewable_procured_kwh"] == Decimal("286334")
        assert entered["solar_water_heater_kwh"] == Decimal("62500")
        assert review["energy"]["provisional"] is False
        assert _value(review["energy"], "renewable_electricity_kwh") == Decimal("304929")
        assert review["energy"]["solar_thermal"]["value"] == 62500
        assert str(LEGACY_COMBINED_TOTAL) not in admin_client.get(f"/api/admin/submissions/{submission_id}").text
        assert admin_client.post(
            f"/api/admin/submissions/{submission_id}/approve", headers=admin_headers
        ).status_code == 200

    # After approval the release calculation uses the same electrical total.
    with Session(postgres_engine) as db:
        submission = db.get(Submission, submission_id)
        assert submission is not None and submission.status.value == "approved"
        block = _generic_domain_payload(db, submission)
        assert "renewable_total_kwh" not in block["metrics"]  # type: ignore[operator]
        assert block["metrics"]["solar_water_heater_kwh"] == {"value": 62500, "unit": "kWh"}  # type: ignore[index]
        indicators = _schema_1_4_indicators({"energy": block})
        assert indicators["renewable_electricity_kwh"]["value"] == 304929  # type: ignore[index]
        assert indicators["total_electricity_consumption_kwh"]["value"] == 345823  # type: ignore[index]
        assert indicators["estimated_avoided_grid_emissions_tco2e"]["value"] == 221.683383  # type: ignore[index]
        # The Manager/Admin summary is that same calculation, not a second formula.
        summary_after = electricity_indicators(db, submission)
        for code in ("renewable_electricity_kwh", "total_electricity_consumption_kwh", "renewable_share_pct",
                     "estimated_avoided_grid_emissions_tco2e"):
            assert summary_after[code] == indicators[code], code
        # Solar thermal stays stored separately, exactly as entered.
        thermal = db.scalar(select(SubmissionValue.value).where(
            SubmissionValue.submission_id == submission_id, SubmissionValue.metric_code == "solar_water_heater_kwh"
        ))
        assert thermal == Decimal("62500")


@pytest.mark.parametrize("solar", ["0", "62500", "999999999"])
def test_solar_water_heater_has_no_electrical_effect(
    postgres_engine: Engine, energy: tuple[ReportingPeriod, str], solar: str
) -> None:
    """Zero, the owner's figure and an extreme value all give the same electrical result."""
    period, manager = energy
    with _client(postgres_engine, period) as client:
        headers = {"X-CSRF-Token": _login(client, manager)}
        summary = _draft(client, headers, period, _energy_values(ON_CAMPUS, PROCURED, solar))["energy"]
    assert _value(summary, "renewable_electricity_kwh") == Decimal("304929")
    assert _value(summary, "total_electricity_consumption_kwh") == Decimal("345823")
    assert _value(summary, "renewable_share_pct") == Decimal("88.174875586644")
    assert _value(summary, "estimated_avoided_grid_emissions_tco2e") == Decimal("221.683383")
    assert Decimal(str(summary["solar_thermal"]["value"])) == Decimal(solar)


@pytest.mark.parametrize(
    ("on_campus", "procured", "expected"),
    [("0", "100", "100"), ("100", "0", "100"), ("0", "0", "0")],
)
def test_zero_is_a_reported_value(
    postgres_engine: Engine, energy: tuple[ReportingPeriod, str], on_campus: str, procured: str, expected: str
) -> None:
    period, manager = energy
    with _client(postgres_engine, period) as client:
        headers = {"X-CSRF-Token": _login(client, manager)}
        summary = _draft(client, headers, period, _energy_values(on_campus, procured, "62500"))["energy"]
    assert summary["renewable_electricity_kwh"]["status"] == "available"
    assert _value(summary, "renewable_electricity_kwh") == Decimal(expected)
    assert _value(summary, "total_electricity_consumption_kwh") == Decimal("40894") + Decimal(expected)
    avoided = formulas.estimated_avoided_grid_emissions_tco2e(Decimal(expected), GRID_FACTOR)
    assert _value(summary, "estimated_avoided_grid_emissions_tco2e") == avoided


def test_missing_source_is_missing_not_zero(postgres_engine: Engine, energy: tuple[ReportingPeriod, str]) -> None:
    period, manager = energy
    with _client(postgres_engine, period) as client:
        headers = {"X-CSRF-Token": _login(client, manager)}
        # Procured renewable not entered; the solar water heater cannot stand in for it.
        draft = _draft(client, headers, period, _energy_values(ON_CAMPUS, None, SOLAR_THERMAL))
        summary = draft["energy"]
        for code in ("renewable_electricity_kwh", "total_electricity_consumption_kwh", "renewable_share_pct",
                     "estimated_avoided_grid_emissions_tco2e"):
            assert summary[code]["status"] == "unavailable" and summary[code]["value"] is None, code
        assert summary["solar_thermal"]["value"] == 62500
        blocked = client.post(f"/api/manager/energy/submissions/{draft['id']}/submit", headers=headers)
        assert blocked.status_code == 422
        assert "renewable_procured_kwh" in blocked.text and "renewable_total_kwh" not in blocked.text

        # Solar water heater missing: the electrical values are unaffected, and it
        # is still a required source field (its requirement was not changed).
        no_solar = client.put(
            f"/api/manager/energy/submissions/{draft['id']}",
            json={"remarks": None, "values": _energy_values(ON_CAMPUS, PROCURED, None),
                  "expected_row_version": draft["row_version"]},
            headers=headers,
        )
        assert no_solar.status_code == 200, no_solar.text
        assert _value(no_solar.json()["energy"], "renewable_electricity_kwh") == Decimal("304929")
        assert no_solar.json()["energy"]["solar_thermal"]["value"] is None  # missing, not 0
        still_blocked = client.post(f"/api/manager/energy/submissions/{draft['id']}/submit", headers=headers)
        assert still_blocked.status_code == 422 and "solar_water_heater_kwh" in still_blocked.text


def test_correction_and_resubmit_recalculate_from_source_values(
    postgres_engine: Engine, energy: tuple[ReportingPeriod, str]
) -> None:
    period, manager = energy
    admin = _account(postgres_engine, RoleCode.ADMIN)
    with _client(postgres_engine, period) as client:
        headers = {"X-CSRF-Token": _login(client, manager)}
        draft = _draft(client, headers, period, _energy_values("100", "200", "50"))
        submission_id = draft["id"]
        submitted = client.post(f"/api/manager/energy/submissions/{submission_id}/submit", headers=headers)
        assert submitted.status_code == 200
        with _client(postgres_engine) as admin_client:
            admin_headers = {"X-CSRF-Token": _login(admin_client, admin)}
            assert admin_client.post(
                f"/api/admin/submissions/{submission_id}/begin-review", headers=admin_headers
            ).status_code == 200
            # The Admin has no way to write a derived value: the correction goes to the source.
            assert admin_client.post(
                f"/api/admin/submissions/{submission_id}/request-correction",
                json={"reason": "Check the procured renewable reading."}, headers=admin_headers,
            ).status_code == 200
        reopened = client.get(f"/api/manager/energy/submissions/{submission_id}").json()
        assert reopened["status"] == "correction_requested"
        assert _value(reopened["energy"], "renewable_electricity_kwh") == Decimal("300")
        corrected = client.put(
            f"/api/manager/energy/submissions/{submission_id}",
            json={"remarks": "Corrected", "values": _energy_values(ON_CAMPUS, PROCURED, SOLAR_THERMAL),
                  "expected_row_version": reopened["row_version"]},
            headers=headers,
        )
        assert corrected.status_code == 200, corrected.text
        assert _value(corrected.json()["energy"], "renewable_electricity_kwh") == Decimal("304929")
        resubmitted = client.post(f"/api/manager/energy/submissions/{submission_id}/submit", headers=headers)
        assert resubmitted.status_code == 200
        final = client.get(f"/api/manager/energy/submissions/{submission_id}").json()
        assert final["revision_number"] == 2 and final["energy"]["provisional"] is False
        assert _value(final["energy"], "total_electricity_consumption_kwh") == Decimal("345823")


def test_other_domains_carry_no_energy_summary(postgres_engine: Engine) -> None:
    period = _period(postgres_engine, 2177)
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.LPG)
    with _client(postgres_engine, period) as client:
        headers = {"X-CSRF-Token": _login(client, manager)}
        created = client.post(
            "/api/manager/lpg/submissions",
            json={"reporting_period_id": str(period.id), "remarks": None,
                  "values": [{"metric_code": "lpg_weight_kg", "value": "10", "quality_note": None}]},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["energy"] is None
