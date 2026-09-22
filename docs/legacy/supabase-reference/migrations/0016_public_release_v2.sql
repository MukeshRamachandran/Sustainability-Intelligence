begin;

-- Return one current approved operational submission for a monthly period.
create or replace function app_private.release_submission(
  target_period uuid,target_domain app_private.operational_domain)
returns uuid language sql stable security definer
set search_path=pg_catalog,app_private as $$
  select s.id from app_private.submissions s
  where s.period_start_id=target_period and s.period_end_id=target_period
    and s.granularity='monthly' and s.operational_domain=target_domain
    and s.status='approved'
    and not exists(select 1 from app_private.submissions z
      where z.status='approved' and z.supersedes_id=s.id)
  order by s.revision desc limit 1;
$$;

-- Public activity values must pass both gates: the publication classification
-- and this function's explicit caller-owned metric-code allowlist.
create or replace function app_private.release_metric_value(
  target_submission uuid,target_metric text)
returns numeric language sql stable security definer
set search_path=pg_catalog,app_private as $$
  select v.value from app_private.submission_values v
  join app_private.metric_definitions m on m.code=v.metric_code
  where v.submission_id=target_submission and v.metric_code=target_metric
    and m.publication_class='public_aggregate';
$$;

create or replace function app_private.prepare_public_release_v2(release_version text)
returns uuid language plpgsql security definer
set search_path=pg_catalog,auth,app_private,extensions as $$
declare rid uuid:=gen_random_uuid(); p record; periods jsonb:='[]'::jsonb;
  transport_id uuid; lpg_id uuid; energy_id uuid; water_id uuid;
  petrol numeric; diesel numeric; dg numeric; lpg_l numeric; grid numeric;
  renewable numeric; consumed numeric; recycled numeric;
  scope1 numeric; scope2 numeric; avoided numeric; lpg_emission numeric;
  missing text[]; body jsonb; digest_hex text; complete_count integer:=0;
begin
  if not app_private.is_admin_mfa() then
    raise exception 'administrator MFA required' using errcode='42501';
  end if;
  if release_version !~ '^20[0-9]{2}-(0[1-9]|1[0-2])$' then
    raise exception 'release version must be YYYY-MM';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('public-release-v2',0));
  for p in select * from app_private.reporting_periods
           where ends_on<=current_date order by starts_on loop
    transport_id:=app_private.release_submission(p.id,'transport');
    lpg_id:=app_private.release_submission(p.id,'lpg');
    energy_id:=app_private.release_submission(p.id,'energy');
    water_id:=app_private.release_submission(p.id,'water');

    -- Explicit public JSON input allowlist. No raw row serialization occurs.
    petrol:=app_private.release_metric_value(transport_id,'transport_petrol_litres');
    diesel:=app_private.release_metric_value(transport_id,'transport_diesel_litres');
    dg:=app_private.release_metric_value(transport_id,'dg_diesel_litres');
    lpg_l:=app_private.release_metric_value(lpg_id,'lpg_consumption_litres');
    grid:=app_private.release_metric_value(energy_id,'grid_total_kwh');
    renewable:=app_private.release_metric_value(energy_id,'renewable_total_kwh');
    consumed:=app_private.release_metric_value(water_id,'water_consumed_kl');
    recycled:=app_private.release_metric_value(water_id,'water_recycled_kl');

    -- Carbon is read only from frozen administrator-approved calculations.
    select sum(c.result_kgco2e) into scope1
      from app_private.approval_calculations c
      where c.submission_id in (transport_id,lpg_id)
        and c.metric_code in ('transport_petrol_litres','transport_diesel_litres',
                              'dg_diesel_litres','lpg_consumption_litres');
    select sum(c.result_kgco2e) into scope2
      from app_private.approval_calculations c
      where c.submission_id=energy_id and c.metric_code='grid_total_kwh';
    select sum(c.result_kgco2e) into avoided
      from app_private.approval_calculations c
      where c.submission_id=energy_id and c.metric_code='renewable_total_kwh';
    select c.result_kgco2e into lpg_emission
      from app_private.approval_calculations c
      where c.submission_id=lpg_id and c.metric_code='lpg_consumption_litres';

    if lpg_id is not null and lpg_l is not null and lpg_emission is null then
      raise exception 'official frozen LPG factor calculation required before release';
    end if;
    if transport_id is null or lpg_id is null then scope1:=null; end if;
    if energy_id is null then scope2:=null; avoided:=null; end if;

    missing:=array_remove(array[
      case when transport_id is null then 'transport' end,
      case when lpg_id is null then 'lpg' end,
      case when energy_id is null then 'energy' end,
      case when water_id is null then 'water' end],null);
    if cardinality(missing)=0 then complete_count:=complete_count+1; end if;

    periods:=periods||jsonb_build_array(jsonb_build_object(
      'year',p.calendar_year,'month',p.calendar_month,
      'carbon',jsonb_build_object(
        'scope1_kgco2e',scope1,'scope2_kgco2e',scope2,
        'total_kgco2e',case when scope1 is null or scope2 is null then null else scope1+scope2 end,
        'avoided_kgco2e',avoided,
        'net_kgco2e',case when scope1 is null or scope2 is null or avoided is null
          then null else scope1+scope2-avoided end,
        'per_capita_kgco2e',null),
      'energy',jsonb_build_object(
        'grid_kwh',grid,'renewable_kwh',renewable,
        'renewable_share_percentage',case
          when grid is null or renewable is null or grid+renewable=0 then null
          else round(renewable*100/(grid+renewable),6) end),
      'fuel',jsonb_build_object('petrol_litres',petrol,'diesel_litres',diesel,
        'dg_diesel_litres',dg),
      'lpg',jsonb_build_object('lpg_litres',lpg_l,'lpg_kgco2e',lpg_emission),
      'water',jsonb_build_object('consumed_kl',consumed,'recycled_kl',recycled,
        'recycling_percentage',case
          when consumed is null or recycled is null or consumed=0 then null
          else round(recycled*100/consumed,6) end),
      'missing_data',to_jsonb(missing)));
  end loop;

  body:=jsonb_build_object(
    'contract_version','2.0',
    'release',jsonb_build_object('version',release_version,'published_at',null,
      'coverage_status',case when jsonb_array_length(periods)>0 and
        complete_count=jsonb_array_length(periods) then 'complete' else 'partial' end),
    'periods',periods);
  digest_hex:=encode(extensions.digest(convert_to(body::text,'UTF8'),'sha256'),'hex');
  insert into app_private.aggregate_releases
    (id,version,status,contract_version,setting_version,content_sha256,generated_by)
  values(rid,release_version,'candidate','2.0',
    (select version from app_private.institution_settings where id=1),digest_hex,auth.uid());
  insert into app_private.public_release_payloads(release_id,payload,latest_complete_period_id)
  values(rid,body,(select id from app_private.reporting_periods
    where ends_on<=current_date order by ends_on desc limit 1));
  insert into app_private.audit_events
    (actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
  values(auth.uid(),'user','release.v2_prepared','release',rid::text,'succeeded',
    jsonb_build_object('content_sha256',digest_hex));
  return rid;
end $$;

create or replace function app_private.publish_public_release_v2(
  target_release uuid,expected_sha256 text)
returns void language plpgsql security definer
set search_path=pg_catalog,auth,app_private,extensions as $$
declare r app_private.aggregate_releases; actual text;
begin
  if not app_private.is_admin_mfa() then
    raise exception 'administrator MFA required' using errcode='42501';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('public-release-v2',0));
  select * into r from app_private.aggregate_releases
    where id=target_release and status='candidate' and contract_version='2.0' for update;
  if r.id is null then raise exception 'v2 candidate release not found'; end if;
  select encode(extensions.digest(convert_to(payload::text,'UTF8'),'sha256'),'hex') into actual
    from app_private.public_release_payloads where release_id=r.id;
  if actual is distinct from expected_sha256 or actual is distinct from r.content_sha256 then
    raise exception 'release checksum mismatch';
  end if;
  update app_private.aggregate_releases set status='superseded'
    where status='active';
  update app_private.aggregate_releases set status='active',published_at=now(),
    published_by=auth.uid(),supersedes_id=(select id from app_private.aggregate_releases
      where status='superseded' order by published_at desc nulls last limit 1)
    where id=r.id;
  insert into app_private.audit_events
    (actor_id,actor_type,event_type,target_type,target_id,outcome,metadata)
  values(auth.uid(),'user','release.v2_published','release',r.id::text,'succeeded',
    jsonb_build_object('content_sha256',actual));
