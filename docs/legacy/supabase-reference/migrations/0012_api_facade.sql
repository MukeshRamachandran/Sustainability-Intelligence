begin;

-- app_private is never a Data API schema. Clients call only this allowlisted API.
revoke all on schema app_private from public, anon, authenticated;
revoke execute on all functions in schema app_private from public, anon, authenticated;
revoke all on all tables in schema app_private from public, anon, authenticated;
revoke all on all sequences in schema app_private from public, anon, authenticated;

revoke all on schema api from public, anon, authenticated;
grant usage on schema api to anon, authenticated;
revoke all on all functions in schema api from public, anon, authenticated;
revoke all on all tables in schema api from public, anon, authenticated;

create or replace function api.get_dashboard()
returns jsonb language sql stable security definer
set search_path=pg_catalog,api,app_private as $$
 select p.payload from app_private.public_release_payloads p
 join app_private.aggregate_releases r on r.id=p.release_id
 where r.status='active' limit 1;
$$;

create or replace function api.create_draft(
 domain_code text, period_start uuid, period_end uuid, granularity_code text, source_description text default '')
returns uuid language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare d app_private.data_domain; g app_private.submission_granularity; result uuid;
begin
 d:=domain_code::app_private.data_domain; g:=granularity_code::app_private.submission_granularity;
 if not app_private.has_domain(d) then raise exception 'domain authorization denied' using errcode='42501'; end if;
 insert into app_private.submissions(domain,submitter_id,period_start_id,period_end_id,granularity,source_description)
 values(d,auth.uid(),period_start,period_end,g,coalesce(source_description,'')) returning id into result;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome)
 values(auth.uid(),'user','submission.draft_created','submission',result::text,'succeeded');
 return result;
end $$;

create or replace function api.set_submission_value(target_submission uuid, metric text, measured_value numeric, measured_unit text, note text default null)
returns void language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private as $$
begin
 if not exists(select 1 from app_private.submissions s where s.id=target_submission and s.submitter_id=auth.uid()
  and app_private.has_domain(s.domain) and s.status in ('draft','correction_requested'))
 then raise exception 'submission edit denied' using errcode='42501'; end if;
 insert into app_private.submission_values(submission_id,metric_code,value,unit,quality_note)
 values(target_submission,metric,measured_value,measured_unit,note)
 on conflict(submission_id,metric_code) do update set value=excluded.value,unit=excluded.unit,quality_note=excluded.quality_note;
end $$;

create or replace function api.update_submission_source(target_submission uuid, description text)
returns void language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private as $$
begin
 update app_private.submissions s set source_description=coalesce(description,'')
 where s.id=target_submission and s.submitter_id=auth.uid() and app_private.has_domain(s.domain)
  and s.status in ('draft','correction_requested');
 if not found then raise exception 'submission edit denied' using errcode='42501'; end if;
end $$;

create or replace function api.submit_submission(target_submission uuid, expected_version integer)
returns jsonb language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$
 select jsonb_build_object('submission_ref',x.id,'status',x.status,'row_version',x.row_version,'revision',x.revision)
 from app_private.transition_submission(target_submission,expected_version,'submitted',null) x;
$$;

create or replace function api.my_submissions()
returns jsonb language sql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
 select coalesce(jsonb_agg(jsonb_build_object('submission_ref',s.id,'domain',s.domain,'start_year',p.calendar_year,
  'start_month',p.calendar_month,'end_year',pe.calendar_year,'end_month',pe.calendar_month,'granularity',s.granularity,
  'status',s.status,'row_version',s.row_version,'revision',s.revision,
  'values',coalesce((select jsonb_agg(jsonb_build_object('metric',v.metric_code,'value',v.value,'unit',v.unit)
   order by v.metric_code) from app_private.submission_values v where v.submission_id=s.id),'[]'::jsonb),
  'evidence_ready',exists(select 1 from app_private.evidence_files e where e.submission_id=s.id and e.status='clean'))
  order by p.starts_on desc),'[]'::jsonb)
 from app_private.submissions s join app_private.reporting_periods p on p.id=s.period_start_id
 join app_private.reporting_periods pe on pe.id=s.period_end_id
 where s.submitter_id=auth.uid() and app_private.has_domain(s.domain);
$$;

create or replace function api.begin_review(target_submission uuid,expected_version integer)
returns jsonb language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$
 select jsonb_build_object('submission_ref',x.id,'status',x.status,'row_version',x.row_version)
 from app_private.transition_submission(target_submission,expected_version,'under_review',null) x;
$$;

