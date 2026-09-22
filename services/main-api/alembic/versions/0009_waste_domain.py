"""add waste as the sixth governed operational domain

Adds the `waste` operational domain, its three metric definitions, the
controlled waste catalog (categories and materials) and the normalized
per-submission dry-waste item table.

Waste is an activity/inventory domain only: no emission factor, no factor code
and no GHG methodology is introduced here.

Non-destructive. The downgrade removes only what this migration created, and
refuses to run while waste submissions still exist so no operational record is
ever silently destroyed.

Revision ID: 0009_waste_domain
Revises: 0008_lpg_litre_governance
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_waste_domain"
down_revision = "0008_lpg_litre_governance"
branch_labels = None
depends_on = None

# (code, display_name, sort_order)
CATEGORIES = (
    ("PAPER_CARDBOARD", "Paper & Cardboard", 10),
    ("PLASTIC", "Plastic", 20),
    ("METAL", "Metal", 30),
    ("ORGANIC_BIOMASS", "Organic / Biomass", 40),
    ("E_WASTE", "E-Waste", 50),
    ("RUBBER", "Rubber", 60),
    ("OTHER_MIXED", "Other / Mixed", 70),
)

# (code, display_name, category_code, sort_order) - institutional labels kept verbatim.
MATERIALS = (
    ("COLOUR_PAPER", "Colour Paper", "PAPER_CARDBOARD", 10),
    ("WHITE_PAPER", "White Paper", "PAPER_CARDBOARD", 20),
    ("CARDBOARD", "Cardboard", "PAPER_CARDBOARD", 30),
    ("NEWS_PAPER", "News Paper", "PAPER_CARDBOARD", 40),
    ("PP_CARDBOARDS", "PP Cardboards", "PLASTIC", 50),
    ("MIXED_PLASTICS", "Plastic (Mixed Plastics)", "PLASTIC", 60),
    ("PVC_PIPE", "PVC Pipe", "PLASTIC", 70),
    ("BLACK_PLASTIC_PP", "Black Plastic (PP)", "PLASTIC", 80),
    ("PET", "PET", "PLASTIC", 90),
    ("HDPE", "HDPE", "PLASTIC", 100),
    ("LDPE", "LDPE", "PLASTIC", 110),
    ("IRON", "Iron", "METAL", 120),
    ("STAINLESS_STEEL", "Stainless Steel", "METAL", 130),
    ("ALUMINIUM", "Aluminium", "METAL", 140),
    ("COCONUT_SHELL", "Coconut Shell", "ORGANIC_BIOMASS", 150),
    ("E_WASTE", "E-WASTE", "E_WASTE", 160),
    ("TYRE", "Tyre", "RUBBER", 170),
    ("LITE_WEIGHT", "Lite Weight", "OTHER_MIXED", 180),
    ("UNCLASSIFIED", "Unclassified", "OTHER_MIXED", 190),
)

# (code, display_name, classification, unit, required, manager_editable,
#  calculation_method, publication_class, display_order)
METRICS = (
    (
        "wet_waste_generated_kg", "Wet Waste Generated", "activity_only", "kg",
        True, True, None, "public_aggregate", 10,
    ),
    (
        "dry_waste_generated_kg", "Dry Waste Generated", "activity_only", "kg",
        False, False, "sum of waste_submission_items.quantity_kg", "public_aggregate", 20,
    ),
    (
        "total_waste_generated_kg", "Total Waste Generated", "activity_only", "kg",
        False, False, "wet_waste_generated_kg + dry_waste_generated_kg", "public_aggregate", 30,
    ),
)


def upgrade() -> None:
    # PostgreSQL refuses to *use* a new enum label in the same transaction that
    # added it (UnsafeNewEnumValueUsage), so the ALTER TYPE is committed on its
    # own before any DML references 'waste'. IF NOT EXISTS keeps it idempotent.
    with op.get_context().autocommit_block():
        op.execute("alter type sustainability.operational_domain add value if not exists 'waste'")

    connection = op.get_bind()

    op.create_table(
        "waste_categories",
        sa.Column("code", sa.String(length=60), primary_key=True),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        schema="sustainability",
    )
    op.create_table(
        "waste_materials",
        sa.Column("code", sa.String(length=60), primary_key=True),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column(
            "category_code",
            sa.String(length=60),
            sa.ForeignKey("sustainability.waste_categories.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        schema="sustainability",
    )
    op.create_index(
        "ix_waste_materials_category", "waste_materials", ["category_code"], schema="sustainability"
    )

    op.create_table(
        "waste_submission_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "submission_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            # CASCADE matches submission_values: items are part of the submission,
            # never independently retained.
            sa.ForeignKey("sustainability.submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_code",
            sa.String(length=60),
            sa.ForeignKey("sustainability.waste_materials.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # One row per material per submission: PET 100 and PET 50 cannot coexist.
        sa.UniqueConstraint("submission_id", "material_code", name="uq_waste_item_submission_material"),
        sa.CheckConstraint("quantity_kg > 0", name="waste_item_quantity_positive"),
        schema="sustainability",
    )
    op.create_index(
        "ix_waste_items_submission", "waste_submission_items", ["submission_id"], schema="sustainability"
    )

    for code, display_name, sort_order in CATEGORIES:
        connection.execute(
            sa.text(
                "insert into sustainability.waste_categories(code, display_name, sort_order, is_active) "
                "values (:code, :display_name, :sort_order, true) on conflict (code) do nothing"
            ),
            {"code": code, "display_name": display_name, "sort_order": sort_order},
        )
    for code, display_name, category_code, sort_order in MATERIALS:
        connection.execute(
            sa.text(
                "insert into sustainability.waste_materials"
                "(code, display_name, category_code, sort_order, is_active) "
                "values (:code, :display_name, :category_code, :sort_order, true) "
                "on conflict (code) do nothing"
            ),
            {
                "code": code,
                "display_name": display_name,
                "category_code": category_code,
                "sort_order": sort_order,
            },
        )

    # Derived waste quantities follow the established calculated-metric
    # mechanism: a database trigger writes them, and submission_value_guard
    # rejects any direct write because manager_editable is false. The
    # application never inserts these rows, so a manager cannot forge them
    # even by bypassing the API.
    op.execute(
        """
        create function sustainability.recalculate_waste_totals(target_submission uuid)
        returns void language plpgsql set search_path=pg_catalog,sustainability as $$
        declare dry numeric(20,6); wet numeric(20,6); dry_unit text; total_unit text;
        begin
          select coalesce(sum(quantity_kg),0) into dry
            from sustainability.waste_submission_items where submission_id=target_submission;
          select coalesce(value,0) into wet from sustainability.submission_values
            where submission_id=target_submission and metric_code='wet_waste_generated_kg';
          wet := coalesce(wet,0);
          select canonical_unit into dry_unit from sustainability.metric_definitions
            where code='dry_waste_generated_kg';
          select canonical_unit into total_unit from sustainability.metric_definitions
            where code='total_waste_generated_kg';
          insert into sustainability.submission_values(submission_id,metric_code,value,canonical_unit)
            values(target_submission,'dry_waste_generated_kg',dry,dry_unit)
          on conflict(submission_id,metric_code) do update set value=excluded.value,updated_at=now();
          insert into sustainability.submission_values(submission_id,metric_code,value,canonical_unit)
            values(target_submission,'total_waste_generated_kg',wet+dry,total_unit)
          on conflict(submission_id,metric_code) do update set value=excluded.value,updated_at=now();
        end $$;

        create function sustainability.refresh_waste_totals() returns trigger
        language plpgsql set search_path=pg_catalog,sustainability as $$
        begin
          perform sustainability.recalculate_waste_totals(
            coalesce(new.submission_id, old.submission_id));
          return coalesce(new, old);
        end $$;

        create trigger waste_item_totals after insert or update or delete
          on sustainability.waste_submission_items for each row
          execute function sustainability.refresh_waste_totals();
        """
    )

    # Extend the existing calculated-total dispatcher with a waste branch. The
    # branch fires only on the wet metric, so the dry/total rows it writes do
    # not re-enter it.
    op.execute(
        """
        create or replace function sustainability.refresh_calculated_totals() returns trigger
        language plpgsql set search_path=pg_catalog,sustainability as $$
        declare sid uuid:=coalesce(new.submission_id,old.submission_id);
                code text:=coalesce(new.metric_code,old.metric_code);
        begin
          if code=any(array['grid_ht_kwh','grid_commercial_kwh','grid_temporary_kwh']) then
            perform sustainability.recalculate_submission_total(sid,'grid_total_kwh',array['grid_ht_kwh','grid_commercial_kwh','grid_temporary_kwh']);
          elsif code=any(array['renewable_on_campus_kwh','renewable_procured_kwh','solar_water_heater_kwh']) then
            perform sustainability.recalculate_submission_total(sid,'renewable_total_kwh',array['renewable_on_campus_kwh','renewable_procured_kwh','solar_water_heater_kwh']);
          elsif code=any(array['water_twad_kl','water_borewell_kl','water_private_kl']) then
            perform sustainability.recalculate_submission_total(sid,'water_consumed_kl',array['water_twad_kl','water_borewell_kl','water_private_kl']);
          elsif code='wet_waste_generated_kg' then
            perform sustainability.recalculate_waste_totals(sid);
          end if;
          return coalesce(new,old);
        end $$;
        """
    )

    for (
        code, display_name, classification, unit, required,
        manager_editable, calculation_method, publication_class, display_order,
    ) in METRICS:
        connection.execute(
            sa.text(
                "insert into sustainability.metric_definitions"
                "(code, display_name, operational_domain, accounting_classification, canonical_unit,"
                " min_value, max_value, required_for_complete, zero_allowed, manager_editable,"
                " calculation_method, publication_class, factor_code, display_order, is_active) "
                "values (:code, :display_name, 'waste', cast(:classification as "
                "sustainability.accounting_classification), :unit, 0, 100000000, :required, true,"
                " :manager_editable, :calculation_method,"
                " cast(:publication_class as sustainability.publication_class), null, :display_order, true) "
                "on conflict (code) do nothing"
            ),
            {
                "code": code,
                "display_name": display_name,
                "classification": classification,
                "unit": unit,
                "required": required,
                "manager_editable": manager_editable,
                "calculation_method": calculation_method,
                "publication_class": publication_class,
                "display_order": display_order,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    existing = connection.execute(
        sa.text("select count(*) from sustainability.submissions where domain = 'waste'")
    ).scalar()
    if existing:
        raise RuntimeError(
            f"refusing to downgrade: {existing} waste submission(s) exist. "
            "Remove or supersede them deliberately before reverting 0009."
        )

    # Restore the pre-waste dispatcher before the waste function it references
    # can be dropped.
    op.execute(
        """
        create or replace function sustainability.refresh_calculated_totals() returns trigger
        language plpgsql set search_path=pg_catalog,sustainability as $$
        declare sid uuid:=coalesce(new.submission_id,old.submission_id);
                code text:=coalesce(new.metric_code,old.metric_code);
        begin
          if code=any(array['grid_ht_kwh','grid_commercial_kwh','grid_temporary_kwh']) then
            perform sustainability.recalculate_submission_total(sid,'grid_total_kwh',array['grid_ht_kwh','grid_commercial_kwh','grid_temporary_kwh']);
          elsif code=any(array['renewable_on_campus_kwh','renewable_procured_kwh','solar_water_heater_kwh']) then
            perform sustainability.recalculate_submission_total(sid,'renewable_total_kwh',array['renewable_on_campus_kwh','renewable_procured_kwh','solar_water_heater_kwh']);
          elsif code=any(array['water_twad_kl','water_borewell_kl','water_private_kl']) then
            perform sustainability.recalculate_submission_total(sid,'water_consumed_kl',array['water_twad_kl','water_borewell_kl','water_private_kl']);
          end if;
          return coalesce(new,old);
        end $$;

        drop trigger if exists waste_item_totals on sustainability.waste_submission_items;
        drop function if exists sustainability.refresh_waste_totals();
        drop function if exists sustainability.recalculate_waste_totals(uuid);
        """
    )
    op.drop_index("ix_waste_items_submission", table_name="waste_submission_items", schema="sustainability")
    op.drop_table("waste_submission_items", schema="sustainability")
    op.drop_index("ix_waste_materials_category", table_name="waste_materials", schema="sustainability")
    op.drop_table("waste_materials", schema="sustainability")
    op.drop_table("waste_categories", schema="sustainability")
    connection.execute(
        sa.text(
            "delete from sustainability.metric_definitions where operational_domain = 'waste'"
        )
    )
    # The 'waste' enum label is intentionally left in place: PostgreSQL cannot
    # drop an enum value, and re-adding it on the next upgrade is idempotent.
