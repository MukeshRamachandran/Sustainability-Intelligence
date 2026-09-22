const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const root = path.resolve(__dirname, '..');
const dir = path.join(root, 'supabase', 'migrations');
const files = fs.readdirSync(dir).filter((n) => n.endsWith('.sql')).sort();
const sql = Object.fromEntries(files.map((n) => [n, fs.readFileSync(path.join(dir, n), 'utf8')]));
const all = Object.values(sql).join('\n').toLowerCase();

test('migration chain is ordered, transactional, and contains no production credentials', () => {
  assert.deepEqual(files, [
    '0001_extensions_schemas_types.sql','0002_identity_roles_settings_audit.sql',
    '0003_metrics_submissions.sql','0004_private_evidence_storage.sql',
    '0005_review_workflow.sql','0006_emission_factors_calculations.sql',
    '0007_public_releases.sql','0008_auth_storage_audit_integration.sql',
    '0009_authorization_workflow_publication.sql','0010_seed_reference_data.sql',
    '0011_security_integrity_hardening.sql','0012_api_facade.sql',
    '0013_portal_domains_metrics.sql','0014_metric_publication_classification.sql',
    '0015_operational_portal_api.sql','0016_public_release_v2.sql',
    '0017_admin_history_api.sql'
  ]);
  Object.entries(sql).forEach(([name, body]) => {
    assert.match(body, /^begin;/i, name);
    assert.match(body, /commit;\s*$/i, name);
  });
  assert.doesNotMatch(all, /service_role\s*[:=]|eyj[a-z0-9_-]{20,}|postgres(?:ql)?:\/\//i);
});

test('reviewed migration SHA-256 manifest matches current bytes', () => {
  const manifest = fs.readFileSync(path.join(dir, 'SHA256SUMS'), 'utf8').trim().split(/\r?\n/);
  assert.equal(manifest.length, files.length);
  for (const line of manifest) {
    const [, expected, name] = line.match(/^([0-9a-f]{64})  (.+\.sql)$/) || [];
    assert.ok(name && files.includes(name), line);
    const actual = crypto.createHash('sha256').update(fs.readFileSync(path.join(dir, name))).digest('hex');
    assert.equal(actual, expected, name);
  }
});

test('every private table is paired with RLS in its creating migration', () => {
  Object.entries(sql).forEach(([name, body]) => {
    const tables = [...body.matchAll(/create table app_private\.([a-z_]+)/gi)].map((m) => m[1]);
    tables.forEach((table) => assert.match(body,
      new RegExp(`alter table app_private\\.${table} enable row level security`, 'i'), `${name}: ${table}`));
  });
});

test('identity and role controls enforce verified users and one active role', () => {
  const body = sql['0002_identity_roles_settings_audit.sql'] + sql['0009_authorization_workflow_publication.sql'];
  assert.match(body, /email_confirmed_at is not null/i);
  assert.match(body, /one_active_role/i);
  assert.match(body, /manager_email_domain/i);
  assert.match(sql['0010_seed_reference_data.sql'], /'kct\.ac\.in','kclas\.ac\.in'/i);
  assert.match(body, /auth\.jwt\(\)->>'aal'.*aal2/is);
});

test('evidence is private, bounded, one-use, and clean-only', () => {
  const body = sql['0004_private_evidence_storage.sql'];
  assert.match(body, /10485760/);
  assert.match(body, /application\/pdf/);
  assert.match(body, /image\/png/);
  assert.match(body, /status='pending'.*status='uploading'/is);
  assert.match(body, /status='clean'/i);
  assert.match(body, /No authenticated INSERT\/UPDATE\/DELETE policy/i);
  assert.doesNotMatch(body, /create trigger[\s\S]*storage\.objects/i);
});

test('approval, factors, publication, and public projection are separated', () => {
  assert.match(sql['0003_metrics_submissions.sql'], /approved submission is immutable/i);
  assert.match(sql['0009_authorization_workflow_publication.sql'], /approve_submission/);
  assert.match(sql['0009_authorization_workflow_publication.sql'], /publish_release/);
  assert.match(sql['0009_authorization_workflow_publication.sql'], /approval_calculations/);
  assert.match(sql['0007_public_releases.sql'], /security_invoker=true/i);
  assert.match(sql['0007_public_releases.sql'], /where r\.status='active'/i);
});

test('seed decisions preserve June year and unconfirmed draft factors', () => {
  const body = sql['0010_seed_reference_data.sql'];
  assert.match(body, /values\(1,6,'kct\.ac\.in','kclas\.ac\.in',7,true,false,1\)/i);
  assert.match(body, /v1-institution-confirmation-required','draft'/i);
  for (const value of ['2.388','2.701','0.727']) assert.match(body, new RegExp(value.replace('.', '\\.')));
});

test('Data API facade exposes only allowlisted API and revokes private execution', () => {
  const body = sql['0012_api_facade.sql'];
  const config = fs.readFileSync(path.join(root, 'supabase', 'config.toml'), 'utf8');
  assert.match(config, /schemas\s*=\s*\["api"\]/);
  assert.doesNotMatch(config, /schemas\s*=.*app_private/);
  assert.match(body, /revoke execute on all functions in schema app_private from public, anon, authenticated/i);
  assert.match(body, /grant execute on function api\.get_dashboard\(\) to anon,authenticated/i);
  assert.doesNotMatch(body, /grant execute on function api\.(?!get_dashboard)[^;]+ to anon/i);
  assert.doesNotMatch(body, /grant (usage|select|insert|update|delete).*app_private.*(anon|authenticated)/i);
  const definers = [...body.matchAll(/create or replace function api\.[\s\S]*?\$\$;/gi)].map((m) => m[0]);
  assert.ok(definers.length >= 16);
  definers.forEach((fn) => {
    assert.match(fn, /security definer/i);
    assert.match(fn, /set search_path=pg_catalog/);
  });
  assert.doesNotMatch(body, /create or replace function api\..*(evidence_read|audit|bootstrap|scan)/i);
  assert.doesNotMatch(body, /to_jsonb\(x\)/i);
  assert.match(body, /function api\.my_submissions\(\)/i);
  assert.match(body, /function api\.review_queue\(\)/i);
  assert.match(body, /'submission_ref',x\.id,'status',x\.status,'row_version',x\.row_version/i);
  for (const forbidden of ['submitter_id','approved_by','source_description','object_path','quality_note']) {
    const dtoArea = body.slice(body.indexOf('function api.submit_submission'), body.indexOf('function api.prepare_release'));
    assert.equal(dtoArea.includes(`'${forbidden}'`), false, `DTO leaks ${forbidden}`);
  }
  const verification = fs.readFileSync(path.join(root, 'supabase', 'verification', 'phase_b2_verification.sql'), 'utf8');
  assert.doesNotMatch(verification, /not has_table_privilege\('anon','api\.dashboard_master','select'\)/i);
  assert.match(verification, /API authenticated\/PUBLIC ACL mismatch/);
});

test('Phase C1 separates four operational domains from accounting classifications', () => {
  const body = sql['0013_portal_domains_metrics.sql'];
  assert.match(body, /operational_domain as enum\s*\('transport','lpg','energy','water'\)/i);
  assert.match(body, /operational_manager_assignments/i);
  assert.match(body, /has_operational_domain/i);
  assert.match(body, /one active role\/domain assignment only/i);
  assert.match(body, /app_private\.has_operational_domain\(s\.operational_domain\)/i);
  assert.match(body, /coalesce\(x\.operational_domain::text,x\.domain::text\)=effective_domain/i);
  assert.match(body, /revoke all on app_private\.operational_manager_assignments from public,anon,authenticated/i);
  assert.doesNotMatch(body, /grant (usage|select|insert|update|delete).*operational_manager_assignments.*(anon|authenticated)/i);
});

test('Phase C1 defines the complete canonical portal metric contract', () => {
  const body = sql['0013_portal_domains_metrics.sql'];
  const expected = {
    transport: [
      'transport_petrol_litres','transport_diesel_litres','petrol_vehicle_count',
      'diesel_vehicle_count','ev_consumption_kwh','dg_diesel_litres','dg_count'
    ],
    lpg: ['lpg_cylinder_count','lpg_weight_kg','lpg_consumption_litres'],
    energy: [
      'grid_ht_kwh','grid_commercial_kwh','grid_temporary_kwh','grid_total_kwh',
      'renewable_on_campus_kwh','renewable_procured_kwh','solar_water_heater_kwh',
      'renewable_total_kwh'
    ],
    water: [
      'water_twad_kl','water_borewell_kl','water_private_kl','water_consumed_kl',
      'wastewater_generated_kl','water_recycled_kl','inlet_ph','inlet_tss','inlet_tds',
      'inlet_nh3n','inlet_phosphorus','inlet_chloride','inlet_sulphate',
      'inlet_oil_grease','inlet_cod','inlet_bod','outlet_ph','outlet_tss','outlet_tds',
      'outlet_nh3n','outlet_phosphorus','outlet_chloride','outlet_sulphate',
      'outlet_oil_grease','outlet_cod','outlet_bod','stp_inlet_cod','stp_outlet_cod'
    ]
  };
  for (const [domain, metrics] of Object.entries(expected)) {
    for (const metric of metrics) {
      assert.match(body, new RegExp(`'${metric}','${domain}'`, 'i'), `${metric} must belong to ${domain}`);
    }
  }
  assert.match(body, /min_value numeric\(20,6\)/i);
  assert.match(body, /max_value numeric\(20,6\)/i);
  assert.match(body, /zero_allowed boolean not null/i);
  assert.match(body, /display_order smallint/i);
  assert.match(body, /calculation_method text/i);
  assert.match(body, /manager_editable boolean not null/i);
});

test('Phase C1 accounting classifications do not follow manager names', () => {
  const body = sql['0013_portal_domains_metrics.sql'];
  for (const metric of ['transport_petrol_litres','transport_diesel_litres','dg_diesel_litres','lpg_consumption_litres']) {
    assert.match(body, new RegExp(`'${metric}'[\\s\\S]{0,160}'scope1_inventory'`, 'i'), metric);
  }
  assert.match(body, /'grid_total_kwh','energy'[\s\S]{0,160}'scope2_inventory','grid',true/i);
  assert.match(body, /'renewable_total_kwh','energy'[\s\S]{0,160}'avoided_impact','grid',true/i);
  assert.match(body, /'renewable_on_campus_kwh','energy'[\s\S]{0,160}'renewable_reporting'/i);
  const waterRows = body.match(/\('[a-z0-9_]+','water',[\s\S]*?\)/gi) || [];
  assert.ok(waterRows.length >= 28);
  waterRows.forEach((row) => {
    assert.match(row, /'water_reporting'/i);
    assert.doesNotMatch(row, /'scope[12]_inventory'/i);
  });
  assert.match(body, /'ev_consumption_kwh','transport'[\s\S]{0,160}'activity_only'/i);
});

test('Phase C1 calculated totals are database-owned and preserve null versus zero', () => {
  const body = sql['0013_portal_domains_metrics.sql'];
  assert.match(body, /grid_ht_kwh \+ grid_commercial_kwh \+ grid_temporary_kwh/i);
  assert.match(body, /renewable_on_campus_kwh \+ renewable_procured_kwh \+ solar_water_heater_kwh/i);
  assert.match(body, /water_twad_kl \+ water_borewell_kl \+ water_private_kl/i);
  for (const metric of ['grid_total_kwh','renewable_total_kwh','water_consumed_kl']) {
    assert.match(body, new RegExp(`'${metric}'[\\s\\S]{0,220},false\\)`, 'i'), `${metric} must not be manager editable`);
  }
  assert.match(body, /calculated metric is not directly editable/i);
  assert.match(body, /count\(\*\)=3 and count\(value\)=3 then sum\(value\)/i);
  assert.match(body, /new\.value is not null/i);
  assert.match(body, /new\.value=0 and not m\.zero_allowed/i);
});

test('Phase C1 keeps public dashboard access approved-release only', () => {
  const facade = sql['0012_api_facade.sql'];
  const release = sql['0007_public_releases.sql'];
  assert.match(facade, /function api\.get_dashboard\(\)[\s\S]*where r\.status='active'/i);
  assert.match(facade, /grant execute on function api\.get_dashboard\(\) to anon,authenticated/i);
  assert.match(release, /where r\.status='active'/i);
  assert.doesNotMatch(sql['0013_portal_domains_metrics.sql'], /grant .* to anon/i);
});

test('Phase C1.1 publication classes are explicit and fail closed', () => {
  const body = sql['0014_metric_publication_classification.sql'];
  assert.match(body, /publication_class as enum\s*\('public_aggregate','admin_only','internal_verification'\)/i);
  assert.match(body, /add column publication_class app_private\.publication_class\s+not null default 'admin_only'/i);
  assert.match(body, /alter column publication_class drop default/i);
  assert.match(body, /metric_public_aggregate_exact_allowlist/i);
  assert.match(body, /metric_internal_verification_exact_allowlist/i);
  assert.match(body, /water_verification_never_public/i);
  assert.match(body, /public_count<>8 or internal_count<>22 or operational_count<>46/i);
});

test('Phase C1.1 exposes exactly the eight approved public aggregate inputs', () => {
  const body = sql['0014_metric_publication_classification.sql'];
  const expected = [
    'transport_petrol_litres','transport_diesel_litres','dg_diesel_litres',
    'lpg_consumption_litres','grid_total_kwh','renewable_total_kwh',
    'water_consumed_kl','water_recycled_kl'
  ].sort();
  const update = body.match(/set publication_class='public_aggregate'[\s\S]*?where code in \(([\s\S]*?)\);/i);
  assert.ok(update, 'public aggregate classification update missing');
  const actual = [...update[1].matchAll(/'([a-z][a-z0-9_]+)'/g)].map((m) => m[1]).sort();
  assert.deepEqual(actual, expected);
  assert.match(body, /publication_class<>'public_aggregate' or code in/i);
});

test('Phase C1.1 keeps every lab and STP metric internal verification only', () => {
  const body = sql['0014_metric_publication_classification.sql'];
  const expected = [
    'inlet_ph','inlet_tss','inlet_tds','inlet_nh3n','inlet_phosphorus',
    'inlet_chloride','inlet_sulphate','inlet_oil_grease','inlet_cod','inlet_bod',
    'outlet_ph','outlet_tss','outlet_tds','outlet_nh3n','outlet_phosphorus',
    'outlet_chloride','outlet_sulphate','outlet_oil_grease','outlet_cod','outlet_bod',
    'stp_inlet_cod','stp_outlet_cod'
  ].sort();
  const update = body.match(/set publication_class='internal_verification'[\s\S]*?where code in \(([\s\S]*?)\);/i);
  assert.ok(update, 'internal verification classification update missing');
  const actual = [...update[1].matchAll(/'([a-z][a-z0-9_]+)'/g)].map((m) => m[1]).sort();
  assert.deepEqual(actual, expected);
  assert.match(body, /release_payload_rejects_internal_metrics/i);
  assert.match(body, /internal verification metric forbidden from public release/i);
});

test('Phase C1.1 leaves remaining operational metrics admin only by conservative backfill', () => {
  const c1 = sql['0013_portal_domains_metrics.sql'];
  const c11 = sql['0014_metric_publication_classification.sql'];
  const operational = [...c1.matchAll(/\('([a-z][a-z0-9_]+)','(transport|lpg|energy|water)'/g)]
    .map((m) => m[1]).filter((code) => code !== 'transport');
  const publicUpdate = c11.match(/set publication_class='public_aggregate'[\s\S]*?where code in \(([\s\S]*?)\);/i)[1];
  const internalUpdate = c11.match(/set publication_class='internal_verification'[\s\S]*?where code in \(([\s\S]*?)\);/i)[1];
  const classified = new Set([...publicUpdate.matchAll(/'([a-z][a-z0-9_]+)'/g),
    ...internalUpdate.matchAll(/'([a-z][a-z0-9_]+)'/g)].map((m) => m[1]));
  const adminOnly = operational.filter((code) => !classified.has(code));
  assert.equal(operational.length, 46);
  assert.equal(adminOnly.length, 16);
  for (const code of ['petrol_vehicle_count','diesel_vehicle_count','ev_consumption_kwh','dg_count',
    'lpg_cylinder_count','lpg_weight_kg','grid_ht_kwh','grid_commercial_kwh','grid_temporary_kwh',
    'renewable_on_campus_kwh','renewable_procured_kwh','solar_water_heater_kwh',
    'water_twad_kl','water_borewell_kl','water_private_kl','wastewater_generated_kl']) {
    assert.ok(adminOnly.includes(code), code);
  }
});

test('Phase C1.1 does not alter the approved-only public API boundary', () => {
  const body = sql['0014_metric_publication_classification.sql'];
  const facade = sql['0012_api_facade.sql'];
  const getDashboard = facade.slice(facade.indexOf('function api.get_dashboard'), facade.indexOf('function api.create_draft'));
  assert.doesNotMatch(body, /create or replace function api\./i);
  assert.doesNotMatch(body, /grant .* to anon/i);
  assert.match(body, /revoke all on app_private\.metric_definitions from public,anon,authenticated/i);
  assert.match(getDashboard, /from app_private\.public_release_payloads/i);
  assert.match(getDashboard, /where r\.status='active' limit 1/i);
  assert.doesNotMatch(getDashboard, /metric_definitions|submission_values|submissions/i);
  assert.doesNotMatch(body, /all_metrics|to_jsonb\(submission\)/i);
});

test('Phase C1.3 manager API enforces operational domain and edit-state boundaries', () => {
  const body = sql['0015_operational_portal_api.sql'];
  for (const rpc of ['my_access','list_reporting_periods','create_draft','set_submission_value',
    'get_my_draft','submit_submission','my_submissions','evidence_upload_authorization']) {
    assert.match(body, new RegExp(`function api\\.${rpc}\\(`, 'i'), rpc);
  }
  assert.match(body, /app_private\.has_operational_domain\(d\)/i);
  assert.match(body, /m\.operational_domain=d/i);
  assert.match(body, /status in \('draft','correction_requested'\)/i);
  assert.match(body, /not m\.manager_editable/i);
  assert.match(body, /calculated metric is not directly editable/i);
  assert.match(body, /controlled_server/i);
  assert.match(body, /grant execute on function api\.get_dashboard\(\) to anon,authenticated/i);
  assert.doesNotMatch(body, /grant execute on function api\.my_access\(\)[\s\S]{0,80}to anon/i);
});

test('Phase C1.3 public release v2 is approved, classified, frozen and explicitly shaped', () => {
  const body = sql['0016_public_release_v2.sql'];
  assert.match(body, /m\.publication_class='public_aggregate'/i);
  assert.match(body, /s\.status='approved'/i);
  assert.match(body, /approval_calculations/i);
  assert.match(body, /official frozen LPG factor calculation required before release/i);
  for (const key of ['scope1_kgco2e','scope2_kgco2e','total_kgco2e','avoided_kgco2e',
    'net_kgco2e','per_capita_kgco2e','grid_kwh','renewable_kwh',
    'renewable_share_percentage','petrol_litres','diesel_litres','dg_diesel_litres',
    'lpg_litres','lpg_kgco2e','consumed_kl','recycled_kl','recycling_percentage','missing_data']) {
    assert.match(body, new RegExp(`'${key}'`, 'i'), key);
  }
  assert.match(body, /grid is null or renewable is null or grid\+renewable=0 then null/i);
  assert.match(body, /consumed is null or recycled is null or consumed=0 then null/i);
  assert.match(body, /where r\.status='active' and r\.contract_version='2\.0'/i);
  assert.doesNotMatch(body, /all_metrics|evidence_files|quality_note|review_actions|manager_email/i);
  for (const lab of ['inlet_ph','outlet_ph','stp_inlet_cod','stp_outlet_cod']) {
    assert.doesNotMatch(body, new RegExp(lab, 'i'), lab);
  }
});

test('Phase C1.3 admin history stays MFA protected and evidence uses expiring audited grants', () => {
  const body = sql['0017_admin_history_api.sql'];
  for (const rpc of ['admin_submission_history','admin_submission_detail','admin_water_history',
    'admin_review_history','admin_evidence_link']) {
    const start = body.indexOf(`function api.${rpc}`);
    assert.ok(start >= 0, rpc);
    assert.match(body.slice(start, start + 900), /is_admin_mfa\(\)/i, `${rpc} MFA`);
  }
  assert.match(body, /publication_class/i);
  assert.match(body, /internal_verification/i);
  assert.match(body, /now\(\)\+interval '5 minutes'/i);
  assert.match(body, /evidence\.read_grant_created/i);
  assert.match(body, /trusted_server_signed_url_exchange/i);
  assert.doesNotMatch(body, /grant execute on function api\.admin_[\s\S]* to anon/i);
});

test('Phase C1.3 final grants keep anon on dashboard only and retire v1 publish access', () => {
  const body = sql['0017_admin_history_api.sql'];
  assert.match(body, /revoke execute on all functions in schema api from public,anon,authenticated/i);
  assert.match(body, /grant execute on function api\.get_dashboard\(\) to anon,authenticated/i);
  assert.match(sql['0016_public_release_v2.sql'], /revoke execute on function api\.prepare_release\(text\),api\.publish_release\(uuid,text\)/i);
  assert.match(body, /revoke all on schema app_private from public,anon,authenticated/i);
});
