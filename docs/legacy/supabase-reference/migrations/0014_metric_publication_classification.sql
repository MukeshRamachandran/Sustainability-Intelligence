begin;

-- Publication eligibility is independent from operational ownership and carbon
-- accounting. public_aggregate permits use only inside an explicitly shaped,
-- approved release; it never grants direct access to raw metric/submission rows.
create type app_private.publication_class as enum
  ('public_aggregate','admin_only','internal_verification');

-- The temporary default performs a conservative backfill of every legacy and
-- operational definition. Dropping it afterwards makes future definitions fail
-- unless their publication class is explicitly chosen.
alter table app_private.metric_definitions
  add column publication_class app_private.publication_class
  not null default 'admin_only';
alter table app_private.metric_definitions
  alter column publication_class drop default;

-- Only these reviewed aggregate inputs are eligible to contribute to a public
-- release. Raw submission rows remain private and are never published directly.
update app_private.metric_definitions
set publication_class='public_aggregate'
where code in (
  'transport_petrol_litres',
  'transport_diesel_litres',
  'dg_diesel_litres',
  'lpg_consumption_litres',
  'grid_total_kwh',
  'renewable_total_kwh',
  'water_consumed_kl',
  'water_recycled_kl'
);

-- Laboratory and STP readings are retained for authorized history,
-- verification, audit, and future internal reporting only.
update app_private.metric_definitions
set publication_class='internal_verification'
where code in (
  'inlet_ph','inlet_tss','inlet_tds','inlet_nh3n','inlet_phosphorus',
  'inlet_chloride','inlet_sulphate','inlet_oil_grease','inlet_cod','inlet_bod',
  'outlet_ph','outlet_tss','outlet_tds','outlet_nh3n','outlet_phosphorus',
  'outlet_chloride','outlet_sulphate','outlet_oil_grease','outlet_cod','outlet_bod',
  'stp_inlet_cod','stp_outlet_cod'
);

-- Fail closed if the preceding C1 definitions are incomplete or renamed.
do $$
declare public_count integer; internal_count integer; operational_count integer;
begin
  select count(*) into public_count from app_private.metric_definitions
  where publication_class='public_aggregate';
  select count(*) into internal_count from app_private.metric_definitions
  where publication_class='internal_verification';
  select count(*) into operational_count from app_private.metric_definitions
  where operational_domain is not null;
  if public_count<>8 or internal_count<>22 or operational_count<>46 then
    raise exception 'metric publication classification source mismatch: public %, internal %, operational %',
      public_count,internal_count,operational_count;
  end if;
end $$;

-- These constraints make the two sensitive allowlists structural rather than
-- conventions. Any future public metric requires a reviewed migration that
-- deliberately changes this contract.
alter table app_private.metric_definitions
  add constraint metric_public_aggregate_exact_allowlist check (
    publication_class<>'public_aggregate' or code in (
      'transport_petrol_litres','transport_diesel_litres','dg_diesel_litres',
      'lpg_consumption_litres','grid_total_kwh','renewable_total_kwh',
      'water_consumed_kl','water_recycled_kl'
    )
  ),
  add constraint metric_internal_verification_exact_allowlist check (
    publication_class<>'internal_verification' or code in (
      'inlet_ph','inlet_tss','inlet_tds','inlet_nh3n','inlet_phosphorus',
      'inlet_chloride','inlet_sulphate','inlet_oil_grease','inlet_cod','inlet_bod',
      'outlet_ph','outlet_tss','outlet_tds','outlet_nh3n','outlet_phosphorus',
      'outlet_chloride','outlet_sulphate','outlet_oil_grease','outlet_cod','outlet_bod',
      'stp_inlet_cod','stp_outlet_cod'
    )
  ),
  add constraint water_verification_never_public check (
    code not in (
      'inlet_ph','inlet_tss','inlet_tds','inlet_nh3n','inlet_phosphorus',
      'inlet_chloride','inlet_sulphate','inlet_oil_grease','inlet_cod','inlet_bod',
      'outlet_ph','outlet_tss','outlet_tds','outlet_nh3n','outlet_phosphorus',
      'outlet_chloride','outlet_sulphate','outlet_oil_grease','outlet_cod','outlet_bod',
      'stp_inlet_cod','stp_outlet_cod'
    ) or publication_class='internal_verification'
  );

-- Defense in depth for future release builders: a candidate payload containing
-- an internal-verification metric code is rejected even before publication.
-- The future builder must additionally filter public_aggregate definitions and
-- construct an explicit JSON field allowlist; generic metric serialization is
-- not authorized by this migration.
create or replace function app_private.reject_internal_metrics_in_release()
returns trigger language plpgsql security definer
set search_path=pg_catalog,app_private as $$
declare forbidden_code text;
begin
  select m.code into forbidden_code
  from app_private.metric_definitions m
  where m.publication_class='internal_verification'
    and position(to_jsonb(m.code)::text in new.payload::text)>0
  order by m.code limit 1;
  if forbidden_code is not null then
    raise exception 'internal verification metric forbidden from public release: %',
      forbidden_code using errcode='42501';
  end if;
  return new;
end $$;

create trigger release_payload_rejects_internal_metrics
before insert on app_private.public_release_payloads
for each row execute function app_private.reject_internal_metrics_in_release();

-- Reassert the private boundary. This migration creates no API routine and
-- intentionally leaves api.get_dashboard() and the API allowlist unchanged.
revoke all on type app_private.publication_class from public,anon,authenticated;
revoke all on function app_private.reject_internal_metrics_in_release()
  from public,anon,authenticated;
revoke all on app_private.metric_definitions from public,anon,authenticated;

commit;
