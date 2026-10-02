"""DG generator methodology: kWh generation is the Manager source from May 2026

Project-owner methodology (2026-10-01). Historical DG records through April
2026 are source-reported diesel litres and stay exactly as they are. From
2026-05-01 the Manager enters DG electricity generation (kWh); the backend
derives diesel litres with a governed specific fuel consumption (SFC) and then
applies the existing governed DIESEL emission factor:

    dg_diesel_litres    = dg_generation_kwh x DG_SFC          (L)
    dg_diesel_emissions = dg_diesel_litres x DIESEL / 1000    (tCO2e)

Schema (additive only; no existing row is updated):
  * ``sustainability.calculation_parameters`` - governed, effective-dated
    conversion parameters that are NOT emission factors. Seeded with
    ``DG_SFC`` = 0.33 L/kWh effective 2026-05-01.
  * ``dg_generation_kwh`` metric definition (Transport domain, where DG entry
    already lives; domain ownership and authorization are unchanged).
  * ``sustainability.calculation_results.derivation`` - the frozen derivation
    (source kWh, SFC, derived litres) behind a kWh-based DG emission.

``dg_diesel_litres`` keeps its definition: it remains the source-reported
activity of legacy periods and is the derived quantity of kWh periods.

Revision ID: 0015_dg_kwh_methodology
Revises: 0014_history_coverage_end_stated
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0015_dg_kwh_methodology"
down_revision = "0014_history_coverage_end_stated"
branch_labels = None
depends_on = None

DG_SFC_ID = "22000000-0000-0000-0000-000000000001"
DG_SFC_SOURCE = (
    "Project-owner approved DG methodology (2026-10-01): institutional DG calculation basis, "
    "specific fuel consumption 0.33 litres of diesel per kWh generated"
)
DG_SFC_NOTE = (
    "Fuel-consumption conversion parameter, not a greenhouse-gas emission factor. Applies to DG "
    "generation (kWh) entered from 2026-05-01; earlier DG records are source-reported litres."
)


def upgrade() -> None:
    op.create_table(
        "calculation_parameters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("parameter_value", sa.Numeric(20, 10), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", "effective_from", name="uq_calculation_parameter_code_effective"),
        sa.CheckConstraint("parameter_value >= 0", name="calculation_parameter_non_negative"),
        sa.CheckConstraint("length(trim(source_reference)) > 0", name="calculation_parameter_source_required"),
        schema="sustainability",
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            insert into sustainability.calculation_parameters
                   (id, code, parameter_value, unit, effective_from, source_reference, notes)
            values (:id, 'DG_SFC', 0.33, 'L/kWh', date '2026-05-01', :source, :notes)
            """
        ),
        {"id": DG_SFC_ID, "source": DG_SFC_SOURCE, "notes": DG_SFC_NOTE},
    )
    connection.execute(
        sa.text(
            """
            insert into sustainability.metric_definitions
                   (code, display_name, operational_domain, accounting_classification, canonical_unit,
                    min_value, max_value, required_for_complete, zero_allowed, manager_editable,
                    calculation_method, publication_class, factor_code, display_order)
            values ('dg_generation_kwh', 'DG electricity generated', 'transport', 'scope1_inventory', 'kWh',
                    0, 1000000000, true, true, true, null, 'public_aggregate', null, 55)
            """
        )
    )
    op.add_column(
        "calculation_results",
        sa.Column("derivation", postgresql.JSONB(astext_type=sa.Text())),
        schema="sustainability",
    )


def downgrade() -> None:
    connection = op.get_bind()
    referenced = connection.execute(
        sa.text(
            """
            select (select count(*) from sustainability.submission_values where metric_code = 'dg_generation_kwh')
                 + (select count(*) from sustainability.calculation_results where derivation is not null)
                 + (select count(*) from history.metric_values where metric_code = 'dg_generation_kwh')
            """
        )
    ).scalar_one()
    if referenced:
        raise RuntimeError(
            "refusing to downgrade 0015: DG generation (kWh) records or kWh-derived calculations exist; "
            "they are source data and frozen provenance and cannot be orphaned"
        )
    op.drop_column("calculation_results", "derivation", schema="sustainability")
    connection.execute(sa.text("delete from sustainability.metric_definitions where code = 'dg_generation_kwh'"))
    op.drop_table("calculation_parameters", schema="sustainability")
