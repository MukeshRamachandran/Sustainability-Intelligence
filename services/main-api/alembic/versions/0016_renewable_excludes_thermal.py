"""Manager workflow: renewable ELECTRICITY excludes the solar water heater

Project-owner decision (2026-10-01). The solar water heater is thermal energy
and is not renewable electricity. The governed electrical total is

    renewable_electricity_kwh = renewable_on_campus_kwh + renewable_procured_kwh

which the historical layer and the publication indicators already use. The
Manager-side trigger total ``renewable_total_kwh`` (on-campus + procured +
solar water heater) mixed thermal energy into that figure, so it is retired
for new work:

  * ``refresh_calculated_totals`` no longer writes ``renewable_total_kwh``.
    The grid, water and waste branches are unchanged.
  * ``renewable_total_kwh`` is deprecated: inactive, admin-only, no factor,
    not required. The definition is kept (not dropped) so legacy submissions
    stay readable.
  * Display names state what each source value is. ``solar_water_heater_kwh``
    stays a separate, Manager-entered thermal value; no emission impact is
    calculated for it here.

No submission value is inserted, updated or deleted: every existing
``renewable_total_kwh`` row keeps the value it was recorded with, and frozen
release payloads are untouched. The electrical indicators shown to the Manager
and the Admin are calculated by the backend from the source values
(app.services.publication.electricity_indicators), not stored by a trigger.

Revision ID: 0016_renewable_excludes_thermal
Revises: 0015_dg_kwh_methodology
"""

import sqlalchemy as sa

from alembic import op

revision = "0016_renewable_excludes_thermal"
down_revision = "0015_dg_kwh_methodology"
branch_labels = None
depends_on = None

_DISPATCHER = """
create or replace function sustainability.refresh_calculated_totals() returns trigger
language plpgsql set search_path=pg_catalog,sustainability as $$
declare sid uuid:=coalesce(new.submission_id,old.submission_id);
        code text:=coalesce(new.metric_code,old.metric_code);
begin
  if code=any(array['grid_ht_kwh','grid_commercial_kwh','grid_temporary_kwh']) then
    perform sustainability.recalculate_submission_total(sid,'grid_total_kwh',array['grid_ht_kwh','grid_commercial_kwh','grid_temporary_kwh']);
{renewable_branch}  elsif code=any(array['water_twad_kl','water_borewell_kl','water_private_kl']) then
    perform sustainability.recalculate_submission_total(sid,'water_consumed_kl',array['water_twad_kl','water_borewell_kl','water_private_kl']);
  elsif code='wet_waste_generated_kg' then
    perform sustainability.recalculate_waste_totals(sid);
  end if;
  return coalesce(new,old);
end $$;
"""
_LEGACY_RENEWABLE_BRANCH = (
    "  elsif code=any(array['renewable_on_campus_kwh','renewable_procured_kwh','solar_water_heater_kwh']) then\n"
    "    perform sustainability.recalculate_submission_total(sid,'renewable_total_kwh',"
    "array['renewable_on_campus_kwh','renewable_procured_kwh','solar_water_heater_kwh']);\n"
)

_METADATA = (
    # (code, upgrade values, downgrade values)
    (
        "renewable_total_kwh",
        {
            "display_name": "Total renewable incl. solar water heater (deprecated - legacy audit only)",
            "classification": "activity_only",
            "publication": "admin_only",
            "factor": None,
            "required": False,
            "active": False,
        },
        {
            "display_name": "Total renewable energy",
            "classification": "avoided_impact",
            "publication": "public_aggregate",
            "factor": "GRID_ELECTRICITY",
            "required": True,
            "active": True,
        },
    ),
)
_DISPLAY_NAMES = (
    ("renewable_on_campus_kwh", "On-campus renewable electricity", "Renewable energy on campus"),
    ("renewable_procured_kwh", "Procured renewable electricity", "Procured renewable energy"),
    ("solar_water_heater_kwh", "Solar water heater (solar thermal, not electricity)", "Solar water heater equivalent"),
)


def _apply_metadata(connection: sa.Connection, index: int) -> None:
    for entry in _METADATA:
        values = entry[index]
        connection.execute(
            sa.text(
                """
                update sustainability.metric_definitions
                   set display_name = :display_name,
                       accounting_classification = cast(:classification as sustainability.accounting_classification),
                       publication_class = cast(:publication as sustainability.publication_class),
                       factor_code = :factor,
                       required_for_complete = :required,
                       is_active = :active
                 where code = :code
                """
            ),
            {"code": entry[0], **values},
        )
    for row in _DISPLAY_NAMES:
        connection.execute(
            sa.text("update sustainability.metric_definitions set display_name = :name where code = :code"),
            {"code": row[0], "name": row[index]},
        )


def upgrade() -> None:
    op.execute(_DISPATCHER.format(renewable_branch=""))
    _apply_metadata(op.get_bind(), 1)


def downgrade() -> None:
    # Restores the pre-0016 definition for future writes only. Totals that were
    # not written while 0016 was in force are not back-filled.
    _apply_metadata(op.get_bind(), 2)
    op.execute(_DISPATCHER.format(renewable_branch=_LEGACY_RENEWABLE_BRANCH))
