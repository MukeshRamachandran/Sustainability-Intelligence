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
        "metric_definitions",
        "submissions",
        "submission_values",
        "review_actions",
        "emission_factor_sets",
        "emission_factors",
        "calculation_results",
    },
    "publication": {"public_releases", "public_release_payloads"},
    "audit": {"audit_logs"},
}

PUBLIC_METRICS = {
    "transport_petrol_litres",
    "transport_diesel_litres",
    "dg_diesel_litres",
    "lpg_weight_kg",
    "grid_total_kwh",
    "renewable_total_kwh",
    "water_consumed_kl",
    "water_recycled_kl",
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
        assert domains == {"transport", "energy", "lpg", "water", "outreach"}
        metrics = (
            connection.execute(
                text("select code,publication_class::text,manager_editable from sustainability.metric_definitions")
            )
            .mappings()
            .all()
        )
        assert len(metrics) == 46
        assert {row["code"] for row in metrics if row["publication_class"] == "public_aggregate"} == PUBLIC_METRICS
        internal = {row["code"] for row in metrics if row["publication_class"] == "internal_verification"}
        assert all(code.startswith(("inlet_", "outlet_", "stp_")) for code in internal)
        assert {row["code"] for row in metrics if not row["manager_editable"]} == {
            "grid_total_kwh",
            "renewable_total_kwh",
            "water_consumed_kl",
        }
        lpg_factor_count = connection.scalar(
            text("select count(*) from sustainability.emission_factors where upper(code)='LPG'")
        )
        assert lpg_factor_count == 0


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
        assert (
            float(
                connection.scalar(
                    text("""
            select value from sustainability.submission_values
            where submission_id=:id and metric_code='renewable_total_kwh'
        """),
                    {"id": energy_submission},
                )
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
