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
