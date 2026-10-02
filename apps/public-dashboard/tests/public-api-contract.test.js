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
  assert.match(app, /totalElectricityKwh: Array\(12\)\.fill\(null\)/);
  assert.match(app, /const cleanZero = arr => \(Array\.isArray\(arr\) \? arr : Array\(12\)\.fill\(null\)\)\.slice\(\);/);
});

// Legacy compatibility: frozen litre-era releases (schema <= 1.4, e.g. the Sep 2026
// TEST releases) stay readable. Active LPG methodology is kg; see the 1.5 test below.
test('adapter still reads a frozen litre-era release (legacy compatibility)', async () => {
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
  // That frozen payload never carried lpg_weight_kg, so it reads as unavailable.
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
  // Governed LPG activity is weight in kg; the deprecated litre metric is not read.
  assert.match(loader, /lpgKg: 'lpg_weight_kg'/);
  assert.doesNotMatch(loader, /lpg_consumption_litres|lpgL\b/);
  assert.doesNotMatch(loader, /2\.98/);
  // No file on the loaded governed path may carry a factor constant.
  for (const file of ['public-api.js', 'public-data-loader.js', 'app.js']) {
    assert.doesNotMatch(read(file), /2\.388|2\.701|0\.727|0\.71|1\.5571|2\.939/, file);
  }
  assert.match(loader, /green_master\.csv/);
});

