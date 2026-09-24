"""Add the historical data layer and release classification metadata.

Revision ID: 0011_historical_data_layer
Revises: 0010_publication_1_3

Historical institutional records are stored in a dedicated ``history``
schema with their true granularity and full provenance; they are never
written into Manager submissions. ``publication.public_release_metadata``
classifies releases (official / test) and controls public visibility without
touching any frozen release payload or checksum.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011_historical_data_layer"
down_revision = "0010_publication_1_3"
branch_labels = None
depends_on = None

TEST_RELEASE_VERSIONS = (
    "sustainability-2026-09-v1",
    "sustainability-2026-09-v2",
    "sustainability-2026-09-v3",
)
TEST_RELEASE_REASON = "Development / publication workflow acceptance data — not official institutional historical data."

UUID = postgresql.UUID(as_uuid=True)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(value) for value in values)})"


def _timestamps() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)]


def upgrade() -> None:
    op.execute("create schema history")
    op.execute("revoke all on schema history from public")

    op.create_table(
        "import_batches",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("batch_name", sa.String(200), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_domain", sa.String(40), nullable=False),
        sa.Column("mapping_code", sa.String(100), nullable=False),
        sa.Column("mapping_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "source_sha256", "mapping_code", "mapping_version", name="uq_import_batches_source_mapping"
        ),
        sa.CheckConstraint(
            _in("status", ("STAGED", "RECONCILED", "VERIFIED", "REJECTED")), name="ck_import_batches_status_allowed"
        ),
        sa.CheckConstraint("length(source_sha256) = 64", name="ck_import_batches_sha256_length"),
        schema="history",
    )
    op.create_table(
        "source_rows",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("batch_id", UUID, sa.ForeignKey("history.import_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_source_rows_batch_row"),
        schema="history",
    )
    op.create_table(
        "periods",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("month", sa.SmallInteger()),
        sa.Column("granularity", sa.String(10), nullable=False),
        sa.Column("coverage_start", sa.Date(), nullable=False),
        sa.Column("coverage_end", sa.Date(), nullable=False),
        sa.Column("display_label", sa.String(80), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("granularity", "coverage_start", "coverage_end", name="uq_periods_granularity_coverage"),
        sa.CheckConstraint(
            _in("granularity", ("MONTHLY", "YTD", "ANNUAL", "STATIC")), name="ck_periods_granularity_allowed"
        ),
        sa.CheckConstraint("coverage_end >= coverage_start", name="ck_periods_coverage_ordered"),
        sa.CheckConstraint(
            "(granularity = 'MONTHLY' and month between 1 and 12) or (granularity <> 'MONTHLY' and month is null)",
            name="ck_periods_month_only_for_monthly",
        ),
        schema="history",
    )
    op.create_table(
        "metric_values",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("period_id", UUID, sa.ForeignKey("history.periods.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("domain", sa.String(40), nullable=False),
        sa.Column("metric_code", sa.String(120), nullable=False),
        sa.Column("value_numeric", sa.Numeric(20, 6), nullable=False),
        sa.Column("value_qualifier", sa.String(20), nullable=False, server_default="EXACT"),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column(
            "source_batch_id", UUID, sa.ForeignKey("history.import_batches.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("source_row_id", UUID, sa.ForeignKey("history.source_rows.id", ondelete="RESTRICT")),
        sa.Column("source_column", sa.String(200), nullable=False),
        sa.Column("verification_status", sa.String(20), nullable=False),
        sa.Column("authority_status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_id", UUID, sa.ForeignKey("history.metric_values.id", ondelete="RESTRICT")),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint(
            "period_id",
            "domain",
            "metric_code",
            "source_batch_id",
            "version",
            name="uq_metric_values_period_metric_batch_version",
        ),
        sa.CheckConstraint(
            _in("verification_status", ("UNVERIFIED", "VERIFIED", "REJECTED", "CONFLICT")),
            name="ck_metric_values_verification_allowed",
        ),
        sa.CheckConstraint(
            _in("authority_status", ("SOURCE_REPORTED", "NORMALIZED", "AUTHORITATIVE")),
            name="ck_metric_values_authority_allowed",
        ),
        sa.CheckConstraint(
            _in("value_qualifier", ("EXACT", "AT_LEAST", "APPROXIMATE")), name="ck_metric_values_qualifier_allowed"
        ),
        sa.CheckConstraint("version >= 1", name="ck_metric_values_version_positive"),
        sa.CheckConstraint(
            "authority_status <> 'AUTHORITATIVE' or verification_status = 'VERIFIED'",
            name="ck_metric_values_authoritative_requires_verified",
        ),
        schema="history",
    )
    op.create_index(
        "ix_metric_values_lookup", "metric_values", ["period_id", "domain", "metric_code"], schema="history"
    )
    op.create_table(
        "calculation_results",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("period_id", UUID, sa.ForeignKey("history.periods.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("calculation_code", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("unavailable_reason", sa.String(160)),
        sa.Column("result_value", sa.Numeric(24, 12)),
        sa.Column("result_unit", sa.String(40), nullable=False),
        sa.Column("methodology_version", sa.String(80), nullable=False),
        sa.Column("factor_code", sa.String(40)),
        sa.Column("factor_value", sa.Numeric(20, 10)),
        sa.Column("factor_unit", sa.String(40)),
        sa.Column("factor_set_id", UUID, sa.ForeignKey("sustainability.emission_factor_sets.id", ondelete="RESTRICT")),
        sa.Column("factor_set_version", sa.String(100)),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.UniqueConstraint(
            "period_id", "calculation_code", "input_hash", name="uq_calculation_results_period_calculation_input"
        ),
        sa.CheckConstraint("status in ('available', 'unavailable')", name="ck_calculation_results_status_allowed"),
        sa.CheckConstraint(
            "(status = 'available' and result_value is not null) or (status = 'unavailable' and result_value is null)",
            name="ck_calculation_results_value_matches_status",
        ),
        schema="history",
    )
    op.create_index(
        "uq_calculation_results_one_current",
        "calculation_results",
        ["period_id", "calculation_code"],
        unique=True,
        schema="history",
        postgresql_where=sa.text("is_current"),
    )
    op.create_table(
        "conflicts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("conflict_key", sa.String(300), nullable=False),
        sa.Column("conflict_type", sa.String(60), nullable=False),
        sa.Column("domain", sa.String(40), nullable=False),
        sa.Column("metric_code", sa.String(120), nullable=False),
        sa.Column("period_id", UUID, sa.ForeignKey("history.periods.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "source_a_batch_id", UUID, sa.ForeignKey("history.import_batches.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("value_a", sa.Numeric(20, 6)),
        sa.Column("source_b_batch_id", UUID, sa.ForeignKey("history.import_batches.id", ondelete="RESTRICT")),
        sa.Column("value_b", sa.Numeric(20, 6)),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("resolution_status", sa.String(20), nullable=False, server_default="UNRESOLVED"),
        sa.Column("chosen_batch_id", UUID, sa.ForeignKey("history.import_batches.id", ondelete="RESTRICT")),
        sa.Column("resolution_reason", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("conflict_key", name="uq_conflicts_conflict_key"),
        sa.CheckConstraint(
            _in("resolution_status", ("UNRESOLVED", "RESOLVED", "REJECTED_SOURCE")),
            name="ck_conflicts_resolution_allowed",
        ),
        sa.CheckConstraint(
            "resolution_status = 'UNRESOLVED' or (resolution_reason is not null and resolved_at is not null)",
            name="ck_conflicts_resolution_documented",
        ),
        schema="history",
    )

    # Provenance is append-only. Corrections insert a new version that
    # supersedes the old row; nothing verified is ever silently rewritten.
    op.execute(
        """
        create function history.forbid_change() returns trigger language plpgsql as $$
        begin
          raise exception 'history.% is append-only; insert a superseding version instead', tg_table_name
            using errcode = 'P0001';
        end $$;
        create trigger metric_values_append_only before update or delete on history.metric_values
          for each row execute function history.forbid_change();
        create trigger source_rows_append_only before update or delete on history.source_rows
          for each row execute function history.forbid_change();
        create trigger periods_append_only before update or delete on history.periods
          for each row execute function history.forbid_change();

        create function history.guard_batch_update() returns trigger language plpgsql as $$
        begin
          if tg_op = 'DELETE' then
            raise exception 'history.import_batches rows cannot be deleted' using errcode = 'P0001';
          end if;
          if (new.id, new.batch_name, new.original_filename, new.source_reference, new.source_sha256,
              new.source_domain, new.mapping_code, new.mapping_version, new.imported_at, new.created_at)
             is distinct from
             (old.id, old.batch_name, old.original_filename, old.source_reference, old.source_sha256,
              old.source_domain, old.mapping_code, old.mapping_version, old.imported_at, old.created_at) then
            raise exception 'history.import_batches provenance is immutable' using errcode = 'P0001';
          end if;
          return new;
        end $$;
        create trigger import_batches_guard before update or delete on history.import_batches
          for each row execute function history.guard_batch_update();

        create function history.guard_calculation_update() returns trigger language plpgsql as $$
        begin
          if tg_op = 'DELETE' then
            raise exception 'history.calculation_results rows cannot be deleted' using errcode = 'P0001';
          end if;
          if not (old.is_current and not new.is_current)
             or (to_jsonb(new) - 'is_current') is distinct from (to_jsonb(old) - 'is_current') then
            raise exception 'history.calculation_results may only be retired (is_current true -> false)'
              using errcode = 'P0001';
          end if;
          return new;
        end $$;
        create trigger calculation_results_guard before update or delete on history.calculation_results
          for each row execute function history.guard_calculation_update();

        create function history.guard_conflict_update() returns trigger language plpgsql as $$
        begin
          if tg_op = 'DELETE' then
            raise exception 'history.conflicts rows cannot be deleted' using errcode = 'P0001';
          end if;
          if old.resolution_status <> 'UNRESOLVED' then
            raise exception 'a resolved conflict is final; record a new conflict instead' using errcode = 'P0001';
          end if;
          if (to_jsonb(new) - 'resolution_status' - 'chosen_batch_id' - 'resolution_reason' - 'resolved_at')
             is distinct from
             (to_jsonb(old) - 'resolution_status' - 'chosen_batch_id' - 'resolution_reason' - 'resolved_at') then
            raise exception 'only the resolution of a conflict may be recorded' using errcode = 'P0001';
          end if;
          return new;
        end $$;
        create trigger conflicts_guard before update or delete on history.conflicts
          for each row execute function history.guard_conflict_update();
        """
    )
    op.execute("revoke all on all tables in schema history from public")
    op.execute("revoke all on all functions in schema history from public")

    op.create_table(
        "public_release_metadata",
        sa.Column(
            "release_id",
            UUID,
            sa.ForeignKey("publication.public_releases.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("public_visible", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "classification in ('official', 'test')", name="ck_public_release_metadata_classification_allowed"
        ),
        sa.CheckConstraint(
            "classification = 'official' or public_visible = false", name="ck_public_release_metadata_test_never_public"
        ),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_public_release_metadata_reason_required"),
        schema="publication",
    )
    # The September 2026 releases were created to accept the publication
    # workflow. They stay intact (payload, checksum, status, audit) but are
    # classified as test data and removed from public visibility.
    op.execute(
        sa.text(
            "insert into publication.public_release_metadata (release_id, classification, public_visible, reason) "
            "select id, 'test', false, :reason from publication.public_releases where version = any(:versions)"
        ).bindparams(reason=TEST_RELEASE_REASON, versions=list(TEST_RELEASE_VERSIONS))
    )


def downgrade() -> None:
    connection = op.get_bind()
    imported = connection.execute(sa.text("select count(*) from history.import_batches")).scalar_one()
    if imported:
        raise RuntimeError("refusing to downgrade: historical import batches exist; export them before reverting 0011")
    op.drop_table("public_release_metadata", schema="publication")
    op.execute("drop schema history cascade")
