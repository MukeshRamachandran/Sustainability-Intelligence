from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import DBAPIError

REQUIRED_TABLES = {
    "identity": {
        "users",
        "roles",
        "user_role_assignments",
        "manager_domain_assignments",
        "sessions",
    },
    "sustainability": {
        "reporting_periods",
        "institutional_population_references",
        "metric_definitions",
        "submissions",
        "submission_values",
        "review_actions",
        "emission_factor_sets",
        "emission_factors",
        "calculation_parameters",
        "calculation_results",
    },
    "publication": {"public_releases", "public_release_payloads"},
    "audit": {"audit_logs"},
}

PUBLIC_METRICS = {
    "transport_petrol_litres",
    "transport_diesel_litres",
    "dg_diesel_litres",
    "dg_generation_kwh",
    "lpg_weight_kg",
    "grid_total_kwh",
    "grid_ht_kwh",
    "grid_commercial_kwh",
    "grid_temporary_kwh",
    "renewable_on_campus_kwh",
    "renewable_procured_kwh",
    "solar_water_heater_kwh",
    "water_twad_kl",
    "water_borewell_kl",
    "water_private_kl",
    "water_consumed_kl",
    "wastewater_generated_kl",
    "water_recycled_kl",
    "wet_waste_generated_kg",
    "dry_waste_generated_kg",
    "total_waste_generated_kg",
}


def test_required_tables_and_secure_columns_exist(postgres_engine: Engine) -> None:
    inspector = inspect(postgres_engine)
    for schema, expected in REQUIRED_TABLES.items():
        assert expected <= set(inspector.get_table_names(schema=schema))
    user_columns = {column["name"] for column in inspector.get_columns("users", schema="identity")}
    session_columns = {column["name"] for column in inspector.get_columns("sessions", schema="identity")}
    assert "password_hash" in user_columns
    assert "password" not in user_columns
    assert "session_token_hash" in session_columns
    assert "session_token" not in session_columns


