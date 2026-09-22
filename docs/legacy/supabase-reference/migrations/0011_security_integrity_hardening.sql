begin;

-- Strict role/domain semantics and configurable domains.
alter table app_private.role_assignments drop constraint role_assignments_check;
alter table app_private.role_assignments add constraint role_domain_exact check (
 (role='administrator' and domain is null) or
 (role='scope1_manager' and domain='scope1') or
 (role='scope2_manager' and domain='scope2') or
 (role='renewable_manager' and domain='renewable'));

-- Explicit calculation mapping prevents component/total double counting.
alter table app_private.metric_definitions add column factor_code text;
alter table app_private.metric_definitions add column accounting_class text
 check(accounting_class in ('scope1_inventory','scope2_inventory','avoided_impact','activity_only')) default 'activity_only';
alter table app_private.metric_definitions add column is_aggregate boolean not null default false;
alter table app_private.evidence_files add constraint clean_evidence_has_validated_metadata check
 (status<>'clean' or (detected_mime is not null and byte_size is not null and sha256 is not null and validated_at is not null));
update app_private.metric_definitions set factor_code='petrol',accounting_class='scope1_inventory' where code='petrol_litres';
update app_private.metric_definitions set factor_code='diesel',accounting_class='scope1_inventory' where code in ('diesel_litres','dg_diesel_litres');
update app_private.metric_definitions set factor_code='grid',accounting_class='scope2_inventory',is_aggregate=true where code='eb_excluding_re_kwh';
update app_private.metric_definitions set factor_code='grid',accounting_class='avoided_impact',is_aggregate=true where code='total_re_kwh';
update app_private.metric_definitions set required_for_complete=false where code in
 ('industrial_kwh','temporary_kwh','commercial_kwh','procured_re_kwh','re_on_campus_kwh','solar_water_heater_kwh','vehicle_count');
insert into app_private.metric_definitions(code,domain,display_name,canonical_unit,required_for_complete,accounting_class)
values('dg_kwh','scope1','DG electricity','kWh',false,'activity_only') on conflict(code) do nothing;

create or replace function app_private.validate_submission_value() returns trigger language plpgsql security definer
set search_path=pg_catalog,app_private as $$
declare m app_private.metric_definitions; d app_private.data_domain;
begin
 select * into m from app_private.metric_definitions where code=new.metric_code and active_to is null;
 select domain into d from app_private.submissions where id=new.submission_id;
 if m.code is null or m.domain<>d or new.unit<>m.canonical_unit then raise exception 'metric domain/unit mismatch'; end if;
 return new;
end $$;
create trigger submission_value_validate before insert or update on app_private.submission_values
for each row execute function app_private.validate_submission_value();

create or replace function app_private.validate_submission_period() returns trigger language plpgsql security definer
set search_path=pg_catalog,app_private as $$
declare a date; b date;
begin
 select starts_on into a from app_private.reporting_periods where id=new.period_start_id;
 select ends_on into b from app_private.reporting_periods where id=new.period_end_id;
 if a is null or b is null or a>b then raise exception 'invalid reporting period order'; end if;
 return new;
end $$;
create trigger submission_period_validate before insert or update of period_start_id,period_end_id on app_private.submissions
for each row execute function app_private.validate_submission_period();

-- Append-only and approval-dependent immutability.
create or replace function app_private.reject_mutation() returns trigger language plpgsql security invoker
set search_path=pg_catalog as $$ begin raise exception 'append-only/immutable record' using errcode='42501'; end $$;
create trigger audit_append_only before update or delete on app_private.audit_events for each row execute function app_private.reject_mutation();
create trigger review_append_only before update or delete on app_private.review_actions for each row execute function app_private.reject_mutation();
create trigger revision_append_only before update or delete on app_private.submission_revisions for each row execute function app_private.reject_mutation();
create trigger calculation_append_only before update or delete on app_private.approval_calculations for each row execute function app_private.reject_mutation();
create trigger evidence_approved_immutable before update or delete on app_private.evidence_files
for each row execute function app_private.guard_approved_child();

