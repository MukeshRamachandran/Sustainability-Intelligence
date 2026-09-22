"""Add outreach domain, programme records, review snapshots, and release period.

Revision ID: 0002_outreach_vertical_slice
Revises: 0001_business_schema
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_outreach_vertical_slice"
down_revision: str | None = "0001_business_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("alter type sustainability.operational_domain add value if not exists 'outreach'")
    op.execute("alter table sustainability.review_actions add column snapshot jsonb")
    op.execute(
        "alter table publication.public_releases add column reporting_period_id uuid "
        "references sustainability.reporting_periods(id) on delete restrict"
    )
    op.execute(
        """
        create table sustainability.outreach_programmes (
          id uuid primary key default gen_random_uuid(),
          submission_id uuid not null references sustainability.submissions(id) on delete cascade,
          programme_name varchar(300) not null,
          programme_date date not null,
          theme varchar(80) not null,
          other_theme varchar(200),
          partner_organisation varchar(300),
          programme_location varchar(300),
          programme_description text,
          school_students integer,
          college_students integer,
          farmers_agriculture integer,
          industrial_experts integer,
          researchers_experts integer,
          government_participants integer,
          participant_total integer generated always as (
            coalesce(school_students,0) + coalesce(college_students,0)
            + coalesce(farmers_agriculture,0) + coalesce(industrial_experts,0)
            + coalesce(researchers_experts,0) + coalesce(government_participants,0)
          ) stored,
          male_participants integer,
          female_participants integer,
          other_not_disclosed_participants integer,
          saplings_planted integer,
          experts_involved integer,
          volunteers_engaged integer,
          volunteer_hours numeric(12,2),
          remarks text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint outreach_programme_name_required check(length(btrim(programme_name)) > 0),
          constraint outreach_theme_allowed check(theme in (
            'climate_smart_agriculture','climate_change','afforestation','water_conservation',
            'waste_management','biodiversity_conservation','hwcc','livelihood_development',
            'campus_sustainability','other'
          )),
          constraint outreach_other_theme_required check(
            theme <> 'other' or (other_theme is not null and length(btrim(other_theme)) > 0)
          ),
          constraint outreach_counts_nonnegative check(
            coalesce(school_students,0) >= 0 and coalesce(college_students,0) >= 0
            and coalesce(farmers_agriculture,0) >= 0 and coalesce(industrial_experts,0) >= 0
            and coalesce(researchers_experts,0) >= 0 and coalesce(government_participants,0) >= 0
            and coalesce(male_participants,0) >= 0 and coalesce(female_participants,0) >= 0
            and coalesce(other_not_disclosed_participants,0) >= 0
            and coalesce(saplings_planted,0) >= 0 and coalesce(experts_involved,0) >= 0
            and coalesce(volunteers_engaged,0) >= 0 and coalesce(volunteer_hours,0) >= 0
          ),
          constraint outreach_gender_not_above_total check(
            coalesce(male_participants,0) + coalesce(female_participants,0)
            + coalesce(other_not_disclosed_participants,0) <= participant_total
          )
        );
        create index ix_outreach_programmes_submission
          on sustainability.outreach_programmes(submission_id);

        create or replace function sustainability.validate_outreach_programme()
        returns trigger language plpgsql as $$
        declare
          parent_domain sustainability.operational_domain;
          parent_status sustainability.submission_status;
          start_date date;
          end_date date;
        begin
          select s.domain,s.status,p.period_start,p.period_end
            into parent_domain,parent_status,start_date,end_date
          from sustainability.submissions s
          join sustainability.reporting_periods p on p.id=s.reporting_period_id
          where s.id=coalesce(new.submission_id,old.submission_id);

          if parent_domain is distinct from 'outreach' then
            raise exception 'outreach programme requires an outreach submission' using errcode='23514';
          end if;
          if parent_status not in ('draft','correction_requested') then
            raise exception 'outreach programme is frozen in this submission state' using errcode='23514';
          end if;
          if tg_op <> 'DELETE' and (new.programme_date < start_date or new.programme_date > end_date) then
            raise exception 'programme date must be inside reporting period' using errcode='23514';
          end if;
          if tg_op = 'DELETE' then return old; end if;
          new.updated_at = now();
          return new;
        end $$;

        create trigger outreach_programme_guard
          before insert or update or delete on sustainability.outreach_programmes
          for each row execute function sustainability.validate_outreach_programme();
        """
    )


def downgrade() -> None:
    op.execute("drop trigger if exists outreach_programme_guard on sustainability.outreach_programmes")
    op.execute("drop function if exists sustainability.validate_outreach_programme()")
    op.execute("drop table if exists sustainability.outreach_programmes")
    op.execute("alter table publication.public_releases drop column if exists reporting_period_id")
    op.execute("alter table sustainability.review_actions drop column if exists snapshot")
    # PostgreSQL enum values are intentionally retained; removing a live enum value
    # requires destructive rewriting of every dependent table.
