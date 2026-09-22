const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

async function loadFixtureData(overrides = {}) {
  const context = {
    console,
    window: {},
    fetch: async requestPath => {
      const relative = String(requestPath).split('?')[0];
      if (Object.hasOwn(overrides, relative)) {
        const value = overrides[relative];
        return { ok: true, status: 200, text: async () => String(value), json: async () => typeof value === 'string' ? JSON.parse(value) : value };
      }
      const absolute = path.join(root, relative);
      if (!fs.existsSync(absolute)) return { ok: false, status: 404 };
      return {
        ok: true,
        status: 200,
        text: async () => fs.readFileSync(absolute, 'utf8'),
        json: async () => JSON.parse(fs.readFileSync(absolute, 'utf8'))
      };
    }
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root, 'data-loader.js'), 'utf8'), context);
  return context.window.loadDashboardData();
}

test('uses the approved June overlay instead of stopping YTD at April', async () => {
  const { data } = await loadFixtureData();
  const y2026 = data['2026'];

  assert.deepEqual(Array.from(y2026.availableMonths), [0, 1, 2, 3, 5]);
  assert.deepEqual(Array.from(y2026.missingMonths), [4]);
  assert.equal(y2026.latestMonthIndex, 5);
  assert.equal(y2026.grossSelected[5], null);
  assert.deepEqual(Array.from(y2026.missingDomains[5]), ['dg']);
  assert.ok(Math.abs(y2026.totalGHG - 277.38981395) < 1e-9);
});

test('does not fabricate monthly renewable readings from a period total', async () => {
  const { data } = await loadFixtureData();

  assert.equal(data['2025'].reKwh[0], null);
  assert.equal(data['2025'].reEnergy, 3373368);
  assert.equal(data['2025'].reGranularity, 'period_total');
  assert.equal(data['2026'].reKwh[0], null);
  assert.equal(data['2026'].reKwh[5], 977);
  assert.equal(data['2026'].reEnergy, 325721);
  assert.equal(data['2026'].reGranularity, 'mixed');
});

test('keeps zero readings distinct from missing readings', async () => {
  const { data } = await loadFixtureData();

  assert.equal(data['2025'].tempKwh[0], 0);
  assert.equal(data['2026'].tempKwh[4], null);
  assert.equal(data['2026'].elecKwh[4], null);
  assert.equal(data['2026'].scope1Selected[5], null);
  assert.equal(data['2026'].grossSelected[5], null);
});

test('applies the configured factors to approved activity', async () => {
  const { data, EF } = await loadFixtureData();

  assert.equal(EF.petrol, 2.388);
  assert.equal(EF.diesel, 2.701);
  assert.equal(EF.grid, 0.727);
  assert.ok(Math.abs(data['2025'].totalGHG - 1753.79617177) < 1e-9);
  assert.ok(Math.abs(data['2026'].avoided - 236.799167) < 1e-9);
});

test('ignores overlay records that are not approved', async () => {
  const overlay = {
    data: {
      energy: [{ Year: 2026, Month: 'Jul', Industrial: 999999, Commercial: 1, Temporary: 1, Total_RE: 1, Status: 'Draft' }],
      transport: [{ Year: 2026, Month: 'Jul', Petrol_Litres: 999999, Diesel_Litres: 999999, Status: 'Rejected' }]
    }
  };
  const { data } = await loadFixtureData({ 'data/dashboard_master.json': overlay });

  assert.equal(data['2026'].htKwh[6], null);
  assert.equal(data['2026'].petrolL[6], null);
  assert.deepEqual(Array.from(data['2026'].availableMonths), [0, 1, 2, 3]);
});

test('does not double count monthly renewable data inside period-total coverage', async () => {
  const overlay = {
    data: {
      energy: [
        { Year: 2026, Month: 'Mar', Industrial: 53200, Commercial: 3200, Temporary: 0, Total_RE: 5000, Status: 'Approved' },
        { Year: 2026, Month: 'Jun', Industrial: 1250, Commercial: 3000, Temporary: 1300, Total_RE: 977, Status: 'Approved' }
      ],
      transport: []
    }
  };
  const { data } = await loadFixtureData({ 'data/dashboard_master.json': overlay });

  assert.equal(data['2026'].rePeriodStartIndex, 0);
  assert.equal(data['2026'].rePeriodEndIndex, 3);
  assert.equal(data['2026'].reEnergy, 324744 + 977);
});
