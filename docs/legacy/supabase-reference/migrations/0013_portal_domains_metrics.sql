begin;

-- Phase C1 separates operational ownership from carbon-accounting treatment.
-- The legacy data_domain/app_role enums remain intact for migration compatibility;
-- no new portal authorization may infer accounting scope from manager identity.
create type app_private.operational_domain as enum
  ('transport','lpg','energy','water');

create table app_private.operational_manager_assignments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete restrict,
  domain app_private.operational_domain not null,
  granted_by uuid references auth.users(id) on delete restrict,
  granted_at timestamptz not null default now(),
  revoked_by uuid references auth.users(id) on delete restrict,
  revoked_at timestamptz,
  reason text not null check (length(trim(reason)) > 0),
  check ((revoked_at is null) = (revoked_by is null))
);
create unique index operational_manager_one_active_assignment
  on app_private.operational_manager_assignments(user_id) where revoked_at is null;
create unique index operational_manager_one_active_domain_owner
  on app_private.operational_manager_assignments(domain) where revoked_at is null;

alter table app_private.operational_manager_assignments enable row level security;
alter table app_private.operational_manager_assignments force row level security;

create or replace function app_private.has_operational_domain(expected app_private.operational_domain)
returns boolean language sql stable security definer
set search_path=pg_catalog,auth,app_private as $$
  select app_private.is_verified_active_user(auth.uid()) and exists (
    select 1 from app_private.operational_manager_assignments a
    where a.user_id=auth.uid() and a.domain=expected and a.revoked_at is null
  );
$$;

-- Existing rows keep their legacy accounting-oriented domain. New portal rows
-- use operational_domain; exactly one domain model is present on each row.
alter table app_private.metric_definitions
  add column operational_domain app_private.operational_domain,
  add column min_value numeric(20,6),
  add column max_value numeric(20,6),
  add column zero_allowed boolean not null default true,
  add column display_order smallint,
  add column calculation_method text,
  add column manager_editable boolean not null default true;
alter table app_private.metric_definitions alter column domain drop not null;
alter table app_private.metric_definitions
  add constraint metric_definition_one_domain check (
    (domain is null) <> (operational_domain is null)
  ),
  add constraint metric_definition_range_valid check (
    min_value is null or max_value is null or min_value <= max_value
  ),
  add constraint metric_definition_display_order_valid check (
    display_order is null or display_order > 0
  ),
  add constraint metric_definition_calculation_contract check (
    (manager_editable and calculation_method is null) or
    (not manager_editable and length(trim(calculation_method)) > 0)
  );

-- Expand accounting vocabulary without treating water as a carbon inventory.
alter table app_private.metric_definitions
  drop constraint metric_definitions_accounting_class_check;
alter table app_private.metric_definitions
  add constraint metric_definitions_accounting_class_check check (
    accounting_class in (
      'scope1_inventory','scope2_inventory','avoided_impact','activity_only',
      'renewable_reporting','water_reporting'
    )
  );

alter table app_private.submissions
  add column operational_domain app_private.operational_domain;
alter table app_private.submissions alter column domain drop not null;
alter table app_private.submissions
  add constraint submission_one_domain check (
    (domain is null) <> (operational_domain is null)
  );
create index submissions_operational_domain_period
  on app_private.submissions(operational_domain,period_start_id,period_end_id,status)
  where operational_domain is not null;

-- Two requested canonical names were present in the legacy seed. They may be
-- replaced only while unused; silently changing the meaning of historical or
-- approved values would destroy provenance. A populated deployment therefore
-- fails closed and requires an explicit reconciliation migration.
do $$ begin
  if exists(select 1 from app_private.submission_values
            where metric_code in ('dg_diesel_litres','solar_water_heater_kwh')) then
    raise exception 'legacy canonical-code collision requires data reconciliation';
  end if;
  delete from app_private.metric_definitions
   where code in ('dg_diesel_litres','solar_water_heater_kwh');
end $$;

