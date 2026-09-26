"""Add the Aeron environmental readings time series.

Revision ID: 0012_environment_readings
Revises: 0011_historical_data_layer

A self-contained ``environment`` schema: append-only readings keyed by
station + observation instant, and one row per ingestion-worker cycle. It has
no foreign keys into, and makes no change to, any sustainability, history,
identity or publication table.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012_environment_readings"
down_revision = "0011_historical_data_layer"
branch_labels = None
depends_on = None

METRIC_COLUMNS = (
    "co_mg_m3",
    "no2_ug_m3",
    "so2_ug_m3",
    "o3_ug_m3",
    "no_ug_m3",
    "pm25_ug_m3",
    "pm10_ug_m3",
    "temperature_c",
    "relative_humidity_percent",
    "rain_mm",
    "wind_speed_kmph",
    "wind_direction_deg",
    "noise_average_db",
    "noise_min_db",
    "noise_max_db",
    "uv_index",
    "co2_ppm",
    "co_we_mv",
    "co_aux_mv",
    "no2_we_mv",
    "no2_aux_mv",
    "so2_we_mv",
    "so2_aux_mv",
    "o3_we_mv",
    "o3_aux_mv",
    "no_we_mv",
    "no_aux_mv",
    "barometric_pressure_mba",
    "molecular_volume_ltr",
    "co_ppb",
    "no2_ppb",
    "so2_ppb",
    "o3_ppb",
    "no_ppb",
    "air_quality_index",
)
HEALTH_COLUMNS = ("network", "battery", "charging", "device_temp")


def upgrade() -> None:
    op.execute("create schema environment")
    op.execute("revoke all on schema environment from public")

    op.create_table(
        "readings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("station_id", sa.String(100), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source_recorded_at_raw", sa.String(64), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("source_route", sa.String(200), nullable=False),
        sa.Column("normalizer_version", sa.SmallInteger(), nullable=False),
        sa.Column("quality_flags", postgresql.JSONB(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        *[sa.Column(name, sa.Double()) for name in METRIC_COLUMNS],
        *[sa.Column(name, sa.Integer()) for name in HEALTH_COLUMNS],
        sa.UniqueConstraint("station_id", "observed_at", name="uq_readings_station_observed_at"),
        schema="environment",
    )
    op.create_index("ix_readings_station_observed_at", "readings", ["station_id", "observed_at"], schema="environment")

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("station_id", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(40)),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("login_performed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("detail", sa.Text()),
        sa.CheckConstraint("outcome in ('INSERTED', 'DUPLICATE', 'FAILED')", name="ck_ingestion_runs_outcome_allowed"),
        schema="environment",
    )
    op.create_index("ix_ingestion_runs_started_at", "ingestion_runs", ["started_at"], schema="environment")


def downgrade() -> None:
    op.drop_index("ix_ingestion_runs_started_at", table_name="ingestion_runs", schema="environment")
    op.drop_table("ingestion_runs", schema="environment")
    op.drop_index("ix_readings_station_observed_at", table_name="readings", schema="environment")
    op.drop_table("readings", schema="environment")
    op.execute("drop schema environment")
