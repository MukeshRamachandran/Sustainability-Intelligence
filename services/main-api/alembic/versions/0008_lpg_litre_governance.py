"""make LPG litres the governed activity and public metric

Supersedes 0007_lpg_kg_governance, which had made lpg_weight_kg authoritative.
The institution has finalized the LPG methodology on a litre basis, so
lpg_consumption_litres becomes the governed activity and lpg_weight_kg reverts
to optional reference metadata.

Metadata only: no metric, no submission value and no historical calculation is
deleted. Existing frozen publication payloads are never rewritten.

Also places the LPG baseline factor into the migration-seeded DRAFT factor set
so an Admin can complete governance through Emission Factor Management. The
factor writes are idempotent and guarded to `status = 'draft'`: an ACTIVE or
RETIRED set is never touched.

Revision ID: 0008_lpg_litre_governance
Revises: 0007_lpg_kg_governance
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_lpg_litre_governance"
down_revision = "0007_lpg_kg_governance"
branch_labels = None
depends_on = None

DRAFT_SET_ID = "20000000-0000-0000-0000-000000000001"
LPG_FACTOR_ID = "21000000-0000-0000-0000-000000000004"
BASELINE_SOURCE = "Existing K-COSMOS institutional calculation baseline (pre-governance)"
LPG_BASELINE_VALUE = "1.5571"
BASELINE_NOTE = (
    "Initial governed factor set migrated from the existing K-COSMOS calculation baseline. "
    "Future factor changes are controlled through Emission Factor Management."
)
ORIGINAL_NOTE = (
    "Existing K-COSMOS values; institutional source confirmation is required before activation."
)

PROMOTE_LITRES = sa.text(
    """
    update sustainability.metric_definitions
       set display_name = 'LPG consumption (litres)',
           accounting_classification = 'scope1_inventory',
           publication_class = 'public_aggregate',
           factor_code = 'LPG',
           required_for_complete = true
     where code = 'lpg_consumption_litres'
    """
)

DEMOTE_KG = sa.text(
    """
    update sustainability.metric_definitions
       set display_name = 'LPG weight (kg, reference only)',
           accounting_classification = 'activity_only',
           publication_class = 'admin_only',
           factor_code = null,
           required_for_complete = false
     where code = 'lpg_weight_kg'
    """
)

# Idempotent and draft-only: inserts nothing if the set is not a draft or an
# LPG factor is already present.
SEED_LPG_FACTOR = sa.text(
    """
    insert into sustainability.emission_factors
           (id, factor_set_id, code, factor_value, activity_unit, result_unit, source_reference)
    select :factor_id, s.id, 'LPG', :factor_value, 'L', 'kgCO2e', :source
      from sustainability.emission_factor_sets s
     where s.id = :set_id
       and s.status = 'draft'
       and not exists (
             select 1 from sustainability.emission_factors f
              where f.factor_set_id = s.id and f.code = 'LPG'
           )
    """
)

STAMP_BASELINE_SOURCE = sa.text(
    """
    update sustainability.emission_factors f
       set source_reference = :source
      from sustainability.emission_factor_sets s
     where f.factor_set_id = s.id
       and s.id = :set_id
       and s.status = 'draft'
       and f.source_reference is null
    """
)

# Draft-only. effective_from is deliberately left unset: the Admin chooses the
# institutional adoption date in Emission Factor Management before activation.
SET_BASELINE_NOTE = sa.text(
    """
    update sustainability.emission_factor_sets
       set source_note = :note
     where id = :set_id
       and status = 'draft'
    """
)

RESTORE_KG = sa.text(
    """
    update sustainability.metric_definitions
       set display_name = 'LPG consumption (kg)',
           accounting_classification = 'scope1_inventory',
           publication_class = 'public_aggregate',
           factor_code = 'LPG',
           required_for_complete = true
     where code = 'lpg_weight_kg'
    """
)

DEPRECATE_LITRES = sa.text(
    """
    update sustainability.metric_definitions
       set display_name = 'LPG consumption (litres, deprecated)',
           accounting_classification = 'scope1_inventory',
           publication_class = 'admin_only',
           factor_code = null,
           required_for_complete = false
     where code = 'lpg_consumption_litres'
    """
)

CLEAR_BASELINE_SOURCE = sa.text(
    """
    update sustainability.emission_factors f
       set source_reference = null
      from sustainability.emission_factor_sets s
     where f.factor_set_id = s.id
       and s.id = :set_id
       and s.status = 'draft'
       and f.source_reference = :source
       and f.code <> 'LPG'
    """
)

REMOVE_LPG_FACTOR = sa.text(
    """
    delete from sustainability.emission_factors f
     using sustainability.emission_factor_sets s
     where f.factor_set_id = s.id
       and f.id = :factor_id
       and s.status = 'draft'
    """
)


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(PROMOTE_LITRES)
    connection.execute(DEMOTE_KG)
    connection.execute(
        SEED_LPG_FACTOR,
        {
            "factor_id": LPG_FACTOR_ID,
            "factor_value": LPG_BASELINE_VALUE,
            "source": BASELINE_SOURCE,
            "set_id": DRAFT_SET_ID,
        },
    )
    connection.execute(STAMP_BASELINE_SOURCE, {"source": BASELINE_SOURCE, "set_id": DRAFT_SET_ID})
    connection.execute(SET_BASELINE_NOTE, {"note": BASELINE_NOTE, "set_id": DRAFT_SET_ID})


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(DEPRECATE_LITRES)
    connection.execute(RESTORE_KG)
    connection.execute(CLEAR_BASELINE_SOURCE, {"source": BASELINE_SOURCE, "set_id": DRAFT_SET_ID})
    connection.execute(REMOVE_LPG_FACTOR, {"factor_id": LPG_FACTOR_ID})
    connection.execute(SET_BASELINE_NOTE, {"note": ORIGINAL_NOTE, "set_id": DRAFT_SET_ID})