create or replace function app_private.factor_set_immutable() returns trigger language plpgsql security invoker
set search_path=pg_catalog as $$ begin
 if tg_op='DELETE' then raise exception 'factor sets cannot be deleted'; end if;
 if old.status<>'draft' and not(old.status='active' and new.status='retired' and current_setting('app.factor_retire',true)='on')
 then raise exception 'active/retired factor set immutable'; end if; return new; end $$;
create trigger factor_set_immutable before update or delete on app_private.emission_factor_sets for each row execute function app_private.factor_set_immutable();
create or replace function app_private.release_immutable() returns trigger language plpgsql security invoker
set search_path=pg_catalog as $$ begin
 if old.status<>'candidate' and not (old.status='active' and new.status='superseded' and current_setting('app.release_publish',true)='on')
 then raise exception 'published release immutable'; end if; return new; end $$;
create trigger release_immutable before update or delete on app_private.aggregate_releases for each row execute function app_private.release_immutable();
create trigger release_payload_immutable before update or delete on app_private.public_release_payloads for each row execute function app_private.reject_mutation();

create or replace function app_private.audit_hash_event() returns trigger language plpgsql security definer
set search_path=pg_catalog,app_private as $$
declare prior text;
begin
 perform pg_advisory_xact_lock(6842371);
 select event_hash into prior from app_private.audit_events order by id desc limit 1;
 new.previous_hash:=prior;
 new.event_hash:=encode(digest(convert_to(concat_ws('|',coalesce(prior,''),new.occurred_at::text,new.actor_id::text,new.actor_type,new.event_type,
  coalesce(new.target_type,''),coalesce(new.target_id,''),new.outcome,coalesce(new.correlation_id::text,''),new.source_service,coalesce(new.source_event_key,''),new.metadata::text),'UTF8'),'sha256'),'hex');
 return new;
end $$;
create trigger audit_hash before insert on app_private.audit_events for each row execute function app_private.audit_hash_event();
create or replace function app_private.audit_submission_edit() returns trigger language plpgsql security definer
set search_path=pg_catalog,auth,app_private as $$
declare sid uuid:=coalesce(new.submission_id,old.submission_id);
begin
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
 values(auth.uid(),'user','submission.value_'||lower(tg_op),'submission',sid::text,'succeeded',
  jsonb_build_object('metric',coalesce(new.metric_code,old.metric_code),'before',case when tg_op<>'INSERT' then to_jsonb(old) end,'after',case when tg_op<>'DELETE' then to_jsonb(new) end));
 if tg_op='DELETE' then return old; else return new; end if; end $$;
create trigger submission_value_audit after insert or update or delete on app_private.submission_values for each row execute function app_private.audit_submission_edit();
create or replace function app_private.audit_submission_source_edit() returns trigger language plpgsql security definer
set search_path=pg_catalog,auth,app_private as $$ begin
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
 values(auth.uid(),'user','submission.source_description_updated','submission',new.id::text,'succeeded',jsonb_build_object('before',old.source_description,'after',new.source_description)); return new; end $$;
create trigger submission_source_audit after update of source_description on app_private.submissions for each row
when(old.source_description is distinct from new.source_description) execute function app_private.audit_submission_source_edit();

-- Normalized, provenance-bearing public release rows.
create table app_private.public_energy_rows(
 release_id uuid not null references app_private.aggregate_releases(id), period_id uuid not null references app_private.reporting_periods(id),
 scope2_submission_id uuid references app_private.submissions(id), renewable_submission_id uuid references app_private.submissions(id), scope1_submission_id uuid references app_private.submissions(id),
 industrial numeric(20,6), temporary numeric(20,6), commercial numeric(20,6), procured_re numeric(20,6), eb_excluding_re numeric(20,6),
 re_on_campus numeric(20,6), solar_water_heater numeric(20,6), total_re numeric(20,6), dg_kwh numeric(20,6), primary key(release_id,period_id));
create table app_private.public_transport_rows(
 release_id uuid not null references app_private.aggregate_releases(id), period_id uuid not null references app_private.reporting_periods(id),
 scope1_submission_id uuid not null references app_private.submissions(id), petrol_litres numeric(20,6), diesel_litres numeric(20,6), vehicle_count numeric(20,6), primary key(release_id,period_id));
