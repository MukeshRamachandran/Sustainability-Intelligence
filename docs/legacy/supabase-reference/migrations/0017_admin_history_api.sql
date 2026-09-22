begin;

-- Full admin DTOs intentionally include admin_only and internal_verification
-- values; this migration never adds those values to the public release.
-- One-time, short-lived evidence grants are exchanged by a trusted server/Edge
-- function for a Storage signed URL. PostgreSQL never makes the bucket public.
create table app_private.evidence_read_grants (
  id uuid primary key default gen_random_uuid(),
  evidence_id uuid not null references app_private.evidence_files(id) on delete restrict,
  requested_by uuid not null references auth.users(id) on delete restrict,
  token_sha256 text not null unique check (token_sha256~'^[0-9a-f]{64}$'),
  expires_at timestamptz not null,
  consumed_at timestamptz,
  created_at timestamptz not null default now(),
  check (expires_at>created_at)
);
alter table app_private.evidence_read_grants enable row level security;
alter table app_private.evidence_read_grants force row level security;
revoke all on app_private.evidence_read_grants from public,anon,authenticated;

create or replace function api.admin_submission_history(
  domain_code text default null,from_date date default null,to_date date default null,
  status_code text default null,page_limit integer default 50,page_offset integer default 0)
returns jsonb language plpgsql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare result jsonb;
begin
  if not app_private.is_admin_mfa() then
    raise exception 'administrator MFA required' using errcode='42501';
  end if;
  if page_limit not between 1 and 200 or page_offset<0 then raise exception 'invalid paging'; end if;
  select coalesce(jsonb_agg(x.item order by x.starts_on desc),'[]'::jsonb) into result
  from (select p.starts_on,jsonb_build_object(
      'submission_ref',s.id,'domain',coalesce(s.operational_domain::text,s.domain::text),
      'year',p.calendar_year,'month',p.calendar_month,'status',s.status,
      'revision',s.revision,'row_version',s.row_version,
      'submitted_at',s.submitted_at,'approved_at',s.approved_at,
      'value_count',(select count(*) from app_private.submission_values v where v.submission_id=s.id),
      'evidence_count',(select count(*) from app_private.evidence_files e where e.submission_id=s.id)
    ) item from app_private.submissions s
    join app_private.reporting_periods p on p.id=s.period_start_id
    where (domain_code is null or coalesce(s.operational_domain::text,s.domain::text)=domain_code)
      and (from_date is null or p.starts_on>=from_date)
      and (to_date is null or p.ends_on<=to_date)
      and (status_code is null or s.status::text=status_code)
    order by p.starts_on desc limit page_limit offset page_offset) x;
  return result;
end $$;

create or replace function api.admin_submission_detail(target_submission uuid)
returns jsonb language plpgsql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare result jsonb;
begin
  if not app_private.is_admin_mfa() then
    raise exception 'administrator MFA required' using errcode='42501';
  end if;
  select jsonb_build_object(
    'submission_ref',s.id,'domain',coalesce(s.operational_domain::text,s.domain::text),
    'year',p.calendar_year,'month',p.calendar_month,'status',s.status,
    'revision',s.revision,'row_version',s.row_version,
    'source_description',s.source_description,'submitted_at',s.submitted_at,
    'approved_at',s.approved_at,
    'values',coalesce((select jsonb_agg(jsonb_build_object(
      'metric',v.metric_code,'display_name',m.display_name,'value',v.value,'unit',v.unit,
      'publication_class',m.publication_class,'quality_note',v.quality_note)
      order by coalesce(m.display_order,32767),m.code)
      from app_private.submission_values v join app_private.metric_definitions m on m.code=v.metric_code
      where v.submission_id=s.id),'[]'::jsonb),
    'frozen_calculations',coalesce((select jsonb_agg(jsonb_build_object(
      'metric',c.metric_code,'activity_value',c.activity_value,'activity_unit',c.activity_unit,
      'factor_ref',c.factor_id,'factor_value',c.factor_value,
      'result_kgco2e',c.result_kgco2e,'formula_version',c.formula_version)
      order by c.metric_code) from app_private.approval_calculations c
      where c.submission_id=s.id),'[]'::jsonb),
    'evidence',coalesce((select jsonb_agg(jsonb_build_object(
      'evidence_ref',e.id,'original_name',e.original_name,'status',e.status,
      'detected_mime',e.detected_mime,'byte_size',e.byte_size,'uploaded_at',e.uploaded_at)
      order by e.uploaded_at) from app_private.evidence_files e
      where e.submission_id=s.id),'[]'::jsonb)) into result
  from app_private.submissions s join app_private.reporting_periods p on p.id=s.period_start_id
  where s.id=target_submission;
  return result;
end $$;