end $$;

create or replace function api.admin_prepare_release(release_version text)
returns jsonb language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare rid uuid;
begin
  rid:=app_private.prepare_public_release_v2(release_version);
  return (select jsonb_build_object('release_ref',r.id,'version',r.version,
    'status',r.status,'contract_version',r.contract_version,
    'content_sha256',r.content_sha256,'generated_at',r.generated_at)
    from app_private.aggregate_releases r where r.id=rid);
end $$;

create or replace function api.admin_release_preview(target_release uuid)
returns jsonb language plpgsql stable security definer
set search_path=pg_catalog,auth,api,app_private as $$
declare result jsonb;
begin
  if not app_private.is_admin_mfa() then
    raise exception 'administrator MFA required' using errcode='42501';
  end if;
  select jsonb_build_object('release_ref',r.id,'status',r.status,
    'content_sha256',r.content_sha256,'payload',p.payload) into result
  from app_private.aggregate_releases r join app_private.public_release_payloads p on p.release_id=r.id
  where r.id=target_release and r.contract_version='2.0';
  return result;
end $$;

create or replace function api.admin_publish_release(target_release uuid,expected_sha256 text)
returns jsonb language plpgsql security definer
set search_path=pg_catalog,auth,api,app_private as $$
begin
  perform app_private.publish_public_release_v2(target_release,expected_sha256);
  return jsonb_build_object('release_ref',target_release,'status','active');
end $$;

create or replace function api.get_dashboard()
returns jsonb language sql stable security definer
set search_path=pg_catalog,api,app_private as $$
  select jsonb_set(p.payload,'{release,published_at}',to_jsonb(r.published_at),true)
  from app_private.public_release_payloads p
  join app_private.aggregate_releases r on r.id=p.release_id
  where r.status='active' and r.contract_version='2.0' limit 1;
$$;

revoke execute on all functions in schema app_private from public,anon,authenticated;
grant execute on function app_private.bootstrap_first_admin(uuid,text),
  app_private.record_evidence_scan(uuid,boolean,text,bigint,text,text),
  app_private.ingest_external_audit(text,text,timestamptz,text,text,text,jsonb) to service_role;
revoke execute on function api.prepare_release(text),api.publish_release(uuid,text)
  from public,anon,authenticated;
grant execute on function api.get_dashboard() to anon,authenticated;
grant execute on function api.admin_prepare_release(text),
  api.admin_release_preview(uuid),api.admin_publish_release(uuid,text) to authenticated;

commit;
