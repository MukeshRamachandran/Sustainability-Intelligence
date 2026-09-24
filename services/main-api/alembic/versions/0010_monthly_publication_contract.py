"""Add the schema 1.3 publication contract and population reference.

Revision ID: 0010_publication_1_3
Revises: 0009_waste_domain
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_publication_1_3"
down_revision = "0009_waste_domain"
branch_labels = None
depends_on = None

PUBLIC_METRICS = (
    "grid_ht_kwh",
    "grid_commercial_kwh",
    "grid_temporary_kwh",
    "renewable_on_campus_kwh",
    "renewable_procured_kwh",
    "solar_water_heater_kwh",
    "water_twad_kl",
    "water_borewell_kl",
    "water_private_kl",
    "wastewater_generated_kl",
)

POPULATION_SOURCE = "K-COSMOS Phase 1.3 project-owner decision: 6,991 people for 2026"


def upgrade() -> None:
    op.create_table(
        "institutional_population_references",
        sa.Column("effective_year", sa.SmallInteger(), nullable=False),
        sa.Column("population", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("population >= 0", name="population_non_negative"),
        sa.CheckConstraint("unit = 'people'", name="population_unit_people"),
        sa.CheckConstraint("length(trim(source_reference)) > 0", name="population_source_required"),
        sa.PrimaryKeyConstraint("effective_year", name="pk_institutional_population_references"),
        schema="sustainability",
    )
    op.execute(
        sa.text(
            "insert into sustainability.institutional_population_references "
            "(effective_year, population, unit, source_reference) "
            "values (2026, 6991, 'people', :source)"
        ).bindparams(source=POPULATION_SOURCE)
    )
    for code in PUBLIC_METRICS:
        op.execute(
            sa.text(
                "update sustainability.metric_definitions "
                "set publication_class = 'public_aggregate' where code = :code"
            ).bindparams(code=code)
        )


def downgrade() -> None:
    connection = op.get_bind()
    reference_count = connection.execute(
        sa.text("select count(*) from sustainability.institutional_population_references")
    ).scalar_one()
    if reference_count > 1:
        raise RuntimeError(
            "refusing to downgrade: additional institutional population references exist; "
            "preserve them before reverting 0010"
        )
    for code in PUBLIC_METRICS:
        op.execute(
            sa.text(
                "update sustainability.metric_definitions "
                "set publication_class = 'admin_only' where code = :code"
            ).bindparams(code=code)
        )
    op.drop_table("institutional_population_references", schema="sustainability")
