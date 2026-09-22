"""Add internal Outreach waste and biodiversity verification fields.

Revision ID: 0003_outreach_impact
Revises: 0002_outreach_vertical_slice
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_outreach_impact"
down_revision: str | None = "0002_outreach_vertical_slice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        alter table sustainability.outreach_programmes
          add column waste_collected_kg numeric(12,2),
          add column species_identified_count integer,
          add column species_details jsonb,
          add column species_verification_notes text,
          add constraint outreach_internal_impact_nonnegative check (
            coalesce(waste_collected_kg, 0) >= 0
            and coalesce(species_identified_count, 0) >= 0
          ),
          add constraint outreach_species_details_array check (
            species_details is null or jsonb_typeof(species_details) = 'array'
          );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        alter table sustainability.outreach_programmes
          drop constraint if exists outreach_species_details_array,
          drop constraint if exists outreach_internal_impact_nonnegative,
          drop column if exists species_verification_notes,
          drop column if exists species_details,
          drop column if exists species_identified_count,
          drop column if exists waste_collected_kg;
        """
    )
