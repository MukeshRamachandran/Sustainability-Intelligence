begin;

create table app_private.profiles (
  user_id uuid primary key references auth.users(id) on delete restrict,
  display_name text not null check (length(trim(display_name)) between 1 and 120),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table app_private.role_assignments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete restrict,
  role app_private.app_role not null,
  domain app_private.data_domain,
  granted_by uuid references auth.users(id) on delete restrict,
  granted_at timestamptz not null default now(),
  revoked_by uuid references auth.users(id) on delete restrict,
  revoked_at timestamptz,
  reason text not null check (length(trim(reason)) > 0),
  check ((role = 'administrator' and domain is null) or
         (role::text = domain::text || '_manager')),
  check ((revoked_at is null) = (revoked_by is null))
);
create unique index role_assignments_one_active_role
  on app_private.role_assignments(user_id) where revoked_at is null;

create table app_private.institution_settings (
  id smallint primary key default 1 check (id = 1),
  academic_year_start_month smallint not null check (academic_year_start_month between 1 and 12),
  manager_email_domain text not null,
  trusted_admin_email_domain text,
  evidence_retention_years smallint not null check (evidence_retention_years >= 7),
  admin_mfa_required boolean not null default true,
  manager_mfa_required boolean not null default false,
  version integer not null default 1 check (version > 0),
  changed_by uuid references auth.users(id) on delete restrict,
  changed_at timestamptz not null default now()
);

create table app_private.reporting_periods (
  id uuid primary key default gen_random_uuid(),
  calendar_year smallint not null check (calendar_year between 2000 and 2200),
  calendar_month smallint not null check (calendar_month between 1 and 12),
  academic_year_label text not null,
  academic_month_index smallint not null check (academic_month_index between 1 and 12),
  setting_version integer not null check (setting_version > 0),
  starts_on date not null,
  ends_on date not null,
  unique (calendar_year, calendar_month),
  check (starts_on <= ends_on)
);

create table app_private.audit_events (
  id bigint generated always as identity primary key,
  occurred_at timestamptz not null default now(),
  recorded_at timestamptz not null default now(),
  actor_id uuid references auth.users(id) on delete set null,
  actor_type text not null check (actor_type in ('user','anonymous','system','auth')),
  event_type text not null check (length(event_type) between 1 and 100),
  target_type text,
  target_id text,
  outcome text not null check (outcome in ('started','succeeded','failed','denied')),
  correlation_id uuid,
  source_service text not null default 'application',
  source_event_key text,
  metadata jsonb not null default '{}'::jsonb,
  previous_hash text,
  event_hash text,
  unique (source_service, source_event_key)
);

create or replace function app_private.is_verified_active_user(target_user uuid)
returns boolean language sql stable security definer
set search_path = pg_catalog, auth, app_private
as $$
  select exists (
    select 1 from auth.users u join app_private.profiles p on p.user_id=u.id
    where u.id=target_user and u.email_confirmed_at is not null and p.is_active
  );
$$;

create or replace function app_private.has_role(expected app_private.app_role)
returns boolean language sql stable security definer
set search_path = pg_catalog, auth, app_private
as $$
  select app_private.is_verified_active_user(auth.uid()) and exists (
    select 1 from app_private.role_assignments r
    where r.user_id=auth.uid() and r.role=expected and r.revoked_at is null
  );
$$;

create or replace function app_private.has_domain(expected app_private.data_domain)
returns boolean language sql stable security definer
set search_path = pg_catalog, auth, app_private
as $$
  select app_private.is_verified_active_user(auth.uid()) and exists (
    select 1 from app_private.role_assignments r
    where r.user_id=auth.uid() and r.domain=expected and r.revoked_at is null
  );
$$;

revoke all on all tables in schema app_private from public, anon, authenticated;
revoke all on all sequences in schema app_private from public, anon, authenticated;
revoke all on all functions in schema app_private from public, anon, authenticated;
grant usage on schema app_private to authenticated;
grant execute on function app_private.is_verified_active_user(uuid) to authenticated;
grant execute on function app_private.has_role(app_private.app_role) to authenticated;
grant execute on function app_private.has_domain(app_private.data_domain) to authenticated;

alter table app_private.profiles enable row level security;
alter table app_private.profiles force row level security;
alter table app_private.role_assignments enable row level security;
alter table app_private.role_assignments force row level security;
alter table app_private.institution_settings enable row level security;
alter table app_private.institution_settings force row level security;
alter table app_private.reporting_periods enable row level security;
alter table app_private.reporting_periods force row level security;
alter table app_private.audit_events enable row level security;
alter table app_private.audit_events force row level security;

create policy profiles_read_self on app_private.profiles for select to authenticated
  using (user_id=auth.uid() or app_private.has_role('administrator'));
create policy roles_read_self_or_admin on app_private.role_assignments for select to authenticated
  using (user_id=auth.uid() or app_private.has_role('administrator'));
create policy settings_read_privileged on app_private.institution_settings for select to authenticated
  using (app_private.is_verified_active_user(auth.uid()));
create policy periods_read_privileged on app_private.reporting_periods for select to authenticated
  using (app_private.is_verified_active_user(auth.uid()));
create policy audit_read_admin on app_private.audit_events for select to authenticated
  using (app_private.has_role('administrator'));

grant select on app_private.profiles, app_private.role_assignments,
  app_private.institution_settings, app_private.reporting_periods to authenticated;
grant select on app_private.audit_events to authenticated;
commit;