create table app_private.public_coverage(
 release_id uuid not null references app_private.aggregate_releases(id), period_id uuid not null references app_private.reporting_periods(id),
 scope1_approved boolean not null,scope2_approved boolean not null,renewable_approved boolean not null,
 missing_domains text[] not null,complete boolean not null,primary key(release_id,period_id));
create table app_private.public_period_total_rows(
 release_id uuid not null references app_private.aggregate_releases(id), submission_id uuid not null references app_private.submissions(id),
 domain app_private.data_domain not null,period_start_id uuid not null references app_private.reporting_periods(id),period_end_id uuid not null references app_private.reporting_periods(id),
 metric_code text not null,value numeric(20,6),unit text not null,primary key(release_id,submission_id,metric_code));
alter table app_private.public_energy_rows enable row level security; alter table app_private.public_energy_rows force row level security;
alter table app_private.public_transport_rows enable row level security; alter table app_private.public_transport_rows force row level security;
alter table app_private.public_coverage enable row level security; alter table app_private.public_coverage force row level security;
alter table app_private.public_period_total_rows enable row level security; alter table app_private.public_period_total_rows force row level security;
revoke all on app_private.public_energy_rows,app_private.public_transport_rows,app_private.public_coverage,app_private.public_period_total_rows from public,anon,authenticated;
create policy public_energy_active on app_private.public_energy_rows for select to anon,authenticated using(exists(select 1 from app_private.aggregate_releases r where r.id=release_id and r.status='active'));
create policy public_transport_active on app_private.public_transport_rows for select to anon,authenticated using(exists(select 1 from app_private.aggregate_releases r where r.id=release_id and r.status='active'));
create policy public_coverage_active on app_private.public_coverage for select to anon,authenticated using(exists(select 1 from app_private.aggregate_releases r where r.id=release_id and r.status='active'));
create policy public_period_totals_active on app_private.public_period_total_rows for select to anon,authenticated using(exists(select 1 from app_private.aggregate_releases r where r.id=release_id and r.status='active'));
create trigger public_energy_immutable before update or delete on app_private.public_energy_rows for each row execute function app_private.reject_mutation();
create trigger public_transport_immutable before update or delete on app_private.public_transport_rows for each row execute function app_private.reject_mutation();
create trigger public_coverage_immutable before update or delete on app_private.public_coverage for each row execute function app_private.reject_mutation();
create trigger public_period_totals_immutable before update or delete on app_private.public_period_total_rows for each row execute function app_private.reject_mutation();

