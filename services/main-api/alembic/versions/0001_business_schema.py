"""Create the K-COSMOS business schema and canonical reference data.

Revision ID: 0001_business_schema
Revises:
Create Date: 2026-09-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_business_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SCHEMA_SQL = r"""
create schema identity;
create schema sustainability;
create schema publication;
create schema audit;

create type sustainability.operational_domain as enum ('transport','energy','lpg','water');
create type sustainability.accounting_classification as enum
  ('scope1_inventory','scope2_inventory','avoided_impact','activity_only','renewable_reporting','water_reporting');
create type sustainability.publication_class as enum ('public_aggregate','admin_only','internal_verification');
create type sustainability.submission_status as enum
  ('draft','submitted','under_review','correction_requested','approved','superseded');
create type sustainability.review_action_type as enum
  ('submit','begin_review','request_correction','approve','supersede');
create type sustainability.factor_set_status as enum ('draft','active','retired');
create type publication.release_status as enum ('candidate','active','superseded','revoked');

create table identity.users (
  id uuid primary key,
  username varchar(100) not null,
  normalized_username varchar(100) not null unique,
  email varchar(320),
  normalized_email varchar(320),
  display_name varchar(160) not null,
  password_hash text not null,
  is_active boolean not null default true,
  must_change_password boolean not null default true,
  failed_login_count integer not null default 0 check(failed_login_count >= 0),
  locked_until timestamptz,
  password_changed_at timestamptz not null default now(),
  last_login_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index uq_identity_users_normalized_email
  on identity.users(normalized_email) where normalized_email is not null;

create table identity.roles (
  id uuid primary key,
  code varchar(40) not null unique,
  display_name varchar(100) not null,
  created_at timestamptz not null default now()
);

create table identity.user_role_assignments (
  id uuid primary key,
  user_id uuid not null references identity.users(id) on delete cascade,
  role_id uuid not null references identity.roles(id) on delete restrict,
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  reason text not null check(length(trim(reason)) > 0)
);
create unique index uq_identity_one_active_role_per_user
  on identity.user_role_assignments(user_id) where revoked_at is null;

create table identity.manager_domain_assignments (
  id uuid primary key,
  user_id uuid not null references identity.users(id) on delete cascade,
  domain sustainability.operational_domain not null,
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  reason text not null check(length(trim(reason)) > 0)
);
create unique index uq_identity_one_active_domain_per_user
  on identity.manager_domain_assignments(user_id) where revoked_at is null;

create table identity.sessions (
  id uuid primary key,
  user_id uuid not null references identity.users(id) on delete cascade,
  session_token_hash varchar(64) not null unique,
  csrf_secret_hash varchar(64) not null,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  idle_expires_at timestamptz not null,
  absolute_expires_at timestamptz not null,
  revoked_at timestamptz,
  revoked_reason text,
  ip_address varchar(64),
  user_agent varchar(512),
  check(idle_expires_at <= absolute_expires_at)
);
create index ix_identity_sessions_user_id on identity.sessions(user_id);

create table sustainability.reporting_periods (
  id uuid primary key,
  year smallint not null check(year between 2000 and 2200),
  month smallint not null check(month between 1 and 12),
  period_start date not null,
  period_end date not null,
  is_open boolean not null default true,
  created_at timestamptz not null default now(),
  constraint uq_reporting_period_year_month unique(year,month),
  check(period_end >= period_start)
);

create table sustainability.metric_definitions (
  code varchar(100) primary key,
  display_name varchar(200) not null,
  operational_domain sustainability.operational_domain not null,
  accounting_classification sustainability.accounting_classification not null,
  canonical_unit varchar(40) not null,
  min_value numeric(20,6),
  max_value numeric(20,6),
  required_for_complete boolean not null,
  zero_allowed boolean not null default true,
  manager_editable boolean not null default true,
  calculation_method text,
  publication_class sustainability.publication_class not null,
  factor_code varchar(80),
  display_order smallint not null check(display_order > 0),
  is_active boolean not null default true,
  check(min_value is null or max_value is null or min_value <= max_value),
  check(manager_editable or calculation_method is not null)
);
create index ix_metric_definitions_domain on sustainability.metric_definitions(operational_domain);

create table sustainability.submissions (
  id uuid primary key,
  domain sustainability.operational_domain not null,
  manager_user_id uuid not null references identity.users(id) on delete restrict,
  reporting_period_id uuid not null references sustainability.reporting_periods(id) on delete restrict,
  status sustainability.submission_status not null default 'draft',
  revision_number integer not null default 1 check(revision_number > 0),
  row_version integer not null default 1 check(row_version > 0),
  remarks text,
  submitted_at timestamptz,
  approved_at timestamptz,
  approved_by uuid references identity.users(id) on delete restrict,
  superseded_submission_id uuid references sustainability.submissions(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check((status = 'approved') = (approved_at is not null and approved_by is not null) or status <> 'approved')
);
create unique index uq_active_submission_domain_period
  on sustainability.submissions(domain,reporting_period_id) where status <> 'superseded';
create index ix_submissions_manager on sustainability.submissions(manager_user_id);

create table sustainability.submission_values (
  submission_id uuid not null references sustainability.submissions(id) on delete cascade,
  metric_code varchar(100) not null references sustainability.metric_definitions(code) on delete restrict,
  value numeric(20,6),
  canonical_unit varchar(40) not null,
  quality_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key(submission_id,metric_code)
);

create table sustainability.review_actions (
  id uuid primary key,
  submission_id uuid not null references sustainability.submissions(id) on delete restrict,
  actor_user_id uuid not null references identity.users(id) on delete restrict,
  action sustainability.review_action_type not null,
  from_status sustainability.submission_status,
  to_status sustainability.submission_status not null,
  comment text,
  created_at timestamptz not null default now()
);
create index ix_review_actions_submission on sustainability.review_actions(submission_id);

create table sustainability.emission_factor_sets (
  id uuid primary key,
  version varchar(100) not null unique,
  status sustainability.factor_set_status not null default 'draft',
  source_note text not null,
  created_at timestamptz not null default now(),
  activated_at timestamptz
);
create unique index uq_one_active_factor_set
  on sustainability.emission_factor_sets(status) where status = 'active';

create table sustainability.emission_factors (
  id uuid primary key,
  factor_set_id uuid not null references sustainability.emission_factor_sets(id) on delete restrict,
  code varchar(80) not null,
  factor_value numeric(20,10) not null check(factor_value >= 0),
  activity_unit varchar(40) not null,
  result_unit varchar(40) not null default 'kgCO2e',
  constraint uq_factor_set_code unique(factor_set_id,code)
);

create table sustainability.calculation_results (
  id uuid primary key,
  submission_id uuid not null references sustainability.submissions(id) on delete restrict,
  metric_code varchar(100) not null,
  activity_value numeric(20,6) not null,
  activity_unit varchar(40) not null,
  factor_id uuid not null references sustainability.emission_factors(id) on delete restrict,
  factor_value numeric(20,10) not null,
  result_kgco2e numeric(20,6) not null,
  formula_version varchar(80) not null,
  calculated_at timestamptz not null default now(),
  constraint uq_calculation_submission_metric unique(submission_id,metric_code)
);

create table publication.public_releases (
  id uuid primary key,
  version varchar(100) not null unique,
  status publication.release_status not null default 'candidate',
  checksum_sha256 varchar(64) not null check(checksum_sha256 ~ '^[0-9a-f]{64}$'),
  prepared_by uuid not null references identity.users(id) on delete restrict,
  published_by uuid references identity.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  published_at timestamptz,
  revoked_reason text
);
create unique index uq_publication_one_active_release
  on publication.public_releases(status) where status = 'active';

create table publication.public_release_payloads (
  release_id uuid primary key references publication.public_releases(id) on delete restrict,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table audit.audit_logs (
  id uuid primary key,
  actor_user_id uuid references identity.users(id) on delete set null,
  actor_type varchar(40) not null,
  event_type varchar(120) not null,
  target_type varchar(80) not null,
  target_reference varchar(200),
  outcome varchar(40) not null,
  request_id varchar(36),
  safe_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index ix_audit_logs_created_at on audit.audit_logs(created_at);
create index ix_audit_logs_event_type on audit.audit_logs(event_type);

create function identity.validate_domain_assignment() returns trigger
language plpgsql set search_path=pg_catalog,identity as $$
declare role_code text;
begin
  select r.code into role_code
  from identity.user_role_assignments a join identity.roles r on r.id=a.role_id
  where a.user_id=new.user_id and a.revoked_at is null;
  if role_code is distinct from 'manager' then
    raise exception 'active manager role required for domain assignment' using errcode='23514';
  end if;
  return new;
end $$;
create trigger manager_domain_role_guard before insert or update
  on identity.manager_domain_assignments for each row execute function identity.validate_domain_assignment();

create function sustainability.validate_submission_owner() returns trigger
language plpgsql set search_path=pg_catalog,identity,sustainability as $$
begin
  if not exists(select 1 from identity.manager_domain_assignments d
                where d.user_id=new.manager_user_id and d.domain=new.domain and d.revoked_at is null) then
    raise exception 'manager is not assigned to submission domain' using errcode='23514';
  end if;
  return new;
end $$;
create trigger submission_owner_guard before insert or update of domain,manager_user_id
  on sustainability.submissions for each row execute function sustainability.validate_submission_owner();

create function sustainability.validate_submission_value() returns trigger
language plpgsql set search_path=pg_catalog,sustainability as $$
declare metric sustainability.metric_definitions; submission_domain sustainability.operational_domain;
begin
  select * into metric from sustainability.metric_definitions where code=new.metric_code and is_active;
  select domain into submission_domain from sustainability.submissions where id=new.submission_id;
  if metric.code is null or submission_domain is null then raise exception 'unknown metric or submission'; end if;
  if metric.operational_domain <> submission_domain then raise exception 'metric domain mismatch' using errcode='23514'; end if;
  if metric.canonical_unit <> new.canonical_unit then raise exception 'metric unit mismatch' using errcode='23514'; end if;
  if not metric.manager_editable and pg_trigger_depth() < 2 then
    raise exception 'calculated metric is not directly editable' using errcode='42501';
  end if;
  if new.value is not null and (
      (metric.min_value is not null and new.value < metric.min_value) or
      (metric.max_value is not null and new.value > metric.max_value) or
      (new.value = 0 and not metric.zero_allowed)) then
    raise exception 'metric value outside definition contract' using errcode='23514';
  end if;
  return new;
end $$;
create trigger submission_value_guard before insert or update
  on sustainability.submission_values for each row execute function sustainability.validate_submission_value();

create function sustainability.recalculate_submission_total(target_submission uuid, total_code text, component_codes text[])
returns void language plpgsql set search_path=pg_catalog,sustainability as $$
declare calculated numeric(20,6); expected integer:=cardinality(component_codes); total_unit text;
begin
  select case when count(*)=expected and count(value)=expected then sum(value) else null end
    into calculated from sustainability.submission_values
    where submission_id=target_submission and metric_code=any(component_codes);
  select canonical_unit into total_unit from sustainability.metric_definitions where code=total_code;
  insert into sustainability.submission_values(submission_id,metric_code,value,canonical_unit)
    values(target_submission,total_code,calculated,total_unit)
  on conflict(submission_id,metric_code) do update set value=excluded.value,updated_at=now();
end $$;

create function sustainability.refresh_calculated_totals() returns trigger
language plpgsql set search_path=pg_catalog,sustainability as $$
declare sid uuid:=coalesce(new.submission_id,old.submission_id); code text:=coalesce(new.metric_code,old.metric_code);
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
create trigger submission_value_calculated_totals after insert or update or delete
  on sustainability.submission_values for each row execute function sustainability.refresh_calculated_totals();

create function sustainability.guard_frozen_submission() returns trigger
language plpgsql set search_path=pg_catalog,sustainability as $$
declare frozen boolean;
begin
  select status in ('approved','superseded') into frozen from sustainability.submissions where id=coalesce(old.submission_id,new.submission_id);
  if frozen then raise exception 'approved submission values are immutable' using errcode='55000'; end if;
  return coalesce(new,old);
end $$;
create trigger frozen_submission_values before update or delete
  on sustainability.submission_values for each row execute function sustainability.guard_frozen_submission();

create function audit.reject_audit_mutation() returns trigger
language plpgsql set search_path=pg_catalog,audit as $$
begin raise exception 'audit logs are append-only' using errcode='55000'; end $$;
create trigger audit_logs_append_only before update or delete on audit.audit_logs
  for each row execute function audit.reject_audit_mutation();

create function publication.reject_payload_mutation() returns trigger
language plpgsql set search_path=pg_catalog,publication as $$
begin raise exception 'public release payloads are immutable' using errcode='55000'; end $$;
create trigger public_release_payloads_immutable before update or delete
  on publication.public_release_payloads for each row execute function publication.reject_payload_mutation();

revoke all on schema identity,sustainability,publication,audit from public;
revoke all on all tables in schema identity,sustainability,publication,audit from public;
revoke all on all functions in schema identity,sustainability,publication,audit from public;
"""


METRIC_SEED_SQL = r"""
insert into identity.roles(id,code,display_name) values
 ('10000000-0000-0000-0000-000000000001','manager','Manager'),
 ('10000000-0000-0000-0000-000000000002','microcosm_admin','MICROCOSM Admin');

insert into sustainability.metric_definitions
 (code,display_name,operational_domain,accounting_classification,canonical_unit,min_value,max_value,
  required_for_complete,zero_allowed,manager_editable,calculation_method,publication_class,factor_code,display_order)
values
 ('transport_petrol_litres','Transport petrol','transport','scope1_inventory','L',0,10000000,true,true,true,null,'public_aggregate','petrol',10),
 ('transport_diesel_litres','Transport diesel','transport','scope1_inventory','L',0,10000000,true,true,true,null,'public_aggregate','diesel',20),
 ('petrol_vehicle_count','Active petrol vehicles','transport','activity_only','count',0,100000,true,true,true,null,'admin_only',null,30),
 ('diesel_vehicle_count','Active diesel vehicles','transport','activity_only','count',0,100000,true,true,true,null,'admin_only',null,40),
 ('ev_consumption_kwh','EV electricity consumption','transport','activity_only','kWh',0,1000000000,false,true,true,null,'admin_only',null,50),
 ('dg_diesel_litres','DG diesel','transport','scope1_inventory','L',0,10000000,true,true,true,null,'public_aggregate','diesel',60),
 ('dg_count','Active DG units','transport','activity_only','count',0,10000,true,true,true,null,'admin_only',null,70),
 ('grid_ht_kwh','Grid HT electricity','energy','activity_only','kWh',0,1000000000,true,true,true,null,'admin_only',null,10),
 ('grid_commercial_kwh','Grid commercial electricity','energy','activity_only','kWh',0,1000000000,true,true,true,null,'admin_only',null,20),
 ('grid_temporary_kwh','Grid temporary electricity','energy','activity_only','kWh',0,1000000000,true,true,true,null,'admin_only',null,30),
 ('grid_total_kwh','Total grid electricity','energy','scope2_inventory','kWh',0,3000000000,true,true,false,'grid_ht_kwh + grid_commercial_kwh + grid_temporary_kwh','public_aggregate','grid',40),
 ('renewable_on_campus_kwh','Renewable energy on campus','energy','renewable_reporting','kWh',0,1000000000,true,true,true,null,'admin_only',null,50),
 ('renewable_procured_kwh','Procured renewable energy','energy','renewable_reporting','kWh',0,1000000000,true,true,true,null,'admin_only',null,60),
 ('solar_water_heater_kwh','Solar water heater equivalent','energy','renewable_reporting','kWh',0,1000000000,true,true,true,null,'admin_only',null,70),
 ('renewable_total_kwh','Total renewable energy','energy','avoided_impact','kWh',0,3000000000,true,true,false,'renewable_on_campus_kwh + renewable_procured_kwh + solar_water_heater_kwh','public_aggregate','grid',80),
 ('lpg_cylinder_count','LPG cylinders','lpg','activity_only','count',0,100000,true,true,true,null,'admin_only',null,10),
 ('lpg_weight_kg','LPG weight','lpg','activity_only','kg',0,10000000,true,true,true,null,'admin_only',null,20),
 ('lpg_consumption_litres','LPG consumption','lpg','scope1_inventory','L',0,10000000,true,true,true,null,'public_aggregate','lpg',30),
 ('water_twad_kl','TWAD water','water','water_reporting','KL',0,1000000000,true,true,true,null,'admin_only',null,10),
 ('water_borewell_kl','Borewell water','water','water_reporting','KL',0,1000000000,true,true,true,null,'admin_only',null,20),
 ('water_private_kl','Private water','water','water_reporting','KL',0,1000000000,true,true,true,null,'admin_only',null,30),
 ('water_consumed_kl','Total water consumed','water','water_reporting','KL',0,3000000000,true,true,false,'water_twad_kl + water_borewell_kl + water_private_kl','public_aggregate',null,40),
 ('wastewater_generated_kl','Wastewater generated','water','water_reporting','KL',0,1000000000,true,true,true,null,'admin_only',null,50),
 ('water_recycled_kl','Water recycled','water','water_reporting','KL',0,1000000000,true,true,true,null,'public_aggregate',null,60),
 ('inlet_ph','Inlet pH','water','water_reporting','pH',0,14,false,false,true,null,'internal_verification',null,110),
 ('inlet_tss','Inlet TSS','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,120),
 ('inlet_tds','Inlet TDS','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,130),
 ('inlet_nh3n','Inlet NH3-N','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,140),
 ('inlet_phosphorus','Inlet phosphorus','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,150),
 ('inlet_chloride','Inlet chloride','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,160),
 ('inlet_sulphate','Inlet sulphate','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,170),
 ('inlet_oil_grease','Inlet oil and grease','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,180),
 ('inlet_cod','Inlet COD','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,190),
 ('inlet_bod','Inlet BOD','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,200),
 ('outlet_ph','Outlet pH','water','water_reporting','pH',0,14,false,false,true,null,'internal_verification',null,210),
 ('outlet_tss','Outlet TSS','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,220),
 ('outlet_tds','Outlet TDS','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,230),
 ('outlet_nh3n','Outlet NH3-N','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,240),
 ('outlet_phosphorus','Outlet phosphorus','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,250),
 ('outlet_chloride','Outlet chloride','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,260),
 ('outlet_sulphate','Outlet sulphate','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,270),
 ('outlet_oil_grease','Outlet oil and grease','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,280),
 ('outlet_cod','Outlet COD','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,290),
 ('outlet_bod','Outlet BOD','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,300),
 ('stp_inlet_cod','STP inlet COD','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,310),
 ('stp_outlet_cod','STP outlet COD','water','water_reporting','mg/L',0,1000000,false,true,true,null,'internal_verification',null,320);

insert into sustainability.emission_factor_sets(id,version,status,source_note) values
 ('20000000-0000-0000-0000-000000000001','existing-project-draft-v1','draft',
  'Existing K-COSMOS values; institutional source confirmation is required before activation.');
insert into sustainability.emission_factors(id,factor_set_id,code,factor_value,activity_unit,result_unit) values
 ('21000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','petrol',2.388,'L','kgCO2e'),
 ('21000000-0000-0000-0000-000000000002','20000000-0000-0000-0000-000000000001','diesel',2.701,'L','kgCO2e'),
 ('21000000-0000-0000-0000-000000000003','20000000-0000-0000-0000-000000000001','grid',0.727,'kWh','kgCO2e');
"""


def upgrade() -> None:
    op.execute(SCHEMA_SQL)
    op.execute(METRIC_SEED_SQL)


def downgrade() -> None:
    op.execute("drop schema audit cascade")
    op.execute("drop schema publication cascade")
    op.execute("drop schema sustainability cascade")
    op.execute("drop schema identity cascade")
