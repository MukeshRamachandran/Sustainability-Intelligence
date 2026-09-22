-- Run only against an isolated staging database after explicit application approval.
-- This script changes no persistent data.
begin;
do $$
declare missing text[];
begin
 select array_agg(x.name) into missing from (values
  ('app_private.profiles'),('app_private.role_assignments'),('app_private.institution_settings'),
  ('app_private.operational_manager_assignments'),
  ('app_private.submissions'),('app_private.submission_values'),('app_private.evidence_files'),
  ('app_private.emission_factor_sets'),('app_private.approval_calculations'),
  ('app_private.aggregate_releases'),('app_private.audit_events')) x(name)
 where to_regclass(x.name) is null;
 if missing is not null then raise exception 'missing relations: %',missing; end if;
end $$;

do $$
declare actual text[];
begin
 select array_agg(e.enumlabel order by e.enumsortorder) into actual
 from pg_type t join pg_enum e on e.enumtypid=t.oid
 join pg_namespace n on n.oid=t.typnamespace
 where n.nspname='app_private' and t.typname='operational_domain';
 if actual is distinct from array['transport','lpg','energy','water']::text[]
 then raise exception 'operational domain contract mismatch: %',actual; end if;
end $$;

do $$
declare actual text[]; public_codes text[]; internal_codes text[];
  expected_public constant text[]:=array[
    'dg_diesel_litres','grid_total_kwh','lpg_consumption_litres',
    'renewable_total_kwh','transport_diesel_litres','transport_petrol_litres',
    'water_consumed_kl','water_recycled_kl'];
  expected_internal constant text[]:=array[
    'inlet_bod','inlet_chloride','inlet_cod','inlet_nh3n','inlet_oil_grease',
    'inlet_ph','inlet_phosphorus','inlet_sulphate','inlet_tds','inlet_tss',
    'outlet_bod','outlet_chloride','outlet_cod','outlet_nh3n','outlet_oil_grease',
    'outlet_ph','outlet_phosphorus','outlet_sulphate','outlet_tds','outlet_tss',
    'stp_inlet_cod','stp_outlet_cod'];
begin
 select array_agg(e.enumlabel order by e.enumsortorder) into actual
 from pg_type t join pg_enum e on e.enumtypid=t.oid
 join pg_namespace n on n.oid=t.typnamespace
 where n.nspname='app_private' and t.typname='publication_class';
 if actual is distinct from array['public_aggregate','admin_only','internal_verification']::text[]
 then raise exception 'publication class contract mismatch: %',actual; end if;

 if exists(select 1 from app_private.metric_definitions where publication_class is null)
 then raise exception 'metric without publication classification'; end if;
 select array_agg(code order by code) into public_codes
 from app_private.metric_definitions where publication_class='public_aggregate';
 if public_codes is distinct from expected_public
 then raise exception 'public aggregate allowlist mismatch: %',public_codes; end if;
 select array_agg(code order by code) into internal_codes
 from app_private.metric_definitions where publication_class='internal_verification';
 if internal_codes is distinct from expected_internal
 then raise exception 'internal verification allowlist mismatch: %',internal_codes; end if;
 if exists(select 1 from app_private.metric_definitions
   where operational_domain is not null
     and code<>all(expected_public) and code<>all(expected_internal)
     and publication_class<>'admin_only')
 then raise exception 'remaining operational metric is not admin only'; end if;
end $$;

do $$
declare expected constant text[]:=array[
 'transport_petrol_litres','transport_diesel_litres','petrol_vehicle_count',
 'diesel_vehicle_count','ev_consumption_kwh','dg_diesel_litres','dg_count',
 'lpg_cylinder_count','lpg_weight_kg','lpg_consumption_litres',
 'grid_ht_kwh','grid_commercial_kwh','grid_temporary_kwh','grid_total_kwh',
 'renewable_on_campus_kwh','renewable_procured_kwh','solar_water_heater_kwh','renewable_total_kwh',
 'water_twad_kl','water_borewell_kl','water_private_kl','water_consumed_kl',
 'wastewater_generated_kl','water_recycled_kl','inlet_ph','inlet_tss','inlet_tds',
 'inlet_nh3n','inlet_phosphorus','inlet_chloride','inlet_sulphate','inlet_oil_grease',
 'inlet_cod','inlet_bod','outlet_ph','outlet_tss','outlet_tds','outlet_nh3n',
 'outlet_phosphorus','outlet_chloride','outlet_sulphate','outlet_oil_grease',
 'outlet_cod','outlet_bod','stp_inlet_cod','stp_outlet_cod'];
 missing text[];
