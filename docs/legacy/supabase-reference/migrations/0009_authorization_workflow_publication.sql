begin;
create or replace function app_private.is_admin_mfa()
returns boolean language sql stable security invoker set search_path=pg_catalog,auth as $$
 select app_private.has_role('administrator') and coalesce(auth.jwt()->>'aal','')='aal2';
$$;

create or replace function app_private.activate_factor_set(target_id uuid,official_source text,official_jurisdiction text)
returns void language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
begin
 if not app_private.is_admin_mfa() or length(trim(official_source))=0 or length(trim(official_jurisdiction))=0
 then raise exception 'administrator MFA and confirmed source/jurisdiction required' using errcode='42501'; end if;
 perform pg_advisory_xact_lock(hashtextextended('factor-lifecycle',0));
 if not exists(select 1 from app_private.emission_factor_sets where id=target_id and status='draft') then raise exception 'draft factor set required'; end if;
 if exists(select 1 from app_private.emission_factor_sets n join app_private.emission_factor_sets a on a.id=target_id
   where n.id<>a.id and n.status in ('active','retired') and daterange(n.valid_from,coalesce(n.valid_to,'infinity'::date),'[]') && daterange(a.valid_from,coalesce(a.valid_to,'infinity'::date),'[]'))
 then raise exception 'factor validity overlap'; end if;
 update app_private.emission_factor_sets set status='active',source_citation=official_source,jurisdiction=official_jurisdiction,approved_by=auth.uid(),approved_at=now() where id=target_id;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome)
 values(auth.uid(),'user','factor_set.activated','factor_set',target_id::text,'succeeded');
end $$;

create or replace function app_private.retire_factor_set(target_id uuid,reason text)
returns void language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
begin
 if not app_private.is_admin_mfa() or length(trim(reason))=0 then raise exception 'administrator MFA and reason required'; end if;
 perform pg_advisory_xact_lock(hashtextextended('factor-lifecycle',0));
 perform set_config('app.factor_retire','on',true);
 update app_private.emission_factor_sets set status='retired',valid_to=coalesce(valid_to,greatest(current_date,valid_from)) where id=target_id and status='active';
 if not found then raise exception 'active factor set required'; end if;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
 values(auth.uid(),'user','factor_set.retired','factor_set',target_id::text,'succeeded',jsonb_build_object('reason',reason));
end $$;

create or replace function app_private.assign_role(target_user uuid,new_role app_private.app_role,new_domain app_private.data_domain,reason text)
returns uuid language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
declare rid uuid; mail text; manager_domain text; admin_domain text;
begin
 if not app_private.is_admin_mfa() then raise exception 'administrator MFA required' using errcode='42501'; end if;
 if length(trim(reason))=0 then raise exception 'reason required'; end if;
 select lower(email) into mail from auth.users where id=target_user and email_confirmed_at is not null;
 if mail is null then raise exception 'verified user required'; end if;
 select manager_email_domain,trusted_admin_email_domain into manager_domain,admin_domain from app_private.institution_settings where id=1;
 if new_role='administrator' then
   if split_part(mail,'@',2) not in (manager_domain,admin_domain) then raise exception 'administrator email domain denied'; end if;
 else
   if split_part(mail,'@',2)<>manager_domain then raise exception 'manager email domain denied'; end if;
 end if;
 if exists(select 1 from app_private.role_assignments where user_id=target_user and revoked_at is null) then raise exception 'one active role only'; end if;
 insert into app_private.profiles(user_id,display_name) values(target_user,split_part(mail,'@',1)) on conflict(user_id) do update set is_active=true;
 insert into app_private.role_assignments(user_id,role,domain,granted_by,reason) values(target_user,new_role,new_domain,auth.uid(),reason) returning id into rid;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
 values(auth.uid(),'user','role.assigned','user',target_user::text,'succeeded',jsonb_build_object('role',new_role,'domain',new_domain));
 return rid;
end $$;

