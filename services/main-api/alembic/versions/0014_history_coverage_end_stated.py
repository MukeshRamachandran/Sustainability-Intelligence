"""Record whether a historical value's source states its coverage end month.

Some institutional sources report a current-year total only as "<year> / to
date". Once the project owner confirms such a figure it is authoritative, but
its end month is still unknown. ``coverage_end_stated = false`` keeps that
fact on the value itself, so the public resolver labels it "<year> YTD" and
never presents the stored period's placeholder end month as real coverage.

Additive only: every existing row keeps ``true`` (its period coverage is the
source's stated coverage). No row is updated, and the append-only triggers are
untouched.

Revision ID: 0014_history_coverage_end_stated
Revises: 0013_lpg_kg_governance_v2
"""

import sqlalchemy as sa

from alembic import op

revision = "0014_history_coverage_end_stated"
down_revision = "0013_lpg_kg_governance_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "metric_values",
        sa.Column("coverage_end_stated", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema="history",
    )


def downgrade() -> None:
    connection = op.get_bind()
    unstated = connection.execute(
        sa.text("select count(*) from history.metric_values where not coverage_end_stated")
    ).scalar_one()
    if unstated:
        raise RuntimeError(
            "refusing to downgrade 0014: owner-confirmed values with an unstated coverage end exist; "
            "dropping the column would erase that provenance"
        )
    op.drop_column("metric_values", "coverage_end_stated", schema="history")
