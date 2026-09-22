begin;
create table app_private.audit_ingestion_checkpoints(
 source_service text primary key, cursor_timestamp timestamptz, cursor_key text,
 last_started_at timestamptz, last_succeeded_at timestamptz, source_count bigint not null default 0,
 imported_count bigint not null default 0, error text, updated_at timestamptz not null default now()
);
create table app_private.audit_reconciliation_runs(
 id bigint generated always as identity primary key, source_service text not null,
 started_at timestamptz not null, finished_at timestamptz, source_count bigint,
 destination_count bigint, gap_count bigint, status text not null check(status in ('running','passed','failed')),
 detail jsonb not null default '{}'::jsonb
);
revoke all on app_private.audit_ingestion_checkpoints,app_private.audit_reconciliation_runs from public,anon,authenticated;
alter table app_private.audit_ingestion_checkpoints enable row level security; alter table app_private.audit_ingestion_checkpoints force row level security;
alter table app_private.audit_reconciliation_runs enable row level security; alter table app_private.audit_reconciliation_runs force row level security;
create policy audit_checkpoints_admin_read on app_private.audit_ingestion_checkpoints for select to authenticated using(app_private.has_role('administrator'));
create policy audit_runs_admin_read on app_private.audit_reconciliation_runs for select to authenticated using(app_private.has_role('administrator'));
grant select on app_private.audit_ingestion_checkpoints,app_private.audit_reconciliation_runs to authenticated;
commit;
