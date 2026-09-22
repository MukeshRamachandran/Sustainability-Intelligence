begin;
insert into app_private.institution_settings(id,academic_year_start_month,manager_email_domain,trusted_admin_email_domain,evidence_retention_years,admin_mfa_required,manager_mfa_required,version)
values(1,6,'kct.ac.in','kclas.ac.in',7,true,false,1) on conflict(id) do nothing;
insert into app_private.metric_definitions(code,domain,display_name,canonical_unit) values
 ('petrol_litres','scope1','Petrol','L'),('diesel_litres','scope1','Transport diesel','L'),
 ('dg_diesel_litres','scope1','DG diesel','L'),('vehicle_count','scope1','Vehicle count','count'),
 ('industrial_kwh','scope2','HT/industrial electricity','kWh'),('temporary_kwh','scope2','Temporary electricity','kWh'),
 ('commercial_kwh','scope2','Commercial electricity','kWh'),('eb_excluding_re_kwh','scope2','Grid electricity excluding RE','kWh'),
 ('procured_re_kwh','renewable','Procured renewable energy','kWh'),('re_on_campus_kwh','renewable','On-campus renewable energy','kWh'),
 ('solar_water_heater_kwh','renewable','Solar water heater equivalent','kWh'),('total_re_kwh','renewable','Total renewable energy','kWh')
on conflict(code) do nothing;
with s as (insert into app_private.emission_factor_sets(version_label,status,jurisdiction,source_citation,valid_from)
 values('v1-institution-confirmation-required','draft',null,null,date '2025-01-01') on conflict(version_label) do update set version_label=excluded.version_label returning id)
insert into app_private.emission_factors(factor_set_id,code,value,input_unit,output_unit,scope,method)
select s.id,v.code,v.factor,v.unit,'kgCO2e',v.scope,'activity multiplied by factor' from s cross join (values
 ('petrol',2.388::numeric,'L',1),('diesel',2.701::numeric,'L',1),('grid',0.727::numeric,'kWh',2)) v(code,factor,unit,scope)
on conflict(factor_set_id,code) do nothing;
commit;
