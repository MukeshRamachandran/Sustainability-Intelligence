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
  assert.match(app, /d\.totalWaste != null \? d\.totalWaste/);
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
  assert.match(app, /Complete GHG not published/);
  assert.match(app, /Methodology under review/);
  assert.match(app, /Not published/);
  assert.doesNotMatch(app, /2\.388|2\.701|0\.727|0\.71|1\.5571|2\.939/);
  assert.doesNotMatch(app, /Calculations\.(?:grossEmissions|netCarbonIndicator|scopeContributionPct)/);
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
    release: { version: 'sustainability-2026-09-v1', published_at: '2026-09-24T05:34:32Z', checksum_sha256: 'f'.repeat(64) },
    schema_version: '1.2', period: { id: 'p', year: 2026, month: 9 },
    publication_status: {},
    indicators: {
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
async function loadDashboardWith(payload) {
  const routes = { '/api/public/dashboard': payload, '/api/public/dashboard/history': [payload] };
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

test('month-bound scalar release blocks are hidden for unpublished months', () => {
  const app = read('app.js');
  assert.match(app, /function selectionHasPublication\(d, month\)/);
  assert.match(app, /published\[\+month\] === true/);
  assert.match(app, /const wasteHasData = hasPublication &&/);
  assert.match(app, /hasPublication \? d\.waterRecycledKL : null/);
  assert.match(app, /outreach\.month === \+month \+ 1/);
  assert.match(app, /outreachForPeriod \? outreach\.participantsServed : null/);
  assert.match(app, /No published operational release/);
});

test('Scope 1 and combined diesel are additive displays of published components, never official totals', async () => {
  const { data } = await loadDashboardWith(publishedPayload());
  const item = data['2026'], sep = 8;
  assert.equal(item.scope1Full[sep], 9.189255);
  assert.equal(item.dieselCombo[sep], 0.964257);
  // The official inventory indicators stay unavailable: nothing sums into them.
  assert.equal(item.totalGHG, null);
  assert.equal(item.avoided, null);
  assert.equal(item.reShare, null);
});

test('a missing component leaves Scope 1 missing instead of treating it as zero', async () => {
  const payload = publishedPayload();
  payload.lpg = { metrics: { lpg_consumption_litres: { value: 2, unit: 'L' } }, calculations: [] };
  const { data } = await loadDashboardWith(payload);
  const item = data['2026'], sep = 8;
  assert.equal(item.lpgEm[sep], null);
  assert.equal(item.scope1Full[sep], null);
  assert.equal(item.scope1Selected[sep], null);
  // Diesel does not depend on LPG, so it is still derived.
  assert.equal(item.dieselCombo[sep], 0.964257);
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
  assert.match(app, /const net = null;/);
  assert.match(app, /Methodology under review/);
  // Nothing in the page derives the official total from Scope 1 + Scope 2.
  assert.doesNotMatch(app, /Calculations\.(?:grossEmissions|netCarbonIndicator|scope1Total|scope2Total)/);
  assert.doesNotMatch(loader, /totalGHG\s*=\s*[^w]*(?:scope1|elecEm)/);
});

test('missing values are shown as unavailable and are never coerced to zero', () => {
  const app = read('app.js');
  assert.doesNotMatch(app, /const (?:dgVal|trDieselVal|petrolVal|lpgVal) = [^;]*\|\| 0/);
  assert.match(app, /c == null \? 'Unavailable' : c/);
  assert.match(app, /"\$\{c == null \? '' : c\}"/);
  assert.doesNotMatch(app, /const cleanZero = arr => arr\.map\(v => v === 0/);
  assert.match(app, /v == null \? null : v \+ \(re\[i\] == null \? 0 : re\[i\]\)/);
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

test('Data Explorer builds each source row on its own published value', () => {
  const app = read('app.js');
  assert.match(app, /if \(d\.elecKwh\[i\] != null\) rows\.push\(\[year, m, 'S2', 'Grid Electricity'/);
  assert.match(app, /tables\.electricity = \{ cols: \['Year', 'Month', 'Grid kWh'/);
});

test('active dashboard files hold no emission-factor formula or operational CSV authority', () => {
  for (const file of ['app.js', 'public-api.js', 'public-data-loader.js', 'calculations.js', 'walkthrough.js', 'mobile.js', 'weather.js']) {
    const source = read(file).replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
    assert.doesNotMatch(source, /2\.388|2\.701|0\.727|1\.5571|2\.939/, file);
    assert.doesNotMatch(source, /(?:transport|dg|lpg|energy|water|outreach|waste)_master\.csv/, file);
    assert.doesNotMatch(source, /dashboard_master/, file);
  }
  // Only static institutional files are still fetched by the loader.
  const fetched = [...read('public-data-loader.js').matchAll(/optionalText\('([^']+)'\)/g)].map(match => match[1]).sort();
  assert.deepEqual(fetched, ['data/dashboard_metadata.csv', 'data/green_master.csv', 'data/population_master.csv']);
});