-- Transport and DG. Only fuel activity is Scope 1 inventory activity. EV
-- electricity and fleet counts are retained as operational reporting inputs.
insert into app_private.metric_definitions
 (code,operational_domain,display_name,canonical_unit,required_for_complete,
  accounting_class,factor_code,is_aggregate,min_value,max_value,zero_allowed,
  display_order,calculation_method,manager_editable)
values
 ('transport_petrol_litres','transport','Transport petrol','L',true,
  'scope1_inventory','petrol',false,0,10000000,true,10,null,true),
 ('transport_diesel_litres','transport','Transport diesel','L',true,
  'scope1_inventory','diesel',false,0,10000000,true,20,null,true),
 ('petrol_vehicle_count','transport','Active petrol vehicles','count',true,
  'activity_only',null,false,0,100000,true,30,null,true),
 ('diesel_vehicle_count','transport','Active diesel vehicles','count',true,
  'activity_only',null,false,0,100000,true,40,null,true),
 ('ev_consumption_kwh','transport','EV electricity consumption','kWh',false,
  'activity_only',null,false,0,1000000000,true,50,null,true),
 ('dg_diesel_litres','transport','DG diesel','L',true,
  'scope1_inventory','diesel',false,0,10000000,true,60,null,true),
 ('dg_count','transport','Active DG units','count',true,
  'activity_only',null,false,0,10000,true,70,null,true);

-- LPG activity remains a Scope 1 input. Emission factors are referenced by
-- factor_code and remain versioned/activated only by the administrator flow.
insert into app_private.metric_definitions
 (code,operational_domain,display_name,canonical_unit,required_for_complete,
  accounting_class,factor_code,is_aggregate,min_value,max_value,zero_allowed,
  display_order,calculation_method,manager_editable)
values
 ('lpg_cylinder_count','lpg','LPG cylinders','count',true,
  'activity_only',null,false,0,100000,true,10,null,true),
 ('lpg_weight_kg','lpg','LPG weight','kg',true,
  'activity_only',null,false,0,10000000,true,20,null,true),
 ('lpg_consumption_litres','lpg','LPG consumption','L',true,
  'scope1_inventory','lpg',false,0,10000000,true,30,null,true);

-- Components are reporting inputs; aggregate totals are calculated in the
-- database and are the only energy rows used for factor-based accounting.
insert into app_private.metric_definitions
 (code,operational_domain,display_name,canonical_unit,required_for_complete,
  accounting_class,factor_code,is_aggregate,min_value,max_value,zero_allowed,
  display_order,calculation_method,manager_editable)
values
 ('grid_ht_kwh','energy','Grid HT electricity','kWh',true,
  'activity_only',null,false,0,1000000000,true,10,null,true),
 ('grid_commercial_kwh','energy','Grid commercial electricity','kWh',true,
  'activity_only',null,false,0,1000000000,true,20,null,true),
 ('grid_temporary_kwh','energy','Grid temporary electricity','kWh',true,
  'activity_only',null,false,0,1000000000,true,30,null,true),
 ('grid_total_kwh','energy','Total grid electricity','kWh',true,
  'scope2_inventory','grid',true,0,3000000000,true,40,
  'grid_ht_kwh + grid_commercial_kwh + grid_temporary_kwh',false),
 ('renewable_on_campus_kwh','energy','Renewable energy on campus','kWh',true,
  'renewable_reporting',null,false,0,1000000000,true,50,null,true),
 ('renewable_procured_kwh','energy','Procured renewable energy','kWh',true,
  'renewable_reporting',null,false,0,1000000000,true,60,null,true),
 ('solar_water_heater_kwh','energy','Solar water heater equivalent','kWh',true,
  'renewable_reporting',null,false,0,1000000000,true,70,null,true),
 ('renewable_total_kwh','energy','Total renewable energy','kWh',true,
  'avoided_impact','grid',true,0,3000000000,true,80,
  'renewable_on_campus_kwh + renewable_procured_kwh + solar_water_heater_kwh',false);

