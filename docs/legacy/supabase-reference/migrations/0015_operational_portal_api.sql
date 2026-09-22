begin;

-- Phase C1.3 manager facade. Browser roles receive DTOs only; app_private
-- relations and composite types remain inaccessible.
create or replace function api.my_access()
returns jsonb language plpgsql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare result jsonb;
begin
  if not app_private.is_verified_active_user(auth.uid()) then
    raise exception 'verified active user required' using errcode='42501';
  end if;
  select jsonb_build_object(
    'role',case when app_private.has_role('administrator') then 'administrator' else 'manager' end,
    'domain',a.domain,'display_name',p.display_name)
    into result
  from app_private.profiles p
  left join app_private.operational_manager_assignments a
    on a.user_id=p.user_id and a.revoked_at is null
  where p.user_id=auth.uid();
  if result is null or (result->>'role'='manager' and result->>'domain' is null) then
    raise exception 'portal access not assigned' using errcode='42501';
  end if;
  return result;
end $$;

create or replace function api.list_reporting_periods()
returns jsonb language plpgsql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare result jsonb;
begin
  perform api.my_access();
  select coalesce(jsonb_agg(jsonb_build_object(
    'period_ref',p.id,'year',p.calendar_year,'month',p.calendar_month,
    'academic_year',p.academic_year_label,'academic_month',p.academic_month_index,
    'starts_on',p.starts_on,'ends_on',p.ends_on) order by p.starts_on desc),'[]'::jsonb)
    into result from app_private.reporting_periods p;
  return result;
end $$;

create or replace function api.create_draft(
  domain_code text,period_start uuid,period_end uuid,granularity_code text,
  source_description text default '')
returns uuid language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare d app_private.operational_domain; result uuid;
begin
  d:=domain_code::app_private.operational_domain;
  if granularity_code<>'monthly' or period_start is distinct from period_end then
    raise exception 'operational portal accepts one monthly period';
  end if;
  if not app_private.has_operational_domain(d) then
    raise exception 'operational domain authorization denied' using errcode='42501';
  end if;
  if not exists(select 1 from app_private.reporting_periods where id=period_start) then
    raise exception 'reporting period not found';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('portal-draft:'||d::text||':'||period_start::text,0));
  if exists(select 1 from app_private.submissions s
    where s.operational_domain=d and s.period_start_id=period_start
      and s.period_end_id=period_start and s.status in
      ('draft','submitted','under_review','correction_requested','approved')
      and not exists(select 1 from app_private.submissions z
        where z.status='approved' and z.supersedes_id=s.id)) then
    raise exception 'active submission already exists for domain and period';
  end if;
  insert into app_private.submissions
    (domain,operational_domain,submitter_id,period_start_id,period_end_id,
     granularity,source_description)
  values(null,d,auth.uid(),period_start,period_start,'monthly',coalesce(source_description,''))
  returning id into result;
  insert into app_private.audit_events
    (actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
  values(auth.uid(),'user','submission.draft_created','submission',result::text,
    'succeeded',jsonb_build_object('operational_domain',d,'period_ref',period_start));
  return result;
end $$;

create or replace function api.set_submission_value(
  target_submission uuid,metric text,measured_value numeric,measured_unit text,
  note text default null)
returns void language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare d app_private.operational_domain;
begin
  select s.operational_domain into d from app_private.submissions s
  where s.id=target_submission and s.submitter_id=auth.uid()
    and s.status in ('draft','correction_requested') for update;
  if d is null or not app_private.has_operational_domain(d) then
    raise exception 'submission edit denied' using errcode='42501';
  end if;
  if not exists(select 1 from app_private.metric_definitions m
    where m.code=metric and m.operational_domain=d and m.active_to is null) then
    raise exception 'metric is not assigned to manager domain' using errcode='42501';
  end if;
  if exists(select 1 from app_private.metric_definitions m
    where m.code=metric and not m.manager_editable) then
    raise exception 'calculated metric is not directly editable' using errcode='42501';
  end if;
  insert into app_private.submission_values
    (submission_id,metric_code,value,unit,quality_note)
  values(target_submission,metric,measured_value,measured_unit,note)
  on conflict(submission_id,metric_code) do update
    set value=excluded.value,unit=excluded.unit,quality_note=excluded.quality_note;
  -- The existing trigger independently recalculates grid, renewable and water totals.
end $$;

create or replace function api.get_my_draft(target_period uuid)
returns jsonb language plpgsql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare result jsonb;
begin
  select jsonb_build_object(
    'submission_ref',s.id,'domain',s.operational_domain,'status',s.status,
    'row_version',s.row_version,'revision',s.revision,
    'values',coalesce((select jsonb_agg(jsonb_build_object(
      'metric',m.code,'display_name',m.display_name,'unit',m.canonical_unit,
      'value',v.value,'required',m.required_for_complete,'editable',m.manager_editable,
      'zero_allowed',m.zero_allowed) order by m.display_order)
      from app_private.metric_definitions m
      left join app_private.submission_values v on v.submission_id=s.id and v.metric_code=m.code
      where m.operational_domain=s.operational_domain and m.active_to is null),'[]'::jsonb))
    into result from app_private.submissions s
  where s.submitter_id=auth.uid() and s.period_start_id=target_period
    and s.period_end_id=target_period and s.status in ('draft','correction_requested')
    and s.operational_domain is not null
    and app_private.has_operational_domain(s.operational_domain)
  order by s.revision desc limit 1;
  return result;
end $$;

create or replace function api.submit_submission(target_submission uuid,expected_version integer)
returns jsonb language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$
  select jsonb_build_object('submission_ref',x.id,'status',x.status,
    'row_version',x.row_version,'revision',x.revision)
  from app_private.transition_submission(target_submission,expected_version,'submitted',null) x;
$$;

create or replace function api.my_submissions()
returns jsonb language sql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'submission_ref',s.id,'domain',s.operational_domain,'year',p.calendar_year,
    'month',p.calendar_month,'status',s.status,'row_version',s.row_version,
    'revision',s.revision,'submitted_at',s.submitted_at,'approved_at',s.approved_at,
    'values',coalesce((select jsonb_agg(jsonb_build_object(
      'metric',v.metric_code,'value',v.value,'unit',v.unit) order by m.display_order)
      from app_private.submission_values v join app_private.metric_definitions m on m.code=v.metric_code
      where v.submission_id=s.id),'[]'::jsonb),
    'evidence_ready',exists(select 1 from app_private.evidence_files e
      where e.submission_id=s.id and e.status='clean')) order by p.starts_on desc),'[]'::jsonb)
  from app_private.submissions s join app_private.reporting_periods p on p.id=s.period_start_id
  where s.submitter_id=auth.uid() and s.operational_domain is not null
    and app_private.has_operational_domain(s.operational_domain);
