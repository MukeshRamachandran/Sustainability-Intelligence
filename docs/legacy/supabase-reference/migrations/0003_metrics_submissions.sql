begin;

create table app_private.metric_definitions (
  code text primary key check (code ~ '^[a-z][a-z0-9_]{1,63}$'),
  domain app_private.data_domain not null,
  display_name text not null,
  canonical_unit text not null,
  required_for_complete boolean not null default true,
  active_from date not null default current_date,
  active_to date,
  check (active_to is null or active_to >= active_from)
);

create table app_private.submissions (
  id uuid primary key default gen_random_uuid(),
  domain app_private.data_domain not null,
  submitter_id uuid not null references auth.users(id) on delete restrict,
  period_start_id uuid not null references app_private.reporting_periods(id),
  period_end_id uuid not null references app_private.reporting_periods(id),
  granularity app_private.submission_granularity not null,
  status app_private.submission_status not null default 'draft',
  revision integer not null default 1 check (revision > 0),
  row_version integer not null default 1 check (row_version > 0),
  supersedes_id uuid references app_private.submissions(id) on delete restrict,
  source_description text not null default '',
  submitted_at timestamptz,
  approved_at timestamptz,
  approved_by uuid references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((granularity='monthly' and period_start_id=period_end_id) or granularity='period_total'),
  check ((status='approved') = (approved_at is not null and approved_by is not null)),
  check (approved_by is null or approved_by <> submitter_id)
);
create index submissions_domain_period on app_private.submissions(domain,period_start_id,period_end_id,status);
create index submissions_submitter on app_private.submissions(submitter_id,status);

create table app_private.submission_values (
  submission_id uuid not null references app_private.submissions(id) on delete cascade,
  metric_code text not null references app_private.metric_definitions(code),
  value numeric(20,6),
  unit text not null,
  quality_note text,
  primary key (submission_id,metric_code),
  check (value is null or value >= 0)
);

create table app_private.submission_revisions (
  submission_id uuid not null references app_private.submissions(id) on delete restrict,
  revision integer not null,
  actor_id uuid not null references auth.users(id) on delete restrict,
  reason text not null,
  snapshot jsonb not null,
  created_at timestamptz not null default now(),
  primary key(submission_id,revision)
);

create table app_private.review_actions (
  id bigint generated always as identity primary key,
  submission_id uuid not null references app_private.submissions(id) on delete restrict,
  action app_private.review_action not null,
  reviewer_id uuid not null references auth.users(id) on delete restrict,
  from_status app_private.submission_status not null,
  to_status app_private.submission_status not null,
  reason text,
  created_at timestamptz not null default now(),
  check (action <> 'correction_requested' or length(trim(reason)) > 0)
);

create or replace function app_private.guard_approved_submission()
returns trigger language plpgsql security invoker set search_path=pg_catalog,app_private as $$
begin
  if old.status='approved' then raise exception 'approved submission is immutable' using errcode='42501'; end if;
  return case when tg_op='DELETE' then old else new end;
end $$;
create trigger submissions_approved_immutable before update or delete on app_private.submissions
for each row execute function app_private.guard_approved_submission();

create or replace function app_private.guard_approved_child()
returns trigger language plpgsql security definer set search_path=pg_catalog,app_private as $$
declare sid uuid := coalesce(new.submission_id,old.submission_id);
begin
  if exists(select 1 from app_private.submissions s where s.id=sid and s.status='approved')
  then raise exception 'approved submission children are immutable' using errcode='42501'; end if;
  return case when tg_op='DELETE' then old else new end;
end $$;
create trigger values_approved_immutable before update or delete on app_private.submission_values
for each row execute function app_private.guard_approved_child();

revoke all on all tables in schema app_private from public, anon, authenticated;
revoke all on all sequences in schema app_private from public, anon, authenticated;
revoke all on function app_private.guard_approved_submission() from public,anon,authenticated;
revoke all on function app_private.guard_approved_child() from public,anon,authenticated;

alter table app_private.metric_definitions enable row level security; alter table app_private.metric_definitions force row level security;
alter table app_private.submissions enable row level security; alter table app_private.submissions force row level security;
alter table app_private.submission_values enable row level security; alter table app_private.submission_values force row level security;
alter table app_private.submission_revisions enable row level security; alter table app_private.submission_revisions force row level security;
alter table app_private.review_actions enable row level security; alter table app_private.review_actions force row level security;

create policy metrics_read_privileged on app_private.metric_definitions for select to authenticated
 using (app_private.is_verified_active_user(auth.uid()));
create policy submissions_read on app_private.submissions for select to authenticated
 using (app_private.has_role('administrator') or (submitter_id=auth.uid() and app_private.has_domain(domain)));
create policy submissions_create_draft on app_private.submissions for insert to authenticated
 with check (submitter_id=auth.uid() and status='draft' and supersedes_id is null and app_private.has_domain(domain));
create policy submissions_edit_own on app_private.submissions for update to authenticated
 using (submitter_id=auth.uid() and app_private.has_domain(domain) and status in ('draft','correction_requested'))
 with check (submitter_id=auth.uid() and app_private.has_domain(domain) and status in ('draft','correction_requested'));
create policy values_read on app_private.submission_values for select to authenticated using
 (exists(select 1 from app_private.submissions s where s.id=submission_id and
  (app_private.has_role('administrator') or (s.submitter_id=auth.uid() and app_private.has_domain(s.domain)))));
create policy values_write on app_private.submission_values for all to authenticated using
 (exists(select 1 from app_private.submissions s where s.id=submission_id and s.submitter_id=auth.uid()
  and app_private.has_domain(s.domain) and s.status in ('draft','correction_requested')))
 with check (exists(select 1 from app_private.submissions s where s.id=submission_id and s.submitter_id=auth.uid()
  and app_private.has_domain(s.domain) and s.status in ('draft','correction_requested')));
create policy revisions_read on app_private.submission_revisions for select to authenticated using
 (exists(select 1 from app_private.submissions s where s.id=submission_id and
  (app_private.has_role('administrator') or s.submitter_id=auth.uid())));
create policy reviews_read on app_private.review_actions for select to authenticated using
 (app_private.has_role('administrator') or exists(select 1 from app_private.submissions s where s.id=submission_id and s.submitter_id=auth.uid()));

grant select on app_private.metric_definitions,app_private.submissions,app_private.submission_values,
 app_private.submission_revisions,app_private.review_actions to authenticated;
grant insert on app_private.submissions to authenticated;
grant update(source_description) on app_private.submissions to authenticated;
grant insert,update on app_private.submission_values to authenticated;
grant delete on app_private.submission_values to authenticated;
commit;