-- Water activity and laboratory values are sustainability reporting only.
-- Laboratory readings are optional for monthly completeness in Phase C1.
insert into app_private.metric_definitions
 (code,operational_domain,display_name,canonical_unit,required_for_complete,
  accounting_class,factor_code,is_aggregate,min_value,max_value,zero_allowed,
  display_order,calculation_method,manager_editable)
values
 ('water_twad_kl','water','TWAD water','KL',true,'water_reporting',null,false,0,1000000000,true,10,null,true),
 ('water_borewell_kl','water','Borewell water','KL',true,'water_reporting',null,false,0,1000000000,true,20,null,true),
 ('water_private_kl','water','Private water','KL',true,'water_reporting',null,false,0,1000000000,true,30,null,true),
 ('water_consumed_kl','water','Total water consumed','KL',true,'water_reporting',null,true,0,3000000000,true,40,
  'water_twad_kl + water_borewell_kl + water_private_kl',false),
 ('wastewater_generated_kl','water','Wastewater generated','KL',true,'water_reporting',null,false,0,1000000000,true,50,null,true),
 ('water_recycled_kl','water','Water recycled','KL',true,'water_reporting',null,false,0,1000000000,true,60,null,true),
 ('inlet_ph','water','Inlet pH','pH',false,'water_reporting',null,false,0,14,false,110,null,true),
 ('inlet_tss','water','Inlet TSS','mg/L',false,'water_reporting',null,false,0,1000000,true,120,null,true),
 ('inlet_tds','water','Inlet TDS','mg/L',false,'water_reporting',null,false,0,1000000,true,130,null,true),
 ('inlet_nh3n','water','Inlet NH3-N','mg/L',false,'water_reporting',null,false,0,1000000,true,140,null,true),
 ('inlet_phosphorus','water','Inlet phosphorus','mg/L',false,'water_reporting',null,false,0,1000000,true,150,null,true),
 ('inlet_chloride','water','Inlet chloride','mg/L',false,'water_reporting',null,false,0,1000000,true,160,null,true),
 ('inlet_sulphate','water','Inlet sulphate','mg/L',false,'water_reporting',null,false,0,1000000,true,170,null,true),
 ('inlet_oil_grease','water','Inlet oil and grease','mg/L',false,'water_reporting',null,false,0,1000000,true,180,null,true),
 ('inlet_cod','water','Inlet COD','mg/L',false,'water_reporting',null,false,0,1000000,true,190,null,true),
 ('inlet_bod','water','Inlet BOD','mg/L',false,'water_reporting',null,false,0,1000000,true,200,null,true),
 ('outlet_ph','water','Outlet pH','pH',false,'water_reporting',null,false,0,14,false,210,null,true),
 ('outlet_tss','water','Outlet TSS','mg/L',false,'water_reporting',null,false,0,1000000,true,220,null,true),
 ('outlet_tds','water','Outlet TDS','mg/L',false,'water_reporting',null,false,0,1000000,true,230,null,true),
 ('outlet_nh3n','water','Outlet NH3-N','mg/L',false,'water_reporting',null,false,0,1000000,true,240,null,true),
 ('outlet_phosphorus','water','Outlet phosphorus','mg/L',false,'water_reporting',null,false,0,1000000,true,250,null,true),
 ('outlet_chloride','water','Outlet chloride','mg/L',false,'water_reporting',null,false,0,1000000,true,260,null,true),
 ('outlet_sulphate','water','Outlet sulphate','mg/L',false,'water_reporting',null,false,0,1000000,true,270,null,true),
 ('outlet_oil_grease','water','Outlet oil and grease','mg/L',false,'water_reporting',null,false,0,1000000,true,280,null,true),
 ('outlet_cod','water','Outlet COD','mg/L',false,'water_reporting',null,false,0,1000000,true,290,null,true),
 ('outlet_bod','water','Outlet BOD','mg/L',false,'water_reporting',null,false,0,1000000,true,300,null,true),
 ('stp_inlet_cod','water','STP inlet COD','mg/L',false,'water_reporting',null,false,0,1000000,true,310,null,true),
 ('stp_outlet_cod','water','STP outlet COD','mg/L',false,'water_reporting',null,false,0,1000000,true,320,null,true);