$$;

create or replace function api.evidence_upload_authorization(
  target_submission uuid,mime text,expected_bytes bigint,idempotency_key uuid)
returns jsonb language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare s app_private.submissions; a app_private.evidence_upload_authorizations;
begin
  select * into s from app_private.submissions where id=target_submission for update;
  if s.submitter_id is distinct from auth.uid() or s.operational_domain is null
     or not app_private.has_operational_domain(s.operational_domain)
     or s.status not in ('draft','correction_requested') then
    raise exception 'evidence authorization denied' using errcode='42501';
  end if;
  if mime not in ('application/pdf','image/png') or expected_bytes not between 1 and 10485760 then
    raise exception 'evidence type or size rejected';
  end if;
  select * into a from app_private.evidence_upload_authorizations
   where uploader_id=auth.uid() and submission_id=s.id
     and app_private.evidence_upload_authorizations.idempotency_key=$4;
  if a.id is null then
    insert into app_private.evidence_upload_authorizations
      (submission_id,uploader_id,object_path,expected_mime,max_bytes,idempotency_key,expires_at)
    values(s.id,auth.uid(),s.operational_domain::text||'/'||s.id||'/'||gen_random_uuid()||
      case when mime='application/pdf' then '.pdf' else '.png' end,
      mime,expected_bytes,$4,now()+interval '10 minutes') returning * into a;
    insert into app_private.audit_events
      (actor_id,actor_type,event_type,target_type,target_id,outcome,correlation_id)
    values(auth.uid(),'user','evidence.authorization_created','upload_authorization',a.id::text,'succeeded',$4);
  end if;
  return jsonb_build_object('authorization_ref',a.id,'object_path',a.object_path,
    'expected_mime',a.expected_mime,'max_bytes',a.max_bytes,'expires_at',a.expires_at,
    'upload_mode','controlled_server');
end $$;

revoke execute on all functions in schema api from public,anon,authenticated;
grant execute on function api.get_dashboard() to anon,authenticated;
grant execute on function api.my_access(),api.list_reporting_periods(),
  api.create_draft(text,uuid,uuid,text,text),api.set_submission_value(uuid,text,numeric,text,text),
  api.update_submission_source(uuid,text),api.get_my_draft(uuid),
  api.submit_submission(uuid,integer),api.my_submissions(),
  api.evidence_upload_authorization(uuid,text,bigint,uuid),
  api.begin_review(uuid,integer),api.request_correction(uuid,integer,text),
  api.approve_submission(uuid,integer),api.review_queue(),
  api.activate_factor_set(uuid,text,text),api.retire_factor_set(uuid,text) to authenticated;

revoke all on schema app_private from public,anon,authenticated;
revoke execute on all functions in schema app_private from public,anon,authenticated;
grant execute on function app_private.bootstrap_first_admin(uuid,text),
  app_private.record_evidence_scan(uuid,boolean,text,bigint,text,text),
  app_private.ingest_external_audit(text,text,timestamptz,text,text,text,jsonb) to service_role;

commit;
