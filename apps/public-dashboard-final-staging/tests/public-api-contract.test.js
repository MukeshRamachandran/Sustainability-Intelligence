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
  // Every sustainability value comes from the backend timeline (PostgreSQL).
  assert.match(loader, /KCOSMOSPublicAPI\.loadTimeline/);
  assert.doesNotMatch(loader, /transport_master|dg_master|lpg_master|energy_master|water_master|outreach_master|emission_factors|dashboard_master|population_master/);
  assert.doesNotMatch(loader, /Calculations\.(co2e|renewableAvoidedEmissions)/);
  assert.doesNotMatch(loader, /2\.388|2\.701|0\.727|0\.71|1\.5571|2\.939/);
  assert.match(loader, /lpg_consumption_litres/);
  assert.doesNotMatch(loader, /lpg_weight_kg/);
  // No file on the loaded governed path may carry a factor constant.
  for (const file of ['public-api.js', 'public-data-loader.js', 'app.js']) {
    assert.doesNotMatch(read(file), /2\.388|2\.701|0\.727|0\.71|1\.5571|2\.939/, file);
  }
  assert.match(loader, /green_master\.csv/);
});

test('staging helper proxies the public routes and nothing else', () => {
  const server = read('serve-staging.py');
  const routes = ['/api/public/dashboard', '/api/public/dashboard/history', '/api/public/dashboard/timeline'];
  for (const route of routes) {
    assert.ok(server.includes(`"${route}"`), `serve-staging.py must proxy ${route}`);
  }
  const adapter = read('public-api.js');
  for (const route of routes) {
    assert.ok(adapter.includes(`'${route}'`), `public-api.js must request ${route}`);
  }
  // The proxy stays narrow: no authenticated or admin path may pass through.
  assert.doesNotMatch(server, /\/api\/(auth|admin|manager)/);
  assert.match(server, /PUBLIC_ROUTES/);
});