create or replace function app_private.prepare_release(release_version text)
returns uuid language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
declare rid uuid:=gen_random_uuid(); body jsonb; latest uuid; digest_hex text;
begin
 if not app_private.is_admin_mfa() then raise exception 'administrator MFA required' using errcode='42501'; end if;
 perform pg_advisory_xact_lock(hashtextextended('submission-approval:scope1',0));
 perform pg_advisory_xact_lock(hashtextextended('submission-approval:scope2',0));
 perform pg_advisory_xact_lock(hashtextextended('submission-approval:renewable',0));
 perform pg_advisory_xact_lock(hashtextextended('factor-lifecycle',0));
 insert into app_private.aggregate_releases(id,version,status,setting_version,content_sha256,generated_by)
 values(rid,release_version,'candidate',(select version from app_private.institution_settings where id=1),repeat('0',64),auth.uid());
 insert into app_private.public_coverage
 select rid,p.id,
  exists(select 1 from app_private.submissions s where s.domain='scope1' and s.status='approved' and s.granularity='monthly' and s.period_start_id=p.id and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=s.id) and exists(select 1 from app_private.approval_calculations c where c.submission_id=s.id)),
  exists(select 1 from app_private.submissions s where s.domain='scope2' and s.status='approved' and s.granularity='monthly' and s.period_start_id=p.id and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=s.id) and exists(select 1 from app_private.approval_calculations c where c.submission_id=s.id)),
  exists(select 1 from app_private.submissions s where s.domain='renewable' and s.status='approved' and s.granularity='monthly' and s.period_start_id=p.id and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=s.id) and exists(select 1 from app_private.approval_calculations c where c.submission_id=s.id)),
  array_remove(array[case when not exists(select 1 from app_private.submissions s where s.domain='scope1' and s.status='approved' and s.granularity='monthly' and s.period_start_id=p.id and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=s.id) and exists(select 1 from app_private.approval_calculations c where c.submission_id=s.id)) then 'scope1' end,
   case when not exists(select 1 from app_private.submissions s where s.domain='scope2' and s.status='approved' and s.granularity='monthly' and s.period_start_id=p.id and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=s.id) and exists(select 1 from app_private.approval_calculations c where c.submission_id=s.id)) then 'scope2' end,
   case when not exists(select 1 from app_private.submissions s where s.domain='renewable' and s.status='approved' and s.granularity='monthly' and s.period_start_id=p.id and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=s.id) and exists(select 1 from app_private.approval_calculations c where c.submission_id=s.id)) then 'renewable' end],null),
  (select count(distinct s.domain)=3 from app_private.submissions s where s.status='approved' and s.granularity='monthly' and s.period_start_id=p.id
   and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=s.id)
   and exists(select 1 from app_private.approval_calculations c where c.submission_id=s.id))
 from app_private.reporting_periods p where p.ends_on<=current_date;
 select period_id into latest from app_private.public_coverage c join app_private.reporting_periods p on p.id=c.period_id
 where c.release_id=rid and c.complete order by p.ends_on desc limit 1;
 insert into app_private.public_energy_rows
 select rid,p.id,s2.id,sr.id,s1.id,
  max(v.value) filter(where v.metric_code='industrial_kwh'),max(v.value) filter(where v.metric_code='temporary_kwh'),
  max(v.value) filter(where v.metric_code='commercial_kwh'),max(v.value) filter(where v.metric_code='procured_re_kwh'),
  max(v.value) filter(where v.metric_code='eb_excluding_re_kwh'),max(v.value) filter(where v.metric_code='re_on_campus_kwh'),
  max(v.value) filter(where v.metric_code='solar_water_heater_kwh'),max(v.value) filter(where v.metric_code='total_re_kwh'),
  max(v.value) filter(where v.metric_code='dg_kwh')
 from app_private.reporting_periods p
 left join app_private.submissions s1 on s1.period_start_id=p.id and s1.period_end_id=p.id and s1.domain='scope1' and s1.status='approved' and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=s1.id)
 left join app_private.submissions s2 on s2.period_start_id=p.id and s2.period_end_id=p.id and s2.domain='scope2' and s2.status='approved' and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=s2.id)
 left join app_private.submissions sr on sr.period_start_id=p.id and sr.period_end_id=p.id and sr.domain='renewable' and sr.status='approved' and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=sr.id)
 left join app_private.submission_values v on v.submission_id in (s1.id,s2.id,sr.id)
 where p.ends_on<=current_date and (s1.id is not null or s2.id is not null or sr.id is not null) group by p.id,s1.id,s2.id,sr.id;
 insert into app_private.public_transport_rows
 select rid,p.id,s.id,max(v.value) filter(where v.metric_code='petrol_litres'),max(v.value) filter(where v.metric_code='diesel_litres'),max(v.value) filter(where v.metric_code='vehicle_count')
 from app_private.reporting_periods p join app_private.submissions s on s.period_start_id=p.id and s.period_end_id=p.id and s.domain='scope1' and s.status='approved'
  and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=s.id)
 left join app_private.submission_values v on v.submission_id=s.id where p.ends_on<=current_date group by p.id,s.id;
 insert into app_private.public_period_total_rows
 select rid,s.id,s.domain,s.period_start_id,s.period_end_id,v.metric_code,v.value,v.unit from app_private.submissions s
 join app_private.submission_values v on v.submission_id=s.id join app_private.reporting_periods pe on pe.id=s.period_end_id
 where s.status='approved' and s.granularity='period_total' and pe.ends_on<=current_date
 and not exists(select 1 from app_private.submissions z where z.status='approved' and z.supersedes_id=s.id);
 select jsonb_build_object('metadata',jsonb_build_object('version',release_version,'last_updated',extract(epoch from now())::bigint,
  'academic_year_start_month',(select academic_year_start_month from app_private.institution_settings where id=1),
  'latest_complete_period',(select jsonb_build_object('year',calendar_year,'month',to_char(make_date(calendar_year,calendar_month,1),'Mon')) from app_private.reporting_periods where id=latest)),
  'data',jsonb_build_object('energy',coalesce((select jsonb_agg(jsonb_build_object('Month',to_char(make_date(p.calendar_year,p.calendar_month,1),'Mon'),'Year',p.calendar_year,
   'Industrial',e.industrial,'Temporary',e.temporary,'Commercial',e.commercial,'Procured_RE',e.procured_re,'EB_Excluding_RE',e.eb_excluding_re,
   'RE_On_Campus',e.re_on_campus,'Solar_Water_Heater',e.solar_water_heater,'Total_RE',e.total_re,'DG_kWh',e.dg_kwh,'Status','Approved') order by p.starts_on)
   from app_private.public_energy_rows e join app_private.reporting_periods p on p.id=e.period_id where e.release_id=rid),'[]'::jsonb),
  'transport',coalesce((select jsonb_agg(jsonb_build_object('Month',to_char(make_date(p.calendar_year,p.calendar_month,1),'Mon'),'Year',p.calendar_year,
   'Petrol_Litres',t.petrol_litres,'Diesel_Litres',t.diesel_litres,'Vehicle_Count',t.vehicle_count,'Status','Approved') order by p.starts_on)
   from app_private.public_transport_rows t join app_private.reporting_periods p on p.id=t.period_id where t.release_id=rid),'[]'::jsonb),
  'coverage',coalesce((select jsonb_agg(jsonb_build_object('Month',to_char(make_date(p.calendar_year,p.calendar_month,1),'Mon'),'Year',p.calendar_year,
   'Scope1',case when c.scope1_approved then 'approved' else 'missing' end,'Scope2',case when c.scope2_approved then 'approved' else 'missing' end,
   'Renewable',case when c.renewable_approved then 'approved' else 'missing' end,'Complete',c.complete,'MissingDomains',c.missing_domains) order by p.starts_on)
   from app_private.public_coverage c join app_private.reporting_periods p on p.id=c.period_id where c.release_id=rid),'[]'::jsonb),
  'period_totals',coalesce((select jsonb_agg(jsonb_build_object('Domain',q.domain,'Metric',q.metric_code,'Value',q.value,'Unit',q.unit,
   'StartYear',ps.calendar_year,'StartMonth',to_char(make_date(ps.calendar_year,ps.calendar_month,1),'Mon'),
   'EndYear',pe.calendar_year,'EndMonth',to_char(make_date(pe.calendar_year,pe.calendar_month,1),'Mon')) order by ps.starts_on,q.metric_code)
   from app_private.public_period_total_rows q join app_private.reporting_periods ps on ps.id=q.period_start_id join app_private.reporting_periods pe on pe.id=q.period_end_id where q.release_id=rid),'[]'::jsonb))) into body;
 digest_hex:=encode(digest(convert_to(jsonb_build_object('contract_version','1.0','setting_version',
  (select version from app_private.institution_settings where id=1),'data',body->'data')::text,'UTF8'),'sha256'),'hex');
 body:=jsonb_set(body,'{metadata,content_sha256}',to_jsonb(digest_hex));
 update app_private.aggregate_releases set content_sha256=digest_hex where id=rid;
 insert into app_private.public_release_payloads(release_id,payload,latest_complete_period_id) values(rid,body,latest);
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,metadata) values(auth.uid(),'user','release.prepared','release',rid::text,'succeeded',jsonb_build_object('sha256',digest_hex));
 return rid;