def test_roles_domains_and_metric_publication_are_seeded(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as connection:
        assert set(connection.execute(text("select code from identity.roles")).scalars()) == {
            "manager",
            "microcosm_admin",
        }
        domains = set(
            connection.execute(
                text("select unnest(enum_range(null::sustainability.operational_domain))::text")
            ).scalars()
        )
        assert domains == {"transport", "energy", "lpg", "water", "outreach", "waste"}
        metrics = (
            connection.execute(
                text("select code,publication_class::text,manager_editable from sustainability.metric_definitions")
            )
            .mappings()
            .all()
        )
        # 46 original + 3 waste metrics (0009_waste_domain) + DG generation (0015_dg_kwh_methodology).
        assert len(metrics) == 50
        assert {row["code"] for row in metrics if row["publication_class"] == "public_aggregate"} == PUBLIC_METRICS
        internal = {row["code"] for row in metrics if row["publication_class"] == "internal_verification"}
        assert all(code.startswith(("inlet_", "outlet_", "stp_")) for code in internal)
        # Derived metrics are written by database trigger only; the
        # submission_value_guard rejects any direct application write.
        assert {row["code"] for row in metrics if not row["manager_editable"]} == {
            "grid_total_kwh",
            "renewable_total_kwh",
            "water_consumed_kl",
            "dry_waste_generated_kg",
            "total_waste_generated_kg",
        }
        # 0013_lpg_kg_governance_v2 replaces the 0008 draft-only litre LPG
        # factor in the migration-seeded DRAFT set with LPG_KG on kg, once.
        seeded = (
            connection.execute(
                text("""
                select f.code, f.factor_value, f.activity_unit, f.result_unit, f.source_reference,
                       s.status, s.effective_from
                  from sustainability.emission_factors f
                  join sustainability.emission_factor_sets s on s.id = f.factor_set_id
                 where s.id = '20000000-0000-0000-0000-000000000001'
                 order by f.code
                """)
            )
            .mappings()
            .all()
        )
        assert [row["code"] for row in seeded] == ["DIESEL", "GRID_ELECTRICITY", "LPG_KG", "PETROL"]
        lpg = next(row for row in seeded if row["code"] == "LPG_KG")
        assert lpg["factor_value"] == Decimal("2.9800000000")
        assert lpg["activity_unit"] == "kg"
        assert lpg["result_unit"] == "kgCO2e"
        assert "institutional LPG kg calculation baseline" in lpg["source_reference"]
        # Every factor carries the baseline provenance, but the set stays a
        # draft with no effective date, so it cannot be activated accidentally.
        assert all(row["source_reference"] for row in seeded)
        assert lpg["status"] == "draft"
        assert lpg["effective_from"] is None
        lpg_metrics = {
            row["code"]: row
            for row in connection.execute(
                text("""
                select code, canonical_unit, factor_code, required_for_complete, is_active,
                       publication_class::text as publication_class
                  from sustainability.metric_definitions where operational_domain = 'lpg'
                """)
            ).mappings()
        }
        assert lpg_metrics["lpg_weight_kg"]["factor_code"] == "LPG_KG"
        assert lpg_metrics["lpg_weight_kg"]["canonical_unit"] == "kg"
        assert lpg_metrics["lpg_weight_kg"]["required_for_complete"] is True
        assert lpg_metrics["lpg_weight_kg"]["publication_class"] == "public_aggregate"
        # The deprecated litre metric is kept for frozen audit records only.
        assert lpg_metrics["lpg_consumption_litres"]["is_active"] is False
        assert lpg_metrics["lpg_consumption_litres"]["factor_code"] is None
        assert lpg_metrics["lpg_consumption_litres"]["publication_class"] == "admin_only"
        assert lpg_metrics["lpg_cylinder_count"]["required_for_complete"] is False


def test_owner_approved_population_reference_is_seeded_and_governed(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as connection:
        rows = connection.execute(
            text(
                "select effective_year, population, unit, source_reference "
                "from sustainability.institutional_population_references"
            )
        ).mappings().all()
    assert rows == [
        {
            "effective_year": 2026,
            "population": 6991,
            "unit": "people",
            "source_reference": "K-COSMOS Phase 1.3 project-owner decision: 6,991 people for 2026",
        }
    ]


def _insert_manager(connection: object, domain: str) -> str:
    user_id = str(uuid4())
    assignment_id = str(uuid4())
    domain_id = str(uuid4())
    connection.execute(
        text("""
        insert into identity.users(id,username,normalized_username,display_name,password_hash)
        values(:id,:username,:username,:username,'argon2-test-hash')
    """),
        {"id": user_id, "username": f"calc-{user_id}"},
    )
    connection.execute(
        text("""
        insert into identity.user_role_assignments(id,user_id,role_id,reason)
        values(:id,:user,'10000000-0000-0000-0000-000000000001','test')
    """),
        {"id": assignment_id, "user": user_id},
    )
    connection.execute(
        text("""
        insert into identity.manager_domain_assignments(id,user_id,domain,reason)
        values(:id,:user,cast(:domain as sustainability.operational_domain),'test')
    """),
        {"id": domain_id, "user": user_id, "domain": domain},
    )
    return user_id


def _insert_submission(connection: object, user_id: str, domain: str, year: int) -> str:
    period_id = str(uuid4())
    submission_id = str(uuid4())
    connection.execute(
        text("""
        insert into sustainability.reporting_periods(id,year,month,period_start,period_end)
        values(:id,:year,1,make_date(:year,1,1),make_date(:year,1,31))
    """),
        {"id": period_id, "year": year},
    )
    connection.execute(
        text("""
        insert into sustainability.submissions(id,domain,manager_user_id,reporting_period_id)
        values(:id,cast(:domain as sustainability.operational_domain),:user,:period)
    """),
        {"id": submission_id, "domain": domain, "user": user_id, "period": period_id},
    )
    return submission_id


def _value(connection: object, submission_id: str, code: str, value: int | None, unit: str) -> None:
    connection.execute(
        text("""
        insert into sustainability.submission_values(submission_id,metric_code,value,canonical_unit)
        values(:submission,:code,:value,:unit)
    """),
        {"submission": submission_id, "code": code, "value": value, "unit": unit},
    )


def test_database_calculates_totals_and_preserves_null_zero(postgres_engine: Engine) -> None:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    try:
        energy_user = _insert_manager(connection, "energy")
        energy_submission = _insert_submission(connection, energy_user, "energy", 2181)
        _value(connection, energy_submission, "grid_ht_kwh", 10, "kWh")
        assert (
            connection.scalar(
                text("""
            select value from sustainability.submission_values
            where submission_id=:id and metric_code='grid_total_kwh'
        """),
                {"id": energy_submission},
            )
            is None
        )
        _value(connection, energy_submission, "grid_commercial_kwh", 20, "kWh")
        _value(connection, energy_submission, "grid_temporary_kwh", 0, "kWh")
        assert (
            float(
                connection.scalar(
                    text("""
            select value from sustainability.submission_values
            where submission_id=:id and metric_code='grid_total_kwh'
        """),
                    {"id": energy_submission},
                )
            )
            == 30
        )
        _value(connection, energy_submission, "renewable_on_campus_kwh", 0, "kWh")
        _value(connection, energy_submission, "renewable_procured_kwh", 0, "kWh")
        _value(connection, energy_submission, "solar_water_heater_kwh", 0, "kWh")
        # 0016: the legacy trigger total (on-campus + procured + solar water
        # heater) is no longer written; renewable electricity is derived by the
        # backend from on-campus + procured only.
        assert (
            connection.scalar(
                text("""
            select count(*) from sustainability.submission_values
            where submission_id=:id and metric_code='renewable_total_kwh'
        """),
                {"id": energy_submission},
            )
            == 0
        )

        water_user = _insert_manager(connection, "water")
        water_submission = _insert_submission(connection, water_user, "water", 2182)
        _value(connection, water_submission, "water_twad_kl", 2, "KL")
        _value(connection, water_submission, "water_borewell_kl", 3, "KL")
        _value(connection, water_submission, "water_private_kl", 4, "KL")
        assert (
            float(
                connection.scalar(
                    text("""
            select value from sustainability.submission_values
            where submission_id=:id and metric_code='water_consumed_kl'
        """),
                    {"id": water_submission},
                )
            )
            == 9
        )
    finally:
        transaction.rollback()
        connection.close()


def test_calculated_direct_write_and_duplicate_active_submission_fail(
    postgres_engine: Engine,
) -> None:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    try:
        user_id = _insert_manager(connection, "energy")
        submission_id = _insert_submission(connection, user_id, "energy", 2183)
        with pytest.raises(DBAPIError), connection.begin_nested():
            _value(connection, submission_id, "grid_total_kwh", 999, "kWh")

        period_id = connection.scalar(
            text("select reporting_period_id from sustainability.submissions where id=:id"),
            {"id": submission_id},
        )
        with pytest.raises(DBAPIError), connection.begin_nested():
            connection.execute(
                text("""
                insert into sustainability.submissions(id,domain,manager_user_id,reporting_period_id)
                values(:id,'energy',:user,:period)
            """),
                {"id": str(uuid4()), "user": user_id, "period": period_id},
            )
    finally:
        transaction.rollback()
        connection.close()