test('public routes stay same-origin and Nginx proxies /api/', () => {
  const routes = ['/api/public/dashboard', '/api/public/dashboard/history', '/api/public/dashboard/timeline'];
  const adapter = read('public-api.js');
  for (const route of routes) {
    assert.ok(adapter.includes(`'${route}'`), `public-api.js must request ${route}`);
  }
  assert.doesNotMatch(adapter, /localhost|127\.0\.0\.1|:8000/);
  const nginx = fs.readFileSync(
    path.resolve(root, '..', '..', 'deployment', 'nginx', 'sustainability.kct.ac.in.conf'),
    'utf8'
  );
  assert.match(nginx, /location \/api\//);
  assert.match(nginx, /proxy_pass http:\/\/kcosmos_api/);
  // Public certificates use the same same-origin /api/ path: two listing routes and a per-document
  // file route, all under /api/public/certificates, which the Nginx /api/ location already proxies.
  const certificates = read('certificates.js');
  assert.match(certificates, /const YEARS_ROUTE = '\/api\/public\/certificates\/years';/);
  assert.match(certificates, /const LIST_ROUTE = '\/api\/public\/certificates';/);
  assert.match(certificates, /const fileRoute = id => `\$\{LIST_ROUTE\}\/\$\{encodeURIComponent\(id\)\}\/file`;/);
  assert.doesNotMatch(certificates, /localhost|127\.0\.0\.1|:8000/);
  // The public dashboard never calls an authenticated, admin or manager route.
  for (const file of ['public-api.js', 'public-data-loader.js', 'certificates.js', 'app.js']) {
    assert.doesNotMatch(read(file), /\/api\/(auth|admin|manager)/, file);
  }
});

test('Weather reads persisted Aeron data same-origin and can never trigger ingestion', () => {
  const weather = read('weather.js');
  const code = weather.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
  assert.match(code, /const API_BASE = '\/api\/environment';/);
  assert.match(code, /request\('\/latest'\)/);
  assert.match(code, /request\(`\/history\?limit=\$\{limit\}`\)/);
  assert.doesNotMatch(code, /:8000|:8001|localhost|127\.0\.0\.1/);
  assert.doesNotMatch(code, /method:\s*'POST'|['"]POST['"]|\/sync/);
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
  // LPG is displayed on its governed kg basis; the deprecated litre series is gone.
  assert.match(app, /lpgKg/);
  assert.doesNotMatch(app, /lpgL\b|lpg_consumption_litres/);
  assert.match(app, /'LPG consumption', valFor\(d, d\.lpgKg, month\), 'kg'/);
  assert.match(app, /rows\.push\(\[year, m, 'S1', 'LPG', d\.lpgKg\[i\], 'kg', d\.lpgEF\[i\], d\.lpgEm\[i\]\]\)/);
  // No runtime LPG factor, and LPG emissions are never derived in the browser.
  assert.doesNotMatch(app, /2\.98/);
  assert.doesNotMatch(app, /lpgKg[^\n]*\*|\*[^\n]*lpgKg/);
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
  lpg_emissions: tv(0.003114, 'lpg', { kind: 'calculation', provenance: { factor_value: '2.98' } }),
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
  assert.equal(item.lpgEF[8], 2.98);
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
  assert.match(app, /s2: \[\['Grid electricity', 'elecEm', 'scope2_tco2e', colors\.cyan\]\]/);
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
  assert.match(app, /title: 'Total electricity consumption', code: 'total_electricity_consumption_kwh', series: 'totalElectricityKwh'/);
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
  // Waste per person is shown in kg/person (one decimal) from the backend value.
  assert.match(app, /code: 'waste_per_capita_kg', unit: 'kg\/person', perUnit: 1,/);
  assert.match(app, /percentage\.toFixed\(percentage > 0 && percentage < 0\.1 \? 3 : 1\)/);
});

test('private water source terminology matches water_private_kl', () => {
  const app = read('app.js');
  const html = read('index.html');
  assert.match(app, /\['Private water supply', 'waterProcured', 'water_private_kl', colors\.gold\]/);
  assert.match(app, /label: 'Private water supply', data: wsl\(d\.waterProcured\)/);
  assert.match(html, /<h2>Private water supply<\/h2>/);
  assert.match(html, /TWAD \/ Borewell \/ Private water supply values/);
});

test('energy total reads the combined value published by the backend', () => {
  const app = read('app.js');
  assert.match(app, /title: 'Total electricity consumption', code: 'total_electricity_consumption_kwh', series: 'totalElectricityKwh'/);
  assert.match(app, /valFor\(d, d\[card\.series\], month\)/);
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

test('Water, Waste and Outreach grids shrink and stack on narrow screens without touching other pages', () => {
  const css = read('styles.css');
  const html = read('index.html');
  // The desktop column counts stay inline in the markup.
  for (const id of ['waterKpis', 'wasteKpis', 'outreachKpis']) {
    assert.match(html, new RegExp(`id="${id}" style="grid-template-columns: repeat\\(3, 1fr\\);"`));
  }
  // Cards (and the Chart.js canvases inside them) may shrink below their content width.
  assert.match(css, /#water \.kpi-grid > \*, #waste \.kpi-grid > \*, #outreach \.kpi-grid > \*,\s*#water \.row > \*, #waste \.row > \*, #outreach \.row > \* \{ min-width: 0; \}/);
  // The shared breakpoints are re-applied to these grids only.
  const block = css.slice(css.indexOf('/* ---- Water / Waste / Outreach responsive layout'), css.indexOf('/* ---- GHG mix widgets'));
  assert.match(block, /@media \(max-width: 1040px\) \{[^}]*#waterKpis, #wasteKpis, #outreachKpis \{ grid-template-columns: repeat\(2, 1fr\) !important; \}[\s\S]*#waste \.row\.g2 \{ grid-template-columns: 1fr !important; \}/);
  assert.match(block, /@media \(max-width: 600px\) \{\s*#waterKpis, #wasteKpis, #outreachKpis \{ grid-template-columns: 1fr !important; \}/);
  assert.doesNotMatch(block, /#(?:overview|ghg|energy|green)\b|\.topbar/);
  assert.doesNotMatch(css, /(?:html|body|\.page|#water|#waste|#outreach)\s*\{[^}]*overflow-x:\s*hidden/);
});

// ---- Single-period composition charts (GHG mixes / profile, Water sources) ----
function compositionHelpers() {
  const app = read('app.js');
  const fn = name => app.match(new RegExp(`function ${name}\\([\\s\\S]*?\\n\\}`))[0];
  const constant = name => app.match(new RegExp(`const ${name} = [\\s\\S]*?\\n[\\]}];`))[0];
  const source = ['valFor', 'periodComposition', 'compositionNote', 'contextComposition'].map(fn)
    .concat(['ELEC_MIX_PARTS', 'FUEL_MIX_PARTS', 'GHG_PROFILE_PARTS', 'WATER_SOURCE_PARTS'].map(constant)).join('\n');
  return vm.runInNewContext(`${source}\n({ periodComposition, compositionNote, contextComposition, ELEC_MIX_PARTS, FUEL_MIX_PARTS, GHG_PROFILE_PARTS, WATER_SOURCE_PARTS })`, {
    n: Number, Array, colors: { cyan: 'c', teal: 't', gold: 'g', orange: 'o', violet: 'v' }
  });
}
// Jan = 10, Feb = missing, Mar = 30 for every component; the YTD record is the
// backend's own aggregate and deliberately differs from any browser sum.
async function compositionFixture() {
  const month = (m, v) => tlMonth(2027, m, {
    grid_total_kwh: tv(v, 'energy'), renewable_electricity_kwh: tv(v, 'energy'),
    renewable_on_campus_kwh: tv(v, 'energy'), renewable_procured_kwh: tv(v, 'energy'),
    dg_diesel_emissions: tv(v, 'transport'), transport_diesel_emissions: tv(v, 'transport'),
    transport_petrol_emissions: tv(v, 'transport'), lpg_emissions: tv(v, 'lpg'), scope2_tco2e: tv(v, 'ghg'),
    water_twad_kl: tv(v, 'water'), water_borewell_kl: tv(v, 'water'), water_private_kl: tv(v == null ? null : 0, 'water')
  });
  const agg = (code, domain, v, extra) => tv(v, domain, { granularity: 'YTD', ...extra });
  const ytd = tlAggregate('2027-YTD', 2027, 'YTD', 3, {
    grid_total_kwh: agg('grid_total_kwh', 'energy', 777, { coverage_status: 'partial', months_covered: ['2027-01', '2027-03'] }),
    renewable_electricity_kwh: agg(0, 'energy', 888), renewable_on_campus_kwh: agg(0, 'energy', 444), renewable_procured_kwh: agg(0, 'energy', 444),
    dg_diesel_emissions: agg(0, 'transport', 111), transport_diesel_emissions: agg(0, 'transport', 222),
    transport_petrol_emissions: agg(0, 'transport', 333), lpg_emissions: agg(0, 'lpg', 99), scope2_tco2e: agg(0, 'ghg', 555),
    water_twad_kl: agg(0, 'water', 1000), water_borewell_kl: agg(0, 'water', 2000), water_private_kl: agg(0, 'water', 0)
  }, '2027 YTD · Jan–Mar');
  const { data } = await loadDashboardFromTimeline(timelineOf([ytd, month(1, 10), month(2, null), month(3, 30)], '2027-03'));
  return data['2027'];
}

test('GHG mixes, Emission Profile and Water sources draw the selected period, never a year sum', async () => {
  const h = compositionHelpers();
  const d = await compositionFixture();
  // Copy out of the vm realm so strict deep-equality compares values, not prototypes.
  const values = (parts, month) => [...h.periodComposition(d, month, parts).map(part => part.value)];
  const profile = [...h.GHG_PROFILE_PARTS.s1, ...h.GHG_PROFILE_PARTS.s2];
  for (const parts of [h.ELEC_MIX_PARTS, h.FUEL_MIX_PARTS, profile]) {
    // Mar selected -> Mar only (30), not the Jan+Mar sum (40) and not Jan (10).
    assert.deepEqual(values(parts, 2), [...parts].map(() => 30));
    // Feb is missing -> stays missing: not 0, not 10, not a sum.
    assert.deepEqual(values(parts, 1), [...parts].map(() => null));
  }
  // Water: a published 0 is a real 0; a missing month is null.
  assert.deepEqual(values(h.WATER_SOURCE_PARTS, 2), [30, 30, 0]);
  assert.deepEqual(values(h.WATER_SOURCE_PARTS, 1), [null, null, null]);
  // YTD reads the backend aggregate record (which differs from any monthly sum).
  assert.deepEqual(values(h.ELEC_MIX_PARTS, 'all'), [777, 888, 444, 444]);
  assert.deepEqual(values(h.FUEL_MIX_PARTS, 'all'), [111, 222, 333, 99]);
  assert.deepEqual(values(profile, 'all'), [222, 111, 333, 99, 555]);
  assert.deepEqual(values(h.WATER_SOURCE_PARTS, 'all'), [1000, 2000, 0]);
  // Partial aggregate coverage is carried to the chart's note.
  const grid = h.periodComposition(d, 'all', h.ELEC_MIX_PARTS)[0];
  assert.deepEqual([grid.partial, grid.monthsCovered], [true, 2]);
  assert.equal(h.compositionNote(h.periodComposition(d, 'all', h.ELEC_MIX_PARTS), '2027 YTD'), 'Partial: Grid electricity (2 month(s) reported).');
  assert.equal(h.compositionNote(h.periodComposition(d, 1, h.FUEL_MIX_PARTS), 'Feb 2027'), 'Not published for Feb 2027: DG diesel, Fleet diesel, Petrol, LPG.');
});

test('a month with only annual water data shows that annual record, labelled as annual', async () => {
  const h = compositionHelpers();
  const annual = { display_context: true, source_key: '2028-FY', source_granularity: 'ANNUAL', display_label: '2028 Annual Data' };
  const may = tlMonth(2028, 5, {});
  may.display = { water_twad_kl: { ...annual, value: 400 }, water_borewell_kl: { ...annual, value: 600 } };
  const fy = tlAggregate('2028-FY', 2028, 'ANNUAL', 12, {
    water_twad_kl: tv(400, 'water', { granularity: 'ANNUAL' }), water_borewell_kl: tv(600, 'water', { granularity: 'ANNUAL' })
  }, '2028 Full Year');
  const { data } = await loadDashboardFromTimeline(timelineOf([fy, may], '2028-05'));
  const d = data['2028'];
  // The month has no source values of its own ...
  assert.ok(h.periodComposition(d, 4, h.WATER_SOURCE_PARTS).every(part => part.value == null));
  // ... so the chart shows the backend's annual context, carrying its annual label.
  const context = h.contextComposition(d, 4, h.WATER_SOURCE_PARTS);
  assert.equal(context.label, '2028 Annual Data');
  assert.deepEqual([...context.parts.map(part => part.value)], [400, 600, null]);
  // Full Year reads the annual record directly; aggregates never use the context path.
  assert.deepEqual([...h.periodComposition(d, 'all', h.WATER_SOURCE_PARTS).map(part => part.value)], [400, 600, null]);
  assert.equal(h.contextComposition(d, 'all', h.WATER_SOURCE_PARTS), null);
  // Mixed sources (one monthly, one annual) are never drawn as one period.
  may.display.water_twad_kl = { ...annual, source_key: '2028-05', display_context: false, value: 400 };
  const mixed = await loadDashboardFromTimeline(timelineOf([fy, may], '2028-05'));
  assert.equal(h.contextComposition(mixed.data['2028'], 4, h.WATER_SOURCE_PARTS), null);
});

test('composition charts carry a visible period and keep no year-sum or hard-coded period', () => {
  const app = read('app.js');
  const html = read('index.html');
  const draw = app.slice(app.indexOf('function drawCharts()'), app.indexOf("mk('waterSourceChartCanvas'"));
  // Each chart's data comes from the selected-period helper.
  assert.match(draw, /const profileParts = periodComposition\(d, month, \[/);
  assert.match(draw, /const \[gridVal, reVal, reOnCampusVal, reProcuredVal\] = periodComposition\(d, month, ELEC_MIX_PARTS\)/);
  assert.match(draw, /const fuelMix = fuelMixView\(d, month\);/);
  assert.match(app, /const \[dg, fleet, petrol, lpg\] = periodComposition\(d, month, FUEL_MIX_PARTS\)/);
  assert.match(draw, /let waterSources = periodComposition\(d, month, WATER_SOURCE_PARTS\)/);
  // No year sums feed these four charts any more.
  assert.doesNotMatch(draw, /sum\(esl\(|ghgData\.push\(sum|const waterTWAD = sum|waterTWADAnnual/);
  // Visible period labels come from periodLabel / the backend label, never literals.
  assert.match(html, /Split of emissions produced by all factors<span id="ghgProfilePeriod"><\/span>\./);
  assert.match(html, /Share of consumption by source<span id="waterSourcePeriod"><\/span>/);
  assert.match(draw, /ghgProfilePeriod\.textContent = ` — \$\{periodLabel\(year, month\)\}`/);
  assert.match(draw, /waterSourcePeriod\.textContent = ` — \$\{waterSourceBasis\}`/);
  const helpers = app.slice(app.indexOf('function periodComposition'), app.indexOf('const ELEC_MIX_PARTS')).replace(/\/\*[\s\S]*?\*\//g, '');
  assert.doesNotMatch(helpers, /\b20\d\d\b|\|\| 0|sum\(/);
  // The Scope 1 vs Scope 2 trend stays a monthly year trend.
  assert.match(app, /label: 'S2: Grid electricity', data: sl\(d\.elecEm\)/);
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
  assert.match(app, /overviewKpi\('Total green cover', hasPublication \? green\.totalGreenCoverPct : null/);
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
  // The legacy static reference is no longer a Waste page KPI.
  assert.doesNotMatch(app, /kpi\('Landfill diversion', landfillDiversionPct/);
  assert.match(app, /title: 'Consumption per capita', code: 'water_per_capita_l', series: 'waterPerCapitaL', unit: 'L\/person'/);
  // Avoided emissions are not an Energy primary KPI; the GHG page and hero carry them.
  assert.doesNotMatch(app, /kpi\('Estimated avoided grid emissions'/);
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
    'Petrol emissions', 'Fleet diesel emissions', 'DG diesel emissions',
    // DG activity (0015_dg_kwh_methodology): source kWh + derived litres, or legacy source litres.
    'DG generation', 'Derived DG diesel', 'DG diesel consumption',
    'LPG emissions', 'LPG consumption',
    'Grid electricity emissions', 'Per capita emissions', 'Reduction through renewables'
  ]);
  // LPG activity is shown in kg from the backend's lpg_weight_kg display item.
  assert.match(app, /'LPG consumption': \{ code: 'lpg_weight_kg', transform: v => \(\{ value: v, unit: 'kg', dec: activityDecimals\(v\) \}\) \}/);
  assert.match(app, /ghgKpi\('LPG consumption', valFor\(d, d\.lpgKg, month\), 'kg'/);
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

test('adapter reads a schema-1.5 release whose LPG activity is governed kg', async () => {
  const api = adapterContext(async () => ({
    ok: true,
    json: async () => ({
      release: { version: 'synthetic-1-5', published_at: '2027-02-01T00:00:00Z' },
      schema_version: '1.5', period: { id: 'period', year: 2027, month: 1 },
      lpg: {
        metrics: { lpg_weight_kg: { value: 7429, unit: 'kg' } },
        calculations: [{
          calculation_code: 'lpg_emissions', status: 'available', activity_metric_code: 'lpg_weight_kg',
          activity_value: 7429, activity_unit: 'kg', factor_code: 'LPG_KG', factor_value: 2.98,
          factor_unit: 'kgCO2e/kg', result_value: 22.13842, result_unit: 'tCO2e'
        }]
      }
    })
  }));
  const result = await api.load();
  const weight = api.metric(result.domains.lpg, 'lpg_weight_kg');
  assert.equal(weight.value, 7429);
  assert.equal(weight.unit, 'kg');
  assert.equal(api.metric(result.domains.lpg, 'lpg_consumption_litres').status, 'unavailable');
  const emission = api.calculation(result.domains.lpg, 'lpg_emissions');
  assert.equal(emission.value, 22.13842);
});

test('timeline LPG kg activity, backend emission and factor provenance reach the dashboard unchanged', async () => {
  const kg = (value, month) => tlMonth(2026, month, {
    lpg_weight_kg: tv(value, 'lpg', { unit: 'kg' }),
    lpg_emissions: tv({ 1: 22.13842, 7: 4.33143 }[month], 'lpg', {
      kind: 'calculation', unit: 'tCO2e', provenance: { factor_code: 'LPG_KG', factor_value: '2.98' }
    })
  });
  const ytd = tlAggregate('2026-YTD', 2026, 'YTD', 7, {
    lpg_weight_kg: tv(21084.3, 'lpg', { unit: 'kg', granularity: 'YTD', months_covered: ['2026-01', '2026-07'] }),
    lpg_emissions: tv(62.831214, 'lpg', { kind: 'calculation', unit: 'tCO2e', granularity: 'YTD' })
  }, '2026 YTD · Jan–Jul');
  const loaded = await loadDashboardFromTimeline(timelineOf([ytd, kg(7429, 1), kg(1453.5, 7)], '2026-06'));
  const item = loaded.data['2026'];
  assert.equal(item.lpgKg[0], 7429);
  assert.equal(item.lpgKg[6], 1453.5);
  assert.equal(item.lpgEm[0], 22.13842);
  assert.equal(item.lpgEm[6], 4.33143);
  assert.equal(item.lpgEF[0], 2.98);
  // The YTD figure is the backend's own sum, never a browser sum.
  assert.equal(item.lpgKg.aggregate, 21084.3);
  assert.equal(item.lpgEm.aggregate, 62.831214);
  assert.ok(!('lpgL' in item));
  // The backend chooses the default period; one LPG-only month never moves it.
  assert.equal(loaded.defaultKey, '2026-06');
  // Data Explorer: LPG activity rows carry the backend unit (kg); emissions stay tCO2e.
  // Copied out of the vm realm so deep-equality compares values, not prototypes.
  const lpgRows = JSON.parse(JSON.stringify(loaded.explorerRows.filter(row => row[3] === 'lpg')));
  assert.deepEqual([...new Set(lpgRows.map(row => row[6]))].sort(), ['kg', 'tCO2e']);
  assert.deepEqual(lpgRows.filter(row => row[6] === 'kg').map(row => row[5]).sort((a, b) => a - b), [1453.5, 7429, 21084.3]);
});

// The GHG completeness helpers of app.js (they only print backend metadata).
function completenessSource(app) {
  return app.match(/\/\* ---- GHG completeness[\s\S]*?\/\* ---- end GHG completeness ---- \*\//)[0];
}

// ---- Overview hero priority (runs the real heroGHG from app.js) -------------
function heroHarness() {
  const app = read('app.js');
  const block = app.match(/let currentHeroView = [\s\S]*?\n  updateDisplayView\(\);\n\}/)[0];
  const completeness = completenessSource(app);
  const els = {};
  const el = id => els[id] || (els[id] = {
    id, style: {}, textContent: '', onclick: null, classList: { add() {}, remove() {} }, closest: () => els.section
  });
  els.section = { style: {} };
  let figures = {};
  const context = {
    document: { getElementById: el, querySelectorAll: () => [] },
    // Mirrors app.js shownValue(): a null backend value is no figure at all.
    shownValue: code => (figures[code] && figures[code].value != null ? figures[code] : null),
    fmt: value => (value == null ? '' : String(value)),
    periodLabel: () => '', reduceMotion: true, Object
  };
  vm.runInNewContext(`${completeness}\n${block}\nglobalThis.heroGHG = heroGHG;`, context);
  const codes = { net: 'operational_ghg_per_capita_kgco2e', gross: 'operational_ghg_tco2e', avoid: 'estimated_avoided_grid_emissions_tco2e' };
  return {
    // meta: { net|gross|avoid: { calculation_status, contributors, missing_contributors } }
    select(year, month, values, meta = {}) {
      figures = Object.fromEntries(Object.entries(values).map(([view, value]) => [codes[view], { value, label: `${year}-${month}`, ...(meta[view] || {}) }]));
      context.heroGHG(null, year, month, {}, null, null);
    },
    note: () => (els.balPartialNote ? els.balPartialNote.innerHTML || '' : ''),
    click(view) { els[`tab-${view}`].onclick(); },
    big: () => ({ label: els.balLabel.textContent, value: els['hero-ghg'].textContent, unit: els['hero-unit'].textContent }),
    tabs: () => ({ net: els.balNetVal.textContent, gross: els.balGrossVal.textContent, avoid: els.balAvoidVal.textContent }),
    hidden: () => els.section.style.display === 'none'
  };
}

test('Overview hero re-runs per capita > operational > avoided priority for every new period', () => {
  const hero = heroHarness();
  // June 2026: only avoided emissions exist.
  hero.select(2026, '5', { avoid: 177.54067 });
  assert.deepEqual(hero.big(), { label: 'Reduction through renewables', value: '177.54067', unit: 'tCO₂e' });
  // Switching to March 2025 re-evaluates: per capita wins (the old view was sticky).
  hero.select(2025, '2', { net: 34.622491, gross: 242.045834, avoid: 135.366673 });
  assert.deepEqual(hero.big(), { label: 'Per capita emissions', value: '34.622491', unit: 'kgCO₂e/person' });
  // A manual tab click persists while the same period stays selected (re-renders included).
  hero.click('gross');
  assert.equal(hero.big().label, 'Operational GHG');
  hero.select(2025, '2', { net: 34.622491, gross: 242.045834, avoid: 135.366673 });
  assert.deepEqual(hero.big(), { label: 'Operational GHG', value: '242.045834', unit: 'tCO₂e' });
  // A new period resets the priority.
  hero.select(2025, '3', { net: 20.328456, gross: 142.116238, avoid: 180.479204 });
  assert.equal(hero.big().label, 'Per capita emissions');
  // No per capita, operational present: operational is the hero.
  hero.select(2027, '0', { gross: 12.5, avoid: 3 });
  assert.deepEqual(hero.big(), { label: 'Operational GHG', value: '12.5', unit: 'tCO₂e' });
  // Only avoided: avoided is the hero.
  hero.select(2027, '1', { avoid: 3 });
  assert.equal(hero.big().label, 'Reduction through renewables');
  // Nothing available: the card is hidden, as before.
  hero.select(2027, '2', {});
  assert.equal(hero.hidden(), true);
});

test('Overview hero shows a backend zero as 0, never as missing', () => {
  const hero = heroHarness();
  hero.select(2027, '3', { net: 0, gross: 0, avoid: 0 });
  assert.equal(hero.hidden(), false);
  assert.deepEqual(hero.big(), { label: 'Per capita emissions', value: '0', unit: 'kgCO₂e/person' });
  hero.select(2027, '4', { gross: 0, avoid: 5 });
  assert.deepEqual(hero.big(), { label: 'Operational GHG', value: '0', unit: 'tCO₂e' });
  hero.select(2027, '5', { avoid: 0 });
  assert.deepEqual(hero.big(), { label: 'Reduction through renewables', value: '0', unit: 'tCO₂e' });
  // A null backend value is still missing, never a visible zero.
  hero.select(2027, '6', { avoid: null });
  assert.equal(hero.hidden(), true);
});

// ---- Current-year water recycled / total waste KPIs --------------------------
test('current-year YTD selector reads "YTD" and an unknown-end figure never borrows a month range', async () => {
  const ytd = tlAggregate('2026-YTD', 2026, 'YTD', 7, {
    water_recycled_kl: tv(47256, 'water', { unit: 'KL', granularity: 'YTD', coverage_label: '2026 YTD' }),
    total_waste_generated_kg: tv(79590.6, 'waste', { unit: 'kg', granularity: 'YTD', coverage_label: '2026 YTD' })
  }, '2026 YTD · Jan–Jul');
  ytd.values.water_recycled_kl.coverage_label = '2026 YTD';
  ytd.values.total_waste_generated_kg.coverage_label = '2026 YTD';
  const timeline = timelineOf([ytd, tlMonth(2026, 6, { water_consumed_kl: tv(19388, 'water', { unit: 'KL' }) })], '2026-06');
  timeline.selector[0].options[0].label = 'YTD';  // the backend's selector label
  const loaded = await loadDashboardFromTimeline(timeline);
  const options = JSON.parse(JSON.stringify(loaded.selector[0].options));
  assert.equal(options[0].label, 'YTD');
  const rows = JSON.parse(JSON.stringify(loaded.explorerRows.filter(row => row[1] === '2026 YTD · Jan–Jul')));
  assert.equal(rows.length, 2);
  rows.forEach(row => {
    assert.equal(row[8], '2026 YTD, end month not stated');
    assert.doesNotMatch(row[8], /Jan|Jun|Jul|2026-07-/);
  });
  // The data values are the backend's own; the browser does not sum or relabel them.
  assert.equal(loaded.data['2026'].waterRecycledKL.aggregate, 47256);
  assert.equal(loaded.data['2026'].totalWaste.aggregate, 79590.6);
});

test('Overview keeps "Total water recycled" and "Total waste generated"; no recycled-waste card exists', () => {
  const app = read('app.js');
  const html = read('index.html');
  assert.match(app, /'Total water recycled': \{ code: 'water_recycled_kl' \}/);
  assert.match(app, /'Total waste generated': \{ code: 'total_waste_generated_kg', transform: kgOrTonnes \}/);
  assert.doesNotMatch(app + html, /Total waste recycled/i);
  // Both cards render only from the backend display item for the selection.
  assert.match(app, /if \(!item\) return '';  \/\/ no trustworthy number for this selection: omit the card/);
});

// ---- Available-data GHG methodology: PARTIAL / COMPLETE and contributors ----
// The backend calculates Scope 1 / Scope 2 / Operational GHG / per capita from
// the emission sources that exist and states what contributed and what is
// missing. The dashboard only prints that metadata.
const part = (code, label, value, unit = 'tCO2e', extra = {}) => ({ code, label, value, unit, status: 'COMPLETE', ...extra });
const absent = (code, label) => ({ code, label });
const PARTIAL_MAY = {
  calculation_status: 'PARTIAL',
  contributors: [part('lpg_emissions', 'LPG', 2.332744), part('grid_electricity_emissions', 'Grid electricity', 32.944005)],
  missing_contributors: [
    absent('transport_petrol_emissions', 'Petrol'), absent('transport_diesel_emissions', 'Fleet Diesel'),
    absent('dg_diesel_emissions', 'DG Diesel')
  ]
};
const COMPLETE_JAN = {
  calculation_status: 'COMPLETE',
  contributors: [
    part('transport_petrol_emissions', 'Petrol', 1.398556), part('transport_diesel_emissions', 'Fleet Diesel', 24.309),
    part('dg_diesel_emissions', 'DG Diesel', 4.8618), part('lpg_emissions', 'LPG', 22.13842),
    part('grid_electricity_emissions', 'Grid electricity', 33.763334)
  ],
  missing_contributors: []
};
function completenessHelpers() {
  const app = read('app.js');
  return vm.runInNewContext(
    `${completenessSource(app)}\n({ partialNoteHtml, completenessOf, ghgStatusLines, PARTIAL_NOTE })`,
    { fmt: (value, dec) => (value == null ? '' : Number(value).toFixed(dec)), Object, String, Number }
  );
}
const NOTE_HTML = '<div class="partial-note">*Based on available reported contributors</div>';
const CONTRIBUTOR_TEXT = /Contribution|LPG|Petrol|Fleet Diesel|DG Diesel|Grid electricity|not reported|available contributor|Complete|PARTIAL/;

test('a partial period keeps the three hero metrics and shows only the one-line partial footnote', () => {
  const hero = heroHarness();
  hero.select(2026, '4', { net: 5.046, gross: 35.276749, avoid: 247.712 }, { net: PARTIAL_MAY, gross: PARTIAL_MAY });
  assert.equal(hero.hidden(), false);
  // Priority unchanged: per capita first.
  assert.deepEqual(hero.big(), { label: 'Per capita emissions', value: '5.046', unit: 'kgCO₂e/person' });
  assert.deepEqual(hero.tabs(), { net: '5.046', gross: '35.276749', avoid: '247.712' });
  assert.equal(hero.note(), NOTE_HTML);
  // No contributor names, values, missing-source sentence or status word.
  assert.doesNotMatch(hero.note(), CONTRIBUTOR_TEXT);
  assert.doesNotMatch(hero.note(), /2\.332744|32\.944005/);
});

test('a complete period shows no contributor list, no "Complete" text and no partial footnote', () => {
  const hero = heroHarness();
  hero.select(2026, '2', { net: 10.460411, gross: 73.128735, avoid: 258.703 }, { net: COMPLETE_JAN, gross: COMPLETE_JAN });
  assert.deepEqual(hero.big(), { label: 'Per capita emissions', value: '10.460411', unit: 'kgCO₂e/person' });
  assert.deepEqual(hero.tabs(), { net: '10.460411', gross: '73.128735', avoid: '258.703' });
  assert.equal(hero.note(), '');
});

test('hero tab switching still works and the footnote follows the selected figure', () => {
  const hero = heroHarness();
  const lpgOnly = {
    calculation_status: 'PARTIAL', contributors: [part('lpg_emissions', 'LPG', 4.33143)],
    missing_contributors: [absent('grid_electricity_emissions', 'Grid electricity')]
  };
  hero.select(2026, '6', { net: 0.619573, gross: 4.33143, avoid: 9 }, { net: lpgOnly, gross: lpgOnly });
  assert.equal(hero.big().label, 'Per capita emissions');
  assert.equal(hero.note(), NOTE_HTML);
  hero.click('gross');
  assert.deepEqual(hero.big(), { label: 'Operational GHG', value: '4.33143', unit: 'tCO₂e' });
  assert.equal(hero.note(), NOTE_HTML);
  // Reduction through renewables carries no completeness: no footnote is invented for it.
  hero.click('avoid');
  assert.deepEqual(hero.big(), { label: 'Reduction through renewables', value: '9', unit: 'tCO₂e' });
  assert.equal(hero.note(), '');
  hero.click('net');
  assert.equal(hero.note(), NOTE_HTML);
});

test('period switching still works: complete -> partial -> metadata-free payload', () => {
  const hero = heroHarness();
  hero.select(2026, '0', { net: 12.368919, gross: 86.47111 }, { net: COMPLETE_JAN, gross: COMPLETE_JAN });
  assert.equal(hero.note(), '');
  hero.select(2026, '4', { net: 5.046, gross: 35.276749 }, { net: PARTIAL_MAY, gross: PARTIAL_MAY });
  assert.equal(hero.big().label, 'Per capita emissions');
  assert.equal(hero.note(), NOTE_HTML);
  hero.select(2026, '2', { net: 10.460411, gross: 73.128735 }, { net: COMPLETE_JAN, gross: COMPLETE_JAN });
  assert.equal(hero.note(), '');
  // An older payload with no completeness metadata shows the number alone.
  hero.select(2025, '0', { net: 25.70589, gross: 179.709878 });
  assert.equal(hero.note(), '');
});

test('backend contributor metadata is accepted but never rendered in the Overview or GHG summary', () => {
  const { partialNoteHtml, completenessOf } = completenessHelpers();
  // Full metadata (including an explicit zero contributor) is accepted...
  const withZero = {
    value: 2.98, calculation_status: 'PARTIAL',
    contributors: [part('transport_petrol_emissions', 'Petrol', 0), part('lpg_emissions', 'LPG', 2.98)],
    missing_contributors: [absent('dg_diesel_emissions', 'DG Diesel')]
  };
  assert.equal(completenessOf(withZero).partial, true);
  // ...and the summary prints exactly one footnote for partial, nothing for complete.
  assert.equal(partialNoteHtml(withZero), NOTE_HTML);
  assert.equal(partialNoteHtml({ value: 5.046, ...PARTIAL_MAY }), NOTE_HTML);
  assert.equal(partialNoteHtml({ value: 12.3, ...COMPLETE_JAN }), '');
  assert.equal(partialNoteHtml({ value: 12.3 }), '');
  assert.equal(partialNoteHtml(null), '');

  const app = read('app.js');
  const html = read('index.html');
  const css = read('styles.css');
  // The contribution list renderer and its markup are gone everywhere.
  assert.doesNotMatch(app, /contributionHtml|statusBadge|contrib-row|contrib-title|contrib-status|contrib-missing|not reported|available contributor\$/);
  assert.doesNotMatch(html + css, /bal-contrib|contrib-row|contrib-status|kpi-status/);
  // The summary never reads the contributor arrays.
  const block = completenessSource(app);
  assert.doesNotMatch(block, /\.contributors|missing_contributors/);
  assert.doesNotMatch(block, /LPG|Petrol|Diesel|Grid|6991|2026|2025/);
  // Overview hero, GHG hero total, GHG Scope splits and KPI cards all use the single footnote.
  assert.match(app, /noteEl\.innerHTML = partialNoteHtml\(figures\[currentHeroView\]\);/);
  assert.match(html, /<div class="bal-partial-note" id="balPartialNote"/);
  assert.match(app, /\$\{sourceBadge\(total\.label, total\.context\)\}\$\{partialNoteHtml\(total\)\}/);
  assert.match(app, /\$\{sourceBadge\(item\.label, item\.context\)\}\n\s+\$\{partialNoteHtml\(item\)\}/);
  assert.match(app, /status = partialNoteHtml\(item\) \+ dgOriginNoteHtml\(item\);/);
  // The Scope 3 methodology footnote stays.
  assert.match(html, /\*Operational GHG covers the governed Scope 1 and Scope 2 boundary only\. Scope 3 is not included\./);
  // The footnote is small and secondary, and an empty holder leaves no gap.
  assert.match(css, /\.partial-note \{[^}]*font-size: 11px/);
  assert.match(css, /\.bal-partial-note:empty \{ display: none; \}/);
});

test('partial months reach the charts and the Data Explorer with status, contributors and missing sources', async () => {
  const ghg = (value, meta) => ({ ...tv(value, 'ghg', { kind: 'calculation', unit: 'tCO2e' }), ...meta });
  const scope1May = { calculation_status: 'PARTIAL', contributors: [PARTIAL_MAY.contributors[0]], missing_contributors: PARTIAL_MAY.missing_contributors };
  const may = tlMonth(2026, 5, {
    lpg_emissions: tv(2.332744, 'lpg', { kind: 'calculation', unit: 'tCO2e' }),
    grid_electricity_emissions: tv(32.944005, 'energy', { kind: 'calculation', unit: 'tCO2e' }),
    scope1_tco2e: ghg(2.332744, scope1May),
    scope2_tco2e: ghg(32.944005, { calculation_status: 'COMPLETE', contributors: [PARTIAL_MAY.contributors[1]], missing_contributors: [] }),
    operational_ghg_tco2e: ghg(35.276749, PARTIAL_MAY),
    operational_ghg_per_capita_kgco2e: { ...ghg(5.045594, PARTIAL_MAY), unit: 'kgCO2e/person' }
  });
  Object.entries(may.values).forEach(([code, value]) => { value.code = code; });
  may.display = { operational_ghg_tco2e: { value: 35.276749, unit: 'tCO2e', display_label: 'May 2026', display_context: false, ...PARTIAL_MAY } };
  const loaded = await loadDashboardFromTimeline(timelineOf([may], '2026-05'));
  const item = loaded.data['2026'], index = 4;
  // The month is plotted from its available values; it is not dropped.
  assert.equal(item.scope1Full[index], 2.332744);
  assert.equal(item.operationalGHG[index], 35.276749);
  assert.equal(item.perCapita[index], 5.045594);
  assert.equal(item.lpgEm[index], 2.332744);
  // Missing contributors stay missing (null), never 0.
  assert.equal(item.petrolEm[index], null);
  assert.equal(item.trDieselEm[index], null);
  assert.equal(item.dgEm[index], null);
  assert.equal(item.display[index].operational_ghg_tco2e.calculation_status, 'PARTIAL');

  const rows = JSON.parse(JSON.stringify(loaded.explorerRows));
  const row = code => rows.find(entry => entry[4] === code);
  assert.deepEqual(row('operational_ghg_tco2e').slice(11), [
    'PARTIAL', 'LPG 2.332744 tCO2e; Grid electricity 32.944005 tCO2e', 'Petrol; Fleet Diesel; DG Diesel'
  ]);
  assert.deepEqual(row('scope2_tco2e').slice(11), ['COMPLETE', 'Grid electricity 32.944005 tCO2e', '']);
  assert.equal(row('operational_ghg_per_capita_kgco2e')[11], 'PARTIAL');
  // Raw metric provenance is untouched: the original eleven columns keep their meaning.
  assert.deepEqual(row('lpg_emissions').slice(0, 11), ['2026', 'May 2026', 'MONTHLY', 'lpg', 'lpg_emissions', 2.332744, 'tCO2e', 'historical_verified', '2026-05-01 – 2026-05-28 (complete)', 'CALCULATED', '']);
  assert.deepEqual(row('lpg_emissions').slice(11), ['', '', '']);

  // Chart tooltip: the total and its status only - no per-fuel list.
  const { ghgStatusLines } = completenessHelpers();
  const lines = JSON.parse(JSON.stringify(ghgStatusLines(item, index)));
  assert.deepEqual(lines, ['Operational GHG: 35.277 tCO₂e', 'Status: Partial']);
  assert.deepEqual(JSON.parse(JSON.stringify(ghgStatusLines(item, 0))), []);  // no record for January

  const app = read('app.js');
  assert.match(app, /callbacks: \{ footer: items => \(items\.length \? ghgStatusLines\(d, items\[0\]\.dataIndex\) : \[\]\) \}/);
  assert.match(app, /'Verification', 'Qualifier', 'Calculation status', 'Contributors', 'Missing contributors'\]/);
  assert.match(app, /cols: \['Year', 'Month', 'Indicator', 'Published value', 'Unit', 'Calculation status'\]/);
});

// ---- DG generator methodology: kWh source, backend-derived litres ------------
// Legacy periods publish source-reported litres. From the governed SFC's
// effective date the backend publishes the source generation (kWh), the litres
// it derived and the emission. The browser never converts one into the other.
const DG_DERIVATION = {
  activity_origin: 'DERIVED_FROM_KWH', source_metric_code: 'dg_generation_kwh', source_value: '9006',
  source_unit: 'kWh', parameter_code: 'DG_SFC', parameter_value: '0.33', parameter_unit: 'L/kWh',
  parameter_effective_from: '2026-05-01', derived_metric_code: 'dg_diesel_litres', derived_value: '2971.98',
  derived_unit: 'L'
};
function dgTimeline() {
  const coded = values => { Object.entries(values).forEach(([code, value]) => { value.code = code; }); return values; };
  const april = tlMonth(2026, 4, coded({
    dg_diesel_litres: { ...tv(2136.83, 'transport', { unit: 'L', provenance: { verification_status: 'VERIFIED' } }), activity_origin: 'SOURCE_REPORTED_LITRES' },
    dg_diesel_emissions: { ...tv(5.771578, 'transport', { kind: 'calculation', unit: 'tCO2e', provenance: { factor_value: '2.701' } }), activity_origin: 'SOURCE_REPORTED_LITRES' }
  }));
  const may = tlMonth(2026, 5, coded({
    dg_generation_kwh: tv(9006, 'transport', { unit: 'kWh', provenance: { verification_status: 'VERIFIED' } }),
    dg_diesel_litres: { ...tv(2971.98, 'transport', { kind: 'calculation', unit: 'L', provenance: { derivation: DG_DERIVATION } }), activity_origin: 'DERIVED_FROM_KWH' },
    dg_diesel_emissions: { ...tv(8.027318, 'transport', { kind: 'calculation', unit: 'tCO2e', provenance: { factor_value: '2.701', derivation: DG_DERIVATION } }), activity_origin: 'DERIVED_FROM_KWH' },
    scope1_tco2e: tv(10.360062, 'ghg', { kind: 'calculation', unit: 'tCO2e' })
  }));
  return timelineOf([april, may], '2026-05');
}

test('a legacy month shows source litres and a kWh month shows generation plus backend-derived litres', async () => {
  const loaded = await loadDashboardFromTimeline(dgTimeline());
  const item = loaded.data['2026'], apr = 3, may = 4;
  // Legacy April: source-reported litres, and no kWh is invented for it.
  assert.equal(item.dgL[apr], 2136.83);
  assert.equal(item.dgKwh[apr], null);
  assert.equal(item.dgEm[apr], 5.771578);
  assert.equal(item.periodMeta[apr].values.dg_diesel_litres.activity_origin, 'SOURCE_REPORTED_LITRES');
  // May: the three backend values, taken as published.
  assert.equal(item.dgKwh[may], 9006);
  assert.equal(item.dgL[may], 2971.98);
  assert.equal(item.dgEm[may], 8.027318);
  assert.equal(item.periodMeta[may].values.dg_diesel_litres.activity_origin, 'DERIVED_FROM_KWH');
  // Scope 1 is the backend's own total (it already includes the DG emission).
  assert.equal(item.scope1Full[may], 10.360062);
});

test('Data Explorer states DG provenance: source kWh, governed SFC, derived litres, calculated emissions', async () => {
  const rows = JSON.parse(JSON.stringify((await loadDashboardFromTimeline(dgTimeline())).explorerRows));
  const of = (period, metric) => rows.find(row => row[1] === period && row[4] === metric);
  // metric, value, unit, ..., verification column [9]
  assert.deepEqual([of('May 2026', 'dg_generation_kwh')[5], of('May 2026', 'dg_generation_kwh')[6], of('May 2026', 'dg_generation_kwh')[9]], [9006, 'kWh', 'VERIFIED']);
  assert.deepEqual(of('May 2026', 'DG_SFC').slice(5, 10), [0.33, 'L/kWh', 'governed_parameter', 'effective from 2026-05-01', 'GOVERNED_PARAMETER']);
  assert.deepEqual([of('May 2026', 'dg_diesel_litres')[5], of('May 2026', 'dg_diesel_litres')[6], of('May 2026', 'dg_diesel_litres')[9]], [2971.98, 'L', 'DERIVED']);
  assert.deepEqual([of('May 2026', 'dg_diesel_emissions')[5], of('May 2026', 'dg_diesel_emissions')[9]], [8.027318, 'CALCULATED']);
  // Legacy April: litres are source data; no SFC row and no kWh row are fabricated.
  assert.deepEqual([of('Apr 2026', 'dg_diesel_litres')[5], of('Apr 2026', 'dg_diesel_litres')[9]], [2136.83, 'VERIFIED']);
  assert.equal(of('Apr 2026', 'DG_SFC'), undefined);
  assert.equal(of('Apr 2026', 'dg_generation_kwh'), undefined);
  assert.equal(rows.filter(row => row[4] === 'DG_SFC').length, 1);
  rows.forEach(row => assert.equal(row.length, 14));
});

test('DG cards and tables follow the backend origin and the browser never derives litres or emissions', () => {
  const app = read('app.js');
  const loader = read('public-data-loader.js');
  assert.match(app, /'DG generation': \{ code: 'dg_generation_kwh' \}/);
  assert.match(app, /'Derived DG diesel': \{ code: 'dg_diesel_litres', when: item => item\.activity_origin === 'DERIVED_FROM_KWH' \}/);
  assert.match(app, /'DG diesel consumption': \{ code: 'dg_diesel_litres', when: item => item\.activity_origin !== 'DERIVED_FROM_KWH' \}/);
  assert.match(app, /if \(spec\.when && !spec\.when\(item\)\) return '';/);
  // The two litre cards are mutually exclusive for any backend item.
  const when = title => vm.runInNewContext(`(${app.match(new RegExp(`'${title}': \\{ code: 'dg_diesel_litres', when: (item => [^}]+) \\}`))[1]})`);
  for (const origin of ['DERIVED_FROM_KWH', 'SOURCE_REPORTED_LITRES', 'MIXED', undefined]) {
    assert.notEqual(when('Derived DG diesel')({ activity_origin: origin }), when('DG diesel consumption')({ activity_origin: origin }));
  }
  assert.equal(when('Derived DG diesel')({ activity_origin: 'DERIVED_FROM_KWH' }), true);
  // A YTD total that spans the methodology change says so.
  const note = vm.runInNewContext(`${app.match(/function dgOriginNoteHtml\(item\) \{[\s\S]*?\n\}/)[0]}\ndgOriginNoteHtml`);
  assert.match(note({ activity_origin: 'MIXED' }), /Includes diesel litres derived from DG generation \(kWh\)/);
  assert.equal(note({ activity_origin: 'DERIVED_FROM_KWH' }), '');
  assert.equal(note({ activity_origin: 'SOURCE_REPORTED_LITRES' }), '');
  // Data Explorer tables: kWh and litres are separate columns with the litre origin stated.
  assert.match(app, /cols: \['Year', 'Month', 'DG Generation kWh', 'DG Diesel L', 'Diesel litres origin', 'DG Emissions tCO₂e'\]/);
  assert.match(app, /'DG Generation \(source\)', d\.dgKwh\[i\], 'kWh', null, null/);
  assert.match(app, /dgDerived \? 'DG Diesel \(derived from kWh\)' : 'DG Diesel'/);
  // DG chart: generation on its own kWh axis, never on the litre axis.
  assert.match(app, /label: 'DG generation \(kWh\)', data: sl\(d\.dgKwh\), [^}]*yAxisID: 'y2'/);
  assert.match(app, /y2: \{ position: 'right'[^}]*\}, border: \{ display: false \}, title: \{ display: true, text: 'kWh'/);
  // No authoritative DG arithmetic in the browser: no SFC, no diesel factor, no kWh->litre product.
  for (const source of [app, loader]) {
    assert.doesNotMatch(source, /0\.33\b/);
    assert.doesNotMatch(source, /2\.701/);
    assert.doesNotMatch(source, /dgKwh\[[^\]]*\]\s*\*/);
    assert.doesNotMatch(source, /dg_generation_kwh[^\n]*\*\s*[\d.]/);
  }
});

// ---- Community Outreach: YTD baseline, lower bounds and data-driven charts ---
// The backend publishes the 2026 outreach baseline as one year-to-date record
// ("through 17 Aug 2026") and adds later published months to it. The page only
// renders what the API sends: no outreach figure lives in the browser.
// Cards and charts say simply "2026 YTD"; the exact coverage dates stay in provenance.
const OUTREACH_LABEL = '2026 YTD';
function outreachYtd(overrides = {}) {
  const baseline = { aggregation: 'ytd_baseline_plus_later_months', baseline_coverage_start: '2026-01-01', baseline_coverage_end: '2026-08-17' };
  const lower = (value, unit) => ({ ...tv(value, 'outreach', { unit, granularity: 'YTD', qualifier: 'AT_LEAST', provenance: baseline }), coverage_label: OUTREACH_LABEL });
  const exact = (value, unit) => ({ ...tv(value, 'outreach', { unit, granularity: 'YTD' }), coverage_label: OUTREACH_LABEL });
  const values = {
    total_programs: lower(20, 'programmes'), volunteers_engaged: lower(364, 'people'), volunteer_hours: lower(1649, 'hours'),
    experts_involved: lower(34, 'people'), total_participants: lower(2009, 'people'),
    partner_organizations: lower(25, 'organizations'), saplings_planted: lower(400, 'saplings'),
    'theme:biodiversity_conservation': exact(6, 'programmes'), 'theme:campus_sustainability': exact(4, 'programmes'),
    'theme:water_conservation': exact(3, 'programmes'),
    'audience:school_students': exact(3, 'count'), 'audience:college_students': exact(15, 'count'),
    'audience:government': exact(0, 'count'),
    ...overrides
  };
  Object.entries(values).forEach(([code, value]) => { value.code = code; });
  const period = tlAggregate('2026-YTD', 2026, 'YTD', 7, values, '2026 YTD · Jan–Jul');
  period.domains = { outreach: { state: 'available' } };
  period.display = Object.fromEntries(Object.entries(values).map(([code, value]) => [code, {
    value: value.value, unit: value.unit, qualifier: value.qualifier, display_label: value.coverage_label || period.label,
    display_context: false, source_granularity: 'YTD'
  }]));
  return period;
}
/* Runs the real outreach chart block of drawCharts() and returns what it built. */
function renderOutreachCharts(outreach) {
  const app = read('app.js');
  const block = app.slice(app.indexOf('  /* Outreach charts use only the active published aggregate. */'), app.indexOf('  // Compute full-year arrays for Energy line charts'));
  const helpers = app.match(/\/\* ---- Outreach chart wording[\s\S]*?\/\* ---- end outreach chart wording ---- \*\//)[0];
  const humanize = app.match(/function humanizeCode\(code\) \{[^\n]*\}/)[0];
  const nodes = {}, charts = {};
  const context = {
    document: { getElementById: id => (nodes[id] ||= { style: {}, textContent: '' }) },
    outreach, mk: (id, config) => { charts[id] = config; },
    colors: { cyan: 'c', teal: 't', gold: 'g', orange: 'o', violet: 'v', lime: 'l', emerald: 'e', red: 'r' }
  };
  vm.runInNewContext(`${helpers}\n${humanize}\n${block}`, context);
  const dataset = id => (charts[id] ? { labels: [...charts[id].data.labels], data: [...charts[id].data.datasets[0].data] } : null);
  const tooltip = id => charts[id].options.plugins.tooltip.callbacks.label({ label: 'X', raw: 7 });
  return { nodes, charts, dataset, tooltip };
}

test('the 2026 outreach baseline is a YTD record with lower bounds and never fills a month', async () => {
  const july = tlMonth(2026, 7, { grid_total_kwh: tv(40894, 'energy', { unit: 'kWh' }) });
  const loaded = await loadDashboardFromTimeline(timelineOf([outreachYtd(), july], '2026-07'));
  const ytd = loaded.outreachFor(2026, 'all');
  assert.equal(ytd.published, true);
  assert.equal(ytd.programsDelivered, 20);
  assert.equal(ytd.participantsServed, 2009);
  assert.equal(ytd.partnerOrganizations, 25);
  assert.equal(ytd.saplingsPlanted, 400);
  assert.equal(ytd.expertsInvolved, 34);
  assert.equal(ytd.volunteersEngaged, 364);
  assert.equal(ytd.volunteerHours, 1649);
  // "+" in the source: every summary figure stays a lower bound.
  for (const field of ['programsDelivered', 'participantsServed', 'partnerOrganizations', 'saplingsPlanted', 'expertsInvolved', 'volunteersEngaged', 'volunteerHours']) {
    assert.equal(ytd.qualifiers[field], 'AT_LEAST', field);
  }
  assert.equal(ytd.coverageLabel, OUTREACH_LABEL);
  assert.equal('gender' in ytd, false);  // outreach has no gender breakdown
  assert.equal(ytd.audienceUnit, 'count');
  assert.equal(ytd.thematicUnit, 'programmes');
  // The YTD figure is not a monthly measurement: July (and every other month) has no outreach.
  for (const month of ['0', '6', '7']) assert.equal(loaded.outreachFor(2026, month).published, false, `month ${month}`);
  // Overview KPI: the card reads the backend display item, with its YTD coverage label.
  assert.equal(loaded.data['2026'].display.all.total_participants.value, 2009);
  assert.equal(loaded.data['2026'].display.all.total_participants.display_label, OUTREACH_LABEL);
  const app = read('app.js');
  assert.match(app, /'Outreach impact': \{ code: 'total_participants' \}/);
  assert.match(app, /outreach\.qualifiers\?\.participantsServed === 'AT_LEAST' \? '\+ people' : 'people'/);
  // Data Explorer rows keep the lower-bound qualifier and the stated coverage.
  const row = JSON.parse(JSON.stringify(loaded.explorerRows.find(entry => entry[4] === 'total_participants')));
  assert.deepEqual([row[2], row[5], row[6], row[8], row[10]], ['YTD', 2009, 'people', '2026 YTD · baseline 2026-01-01 – 2026-08-17', 'at least']);
  assert.doesNotMatch(row[8], /not stated/);  // the audit view keeps the stated coverage dates
});

test('a later published month raises the YTD figures the page shows, with no code change', async () => {
  const extended = '2026 YTD';
  const more = outreachYtd({
    total_participants: { ...tv(2309, 'outreach', { unit: 'people', granularity: 'YTD', qualifier: 'AT_LEAST' }), coverage_label: extended },
    total_programs: { ...tv(22, 'outreach', { unit: 'programmes', granularity: 'YTD', qualifier: 'AT_LEAST' }), coverage_label: extended }
  });
  const loaded = await loadDashboardFromTimeline(timelineOf([more], '2026-YTD'));
  const ytd = loaded.outreachFor(2026, 'all');
  assert.equal(ytd.participantsServed, 2309);
  assert.equal(ytd.programsDelivered, 22);
  assert.equal(ytd.qualifiers.participantsServed, 'AT_LEAST');
  assert.equal(ytd.coverageLabel, extended);
  assert.equal(loaded.data['2026'].display.all.total_participants.value, 2309);
});

test('thematic chart: labels and values come from the API and change with it', async () => {
  const a = (await loadDashboardFromTimeline(timelineOf([outreachYtd()], '2026-YTD'))).outreachFor(2026, 'all');
  const first = renderOutreachCharts(a);
  assert.deepEqual(first.dataset('outreachThematicChart'), {
    labels: ['Biodiversity conservation', 'Campus sustainability', 'Water conservation'], data: [6, 4, 3]
  });
  assert.equal(first.tooltip('outreachThematicChart'), ' X: 7 programmes');
  // Theme counts (13) do not exceed 20 programmes here, so no note.
  assert.equal(first.nodes.outreachThematicNote.textContent, '');

  // Different API data, including a category the first fixture did not have.
  const b = (await loadDashboardFromTimeline(timelineOf([outreachYtd({
    'theme:biodiversity_conservation': tv(9, 'outreach', { unit: 'programmes' }),
    'theme:campus_sustainability': tv(1, 'outreach', { unit: 'programmes' }),
    'theme:water_conservation': tv(null, 'outreach', { unit: 'programmes' }),
    'theme:urban_forestry': tv(12, 'outreach', { unit: 'programmes' })
  })], '2026-YTD'))).outreachFor(2026, 'all');
  const second = renderOutreachCharts(b);
  assert.deepEqual(second.dataset('outreachThematicChart'), {
    labels: ['Biodiversity conservation', 'Campus sustainability', 'Urban forestry'], data: [9, 1, 12]
  });
  // 22 theme counts against 20+ programmes: the page says a programme can sit under more than one theme.
  assert.equal(second.nodes.outreachThematicNote.textContent,
    'Theme counts total 22; a programme can be counted under more than one theme (20+ programmes).');
});

test('audience chart: values come from the API and a source count is never labelled as reach', async () => {
  const a = (await loadDashboardFromTimeline(timelineOf([outreachYtd()], '2026-YTD'))).outreachFor(2026, 'all');
  const first = renderOutreachCharts(a);
  assert.deepEqual(first.dataset('outreachAudienceChart'), {
    labels: ['School students', 'College students', 'Government'], data: [3, 15, 0]  // an explicit zero is kept
  });
  assert.equal(first.nodes.outreachAudienceTitle.textContent, 'Audience Categories');
  assert.equal(first.nodes.outreachAudienceHint.textContent, '2026 YTD · Source-reported count per audience category - not participant numbers');
  assert.equal(first.nodes.outreachThematicHint.textContent, '2026 YTD · Programmes delivered per theme - hover a slice for the count');
  assert.equal(first.tooltip('outreachAudienceChart'), ' X: 7 (source count)');
  assert.doesNotMatch(first.nodes.outreachAudienceTitle.textContent + first.nodes.outreachAudienceHint.textContent, /reach|Participants/);

  // Manager programme data: people per category. Same chart, different values and wording.
  const people = value => tv(value, 'outreach', { unit: 'people' });
  const b = (await loadDashboardFromTimeline(timelineOf([outreachYtd({
    'audience:school_students': people(120), 'audience:college_students': people(480),
    'audience:government': tv(null, 'outreach', { unit: 'people' }), 'audience:alumni': people(35)
  })], '2026-YTD'))).outreachFor(2026, 'all');
  const second = renderOutreachCharts(b);
  assert.deepEqual(second.dataset('outreachAudienceChart'), { labels: ['School students', 'College students', 'Alumni'], data: [120, 480, 35] });
  assert.equal(second.nodes.outreachAudienceTitle.textContent, 'Participants by Category');
  assert.equal(second.tooltip('outreachAudienceChart'), ' X: 7 reach');
});

test('Outreach has no gender breakdown: no widget, no chart, no empty state, and legacy data is ignored', async () => {
  const html = read('index.html'), app = read('app.js'), loader = read('public-data-loader.js');
  // Nothing about gender is left in the active page, its code or its data adapter.
  for (const [name, source] of [['index.html', html], ['app.js', app], ['public-data-loader.js', loader], ['public-api.js', read('public-api.js')]]) {
    assert.doesNotMatch(source, /gender|\bMale\b|\bFemale\b|not disclosed|other_not_disclosed/i, name);
  }
  assert.doesNotMatch(html, /outreachGender|Gender Breakdown|gender-disaggregated/);
  // The two remaining charts share the row as two balanced columns (stacked on small screens by .g2).
  const row = html.slice(html.indexOf('id="outreachChartsRow"') - 30, html.indexOf('<!-- ', html.indexOf('id="outreachChartsRow"')));
  assert.match(row, /<section class="row g2" id="outreachChartsRow"/);
  assert.equal((row.match(/<div class="card">/g) || []).length, 2);
  assert.deepEqual([...row.matchAll(/<canvas id="(\w+)"/g)].map(match => match[1]), ['outreachAudienceChart', 'outreachThematicChart']);
  assert.match(read('styles.css'), /\.g2,\.g3\{grid-template-columns:1fr\}/);

  // A legacy payload that still carries gender values changes nothing on the page.
  const legacy = value => tv(value, 'outreach', { unit: 'people', granularity: 'YTD' });
  const plain = (await loadDashboardFromTimeline(timelineOf([outreachYtd()], '2026-YTD'))).outreachFor(2026, 'all');
  const withLegacy = (await loadDashboardFromTimeline(timelineOf([outreachYtd({
    'gender:male': legacy(120), 'gender:female': legacy(170), 'gender:other_not_disclosed': legacy(10)
  })], '2026-YTD'))).outreachFor(2026, 'all');
  assert.equal('gender' in plain, false);
  assert.equal('gender' in withLegacy, false);
  assert.equal(JSON.stringify(withLegacy), JSON.stringify(plain));
  const charts = renderOutreachCharts(withLegacy);
  assert.deepEqual(Object.keys(charts.charts).sort(), ['outreachAudienceChart', 'outreachThematicChart']);
  assert.deepEqual(Object.keys(charts.nodes).filter(id => /gender/i.test(id)), []);
  // The audience and thematic charts still render from the API data.
  assert.equal(charts.dataset('outreachAudienceChart').data.length > 0, true);
  assert.equal(charts.dataset('outreachThematicChart').data.length > 0, true);
});

test('the Data Explorer carries no gender row', async () => {
  const loaded = await loadDashboardFromTimeline(timelineOf([outreachYtd()], '2026-YTD'));
  assert.equal(JSON.stringify(loaded.explorerRows || []).toLowerCase().includes('gender'), false);
  // The backend no longer emits gender codes; this pins the contract the page relies on.
  const codes = Object.keys(outreachYtd().values);
  assert.deepEqual(codes.filter(code => /gender/i.test(code)), []);
  assert.ok(loaded.explorerRows.some(row => row[3] === 'outreach'));  // outreach rows are still listed
});

test('no outreach source value is hardcoded in the dashboard', () => {
  const sources = ['app.js', 'public-data-loader.js', 'public-api.js'].map(read).join('\n');
  // Summary lower bounds of the owner's source, as numbers or as "+" text.
  assert.doesNotMatch(sources, /\b(?:364|1649|2009|337|1951|11375)\b|1,649|2,009|['"`]20\+['"`]/);
  const app = read('app.js');
  const chartBlock = app.slice(app.indexOf('/* Outreach charts use only the active published aggregate. */'), app.indexOf('// Compute full-year arrays for Energy line charts'));
  // Chart datasets are built only from the loaded outreach object.
  assert.match(chartBlock, /data: audience\.map\(a => a\.reach\)/);
  assert.match(chartBlock, /labels: audience\.map\(a => humanizeCode\(a\.category\)\)/);
  assert.match(chartBlock, /data: thematic\.map\(t => t\.programs\)/);
  assert.doesNotMatch(chartBlock, /data: \[\s*\d/);  // no literal data arrays
  // Category names are produced from API codes, not a list in the page.
  assert.doesNotMatch(app, /biodiversity_conservation|campus_sustainability|school_students|college_students/);
});

// ---- Outreach is one running YTD dataset for every month of its year --------
// For a year whose outreach is a cumulative baseline plus later published
// months, the backend marks each month `year_to_date` and points it at the YTD
// record. Selecting a month never filters outreach; every other domain still
// follows the selected month.
function runningYear(participants = 2009, themeBiodiversity = 6, extra = {}) {
  const ytd = outreachYtd({
    total_participants: { ...tv(participants, 'outreach', { unit: 'people', granularity: 'YTD', qualifier: 'AT_LEAST' }), coverage_label: OUTREACH_LABEL },
    'theme:biodiversity_conservation': { ...tv(themeBiodiversity, 'outreach', { unit: 'programmes', granularity: 'YTD' }), coverage_label: OUTREACH_LABEL },
    ...extra
  });
  const context = Object.fromEntries(Object.entries(ytd.display).map(([code, item]) => [code, { ...item, domain: 'outreach', display_context: true, source_key: '2026-YTD' }]));
  const months = [1, 4, 7, 8, 9, 12].map(month => {
    const period = tlMonth(2026, month, {
      grid_total_kwh: tv(month * 1000, 'energy', { unit: 'kWh', kind: 'calculation' }),
      operational_ghg_tco2e: tv(month * 10, 'ghg', { unit: 'tCO2e', kind: 'calculation' }),
      lpg_weight_kg: tv(month * 100, 'lpg', { unit: 'kg' }),
      transport_petrol_litres: tv(month * 5, 'transport', { unit: 'L' }),
      water_consumed_kl: tv(month * 7, 'water', { unit: 'KL' }),
      // September carries its own genuine monthly outreach record.
      ...(month === 9 ? { total_participants: tv(300, 'outreach', { unit: 'people' }) } : {})
    });
    period.domains.outreach = { state: 'year_to_date', alternative_key: '2026-YTD', message: '2026 outreach is reported as one year-to-date figure, not a monthly value.' };
    period.display = { ...context, grid_total_kwh: { value: month * 1000, unit: 'kWh', domain: 'energy', display_label: `${TL_MONTHS[month - 1]} 2026`, display_context: false } };
    return period;
  });
  return timelineOf([ytd, ...months], '2026-07');
}
const SELECTIONS = { Jan: '0', Apr: '3', Jul: '6', Aug: '7', Sep: '8', Dec: '11' };

test('every 2026 month selection shows the same outreach YTD cards and charts', async () => {
  const loaded = await loadDashboardFromTimeline(runningYear());
  const ytd = loaded.outreachFor(2026, 'all');
  const reference = renderOutreachCharts(ytd);
  for (const [name, index] of Object.entries(SELECTIONS)) {
    const shown = loaded.outreachFor(2026, index);
    assert.equal(shown.published, true, `${name}: outreach must not disappear`);
    assert.deepEqual(
      [shown.programsDelivered, shown.participantsServed, shown.partnerOrganizations, shown.saplingsPlanted, shown.expertsInvolved, shown.volunteersEngaged, shown.volunteerHours],
      [20, 2009, 25, 400, 34, 364, 1649], name);
    assert.equal(shown.qualifiers.participantsServed, 'AT_LEAST', name);
    assert.equal(shown.coverageLabel, '2026 YTD', name);
    assert.doesNotMatch(shown.coverageLabel, /17 Aug|through/);
    // The month selector does not alter the thematic or audience datasets.
    const charts = renderOutreachCharts(shown);
    assert.deepEqual(charts.dataset('outreachThematicChart'), reference.dataset('outreachThematicChart'), name);
    assert.deepEqual(charts.dataset('outreachAudienceChart'), reference.dataset('outreachAudienceChart'), name);
    assert.deepEqual(Object.keys(charts.charts).sort(), ['outreachAudienceChart', 'outreachThematicChart'], name);
    assert.equal(charts.nodes.outreachAudienceTitle.textContent, 'Audience Categories');
    assert.doesNotMatch(charts.nodes.outreachAudienceHint.textContent, /reach/);
    // KPI cards (Outreach page and the Overview "Outreach impact") read the month's display item: the YTD value, labelled "2026 YTD".
    const card = loaded.data['2026'].display[+index].total_participants;
    assert.deepEqual([card.value, card.qualifier, card.display_label, card.display_context], [2009, 'AT_LEAST', '2026 YTD', true], name);
  }
  assert.deepEqual(reference.dataset('outreachThematicChart').data, [6, 4, 3]);
  // September's own genuine monthly record (300) is never shown as the outreach figure.
  assert.equal(loaded.outreachFor(2026, '8').participantsServed, 2009);
  assert.equal(loaded.data['2026'].periodMeta[8].values.total_participants.value, 300);
  // No outreach rows are fabricated for the months in the Data Explorer.
  const rows = JSON.parse(JSON.stringify(loaded.explorerRows.filter(row => row[3] === 'outreach' && row[2] === 'MONTHLY')));
  assert.deepEqual(rows.map(row => [row[1], row[5]]), [['Sep 2026', 300]]);
});

test('a later publication changes the outreach shown on every 2026 month selection', async () => {
  for (const [participants, biodiversity] of [[2309, 6], [2459, 9]]) {
    const loaded = await loadDashboardFromTimeline(runningYear(participants, biodiversity));
    for (const [name, index] of Object.entries(SELECTIONS)) {
      const shown = loaded.outreachFor(2026, index);
      assert.equal(shown.participantsServed, participants, `${name} @ ${participants}`);
      assert.equal(shown.qualifiers.participantsServed, 'AT_LEAST');
      assert.equal(loaded.data['2026'].display[+index].total_participants.value, participants, name);
      // Changing the authoritative YTD theme data changes the chart on every month selection.
      assert.equal(renderOutreachCharts(shown).dataset('outreachThematicChart').data[0], biodiversity, name);
    }
  }
});

test('only outreach is year-to-date: other domains still follow the selected month, and other years are untouched', async () => {
  const timeline = runningYear();
  const annual = tlAggregate('2025-FY', 2025, 'ANNUAL', 12, { total_participants: tv(4000, 'outreach', { granularity: 'ANNUAL', qualifier: 'AT_LEAST' }) }, '2025 Full Year');
  annual.domains = { outreach: { state: 'available' } };
  const march2025 = tlMonth(2025, 3, { grid_total_kwh: tv(111, 'energy', { unit: 'kWh' }) }, {
    domains: { outreach: { state: 'aggregate_only', alternative_key: '2025-FY', message: 'Monthly Outreach data unavailable.' } }
  });
  const jan2027 = tlMonth(2027, 1, { grid_total_kwh: tv(222, 'energy', { unit: 'kWh' }) });
  const merged = timelineOf([...Object.values(timeline.periods), annual, march2025, jan2027], '2026-07');
  const loaded = await loadDashboardFromTimeline(merged);
  const item = loaded.data['2026'];
  // Genuine monthly metrics differ between January and July.
  for (const series of ['elecKwh', 'operationalGHG', 'lpgKg', 'petrolL', 'waterKL']) {
    assert.notEqual(item[series][0], item[series][6], series);
    assert.ok(item[series][0] != null && item[series][6] != null, series);
  }
  assert.deepEqual([item.elecKwh[0], item.elecKwh[6], item.elecKwh[11]], [1000, 7000, 12000]);
  assert.equal(item.display[0].grid_total_kwh.value, 1000);
  assert.equal(item.display[6].grid_total_kwh.value, 7000);
  // 2025 keeps its own governed outreach: annual only, never in a month, never 2026's figures.
  assert.equal(loaded.outreachFor(2025, 'all').participantsServed, 4000);
  assert.equal(loaded.outreachFor(2025, '2').published, false);
  // A year with no outreach shows none - 2026's YTD does not leak into it.
  assert.equal(loaded.outreachFor(2027, '0').published, false);
  assert.equal(loaded.outreachFor(2027, 'all').published, false);
  // The redirect is taken from the backend's domain state, never from a year written in the page.
  const loader = read('public-data-loader.js');
  assert.match(loader, /period\.domains\?\.outreach\?\.state === 'year_to_date' && period\.domains\.outreach\.alternative_key/);
  assert.doesNotMatch(loader + read('app.js'), /=== ?2026\b|['"]2026-YTD['"]/);
});

// ---- Water: a newly imported month is appended to the charts from API data ---
// Total water consumed is the backend's own calculation (TWAD + borewell +
// private). The page plots the monthly series it is given; no monthly figure
// is written into the browser code.
function waterTimeline(rows) {
  // rows: [month, twad, borewell, private, consumed]
  return timelineOf(rows.map(([month, twad, borewell, priv, consumed]) => tlMonth(2026, month, {
    water_twad_kl: tv(twad, 'water', { unit: 'KL' }), water_borewell_kl: tv(borewell, 'water', { unit: 'KL' }),
    water_private_kl: tv(priv, 'water', { unit: 'KL' }),
    water_consumed_kl: tv(consumed, 'water', { unit: 'KL', kind: 'calculation' })
  })), `2026-${String(rows[rows.length - 1][0]).padStart(2, '0')}`);
}
/* Runs the real Water chart block of drawCharts() for a year dataset and selection. */
function renderWaterCharts(d, month) {
  const app = read('app.js');
  const fn = name => app.match(new RegExp(`function ${name}\\([\\s\\S]*?\\n\\}`))[0];
  const line = name => app.match(new RegExp(`function ${name}\\([^\\n]*`))[0];
  const constant = name => app.match(new RegExp(`const ${name} = [\\s\\S]*?\\n[\\]}];`))[0];
  const block = app.slice(app.indexOf('  const waterMonths = monthsWithData(d.waterKL);\n  const waterLabels'), app.indexOf('  /* Outreach charts use only the active published aggregate. */'));
  const nodes = {}, charts = {}, notes = {};
  const context = {
    d, month, year: 2026, months: TL_MONTHS, n: Number, Array,
    colors: { cyan: 'c', teal: 't', gold: 'g' },
    document: { getElementById: id => (nodes[id] ||= { style: {}, textContent: '' }) },
    mk: (id, config) => { charts[id] = config; },
    chartNote: () => {}, setChartNote: (id, text) => { notes[id] = text; },
    chartOptions: () => ({ plugins: {} }), periodLabel: () => 'selected period'
  };
  const source = [line('monthsWithData'), line('sum'), fn('valFor'), fn('periodComposition'), fn('compositionNote'), fn('contextComposition'), constant('WATER_SOURCE_PARTS'), block].join('\n');
  vm.runInNewContext(source, context);
  const series = id => ({ labels: [...charts[id].data.labels], data: [...charts[id].data.datasets[0].data] });
  return { charts, nodes, notes, series };
}
const JAN_TO_JUN = [[1, 3157, 17050, 8, 20215], [2, 3410, 18876, 46, 22332], [3, 3558, 17050, 0, 20608], [4, 3568, 16500, 108, 20176], [5, 3136, 17050, 0, 20186], [6, 2888, 16500, 0, 19388]];

test('a new month of water data is appended to every Water chart straight from the API', async () => {
  const before = (await loadDashboardFromTimeline(waterTimeline(JAN_TO_JUN))).data['2026'];
  const six = renderWaterCharts(before, '5');
  assert.deepEqual(six.series('waterTrendChartCanvas').labels, ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']);
  assert.equal(before.waterKL[6], null);  // no July yet: missing, never zero

  // The backend now publishes July. Nothing in the page changes.
  const after = (await loadDashboardFromTimeline(waterTimeline([...JAN_TO_JUN, [7, 3293, 17050, 124.27, 20467.27]]))).data['2026'];
  assert.deepEqual([after.waterTWAD[6], after.waterBorewell[6], after.waterProcured[6], after.waterKL[6]], [3293, 17050, 124.27, 20467.27]);
  const seven = renderWaterCharts(after, '6');
  const labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul'];
  assert.deepEqual(seven.series('waterTrendChartCanvas'), { labels, data: [20215, 22332, 20608, 20176, 20186, 19388, 20467.27] });
  assert.deepEqual(seven.series('waterTWADTrendCanvas'), { labels, data: [3157, 3410, 3558, 3568, 3136, 2888, 3293] });
  assert.deepEqual(seven.series('waterBorewellTrendCanvas'), { labels, data: [17050, 18876, 17050, 16500, 17050, 16500, 17050] });
  // 124.27 is kept exactly - not rounded to 124 - and published zeros stay zeros.
  assert.deepEqual(seven.series('waterProcuredTrendCanvas'), { labels, data: [8, 46, 0, 108, 0, 0, 124.27] });
  // The source breakdown for the selected month is that month's own three values.
  assert.deepEqual(seven.series('waterSourceChartCanvas'), { labels: ['TWAD supply', 'Borewell', 'Private water supply'], data: [3293, 17050, 124.27] });
  // Jan-Jun points are exactly what they were before July was added.
  assert.deepEqual(seven.series('waterTrendChartCanvas').data.slice(0, 6), six.series('waterTrendChartCanvas').data);

  // Different API values produce different chart points (no baked-in July figure).
  const other = (await loadDashboardFromTimeline(waterTimeline([...JAN_TO_JUN, [7, 1111, 2222, 33.5, 3366.5]]))).data['2026'];
  const changed = renderWaterCharts(other, '6');
  assert.equal(changed.series('waterTWADTrendCanvas').data[6], 1111);
  assert.equal(changed.series('waterProcuredTrendCanvas').data[6], 33.5);
  assert.equal(changed.series('waterTrendChartCanvas').data[6], 3366.5);
  assert.deepEqual(changed.series('waterSourceChartCanvas').data, [1111, 2222, 33.5]);
});

test('the browser never totals water sources or carries a monthly water figure', () => {
  const app = read('app.js');
  const loader = read('public-data-loader.js');
  // Total consumption is read from the backend's water_consumed_kl, never summed from the sources.
  assert.match(loader, /waterKL: 'water_consumed_kl', waterTWAD: 'water_twad_kl', waterBorewell: 'water_borewell_kl',/);
  assert.match(loader, /waterProcured: 'water_private_kl'/);
  assert.doesNotMatch(app + loader, /waterTWAD\[[^\]]*\]\s*\+\s*d?\.?waterBorewell|water_twad_kl[^\n]*\+[^\n]*water_borewell_kl/);
  assert.match(app, /data: wsl\(d\.waterKL\)/);
  assert.match(app, /data: wsl\(d\.waterTWAD\)/);
  assert.match(app, /data: wsl\(d\.waterBorewell\)/);
  assert.match(app, /data: wsl\(d\.waterProcured\)/);
  // No owner-supplied water figure is written into active front-end code.
  for (const source of [app, loader, read('public-api.js'), read('index.html')]) {
    assert.doesNotMatch(source, /\b(?:3293|17050|20467|143372|122905)\b|124\.27/);
  }
});

// ---- Energy page: exactly four primary KPI cards for every selection --------
// One definition (ENERGY_PRIMARY_KPIS) drives a month, YTD and Full Year alike.
// The figures below are test fixtures fed through the real loader and the real
// card code; none of them exists in the dashboard source.
const ENERGY_TITLES = ['Total electricity consumption', 'Total grid electricity consumption', 'Solar PV electricity generation', 'Procured green energy'];
const ENERGY_CODES = ['total_electricity_consumption_kwh', 'grid_total_kwh', 'renewable_on_campus_kwh', 'renewable_procured_kwh'];
/* An energy period: [total, grid, on-campus, procured] plus optional extra codes. */
function energyValues([total, grid, onCampus, procured], extra = {}) {
  const kwh = (value, kind = 'metric') => tv(value, 'energy', { unit: 'kWh', kind });
  return {
    total_electricity_consumption_kwh: kwh(total, 'calculation'), grid_total_kwh: kwh(grid, 'calculation'),
    renewable_on_campus_kwh: kwh(onCampus), renewable_procured_kwh: kwh(procured),
    ...Object.fromEntries(Object.entries(extra).map(([code, [value, unit]]) => [code, tv(value, 'energy', { unit, kind: 'calculation' })]))
  };
}
/* The backend's display items for a period: every available value, labelled. */
function withDisplay(period) {
  period.display = Object.fromEntries(Object.entries(period.values).filter(([, item]) => item.value != null)
    .map(([code, item]) => [code, { value: item.value, unit: item.unit, display_label: period.label, display_context: false }]));
  return period;
}
const ENERGY_EXTRA = {
  renewable_electricity_kwh: [304929, 'kWh'], renewable_share_pct: [88.17, '%'],
  estimated_avoided_grid_emissions_tco2e: [221.68, 'tCO2e'], solar_water_heater_kwh: [99999, 'kWh'],
  grid_ht_kwh: [39366, 'kWh'], grid_commercial_kwh: [1261, 'kWh'], grid_temporary_kwh: [267, 'kWh']
};
const ENERGY_PERIODS = {
  '2026-01': [303994, 46442, 15950, 241602], '2026-04': [412864, 48748, 19556, 344560],
  '2026-07': [345823, 40894, 18595, 286334], '2026-YTD': [2474176, 308059, 128212, 2037905],
  '2025-FY': [4241689, 1037406, 197809, 3006474]
};
function energyTimeline(periods = ENERGY_PERIODS, extra = ENERGY_EXTRA) {
  const built = Object.entries(periods).map(([key, numbers]) => {
    const [year, part] = key.split('-');
    const values = energyValues(numbers, extra);
    if (part === 'YTD') return withDisplay(tlAggregate(key, +year, 'YTD', 7, values, `${year} YTD · Jan–Jul`));
    if (part === 'FY') return withDisplay(tlAggregate(key, +year, 'ANNUAL', 12, values, `${year} Full Year`));
    return withDisplay(tlMonth(+year, +part, values));
  });
  return timelineOf(built, '2026-07');
}
/* Renders #energyKpis with the real definition, card lookup and kpi() override. */
function energyCards(data, year, month) {
  const app = read('app.js');
  const fn = name => app.match(new RegExp(`function ${name}\\([\\s\\S]*?\\n\\}`))[0];
  const source = [
    'const kgOrTonnes = kg => ({ value: kg });',
    app.match(/const CARD_DISPLAY = \{[\s\S]*?\n\};/)[0],
    app.match(/const ENERGY_PRIMARY_KPIS = \[[\s\S]*?\n\];\nENERGY_PRIMARY_KPIS\.forEach[^\n]*/)[0],
    fn('missingKpiHtml'), fn('energyPrimaryKpisHtml'), fn('valFor'), fn('displayFor'), fn('sourceBadge'),
    'let kpi;', app.match(/\nkpi = function \([\s\S]*?\n\};/)[0],
    'globalThis.html = energyPrimaryKpisHtml(d, month); globalThis.definition = ENERGY_PRIMARY_KPIS; globalThis.cardDisplay = CARD_DISPLAY;'
  ].join('\n');
  const d = data[String(year)];
  const context = {
    d, month, n: Number, Array, Object, String,
    colors: { cyan: 'c', emerald: 'e' }, ic: name => `<i>${name}</i>`,
    currentPeriod: () => ({ year, month, d }), previousValue: () => null,
    partialNoteHtml: () => '', dgOriginNoteHtml: () => '', STATIC_CARDS: new Set(), STATIC_LABEL: '',
    renderNumericKpi: (title, value, unit) => `<article class="kpi"><div class="label">${title}</div><div class="value"><span class="counter-val" data-val="${value}">0</span><small>${unit}</small></div><div class="trend"></div></article>`
  };
  vm.runInNewContext(source, context);
  const cards = context.html.split('</article>').filter(Boolean).map(card => ({
    title: card.match(/<div class="label">([^<]*)<\/div>/)[1],
    value: /data-val="([^"]*)"/.test(card) ? Number(card.match(/data-val="([^"]*)"/)[1]) : null,
    unit: card.match(/<small>([^<]*)<\/small>/)[1],
    source: (card.match(/<div class="kpi-source[^"]*">([^<]*)<\/div>/) || [])[1] || null
  }));
  return { cards, html: context.html, definition: context.definition, cardDisplay: context.cardDisplay };
}
const energySelections = [['2026', '0', '2026-01'], ['2026', '3', '2026-04'], ['2026', '6', '2026-07'], ['2026', 'all', '2026-YTD'], ['2025', 'all', '2025-FY']];
const values = result => result.cards.map(card => card.value);
const titles = result => result.cards.map(card => card.title);

test('the Energy page renders exactly four primary KPI cards with the exact titles, in order', async () => {
  const { data } = await loadDashboardFromTimeline(energyTimeline());
  const result = energyCards(data, 2026, '6');
  assert.equal(result.cards.length, 4);
  assert.deepEqual(titles(result), ENERGY_TITLES);
  assert.deepEqual(result.cards.map(card => card.unit), ['kWh', 'kWh', 'kWh', 'kWh']);
});

test('each Energy primary KPI is bound to its one canonical backend value', async () => {
  const { data } = await loadDashboardFromTimeline(energyTimeline());
  const { definition, cardDisplay } = energyCards(data, 2026, '6');
  assert.deepEqual([...definition].map(card => card.title), ENERGY_TITLES);
  assert.deepEqual([...definition].map(card => card.code), ENERGY_CODES);
  assert.deepEqual([...definition].map(card => card.series), ['totalElectricityKwh', 'elecKwh', 'reOnCampusKwh', 'reProcuredKwh']);
  ENERGY_TITLES.forEach((title, index) => assert.equal(cardDisplay[title].code, ENERGY_CODES[index]));
  const loader = read('public-data-loader.js');
  for (const pair of ["totalElectricityKwh: 'total_electricity_consumption_kwh'", "elecKwh: 'grid_total_kwh'", "reOnCampusKwh: 'renewable_on_campus_kwh'", "reProcuredKwh: 'renewable_procured_kwh'"]) {
    assert.ok(loader.includes(pair), pair);
  }
});

test('January, April, July, YTD and Full Year all show the same four KPI identities', async () => {
  const { data } = await loadDashboardFromTimeline(energyTimeline());
  for (const [year, month, key] of energySelections) {
    const result = energyCards(data, +year, month);
    assert.deepEqual(titles(result), ENERGY_TITLES, key);
    // Only the values change with the period: each is that period's own backend value.
    assert.deepEqual(values(result), ENERGY_PERIODS[key], key);
  }
});

test('July, YTD and Full Year Energy KPI values are the backend values for that selection', async () => {
  const { data } = await loadDashboardFromTimeline(energyTimeline());
  assert.deepEqual(values(energyCards(data, 2026, '6')), [345823, 40894, 18595, 286334]);
  assert.deepEqual(values(energyCards(data, 2026, 'all')), [2474176, 308059, 128212, 2037905]);
  assert.deepEqual(values(energyCards(data, 2025, 'all')), [4241689, 1037406, 197809, 3006474]);
  assert.equal(energyCards(data, 2026, 'all').cards[0].source, '2026 YTD · Jan–Jul');
  assert.equal(energyCards(data, 2025, 'all').cards[0].source, '2025 Full Year');
  // Different backend values give different cards: nothing is baked into the page.
  const other = (await loadDashboardFromTimeline(energyTimeline({ '2026-07': [9000, 4000, 3000, 2000] }))).data;
  assert.deepEqual(values(energyCards(other, 2026, '6')), [9000, 4000, 3000, 2000]);
  for (const file of ['app.js', 'public-data-loader.js', 'public-api.js', 'index.html']) {
    assert.doesNotMatch(read(file), /\b(?:345823|40894|18595|286334|2474176|308059|128212|2037905|4241689|1037406|197809|3006474)\b/, file);
  }
});

test('solar water heater, renewable share and avoided emissions never become an Energy primary KPI', async () => {
  // The thermal figure is deliberately huge: if it leaked into a card it would show.
  const withThermal = (await loadDashboardFromTimeline(energyTimeline())).data;
  const without = (await loadDashboardFromTimeline(energyTimeline(ENERGY_PERIODS, {}))).data;
  for (const [year, month, key] of energySelections) {
    const result = energyCards(withThermal, +year, month);
    assert.deepEqual(result.cards, energyCards(without, +year, month).cards, key);
    assert.doesNotMatch(result.html, /water heater|Renewable share|avoided|Renewable electricity|connection/i, key);
  }
  const app = read('app.js');
  const definition = app.match(/const ENERGY_PRIMARY_KPIS = \[[\s\S]*?\n\];/)[0];
  assert.doesNotMatch(definition, /solar_water_heater|solarWaterHeater|renewable_share|estimated_avoided|renewable_electricity_kwh|renewable_total/);
  // The Energy KPI row is that one definition and nothing else, for every selection.
  assert.match(app, /energyKpisEl\.innerHTML = energyPrimaryKpisHtml\(d, month\);/);
  assert.equal(app.match(/energyKpisEl\.innerHTML/g).length, 1);
  assert.doesNotMatch(app.match(/function energyPrimaryKpisHtml\([\s\S]*?\n\}/)[0], /month === 'all'|[^=!]==? *'all'|\+ *valFor|reduce\(/);
});

test('an Energy primary KPI the backend has no value for stays in place and is never zero', async () => {
  const { data } = await loadDashboardFromTimeline(energyTimeline({ '2026-07': [null, 40894, null, 286334] }));
  const result = energyCards(data, 2026, '6');
  assert.deepEqual(titles(result), ENERGY_TITLES);
  assert.deepEqual(values(result), [null, 40894, null, 286334]);
  assert.match(result.html, /No value for this period/);
  assert.doesNotMatch(result.html, /data-val="(?:0|null|undefined|NaN)"/);
});

test('Energy graphs, the renewable progress widget and other pages are untouched by the KPI row', () => {
  const app = read('app.js');
  const html = read('index.html');
  for (const chart of ['energyTotalLineChart', 'energyGridLineChart', 'energySrcBreakdownChart']) assert.ok(app.includes(chart), chart);
  assert.match(app, /const total26 = cleanZero\(d26\.totalElectricityKwh\)/);
  assert.match(app, /const reProgressPct = reShare;/);
  assert.match(html, /<section class="kpi-grid" id="energyKpis"><\/section>/);
  assert.match(html, /<div id="energyProgressWidget"><\/div>/);
  // Other pages keep their own cards for the same governed metrics.
  assert.match(app, /overviewKpi\('Renewable energy used', re, 'kWh'/);
  assert.match(app, /ghgKpi\('Reduction through renewables', avoid,/);
  assert.match(app, /title: 'Total water consumption', code: 'water_consumed_kl'/);
  assert.match(app, /title: 'Consumption per capita', code: 'water_per_capita_l', series: 'waterPerCapitaL', unit: 'L\/person'/);
  // The Carbon Story still finds the avoided-emissions figure (GHG page card).
  assert.match(read('walkthrough.js'), /alias\('Emission avoided', 'Reduction through renewables'\)/);
});

// ---- Waste page: three fixed KPI cards + year-aggregate charts ---------------
// Waste is one running figure per year. The backend resolves it and offers it
// as the display items of EVERY selection inside that year; the page shows it.
// The figures below are test fixtures fed through the real loader and the real
// card / chart code; none of them exists in the dashboard source.
const WASTE_TITLES = ['Total waste generated', 'Total waste diverted from landfill', 'Waste contribution per person'];
const WASTE_2025 = {
  wet: 6577, dry: 48762.55, total: 55339.55, perPerson: 7.915827, label: '2025 Full Year',
  materials: {
    COLOUR_PAPER: 4982.3, WHITE_PAPER: 8299.75, IRON: 6356.45, LITE_WEIGHT: 2708.55, CARDBOARD: 5143.95,
    COCONUT_SHELL: 1604.7, PP_CARDBOARDS: 6073.9, MIXED_PLASTICS: 1951.45, STAINLESS_STEEL: 516.25, PVC_PIPE: 953.23,
    BLACK_PLASTIC_PP: 1931.22, PET: 812, ALUMINIUM: 256.4, E_WASTE: 1400, LDPE: 409.3, NEWS_PAPER: 2048.2, TYRE: 322.9,
    UNCLASSIFIED: 2992
  }
};
const WASTE_2026 = {
  wet: 3000, dry: 76590.6, total: 79590.6, perPerson: 11.384723, label: '2026 YTD',
  materials: {
    COLOUR_PAPER: 21174.1, WHITE_PAPER: 5178.07, IRON: 7726.75, LITE_WEIGHT: 20226.25, CARDBOARD: 1669.6,
    PP_CARDBOARDS: 7759.33, MIXED_PLASTICS: 3539.8, BLACK_PLASTIC_PP: 5033.5, PET: 1116.5, ALUMINIUM: 838.4,
    HDPE: 806.9, LDPE: 784.1, NEWS_PAPER: 719.1, TYRE: 18.2
  }
};
/* The waste display items the backend attaches to a selection of that year. */
function wasteDisplayItems(year, context) {
  const item = (value, unit) => ({ value, unit, domain: 'waste', display_label: year.label, display_context: context });
  const items = {
    wet_waste_generated_kg: item(year.wet, 'kg'), dry_waste_generated_kg: item(year.dry, 'kg'),
    total_waste_generated_kg: item(year.total, 'kg'), waste_diverted_from_landfill_kg: item(year.diverted ?? year.dry, 'kg'),
    waste_per_capita_kg: item(year.perPerson, 'kg/person')
  };
  Object.entries(year.materials).forEach(([code, value]) => { items[`material:${code}`] = item(value, 'kg'); });
  Object.keys(items).forEach(code => { if (items[code].value == null) delete items[code]; });
  // The legacy static reference still travels with every selection; the Waste page ignores it.
  items.landfill_diversion_pct = { value: year.staticPct ?? 88.1, unit: '%', domain: 'waste', source_granularity: 'STATIC', display_label: 'Institutional Reference', display_context: true };
  return items;
}
function wasteTimeline(y2025 = WASTE_2025, y2026 = WASTE_2026) {
  const month = (year, number, waste) => {
    const period = tlMonth(year, number, { grid_total_kwh: tv(100 + number, 'energy', { unit: 'kWh', kind: 'calculation' }) });
    period.display = wasteDisplayItems(waste, true);  // waste is never in a month's own values
    period.domains.waste = { state: 'year_aggregate', alternative_key: `${year}-${year === 2025 ? 'FY' : 'YTD'}`, label: waste.label };
    return period;
  };
  const aggregate = (key, year, granularity, end, waste) => {
    const period = tlAggregate(key, year, granularity, end, {}, waste.label);
    period.display = wasteDisplayItems(waste, false);
    return period;
  };
  const timeline = timelineOf([
    aggregate('2025-FY', 2025, 'ANNUAL', 12, y2025), month(2025, 1, y2025), month(2025, 6, y2025), month(2025, 12, y2025),
    aggregate('2026-YTD', 2026, 'YTD', 7, y2026), month(2026, 1, y2026), month(2026, 4, y2026), month(2026, 7, y2026)
  ], '2026-07');
  timeline.labels = {
    'material:PET': 'PET', 'material:COLOUR_PAPER': 'Colour Paper', 'material:MIXED_PLASTICS': 'Plastic (Mixed Plastics)',
    'material:E_WASTE': 'E-WASTE', 'material:LITE_WEIGHT': 'Lite Weight'
  };
  return timeline;
}
/* Renders #wasteKpis with the real definition and renderer. */
function wasteCards(data, year, month) {
  const app = read('app.js');
  const fn = name => app.match(new RegExp(`function ${name}\\([\\s\\S]*?\\n\\}`))[0];
  const source = [
    app.match(/const WASTE_PRIMARY_KPIS = \[[\s\S]*?\n\];/)[0],
    fn('missingKpiHtml'), fn('wastePrimaryKpisHtml'), fn('displayFor'), fn('sourceBadge'),
    'globalThis.html = wastePrimaryKpisHtml(); globalThis.definition = WASTE_PRIMARY_KPIS;'
  ].join('\n');
  const d = data[String(year)];
  const context = {
    colors: { orange: 'o', emerald: 'e', teal: 't' }, ic: name => `<i>${name}</i>`,
    currentPeriod: () => ({ year, month, d }),
    renderNumericKpi: (title, value, unit, accent, icon, prev, lowerGood, dec) => `<article class="kpi"><div class="label">${title}</div><div class="value"><span class="counter-val" data-val="${value}" data-dec="${dec}">0</span><small>${unit}</small></div><div class="trend"></div></article>`
  };
  vm.runInNewContext(source, context);
  const cards = context.html.split('</article>').filter(Boolean).map(card => {
    const value = /data-val="([^"]*)"/.test(card) ? Number(card.match(/data-val="([^"]*)"/)[1]) : null;
    return {
      title: card.match(/<div class="label">([^<]*)<\/div>/)[1],
      shown: value == null ? '—' : value.toFixed(Number(card.match(/data-dec="([^"]*)"/)[1])),
      unit: card.match(/<small>([^<]*)<\/small>/)[1],
      source: (card.match(/<div class="kpi-source[^"]*">([^<]*)<\/div>/) || [])[1] || null
    };
  });
  return { cards, html: context.html, definition: [...context.definition] };
}
/* Runs the real Waste chart block of drawCharts() for a year dataset and selection. */
function renderWasteCharts(data, year, month) {
  const app = read('app.js');
  const block = app.slice(
    app.indexOf('  /* Waste is a year-aggregate domain: the charts show the year\'s current'),
    app.indexOf('\n', app.indexOf("  chartNote('wasteMaterialChartCanvas'"))
  );
  const nodes = {}, charts = {}, notes = {};
  const context = {
    d: data[String(year)], month, Math, Number,
    colors: { blue: 'b', gold: 'g', teal: 't', emerald: 'e', orange: 'o', grid: 'x' },
    document: { getElementById: id => (nodes[id] ||= { style: {}, textContent: '' }) },
    mk: (id, config) => { charts[id] = config; },
    chartNote: (id, arrays, text) => { notes[id] = arrays.some(values => values.some(value => value != null)) ? '' : text; }
  };
  vm.runInNewContext(block, context);
  const material = charts.wasteMaterialChartCanvas;
  return {
    charts, nodes, notes,
    pie: [...charts.wastePieChartCanvas.data.datasets[0].data],
    materials: material.data.labels.map((name, index) => [name, material.data.datasets[0].data[index]])
  };
}
const wasteSelections2025 = ['all', '0', '5', '11'], wasteSelections2026 = ['all', '0', '3', '6'];
const sumOf = rows => Math.round(rows.reduce((total, [, value]) => total + value, 0) * 100) / 100;

test('the Waste page renders exactly three primary KPI cards, the same for every selection', async () => {
  const { data } = await loadDashboardFromTimeline(wasteTimeline());
  for (const [year, selections] of [[2025, wasteSelections2025], [2026, wasteSelections2026]]) {
    for (const month of selections) {
      const { cards } = wasteCards(data, year, month);
      assert.deepEqual(cards.map(card => card.title), WASTE_TITLES, `${year}/${month}`);
      assert.deepEqual(cards.map(card => card.unit), ['tons', 'tons', 'kg/person'], `${year}/${month}`);
    }
  }
  const { definition } = wasteCards(data, 2026, '6');
  assert.deepEqual(definition.map(card => card.code), ['total_waste_generated_kg', 'waste_diverted_from_landfill_kg', 'waste_per_capita_kg']);
  // Wet and dry are no longer primary cards; they stay in the composition chart.
  const app = read('app.js');
  assert.doesNotMatch(app, /kpi\('(?:Wet|Dry) waste generated'/);
  assert.match(app, /wasteKpisEl\.innerHTML = wastePrimaryKpisHtml\(\);/);
  assert.equal(app.match(/wasteKpisEl\.innerHTML/g).length, 1);
});

test('Waste KPI cards show the year aggregate in tons and kg/person, one decimal', async () => {
  const { data } = await loadDashboardFromTimeline(wasteTimeline());
  const shown = (year, month) => wasteCards(data, year, month).cards.map(card => `${card.shown} ${card.unit}`);
  assert.deepEqual(shown(2025, 'all'), ['55.3 tons', '48.8 tons', '7.9 kg/person']);
  assert.deepEqual(shown(2026, 'all'), ['79.6 tons', '76.6 tons', '11.4 kg/person']);
  // A month does not filter waste: every selection of a year shows that year's aggregate.
  for (const month of wasteSelections2025) assert.deepEqual(shown(2025, month), shown(2025, 'all'), `2025/${month}`);
  for (const month of wasteSelections2026) assert.deepEqual(shown(2026, month), shown(2026, 'all'), `2026/${month}`);
  assert.equal(wasteCards(data, 2025, '5').cards[0].source, '2025 Full Year');
  assert.equal(wasteCards(data, 2026, '6').cards[0].source, '2026 YTD');
  // Different backend values give different cards.
  const other = (await loadDashboardFromTimeline(wasteTimeline(WASTE_2025, { ...WASTE_2026, total: 90000, diverted: 80000, perPerson: 12.345 }))).data;
  assert.deepEqual(wasteCards(other, 2026, '3').cards.map(card => card.shown), ['90.0', '80.0', '12.3']);
});

test('a Waste KPI the backend has no value for keeps its place and is never zero', async () => {
  const { data } = await loadDashboardFromTimeline(wasteTimeline(WASTE_2025, { ...WASTE_2026, perPerson: null }));
  const { cards, html } = wasteCards(data, 2026, '6');
  assert.deepEqual(cards.map(card => card.title), WASTE_TITLES);
  assert.deepEqual(cards.map(card => card.shown), ['79.6', '76.6', '—']);
  assert.doesNotMatch(html, /data-val="(?:0|null|undefined|NaN)"/);
});

test('diverted waste is the backend value and never the legacy static percentage', async () => {
  // The static reference changes; the three cards do not.
  const base = (await loadDashboardFromTimeline(wasteTimeline())).data;
  const moved = (await loadDashboardFromTimeline(wasteTimeline({ ...WASTE_2025, staticPct: 10 }, { ...WASTE_2026, staticPct: 10 }))).data;
  for (const [year, month] of [[2025, 'all'], [2026, '6']]) {
    assert.deepEqual(wasteCards(moved, year, month).cards, wasteCards(base, year, month).cards);
  }
  const app = read('app.js');
  const definition = app.match(/const WASTE_PRIMARY_KPIS = \[[\s\S]*?\n\];/)[0] + app.match(/function wastePrimaryKpisHtml\([\s\S]*?\n\}/)[0];
  assert.doesNotMatch(definition, /landfill_diversion|landfillDiversionPct|88/);
  for (const file of ['app.js', 'public-data-loader.js', 'public-api.js', 'index.html']) assert.doesNotMatch(read(file), /88\.1/, file);
  // No total x percentage, wet + dry or per-person arithmetic in the browser.
  assert.doesNotMatch(app + read('public-data-loader.js'), /wet\s*\+\s*[\w.]*dry|dry\s*\/\s*[\w.]*total|\*\s*[\w.]*landfill/i);
});

test('the Wet vs Dry chart shows the year aggregate for every selection of that year', async () => {
  const { data } = await loadDashboardFromTimeline(wasteTimeline());
  for (const month of wasteSelections2025) assert.deepEqual(renderWasteCharts(data, 2025, month).pie, [6577, 48762.55], `2025/${month}`);
  for (const month of wasteSelections2026) assert.deepEqual(renderWasteCharts(data, 2026, month).pie, [3000, 76590.6], `2026/${month}`);
  const july = renderWasteCharts(data, 2026, '6');
  assert.deepEqual([...july.charts.wastePieChartCanvas.data.labels], ['Wet waste', 'Dry waste']);
  assert.equal(july.nodes.wasteContext.textContent, ' — 2026 YTD');
  assert.equal(renderWasteCharts(data, 2025, '0').nodes.wasteContext.textContent, ' — 2025 Full Year');
  assert.match(read('index.html'), /Dry waste = diverted from landfill<span id="wasteContext"><\/span>/);
});

test('the Waste Material Breakdown is a horizontal bar chart of the reported materials, largest first', async () => {
  const { data } = await loadDashboardFromTimeline(wasteTimeline());
  const y2025 = renderWasteCharts(data, 2025, 'all'), y2026 = renderWasteCharts(data, 2026, '6');
  assert.equal(y2025.materials.length, 18);
  assert.equal(y2026.materials.length, 14);
  assert.equal(sumOf(y2025.materials), 48762.55);
  assert.equal(sumOf(y2026.materials), 76590.6);
  for (const chart of [y2025, y2026]) {
    const amounts = chart.materials.map(([, value]) => value);
    assert.deepEqual(amounts, [...amounts].sort((a, b) => b - a));
    const config = chart.charts.wasteMaterialChartCanvas;
    assert.equal(config.type, 'bar');
    assert.equal(config.options.indexAxis, 'y');
    assert.equal(config.options.scales.x.title.text, 'kg');
  }
  assert.deepEqual(y2025.materials[0], ['WHITE_PAPER', 8299.75]);
  assert.deepEqual(y2026.materials.slice(0, 2), [['Colour Paper', 21174.1], ['Lite Weight', 20226.25]]);
  // Materials the 2026 source does not report are absent - never a zero bar.
  const names2026 = y2026.materials.map(([name]) => name);
  for (const absent of ['COCONUT_SHELL', 'STAINLESS_STEEL', 'PVC_PIPE', 'E-WASTE', 'UNCLASSIFIED']) assert.ok(!names2026.includes(absent), absent);
  assert.ok(names2026.includes('HDPE') && !y2025.materials.some(([name]) => name === 'HDPE'));
  // Every 2026 selection shows the same breakdown; the exact kg stays in the tooltip.
  for (const month of wasteSelections2026) assert.deepEqual(renderWasteCharts(data, 2026, month).materials, y2026.materials, month);
  const tooltip = y2026.charts.wasteMaterialChartCanvas.options.plugins.tooltip.callbacks.label({ raw: 21174.1 });
  assert.match(tooltip, /21,174\.1 kg/);
  assert.match(tooltip, /21\.17 tons/);
  assert.equal(y2026.nodes.wasteMaterialBox.style.height, `${14 * 26 + 70}px`);
});

test('Waste charts follow the API: changed values and a new material appear without a code change', async () => {
  const changed = {
    ...WASTE_2026, wet: 3500, dry: 77000, materials: { ...WASTE_2026.materials, COLOUR_PAPER: 100, GLASS_BOTTLES: 30000 }
  };
  const { data } = await loadDashboardFromTimeline(wasteTimeline(WASTE_2025, changed));
  const charts = renderWasteCharts(data, 2026, '3');
  assert.deepEqual(charts.pie, [3500, 77000]);
  assert.equal(charts.materials.length, 15);
  assert.deepEqual(charts.materials[0], ['GLASS_BOTTLES', 30000]);  // an unknown code is shown under its own code
  assert.deepEqual(charts.materials.find(([name]) => name === 'Colour Paper'), ['Colour Paper', 100]);
  // 2025 is untouched by a 2026 change.
  assert.deepEqual(renderWasteCharts(data, 2025, 'all').pie, [6577, 48762.55]);
  // A year with no waste draws nothing and says so; nothing becomes zero.
  const empty = (await loadDashboardFromTimeline(wasteTimeline(WASTE_2025, { label: '2026 YTD', materials: {} }))).data;
  const none = renderWasteCharts(empty, 2026, '6');
  assert.deepEqual(none.pie, [null, null]);
  assert.deepEqual(none.materials, []);
  assert.equal(none.notes.wastePieChartCanvas, 'No wet / dry waste data for this year.');
  assert.equal(none.notes.wasteMaterialChartCanvas, 'No material breakdown for this year.');
});

test('no operational Waste figure is written into the dashboard, and other pages are unchanged', () => {
  const app = read('app.js');
  for (const file of ['app.js', 'public-data-loader.js', 'public-api.js', 'index.html']) {
    assert.doesNotMatch(read(file), /\b(?:55339|48762|6577|79590|76590|21174|20226|7726|7759|5178|8299|6356)\b|\b55\.3\b|\b48\.8\b|\b79\.6\b|\b76\.6\b|\b11\.4\b/, file);
  }
  // The material list and order come from the data: no material name in the page code.
  assert.doesNotMatch(app, /Colour Paper|White Paper|Lite Weight|PP Cardboards|COLOUR_PAPER/);
  assert.doesNotMatch(app, /type: 'treemap'/);
  // Overview keeps its own Total waste card, resolved through the same backend display item.
  assert.match(app, /overviewKpi\('Total waste generated', wasteTot == null \? null : wasteTot \* wasteShow\.factor, wasteShow\.unit/);
  assert.match(app, /'Total waste generated': \{ code: 'total_waste_generated_kg', transform: kgOrTonnes \}/);
  // Energy and Water primary cards are untouched.
  assert.match(app, /energyKpisEl\.innerHTML = energyPrimaryKpisHtml\(d, month\);/);
  assert.match(app, /title: 'Total water consumption', code: 'water_consumed_kl', series: 'waterKL', unit: 'KL'/);
  assert.match(read('index.html'), /<section class="kpi-grid" id="wasteKpis" style="grid-template-columns: repeat\(3, 1fr\);"><\/section>/);
});

// ---- Electricity Mix + Fossil Fuel Emissions Mix: two rings, backend data ----
// Both widgets are driven through the real loader and the real app.js code.
// Every figure below is a test fixture; none exists in the dashboard source.
/* [grid, on-campus, procured] -> the backend's electricity values for a period. */
function mixEnergy([grid, onCampus, procured], extra = {}) {
  const kwh = (value, kind = 'metric') => tv(value, 'energy', { unit: 'kWh', kind });
  const renewable = onCampus == null || procured == null ? null : onCampus + procured;
  const total = grid == null || renewable == null ? null : grid + renewable;
  return {
    grid_total_kwh: kwh(grid, 'calculation'), renewable_on_campus_kwh: kwh(onCampus), renewable_procured_kwh: kwh(procured),
    renewable_electricity_kwh: kwh('renewable' in extra ? extra.renewable : renewable, 'calculation'),
    total_electricity_consumption_kwh: kwh('total' in extra ? extra.total : total, 'calculation'),
    renewable_share_pct: tv('share' in extra ? extra.share : (total ? renewable / total * 100 : null), 'energy', { unit: '%', kind: 'calculation' }),
    solar_water_heater_kwh: kwh(extra.heater ?? null)
  };
}
/* [dg, fleet, petrol, lpg] -> the backend's fuel emission results and Scope 1. */
function mixFuel([dg, fleet, petrol, lpg], scope1) {
  const t = value => tv(value, 'transport', { unit: 'tCO2e', kind: 'calculation' });
  const present = [dg, fleet, petrol, lpg].filter(value => value != null);
  return {
    dg_diesel_emissions: t(dg), transport_diesel_emissions: t(fleet), transport_petrol_emissions: t(petrol),
    lpg_emissions: tv(lpg, 'lpg', { unit: 'tCO2e', kind: 'calculation' }),
    scope1_tco2e: tv(scope1 !== undefined ? scope1 : present.reduce((a, b) => a + b, 0), 'ghg', { unit: 'tCO2e', kind: 'calculation' })
  };
}
/* A 2026 timeline: January, February and the YTD record, each with its OWN values. */
function mixTimeline({ jan, feb, ytd }) {
  return timelineOf([
    tlMonth(2026, 1, jan), tlMonth(2026, 2, feb || jan),
    tlAggregate('2026-YTD', 2026, 'YTD', 2, ytd || jan, '2026 YTD · Jan–Feb')
  ], '2026-01');
}
/* Runs the real view helpers and the real chart blocks for one selection. */
function mixCharts(data, year, month) {
  const app = read('app.js');
  const fn = name => app.match(new RegExp(`function ${name}\\([\\s\\S]*?\\n\\}`))[0];
  const constant = name => app.match(new RegExp(`const ${name} = [\\s\\S]*?\\n[\\]}];`))[0];
  const elec = app.slice(app.indexOf('  const [gridVal, reVal, reOnCampusVal, reProcuredVal]'), app.indexOf('  // Same selected period as Renewable Energy Progress and the KPI cards.'));
  const fuel = app.slice(app.indexOf('  const fuelMix = fuelMixView(d, month);'), app.indexOf('  let hStack = null;'));
  const charts = {};
  const context = {
    d: data[String(year)], month, n: Number, Array, Number, Math,
    colors: { orange: 'ORANGE', gold: 'GOLD', teal: 'TEAL', violet: 'VIOLET' },
    mk: (id, config) => { charts[id] = config; }
  };
  const source = [
    fn('valFor'), fn('periodComposition'), constant('ELEC_MIX_PARTS'), constant('FUEL_MIX_PARTS'),
    fn('sharePct'), fn('elecMixView'), fn('fuelMixView'), elec, fuel,
    'globalThis.elecView = elecMixView(d, month); globalThis.fuelView = fuelMixView(d, month);'
  ].join('\n');
  vm.runInNewContext(source, context);
  const rings = id => [...charts[id].data.datasets].map(dataset => [...dataset.data]);
  const tip = (id, datasetIndex, dataIndex) => {
    const chart = charts[id], callbacks = chart.options.plugins.tooltip.callbacks;
    const item = { datasetIndex, dataIndex, raw: chart.data.datasets[datasetIndex].data[dataIndex], chart };
    // Digit grouping follows the viewer's locale; the tests compare the ungrouped text.
    return { title: callbacks.title([item]), label: callbacks.label(item).replace(/,/g, '') };
  };
  return { charts, elec: rings('elecMixChartCanvas'), fuel: rings('fuelMixChartCanvas'), tip, elecView: context.elecView, fuelView: { ...context.fuelView } };
}
const mixData = async timeline => (await loadDashboardFromTimeline(timeline)).data;
const pctNumber = text => Number(String(text).replace('%', ''));

test('Electricity Mix draws two rings from the backend kWh values of the selected period', async () => {
  const data = await mixData(mixTimeline({
    jan: mixEnergy([46442, 15950, 241602]), feb: mixEnergy([900, 60, 40]), ytd: mixEnergy([47342, 16010, 241642])
  }));
  const jan = mixCharts(data, 2026, '0');
  assert.equal(jan.elec.length, 2);
  assert.deepEqual(jan.elec[0], [46442, 257552]);          // outer: grid, renewable electricity
  assert.deepEqual(jan.elec[1], [46442, 15950, 241602]);   // inner: grid, on-campus, procured
  // A month is that month; YTD / Full Year is the backend's aggregate record - never a browser sum.
  assert.deepEqual(mixCharts(data, 2026, '1').elec, [[900, 100], [900, 60, 40]]);
  assert.deepEqual(mixCharts(data, 2026, 'all').elec, [[47342, 257652], [47342, 16010, 241642]]);
  const annual = await mixData(timelineOf([tlAggregate('2025-FY', 2025, 'ANNUAL', 12, mixEnergy([1000, 200, 800]), '2025 Full Year')], '2025-FY'));
  assert.deepEqual(mixCharts(annual, 2025, 'all').elec, [[1000, 1000], [1000, 200, 800]]);
  // Tooltips name each ring's own categories and give the raw kWh.
  assert.deepEqual(jan.tip('elecMixChartCanvas', 0, 0), { title: 'Grid electricity', label: ' Grid electricity: 46442 kWh' });
  assert.equal(jan.tip('elecMixChartCanvas', 0, 1).label, ' Renewable electricity: 257552 kWh');
  assert.equal(jan.tip('elecMixChartCanvas', 1, 1).label, ' On-campus Solar PV: 15950 kWh');
  assert.equal(jan.tip('elecMixChartCanvas', 1, 2).label, ' Procured Green Energy: 241602 kWh');
});

test('Electricity Mix shows both the renewable and the grid percentage, to one decimal', async () => {
  const data = await mixData(mixTimeline({ jan: mixEnergy([46442, 15950, 241602]), feb: mixEnergy([900, 60, 40]) }));
  assert.deepEqual({ ...mixCharts(data, 2026, '0').elecView }, { available: true, rePct: '84.7%', gridPct: '15.3%' });
  assert.deepEqual({ ...mixCharts(data, 2026, '1').elecView }, { available: true, rePct: '10.0%', gridPct: '90.0%' });
  // Renewable % is the backend's own share; grid % is backend grid over the backend total.
  const backend = await mixData(mixTimeline({ jan: mixEnergy([250, 100, 650], { share: 77.77 }) }));
  assert.deepEqual({ ...mixCharts(backend, 2026, '0').elecView }, { available: true, rePct: '77.8%', gridPct: '25.0%' });
  const app = read('app.js');
  assert.match(app, /const gridPctStr = elecMix\.gridPct, rePctStr = elecMix\.rePct;/);
  assert.doesNotMatch(app, /const gridPctStr = '';/);
  assert.match(app, /<div class="elec-pct elec-pct-grid">\$\{gridPctStr\}<\/div>/);
  assert.match(app, /<div class="elec-pct elec-pct-re">\$\{rePctStr\}<\/div>/);
  // The browser never adds grid + renewable to make its own total.
  assert.doesNotMatch(app.match(/function elecMixView\([\s\S]*?\n\}/)[0], /\+/);
});

test('Electricity Mix follows the data, ignores the solar water heater and never turns missing into zero', async () => {
  // Grid high / renewable low, then the reverse: both rings and both labels move.
  const low = mixCharts(await mixData(mixTimeline({ jan: mixEnergy([800, 50, 150]) })), 2026, '0');
  const high = mixCharts(await mixData(mixTimeline({ jan: mixEnergy([100, 300, 600]) })), 2026, '0');
  assert.deepEqual(low.elec, [[800, 200], [800, 50, 150]]);
  assert.deepEqual(high.elec, [[100, 900], [100, 300, 600]]);
  assert.deepEqual([low.elecView.rePct, low.elecView.gridPct], ['20.0%', '80.0%']);
  assert.deepEqual([high.elecView.rePct, high.elecView.gridPct], ['90.0%', '10.0%']);
  for (const view of [low.elecView, high.elecView]) assert.equal(pctNumber(view.rePct) + pctNumber(view.gridPct), 100);
  // A large thermal figure changes nothing in either ring or label.
  const heater = mixCharts(await mixData(mixTimeline({ jan: mixEnergy([100, 300, 600], { heater: 99999 }) })), 2026, '0');
  assert.deepEqual(heater.elec, high.elec);
  assert.deepEqual({ ...heater.elecView }, { ...high.elecView });
  assert.doesNotMatch(read('app.js').match(/const ELEC_MIX_PARTS = \[[\s\S]*?\n\];/)[0], /solar_water_heater|solarWaterHeater/);
  // No backend share, but grid and renewable exist: the widget still renders, from the raw values.
  const noShare = mixCharts(await mixData(mixTimeline({ jan: mixEnergy([100, 300, 600], { share: null }) })), 2026, '0');
  assert.deepEqual({ ...noShare.elecView }, { available: true, rePct: '90.0%', gridPct: '10.0%' });
  // A missing procured value stays missing in the inner ring; the top level is still drawn.
  const partial = mixCharts(await mixData(mixTimeline({ jan: mixEnergy([100, 300, null], { renewable: 300, total: 400, share: 75 }) })), 2026, '0');
  assert.deepEqual(partial.elec, [[100, 300], [100, 300, null]]);
  // A missing top-level component means no widget and no percentage - never a 0 % or 100 %.
  const noGrid = mixCharts(await mixData(mixTimeline({ jan: mixEnergy([null, 300, 600], { renewable: 900 }) })), 2026, '0');
  assert.deepEqual({ ...noGrid.elecView }, { available: false, rePct: '', gridPct: '' });
  assert.match(read('app.js'), /if \(!elecMix\.available\) \{\s*elecMixWidget\.innerHTML = '';/);
  // An explicit zero is a value: 0 kWh of grid is 0.0 %, and the widget renders.
  const zeroGrid = mixCharts(await mixData(mixTimeline({ jan: mixEnergy([0, 300, 700]) })), 2026, '0');
  assert.deepEqual({ ...zeroGrid.elecView }, { available: true, rePct: '100.0%', gridPct: '0.0%' });
  assert.deepEqual(zeroGrid.elec[0], [0, 1000]);
});

test('Fossil Fuel Emissions Mix draws fuel groups outside and the four contributors inside', async () => {
  const data = await mixData(mixTimeline({
    jan: mixFuel([4.8618, 24.309, 1.398556, 22.13842], 52.707776), feb: mixFuel([1, 2, 3, 4]), ytd: mixFuel([5.8618, 26.309, 4.398556, 26.13842])
  }));
  const jan = mixCharts(data, 2026, '0');
  assert.equal(jan.fuel.length, 2);
  assert.equal(jan.fuel[0].length, 3);
  assert.deepEqual(jan.fuel[1], [4.8618, 24.309, 1.398556, 22.13842]);        // inner: DG, Fleet, Petrol, LPG
  assert.ok(Math.abs(jan.fuel[0][0] - (24.309 + 4.8618)) < 1e-9);             // outer Diesel = Fleet + DG
  assert.deepEqual(jan.fuel[0].slice(1), [1.398556, 22.13842]);               // outer Petrol, LPG
  // Petrol and LPG share one colour across both rings; DG and Fleet differ inside the Diesel arc.
  const [outer, inner] = jan.charts.fuelMixChartCanvas.data.datasets;
  assert.deepEqual([...outer.backgroundColor], ['ORANGE', 'TEAL', 'VIOLET']);
  assert.deepEqual([...inner.backgroundColor], ['ORANGE', 'GOLD', 'TEAL', 'VIOLET']);
  assert.notEqual(inner.backgroundColor[0], inner.backgroundColor[1]);
  // Month = that month; YTD = the backend aggregate record.
  assert.deepEqual(mixCharts(data, 2026, '1').fuel, [[3, 3, 4], [1, 2, 3, 4]]);
  assert.deepEqual(mixCharts(data, 2026, 'all').fuel[1], [5.8618, 26.309, 4.398556, 26.13842]);
  // Tooltips: group names outside, contributor names inside, raw tCO2e.
  assert.equal(jan.tip('fuelMixChartCanvas', 0, 0).title, 'Total Diesel emissions');
  assert.equal(jan.tip('fuelMixChartCanvas', 0, 1).label, ' Petrol emissions: 1.399 tCO₂e');
  assert.equal(jan.tip('fuelMixChartCanvas', 0, 2).title, 'LPG emissions');
  assert.equal(jan.tip('fuelMixChartCanvas', 1, 0).label, ' DG Diesel emissions: 4.862 tCO₂e');
  assert.equal(jan.tip('fuelMixChartCanvas', 1, 1).title, 'Fleet Diesel emissions');
});

test('every Fossil Fuel percentage is a share of the backend Scope 1 total', async () => {
  const jan = mixCharts(await mixData(mixTimeline({ jan: mixFuel([4.8618, 24.309, 1.398556, 22.13842], 52.707776) })), 2026, '0').fuelView;
  assert.deepEqual([jan.lpgPct, jan.petrolPct, jan.dieselPct, jan.fleetPct, jan.dgPct], ['42.0%', '2.7%', '55.3%', '46.1%', '9.2%']);
  // Fleet % + DG % = Diesel %, and the four contributors make up the whole (within rounding).
  assert.ok(Math.abs(pctNumber(jan.fleetPct) + pctNumber(jan.dgPct) - pctNumber(jan.dieselPct)) < 0.11);
  assert.ok(Math.abs(pctNumber(jan.lpgPct) + pctNumber(jan.petrolPct) + pctNumber(jan.fleetPct) + pctNumber(jan.dgPct) - 100) < 0.21);
  // The denominator is the backend Scope 1, not a browser sum: a different Scope 1 moves every share.
  const other = mixCharts(await mixData(mixTimeline({ jan: mixFuel([10, 20, 30, 40], 200) })), 2026, '0').fuelView;
  assert.deepEqual([other.lpgPct, other.petrolPct, other.dieselPct, other.fleetPct, other.dgPct], ['20.0%', '15.0%', '15.0%', '10.0%', '5.0%']);
  const app = read('app.js');
  const view = app.match(/function fuelMixView\([\s\S]*?\n\}/)[0];
  assert.equal((view.match(/sharePct\([^)]*, scope1\)/g) || []).length, 5);
  assert.match(view, /const scope1 = valFor\(d, d\?\.scope1Full, month\);/);
  // The widget shows the Diesel total with the Fleet / DG breakdown beneath it.
  assert.match(app, /<div class="elec-sub">Diesel<br>emissions<\/div>/);
  assert.match(app, /Fleet diesel <b>\$\{fleetPct\}<\/b>/);
  assert.match(app, /DG diesel <b>\$\{dgPct\}<\/b>/);
  assert.match(read('styles.css'), /\.fuel-mix-breakdown \{[^}]*font-size: 12px/);
});

test('swapping Fleet and DG changes the inner partition but not the outer Diesel total', async () => {
  const fleetHigh = mixCharts(await mixData(mixTimeline({ jan: mixFuel([5, 45, 10, 40]) })), 2026, '0');
  const dgHigh = mixCharts(await mixData(mixTimeline({ jan: mixFuel([45, 5, 10, 40]) })), 2026, '0');
  assert.deepEqual(fleetHigh.fuel[0], [50, 10, 40]);
  assert.deepEqual(dgHigh.fuel[0], fleetHigh.fuel[0]);                 // outer ring unchanged
  assert.deepEqual(fleetHigh.fuel[1], [5, 45, 10, 40]);
  assert.deepEqual(dgHigh.fuel[1], [45, 5, 10, 40]);                   // inner Fleet / DG partition swapped
  assert.equal(fleetHigh.fuelView.dieselPct, '50.0%');
  assert.equal(dgHigh.fuelView.dieselPct, '50.0%');
  assert.deepEqual([fleetHigh.fuelView.fleetPct, fleetHigh.fuelView.dgPct], ['45.0%', '5.0%']);
  assert.deepEqual([dgHigh.fuelView.fleetPct, dgHigh.fuelView.dgPct], ['5.0%', '45.0%']);
});

test('a missing fuel contributor stays missing, and an explicit zero stays zero', async () => {
  // DG not published: its slice is empty, it has no percentage, and no combined Diesel % is claimed.
  const missing = mixCharts(await mixData(mixTimeline({ jan: mixFuel([null, 45, 10, 40]) })), 2026, '0');
  assert.deepEqual(missing.fuel[1], [null, 45, 10, 40]);
  assert.equal(missing.fuelView.dgPct, '');
  assert.equal(missing.fuelView.dieselPct, '');
  assert.equal(missing.fuelView.dieselComplete, false);
  assert.equal(missing.fuelView.fleetPct, '47.4%');   // share of the Scope 1 the backend published for what exists
  // The outer arc covers only the published part, and its tooltip says so.
  assert.deepEqual(missing.fuel[0], [45, 10, 40]);
  assert.equal(missing.tip('fuelMixChartCanvas', 0, 0).title, 'Diesel emissions (published part only)');
  assert.equal(missing.tip('fuelMixChartCanvas', 1, 0).label, ' DG Diesel emissions: Not published');
  // Neither diesel source published: no Diesel arc at all.
  const none = mixCharts(await mixData(mixTimeline({ jan: mixFuel([null, null, 10, 40]) })), 2026, '0');
  assert.deepEqual(none.fuel, [[null, 10, 40], [null, null, 10, 40]]);
  // DG reported as 0: a real value, 0.0 %, and the Diesel total is complete.
  const zero = mixCharts(await mixData(mixTimeline({ jan: mixFuel([0, 50, 10, 40]) })), 2026, '0');
  assert.deepEqual(zero.fuel, [[50, 10, 40], [0, 50, 10, 40]]);
  assert.deepEqual([zero.fuelView.dgPct, zero.fuelView.fleetPct, zero.fuelView.dieselPct, zero.fuelView.dieselComplete], ['0.0%', '50.0%', '50.0%', true]);
});

test('the two mix widgets carry no operational number, factor or CSV', () => {
  const app = read('app.js');
  const slice = (from, to) => app.slice(app.indexOf(from), app.indexOf(to));
  const code = [
    app.match(/function sharePct\([\s\S]*?\n\}/)[0], app.match(/function elecMixView\([\s\S]*?\n\}/)[0],
    app.match(/function fuelMixView\([\s\S]*?\n\}/)[0],
    slice('  const [gridVal, reVal, reOnCampusVal, reProcuredVal]', '  // Same selected period as Renewable Energy Progress'),
    slice('  const fuelMix = fuelMixView(d, month);', '  let hStack = null;')
  ].join('\n');
  // No share, emission figure or energy figure from any period.
  assert.doesNotMatch(code, /84\.7|15\.3|69\.2|42\.0|55\.3|46\.1|9\.2|32\.8|63\.2|22\.138|24\.309|4\.8618|46442|257552/);
  // No emission factor and no litre / kg conversion anywhere in the dashboard code.
  for (const file of ['app.js', 'public-data-loader.js', 'public-api.js']) {
    assert.doesNotMatch(read(file), /2\.701|2\.388|0\.727|2\.98\b|1\.5571/, file);
  }
  assert.doesNotMatch(code, /dgL|trDieselL|petrolL|lpgKg|\.csv/);
  // The data path is the public timeline only.
  const loader = read('public-data-loader.js');
  for (const pair of ["petrolEm: 'transport_petrol_emissions'", "trDieselEm: 'transport_diesel_emissions'", "dgEm: 'dg_diesel_emissions'", "lpgEm: 'lpg_emissions'", "scope1Full: 'scope1_tco2e'"]) {
    assert.ok(loader.includes(pair), pair);
  }
  assert.doesNotMatch(loader, /transport_master|dg_master|lpg_master|energy_master|emission_factors/);
  // Other pages' primary cards are untouched by this change.
  assert.match(app, /energyKpisEl\.innerHTML = energyPrimaryKpisHtml\(d, month\);/);
  assert.match(app, /wasteKpisEl\.innerHTML = wastePrimaryKpisHtml\(\);/);
  assert.match(app, /ghgKpi\('Reduction through renewables', avoid,/);
});

// ---- Water page: exactly three primary KPI cards for every selection ---------
// One definition (WATER_PRIMARY_KPIS) drives a month, YTD and Full Year alike.
// The figures below are test fixtures fed through the real loader and the real
// card code; none of them exists in the dashboard source.
const WATER_TITLES = ['Total water consumption', 'Consumption per capita', 'Total water recycled'];
const WATER_CODES = ['water_consumed_kl', 'water_per_capita_l', 'water_recycled_kl'];
/* A water period: source components plus the backend's own total, per capita and recycled. */
function waterValues({ twad = 10, borewell = 20, priv = 5, total, perCapita, recycled }) {
  const kl = (value, kind = 'metric') => tv(value, 'water', { unit: 'KL', kind });
  return {
    water_twad_kl: kl(twad), water_borewell_kl: kl(borewell), water_private_kl: kl(priv),
    water_consumed_kl: kl(total, 'calculation'),
    water_per_capita_l: tv(perCapita, 'water', { unit: 'L/person', kind: 'calculation' }),
    water_recycled_kl: kl(recycled)
  };
}
/* The backend's display items: the period's own values, plus labelled year context it resolved. */
function waterDisplay(period, context = {}) {
  period.display = Object.fromEntries(Object.entries(period.values).filter(([, item]) => item.value != null)
    .map(([code, item]) => [code, { value: item.value, unit: item.unit, display_label: period.label, display_context: false }]));
  Object.entries(context).forEach(([code, [value, label]]) => {
    period.display[code] = { value, unit: 'KL', display_label: label, display_context: true };
  });
  return period;
}
const WATER_PERIODS = {
  '2026-01': { total: 20215, perCapita: 2891.574882, recycled: null },
  '2026-04': { total: 20176, perCapita: 2885.996281, recycled: null },
  '2026-07': { total: 20467.27, perCapita: 2927.659848, recycled: null },
  '2026-YTD': { total: 143372.27, perCapita: 20508.120441, recycled: 47256 },
  '2025-FY': { total: 195708, perCapita: 27994.278358, recycled: 169404 }
};
function waterKpiTimeline(periods = WATER_PERIODS) {
  const built = Object.entries(periods).map(([key, numbers]) => {
    const [year, part] = key.split('-');
    const values = waterValues(numbers);
    if (part === 'YTD') return waterDisplay(tlAggregate(key, +year, 'YTD', 7, values, `${year} YTD · Jan–Jul`));
    if (part === 'FY') return waterDisplay(tlAggregate(key, +year, 'ANNUAL', 12, values, `${year} Full Year`));
    // A month has no recycled value of its own; the backend offers the year's figure as labelled context.
    const yearly = periods[`${year}-YTD`];
    return waterDisplay(tlMonth(+year, +part, values), numbers.recycled == null && yearly?.recycled != null ? { water_recycled_kl: [yearly.recycled, `${year} YTD`] } : {});
  });
  return timelineOf(built, Object.keys(periods).find(key => /-\d\d$/.test(key)) || Object.keys(periods)[0]);
}
/* Renders #waterKpis with the real definition, card lookup and kpi() override. */
function waterCards(data, year, month) {
  const app = read('app.js');
  const fn = name => app.match(new RegExp(`function ${name}\\([\\s\\S]*?\\n\\}`))[0];
  const source = [
    'const kgOrTonnes = kg => ({ value: kg });',
    app.match(/const CARD_DISPLAY = \{[\s\S]*?\n\};/)[0],
    app.match(/const WATER_PRIMARY_KPIS = \[[\s\S]*?\n\];\nWATER_PRIMARY_KPIS\.forEach[^\n]*/)[0],
    fn('missingKpiHtml'), fn('waterPrimaryKpisHtml'), fn('valFor'), fn('displayFor'), fn('sourceBadge'),
    'let kpi;', app.match(/\nkpi = function \([\s\S]*?\n\};/)[0],
    'globalThis.html = waterPrimaryKpisHtml(d, month); globalThis.definition = WATER_PRIMARY_KPIS; globalThis.cardDisplay = CARD_DISPLAY;'
  ].join('\n');
  const d = data[String(year)];
  const context = {
    d, month, n: Number, Array, Object, String,
    colors: { cyan: 'c', teal: 't', emerald: 'e' }, ic: name => `<i>${name}</i>`,
    currentPeriod: () => ({ year, month, d }), previousValue: () => null,
    partialNoteHtml: () => '', dgOriginNoteHtml: () => '', STATIC_CARDS: new Set(), STATIC_LABEL: '',
    renderNumericKpi: (title, value, unit, accent, icon, prev, lowerGood, dec) => `<article class="kpi"><div class="label">${title}</div><div class="value"><span class="counter-val" data-val="${value}" data-dec="${dec}">0</span><small>${unit}</small></div><div class="trend"></div></article>`
  };
  vm.runInNewContext(source, context);
  const cards = context.html.split('</article>').filter(Boolean).map(card => ({
    title: card.match(/<div class="label">([^<]*)<\/div>/)[1],
    value: /data-val="([^"]*)"/.test(card) ? Number(card.match(/data-val="([^"]*)"/)[1]) : null,
    unit: card.match(/<small>([^<]*)<\/small>/)[1],
    source: (card.match(/<div class="kpi-source[^"]*">([^<]*)<\/div>/) || [])[1] || null
  }));
  return { cards, html: context.html, definition: [...context.definition], cardDisplay: context.cardDisplay };
}
const waterSelections = [['2026', '0', '2026-01'], ['2026', '3', '2026-04'], ['2026', '6', '2026-07'], ['2026', 'all', '2026-YTD'], ['2025', 'all', '2025-FY']];
const waterShown = result => result.cards.map(card => card.value);

test('the Water page renders exactly three primary KPI cards, the same for every selection', async () => {
  const { data } = await loadDashboardFromTimeline(waterKpiTimeline());
  for (const [year, month, key] of waterSelections) {
    const { cards } = waterCards(data, +year, month);
    assert.equal(cards.length, 3, key);
    assert.deepEqual(cards.map(card => card.title), WATER_TITLES, key);
    assert.deepEqual(cards.map(card => card.unit), ['KL', 'L/person', 'KL'], key);
  }
  const { definition, cardDisplay } = waterCards(data, 2026, '6');
  assert.deepEqual(definition.map(card => card.code), WATER_CODES);
  assert.deepEqual(definition.map(card => card.series), ['waterKL', 'waterPerCapitaL', 'waterRecycledKL']);
  WATER_TITLES.forEach((title, index) => assert.equal(cardDisplay[title].code, WATER_CODES[index]));
  const loader = read('public-data-loader.js');
  for (const pair of ["waterKL: 'water_consumed_kl'", "waterPerCapitaL: 'water_per_capita_l'", "waterRecycledKL: 'water_recycled_kl'"]) {
    assert.ok(loader.includes(pair), pair);
  }
  // The row is that one definition and nothing else, for every selection.
  const app = read('app.js');
  assert.match(app, /waterKpisEl\.innerHTML = inDomain\('water', \(\) => waterPrimaryKpisHtml\(d, month\)\);/);
  assert.equal(app.match(/waterKpisEl\.innerHTML/g).length, 1);
});

test('each Water KPI shows the backend value resolved for the selection', async () => {
  const { data } = await loadDashboardFromTimeline(waterKpiTimeline());
  // A month: its own backend total and per capita; recycled is the year's figure, labelled as such.
  const july = waterCards(data, 2026, '6');
  assert.deepEqual(waterShown(july), [20467.27, 2927.659848, 47256]);
  assert.deepEqual(july.cards.map(card => card.source), ['Jul 2026', 'Jul 2026', '2026 YTD']);
  assert.deepEqual(waterShown(waterCards(data, 2026, '0')), [20215, 2891.574882, 47256]);
  assert.deepEqual(waterShown(waterCards(data, 2026, '3')), [20176, 2885.996281, 47256]);
  // YTD and Full Year: the backend's aggregate records.
  assert.deepEqual(waterShown(waterCards(data, 2026, 'all')), [143372.27, 20508.120441, 47256]);
  assert.deepEqual(waterShown(waterCards(data, 2025, 'all')), [195708, 27994.278358, 169404]);
  assert.equal(waterCards(data, 2025, 'all').cards[2].source, '2025 Full Year');
  // Different backend values give different cards - and per capita is whatever the backend says,
  // even when it does not equal total x 1000 / population (the browser never recomputes it).
  const other = (await loadDashboardFromTimeline(waterKpiTimeline({ '2026-01': { total: 900, perCapita: 7.5, recycled: 60 } }))).data;
  assert.deepEqual(waterShown(waterCards(other, 2026, '0')), [900, 7.5, 60]);
  const changedSources = (await loadDashboardFromTimeline(waterKpiTimeline({ '2026-01': { twad: 999, borewell: 999, priv: 999, total: 900, perCapita: 7.5, recycled: 60 } }))).data;
  assert.deepEqual(waterShown(waterCards(changedSources, 2026, '0')), [900, 7.5, 60]);  // sources are not summed here
});

test('a Water KPI with no backend value stays in place as "—", and an explicit zero stays zero', async () => {
  const missing = (await loadDashboardFromTimeline(waterKpiTimeline({ '2026-01': { total: 900, perCapita: null, recycled: null } }))).data;
  const result = waterCards(missing, 2026, '0');
  assert.deepEqual(result.cards.map(card => card.title), WATER_TITLES);
  assert.deepEqual(waterShown(result), [900, null, null]);
  assert.equal((result.html.match(/No value for this period/g) || []).length, 2);
  assert.doesNotMatch(result.html, /data-val="(?:0|null|undefined|NaN)"/);
  const zero = (await loadDashboardFromTimeline(waterKpiTimeline({ '2026-01': { total: 900, perCapita: 128.7, recycled: 0 } }))).data;
  assert.deepEqual(waterShown(waterCards(zero, 2026, '0')), [900, 128.7, 0]);
  assert.doesNotMatch(waterCards(zero, 2026, '0').html, /No value for this period/);
});

test('water source components and other metrics never become a main Water card, and nothing is calculated in the browser', async () => {
  const { data } = await loadDashboardFromTimeline(waterKpiTimeline());
  for (const [year, month, key] of waterSelections) {
    assert.doesNotMatch(waterCards(data, +year, month).html, /TWAD|Borewell|Private|Wastewater|supply/i, key);
  }
  const app = read('app.js');
  const definition = app.match(/const WATER_PRIMARY_KPIS = \[[\s\S]*?\n\];/)[0];
  assert.doesNotMatch(definition, /water_twad|water_borewell|water_private|wastewater|waterTWAD|waterBorewell|waterProcured/);
  assert.doesNotMatch(app, /kpi\('(?:TWAD water supply|Borewell water supply|Private water supply|Wastewater generated)'/);
  // No total, per-capita or population arithmetic in the card code.
  const renderer = app.match(/function waterPrimaryKpisHtml\([\s\S]*?\n\}/)[0];
  assert.doesNotMatch(renderer, /[*/+]\s*(?:1000|population|d\.population)|waterTWAD|reduce\(|month === 'all'/);
  assert.doesNotMatch(app + read('public-data-loader.js'), /water(?:KL|_consumed_kl)[^\n;]*\*\s*1000\s*\/|waterTWAD\[[^\]]*\]\s*\+/);
  // No operational water figure is written into the dashboard.
  for (const file of ['app.js', 'public-data-loader.js', 'public-api.js', 'index.html']) {
    assert.doesNotMatch(read(file), /\b(?:20215|20176|143372|195708|47256|169404|5077)\b|\b726\b/, file);
  }
});

test('Water graphs and other pages are untouched by the Water KPI row', () => {
  const app = read('app.js');
  const html = read('index.html');
  for (const chart of ['waterTrendChartCanvas', 'waterSourceChartCanvas', 'waterTWADTrendCanvas', 'waterBorewellTrendCanvas', 'waterProcuredTrendCanvas']) {
    assert.ok(app.includes(`mk('${chart}'`), chart);
    assert.ok(html.includes(`id="${chart}"`), chart);
  }
  assert.match(app, /data: wsl\(d\.waterKL\)/);
  assert.match(app, /label: 'Private water supply', data: wsl\(d\.waterProcured\)/);
  assert.match(app, /\['Private water supply', 'waterProcured', 'water_private_kl', colors\.gold\]/);
  assert.match(html, /<section class="kpi-grid" id="waterKpis" style="grid-template-columns: repeat\(3, 1fr\);"><\/section>/);
  // Overview keeps its own water cards; other pages keep their primary definitions.
  assert.match(app, /overviewKpi\('Total water usage', waterKL, 'KL'/);
  assert.match(app, /overviewKpi\('Total water recycled', hasPublication \? waterRecycled : null, 'KL'/);
  assert.match(app, /energyKpisEl\.innerHTML = energyPrimaryKpisHtml\(d, month\);/);
  assert.match(app, /wasteKpisEl\.innerHTML = wastePrimaryKpisHtml\(\);/);
});

// ---- Public certificates: Waste -> Certificates -> year -> gallery -> viewer --
// Years, documents and every piece of metadata come from the certificate API.
// The fixtures below are test data; none of it exists in the dashboard source.
/* A small DOM stand-in: enough of the element API for certificates.js to render into. */
function certDom() {
  const byId = {};
  class Node {
    constructor(tag) { this.tagName = String(tag).toUpperCase(); this.children = []; this.attributes = {}; this.listeners = {}; this.style = {}; this.hidden = false; this.className = ''; this._text = ''; this._id = ''; }
    set id(value) { this._id = value; byId[value] = this; } get id() { return this._id; }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return [this._text, ...this.children.map(child => child.textContent)].filter(Boolean).join(' '); }
    get classList() { const node = this; return { toggle(name, on) { const set = new Set(node.className.split(' ').filter(Boolean)); if (on) set.add(name); else set.delete(name); node.className = [...set].join(' '); }, add(name) { this.toggle(name, true); }, remove(name) { this.toggle(name, false); }, contains: name => node.className.split(' ').includes(name) }; }
    setAttribute(name, value) { this.attributes[name] = String(value); } getAttribute(name) { return this.attributes[name] ?? null; }
    addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
    append(...nodes) { nodes.forEach(node => { node.parent = this; this.children.push(node); }); }
    replaceChildren(...nodes) { this.children = []; this._text = ''; this.append(...nodes); }
    get lastChild() { return this.children[this.children.length - 1]; }
    replaceWith(node) { const list = this.parent.children; node.parent = this.parent; list[list.indexOf(this)] = node; }
    all(test, found = []) { this.children.forEach(child => { if (test(child)) found.push(child); child.all(test, found); }); return found; }
    byClass(name) { return this.all(node => node.className.split(' ').includes(name)); }
    querySelector() { return null; } querySelectorAll() { return []; } closest() { return null; } focus() {}
    click() { (this.listeners.click || []).forEach(handler => handler({ target: this, preventDefault() {} })); }
  }
  const body = new Node('body');
  const document = {
    readyState: 'complete', body, activeElement: null,
    createElement: tag => new Node(tag), getElementById: id => byId[id] || null,
    querySelectorAll: () => [], addEventListener() {}
  };
  return { Node, document, byId };
}
/* Loads the real certificates.js against a fake page and a fake public API. */
async function certHarness(api, hash = '') {
  const { Node, document, byId } = certDom();
  for (const id of ['waste', 'wasteCertificates', 'wasteCertOpen']) { const node = new Node('section'); node.id = id; document.body.append(node); }
  byId.wasteCertificates.hidden = true;
  const requested = [];
  const listeners = {};
  const window = {
    location: { hash, pathname: '/', search: '' }, history: { pushState() {}, replaceState() {} },
    addEventListener: (type, handler) => { (listeners[type] ||= []).push(handler); }, scrollTo() {},
    go: id => { document.body.setAttribute('data-page', id); }
  };
  const fetchImpl = async url => {
    requested.push(String(url));
    const [path, query] = String(url).split('?');
    const params = new URLSearchParams(query || '');
    if (path === '/api/public/certificates/years') return { ok: true, json: async () => ({ domain: params.get('domain'), years: api.years }) };
    if (path === '/api/public/certificates') return { ok: true, json: async () => ({ domain: params.get('domain'), reporting_year: Number(params.get('year')), certificates: api.certificates[params.get('year')] || [] }) };
    return { ok: false, status: 404, json: async () => ({}) };
  };
  vm.runInNewContext(read('certificates.js'), { window, document, fetch: fetchImpl, URLSearchParams, Number, String, Object, Date, Promise, Boolean, setTimeout, encodeURIComponent });
  const settle = () => new Promise(resolve => setTimeout(resolve, 5));
  const navigate = async next => { window.location.hash = next; listeners.hashchange.forEach(handler => handler()); await settle(); };
  await settle();
  return { byId, requested, navigate, settle, host: byId.wasteCertificates, page: byId.waste, entry: byId.wasteCertOpen, window };
}
const CERT_A = { id: '11111111-1111-4111-8111-111111111111', title: 'Fixture certificate A', certificate_type: 'Fixture Disposal Certificate', reporting_year: 2031, issuer: 'Fixture Recycler', serial_no: 'FX-1', manifest_doc_no: 'FX/M/1', invoice_no: 'FX/I/1', registration_id: 'R-1', authorization_no: 'AU-1', received_date: '2031-11-28', certificate_date: '2032-01-23', quantity_value: 1234.5, quantity_unit: 'kg', mime_type: 'image/jpeg' };
const CERT_B = { ...CERT_A, id: '22222222-2222-4222-8222-222222222222', title: 'Fixture certificate B', serial_no: 'FX-2', manifest_doc_no: 'FX/M/2', received_date: '2031-11-29', quantity_value: 77, mime_type: 'application/pdf' };

test('the Waste page offers Certificates as a supporting section, not a KPI card', () => {
  const html = read('index.html');
  const waste = html.slice(html.indexOf('<main class="page" id="waste">'), html.indexOf('<!-- ===================== WATER'));
  assert.match(waste, /<section class="card cert-entry" id="wasteCertEntry">/);
  assert.match(waste, /<h2>Certificates<\/h2>/);
  assert.match(waste, /<button type="button" class="cert-btn" id="wasteCertOpen">View Certificates →<\/button>/);
  assert.match(waste, /<section class="cert-section" id="wasteCertificates" hidden><\/section>/);
  // It sits after the charts and inside no KPI grid; the KPI row itself is untouched.
  assert.ok(waste.indexOf('wasteMaterialChartCanvas') < waste.indexOf('wasteCertEntry'));
  assert.match(waste, /<section class="kpi-grid" id="wasteKpis" style="grid-template-columns: repeat\(3, 1fr\);"><\/section>/);
  assert.match(read('app.js'), /wasteKpisEl\.innerHTML = wastePrimaryKpisHtml\(\);/);
  assert.equal(read('app.js').match(/const WASTE_PRIMARY_KPIS = \[[\s\S]*?\n\];/)[0].match(/title:/g).length, 3);
  assert.doesNotMatch(read('app.js'), /certificate/i);  // no KPI, chart or calculation knows about certificates
  assert.match(html, /<script src="certificates\.js\?v=\d+"><\/script>/);
  // While the certificate view is open the page's own content is hidden by CSS, not changed.
  assert.match(read('styles.css'), /\.page\.cert-view > \.page-hero, \.page\.cert-view > \.row, \.page\.cert-view > \.cert-entry \{ display: none; \}/);
});

test('certificate years and cards come from the API; a new year appears with no code change', async () => {
  const api = { years: [{ year: 2031, certificate_count: 2, certificate_types: ['Fixture Disposal Certificate'] }], certificates: { 2031: [CERT_A, CERT_B] } };
  const view = await certHarness(api);
  assert.equal(view.host.hidden, true);
  assert.deepEqual(view.requested, []);  // nothing is fetched until the visitor opens Certificates
  view.entry.click();
  assert.equal(view.window.location.hash, '#waste-certificates');
  await view.navigate('#waste-certificates');
  assert.equal(view.host.hidden, false);
  assert.ok(view.page.classList.contains('cert-view'));
  assert.deepEqual(view.requested, ['/api/public/certificates/years?domain=waste']);
  const years = view.host.byClass('cert-year-card');
  assert.equal(years.length, 1);
  assert.equal(years[0].href, '#waste-certificates/2031');
  assert.match(years[0].textContent, /2031 Fixture Disposal Certificate 2 documents/);

  await view.navigate('#waste-certificates/2031');
  assert.equal(view.requested[1], '/api/public/certificates?domain=waste&year=2031');
  const cards = view.host.byClass('cert-card');
  assert.equal(cards.length, 2);
  const text = cards[0].textContent;
  for (const piece of ['Fixture certificate A', 'Fixture Disposal Certificate', 'Fixture Recycler', 'Reporting year 2031', 'Disposal received 28 Nov 2031', 'Certificate issued 23 Jan 2032', 'Serial no. FX-1', 'Manifest doc. no. FX/M/1', 'View Certificate']) {
    assert.ok(text.includes(piece), piece);
  }
  assert.match(text, /1,234\.5 kg/);
  // An image gets a thumbnail from the public file route; a PDF gets a document tile.
  assert.equal(cards[0].all(node => node.tagName === 'IMG')[0].src, '/api/public/certificates/11111111-1111-4111-8111-111111111111/file');
  assert.equal(cards[1].byClass('cert-thumb-doc')[0].textContent, 'PDF');

  // The backend publishes a certificate for another year: it simply appears.
  api.years.unshift({ year: 2032, certificate_count: 1, certificate_types: ['Other Certificate'] });
  await view.navigate('#waste-certificates');
  assert.deepEqual(view.host.byClass('cert-year').map(node => node.textContent), ['2032', '2031']);
  assert.match(view.host.byClass('cert-year-card')[0].textContent, /1 document$/);
  // ...and disappears when the API no longer lists it (archived).
  api.years.shift();
  await view.navigate('#waste-certificates/2031');
  await view.navigate('#waste-certificates');
  assert.deepEqual(view.host.byClass('cert-year').map(node => node.textContent), ['2031']);
  // Leaving the hash returns to the normal Waste page.
  await view.navigate('');
  assert.equal(view.host.hidden, true);
  assert.equal(view.page.classList.contains('cert-view'), false);
});

test('the certificate view shows only what the public API returns, and says so when there is nothing', async () => {
  // A draft or archived certificate is never in the public API response, so it can never be rendered.
  const empty = await certHarness({ years: [], certificates: {} }, '#waste-certificates');
  await empty.navigate('#waste-certificates');
  assert.equal(empty.host.byClass('cert-year-card').length, 0);
  assert.match(empty.host.textContent, /No certificates have been published yet\./);
  await empty.navigate('#waste-certificates/2031');
  assert.match(empty.host.textContent, /No certificates are published for 2031\./);
  // Only the public, read-only certificate routes are ever requested.
  for (const url of empty.requested) assert.match(url, /^\/api\/public\/certificates(\/years)?\?/);
  const source = read('certificates.js');
  assert.doesNotMatch(source, /\/api\/(admin|manager|auth)/);
  assert.doesNotMatch(source, /method:\s*['"](POST|PUT|PATCH|DELETE)/i);
  assert.match(source, /credentials: 'omit'/);
  // API text is written as text, never parsed as HTML.
  assert.doesNotMatch(source, /innerHTML|insertAdjacentHTML|document\.write/);
});

test('the certificate viewer opens, navigates, rotates and closes from the keyboard', async () => {
  const view = await certHarness({ years: [{ year: 2031, certificate_count: 2, certificate_types: [] }], certificates: { 2031: [CERT_A, CERT_B] } }, '#waste-certificates/2031');
  await view.navigate('#waste-certificates/2031');
  view.host.byClass('cert-card')[0].byClass('cert-btn')[0].click();
  const viewer = view.byId.certViewer;
  assert.equal(viewer.hidden, false);
  assert.equal(viewer.getAttribute('role'), 'dialog');
  assert.equal(viewer.getAttribute('aria-modal'), 'true');
  assert.equal(view.byId.certViewerTitle.textContent, 'Fixture certificate A');
  assert.equal(view.byId.certViewerStage.children[0].tagName, 'IMG');
  assert.equal(view.byId.certViewerOpen.href, '/api/public/certificates/11111111-1111-4111-8111-111111111111/file');
  assert.equal(view.byId.certViewerDownload.href, '/api/public/certificates/11111111-1111-4111-8111-111111111111/file?download=1');
  const side = view.byId.certViewerSide.textContent;
  for (const piece of ['Reporting year 2031', 'Disposal received 28 Nov 2031', 'Certificate issued 23 Jan 2032', 'Invoice no. FX/I/1', 'Registration ID R-1', 'Authorization no. AU-1']) {
    assert.ok(side.includes(piece), piece);
  }
  assert.match(side, /Its quantity is not used in any dashboard figure/);
  const key = name => viewer.listeners.keydown.forEach(handler => handler({ key: name, preventDefault() {} }));
  key('ArrowRight');
  assert.equal(view.byId.certViewerTitle.textContent, 'Fixture certificate B');
  assert.equal(view.byId.certViewerStage.children[0].tagName, 'IFRAME');  // a PDF is embedded, with an open-document fallback
  assert.equal(view.byId.certViewerStage.children[1].textContent, 'Open document');
  assert.equal(view.byId.certViewerRotate.hidden, true);
  assert.equal(view.byId.certViewerNext.disabled, true);
  key('ArrowLeft');
  assert.equal(view.byId.certViewerRotate.hidden, false);
  key('Escape');
  assert.equal(viewer.hidden, true);
  const css = read('styles.css');
  assert.match(css, /\.cert-viewer-image \{ max-width: 100%; max-height: 100%; object-fit: contain;/);
  assert.match(css, /@media \(max-width: 860px\) \{[\s\S]*?\.cert-viewer-image \{ width: 100%; height: auto; \}/);
});

test('no certificate content is written into the dashboard code', () => {
  for (const file of ['certificates.js', 'app.js', 'index.html', 'public-data-loader.js', 'public-api.js']) {
    const source = read(file);
    assert.doesNotMatch(source, /e-waste|Green India|\b1640\b|\b1390\b|2041-|20411|GIR\/|KCT\/|1718109|20HFZ/i, file);
    assert.doesNotMatch(source, /\.jpe?g['"]/i, file);  // no certificate file name
  }
  const source = read('certificates.js');
  assert.doesNotMatch(source, /\b20[2-9]\d\b/);  // no reporting year anywhere in the certificate code
  assert.doesNotMatch(source, /years\s*=\s*\[\s*\d/);
  assert.match(source, /const YEARS_ROUTE = '\/api\/public\/certificates\/years';/);
  assert.match(source, /domain: 'waste', pageId: 'waste'/);
});