end $$;
revoke all on function app_private.prepare_release(text) from public,anon;
grant execute on function app_private.prepare_release(text) to authenticated;

-- Protected evidence lifecycle primitives; validator/worker only.
create or replace function app_private.create_evidence_authorization(target_submission uuid,mime text,idem uuid)
returns app_private.evidence_upload_authorizations language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
declare s app_private.submissions; a app_private.evidence_upload_authorizations;
begin select * into s from app_private.submissions where id=target_submission;
 if s.submitter_id<>auth.uid() or not app_private.has_domain(s.domain) or s.status not in ('draft','correction_requested') or mime not in ('application/pdf','image/png') then raise exception 'authorization denied'; end if;
 insert into app_private.evidence_upload_authorizations(submission_id,uploader_id,object_path,expected_mime,idempotency_key,expires_at)
 values(s.id,auth.uid(),s.domain::text||'/'||s.id||'/'||gen_random_uuid()||case when mime='application/pdf' then '.pdf' else '.png' end,mime,idem,now()+interval '10 minutes') returning * into a;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,correlation_id) values(auth.uid(),'user','evidence.authorization_created','upload_authorization',a.id::text,'succeeded',idem);
 return a; end $$;

create or replace function app_private.record_evidence_scan(evidence_id uuid,clean boolean,detected text,bytes bigint,hash text,detail text)
returns void language plpgsql security definer set search_path=pg_catalog,app_private as $$
declare expected text;
begin
 select a.expected_mime into expected from app_private.evidence_files e join app_private.evidence_upload_authorizations a on a.id=e.authorization_id where e.id=evidence_id;
 if detected not in ('application/pdf','image/png') or detected is distinct from expected or bytes is null or bytes not between 1 and 10485760 or hash is null or hash !~ '^[0-9a-f]{64}$' then clean:=false; end if;
 update app_private.evidence_files set status=case when clean then 'clean'::app_private.evidence_status else 'failed'::app_private.evidence_status end,
  detected_mime=case when detected in ('application/pdf','image/png') then detected end,
  byte_size=case when bytes between 1 and 10485760 then bytes end,
  sha256=case when hash ~ '^[0-9a-f]{64}$' then hash end,validated_at=now() where id=evidence_id and status='quarantined';
 if not found then raise exception 'evidence not quarantined'; end if;
 insert into app_private.audit_events(actor_type,event_type,target_type,target_id,outcome,metadata)
 values('system','evidence.scan_completed','evidence',evidence_id::text,case when clean then 'succeeded' else 'failed' end,jsonb_build_object('detail',detail));