-- Validate operational metric ownership, units, ranges, null/zero semantics,
-- and calculated-field immutability at the database boundary.
create or replace function app_private.validate_submission_value()
returns trigger language plpgsql security definer
set search_path=pg_catalog,app_private as $$
declare m app_private.metric_definitions; legacy app_private.data_domain;
  operational app_private.operational_domain;
begin
  select * into m from app_private.metric_definitions
   where code=new.metric_code and active_to is null;
  select domain,operational_domain into legacy,operational
   from app_private.submissions where id=new.submission_id;
  if m.code is null or new.unit<>m.canonical_unit then
    raise exception 'metric definition/unit mismatch';
  end if;
  if operational is not null then
    if m.operational_domain is distinct from operational then
      raise exception 'operational metric domain mismatch';
    end if;
  elsif m.domain is distinct from legacy then
    raise exception 'legacy metric domain mismatch';
  end if;
  if not m.manager_editable and
     current_setting('app.calculated_metric_write',true) is distinct from 'on' then
    raise exception 'calculated metric is not directly editable' using errcode='42501';
  end if;
  if new.value is not null and
     ((m.min_value is not null and new.value<m.min_value) or
      (m.max_value is not null and new.value>m.max_value) or
      (new.value=0 and not m.zero_allowed)) then
    raise exception 'metric value outside definition contract';
  end if;
  return new;
end $$;

create or replace function app_private.recalculate_operational_totals(target_submission uuid)
returns void language plpgsql security definer
set search_path=pg_catalog,app_private as $$
declare d app_private.operational_domain; total numeric(20,6);
begin
  select operational_domain into d from app_private.submissions where id=target_submission;
  if d='energy' then
    select case when count(*)=3 and count(value)=3 then sum(value) end into total
    from app_private.submission_values
    where submission_id=target_submission and metric_code in
      ('grid_ht_kwh','grid_commercial_kwh','grid_temporary_kwh');
    perform set_config('app.calculated_metric_write','on',true);
    insert into app_private.submission_values(submission_id,metric_code,value,unit)
    values(target_submission,'grid_total_kwh',total,'kWh')
    on conflict(submission_id,metric_code) do update set value=excluded.value,unit=excluded.unit;

    select case when count(*)=3 and count(value)=3 then sum(value) end into total
    from app_private.submission_values
    where submission_id=target_submission and metric_code in
      ('renewable_on_campus_kwh','renewable_procured_kwh','solar_water_heater_kwh');
    insert into app_private.submission_values(submission_id,metric_code,value,unit)
    values(target_submission,'renewable_total_kwh',total,'kWh')
    on conflict(submission_id,metric_code) do update set value=excluded.value,unit=excluded.unit;
  elsif d='water' then
    select case when count(*)=3 and count(value)=3 then sum(value) end into total
    from app_private.submission_values
    where submission_id=target_submission and metric_code in
      ('water_twad_kl','water_borewell_kl','water_private_kl');
    perform set_config('app.calculated_metric_write','on',true);
    insert into app_private.submission_values(submission_id,metric_code,value,unit)
    values(target_submission,'water_consumed_kl',total,'KL')
    on conflict(submission_id,metric_code) do update set value=excluded.value,unit=excluded.unit;
  end if;
end $$;

create or replace function app_private.refresh_operational_totals()
returns trigger language plpgsql security definer
set search_path=pg_catalog,app_private as $$
declare sid uuid:=coalesce(new.submission_id,old.submission_id);
  code text:=coalesce(new.metric_code,old.metric_code);
begin
  if code in ('grid_ht_kwh','grid_commercial_kwh','grid_temporary_kwh',
              'renewable_on_campus_kwh','renewable_procured_kwh','solar_water_heater_kwh',
              'water_twad_kl','water_borewell_kl','water_private_kl') then
    perform app_private.recalculate_operational_totals(sid);
  end if;
  return case when tg_op='DELETE' then old else new end;
