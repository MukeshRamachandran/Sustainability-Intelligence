const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');

function adapterContext(fetchImpl) {
  const window = { location: { hostname: '127.0.0.1', port: '3001' } };
  vm.runInNewContext(read('public-api.js'), { window, fetch: fetchImpl, Object, Number, String, Error });
  return window.KCOSMOSPublicAPI;
}

test('index loads the public adapter before its API data loader and app', () => {
  const html = read('index.html');
  assert.ok(html.indexOf('public-api.js') < html.indexOf('public-data-loader.js'));
  assert.ok(html.indexOf('public-data-loader.js') < html.indexOf('app.js'));
  assert.doesNotMatch(html, /<script[^>]+src="calculations\.js/);
  assert.doesNotMatch(html, /<script[^>]+src="data-loader\.js/);
});

test('Chart.js and the treemap plugin are vendored locally, loaded before app.js', () => {
  // An unreachable CDN previously left window.Chart undefined, throwing
  // "Chart is not defined" at the dashboard script's first chart call and
  // making the whole page inert. Pinned local copies remove that single
  // point of failure without changing chart logic or the pinned versions.
  const html = read('index.html');
  assert.match(html, /<script src="vendor\/chart\.umd\.min\.js"><\/script>/);
  assert.match(html, /<script src="vendor\/chartjs-chart-treemap\.min\.js"><\/script>/);
  assert.doesNotMatch(html, /cdnjs\.cloudflare\.com\/ajax\/libs\/Chart\.js/);
  assert.doesNotMatch(html, /cdn\.jsdelivr\.net\/npm\/chartjs-chart-treemap/);
  assert.ok(html.indexOf('vendor/chart.umd.min.js') < html.indexOf('vendor/chartjs-chart-treemap.min.js'));
  assert.ok(html.indexOf('vendor/chartjs-chart-treemap.min.js') < html.indexOf('app.js'));

  const chartFile = fs.readFileSync(path.join(root, 'vendor/chart.umd.min.js'), 'utf8');
  const treemapFile = fs.readFileSync(path.join(root, 'vendor/chartjs-chart-treemap.min.js'), 'utf8');
  assert.ok(chartFile.length > 50000, 'vendored Chart.js should be the full UMD bundle, not a stub');
  assert.match(treemapFile, /chartjs-chart-treemap v3\.1\.0/, 'must be the pinned 3.1.0 build, not an upgrade');
});

test('a chart-rendering failure cannot block non-chart content from rendering', () => {
  const app = read('app.js');
  const refreshBody = app.slice(app.indexOf('function refresh()'), app.indexOf('function refresh()') + 800);
  assert.match(refreshBody, /try\s*\{\s*[\s\S]*?drawCharts\(\);\s*[\s\S]*?\}\s*catch/);
  // renderTable() and the animation hooks must still be reachable after a
  // chart failure, i.e. outside the try block, not inside it.
  const afterCatch = refreshBody.slice(refreshBody.indexOf('catch'));
  assert.match(afterCatch, /renderTable\(\);/);
});

test('missing comparison years and error-state trend years do not throw', () => {
  const app = read('app.js');
  assert.match(app, /!d \|\| !py \|\| !Array\.isArray\(d\[arrName\]\) \|\| !Array\.isArray\(py\[arrName\]\)/);
  assert.match(app, /if \(!d\) return;/);
  assert.match(app, /const d25 = trendYear\(data\[2025\]\), d26 = trendYear\(data\[2026\]\);/);
});

test('adapter normalizes the active immutable release and preserves governed LPG litre state', async () => {
  let requested;
  const api = adapterContext(async (url, options) => {
    requested = { url, options };
    return {
      ok: true,
      json: async () => ({
        release: { version: '2026-09-v1', published_at: '2026-09-22T10:00:00Z' },
        schema_version: '1.1', period: { id: 'period', year: 2026, month: 9 },
        lpg: {
          metrics: { lpg_consumption_litres: { value: 52, unit: 'L' } },
          calculations: [{
            calculation_code: 'lpg_emissions', status: 'unavailable', reason: 'factor_not_configured',
            activity_value: 52, activity_unit: 'L', result_value: null
          }]
        }
      })
    };
  });
  const result = await api.load();
  assert.equal(requested.url, '/api/public/dashboard');
  assert.equal(requested.options.credentials, 'omit');
  assert.equal(result.state, 'published');
  assert.equal(api.metric(result.domains.lpg, 'lpg_consumption_litres').value, 52);
  // The superseded kg metric is not published and must read as unavailable.
  assert.equal(api.metric(result.domains.lpg, 'lpg_weight_kg').status, 'unavailable');
  const lpgEmission = api.calculation(result.domains.lpg, 'lpg_emissions');
  assert.equal(lpgEmission.code, 'lpg_emissions');
  assert.equal(lpgEmission.status, 'unavailable');
  assert.equal(lpgEmission.value, null);
  assert.equal(lpgEmission.reason, 'factor_not_configured');
  assert.equal(lpgEmission.activityValue, 52);
  assert.equal(lpgEmission.activityUnit, 'L');
});

test('adapter preserves the schema 1.3 governed population and operational indicators', async () => {
  const api = adapterContext(async () => ({
    ok: true,
    json: async () => ({
      release: { version: 'sustainability-2026-09-v1' },
      schema_version: '1.3',
      period: { id: 'period', year: 2026, month: 9 },
      population: {
        status: 'available', value: 6991, unit: 'people', effective_year: 2026,
        source_reference: 'Project-owner decision for 2026'
      },
      indicators: {
        scope1_tco2e: { status: 'available', value: 3, unit: 'tCO2e' },
        scope2_tco2e: { status: 'available', value: 2, unit: 'tCO2e' },
        operational_ghg_tco2e: { status: 'available', value: 5, unit: 'tCO2e' },
        operational_ghg_per_capita_kgco2e: { status: 'available', value: 0.715, unit: 'kgCO2e/person' },
        waste_per_capita_kg: { status: 'available', value: 2.5, unit: 'kg/person' }
      }
    })
  }));
  const result = await api.load();
  assert.equal(result.release.schemaVersion, '1.3');
  assert.equal(result.population.value, 6991);
  assert.equal(result.population.effective_year, 2026);
  assert.equal(api.indicator(result.raw, 'operational_ghg_tco2e').value, 5);
  assert.equal(api.indicator(result.raw, 'operational_ghg_per_capita_kgco2e').value, 0.715);
  assert.equal(api.indicator(result.raw, 'waste_per_capita_kg').value, 2.5);
});

test('adapter loads published history only from the public history contract', async () => {
  let requested;
  const api = adapterContext(async (url, options) => {
    requested = { url, options };
    return {
      ok: true,
      json: async () => [{
        release: { version: '2026-09-v1', published_at: '2026-09-22T10:00:00Z' },
        schema_version: '1.1', period: { id: 'period', year: 2026, month: 9 }
      }]
    };
  });
  const result = await api.loadHistory();
  assert.equal(requested.url, '/api/public/dashboard/history');
  assert.equal(requested.options.credentials, 'omit');
  assert.equal(result.releases.length, 1);
  assert.equal(result.releases[0].release.version, '2026-09-v1');
});

test('adapter returns an explicit error state without fabricating data', async () => {
  const api = adapterContext(async () => { throw new Error('offline'); });
  const result = await api.load();
  assert.equal(result.state, 'error');
  assert.equal(result.release, null);
  assert.equal(result.domains.transport, null);
});

test('active loader has no governed CSV, JSON overlay, or emission-factor calculation path', () => {
  const loader = read('public-data-loader.js');
  assert.match(loader, /KCOSMOSPublicAPI\.load/);
  assert.match(loader, /KCOSMOSPublicAPI\.loadHistory/);
  assert.doesNotMatch(loader, /transport_master|dg_master|lpg_master|energy_master|water_master|outreach_master|emission_factors|dashboard_master/);
  assert.doesNotMatch(loader, /Calculations\.(co2e|renewableAvoidedEmissions)/);
  assert.doesNotMatch(loader, /2\.388|2\.701|0\.727|0\.71|1\.5571|2\.939/);
  assert.match(loader, /lpg_consumption_litres/);
  assert.doesNotMatch(loader, /lpg_weight_kg/);
  // No file on the loaded governed path may carry a factor constant.
  for (const file of ['public-api.js', 'public-data-loader.js', 'app.js']) {
    assert.doesNotMatch(read(file), /2\.388|2\.701|0\.727|0\.71|1\.5571|2\.939/, file);
  }
  assert.match(loader, /waste_master\.csv/);
  assert.match(loader, /green_master\.csv/);
});

test('staging helper proxies both public routes and nothing else', () => {
  const server = read('serve-staging.py');
  // Both routes the adapter consumes must reach the Main API; the history
  // route was previously missing, which silently emptied every trend.
  for (const route of ['/api/public/dashboard', '/api/public/dashboard/history']) {
    assert.ok(server.includes(`"${route}"`), `serve-staging.py must proxy ${route}`);
  }
  const adapter = read('public-api.js');
  for (const route of ['/api/public/dashboard', '/api/public/dashboard/history']) {
    assert.ok(adapter.includes(`'${route}'`), `public-api.js must request ${route}`);
  }
  // The proxy stays narrow: no authenticated or admin path may pass through.
  assert.doesNotMatch(server, /\/api\/(auth|admin|manager)/);
  assert.match(server, /PUBLIC_ROUTES/);
});

test('governed waste comes from the published release, never waste_master.csv', () => {
  const loader = read('public-data-loader.js');
  // Waste is a governed Manager domain now: the loader neither fetches the CSV
  // nor keeps a parser for it. (Comments may still explain why it is gone.)
  const code = loader.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
  assert.doesNotMatch(code, /waste_master\.csv/);
  assert.doesNotMatch(code, /staticWaste/);
  assert.match(loader, /wet_waste_generated_kg/);
  assert.match(loader, /dry_waste_generated_kg/);
  assert.match(loader, /total_waste_generated_kg/);
  assert.match(loader, /publication\.domains\.waste/);
  // Green cover remains legitimately static.
  assert.match(loader, /green_master\.csv/);

  const app = read('app.js');
  // No browser-side authoritative waste totals: the published total is used
  // as-is, and a missing month is not coerced to zero.
  assert.doesNotMatch(app, /d\.wetWaste \|\| 0/);
  assert.doesNotMatch(app, /d\.dryWaste \|\| 0/);
  assert.match(app, /const wasteHasData = publishedWaste && wasteTotalKg != null/);
  assert.doesNotMatch(app, /wetWasteKg \+ dryWasteKg/);
});

test('waste adapter reads published metrics, categories and materials', async () => {
  const api = adapterContext(async () => ({
    ok: true,
    json: async () => ({
      release: { version: '2026-09-v1', published_at: '2026-09-22T10:00:00Z' },
      schema_version: '1.2', period: { id: 'period', year: 2026, month: 9 },
      waste: {
        metrics: {
          wet_waste_generated_kg: { value: 300, unit: 'kg' },
          dry_waste_generated_kg: { value: 176, unit: 'kg' },
          total_waste_generated_kg: { value: 476, unit: 'kg' }
        },
        categories: [{ code: 'PLASTIC', display_name: 'Plastic', quantity_kg: 50.5 }],
        materials: [{
          code: 'PET', display_name: 'PET', category_code: 'PLASTIC',
          category_display_name: 'Plastic', quantity_kg: 50.5
        }]
      }
    })
  }));
  const result = await api.load();
  assert.equal(result.release.schemaVersion, '1.2');
  assert.equal(api.metric(result.domains.waste, 'wet_waste_generated_kg').value, 300);
  assert.equal(api.metric(result.domains.waste, 'dry_waste_generated_kg').value, 176);
  assert.equal(api.metric(result.domains.waste, 'total_waste_generated_kg').value, 476);
  assert.equal(result.domains.waste.categories[0].quantity_kg, 50.5);
  assert.equal(result.domains.waste.materials[0].category_display_name, 'Plastic');
});

test('an unpublished waste period reports unavailable rather than zero', async () => {
  const api = adapterContext(async () => ({
    ok: true,
    json: async () => ({
      release: { version: 'v1', published_at: '2026-09-22T10:00:00Z' },
      schema_version: '1.2', period: { id: 'p', year: 2026, month: 9 }, waste: null
    })
  }));
  const result = await api.load();
  assert.equal(result.domains.waste, null);
  const metric = api.metric(result.domains.waste, 'total_waste_generated_kg');
  assert.equal(metric.status, 'unavailable');
  assert.equal(metric.value, null);
});

test('active display marks full GHG and unresolved methodology values unavailable', () => {
  const app = read('app.js');
  assert.match(app, /Operational GHG Emissions — Scope 1 \+ Scope 2/);
  assert.match(app, /Not published for this period/);
  assert.match(app, /Not published/);
  assert.doesNotMatch(app, /2\.388|2\.701|0\.727|0\.71|1\.5571|2\.939/);
  assert.doesNotMatch(app, /Calculations\./);
  // LPG is displayed on its governed litre basis; the superseded kg series is gone.
  assert.match(app, /lpgL/);
  assert.doesNotMatch(app, /lpgKg/);
  assert.match(app, /'LPG consumption', valFor\(d, d\.lpgL, month\), 'L'/);
});

// ---- Public dashboard completeness audit --------------------------------

const calc = (code, value, unit = 'tCO2e') => ({
  calculation_code: code, status: 'available', result_value: value, result_unit: unit, reason: null,
  activity_value: 1, activity_unit: 'L', factor_value: 1, factor_unit: 'kgCO2e/L'
});
function publishedPayload(overrides = {}) {
  return {
    release: { version: 'sustainability-2026-09-v2', published_at: '2026-09-24T05:34:32Z', checksum_sha256: 'f'.repeat(64) },
    schema_version: '1.3', period: { id: 'p', year: 2026, month: 9 },
    population: { status: 'available', value: 6991, unit: 'people', effective_year: 2026 },
    publication_status: {},
    indicators: {
      scope1_tco2e: { status: 'available', value: 9.189255, unit: 'tCO2e' },
      scope2_tco2e: { status: 'available', value: 2.569945, unit: 'tCO2e' },
      operational_ghg_tco2e: { status: 'available', value: 11.7592, unit: 'tCO2e' },
      operational_ghg_per_capita_kgco2e: { status: 'available', value: 1.682048, unit: 'kgCO2e/person' },
      waste_per_capita_kg: { status: 'unavailable', value: null, unit: 'kg/person' },
      total_ghg_tco2e: { status: 'unavailable', value: null, unit: 'tCO2e', reason: 'methodology_under_review' },
      avoided_emissions_tco2e: { status: 'unavailable', value: null, unit: 'tCO2e', reason: 'methodology_under_review' },
      renewable_share_percent: { status: 'unavailable', value: null, unit: '%', reason: 'methodology_under_review' }
    },
    transport: {
      metrics: {
        transport_petrol_litres: { value: 3443, unit: 'L' }, transport_diesel_litres: { value: 123, unit: 'L' },
        dg_diesel_litres: { value: 234, unit: 'L' }
      },
      calculations: [
        calc('transport_petrol_emissions', 8.221884), calc('transport_diesel_emissions', 0.332223),
        calc('dg_diesel_emissions', 0.632034)
      ]
    },
    energy: {
      metrics: { grid_total_kwh: { value: 3535, unit: 'kWh' }, renewable_total_kwh: { value: 92, unit: 'kWh' } },
      calculations: [calc('grid_electricity_emissions', 2.569945, 'tCO2e')]
    },
    lpg: {
      metrics: { lpg_consumption_litres: { value: 2, unit: 'L' } },
      emissions: { status: 'available', value: 0.003114, unit: 'tCO2e', reason: null },
      calculations: [calc('lpg_emissions', 0.003114)]
    },
    water: null, outreach: null, waste: null,
    ...overrides
  };
}
async function loadDashboardWith(payload, history = [payload]) {
  const routes = { '/api/public/dashboard': payload, '/api/public/dashboard/history': history };
  const window = { location: { hostname: '127.0.0.1', port: '3001' } };
  const fetchImpl = async url => (routes[url]
    ? { ok: true, json: async () => routes[url], text: async () => '' }
    : { ok: false, text: async () => '' });
  const sandbox = { window, fetch: fetchImpl, Object, Number, String, Error, Array, Math, Date, Promise, JSON };
  vm.runInNewContext(read('public-api.js'), sandbox);
  vm.runInNewContext(read('public-data-loader.js'), sandbox);
  return window.loadDashboardData();
}

test('governed emission components reach the dashboard arrays from the frozen release', async () => {
  const { data, history } = await loadDashboardWith(publishedPayload());
  const item = data['2026'], sep = 8;
  assert.equal(history.releases.length, 1, 'one genuinely published month is not a history failure');
  assert.equal(item.petrolEm[sep], 8.221884);
  assert.equal(item.trDieselEm[sep], 0.332223);
  assert.equal(item.dgEm[sep], 0.632034);
  assert.equal(item.lpgEm[sep], 0.003114);
  assert.equal(item.elecEm[sep], 2.569945);
  // Every other month is missing, never zero.
  item.petrolEm.forEach((value, index) => { if (index !== sep) assert.equal(value, null); });
  item.elecEm.forEach((value, index) => { if (index !== sep) assert.equal(value, null); });
  item.publishedMonths.forEach((value, index) => assert.equal(value, index === sep));
});

test('calculation factors stay attached to the published month that supplied each result', async () => {
  const september = publishedPayload();
  const august = publishedPayload();
  august.period.month = 8;
  august.transport.calculations[0].factor_value = 2.4;
  august.transport.calculations[1].factor_value = 2.7;
  august.transport.calculations[2].factor_value = 2.7;
  august.energy.calculations[0].factor_value = 0.73;
  august.lpg.calculations[0].factor_value = 1.6;
  const { data } = await loadDashboardWith(september, [august, september]);
  const item = data['2026'];
  assert.equal(item.petrolEF[7], 2.4);
  assert.equal(item.petrolEF[8], 1);
  assert.equal(item.trDieselEF[7], 2.7);
  assert.equal(item.dgEF[7], 2.7);
  assert.equal(item.gridEF[7], 0.73);
  assert.equal(item.gridEF[8], 1);
  assert.equal(item.lpgEF[7], 1.6);
  assert.equal(item.lpgEF[8], 1);
  const app = read('app.js');
  for (const field of ['petrolEF', 'trDieselEF', 'dgEF', 'gridEF', 'lpgEF']) {
    assert.match(app, new RegExp(`d\\.${field}\\[i\\]`));
  }
  assert.doesNotMatch(app, /\bEF\.(?:petrol|diesel|grid|lpg)\b/);
});

test('published zero, missing values, and methodology-unavailable remain distinct', async () => {
  const payload = publishedPayload();
  payload.energy.metrics.grid_total_kwh.value = 0;
  payload.energy.metrics.grid_commercial_kwh = { value: null, unit: 'kWh' };
  payload.energy.calculations[0].result_value = 0;
  payload.indicators.scope2_tco2e.value = 0;
  const api = adapterContext(async () => ({ ok: true, json: async () => payload }));
  const release = await api.load();
  const zeroMetric = api.metric(release.domains.energy, 'grid_total_kwh');
  const missingMetric = api.metric(release.domains.energy, 'grid_commercial_kwh');
  const zeroCalculation = api.calculation(release.domains.energy, 'grid_electricity_emissions');
  const zeroIndicator = api.indicator(release.raw, 'scope2_tco2e');
  const unavailableMethod = api.indicator(release.raw, 'avoided_emissions_tco2e');
  assert.deepEqual([zeroMetric.status, zeroMetric.value], ['available', 0]);
  assert.deepEqual([missingMetric.status, missingMetric.value], ['unavailable', null]);
  assert.equal(zeroCalculation.value, 0);
  assert.equal(zeroIndicator.value, 0);
  assert.equal(unavailableMethod.value, null);
  assert.equal(unavailableMethod.reason, 'methodology_under_review');
});

test('month-bound scalar release blocks are hidden for unpublished months', () => {
  const app = read('app.js');
  assert.match(app, /function selectionHasPublication\(d, month\)/);
  assert.match(app, /published\[\+month\] === true/);
  assert.match(app, /const publishedWaste = hasPublication &&/);
  assert.match(app, /hasPublication \? waterRecycled : null/);
  assert.match(app, /outreach\.month === \+month \+ 1/);
  assert.match(app, /outreachForPeriod \? outreach\.participantsServed : null/);
  assert.match(app, /No published operational release/);
});

test('Scope 1 and Operational GHG use backend-published indicators, with component values preserved', async () => {
  const { data } = await loadDashboardWith(publishedPayload());
  const item = data['2026'], sep = 8;
  assert.equal(item.scope1Full[sep], 9.189255);
  assert.equal('dieselCombo' in item, false, 'do not publish a browser-derived emissions subtotal');
  assert.equal(item.operationalGHG[sep], 11.7592);
  assert.equal(item.perCapita[sep], 1.682048);
  // A broad all-scope total remains unavailable.
  assert.equal(item.totalGHG, null);
  assert.equal(item.avoided, null);
  assert.equal(item.reShare, null);
});

test('a missing component leaves Scope 1 missing instead of treating it as zero', async () => {
  const payload = publishedPayload();
  payload.lpg = { metrics: { lpg_consumption_litres: { value: 2, unit: 'L' } }, calculations: [] };
  payload.indicators.scope1_tco2e = { status: 'unavailable', value: null, unit: 'tCO2e' };
  const { data } = await loadDashboardWith(payload);
  const item = data['2026'], sep = 8;
  assert.equal(item.lpgEm[sep], null);
  assert.equal(item.scope1Full[sep], null);
  assert.equal(item.scope1Selected[sep], null);
  assert.equal('dieselCombo' in item, false);
});

test('GHG charts use the governed grid aggregate, not an unpublished per-connection split', () => {
  const app = read('app.js');
  assert.match(app, /ghgLabels\.push\('Grid electricity'\)/);
  assert.match(app, /label: 'S2: Grid electricity', data: sl\(d\.elecEm\)/);
  assert.doesNotMatch(app, /sl\(d\.(?:htEm|commEm|tempEm)\)/);
  for (const title of ['Petrol emissions', 'Fleet diesel emissions', 'DG diesel emissions', 'LPG emissions', 'Grid electricity emissions']) {
    assert.ok(app.includes(`kpi('${title}'`), `${title} card must exist on the GHG page`);
  }
});

test('the official Total GHG, avoided emissions and renewable share stay unavailable', () => {
  const app = read('app.js');
  const loader = read('public-data-loader.js');
  assert.match(loader, /item\.totalGHG = window\.KCOSMOSPublicAPI\.indicator\(publication\.raw, 'total_ghg_tco2e'\)\.value/);
  assert.doesNotMatch(app, /const net = null;/);
  assert.match(app, /Not published for this period/);
  // Nothing in the page derives the official total from Scope 1 + Scope 2.
  assert.doesNotMatch(app, /Calculations\.(?:grossEmissions|netCarbonIndicator|scope1Total|scope2Total)/);
  assert.doesNotMatch(loader, /totalGHG\s*=\s*[^w]*(?:scope1|elecEm)/);
  assert.doesNotMatch(loader, /population_master\.csv|6991/);
});

test('schema 1.4 monthly loader maps frozen derived Energy and Water indicators without population CSV', async () => {
  const requestedFiles = [];
  const transport = { metrics: {}, calculations: [] };
  const energy = { metrics: {
    grid_ht_kwh: { value: 100, unit: 'kWh' },
    grid_commercial_kwh: { value: 20, unit: 'kWh' },
    grid_temporary_kwh: { value: 5, unit: 'kWh' },
    grid_total_kwh: { value: 125, unit: 'kWh' },
    renewable_on_campus_kwh: { value: 40, unit: 'kWh' },
    renewable_procured_kwh: { value: 10, unit: 'kWh' },
    solar_water_heater_kwh: { value: 7, unit: 'kWh' },
    renewable_total_kwh: { value: 57, unit: 'kWh' }
  }, calculations: [] };
  const water = { metrics: {
    water_twad_kl: { value: 10, unit: 'KL' },
    water_borewell_kl: { value: 5, unit: 'KL' },
    water_private_kl: { value: 2, unit: 'KL' },
    water_consumed_kl: { value: 17, unit: 'KL' },
    wastewater_generated_kl: { value: 3, unit: 'KL' },
    water_recycled_kl: { value: 1, unit: 'KL' }
  }, calculations: [] };
  const release = {
    state: 'published',
    release: { version: 'sustainability-2026-09-v3' },
    period: { year: 2026, month: 9 },
    population: { status: 'available', value: 6991, unit: 'people', effective_year: 2026 },
    indicators: {
      scope1_tco2e: { status: 'available', value: 3 },
      scope2_tco2e: { status: 'available', value: 2 },
      operational_ghg_tco2e: { status: 'available', value: 5 },
      operational_ghg_per_capita_kgco2e: { status: 'available', value: 0.715 },
      waste_per_capita_kg: { status: 'available', value: 2.5 },
      renewable_electricity_kwh: { status: 'available', value: 50 },
      total_electricity_consumption_kwh: { status: 'available', value: 175 },
      renewable_share_pct: { status: 'available', value: 28.571428571429 },
      estimated_avoided_grid_emissions_tco2e: { status: 'available', value: 0.03635 },
      water_per_capita_l: { status: 'available', value: 2.4316978973 },
      total_ghg_tco2e: { status: 'unavailable', value: null },
      avoided_emissions_tco2e: { status: 'unavailable', value: null },
      renewable_share_percent: { status: 'unavailable', value: null }
    },
    domains: { transport, energy, lpg: { metrics: {}, calculations: [] }, water, outreach: null, waste: null },
    raw: { static_references: { landfill_diversion_pct: { value: 88.1 } } }
  };
  const metric = (domain, code) => {
    const value = domain?.metrics?.[code]?.value ?? null;
    return { status: value == null ? 'unavailable' : 'available', value };
  };
  const calculation = (domain, code) => ({ value: null });
  const api = {
    load: async () => release,
    loadHistory: async () => ({ releases: [release] }),
    metric,
    calculation,
    indicator: (_raw, code) => ({ value: release.indicators[code]?.value ?? null }),
    numberOrNull: value => value == null || value === '' ? null : Number(value)
  };
  const window = { KCOSMOSPublicAPI: api };
  vm.runInNewContext(read('public-data-loader.js'), { window, fetch: async url => {
    requestedFiles.push(String(url).split('?')[0]);
    return { ok: true, text: async () => '' };
  }, Object, Number, String, Date, Promise, Math });
  const result = await window.loadDashboardData();
  const year = result.data[2026];
  assert.equal(year.htKwh[8], 100);
  assert.equal(year.commKwh[8], 20);
  assert.equal(year.tempKwh[8], 5);
  assert.equal(year.elecKwh[8], 125);
  assert.equal(year.reOnCampusKwh[8], 40);
  assert.equal(year.reProcuredKwh[8], 10);
  assert.equal(year.solarWaterHeaterKwh[8], 7);
  assert.equal(year.reKwh[8], 50);
  assert.equal(year.totalElectricityKwh[8], 175);
  assert.equal(year.renewableSharePct[8], 28.571428571429);
  assert.equal(year.avoidEm[8], 0.03635);
  assert.equal(year.waterPerCapitaL[8], 2.4316978973);
  assert.equal(year.landfillDiversionPct, 88.1);
  assert.equal(year.waterTWAD[8], 10);
  assert.equal(year.waterBorewell[8], 5);
  assert.equal(year.waterProcured[8], 2);
  assert.equal(year.waterKL[8], 17);
  assert.equal(year.wastewaterKL[8], 3);
  assert.equal(year.waterRecycledKL[8], 1);
  assert.equal(year.scope1Full[8], 3);
  assert.equal(year.operationalGHG[8], 5);
  assert.equal(year.perCapita[8], 0.715);
  assert.equal(year.wastePerCapita[8], 2.5);
  assert.equal(year.population, 6991);
  assert.deepEqual(requestedFiles.sort(), ['data/dashboard_metadata.csv', 'data/green_master.csv']);
});

test('missing values are shown as unavailable and are never coerced to zero', () => {
  const app = read('app.js');
  assert.doesNotMatch(app, /const (?:dgVal|trDieselVal|petrolVal|lpgVal) = [^;]*\|\| 0/);
  assert.match(app, /c == null \? 'Unavailable' : c/);
  assert.match(app, /"\$\{c == null \? '' : c\}"/);
  assert.doesNotMatch(app, /const cleanZero = arr => arr\.map\(v => v === 0/);
  assert.match(app, /Combined electricity consumption is not published for this period/);
  assert.match(app, /kpi\('Total electricity consumption', totalElec/);
  assert.doesNotMatch(app, /v == null \? null : v \+ \(re\[i\] == null \? 0 : re\[i\]\)/);
});

test('single-month history is explained rather than implying unpublished months', () => {
  const app = read('app.js');
  assert.match(app, /Insufficient published history/);
  for (const chart of ['ghgTrendChart', 'energyTotalLineChart', 'energyGridLineChart', 'waterTrendChartCanvas']) {
    assert.ok(app.includes(`chartNote('${chart}'`), chart);
  }
  // An all-empty prior-year series is dropped instead of drawn as a legend entry.
  assert.match(app, /\.some\(v => v != null\) \? \[\{ label: '2025'/);
});

test('waste below one tonne is shown in kg so a real value is not rounded to 0.0 tons', () => {
  const app = read('app.js');
  assert.match(app, /function wasteDisplay\(tons\)/);
  assert.match(app, /unit: 'kg', dec: 2/);
  assert.doesNotMatch(app, /'Total waste generated', wasteTot, 'tons'/);
});

test('small positive emissions and waste/person values remain visibly nonzero', () => {
  const app = read('app.js');
  assert.match(app, /function emissionDecimals\(value\)/);
  assert.match(app, /emissionDecimals\(valFor\(d, d\.lpgEm, month\)\)/);
  assert.match(app, /perPersonKg == null \? null : perPersonKg \* 1000/);
  assert.match(app, /perPersonGrams, 'g\/person'.*3\)/);
  assert.match(app, /percentage\.toFixed\(percentage > 0 && percentage < 0\.1 \? 3 : 1\)/);
});

test('private water source terminology matches water_private_kl', () => {
  const app = read('app.js');
  const html = read('index.html');
  assert.match(app, /\['Private water supply', waterProcured, colors\.gold\]/);
  assert.match(app, /label: 'Private water supply', data: wsl\(d\.waterProcured\)/);
  assert.match(html, /<h2>Private water supply<\/h2>/);
  assert.match(html, /TWAD \/ Borewell \/ Private water supply values/);
});

test('energy total reads the combined value published by the backend', () => {
  const app = read('app.js');
  assert.match(app, /kpi\('Total electricity consumption', totalElec/);
  assert.match(app, /valFor\(d, d\.totalElectricityKwh, month\)/);
  assert.match(app, /const total26 = cleanZero\(d26\.totalElectricityKwh\)/);
  assert.doesNotMatch(app, /elec \+ re/);
});

test('Data Explorer builds each source row on its own published value', () => {
  const app = read('app.js');
  assert.match(app, /if \(d\.elecKwh\[i\] != null\) rows\.push\(\[year, m, 'S2', 'Grid Electricity'/);
  assert.match(app, /tables\.electricity = \{ cols: \['Year', 'Month', 'Grid kWh'/);
  assert.match(app, /function tableDecimals\(column, value\)/);
  assert.match(app, /column\.includes\('tCO₂e'\) && value > 0 && value < 0\.01 \? 6/);
});

test('active dashboard files hold no emission-factor formula or operational CSV authority', () => {
  for (const file of ['app.js', 'public-api.js', 'public-data-loader.js', 'walkthrough.js', 'mobile.js', 'weather.js']) {
    const source = read(file).replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
    assert.doesNotMatch(source, /2\.388|2\.701|0\.727|1\.5571|2\.939/, file);
    assert.doesNotMatch(source, /(?:transport|dg|lpg|energy|water|outreach|waste)_master\.csv/, file);
    assert.doesNotMatch(source, /dashboard_master/, file);
  }
  // Only static institutional files are still fetched by the loader.
  const fetched = [...read('public-data-loader.js').matchAll(/optionalText\('([^']+)'\)/g)].map(match => match[1]).sort();
  assert.deepEqual(fetched, ['data/dashboard_metadata.csv', 'data/green_master.csv']);
  assert.match(read('index.html'), /<script src="walkthrough\.js\?v=\d+"><\/script>/);
  assert.doesNotMatch(read('index.html'), /<script[^>]+src="calculations\.js/);
});

test('Overview contains exactly the eight governed presentation KPIs and keeps Scope 1/2 on GHG', () => {
  const app = read('app.js');
  const overview = app.match(/document\.getElementById\('overviewKpis'\)\.innerHTML = \[([\s\S]*?)\]\.join\(''\);/);
  assert.ok(overview, 'Overview KPI renderer must be present');
  const titles = [...overview[1].matchAll(/kpi\('([^']+)'/g)].map(match => match[1]);
  assert.deepEqual(titles, [
    'Renewable energy used',
    'Total grid electricity consumed',
    'Total water recycled',
    'Total waste generated',
    'Landfill diversion',
    'Total water usage',
    'Total green cover',
    'Outreach impact'
  ]);
  assert.ok(!titles.includes('Scope 1 emissions'));
  assert.ok(!titles.includes('Scope 2 emissions'));
  assert.match(app, /kpi\('Scope 1 emissions'/);
  assert.match(app, /kpi\('Scope 2 emissions'/);
});

test('Carbon Story restores the last-good final-staging scenes and reads current published cards safely', () => {
  const html = read('index.html');
  const story = read('walkthrough.js').replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
  const css = read('walkthrough.css');
  assert.match(html, /walkthrough\.css\?v=13/);
  assert.match(html, /walkthrough\.js\?v=16/);
  assert.ok(html.indexOf('vendor/gsap-scrolltrigger.min.js') < html.indexOf('walkthrough.js'));
  assert.match(story, /document\.querySelectorAll\('\.page \.kpi'\)/);
  assert.match(story, /document\.querySelectorAll\('#ghgKpis \.ghg-split'\)/);
  const titles = [...story.matchAll(/title: '([^']+)'/g)].map(match => match[1]);
  assert.deepEqual(titles, [
    'Total carbon footprint (gross)',
    'Total electricity consumption',
    'Renewable energy used',
    'Emission avoided',
    'Scope 1 emissions',
    'Scope 2 emissions',
    'Per capita emissions',
    'Where We Stand'
  ]);
  for (const video of [
    'industrynew.mp4', 'elecmeter.mp4', 'solar-kpi.mp4', 'solarbuild.mp4',
    'leavesfall.mp4', 'natureview.mp4', 'fuelpour.mp4', 'busdepot.mp4',
    'electricspark.mp4', 'electri.mp4', 'queper.mp4', 'earth.mp4',
    'entrykct.mp4', 'micronew.mp4'
  ]) assert.ok(story.includes(video), `last-good Carbon Story video ${video} must remain mapped`);
  assert.match(story, /alias\('Emission avoided', 'Estimated avoided grid emissions'\)/);
  assert.match(story, /alias\('Per capita emissions', 'Operational GHG per capita'\)/);
  assert.match(story, /document\.querySelector\('#ghgKpis \.ghg-top \.counter-val'\)/);
  assert.doesNotMatch(story, /Gross − avoided|Net impact|netVal|ledgerReady/);
  assert.match(story, /Estimated avoided grid emissions/);
  assert.match(css, /\.wt-equiv/);
  assert.match(css, /\.wt-ledger/);
});

test('schema 1.4 hero indicators continue to be sourced by the public API loader', () => {
  const loader = read('public-data-loader.js');
  assert.match(loader, /indicator\(publication\.raw, 'operational_ghg_tco2e'\)/);
  assert.match(loader, /indicator\(publication\.raw, 'operational_ghg_per_capita_kgco2e'\)/);
  assert.match(loader, /indicator\(publication\.raw, 'estimated_avoided_grid_emissions_tco2e'\)/);
});

test('new KPI cards use frozen indicators, static landfill reference, and no waste or green carbon claims', () => {
  const app = read('app.js');
  const loader = read('public-data-loader.js');
  const html = read('index.html');
  for (const code of [
    'renewable_electricity_kwh', 'total_electricity_consumption_kwh',
    'renewable_share_pct', 'estimated_avoided_grid_emissions_tco2e', 'water_per_capita_l'
  ]) assert.match(loader, new RegExp(`indicator\\(publication\\.raw, '${code}'\\)`));
  assert.match(loader, /static_references\?\.landfill_diversion_pct\?\.value/);
  assert.match(app, /const landfillDiversionPct = d\.landfillDiversionPct/);
  assert.match(app, /kpi\('Landfill diversion', landfillDiversionPct/);
  assert.match(app, /kpi\('Consumption per capita', waterPerCapitaL, 'L\/person'/);
  assert.match(app, /kpi\('Estimated avoided grid emissions', avoid/);
  assert.match(app, /tables\.derived =/);
  assert.match(html, /data-t="derived"/);
  assert.doesNotMatch(app, /kpi\('Green-cover carbon sequestration'/);
  assert.doesNotMatch(app, /kpi\('Waste emissions'|kpi\('Waste CO₂e'/);
  assert.doesNotMatch(app, /renewable_total_kwh/);
});
