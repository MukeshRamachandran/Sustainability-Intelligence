"""make LPG weight the governed activity and public metric

Revision ID: 0007_lpg_kg_governance
Revises: 0006_emission_factor_governance
"""

from alembic import op

revision = "0007_lpg_kg_governance"
down_revision = "0006_emission_factor_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        update sustainability.metric_definitions
           set display_name = 'LPG consumption (kg)',
               accounting_classification = 'scope1_inventory',
               publication_class = 'public_aggregate',
               factor_code = 'LPG'
         where code = 'lpg_weight_kg';

        update sustainability.metric_definitions
           set display_name = 'LPG consumption (litres, deprecated)',
               required_for_complete = false,
               publication_class = 'admin_only',
               factor_code = null
         where code = 'lpg_consumption_litres';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        update sustainability.metric_definitions
           set display_name = 'LPG weight',
               accounting_classification = 'activity_only',
               publication_class = 'admin_only',
               factor_code = null
         where code = 'lpg_weight_kg';

        update sustainability.metric_definitions
           set display_name = 'LPG consumption',
               required_for_complete = true,
               publication_class = 'public_aggregate',
               factor_code = 'LPG'
         where code = 'lpg_consumption_litres';
        """
    )