end $$;
create trigger submission_value_refresh_operational_totals
after insert or update or delete on app_private.submission_values
for each row execute function app_private.refresh_operational_totals();

-- Completeness is checked when a portal submission is transitioned out of a
-- manager-editable state. Calculated totals must exist and be non-null too.
create or replace function app_private.assert_operational_submission_complete(target_submission uuid)
returns void language plpgsql stable security definer
set search_path=pg_catalog,app_private as $$
declare d app_private.operational_domain; missing text[];
begin
  select operational_domain into d from app_private.submissions where id=target_submission;
  if d is null then return; end if;
  select array_agg(m.code order by m.display_order) into missing
  from app_private.metric_definitions m
  where m.operational_domain=d and m.active_to is null and m.required_for_complete
    and not exists (
      select 1 from app_private.submission_values v
      where v.submission_id=target_submission and v.metric_code=m.code and v.value is not null
    );
  if missing is not null then raise exception 'required metrics missing: %',missing; end if;
end $$;

-- Administrator-controlled operational assignment. This is deliberately kept
-- private in C1; a narrow API facade can be added with the portal integration.
create or replace function app_private.assign_operational_manager(
  target_user uuid,new_domain app_private.operational_domain,reason text)
returns uuid language plpgsql security definer
set search_path=pg_catalog,auth,app_private as $$
declare assignment_id uuid; mail text; manager_domain text;
begin
  if not app_private.is_admin_mfa() then
    raise exception 'administrator MFA required' using errcode='42501';
  end if;
  if length(trim(reason))=0 then raise exception 'reason required'; end if;
  select lower(email) into mail from auth.users
   where id=target_user and email_confirmed_at is not null;
  select manager_email_domain into manager_domain
   from app_private.institution_settings where id=1;
  if mail is null or split_part(mail,'@',2)<>manager_domain then
    raise exception 'verified institutional manager required';
  end if;
  if exists(select 1 from app_private.role_assignments
            where user_id=target_user and revoked_at is null) or
     exists(select 1 from app_private.operational_manager_assignments
            where user_id=target_user and revoked_at is null) then
    raise exception 'one active role/domain assignment only';
  end if;
  insert into app_private.operational_manager_assignments
    (user_id,domain,granted_by,reason)
  values(target_user,new_domain,auth.uid(),reason) returning id into assignment_id;
  insert into app_private.profiles(user_id,display_name)
  values(target_user,split_part(mail,'@',1))
  on conflict(user_id) do update set is_active=true,updated_at=now();
  insert into app_private.audit_events
    (actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
  values(auth.uid(),'user','operational_domain.assigned','user',target_user::text,
         'succeeded',jsonb_build_object('domain',new_domain));
  return assignment_id;
end $$;

-- Replace the legacy transition implementation with a dual-contract version.
-- Operational submissions use operational_domain exclusively; legacy rows
-- remain reviewable without being silently reclassified.
create or replace function app_private.transition_submission(
  target_id uuid,expected_version integer,requested app_private.submission_status,reason text default null)
returns app_private.submissions language plpgsql security definer
set search_path=pg_catalog,auth,app_private as $$
declare s app_private.submissions; action app_private.review_action;
  prior app_private.submission_status;
begin
  select * into s from app_private.submissions where id=target_id for update;
  if not found or s.row_version<>expected_version then
    raise exception 'not found or stale version' using errcode='40001';
  end if;
  if not app_private.is_verified_active_user(auth.uid()) then
    raise exception 'verified active user required' using errcode='42501';
  end if;
  prior:=s.status;
  if requested='submitted' then
    if s.submitter_id<>auth.uid() or s.status not in ('draft','correction_requested') or
       case when s.operational_domain is not null
         then not app_private.has_operational_domain(s.operational_domain)
         else not app_private.has_domain(s.domain) end then
      raise exception 'transition denied' using errcode='42501';
    end if;
    if s.operational_domain is not null then
      if exists(select 1 from app_private.submission_values v
        join app_private.metric_definitions m on m.code=v.metric_code
        where v.submission_id=s.id and
              m.operational_domain is distinct from s.operational_domain) then
        raise exception 'cross-domain metric';
      end if;
      perform app_private.assert_operational_submission_complete(s.id);
    else
      if exists(select 1 from app_private.submission_values v
        join app_private.metric_definitions m on m.code=v.metric_code
        where v.submission_id=s.id and m.domain<>s.domain) then
        raise exception 'cross-domain metric';
      end if;
      if exists(select 1 from app_private.metric_definitions m
        where m.domain=s.domain and m.required_for_complete and not exists(
          select 1 from app_private.submission_values v
          where v.submission_id=s.id and v.metric_code=m.code and v.value is not null)) then
        raise exception 'required values missing';
      end if;
    end if;
    s.revision:=s.revision+1;
    insert into app_private.submission_revisions
      (submission_id,revision,actor_id,reason,snapshot)
    select s.id,s.revision,auth.uid(),coalesce(reason,requested::text),
      jsonb_build_object('submission',to_jsonb(s),'values',coalesce((
        select jsonb_agg(to_jsonb(v) order by v.metric_code)
        from app_private.submission_values v where v.submission_id=s.id),'[]'::jsonb));
    action:=case when s.status='draft' then 'submitted' else 'resubmitted' end;
  elsif requested='under_review' then
    if not app_private.is_admin_mfa() or s.status<>'submitted' then
      raise exception 'transition denied' using errcode='42501';
    end if;
    action:='review_started';
  elsif requested='correction_requested' then
    if not app_private.is_admin_mfa() or s.status<>'under_review' or length(trim(reason))=0 then
      raise exception 'reason/admin MFA review required' using errcode='42501';
    end if;
    action:='correction_requested';
  else
    raise exception 'approval uses approve_submission';
  end if;
  update app_private.submissions
   set status=requested,revision=s.revision,row_version=row_version+1,updated_at=now(),
       submitted_at=case when requested='submitted' then now() else submitted_at end
   where id=s.id returning * into s;
  insert into app_private.review_actions
    (submission_id,action,reviewer_id,from_status,to_status,reason)
  values(s.id,action,auth.uid(),prior,requested,reason);
  insert into app_private.audit_events
    (actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
  values(auth.uid(),'user','submission.'||requested,'submission',s.id::text,
         'succeeded',jsonb_build_object('row_version',s.row_version));
  return s;
end $$;

create or replace function app_private.approve_submission(target_id uuid,expected_version integer)
returns app_private.submissions language plpgsql security definer
set search_path=pg_catalog,auth,app_private as $$
declare s app_private.submissions; effective_domain text;
begin
  if not app_private.is_admin_mfa() then
    raise exception 'administrator MFA required' using errcode='42501';
  end if;
  select * into s from app_private.submissions where id=target_id for update;
  if not found or s.row_version<>expected_version or s.status<>'under_review' or
     s.submitter_id=auth.uid() then raise exception 'approval denied or stale'; end if;
  effective_domain:=coalesce(s.operational_domain::text,s.domain::text);
  perform pg_advisory_xact_lock(hashtextextended('submission-approval:'||effective_domain,0));
  perform pg_advisory_xact_lock(hashtextextended('factor-lifecycle',0));
  if s.operational_domain is not null then
    perform app_private.assert_operational_submission_complete(s.id);
  end if;
  if not exists(select 1 from app_private.evidence_files e
                where e.submission_id=s.id and e.status='clean') then
    raise exception 'clean evidence required';
  end if;
  if exists(select 1 from app_private.submissions x
    join app_private.reporting_periods xs on xs.id=x.period_start_id
    join app_private.reporting_periods xe on xe.id=x.period_end_id
    join app_private.reporting_periods ns on ns.id=s.period_start_id
    join app_private.reporting_periods ne on ne.id=s.period_end_id
    where x.id<>s.id and x.id is distinct from s.supersedes_id and x.status='approved'
      and coalesce(x.operational_domain::text,x.domain::text)=effective_domain
      and daterange(xs.starts_on,xe.ends_on,'[]') && daterange(ns.starts_on,ne.ends_on,'[]')
      and exists(select 1 from app_private.submission_values xv
        join app_private.submission_values nv on nv.submission_id=s.id
        where xv.submission_id=x.id and xv.metric_code=nv.metric_code)) then
    raise exception 'approved period overlap';
  end if;
  if exists(select 1 from app_private.submission_values v
    join app_private.metric_definitions m on m.code=v.metric_code
    where v.submission_id=s.id and v.value is not null and m.factor_code is not null and 1<>(
      select count(*) from app_private.emission_factor_sets fs
      join app_private.emission_factors f
        on f.factor_set_id=fs.id and f.code=m.factor_code and f.input_unit=v.unit
      where fs.status in ('active','retired')
        and (select starts_on from app_private.reporting_periods where id=s.period_start_id)>=fs.valid_from
        and (select ends_on from app_private.reporting_periods where id=s.period_end_id)<=coalesce(fs.valid_to,'infinity'::date))) then
    raise exception 'exactly one effective factor must contain full interval and match unit';
  end if;
  insert into app_private.approval_calculations
    (submission_id,metric_code,activity_value,activity_unit,factor_id,
     factor_value,result_kgco2e,formula_version)
  select s.id,v.metric_code,v.value,v.unit,f.id,f.value,round(v.value*f.value,6),
         'activity_x_factor_v1'
  from app_private.submission_values v
  join app_private.metric_definitions m on m.code=v.metric_code
  join app_private.emission_factor_sets fs on fs.status in ('active','retired')
    and (select starts_on from app_private.reporting_periods where id=s.period_start_id)>=fs.valid_from
    and (select ends_on from app_private.reporting_periods where id=s.period_end_id)<=coalesce(fs.valid_to,'infinity'::date)
  join app_private.emission_factors f
    on f.factor_set_id=fs.id and f.code=m.factor_code and f.input_unit=v.unit
  where v.submission_id=s.id and v.value is not null and m.factor_code is not null;
  update app_private.submissions
   set status='approved',approved_at=now(),approved_by=auth.uid(),
       row_version=row_version+1,updated_at=now()
   where id=s.id returning * into s;
  insert into app_private.review_actions
    (submission_id,action,reviewer_id,from_status,to_status)
  values(s.id,'approved',auth.uid(),'under_review','approved');
  insert into app_private.audit_events
    (actor_id,actor_type,event_type,target_type,target_id,outcome)
  values(auth.uid(),'user','submission.approved','submission',s.id::text,'succeeded');
  return s;
end $$;

-- Preserve the reviewed API allowlist while switching manager-facing draft and
-- value operations to operational domains. No frontend is connected in C1.
create or replace function api.create_draft(
  domain_code text,period_start uuid,period_end uuid,granularity_code text,
  source_description text default '')
returns uuid language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare d app_private.operational_domain;
  g app_private.submission_granularity; result uuid;
begin
  d:=domain_code::app_private.operational_domain;
  g:=granularity_code::app_private.submission_granularity;
  if not app_private.has_operational_domain(d) then
    raise exception 'operational domain authorization denied' using errcode='42501';
  end if;
  insert into app_private.submissions
    (domain,operational_domain,submitter_id,period_start_id,period_end_id,
     granularity,source_description)
  values(null,d,auth.uid(),period_start,period_end,g,coalesce(source_description,''))
  returning id into result;
  insert into app_private.audit_events
    (actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
  values(auth.uid(),'user','submission.draft_created','submission',result::text,
         'succeeded',jsonb_build_object('operational_domain',d));
  return result;
end $$;

create or replace function api.set_submission_value(
  target_submission uuid,metric text,measured_value numeric,measured_unit text,
  note text default null)
returns void language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private as $$
begin
  if not exists(select 1 from app_private.submissions s
    where s.id=target_submission and s.submitter_id=auth.uid()
      and s.operational_domain is not null
      and app_private.has_operational_domain(s.operational_domain)
      and s.status in ('draft','correction_requested')) then
    raise exception 'submission edit denied' using errcode='42501';
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
end $$;

create or replace function api.update_submission_source(target_submission uuid,description text)
returns void language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private as $$
begin
  update app_private.submissions s set source_description=coalesce(description,'')
  where s.id=target_submission and s.submitter_id=auth.uid()
    and s.operational_domain is not null
    and app_private.has_operational_domain(s.operational_domain)
    and s.status in ('draft','correction_requested');
  if not found then raise exception 'submission edit denied' using errcode='42501'; end if;
end $$;

create or replace function api.my_submissions()
returns jsonb language sql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
  select coalesce(jsonb_agg(jsonb_build_object(
    'submission_ref',s.id,'domain',s.operational_domain,
    'start_year',p.calendar_year,'start_month',p.calendar_month,
    'end_year',pe.calendar_year,'end_month',pe.calendar_month,
    'granularity',s.granularity,'status',s.status,'row_version',s.row_version,
    'revision',s.revision,'values',coalesce((select jsonb_agg(
      jsonb_build_object('metric',v.metric_code,'value',v.value,'unit',v.unit)
      order by m.display_order) from app_private.submission_values v
      join app_private.metric_definitions m on m.code=v.metric_code
      where v.submission_id=s.id),'[]'::jsonb),
    'evidence_ready',exists(select 1 from app_private.evidence_files e
      where e.submission_id=s.id and e.status='clean'))
    order by p.starts_on desc),'[]'::jsonb)
  from app_private.submissions s
  join app_private.reporting_periods p on p.id=s.period_start_id
  join app_private.reporting_periods pe on pe.id=s.period_end_id
  where s.submitter_id=auth.uid() and s.operational_domain is not null
    and app_private.has_operational_domain(s.operational_domain);
$$;

create or replace function api.review_queue()
returns jsonb language plpgsql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare result jsonb;
begin
  if not app_private.is_admin_mfa() then
    raise exception 'administrator MFA required' using errcode='42501';
  end if;
  select coalesce(jsonb_agg(jsonb_build_object(
    'submission_ref',s.id,
    'domain',coalesce(s.operational_domain::text,s.domain::text),
    'year',p.calendar_year,'month',p.calendar_month,'status',s.status,
    'row_version',s.row_version,'submitted_at',s.submitted_at,
    'values',coalesce((select jsonb_agg(jsonb_build_object(
      'metric',v.metric_code,'value',v.value,'unit',v.unit)
      order by coalesce(m.display_order,32767),v.metric_code)
      from app_private.submission_values v
      join app_private.metric_definitions m on m.code=v.metric_code
      where v.submission_id=s.id),'[]'::jsonb),
    'clean_evidence_count',(select count(*) from app_private.evidence_files e
      where e.submission_id=s.id and e.status='clean'))
    order by s.submitted_at nulls last),'[]'::jsonb) into result
  from app_private.submissions s
  join app_private.reporting_periods p on p.id=s.period_start_id
  where s.status in ('submitted','under_review','correction_requested');
  return result;
end $$;

-- Private schema and internal helpers stay unavailable to browser roles.
revoke all on app_private.operational_manager_assignments from public,anon,authenticated;
revoke all on all functions in schema app_private from public,anon,authenticated;
grant execute on function app_private.bootstrap_first_admin(uuid,text) to service_role;
grant execute on function app_private.record_evidence_scan(uuid,boolean,text,bigint,text,text) to service_role;
grant execute on function app_private.ingest_external_audit(text,text,timestamptz,text,text,text,jsonb) to service_role;
revoke all on type app_private.operational_domain from public,anon,authenticated;

commit;
