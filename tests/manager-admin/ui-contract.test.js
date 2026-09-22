const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

function loadSafeRatio() {
  const source = read('app.js').match(/function safeRatio\([^}]+\}/)?.[0];
  assert.ok(source, 'safeRatio implementation must exist');
  return vm.runInNewContext(`(${source})`);
}

test('ratios return unavailable for missing and zero denominators', () => {
  const safeRatio = loadSafeRatio();
  assert.equal(safeRatio(10, null, 100), null);
  assert.equal(safeRatio(10, 0, 100), null);
  assert.equal(safeRatio(null, 10, 100), null);
  assert.equal(safeRatio(0, 10, 100), 0);
  assert.equal(safeRatio(5, 10, 100), 50);
});

test('public copy does not claim avoided emissions cancel the inventory', () => {
  const copy = [read('app.js'), read('walkthrough.js'), read('index.html')].join('\n').toLowerCase();
  const forbidden = [
    'net removal',
    'honest, settled',
    'before offsets',
    'never had to burn coal',
    'purchased away',
    'accelerating the path to net-zero',
    'scope 2 offset',
    'net carbon impact',
    'true environmental footprint'
  ];
  forbidden.forEach((phrase) => assert.equal(copy.includes(phrase), false, phrase));
  assert.match(copy, /does not cancel.*inventory|does not reduce.*inventory/);
});

test('missing KPI and gauge evidence stays unavailable', () => {
  const app = read('app.js');
  assert.match(app, /hsAdmin\.textContent\s*=\s*elec\s*==\s*null\s*\?\s*['"]N\/A['"]/);
  assert.match(app, /reGauge[\s\S]*?reShareVal\s*==\s*null\s*\?\s*\[null,null\]/);
  assert.doesNotMatch(app, /Scope 2 offset/);
});

test('chart and explorer code retain the selected period contract', () => {
  const app = read('app.js');
  assert.match(app, /chartIndexes\s*=\s*month\s*===\s*['"]all['"]/);
  assert.match(app, /prior\s*=\s*data\[year\s*-\s*1\]/);
  assert.match(app, /d\.reKwh\.forEach/);
  assert.match(app, /filteredTableRows\(t\)/);
  assert.match(app, /exportBtn[\s\S]*?filteredTableRows\(t\)/);
});
