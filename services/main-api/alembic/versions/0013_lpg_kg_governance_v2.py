"""make LPG weight (kg) the governed activity under a new LPG_KG factor

Project-owner methodology correction (2026-09-30): the historical LPG values
that 0008_lpg_litre_governance treated as litres are kilograms. LPG activity is
``lpg_weight_kg`` (kg) and its factor is the new code ``LPG_KG``
(2.98 kgCO2e/kg). Numbers are never converted; only the unit interpretation
changes.

Metric catalog:
  * ``lpg_weight_kg``          governed, required, public Scope-1 activity -> LPG_KG
  * ``lpg_consumption_litres`` deprecated: inactive, admin-only, no factor.
                               Kept (not dropped) so frozen litre-era
                               submissions and calculations stay readable.
  * ``lpg_cylinder_count``     optional reference only.

Factor governance (an ACTIVE set is immutable, and only one ACTIVE set may hold
an effective date):
  * The governing ACTIVE set is copied into a NEW versioned ACTIVE set with the
    same effective date. Petrol/Diesel/Grid are copied verbatim, the litre LPG
    factor is left out and LPG_KG is added. The old set is retired; none of its
    factor rows change, so every frozen litre-era calculation that references
    it stays reproducible.
  * On a fresh install (the 0008-seeded set is still a DRAFT), LPG_KG replaces
    the draft-only litre LPG factor in that draft.

Revision ID: 0013_lpg_kg_governance_v2
Revises: 0012_environment_readings
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "0013_lpg_kg_governance_v2"
down_revision = "0012_environment_readings"
branch_labels = None
depends_on = None

BASELINE_SET_ID = "20000000-0000-0000-0000-000000000001"
KG_SET_ID = "20000000-0000-0000-0000-000000000002"
KG_SET_VERSION = "kcosmos-factors-2025-v2-lpg-kg"
LPG_KG_FACTOR_ID = "21000000-0000-0000-0000-000000000005"
LPG_KG_VALUE = "2.98"
LPG_KG_SOURCE = (
    "Existing K-COSMOS institutional LPG kg calculation baseline supplied with the historical LPG source "
    "(project owner, 2026-09-30)"
)
LPG_KG_NOTE = (
    "Project owner confirmed on 2026-09-30 that LPG activity is weighed in kilograms. Not attributed to "
    "IPCC, DEFRA or the GHG Protocol; it is the institution's own supplied baseline."
)
KG_SET_NOTE = (
    "LPG kg methodology correction (0013_lpg_kg_governance_v2). Supersedes {old} with the same effective "
    "date: Petrol, Diesel and Grid factors copied unchanged; LPG is governed as LPG_KG = 2.98 kgCO2e/kg "
    "against lpg_weight_kg. The litre LPG factor (kgCO2e/L) is retired with {old} and never applied to kg."
)

PROMOTE_KG = sa.text(
    """
    update sustainability.metric_definitions
       set display_name = 'LPG consumption (kg)',
           accounting_classification = 'scope1_inventory',
           publication_class = 'public_aggregate',
           factor_code = 'LPG_KG',
           required_for_complete = true,
           manager_editable = true,
           is_active = true
     where code = 'lpg_weight_kg'
    """
)
DEPRECATE_LITRES = sa.text(
    """
    update sustainability.metric_definitions
       set display_name = 'LPG consumption (litres, deprecated - legacy audit only)',
           accounting_classification = 'activity_only',
           publication_class = 'admin_only',
           factor_code = null,
           required_for_complete = false,
           is_active = false
     where code = 'lpg_consumption_litres'
    """
)
CYLINDERS_OPTIONAL = sa.text(
    """
    update sustainability.metric_definitions
       set display_name = 'LPG cylinders (reference)',
           required_for_complete = false
     where code = 'lpg_cylinder_count'
    """
)

GOVERNING_ACTIVE_SET = sa.text(
    """
    select id, version, effective_from
      from sustainability.emission_factor_sets
     where status = 'active' and effective_from is not null
     order by effective_from desc, id
     limit 1
    """
)


def _audit(connection: sa.Connection, event: str, target: str, metadata: dict[str, object]) -> None:
    connection.execute(
        sa.text(
            """
            insert into audit.audit_logs
                   (id, actor_user_id, actor_type, event_type, target_type, target_reference, outcome, safe_metadata)
            values (gen_random_uuid(), null, 'system', :event, 'emission_factor_set', :target, 'succeeded',
                    cast(:metadata as jsonb))
            """
        ),
        {"event": event, "target": target, "metadata": json.dumps(metadata)},
    )


def _supersede_active_set(connection: sa.Connection) -> None:
    governing = connection.execute(GOVERNING_ACTIVE_SET).mappings().first()
    if governing is None or str(governing["id"]) == KG_SET_ID:
        return
    has_kg = connection.execute(
        sa.text("select 1 from sustainability.emission_factors where factor_set_id = :id and code = 'LPG_KG'"),
        {"id": governing["id"]},
    ).first()
    if has_kg:
        return
    # Retire first: only one ACTIVE set may hold an effective date.
    connection.execute(
        sa.text(
            """
            update sustainability.emission_factor_sets
               set status = 'retired', updated_at = now(), row_version = row_version + 1
             where id = :id and status = 'active'
            """
        ),
        {"id": governing["id"]},
    )
    connection.execute(
        sa.text(
            """
            insert into sustainability.emission_factor_sets
                   (id, version, status, source_note, activated_at, effective_from)
            values (:id, :version, 'active', :note, now(), :effective_from)
            """
        ),
        {
            "id": KG_SET_ID,
            "version": KG_SET_VERSION,
            "note": KG_SET_NOTE.format(old=governing["version"]),
            "effective_from": governing["effective_from"],
        },
    )
    connection.execute(
        sa.text(
            """
            insert into sustainability.emission_factors
                   (id, factor_set_id, code, factor_value, activity_unit, result_unit,
                    source_reference, source_url, notes)
            select gen_random_uuid(), :new_id, code, factor_value, activity_unit, result_unit,
                   source_reference, source_url, notes
              from sustainability.emission_factors
             where factor_set_id = :old_id and code <> 'LPG'
            """
        ),
        {"new_id": KG_SET_ID, "old_id": governing["id"]},
    )
    _insert_lpg_kg(connection, KG_SET_ID)
    _audit(
        connection,
        "emission_factor_set.lpg_kg_methodology_migrated",
        KG_SET_ID,
        {
            "migration": revision,
            "new_version": KG_SET_VERSION,
            "retired_version": governing["version"],
            "effective_from": str(governing["effective_from"]),
            "lpg_factor": {"code": "LPG_KG", "value": LPG_KG_VALUE, "unit": "kgCO2e/kg"},
            "approved_by": "Project owner",
            "approved_at": "2026-09-30",
        },
    )


def _insert_lpg_kg(connection: sa.Connection, set_id: str) -> None:
    connection.execute(
        sa.text(
            """
            insert into sustainability.emission_factors
                   (id, factor_set_id, code, factor_value, activity_unit, result_unit, source_reference, notes)
            values (:id, :set_id, 'LPG_KG', :value, 'kg', 'kgCO2e', :source, :notes)
            """
        ),
        {
            "id": LPG_KG_FACTOR_ID,
            "set_id": set_id,
            "value": LPG_KG_VALUE,
            "source": LPG_KG_SOURCE,
            "notes": LPG_KG_NOTE,
        },
    )


def _replace_draft_litre_factor(connection: sa.Connection) -> None:
    """Fresh install: the 0008-seeded baseline set is still a DRAFT."""
    draft = connection.execute(
        sa.text("select 1 from sustainability.emission_factor_sets where id = :id and status = 'draft'"),
        {"id": BASELINE_SET_ID},
    ).first()
    if draft is None:
        return
    connection.execute(
        sa.text(
            """
            delete from sustainability.emission_factors f
             using sustainability.emission_factor_sets s
             where f.factor_set_id = s.id and s.id = :id and s.status = 'draft' and f.code = 'LPG'
            """
        ),
        {"id": BASELINE_SET_ID},
    )
    exists = connection.execute(
        sa.text("select 1 from sustainability.emission_factors where factor_set_id = :id and code = 'LPG_KG'"),
        {"id": BASELINE_SET_ID},
    ).first()
    if exists is None:
        _insert_lpg_kg(connection, BASELINE_SET_ID)


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(PROMOTE_KG)
    connection.execute(DEPRECATE_LITRES)
    connection.execute(CYLINDERS_OPTIONAL)
    _supersede_active_set(connection)
    _replace_draft_litre_factor(connection)


def downgrade() -> None:
    connection = op.get_bind()
    referenced = connection.execute(
        sa.text(
            """
            select (select count(*) from sustainability.calculation_results
                     where factor_set_id = :kg_set or factor_code = 'LPG_KG')
                 + (select count(*) from history.calculation_results
                     where factor_set_id = :kg_set or factor_code = 'LPG_KG')
            """
        ),
        {"kg_set": KG_SET_ID},
    ).scalar_one()
    if referenced:
        raise RuntimeError(
            "refusing to downgrade 0013: calculations reference the LPG_KG factor or its factor set; "
            "they are frozen provenance and cannot be orphaned"
        )
    retired = connection.execute(
        sa.text(
            """
            select s.id from sustainability.emission_factor_sets s
             where s.status = 'retired'
               and s.effective_from = (select effective_from from sustainability.emission_factor_sets
                                        where id = :kg_set)
             order by s.updated_at desc
             limit 1
            """
        ),
        {"kg_set": KG_SET_ID},
    ).scalar()
    connection.execute(
        sa.text("delete from sustainability.emission_factors where factor_set_id = :id"), {"id": KG_SET_ID}
    )
    connection.execute(sa.text("delete from sustainability.emission_factor_sets where id = :id"), {"id": KG_SET_ID})
    if retired is not None:
        connection.execute(
            sa.text(
                """
                update sustainability.emission_factor_sets
                   set status = 'active', updated_at = now(), row_version = row_version + 1
                 where id = :id
                """
            ),
            {"id": retired},
        )
    connection.execute(
        sa.text(
            """
            delete from sustainability.emission_factors f
             using sustainability.emission_factor_sets s
             where f.factor_set_id = s.id and s.status = 'draft' and f.code = 'LPG_KG'
            """
        )
    )
    # Restore the 0008 draft baseline litre factor if the draft set still exists.
    connection.execute(
        sa.text(
            """
            insert into sustainability.emission_factors
                   (id, factor_set_id, code, factor_value, activity_unit, result_unit, source_reference)
            select '21000000-0000-0000-0000-000000000004', s.id, 'LPG', 1.5571, 'L', 'kgCO2e',
                   'Existing K-COSMOS institutional calculation baseline (pre-governance)'
              from sustainability.emission_factor_sets s
             where s.id = :id and s.status = 'draft'
               and not exists (select 1 from sustainability.emission_factors f
                                where f.factor_set_id = s.id and f.code = 'LPG')
            """
        ),
        {"id": BASELINE_SET_ID},
    )
    for statement in (
        """
        update sustainability.metric_definitions
           set display_name = 'LPG consumption (litres)', accounting_classification = 'scope1_inventory',
               publication_class = 'public_aggregate', factor_code = 'LPG', required_for_complete = true,
               is_active = true
         where code = 'lpg_consumption_litres'
        """,
        """
        update sustainability.metric_definitions
           set display_name = 'LPG weight (kg, reference only)', accounting_classification = 'activity_only',
               publication_class = 'admin_only', factor_code = null, required_for_complete = false
         where code = 'lpg_weight_kg'
        """,
        """
        update sustainability.metric_definitions
           set display_name = 'LPG cylinders', required_for_complete = true
         where code = 'lpg_cylinder_count'
        """,
    ):
        connection.execute(sa.text(statement))