test('Weather reads persisted Aeron data same-origin and can never trigger ingestion', () => {
  const weather = read('weather.js');
  const code = weather.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
  assert.match(code, /const API_BASE = '\/api\/environment';/);
  assert.match(code, /request\('\/latest'\)/);
  assert.match(code, /request\(`\/history\?limit=\$\{limit\}`\)/);
  assert.doesNotMatch(code, /:8000|:8001|localhost|127\.0\.0\.1/);
  assert.doesNotMatch(code, /method:\s*'POST'|['"]POST['"]|\/sync/);

  const server = read('serve-staging.py');
  for (const route of ['/api/environment/latest', '/api/environment/history', '/api/environment/status']) {
    assert.ok(server.includes(`"${route}"`), `serve-staging.py must proxy ${route}`);
  }
  assert.doesNotMatch(server, /\/api\/environment\/sync|\/api\/sync/);
});

test('production Weather also reads the same-origin environment API with server freshness', () => {
  // Ported from the retired services/aeron-api contract test.
  const weather = fs.readFileSync(path.resolve(root, '..', 'public-dashboard', 'weather.js'), 'utf8');
  assert.ok(weather.includes("const API_BASE = '/api/environment'"));
  assert.doesNotMatch(weather, /localhost:8000|127\.0\.0\.1:8000|:8001/);
  assert.ok(weather.includes('setInterval(tickLatest, POLL_MS)'));
  assert.ok(weather.includes("if (document.body.dataset.page !== 'weather'"));
  assert.match(weather, /if \(data\.freshness\) return String\(data\.freshness\)\.toLowerCase\(\);/);
  assert.doesNotMatch(weather, /['"]POST['"]|\/sync/);
});

test('Weather reads only fields the backend environment schema serves', () => {
  const schema = fs.readFileSync(
    path.resolve(root, '..', '..', 'services', 'main-api', 'app', 'schemas', 'environment.py'), 'utf8');
  const block = schema.match(/class EnvironmentReadingResponse\(BaseModel\):([\s\S]*?)\nclass /)[1];
  const served = new Set([...block.matchAll(/^ {4}(\w+): /gm)].map(match => match[1]));
  const used = new Set([...read('weather.js').matchAll(/(?<![.\w])(?:data|d)\.([a-z][a-z0-9_]*)/g)].map(match => match[1]));
  assert.ok(used.size > 20, 'expected the Weather UI to read many reading fields');
  for (const field of used) assert.ok(served.has(field), `weather.js reads ${field}, which the API does not serve`);
  assert.ok(served.has('freshness') && served.has('recorded_at') && served.has('observed_at'));
});

test('Weather status follows server freshness and shows the station time in IST', () => {
  const weather = read('weather.js');
  const source = weather.match(/function computeStatus\(data\) \{[\s\S]*?\n  \}/)[0];
  const computeStatus = vm.runInNewContext(`(${source})`, { Date, String });
  assert.equal(computeStatus(null), 'offline');
  assert.equal(computeStatus({ recorded_at: new Date().toISOString(), freshness: 'OFFLINE' }), 'offline');
  assert.equal(computeStatus({ recorded_at: '2020-01-01T00:00:00Z', freshness: 'LIVE' }), 'live');
  assert.equal(computeStatus({ recorded_at: new Date(Date.now() - 10 * 60 * 1000).toISOString() }), 'stale');
  assert.match(weather, /const DISPLAY_TZ = 'Asia\/Kolkata';/);
  assert.match(weather, /IST`/);
  assert.doesNotMatch(weather, /Data fetched:/);
});

test('governed waste comes from the backend timeline, never waste_master.csv', () => {
  const loader = read('public-data-loader.js');
  const code = loader.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
  assert.doesNotMatch(code, /waste_master\.csv/);
  assert.doesNotMatch(code, /staticWaste/);
  assert.match(loader, /wet_waste_generated_kg/);
  assert.match(loader, /dry_waste_generated_kg/);
  assert.match(loader, /total_waste_generated_kg/);
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

test('official GHG is shown only from backend values and never derived in the browser', () => {
  const app = read('app.js');
  assert.match(app, /<\/div>Gross Organizational Emissions<\/div>/);
  // The GHG hero keeps one structure: each official figure comes from the
  // backend display item, or shows "—" with a reason; never summed or zeroed.
  assert.match(app, /const total = shownValue\('operational_ghg_tco2e'\)/);
  assert.match(app, /const s1 = shownValue\('scope1_tco2e'\), s2 = shownValue\('scope2_tco2e'\)/);
  assert.doesNotMatch(app, /if \(!total && !s1 && !s2\) return '';/);
  assert.match(app, /\$\{total \? counter\(total\.value, '1\.2rem'\) : dash\}/);
  assert.match(app, /\$\{item \? counter\(item\.value, '13px'\) : dash\}/);
  assert.doesNotMatch(app, /s1\.value \+ s2\.value|s2\.value \+ s1\.value/);
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
// ---- Timeline fixtures ------------------------------------------------------
// The dashboard reads GET /api/public/dashboard/timeline. These fixtures mirror
// its contract: one entry per genuine period, values keyed by governed code.

const TL_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function tv(value, domain, extra = {}) {
  return {
    status: value == null ? 'unavailable' : 'available', value, unit: extra.unit || '', domain,
    kind: extra.kind || 'metric', qualifier: extra.qualifier || 'EXACT', reason: extra.reason || null,
    source_kind: extra.source_kind || 'historical_verified', granularity: extra.granularity || 'MONTHLY',
    coverage_status: extra.coverage_status || 'complete', months_covered: extra.months_covered || [],
    provenance: extra.provenance || {}
  };
}
function tlMonth(year, month, values, extra = {}) {
  const key = `${year}-${String(month).padStart(2, '0')}`;
  const domains = Object.fromEntries(['transport', 'energy', 'lpg', 'water', 'waste', 'outreach'].map(domain => [
    domain,
    Object.values(values).some(item => item.domain === domain && item.status === 'available')
      ? { state: 'available' }
      : (extra.domains || {})[domain] || { state: 'unavailable', message: `${domain} not available` }
  ]));
  return {
    key, label: `${TL_MONTHS[month - 1]} ${year}`, year, month, granularity: 'MONTHLY',
    coverage_start: `${key}-01`, coverage_end: `${key}-28`, coverage_status: 'complete',
    source_kind: extra.source_kind || 'historical_verified', release_version: extra.release_version || null,
    population: { status: 'available', value: 6991 }, domains, values
  };
}
function tlAggregate(key, year, granularity, endMonth, values, label) {
  return {
    key, label, year, month: null, granularity, coverage_start: `${year}-01-01`,
    coverage_end: `${year}-${String(endMonth).padStart(2, '0')}-28`, coverage_status: 'complete',
    source_kind: 'historical_aggregate', release_version: null, population: { status: 'available', value: 6991 },
    domains: {}, values
  };
}
function timelineOf(periods, defaultKey) {
  const byYear = {};
  periods.forEach(period => {
    (byYear[period.year] ||= []).push({
      key: period.key, granularity: period.granularity,
      label: period.granularity === 'MONTHLY' ? TL_MONTHS[period.month - 1]
        : (period.granularity === 'ANNUAL' ? 'Full Year' : period.label.split(' ').slice(1).join(' '))
    });
  });
  Object.values(byYear).forEach(options => options.sort((a, b) => (a.granularity === 'MONTHLY') - (b.granularity === 'MONTHLY')));
  return {
    schema_version: 'timeline-1.0', default_key: defaultKey,
    selector: Object.keys(byYear).sort().map(year => ({ year: Number(year), options: byYear[year] })),
    periods: Object.fromEntries(periods.map(period => [period.key, period])),
    labels: { 'material:PET': 'PET' },
    static_references: { landfill_diversion_pct: { value: 88.1, unit: '%' } }
  };
}
async function loadDashboardFromTimeline(timeline) {
  const requested = [];
  const window = { location: { hostname: '127.0.0.1', port: '3001' } };
  const fetchImpl = async url => {
    requested.push(String(url).split('?')[0]);
    return url === '/api/public/dashboard/timeline'
      ? { ok: true, json: async () => timeline, text: async () => '' }
      : { ok: true, json: async () => ({}), text: async () => '' };
  };
  const sandbox = { window, fetch: fetchImpl, Object, Number, String, Error, Array, Math, Date, Promise, JSON };
  vm.runInNewContext(read('public-api.js'), sandbox);
  vm.runInNewContext(read('public-data-loader.js'), sandbox);
  const result = await window.loadDashboardData();
  return { ...result, requested };
}
const septemberValues = () => ({
  transport_petrol_litres: tv(3443, 'transport', { unit: 'L' }),
  transport_petrol_emissions: tv(8.221884, 'transport', { kind: 'calculation', provenance: { factor_value: '2.388' } }),
  transport_diesel_emissions: tv(0.332223, 'transport', { kind: 'calculation', provenance: { factor_value: '2.701' } }),
  dg_diesel_emissions: tv(0.632034, 'transport', { kind: 'calculation', provenance: { factor_value: '2.701' } }),
  lpg_emissions: tv(0.003114, 'lpg', { kind: 'calculation', provenance: { factor_value: '1.5571' } }),
  grid_electricity_emissions: tv(2.569945, 'energy', { kind: 'calculation', provenance: { factor_value: '0.727' } }),
  scope1_tco2e: tv(9.189255, 'ghg', { kind: 'calculation' }),
  scope2_tco2e: tv(2.569945, 'ghg', { kind: 'calculation' }),
  operational_ghg_tco2e: tv(11.7592, 'ghg', { kind: 'calculation' }),
  operational_ghg_per_capita_kgco2e: tv(1.682048, 'ghg', { kind: 'calculation' })
});

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

test('governed emission components reach the dashboard arrays from the timeline month only', async () => {
  const { data } = await loadDashboardFromTimeline(timelineOf([tlMonth(2026, 9, septemberValues())], '2026-09'));
  const item = data['2026'], sep = 8;
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

test('calculation factors stay attached to the month that supplied each result', async () => {
  const august = septemberValues();
  august.transport_petrol_emissions.provenance.factor_value = '2.4';
  august.grid_electricity_emissions.provenance.factor_value = '0.73';
  august.lpg_emissions.provenance.factor_value = '1.6';
  const { data } = await loadDashboardFromTimeline(timelineOf([tlMonth(2026, 8, august), tlMonth(2026, 9, septemberValues())], '2026-09'));
  const item = data['2026'];
  assert.equal(item.petrolEF[7], 2.4);
  assert.equal(item.petrolEF[8], 2.388);
  assert.equal(item.gridEF[7], 0.73);
  assert.equal(item.gridEF[8], 0.727);
  assert.equal(item.lpgEF[7], 1.6);
  assert.equal(item.lpgEF[8], 1.5571);
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

test('month-bound values are hidden for months without genuine records', () => {
  const app = read('app.js');
  assert.match(app, /function selectionHasPublication\(d, month\)/);
  assert.match(app, /published\[\+month\] === true/);
  assert.match(app, /const publishedWaste = hasPublication &&/);
  assert.match(app, /hasPublication \? waterRecycled : null/);
  // Outreach follows the selected period; annual outreach is never a month.
  assert.match(app, /outreach = outreachFor\(\+yearFilter\.value, monthFilter\.value\)/);
  assert.match(app, /outreachForPeriod \? outreach\.participantsServed : null/);
  assert.match(app, /No published or verified data/);
});

test('Scope 1 and Operational GHG use backend-published values, with component values preserved', async () => {
  const { data } = await loadDashboardFromTimeline(timelineOf([tlMonth(2026, 9, septemberValues())], '2026-09'));
  const item = data['2026'], sep = 8;
  assert.equal(item.scope1Full[sep], 9.189255);
  assert.equal('dieselCombo' in item, false, 'do not publish a browser-derived emissions subtotal');
  assert.equal(item.operationalGHG[sep], 11.7592);
  assert.equal(item.perCapita[sep], 1.682048);
  // A broad all-scope total remains unavailable.
  assert.equal(item.totalGHG, null);
});

test('a missing component leaves Scope 1 missing instead of treating it as zero', async () => {
  const values = septemberValues();
  delete values.lpg_emissions;
  values.scope1_tco2e = tv(null, 'ghg', { kind: 'calculation', reason: 'inputs_missing:lpg_emissions' });
  const { data } = await loadDashboardFromTimeline(timelineOf([tlMonth(2026, 9, values)], '2026-09'));
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
    assert.ok(app.includes(`ghgKpi('${title}'`), `${title} card must exist on the GHG page`);
  }
});

test('no browser-derived official total and no population CSV', () => {
  const app = read('app.js');
  const loader = read('public-data-loader.js');
  assert.doesNotMatch(app, /const net = null;/);
  // Nothing in the page derives an official total from Scope 1 + Scope 2.
  assert.doesNotMatch(app, /Calculations\.(?:grossEmissions|netCarbonIndicator|scope1Total|scope2Total)/);
  assert.doesNotMatch(loader, /totalGHG\s*=\s*[^n]*(?:scope1|elecEm)/);
  assert.doesNotMatch(loader, /population_master\.csv|6991/);
});

test('loader maps derived Energy and Water values per month and fetches only the static green file', async () => {
  const values = {
    grid_ht_kwh: tv(100, 'energy'), grid_commercial_kwh: tv(20, 'energy'), grid_temporary_kwh: tv(5, 'energy'),
    grid_total_kwh: tv(125, 'energy', { kind: 'calculation' }), renewable_on_campus_kwh: tv(40, 'energy'),
    renewable_procured_kwh: tv(10, 'energy'), solar_water_heater_kwh: tv(7, 'energy'),
    renewable_electricity_kwh: tv(50, 'energy', { kind: 'calculation' }),
    total_electricity_consumption_kwh: tv(175, 'energy', { kind: 'calculation' }),
    renewable_share_pct: tv(28.571428571429, 'energy', { kind: 'calculation' }),
    estimated_avoided_grid_emissions_tco2e: tv(0.03635, 'energy', { kind: 'calculation' }),
    water_twad_kl: tv(10, 'water'), water_borewell_kl: tv(5, 'water'), water_private_kl: tv(2, 'water'),
    water_consumed_kl: tv(17, 'water', { kind: 'calculation' }), wastewater_generated_kl: tv(3, 'water'),
    water_recycled_kl: tv(1, 'water'), water_per_capita_l: tv(2.4316978973, 'water', { kind: 'calculation' }),
    waste_per_capita_kg: tv(2.5, 'waste', { kind: 'calculation' })
  };
  const aggregate = tlAggregate('2026-YTD', 2026, 'YTD', 9, { water_consumed_kl: tv(17, 'water') }, '2026 YTD · Jan–Sep');
  const { data, requested } = await loadDashboardFromTimeline(timelineOf([aggregate, tlMonth(2026, 9, values)], '2026-09'));
  const year = data[2026];
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
  assert.equal(year.wastePerCapita[8], 2.5);
  assert.equal(year.population, 6991);
  assert.deepEqual(requested.sort(), ['/api/public/dashboard/timeline', 'data/green_master.csv']);
});

test('missing values are never coerced to zero', () => {
  const app = read('app.js');
  assert.doesNotMatch(app, /const (?:dgVal|trDieselVal|petrolVal|lpgVal) = [^;]*\|\| 0/);
  assert.match(app, /c == null \? '' : c/);
  assert.match(app, /"\$\{c == null \? '' : c\}"/);
  assert.doesNotMatch(app, /const cleanZero = arr => arr\.map\(v => v === 0/);
  assert.match(app, /No combined electricity total for this selection/);
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

test('Energy Source Breakdown reads the selected period record, never a year sum', async () => {
  const app = read('app.js');
  const fn = name => app.match(new RegExp(`function ${name}\\([\\s\\S]*?\\n\\}`))[0];
  const breakdown = vm.runInNewContext(`${fn('valFor')}\n${fn('energySourceBreakdown')}\nenergySourceBreakdown`, {
    n: Number, colors: { cyan: 'c', emerald: 'e', gold: 'g' }, Array
  });
  const energy = (grid, onCampus, procured) => ({
    grid_total_kwh: tv(grid, 'energy', { kind: 'calculation' }),
    renewable_on_campus_kwh: tv(onCampus, 'energy'), renewable_procured_kwh: tv(procured, 'energy')
  });
  const ytd = tlAggregate('2027-YTD', 2027, 'YTD', 3, {
    ...energy(300, 60, 900),
    grid_total_kwh: tv(300, 'energy', { coverage_status: 'partial', months_covered: ['2027-01', '2027-03'] })
  }, '2027 YTD · Jan–Mar');
  const { data } = await loadDashboardFromTimeline(timelineOf([
    ytd, tlMonth(2027, 1, energy(100, 20, 300)), tlMonth(2027, 2, energy(null, 20, 300)),
    tlMonth(2027, 3, { ...energy(200, 20, 300), solar_water_heater_kwh: tv(0, 'energy') })
  ], '2027-03'));
  const d = data['2027'];
  const bars = month => Object.fromEntries(breakdown(d, month).map(bar => [bar.label, bar.value]));
  // A month uses only that month; the aggregate uses the backend's own record.
  assert.deepEqual(bars(0), { 'Grid total': 100, 'On-campus renewable': 20, 'Procured renewable': 300 });
  assert.deepEqual(bars('all'), { 'Grid total': 300, 'On-campus renewable': 60, 'Procured renewable': 900 });
  // Missing grid and missing solar water heater are omitted, never 0; a published 0 stays 0.
  assert.deepEqual(bars(1), { 'On-campus renewable': 20, 'Procured renewable': 300 });
  assert.equal(bars(2)['Solar water heater'], 0);
  // A partial aggregate keeps its coverage.
  const grid = breakdown(d, 'all').find(bar => bar.label === 'Grid total');
  assert.deepEqual([grid.partial, grid.monthsCovered], [true, 2]);
  // Chart, progress card and KPIs all follow the selection; no year-sum or hard-coded period.
  assert.match(app, /const sourceBars = energySourceBreakdown\(d, month\)/);
  assert.match(app, /const breakdown = energySourceBreakdown\(d, month\)/);
  assert.doesNotMatch(app, /solarWaterHeaterTotal|sum\(esl\(d\.solarWaterHeaterKwh\)\)/);
  assert.doesNotMatch(fn('energySourceBreakdown'), /\b20\d\d\b|sum\(|\|\| 0/);
  // Renewable Energy Progress still shows the backend renewable_share_pct only.
  assert.match(app, /const reShare = valFor\(d, d\.renewableSharePct, month\)/);
  assert.match(app, /const reProgressPct = reShare;/);
  assert.match(app, /\$\{reProgressPct == null \? '' : `<div class="ep-hero">/);
});

test('Energy cards can shrink with the page and the two hero cards stack by their own width', () => {
  const css = read('styles.css');
  // Grid items holding Chart.js canvases must be allowed to shrink below the canvas's last pixel width.
  assert.match(css, /#energy \.row > \* \{ min-width: 0; \}/);
  // Stacking follows the widget's container width, not a device breakpoint.
  assert.match(css, /#energyProgressWidget \{ container-type: inline-size; \}/);
  assert.match(css, /@container \(max-width: \d+px\) \{\s*\.ep-hero-row \{ flex-direction: column; \}/);
  // Fixed by layout, never by clipping the page.
  assert.doesNotMatch(css, /(?:html|body|\.page|#energy)\s*\{[^}]*overflow-x:\s*hidden/);
});

test('shared top bar wraps and grows instead of overflowing, keeping every control', () => {
  const css = read('styles.css');
  const mobile = read('mobile.css');
  const html = read('index.html');
  const topbar = css.match(/\.topbar\{[^}]*\}/)[0];
  // No fixed height: the bar grows when the controls wrap to their own row.
  assert.match(topbar, /flex-wrap:wrap/);
  assert.match(topbar, /min-height:68px/);
  assert.doesNotMatch(topbar, /[{;]\s*height:/);
  assert.doesNotMatch(mobile.match(/\.topbar \{[^}]*\}/)[0], /[{;]\s*height:/);
  assert.match(css, /\.topbar-controls\{[^}]*min-width:0/);
  // Every control stays in the bar; nothing is hidden or clipped to make it fit.
  for (const id of ['yearFilter', 'monthFilter', 'periodText', 'exportBtn']) assert.match(html, new RegExp(`id="${id}"`));
  assert.doesNotMatch(css + mobile, /(?:html|body|\.topbar|\.topbar-controls)\s*\{[^}]*overflow-x:\s*hidden/);
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
    assert.doesNotMatch(source, /(?:transport|dg|lpg|energy|water|outreach|waste|population)_master\.csv/, file);
    assert.doesNotMatch(source, /dashboard_master|dashboard_metadata/, file);
  }
  // Only the static green-cover file is still fetched by the loader.
  const fetched = [...read('public-data-loader.js').matchAll(/optionalText\('([^']+)'\)/g)].map(match => match[1]).sort();
  assert.deepEqual(fetched, ['data/green_master.csv']);
  assert.match(read('index.html'), /<script src="walkthrough\.js\?v=\d+"><\/script>/);
  assert.doesNotMatch(read('index.html'), /<script[^>]+src="calculations\.js/);
});

test('Overview contains exactly the eight governed presentation KPIs and keeps Scope 1/2 on GHG', () => {
  const app = read('app.js');
  const overview = app.match(/document\.getElementById\('overviewKpis'\)\.innerHTML = \[([\s\S]*?)\]\.join\(''\);/);
  assert.ok(overview, 'Overview KPI renderer must be present');
  const titles = [...overview[1].matchAll(/(?:overviewKpi|kpi)\('([^']+)'/g)].map(match => match[1]);
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
  assert.match(html, /walkthrough\.css\?v=\d+/);
  assert.match(html, /walkthrough\.js\?v=\d+/);
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

test('hero indicators are sourced from the backend timeline', () => {
  const loader = read('public-data-loader.js');
  for (const code of ['operational_ghg_tco2e', 'operational_ghg_per_capita_kgco2e', 'estimated_avoided_grid_emissions_tco2e']) {
    assert.match(loader, new RegExp(`'${code}'`));
  }
});

test('KPI cards use backend values, the static landfill reference, and no waste or green carbon claims', () => {
  const app = read('app.js');
  const loader = read('public-data-loader.js');
  const html = read('index.html');
  for (const code of [
    'renewable_electricity_kwh', 'total_electricity_consumption_kwh',
    'renewable_share_pct', 'estimated_avoided_grid_emissions_tco2e', 'water_per_capita_l'
  ]) assert.match(loader, new RegExp(`'${code}'`));
  assert.match(loader, /static_references\?\.landfill_diversion_pct\?\.value/);
  assert.match(app, /const landfillDiversionPct = d\.landfillDiversionPct/);
  assert.match(app, /kpi\('Landfill diversion', landfillDiversionPct/);
  assert.match(app, /kpi\('Consumption per capita', waterPerCapitaL, 'L\/person'/);
  assert.match(app, /kpi\('Estimated avoided grid emissions', avoid/);
  // The GHG page shows the same governed metric as "Reduction through renewables".
  assert.match(app, /'Reduction through renewables': \{ code: 'estimated_avoided_grid_emissions_tco2e' \}/);
  assert.match(app, /ghgKpi\('Reduction through renewables', avoid,/);
  assert.match(app, /tables\.derived =/);
  assert.match(html, /data-t="derived"/);
  assert.doesNotMatch(app, /kpi\('Green-cover carbon sequestration'/);
  assert.doesNotMatch(app, /kpi\('Waste emissions'|kpi\('Waste CO₂e'/);
  assert.doesNotMatch(app, /renewable_total_kwh/);
});

// ---- Historical granularity (timeline) ---------------------------------------

test('annual waste and outreach are never placed into a month', async () => {
  const march = tlMonth(2025, 3, { grid_ht_kwh: tv(10, 'energy') }, {
    domains: {
      waste: { state: 'aggregate_only', alternative_key: '2025-FY', message: 'Monthly Waste data unavailable. 2025 annual data is available under 2025 Full Year.' },
      outreach: { state: 'aggregate_only', alternative_key: '2025-FY', message: 'Monthly Outreach data unavailable. 2025 annual data is available under 2025 Full Year.' }
    }
  });
  const annual = tlAggregate('2025-FY', 2025, 'ANNUAL', 12, {
    total_waste_generated_kg: tv(55339.55, 'waste', { granularity: 'ANNUAL' }),
    'material:PET': tv(812, 'waste', { granularity: 'ANNUAL' }),
    total_programs: tv(20, 'outreach', { granularity: 'ANNUAL', qualifier: 'AT_LEAST' }),
    total_participants: tv(4000, 'outreach', { granularity: 'ANNUAL', qualifier: 'AT_LEAST' })
  }, '2025 Full Year');
  annual.domains = { waste: { state: 'available' }, outreach: { state: 'available' } };
  const { data, outreachFor } = await loadDashboardFromTimeline(timelineOf([annual, march], '2025-03'));
  const year = data['2025'];
  assert.equal(year.totalWaste[2], null);
  assert.ok(year.totalWaste.every(value => value === null), 'no monthly waste invented');
  assert.equal(year.totalWaste.aggregate, 55339.55);
  assert.equal(JSON.stringify(year.wasteBreakdownAggregate), JSON.stringify([{ name: 'PET', value: 812 }]));
  assert.equal(year.domainStatus[2].waste.state, 'aggregate_only');
  assert.match(year.domainStatus[2].waste.message, /Monthly Waste data unavailable/);
  assert.equal(outreachFor(2025, '2').published, false);
  const fullYear = outreachFor(2025, 'all');
  assert.equal(fullYear.published, true);
  assert.equal(fullYear.programsDelivered, 20);
  assert.equal(fullYear.qualifiers.programsDelivered, 'AT_LEAST');
});

test('Full Year / YTD values are the backend aggregate, never browser sums', async () => {
  const jan = tlMonth(2026, 1, { water_consumed_kl: tv(100, 'water') });
  const feb = tlMonth(2026, 2, { water_consumed_kl: tv(200, 'water') });
  // A deliberately different aggregate proves the page shows the API value.
  const ytd = tlAggregate('2026-YTD', 2026, 'YTD', 2, {
    water_consumed_kl: tv(299, 'water', { coverage_status: 'partial', months_covered: ['2026-01'] }),
    renewable_share_pct: tv(41.5, 'energy', { kind: 'calculation' })
  }, '2026 YTD · Jan–Feb');
  const { data, selector, defaultKey } = await loadDashboardFromTimeline(timelineOf([ytd, jan, feb], '2026-02'));
  const year = data['2026'];
  assert.equal(year.waterKL.aggregate, 299);
  assert.equal(year.waterKL.aggregateCoverage, 'partial');
  assert.equal(year.renewableSharePct.aggregate, 41.5);
  assert.equal(year.frequency, 'ytd');
  assert.equal(year.label, '2026 YTD · Jan–Feb');
  assert.equal(defaultKey, '2026-02');
  assert.deepEqual(selector[0].options.map(option => option.key), ['2026-YTD', '2026-01', '2026-02']);
  const app = read('app.js');
  assert.match(app, /if \(m === 'all'\) return arr\.aggregate == null \? null : n\(arr\.aggregate\);/);
  // A YTD window is never compared with a different window.
  assert.match(app, /py\.aggregateEndMonth === d\.aggregateEndMonth/);
});

test('period controls come from the timeline selector and default to its latest official month', () => {
  const app = read('app.js');
  const html = read('index.html');
  assert.match(app, /populatePeriodControls\(loaded\.defaultKey\)/);
  assert.match(app, /function monthOptionsFor\(year\)/);
  assert.match(app, /option\.granularity === 'MONTHLY'/);
  // No hard-coded year or month list remains in the toolbar markup.
  const toolbar = html.slice(html.indexOf('id="yearFilter"'), html.indexOf('id="periodText"'));
  assert.doesNotMatch(toolbar, /value="2025"|value="2026"|value="11"/);
  assert.match(html, /data-t="records"/);
  assert.match(app, /tables\.records = \{/);
  assert.match(app, /'Granularity'/);
});

test('a year with a partial YTD and a separate annual record exposes both views', async () => {
  const march = tlMonth(2027, 3, { grid_ht_kwh: tv(10, 'energy') });
  const ytd = tlAggregate('2027-YTD', 2027, 'YTD', 3, { grid_ht_kwh: tv(10, 'energy') }, '2027 YTD · Jan–Mar');
  const annual = tlAggregate('2027-FY', 2027, 'ANNUAL', 12, {
    total_waste_generated_kg: tv(900, 'waste', { granularity: 'ANNUAL' })
  }, '2027 Full Year');
  annual.domains = { waste: { state: 'available' } };
  const timeline = timelineOf([ytd, annual, march], '2027-03');
  timeline.selector[0].options = [
    { key: '2027-YTD', label: 'YTD · Jan–Mar', granularity: 'YTD' },
    { key: '2027-FY', label: 'Full Year', granularity: 'ANNUAL' },
    { key: '2027-03', label: 'Mar', granularity: 'MONTHLY' }
  ];
  const { data, outreachFor } = await loadDashboardFromTimeline(timeline);
  const year = data['2027'];
  assert.equal(year.aggregateKey, '2027-YTD');
  assert.equal(year.totalWaste.aggregate, null, 'the annual record is not merged into the YTD view');
  const fullYear = year.secondary['2027-FY'];
  assert.equal(fullYear.totalWaste.aggregate, 900);
  assert.equal(fullYear.label, '2027 Full Year');
  assert.equal(outreachFor(2027, 'agg:2027-FY').published, false);
  const app = read('app.js');
  assert.match(app, /value\.startsWith\('agg:'\)/);
  assert.match(app, /`agg:\$\{option\.key\}`/);
});

// ---- Display fallback (presentation only) ----------------------------------

test('a month view shows annual context from the backend display map without touching monthly data', async () => {
  const march = tlMonth(2025, 3, { grid_ht_kwh: tv(10, 'energy') });
  march.display = {
    grid_ht_kwh: { value: 10, unit: 'kWh', source_granularity: 'MONTHLY', display_context: false, display_label: 'March 2025' },
    total_waste_generated_kg: { value: 55339.55, unit: 'kg', source_granularity: 'ANNUAL', source_year: 2025, display_context: true, display_label: '2025 Annual Data' },
    total_participants: { value: 4000, unit: 'people', qualifier: 'AT_LEAST', source_granularity: 'ANNUAL', display_context: true, display_label: '2025 Annual Data' },
    landfill_diversion_pct: { value: 88.1, unit: '%', source_granularity: 'STATIC', display_context: true, display_label: 'Institutional Reference' }
  };
  const annual = tlAggregate('2025-FY', 2025, 'ANNUAL', 12, { total_waste_generated_kg: tv(55339.55, 'waste', { granularity: 'ANNUAL' }) }, '2025 Full Year');
  annual.display = { total_waste_generated_kg: { value: 55339.55, unit: 'kg', source_granularity: 'ANNUAL', display_context: false, display_label: '2025 Annual Data' } };
  const { data, explorerRows } = await loadDashboardFromTimeline(timelineOf([annual, march], '2025-03'));
  const year = data['2025'];
  // Shown in the March view, labelled as annual context...
  assert.equal(year.display[2].total_waste_generated_kg.value, 55339.55);
  assert.equal(year.display[2].total_waste_generated_kg.display_label, '2025 Annual Data');
  assert.equal(year.display[2].total_waste_generated_kg.display_context, true);
  assert.equal(year.display[2].landfill_diversion_pct.display_label, 'Institutional Reference');
  // ...but never a March record: charts, sums and exports read the true series.
  assert.ok(year.totalWaste.every(value => value === null), 'no monthly waste point');
  assert.equal(year.totalWaste.aggregate, 55339.55, 'annual value stays in the Full Year view');
  const marchRows = explorerRows.filter(row => row[1] === 'Mar 2025');
  assert.ok(marchRows.every(row => row[3] !== 'waste' && row[3] !== 'outreach'), 'no March waste/outreach export row');
  const annualRow = explorerRows.find(row => row[3] === 'waste' && row[5] === 55339.55);
  assert.equal(annualRow[1], '2025 Full Year');
  assert.equal(annualRow[2], 'ANNUAL');
});

test('KPI cards render the backend display item with a provenance badge, or are omitted', () => {
  const app = read('app.js');
  assert.match(app, /const CARD_DISPLAY = \{/);
  for (const [title, code] of [
    ['Total waste generated', 'total_waste_generated_kg'], ['Outreach impact', 'total_participants'],
    ['Landfill diversion', 'landfill_diversion_pct'], ['Total water recycled', 'water_recycled_kl'],
    ['Wet waste generated', 'wet_waste_generated_kg'], ['Dry waste generated', 'dry_waste_generated_kg'],
    ['Grid electricity emissions', 'scope2_tco2e'], ['Total grid electricity consumed', 'grid_total_kwh']
  ]) assert.ok(app.includes(`'${title}': { code: '${code}'`), title);
  // No trustworthy number: the card is omitted, never rendered as "Unavailable".
  assert.match(app, /if \(!item\) return '';\s*\/\/ no trustworthy number/);
  assert.match(app, /sourceBadge\(label, context\)/);
  assert.match(app, /if \(context\) prev = null;/);
  // Static institutional references always carry their label.
  assert.match(app, /const STATIC_LABEL = 'Institutional Reference';/);
  for (const title of ['Total green cover', 'Maintained vegetation', 'Natural vegetation', 'Total trees', 'Green cover zones']) {
    assert.ok(app.includes(`'${title}'`), title);
  }
  assert.match(read('styles.css'), /\.kpi-source/);
});

test('public dashboard code renders no generic unavailable text', () => {
  const sources = ['app.js', 'walkthrough.js'].map(file => read(file).replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, ''));
  for (const source of sources) {
    // string literals only; code identifiers such as `unavailable` are fine
    const literals = [...source.matchAll(/(['"`])((?:\\.|(?!\1)[^\\])*)\1/g)].map(match => match[2]);
    for (const text of literals) {
      assert.doesNotMatch(text, /^\s*(Unavailable|Not available|N\/A|No data)\s*$/i, text);
      assert.doesNotMatch(text, /Methodology under review|Not published for this period|Source not published/i, text);
    }
  }
});

test('Carbon Story carries provenance labels and skips acts without a number', () => {
  const story = read('walkthrough.js').replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
  assert.match(story, /card\.querySelector\('\.kpi-source'\)/);
  assert.match(story, /split\.querySelector\('\.kpi-source'\)/);
  assert.match(story, /if \(!c \|\| c\.na \|\| c\.value == null\) return;/);
  assert.match(story, /if \(cfg\.provenance\) copy\.appendChild\(el\('div', 'wt-source', cfg\.provenance\)\)/);
  assert.match(story, /if \(!ledgerRows\.length\) return;/);
  assert.doesNotMatch(story, /Gross − avoided|Net impact|netVal|ledgerReady/);
});

test('the 2025 annual water total is backend data, never a frontend constant', () => {
  for (const file of ['app.js', 'public-data-loader.js', 'public-api.js', 'walkthrough.js', 'index.html']) {
    assert.doesNotMatch(read(file), /195[,_]?708|27994/, file);
  }
  // Total water usage is a backend display item like every other KPI.
  assert.match(read('app.js'), /'Total water usage': \{ code: 'water_consumed_kl' \}/);
});

test('Overview and GHG share public labels bound to the governed fields; GHG mix charts lay out from stable CSS', () => {
  const app = read('app.js');
  const html = read('index.html');
  const css = read('styles.css');
  // Labels are display text only; each maps to the one authoritative backend field.
  assert.match(app, /'Reduction through renewables': \{ code: 'estimated_avoided_grid_emissions_tco2e' \}/);
  assert.match(app, /'Per capita emissions': \{ code: 'operational_ghg_per_capita_kgco2e' \}/);
  assert.match(app, /net: shownValue\('operational_ghg_per_capita_kgco2e'\)/);
  assert.match(app, /avoid: shownValue\('estimated_avoided_grid_emissions_tco2e'\)/);
  assert.match(app, /labelEl\.textContent = "Per capita emissions"/);
  assert.match(app, /labelEl\.textContent = "Reduction through renewables"/);
  assert.match(html, /<\/i>Per capita emissions<\/span>/);
  assert.match(html, /<\/i>Reduction through renewables<\/span>/);
  assert.doesNotMatch(app + html, /per capita income/i);
  // More avoided emissions is good; per-person emissions keep lower-is-better.
  assert.match(app, /ghgKpi\('Reduction through renewables', avoid, 'tCO₂e', colors\.emerald, 'leaf', previousValue\('avoidEm'\), false, 3\)/);
  assert.match(app, /ghgKpi\('Per capita emissions', operationalPerCapita, 'kgCO₂e\/person', colors\.blue, 'users', null, true, 3\)/);
  // GHG KPI card contract.
  const ghg = app.match(/document\.getElementById\('ghgKpis'\)\.innerHTML = \[([\s\S]*?)\]\.join\(''\);/);
  assert.deepEqual([...ghg[1].matchAll(/ghgKpi\('([^']+)'/g)].map(m => m[1]), [
    'Petrol emissions', 'Fleet diesel emissions', 'DG diesel emissions', 'LPG emissions',
    'Grid electricity emissions', 'Per capita emissions', 'Reduction through renewables'
  ]);
  // Charts: every rebuild destroys the previous instances first; no timer-based layout fix.
  assert.match(app, /function drawCharts\(\) \{\s*killCharts\(\);\s*redrawWhenChartFontLoads\(\);/);
  assert.match(app, /function killCharts\(\) \{ Object\.values\(charts\)\.forEach\(c => c\.destroy\(\)\); charts = \{\}; \}/);
  assert.match(app, /document\.fonts\.load\(font\)\.then\(/);
  assert.doesNotMatch(app.slice(app.indexOf('function redrawWhenChartFontLoads'), app.indexOf('function drawCharts')), /setTimeout/);
  // Mix-widget layout is static CSS (not injected per render) and sized by its own container.
  assert.doesNotMatch(app, /<style>\s*\.elec-mix-widget|<style>\s*\.fuel-mix-widget/);
  assert.match(css, /\.elec-mix-widget\.fuel-mix-widget \{/);
  assert.match(css, /#elecMixWidget, #fuelMixWidget \{ container-type: inline-size; \}/);
  assert.match(css, /#ghg \.row > \* \{ min-width: 0; \}/);
  assert.doesNotMatch(css.slice(css.indexOf('GHG mix widgets')), /left:\s*\d{3,}px|margin-left:\s*\d{3,}px|translateX\(/);
});