end $$;

revoke all on function app_private.create_evidence_authorization(uuid,text,uuid) from public,anon;
grant execute on function app_private.create_evidence_authorization(uuid,text,uuid) to authenticated;

create or replace function app_private.authorize_supersession(draft_id uuid,approved_id uuid,reason text)
returns void language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
begin
 if not app_private.is_admin_mfa() or length(trim(reason))=0 then raise exception 'administrator MFA/reason required'; end if;
 if not exists(select 1 from app_private.submissions d join app_private.submissions a on a.id=approved_id
  where d.id=draft_id and d.status='draft' and a.status='approved' and d.domain=a.domain
   and d.period_start_id=a.period_start_id and d.period_end_id=a.period_end_id)
 then raise exception 'invalid supersession pairing'; end if;
 update app_private.submissions set supersedes_id=approved_id where id=draft_id;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
 values(auth.uid(),'user','submission.supersession_authorized','submission',draft_id::text,'succeeded',jsonb_build_object('supersedes',approved_id,'reason',reason));
end $$;
revoke all on function app_private.authorize_supersession(uuid,uuid,text) from public,anon;
grant execute on function app_private.authorize_supersession(uuid,uuid,text) to authenticated;

create or replace function app_private.authorize_evidence_read(evidence_id uuid)
returns text language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
declare p text;
begin select object_path into p from app_private.evidence_files e where e.id=evidence_id and e.status='clean' and
 (e.uploader_id=auth.uid() or app_private.is_admin_mfa());
 if p is null then raise exception 'evidence read denied' using errcode='42501'; end if;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome) values(auth.uid(),'user','evidence.read_authorized','evidence',evidence_id::text,'succeeded');
 return p; end $$;
revoke all on function app_private.authorize_evidence_read(uuid) from public,anon;
grant execute on function app_private.authorize_evidence_read(uuid) to authenticated;

create or replace function app_private.revoke_role(target_user uuid,reason text)
returns void language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$ begin
 if not app_private.is_admin_mfa() or target_user=auth.uid() or length(trim(reason))=0 then raise exception 'admin MFA, different target, and reason required'; end if;
 update app_private.role_assignments set revoked_at=now(),revoked_by=auth.uid(),reason=app_private.role_assignments.reason||'; revoked: '||reason where user_id=target_user and revoked_at is null;
 if not found then raise exception 'active role not found'; end if;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
 values(auth.uid(),'user','role.revoked','user',target_user::text,'succeeded',jsonb_build_object('reason',reason)); end $$;