create or replace function api.admin_water_history(
  from_date date default null,to_date date default null)
returns jsonb language plpgsql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare result jsonb;
begin
  if not app_private.is_admin_mfa() then
    raise exception 'administrator MFA required' using errcode='42501';
  end if;
  select coalesce(jsonb_agg(jsonb_build_object(
    'submission_ref',s.id,'year',p.calendar_year,'month',p.calendar_month,
    'status',s.status,'revision',s.revision,
    'values',coalesce((select jsonb_agg(jsonb_build_object(
      'metric',v.metric_code,'value',v.value,'unit',v.unit,
      'publication_class',m.publication_class) order by m.display_order)
      from app_private.submission_values v join app_private.metric_definitions m on m.code=v.metric_code
      where v.submission_id=s.id and m.operational_domain='water'),'[]'::jsonb))
    order by p.starts_on desc),'[]'::jsonb) into result
  from app_private.submissions s join app_private.reporting_periods p on p.id=s.period_start_id
  where s.operational_domain='water'
    and (from_date is null or p.starts_on>=from_date)
    and (to_date is null or p.ends_on<=to_date);
  return result;
end $$;

create or replace function api.admin_review_history(target_submission uuid default null)
returns jsonb language plpgsql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare result jsonb;
begin
  if not app_private.is_admin_mfa() then
    raise exception 'administrator MFA required' using errcode='42501';
  end if;
  select coalesce(jsonb_agg(jsonb_build_object(
    'review_ref',r.id,'submission_ref',r.submission_id,'action',r.action,
    'from_status',r.from_status,'to_status',r.to_status,'reason',r.reason,
    'reviewer_ref',r.reviewer_id,'created_at',r.created_at)
    order by r.created_at desc),'[]'::jsonb) into result
  from app_private.review_actions r
  where target_submission is null or r.submission_id=target_submission;
  return result;
end $$;

create or replace function api.admin_evidence_link(target_evidence uuid)
returns jsonb language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private,extensions as $$
declare e app_private.evidence_files; grant_id uuid:=gen_random_uuid(); token text;
begin
  if not app_private.is_admin_mfa() then
    raise exception 'administrator MFA required' using errcode='42501';
  end if;
  select * into e from app_private.evidence_files
    where id=target_evidence and status='clean';
  if e.id is null then raise exception 'clean evidence not found'; end if;
  token:=encode(extensions.gen_random_bytes(32),'hex');
  insert into app_private.evidence_read_grants
    (id,evidence_id,requested_by,token_sha256,expires_at)
  values(grant_id,e.id,auth.uid(),
    encode(extensions.digest(convert_to(token,'UTF8'),'sha256'),'hex'),now()+interval '5 minutes');
  insert into app_private.audit_events
    (actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
  values(auth.uid(),'user','evidence.read_grant_created','evidence',e.id::text,'succeeded',
    jsonb_build_object('grant_ref',grant_id,'expires_in_seconds',300));
  return jsonb_build_object('grant_ref',grant_id,'exchange_token',token,
    'expires_at',now()+interval '5 minutes','access_mode','trusted_server_signed_url_exchange');
end $$;

-- Rebuild the complete callable boundary. Deprecated v1 release RPCs remain
-- installed only for migration history and are intentionally not executable.
revoke execute on all functions in schema api from public,anon,authenticated;
grant execute on function api.get_dashboard() to anon,authenticated;
grant execute on function api.my_access(),api.list_reporting_periods(),
  api.create_draft(text,uuid,uuid,text,text),api.set_submission_value(uuid,text,numeric,text,text),
  api.update_submission_source(uuid,text),api.get_my_draft(uuid),
  api.submit_submission(uuid,integer),api.my_submissions(),
  api.evidence_upload_authorization(uuid,text,bigint,uuid),
  api.begin_review(uuid,integer),api.request_correction(uuid,integer,text),
  api.approve_submission(uuid,integer),api.review_queue(),
  api.activate_factor_set(uuid,text,text),api.retire_factor_set(uuid,text),
  api.admin_prepare_release(text),api.admin_release_preview(uuid),
  api.admin_publish_release(uuid,text),
  api.admin_submission_history(text,date,date,text,integer,integer),
  api.admin_submission_detail(uuid),api.admin_water_history(date,date),
  api.admin_review_history(uuid),api.admin_evidence_link(uuid) to authenticated;

revoke all on schema app_private from public,anon,authenticated;
revoke execute on all functions in schema app_private from public,anon,authenticated;
grant execute on function app_private.bootstrap_first_admin(uuid,text),
  app_private.record_evidence_scan(uuid,boolean,text,bigint,text,text),
  app_private.ingest_external_audit(text,text,timestamptz,text,text,text,jsonb) to service_role;

commit;
