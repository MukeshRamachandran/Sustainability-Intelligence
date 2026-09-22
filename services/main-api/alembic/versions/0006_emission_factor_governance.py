"""govern emission factors and snapshot calculations

Revision ID: 0006_emission_factor_governance
Revises: 0005_evidence_committed_at
"""

from alembic import op

revision = "0006_emission_factor_governance"
down_revision = "0005_evidence_committed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        drop index if exists sustainability.uq_one_active_factor_set;

        alter table sustainability.emission_factor_sets
          add column effective_from date,
          add column created_by uuid references identity.users(id) on delete restrict,
          add column activated_by uuid references identity.users(id) on delete restrict,
          add column updated_at timestamptz not null default now(),
          add column row_version integer not null default 1,
          add constraint factor_set_row_version_positive check (row_version > 0);

        create unique index uq_active_factor_set_effective_from
          on sustainability.emission_factor_sets(effective_from)
          where status = 'active';

        alter table sustainability.emission_factors
          add column source_reference text,
          add column source_url text,
          add column notes text;

        update sustainability.emission_factors set code = upper(code);
        update sustainability.emission_factors set code = 'GRID_ELECTRICITY' where code = 'GRID';
        update sustainability.metric_definitions set factor_code = upper(factor_code)
          where factor_code is not null;
        update sustainability.metric_definitions set factor_code = 'GRID_ELECTRICITY'
          where factor_code = 'GRID';

        alter table sustainability.calculation_results
          drop constraint uq_calculation_submission_metric,
          alter column metric_code drop not null,
          alter column activity_value drop not null,
          alter column activity_unit drop not null,
          alter column factor_id drop not null,
          alter column factor_value drop not null,
          alter column result_kgco2e drop not null,
          add column submission_revision integer not null default 1,
          add column calculation_code varchar(100) not null,
          add column calculation_status varchar(20) not null default 'available',
          add column unavailable_reason varchar(100),
          add column factor_set_id uuid references sustainability.emission_factor_sets(id) on delete restrict,
          add column factor_set_version varchar(100),
          add column factor_code varchar(80),
          add column factor_unit varchar(80),
          add column result_value numeric(20,6),
          add column result_unit varchar(40);

        alter table sustainability.calculation_results
          add constraint calculation_submission_revision_positive check (submission_revision > 0),
          add constraint uq_calculation_submission_revision_code
            unique(submission_id, submission_revision, calculation_code);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        alter table sustainability.calculation_results
          drop constraint uq_calculation_submission_revision_code,
          drop constraint calculation_submission_revision_positive,
          drop column result_unit,
          drop column result_value,
          drop column factor_unit,
          drop column factor_code,
          drop column factor_set_version,
          drop column factor_set_id,
          drop column unavailable_reason,
          drop column calculation_status,
          drop column calculation_code,
          drop column submission_revision,
          alter column result_kgco2e set not null,
          alter column factor_value set not null,
          alter column factor_id set not null,
          alter column activity_unit set not null,
          alter column activity_value set not null,
          alter column metric_code set not null,
          add constraint uq_calculation_submission_metric unique(submission_id, metric_code);

        update sustainability.metric_definitions set factor_code = lower(factor_code)
          where factor_code is not null;
        update sustainability.metric_definitions set factor_code = 'grid' where factor_code = 'grid_electricity';
        update sustainability.emission_factors set code = lower(code);
        update sustainability.emission_factors set code = 'grid' where code = 'grid_electricity';

        alter table sustainability.emission_factors
          drop column notes,
          drop column source_url,
          drop column source_reference;
        drop index sustainability.uq_active_factor_set_effective_from;
        alter table sustainability.emission_factor_sets
          drop constraint factor_set_row_version_positive,
          drop column row_version,
          drop column updated_at,
          drop column activated_by,
          drop column created_by,
          drop column effective_from;
        create unique index uq_one_active_factor_set
          on sustainability.emission_factor_sets(status) where status = 'active';
        """
    )