create or replace function app_private.deactivate_profile(target_user uuid,reason text)
returns void language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$ begin
 if not app_private.is_admin_mfa() or target_user=auth.uid() or length(trim(reason))=0 then raise exception 'admin MFA, different target, and reason required'; end if;
 update app_private.profiles set is_active=false,updated_at=now() where user_id=target_user;
 if not found then raise exception 'profile not found'; end if;
 insert into app_private.audit_events(actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
 values(auth.uid(),'user','profile.deactivated','user',target_user::text,'succeeded',jsonb_build_object('reason',reason)); end $$;
revoke all on function app_private.revoke_role(uuid,text),app_private.deactivate_profile(uuid,text) from public,anon;
grant execute on function app_private.revoke_role(uuid,text),app_private.deactivate_profile(uuid,text) to authenticated;
revoke all on function app_private.record_evidence_scan(uuid,boolean,text,bigint,text,text) from public,anon,authenticated;
grant execute on function app_private.record_evidence_scan(uuid,boolean,text,bigint,text,text) to service_role;

create table app_private.bootstrap_state(id smallint primary key check(id=1),completed_at timestamptz,administrator_id uuid references auth.users(id));
insert into app_private.bootstrap_state(id) values(1);
alter table app_private.bootstrap_state enable row level security; alter table app_private.bootstrap_state force row level security;
revoke all on app_private.bootstrap_state from public,anon,authenticated;
create or replace function app_private.bootstrap_first_admin(target_user uuid,reason text)
returns void language plpgsql security definer set search_path=pg_catalog,auth,app_private as $$
declare mail text; manager_domain text; admin_domain text;
begin
 select lower(email) into mail from auth.users where id=target_user and email_confirmed_at is not null;
 select manager_email_domain,trusted_admin_email_domain into manager_domain,admin_domain from app_private.institution_settings where id=1;
 if mail is null or split_part(mail,'@',2) not in (manager_domain,admin_domain) or exists(select 1 from app_private.role_assignments where revoked_at is null)
 then raise exception 'bootstrap preconditions failed'; end if;
 update app_private.bootstrap_state set completed_at=now(),administrator_id=target_user where id=1 and completed_at is null;
 if not found then raise exception 'bootstrap already consumed'; end if;
 insert into app_private.profiles(user_id,display_name) values(target_user,split_part(mail,'@',1)) on conflict(user_id) do update set is_active=true;
 insert into app_private.role_assignments(user_id,role,domain,reason) values(target_user,'administrator',null,reason);
 insert into app_private.audit_events(actor_type,event_type,target_type,target_id,outcome) values('system','role.bootstrap_admin','user',target_user::text,'succeeded');
end $$;
revoke all on function app_private.bootstrap_first_admin(uuid,text) from public,anon,authenticated;
grant execute on function app_private.bootstrap_first_admin(uuid,text) to service_role;

create or replace function app_private.ingest_external_audit(service text,source_key text,event_time timestamptz,event_name text,subject text,outcome text,detail jsonb)
returns void language plpgsql security definer set search_path=pg_catalog,app_private as $$
begin
 insert into app_private.audit_events(occurred_at,actor_type,event_type,target_type,target_id,outcome,source_service,source_event_key,metadata)
 values(event_time,case when service='auth' then 'auth' else 'system' end,event_name,service,subject,outcome,service,source_key,detail)
 on conflict(source_service,source_event_key) do nothing;
end $$;
revoke all on function app_private.ingest_external_audit(text,text,timestamptz,text,text,text,jsonb) from public,anon,authenticated;
grant execute on function app_private.ingest_external_audit(text,text,timestamptz,text,text,text,jsonb) to service_role;

revoke all on function app_private.reject_mutation(),app_private.validate_submission_value(),app_private.validate_submission_period(),app_private.factor_set_immutable(),app_private.release_immutable() from public,anon,authenticated;
commit;