begin
 select array_agg(x) into missing from unnest(expected) x
 where not exists(select 1 from app_private.metric_definitions m
                  where m.code=x and m.operational_domain is not null);
 if missing is not null then raise exception 'portal metrics missing: %',missing; end if;
 if exists(select 1 from app_private.metric_definitions
   where operational_domain='water' and accounting_class in ('scope1_inventory','scope2_inventory'))
 then raise exception 'water metric classified as carbon inventory'; end if;
 if exists(select 1 from app_private.metric_definitions
   where code in ('grid_total_kwh','renewable_total_kwh','water_consumed_kl') and manager_editable)
 then raise exception 'calculated total is manager editable'; end if;
 if exists(select 1 from app_private.metric_definitions
   where code='grid_total_kwh' and accounting_class<>'scope2_inventory') or
    exists(select 1 from app_private.metric_definitions
   where code='renewable_total_kwh' and accounting_class<>'avoided_impact')
 then raise exception 'energy accounting classification mismatch'; end if;
end $$;

do $$
declare bad text[];
begin
 select array_agg(format('%I.%I',n.nspname,c.relname)) into bad
 from pg_class c join pg_namespace n on n.oid=c.relnamespace
 where n.nspname='app_private' and c.relkind in ('r','p') and (not c.relrowsecurity or not c.relforcerowsecurity);
 if bad is not null then raise exception 'RLS not enabled/forced: %',bad; end if;
end $$;

do $$ begin
 if has_schema_privilege('anon','app_private','usage') then raise exception 'anon has private schema usage'; end if;
 if has_table_privilege('anon','app_private.submissions','select') then raise exception 'anon can read submissions'; end if;
 if exists(select 1 from pg_policies where schemaname='storage' and tablename='objects' and cmd in ('INSERT','UPDATE','DELETE')
   and policyname like 'microcosm%') then raise exception 'Microcosm direct-write Storage policy exists'; end if;
 if exists(select 1 from storage.buckets where id='submission-evidence' and (public or file_size_limit<>10485760))
 then raise exception 'evidence bucket is public or wrong size'; end if;
end $$;

do $$
declare actual text[]; expected constant text[]:=array[
 'activate_factor_set','admin_evidence_link','admin_prepare_release','admin_publish_release',
 'admin_release_preview','admin_review_history','admin_submission_detail',
 'admin_submission_history','admin_water_history','approve_submission','assign_role',
 'authorize_supersession','begin_review','create_draft','deactivate_profile',
 'evidence_upload_authorization','get_dashboard','get_my_draft','list_reporting_periods',
 'my_access','my_submissions','prepare_release','publish_release','request_correction',
 'retire_factor_set','review_queue','revoke_role','set_submission_value',
 'submit_submission','update_submission_source'];
begin
 select array_agg(p.proname order by p.proname) into actual from pg_proc p
 join pg_namespace n on n.oid=p.pronamespace where n.nspname='api';
 if actual is distinct from expected then raise exception 'api routine allowlist mismatch: %',actual; end if;
 if exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='api'
   and (not p.prosecdef or pg_get_userbyid(p.proowner)<>'postgres'))
 then raise exception 'API function security mode/owner is unsafe'; end if;
 if exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='api'
   and (select n2.nspname from pg_type t join pg_namespace n2 on n2.oid=t.typnamespace where t.oid=p.prorettype)='app_private')
 then raise exception 'API function exposes private composite return type'; end if;
 if to_regclass('api.dashboard_master') is null then raise exception 'approved dashboard view missing'; end if;
end $$;

do $$
declare bad text[];
begin
 if has_schema_privilege('anon','app_private','usage') or has_schema_privilege('authenticated','app_private','usage')
 then raise exception 'client has private schema usage'; end if;
 if has_schema_privilege('anon','api','create') or has_schema_privilege('authenticated','api','create')
 then raise exception 'client can create in API schema'; end if;
 select array_agg(p.oid::regprocedure::text) into bad from pg_proc p join pg_namespace n on n.oid=p.pronamespace
 where n.nspname='app_private' and (has_function_privilege('anon',p.oid,'execute') or has_function_privilege('authenticated',p.oid,'execute'));
 if bad is not null then raise exception 'private routines executable by clients: %',bad; end if;
 if has_table_privilege('anon','api.dashboard_master','select') or has_table_privilege('authenticated','api.dashboard_master','select')
 then raise exception 'security-invoker view must not have direct client select'; end if;
 if not has_function_privilege('anon','api.get_dashboard()','execute') then raise exception 'anon dashboard RPC missing'; end if;
 if exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='api' and p.proname<>'get_dashboard'
   and has_function_privilege('anon',p.oid,'execute')) then raise exception 'anon can execute non-public API RPC'; end if;
 if exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='api'
   and (not has_function_privilege('authenticated',p.oid,'execute') or exists(
    select 1 from aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a where a.grantee=0 and a.privilege_type='EXECUTE')))
 then raise exception 'API authenticated/PUBLIC ACL mismatch'; end if;
 if exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='app_private'
   and has_function_privilege('service_role',p.oid,'execute') and p.proname not in ('bootstrap_first_admin','record_evidence_scan','ingest_external_audit'))
 then raise exception 'unexpected private routine granted to service_role'; end if;
 if exists(select 1 from (values('app_private.bootstrap_first_admin(uuid,text)'),
   ('app_private.record_evidence_scan(uuid,boolean,text,bigint,text,text)'),
   ('app_private.ingest_external_audit(text,text,timestamp with time zone,text,text,text,jsonb)')) x(signature)
   where not has_function_privilege('service_role',x.signature,'execute'))
 then raise exception 'required service-only routine grant missing'; end if;