create or replace function api.request_correction(target_submission uuid,expected_version integer,reason text)
returns jsonb language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$
 select jsonb_build_object('submission_ref',x.id,'status',x.status,'row_version',x.row_version)
 from app_private.transition_submission(target_submission,expected_version,'correction_requested',reason) x;
$$;

create or replace function api.approve_submission(target_submission uuid,expected_version integer)
returns jsonb language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$
 select jsonb_build_object('submission_ref',x.id,'status',x.status,'row_version',x.row_version,'approved_at',x.approved_at)
 from app_private.approve_submission(target_submission,expected_version) x;
$$;

create or replace function api.review_queue()
returns jsonb language plpgsql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare result jsonb;
begin
 if not app_private.is_admin_mfa() then raise exception 'administrator MFA required' using errcode='42501'; end if;
 select coalesce(jsonb_agg(jsonb_build_object('submission_ref',s.id,'domain',s.domain,'year',p.calendar_year,
  'month',p.calendar_month,'status',s.status,'row_version',s.row_version,'submitted_at',s.submitted_at,
  'values',coalesce((select jsonb_agg(jsonb_build_object('metric',v.metric_code,'value',v.value,'unit',v.unit)
   order by v.metric_code) from app_private.submission_values v where v.submission_id=s.id),'[]'::jsonb),
  'clean_evidence_count',(select count(*) from app_private.evidence_files e where e.submission_id=s.id and e.status='clean'))
  order by s.submitted_at nulls last),'[]'::jsonb) into result
 from app_private.submissions s join app_private.reporting_periods p on p.id=s.period_start_id
 where s.status in ('submitted','under_review','correction_requested');
 return result;
end $$;

create or replace function api.prepare_release(release_version text)
returns uuid language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$ select app_private.prepare_release(release_version); $$;

create or replace function api.publish_release(release_id uuid,expected_sha256 text)
returns void language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$ select app_private.publish_release(release_id,expected_sha256); $$;

create or replace function api.assign_role(target_user uuid,role_code text,domain_code text,reason text)
returns boolean language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$
 select app_private.assign_role(target_user,role_code::app_private.app_role,
  case when domain_code is null then null else domain_code::app_private.data_domain end,reason) is not null;
$$;

create or replace function api.revoke_role(target_user uuid,reason text)
returns void language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$ select app_private.revoke_role(target_user,reason); $$;

create or replace function api.deactivate_profile(target_user uuid,reason text)
returns void language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$ select app_private.deactivate_profile(target_user,reason); $$;

create or replace function api.authorize_supersession(draft_id uuid,approved_id uuid,reason text)
returns void language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$ select app_private.authorize_supersession(draft_id,approved_id,reason); $$;

create or replace function api.activate_factor_set(factor_set_id uuid,official_source text,official_jurisdiction text)
returns void language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$ select app_private.activate_factor_set(factor_set_id,official_source,official_jurisdiction); $$;

create or replace function api.retire_factor_set(factor_set_id uuid,reason text)
returns void language sql security definer
set search_path=pg_catalog,auth,api,app_private as $$ select app_private.retire_factor_set(factor_set_id,reason); $$;

-- Public has one read-only aggregate RPC. All workflow RPCs require authenticated JWTs.
revoke execute on all functions in schema api from public, anon, authenticated;
grant execute on function api.get_dashboard() to anon,authenticated;
grant execute on function api.create_draft(text,uuid,uuid,text,text),
 api.set_submission_value(uuid,text,numeric,text,text),api.update_submission_source(uuid,text),
 api.submit_submission(uuid,integer),api.my_submissions(),
 api.begin_review(uuid,integer),api.request_correction(uuid,integer,text),
 api.approve_submission(uuid,integer),api.review_queue(),api.prepare_release(text),api.publish_release(uuid,text),
 api.assign_role(uuid,text,text,text),api.revoke_role(uuid,text),api.deactivate_profile(uuid,text),
 api.authorize_supersession(uuid,uuid,text),api.activate_factor_set(uuid,text,text),
 api.retire_factor_set(uuid,text) to authenticated;

-- The approved-only view is retained for internal composition. Anonymous access
-- uses get_dashboard(); the security-invoker view has no direct client grant.

-- Trigger functions and protected worker/bootstrap routines remain private.
grant execute on function app_private.bootstrap_first_admin(uuid,text),
 app_private.record_evidence_scan(uuid,boolean,text,bigint,text,text),
 app_private.ingest_external_audit(text,text,timestamptz,text,text,text,jsonb) to service_role;

commit;