create or replace function app_private.approve_submission(target_id uuid,expected_version integer)
returns app_private.submissions language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
declare s app_private.submissions;
begin
 if not app_private.is_admin_mfa() then raise exception 'administrator MFA required' using errcode='42501'; end if;
 select * into s from app_private.submissions where id=target_id for update;
 if not found or s.row_version<>expected_version or s.status<>'under_review' or s.submitter_id=auth.uid() then raise exception 'approval denied or stale'; end if;
 perform pg_advisory_xact_lock(hashtextextended('submission-approval:'||s.domain::text,0));
 perform pg_advisory_xact_lock(hashtextextended('factor-lifecycle',0));
 if not exists(select 1 from app_private.evidence_files e where e.submission_id=s.id and e.status='clean') then raise exception 'clean evidence required'; end if;
 if exists(select 1 from app_private.submissions x
   join app_private.reporting_periods xs on xs.id=x.period_start_id join app_private.reporting_periods xe on xe.id=x.period_end_id
   join app_private.reporting_periods ns on ns.id=s.period_start_id join app_private.reporting_periods ne on ne.id=s.period_end_id
   where x.id<>s.id and x.id is distinct from s.supersedes_id and x.domain=s.domain and x.status='approved'
   and daterange(xs.starts_on,xe.ends_on,'[]') && daterange(ns.starts_on,ne.ends_on,'[]')
   and exists(select 1 from app_private.submission_values xv join app_private.submission_values nv on nv.submission_id=s.id
     where xv.submission_id=x.id and xv.metric_code=nv.metric_code))
 then raise exception 'approved period overlap'; end if;
 if exists(select 1 from app_private.submission_values v join app_private.metric_definitions m on m.code=v.metric_code
   where v.submission_id=s.id and m.factor_code is not null and 1<>(
    select count(*) from app_private.emission_factor_sets fs join app_private.emission_factors f on f.factor_set_id=fs.id and f.code=m.factor_code and f.input_unit=v.unit
    where fs.status in ('active','retired')
      and (select starts_on from app_private.reporting_periods where id=s.period_start_id)>=fs.valid_from
      and (select ends_on from app_private.reporting_periods where id=s.period_end_id)<=coalesce(fs.valid_to,'infinity'::date)))
 then raise exception 'exactly one effective factor must contain full interval and match unit'; end if;
 insert into app_private.approval_calculations(submission_id,metric_code,activity_value,activity_unit,factor_id,factor_value,result_kgco2e,formula_version)
 select s.id,v.metric_code,v.value,v.unit,f.id,f.value,round(v.value*f.value,6),'activity_x_factor_v1'
 from app_private.submission_values v join app_private.metric_definitions m on m.code=v.metric_code
 join app_private.emission_factor_sets fs on fs.status in ('active','retired') and
   (select starts_on from app_private.reporting_periods where id=s.period_start_id)>=fs.valid_from and
   (select ends_on from app_private.reporting_periods where id=s.period_end_id)<=coalesce(fs.valid_to,'infinity'::date)
 join app_private.emission_factors f on f.factor_set_id=fs.id and f.code=m.factor_code and f.input_unit=v.unit
 where v.submission_id=s.id and v.value is not null and m.factor_code is not null;
 update app_private.submissions set status='approved',approved_at=now(),approved_by=auth.uid(),row_version=row_version+1,updated_at=now() where id=s.id returning * into s;
 insert into app_private.review_actions(submission_id,action,reviewer_id,from_status,to_status) values(s.id,'approved',auth.uid(),'under_review','approved');
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome) values(auth.uid(),'user','submission.approved','submission',s.id::text,'succeeded');
 return s;
end $$;

create or replace function app_private.publish_release(target_id uuid,expected_sha256 text)
returns void language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
declare r app_private.aggregate_releases; actual text;
begin
 if not app_private.is_admin_mfa() then raise exception 'administrator MFA required' using errcode='42501'; end if;
 select * into r from app_private.aggregate_releases where id=target_id for update;
 select encode(digest(convert_to(jsonb_build_object('contract_version',r.contract_version,'setting_version',r.setting_version,'data',payload->'data')::text,'UTF8'),'sha256'),'hex')
 into actual from app_private.public_release_payloads where release_id=target_id;
 if not found or r.status<>'candidate' or r.content_sha256<>expected_sha256 or actual<>expected_sha256 then raise exception 'candidate/hash mismatch'; end if;
 perform set_config('app.release_publish','on',true);
 update app_private.aggregate_releases set status='superseded' where status='active';
 update app_private.aggregate_releases set status='active',published_at=now(),published_by=auth.uid() where id=target_id;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
 values(auth.uid(),'user','release.published','release',target_id::text,'succeeded',jsonb_build_object('sha256',expected_sha256));
end $$;

revoke all on function app_private.assign_role(uuid,app_private.app_role,app_private.data_domain,text) from public,anon;
revoke all on function app_private.activate_factor_set(uuid,text,text) from public,anon;
revoke all on function app_private.retire_factor_set(uuid,text) from public,anon;
revoke all on function app_private.approve_submission(uuid,integer) from public,anon;
revoke all on function app_private.publish_release(uuid,text) from public,anon;
grant execute on function app_private.assign_role(uuid,app_private.app_role,app_private.data_domain,text) to authenticated;
grant execute on function app_private.activate_factor_set(uuid,text,text) to authenticated;
grant execute on function app_private.retire_factor_set(uuid,text) to authenticated;
grant execute on function app_private.approve_submission(uuid,integer) to authenticated;
grant execute on function app_private.publish_release(uuid,text) to authenticated;
revoke all on function app_private.is_admin_mfa() from public,anon;
grant execute on function app_private.is_admin_mfa() to authenticated;
commit;