end $$;

do $$
declare bad text[];
begin
 select array_agg(p.oid::regprocedure::text) into bad from pg_proc p join pg_namespace n on n.oid=p.pronamespace
 where n.nspname in ('api','app_private') and p.prosecdef and
  (p.proconfig is null or not exists(select 1 from unnest(p.proconfig) c where c like 'search_path=%')
   or exists(select 1 from unnest(p.proconfig) c where c like 'search_path=%public%' or c like '%$user%'));
 if bad is not null then raise exception 'unsafe SECURITY DEFINER search_path: %',bad; end if;
end $$;

do $$
declare mimes text[];
begin
 if not exists(select 1 from storage.buckets where id='submission-evidence' and public=false and file_size_limit=10485760)
 then raise exception 'private evidence bucket missing or misconfigured'; end if;
 select allowed_mime_types into mimes from storage.buckets where id='submission-evidence';
 if mimes is distinct from array['application/pdf','image/png']::text[] then raise exception 'bucket MIME allowlist mismatch: %',mimes; end if;
end $$;

-- Data API exposure is hosted PostgREST configuration, not a PostgreSQL catalog
-- object. Gate B3.2 must query/inspect the hosted API schema configuration and
-- prove it contains `api` and excludes `app_private`; config.toml is also
-- checked by source tests. SQL verification alone cannot establish this fact.

do $$ begin
 if to_regclass('app_private.evidence_read_grants') is null
 then raise exception 'evidence read grant table missing'; end if;
 if has_function_privilege('anon','api.admin_publish_release(uuid,text)','execute')
 then raise exception 'anon can publish releases'; end if;
 if has_function_privilege('anon','api.admin_evidence_link(uuid)','execute')
 then raise exception 'anon can authorize evidence reads'; end if;
 if has_function_privilege('authenticated','api.prepare_release(text)','execute') or
    has_function_privilege('authenticated','api.publish_release(uuid,text)','execute')
 then raise exception 'deprecated v1 release API remains executable'; end if;
 if not has_function_privilege('authenticated','api.admin_prepare_release(text)','execute') or
    not has_function_privilege('authenticated','api.admin_publish_release(uuid,text)','execute')
 then raise exception 'protected v2 release API grant missing'; end if;
end $$;

do $$
declare definition text;
begin
 select pg_get_functiondef('api.get_dashboard()'::regprocedure) into definition;
 if definition !~ 'status=''active''' or definition !~ 'contract_version=''2.0'''
 then raise exception 'dashboard is not active v2 release only'; end if;
 if definition ~* 'metric_definitions|submission_values|submissions|evidence|review_actions|audit_events'
 then raise exception 'dashboard RPC reads a private source directly'; end if;
 select pg_get_functiondef('app_private.prepare_public_release_v2(text)'::regprocedure) into definition;
 if definition !~ 'publication_class=''public_aggregate''' or
    definition ~* 'inlet_ph|outlet_ph|stp_inlet_cod|stp_outlet_cod|all_metrics'
 then raise exception 'public release builder classification/allowlist unsafe'; end if;
end $$;

do $$ begin
 if (select academic_year_start_month from app_private.institution_settings where id=1)<>6 then raise exception 'academic year must begin June'; end if;
 if exists(select 1 from app_private.emission_factor_sets where version_label='v1-institution-confirmation-required' and status<>'draft')
 then raise exception 'unconfirmed seed factor set must remain draft'; end if;
 if (select count(*) from app_private.emission_factors f join app_private.emission_factor_sets s on s.id=f.factor_set_id
   where s.version_label='v1-institution-confirmation-required' and
   ((f.code='petrol' and f.value=2.388) or (f.code='diesel' and f.value=2.701) or (f.code='grid' and f.value=0.727)))<>3
 then raise exception 'seed factors mismatch'; end if;
end $$;

-- Behavior tests in staging must use five real verified accounts and JWTs
-- (four operational managers plus one administrator):
-- deny anon/unassigned/unverified/wrong-domain; require admin aal2; reject self approval;
-- run draft->submit->review->correction->resubmit->approve; reject approved UPDATE/DELETE;
-- claim upload once under concurrency; reject direct/upsert Storage; clean-only evidence reads;
-- reject period overlap; preserve null vs zero; require active dated factors and frozen snapshots;
-- create candidate release, prove approved-only payload, publish atomically, and roll back release.
rollback;
