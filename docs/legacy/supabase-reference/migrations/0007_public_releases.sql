begin;
create table app_private.aggregate_releases(
 id uuid primary key default gen_random_uuid(), version text not null unique, status app_private.release_status not null default 'candidate',
 contract_version text not null default '1.0', setting_version integer not null, content_sha256 text not null check(content_sha256~'^[0-9a-f]{64}$'),
 generated_at timestamptz not null default now(), generated_by uuid references auth.users(id), published_at timestamptz,
 published_by uuid references auth.users(id), supersedes_id uuid references app_private.aggregate_releases(id),
 check(status<>'active' or (published_at is not null and published_by is not null))
);
create unique index one_active_release on app_private.aggregate_releases((status)) where status='active';
create table app_private.public_release_payloads(
 release_id uuid primary key references app_private.aggregate_releases(id) on delete restrict,
 payload jsonb not null, latest_complete_period_id uuid references app_private.reporting_periods(id)
);
create or replace view api.dashboard_master with (security_invoker=true) as
 select p.payload from app_private.public_release_payloads p join app_private.aggregate_releases r on r.id=p.release_id where r.status='active';
revoke all on app_private.aggregate_releases,app_private.public_release_payloads from public,anon,authenticated;
alter table app_private.aggregate_releases enable row level security; alter table app_private.aggregate_releases force row level security;
alter table app_private.public_release_payloads enable row level security; alter table app_private.public_release_payloads force row level security;
create policy releases_public_active on app_private.aggregate_releases for select to anon,authenticated using(status='active');
create policy payload_public_active on app_private.public_release_payloads for select to anon,authenticated using
 (exists(select 1 from app_private.aggregate_releases r where r.id=release_id and r.status='active'));
grant usage on schema api to anon,authenticated;
grant select on api.dashboard_master to anon,authenticated;
grant select on app_private.aggregate_releases,app_private.public_release_payloads to anon,authenticated;
commit;
