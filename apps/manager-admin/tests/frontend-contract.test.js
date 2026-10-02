const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');

const loginContracts = {
  'admin-login.html': { role: 'microcosm_admin', destination: 'admin-overview.html' },
  'transport-login.html': { role: 'manager', domain: 'transport', destination: 'transport-entry.html' },
  'energy-login.html': { role: 'manager', domain: 'energy', destination: 'energy-entry.html' },
  'lpg-login.html': { role: 'manager', domain: 'lpg', destination: 'lpg-entry.html' },
  'water-login.html': { role: 'manager', domain: 'water', destination: 'water-entry.html' },
  'outreach-login.html': { role: 'manager', domain: 'outreach', destination: 'community-outreach-entry.html' },
  'waste-login.html': { role: 'manager', domain: 'waste', destination: 'waste-entry.html' }
};

const managerContracts = {

  'transport-entry.html': ['transport', 'petrol', 'diesel-transport', 'active-vehicles-petrol', 'active-vehicles-diesel', 'ev-consumption', 'dg-generation', 'active-dg'],
  'energy-entry.html': ['energy', 'grid-ht', 'grid-comm', 'grid-temp', 'ren-campus', 'ren-procured', 'ren-solar', 'grid-total', 'ren-total'],
  'lpg-entry.html': ['lpg', 'lpg-kg', 'lpg-cylinders'],
  'water-entry.html': ['water', 'water-twad', 'water-borewell', 'water-priv', 'water-waste', 'water-recycled', 'water-consumed'],
  'waste-entry.html': ['waste', 'wet-waste']
};
const evidenceInputs = {
  'transport-entry.html': ['evidence-petrol', 'evidence-diesel', 'evidence-dg'],
  'energy-entry.html': ['evidence-energy'],
  'lpg-entry.html': ['evidence-lpg'],
  'water-entry.html': ['evidence-water'],
  'community-outreach-entry.html': ['evidence-file'],
  'waste-entry.html': ['evidence-waste']
};

const adminPages = ['admin-overview.html', 'admin-queue.html', 'admin-evidence.html', 'admin-preview.html', 'admin-factors.html', 'admin-users.html', 'admin-audit.html'];
const activePages = [
  'index.html', 'change-password.html', ...Object.keys(loginContracts), ...Object.keys(managerContracts),
  'community-outreach-entry.html', 'manager-home.html', 'submission-history.html', 'outreach-history.html',
  ...adminPages
];

function hasAttribute(html, name, value) {
  return new RegExp(`${name}=["']${value}["']`).test(html);
}

function hasId(html, id) {
  return new RegExp(`id=["']${id}["']`).test(html);
}

test('all active pages and their local resources exist', () => {
  for (const file of activePages) {
    const html = read(file);
    const references = [...html.matchAll(/(?:src|href)=["']([^"']+)["']/g)].map(match => match[1]);
    for (const reference of references) {
      if (/^(?:#|https?:|mailto:|javascript:|data:)/.test(reference) || reference.includes('${')) continue;
      const local = reference.split(/[?#]/, 1)[0];
      assert.ok(fs.existsSync(path.join(root, local)), `${file} references missing ${local}`);
    }
  }
});

test('all active inline scripts parse as JavaScript', () => {
  for (const file of activePages) {
    const html = read(file);
    const scripts = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)];
    for (const [, source] of scripts) {
      assert.doesNotThrow(() => new Function(source), `${file} contains invalid inline JavaScript`); // eslint-disable-line no-new-func
    }
  }
});

test('role login pages have the complete unprotected login contract', () => {
  for (const [file, contract] of Object.entries(loginContracts)) {
    const html = read(file);
    assert.equal(html.includes('data-auth-role'), false, `${file} must not be protected-page hidden`);
    assert.ok(hasAttribute(html, 'data-login-role', contract.role));
    if (contract.domain) assert.ok(hasAttribute(html, 'data-login-domain', contract.domain));
    assert.ok(hasAttribute(html, 'data-destination', contract.destination));
    for (const id of ['login-form', 'login-username', 'login-password', 'login-message']) assert.ok(hasId(html, id), `${file}: ${id}`);
    for (const script of ['auth-client.js', 'role-auth.js', 'role-login.js']) assert.ok(html.includes(`src="${script}"`), `${file}: ${script}`);
  }
});

test('generic manager pages have guards, integration scripts, controls, and mapped fields', () => {
  for (const [file, [domain, ...ids]] of Object.entries(managerContracts)) {
    const html = read(file);
    assert.ok(hasAttribute(html, 'data-auth-role', 'manager'));
    assert.ok(hasAttribute(html, 'data-auth-domain', domain));
    for (const script of ['auth-client.js', 'role-auth.js', 'manager-submissions-api.js']) assert.ok(html.includes(`src="${script}"`), `${file}: ${script}`);
    for (const id of ['entry-form', 'reporting-period-label', 'year', 'month', 'save-draft-btn', 'submit-btn', 'reset-btn', ...ids]) assert.ok(hasId(html, id), `${file}: ${id}`);
    assert.match(html, /id="reporting-period-label"[^>]*readonly/);
    assert.doesNotMatch(html, /<select[^>]+id="(?:year|month)"/);
  }
});

test('outreach and history pages retain their backend integrations', () => {
  const outreach = read('community-outreach-entry.html');
  for (const script of ['auth-client.js', 'role-auth.js', 'app.js', 'outreach-api.js', 'outreach-integration.js']) assert.ok(outreach.includes(`src="${script}"`));
  for (const id of ['outreach-entry-form', 'reporting-year', 'reporting-month', 'save-draft-btn', 'submit-review-btn', 'modal-confirm-btn']) assert.ok(hasId(outreach, id));
  assert.match(outreach, /id="reporting-period-label"[^>]*readonly/);
  assert.doesNotMatch(outreach, /<select[^>]+id="reporting-(?:year|month)"/);
  assert.ok(read('submission-history.html').includes('src="manager-history.js"'));
});

test('admin pages are protected and review queue loads the real API helpers', () => {
  for (const file of adminPages) {
    const html = read(file);
    assert.ok(hasAttribute(html, 'data-auth-role', 'microcosm_admin'), file);
    assert.ok(hasAttribute(html, 'data-login-page', 'admin-login.html'), file);
  }
  const queue = read('admin-queue.html');
  for (const script of ['auth-client.js', 'role-auth.js', 'outreach-api.js', 'evidence-api.js']) assert.ok(queue.includes(`src="${script}"`));
  for (const domain of ['transport', 'energy', 'lpg', 'water', 'outreach']) assert.ok(queue.includes(`'${domain}'`));
  assert.ok(hasId(queue, 'modal-evidence-container'));
  assert.match(queue, /Current revision/);
  assert.match(queue, /Previous submitted revision/);
  assert.match(queue, /\/api\/admin\/reporting-periods\/\$\{encodeURIComponent\(periodId\)\}\/publication-readiness/);
  assert.match(queue, /id="prepare-release" disabled/);
  assert.match(queue, /approved_domains/);
  assert.match(queue, /ready_to_publish/);
  for (const domain of ['transport', 'energy', 'lpg', 'water', 'outreach']) {
    assert.ok(hasId(queue, `readiness-${domain}`));
  }
  assert.doesNotMatch(queue, /localStorage|sessionStorage/);
  for (const file of adminPages) assert.match(read(file), /href="admin-evidence\.html"/);
  for (const file of adminPages) assert.match(read(file), /href="admin-users\.html"/);
});

test('admin access and audit pages use protected backend APIs', () => {
  const usersHtml = read('admin-users.html');
  const users = read('admin-users.js');
  const auditHtml = read('admin-audit.html');
  const audit = read('admin-audit.js');
  for (const id of ['create-manager-form', 'new-username', 'new-domain', 'new-password', 'users-table-body']) {
    assert.ok(hasId(usersHtml, id), id);
  }
  assert.match(users, /\/api\/admin\/users/);
  assert.match(users, /csrf: write/);
  assert.match(users, /reset-password/);
  assert.match(users, /revoke-sessions/);
  assert.match(audit, /\/api\/admin\/audit-logs\?/);
  assert.ok(hasId(auditHtml, 'audit-filter-form'));
  assert.doesNotMatch(`${usersHtml}\n${users}\n${auditHtml}\n${audit}`, /localStorage|sessionStorage/);
});

test('admin evidence repository is filtered, read-only, and uses secure content routes', () => {
  const html = read('admin-evidence.html');
  const script = read('admin-evidence.js');
  for (const id of [
    'evidence-filters', 'filter-year', 'filter-month', 'filter-domain', 'filter-status',
    'filter-submission', 'filter-revision', 'filter-metric', 'filter-category', 'filter-filename', 'filter-scope',
    'evidence-repository-results', 'previous-evidence-page', 'next-evidence-page'
  ]) assert.ok(hasId(html, id), id);
  for (const source of ['auth-client.js', 'role-auth.js', 'evidence-api.js', 'admin-evidence.js']) {
    assert.ok(html.includes(`src="${source}"`), source);
  }
  assert.match(script, /\/api\/admin\/evidence\?/);
  assert.match(script, /KCosmosEvidence\.contentUrl\('admin'/);
  assert.match(script, />View</);
  assert.match(script, />Download</);
  assert.match(script, /history\.replaceState/);
  assert.doesNotMatch(`${html}\n${script}`, /localStorage|sessionStorage|file:\/\/|\/data\/evidence|private-evidence/i);
  assert.doesNotMatch(script, /method\s*:\s*['"](?:POST|PUT|PATCH|DELETE)['"]/i);
  assert.doesNotMatch(html, /<button[^>]*>\s*(?:Delete|Replace|Upload|Rename)\s*<\/button>/i);
});

test('admin review queue selection drives the backend reporting period filter', () => {
  const html = read('admin-queue.html');
  assert.ok(hasId(html, 'queue-period'));
  assert.match(html, /reporting_period_id=\$\{encodeURIComponent\(periodId\)\}/);
  assert.match(html, /parameters\.set\('period', event\.target\.value\)/);
  assert.match(html, /timeZone:'Asia\/Kolkata'/);
});

test('emission factor governance uses backend data and authoritative calculation responses', () => {
  const html = read('admin-factors.html');
  const factors = read('admin-factors.js');
  const calculations = read('calculation-preview.js');
  assert.ok(html.includes('src="outreach-api.js"'));
  assert.ok(html.includes('src="admin-factors.js"'));
  assert.ok(html.indexOf('src="outreach-api.js"') < html.indexOf('src="admin-factors.js"'));
  assert.match(factors, /\/api\/admin\/emission-factor-sets/);
  assert.match(factors, /csrf:\s*true/);
  assert.match(factors, /window\.confirm/);
  assert.match(factors, /item\.status === 'draft'/);
  assert.doesNotMatch(`${html}\n${factors}`, /localStorage|sessionStorage|2\.388|2\.701|0\.727|1\.5571/);
  assert.doesNotMatch(`${read('transport-entry.html')}\n${read('energy-entry.html')}`, /2\.388|2\.701|0\.727/);
  assert.match(calculations, /submission\?\.calculations/);
  assert.match(calculations, /factor_not_configured|Unavailable/);
  // Electrical avoided emissions are the backend's governed result (renewable
  // electricity x grid factor), printed by the single preview renderer - never
  // a placeholder and never duplicated into the entry page.
  assert.match(calculations, /set\('prev-avoided', show\(energy\?\.estimated_avoided_grid_emissions_tco2e, 6\)\)/);
  assert.doesNotMatch(calculations, /Methodology review required/);
  // LPG is governed on weight as LPG_KG (0013_lpg_kg_governance_v2); the
  // retired litre code is never offered for a new or edited factor set.
  assert.match(factors, /code: 'LPG_KG'[^}]*unit: 'kg'/);
  assert.doesNotMatch(factors, /code: 'LPG'[,\s]/);
  assert.doesNotMatch(factors, /unit: 'L', optional/);
  // A retired set's legacy factor is shown read-only and never written back.
  assert.match(factors, /function legacyRows\(factors\)/);
  assert.match(factors, /const factors = definitions\.flatMap/);
  const lpgPage = read('lpg-entry.html');
  const submissions = read('manager-submissions-api.js');
  // lpg_weight_kg is the governed, required activity; litres are not collected.
  assert.match(submissions, /'lpg-kg': 'lpg_weight_kg'/);
  assert.doesNotMatch(submissions, /lpg_consumption_litres|'lpg-litres'/);
  assert.match(lpgPage, /<label class="form-label" for="lpg-kg">LPG Consumption \(kg\)<\/label>/);
  assert.match(lpgPage, /id="lpg-kg" min="0" step="0.01" required/);
  assert.doesNotMatch(lpgPage, /id="lpg-litres"|LPG Consumption \(litres\)/);
  // The cylinder count stays optional reference metadata, and the browser
  // never derives kg from cylinders (the backend freezes the entered kg).
  assert.match(lpgPage, /No\. of Cylinders Used[\s\S]{0,200}optional, reference/);
  assert.doesNotMatch(lpgPage, /cylinders?[^\n]*\*\s*19|\*\s*cylinder/i);
  assert.match(lpgPage, /toFixed\(2\) \+ ' kg'/);
  assert.match(calculations, /kgCO2e\/kg/);
  assert.doesNotMatch(calculations, /kgCO2e\/L/);
});

test('waste manager page is governed, catalog-driven and backend-authoritative', () => {
  const page = read('waste-entry.html');
  const inventory = read('waste-inventory.js');
  const submissions = read('manager-submissions-api.js');

  // Same portal shell and evidence component as the other domains.
  assert.match(page, /data-auth-role="manager"/);
  assert.match(page, /data-auth-domain="waste"/);
  assert.match(page, /data-login-page="waste-login.html"/);
  assert.ok(hasId(page, 'wet-waste'));
  assert.ok(hasId(page, 'evidence-waste'));
  assert.match(page, /data-evidence-input/);
  assert.match(page, /src="evidence-manager.js"/);
  // The topbar mirrors the server-authoritative reporting month, so the
  // monthly nature of the page cannot be mistaken for an annual form.
  assert.ok(hasId(page, 'topbar-period'));
  assert.match(page, /kcosmos:submission-loaded[\s\S]{0,300}topbar-period/);

  // The module's domain guard must include 'waste', or the entire shared
  // workflow (current-period fetch, Save/Submit wiring, evidence context)
  // silently no-ops for this domain - the bug this test was added to catch.
  assert.match(
    submissions,
    /if \(!\[[^\]]*'waste'[^\]]*\]\.includes\(domain\)\) return;/,
    "manager-submissions-api.js's top-level domain guard must include 'waste'"
  );

  // Only wet waste is manager-entered; derived totals are never sent.
  assert.match(submissions, /'wet-waste': 'wet_waste_generated_kg'/);
  assert.doesNotMatch(submissions, /'dry_waste_generated_kg'|'total_waste_generated_kg'/);
  assert.match(submissions, /body\.waste_items = window\.KCosmosWasteInventory\.items\(\)/);

  // The catalog comes from the backend, never hardcoded in the browser.
  assert.match(inventory, /\/api\/manager\/waste\/catalog/);
  assert.doesNotMatch(inventory, /PAPER_CARDBOARD|COLOUR_PAPER|MIXED_PLASTICS|STAINLESS_STEEL/);
  // Cascading material list filtered by the selected category.
  assert.match(inventory, /item\.category_code === categoryCode/);
  // Duplicates are refused with a clear message, not silently added.
  assert.match(inventory, /has already been added\. Edit the existing quantity instead/);
  // Client arithmetic is never stored: the server's saved items replace the buffer.
  assert.match(inventory, /kcosmos:submission-loaded/);
  assert.match(inventory, /applyServerItems/);
});

test('calculation-preview.js is the only writer of governed emission preview nodes', () => {
  const calculations = read('calculation-preview.js');
  // The renderer labels every figure with the backend's own result unit and
  // never rescales a component to fit a hardcoded label.
  assert.match(calculations, /item\.result_unit/);
  assert.doesNotMatch(calculations, /toFixed\(2\)\}\s*kgCO2e/);

  // Entry pages may echo typed activity, but must never write the nodes that
  // hold a governed server result.
  const owned = ['prev-scope2', 'prev-avoided', 'prev-emission', 'prev-factor', 'prev-total', 'prev-petrol', 'prev-diesel-t', 'prev-diesel-dg',
    'prev-re-electricity', 'prev-total-electricity', 'prev-re-share', 'prev-solar-thermal'];
  for (const page of ['transport-entry.html', 'energy-entry.html', 'lpg-entry.html']) {
    const source = read(page);
    const inline = source.slice(source.indexOf('<script>'));
    for (const id of owned) {
      // The page must not even resolve these nodes: holding a reference is the
      // first step back to overwriting a governed value.
      assert.doesNotMatch(
        inline,
        new RegExp(`getElementById\\(['"]${id}['"]\\)`),
        `${page} must not reference ${id}`
      );
    }
    // Staleness is signalled without destroying the last governed result.
    assert.match(source, /KCosmosPreview\?\.markStale\(\)/, `${page} must flag staleness`);
    assert.ok(hasId(source, 'prev-stale'), `${page}: prev-stale`);
  }
  assert.match(calculations, /window\.KCosmosPreview\s*=/);
});

test('all manager evidence controls use the shared private evidence integration', () => {
  for (const [file, ids] of Object.entries(evidenceInputs)) {
    const html = read(file);
    for (const id of ids) assert.ok(hasId(html, id), `${file}: ${id}`);
    for (const script of ['evidence-api.js', 'evidence-manager.js']) {
      assert.ok(html.includes(`src="${script}"`), `${file}: ${script}`);
    }
    assert.match(html, /data-evidence-input/);
    assert.match(html, /data-evidence-container/);
  }
  assert.ok(fs.existsSync(path.join(root, 'evidence-api.js')));
  assert.ok(fs.existsSync(path.join(root, 'evidence-manager.js')));
});

test('shared API treats a successful 204 response as bodyless', async () => {
  let jsonCalls = 0;
  let fetchOptions = null;
  class TestFormData {}
  const context = {
    console,
    document: { cookie: '' },
    FormData: TestFormData,
    window: {
      location: { port: '3000', protocol: 'http:', hostname: '127.0.0.1' }
    },
    fetch: async (_url, options) => {
      fetchOptions = options;
      return {
        status: 204,
        ok: true,
        headers: { get: () => null },
        json: async () => {
          jsonCalls += 1;
          throw new Error('204 must not be parsed');
        }
      };
    }
  };
  vm.createContext(context);
  vm.runInContext(read('auth-client.js'), context);
  const result = await context.apiRequest('/api/test-delete', { method: 'DELETE' });
  assert.equal(result, null);
  assert.equal(jsonCalls, 0);
  assert.equal(fetchOptions.credentials, 'include');
});

test('shared API accepts 201 and safely formats FastAPI 422 errors', async () => {
  class TestFormData {}
  const responses = [
    {
      status: 201,
      ok: true,
      headers: { get: () => 'create-request' },
      json: async () => ({ id: 'submission-id', status: 'draft' })
    },
    {
      status: 422,
      ok: false,
      headers: { get: name => name === 'X-Request-ID' ? 'validation-request' : null },
      json: async () => ({ detail: [{ loc: ['body', 'values', 0, 'value'], msg: 'Input should be numeric' }] })
    }
  ];
  const context = {
    console,
    document: { cookie: '' },
    FormData: TestFormData,
    window: { location: { port: '3000', protocol: 'http:', hostname: '127.0.0.1' } },
    fetch: async () => responses.shift()
  };
  vm.createContext(context);
  vm.runInContext(read('auth-client.js'), context);
  assert.deepEqual(
    JSON.parse(JSON.stringify(await context.apiRequest('/create', { method: 'POST' }))),
    { id: 'submission-id', status: 'draft' }
  );
  await assert.rejects(
    () => context.apiRequest('/invalid', { method: 'POST' }),
    error => error.message === 'values.0.value: Input should be numeric'
      && error.status === 422
      && error.requestId === 'validation-request'
  );
});

test('portal-owned toast replaces a denied browser global and never throws', () => {
  const denied = () => { throw new Error('showToast denied'); };
  const context = {
    console,
    document: {
      body: { appendChild() {} },
      addEventListener() {},
      createElement: () => ({ appendChild() {}, className: '', id: '', remove() {}, style: {}, textContent: '' }),
      getElementById: () => null,
      querySelectorAll: () => []
    },
    window: {
      location: { pathname: '/transport-entry.html' },
      setTimeout() {},
      showToast: denied
    }
  };
  vm.createContext(context);
  vm.runInContext(read('app.js'), context);
  assert.notEqual(context.window.showToast, denied);
  assert.doesNotThrow(() => context.window.KCosmosUI.notify('Draft saved.', 'success', { operation: 'Save Draft' }));
});

test('shared evidence API generates manager endpoints with CSRF-protected mutations', async () => {
  const calls = [];
  class TestFormData {
    append() {}
  }
  const context = {
    FormData: TestFormData,
    apiRequest: async (pathValue, options) => {
      calls.push({ path: pathValue, options });
      return [];
    },
    window: { KCOSMOS_API_URL: value => value }
  };
  vm.createContext(context);
  vm.runInContext(read('evidence-api.js'), context);
  await context.window.KCosmosEvidence.listManager('transport', 'submission id');
  await context.window.KCosmosEvidence.removeManager('transport', 'submission id', 'evidence id');
  await context.window.KCosmosEvidence.uploadManager(
    'transport', 'submission id', {}, { metricCode: 'transport_diesel_litres' }
  );
  assert.equal(
    calls[0].path,
    '/api/manager/transport/submissions/submission%20id/evidence'
  );
  assert.equal(calls[0].options.csrf, false);
  assert.equal(
    calls[1].path,
    '/api/manager/transport/submissions/submission%20id/evidence/evidence%20id'
  );
  assert.equal(calls[1].options.method, 'DELETE');
  assert.equal(calls[1].options.csrf, true);
  assert.equal(calls[2].options.method, 'POST');
  assert.equal(calls[2].options.csrf, true);
});

test('shared evidence lifecycle resets file input and uses non-submit mutation buttons', () => {
  const manager = read('evidence-manager.js');
  assert.match(manager, /function resetInput\(input\)[\s\S]*?input\.value = ''/);
  assert.match(manager, /finally \{[\s\S]*?resetInput\(input\);[\s\S]*?setBusy\(input, false\)/);
  assert.match(manager, /<button type="button"[^>]*evidence-replace/);
  assert.match(manager, /<button type="button"[^>]*evidence-remove/);
  assert.match(manager, /lifecycle_state/);
  assert.match(manager, /Current Correction Evidence/);
  assert.match(manager, /Previously Submitted Evidence/);
  assert.doesNotMatch(manager, /Evidence history/);
  assert.doesNotMatch(`${read('evidence-api.js')}\n${manager}`, /localStorage|sessionStorage/);
});

test('generic Manager save and submit wiring is single-owner and persistence-safe', () => {
  const manager = read('manager-submissions-api.js');
  for (const file of Object.keys(managerContracts)) {
    const html = read(file);
    assert.match(html, /<button type="button"[^>]*id="save-draft-btn"/);
    assert.match(html, /<button type="button"[^>]*id="submit-btn"/);
    assert.doesNotMatch(html, /addEventListener\(['"]submit['"]/);
  }
  assert.equal((manager.match(/replaceButton\('save-draft-btn'/g) || []).length, 1);
  assert.equal((manager.match(/replaceButton\('submit-btn'/g) || []).length, 1);
  assert.match(manager, /input\.value\.trim\(\) === '' \? null : input\.value/);
  assert.match(manager, /byCode\.get\(metricCode\) \?\? ''/);
  assert.match(manager, /request\('\/current-period'\)/);
  assert.match(manager, /expected_row_version = currentSubmission\.row_version/);
  assert.match(manager, /stale_submission/);
  assert.match(manager, /Refresh submission/);
  assert.doesNotMatch(manager, /new Date|searchParams\.set\('reporting_period_id'/);
  const submit = manager.slice(manager.indexOf('async function submitForReview'));
  assert.ok(submit.indexOf("/submit`, { method: 'POST' }") < submit.indexOf('await loadCurrent()'));
  assert.ok(submit.indexOf('await loadCurrent()') < submit.indexOf("showSuccess('Submitted for review.'"));
  assert.doesNotMatch(read('evidence-manager.js'), /currentSubmission\s*=/);
});

test('Outreach save/submit restores by programme URL and uses the safe notifier', () => {
  const outreach = read('outreach-integration.js');
  assert.match(outreach, /searchParams\.set\('programme', programmeId\)/);
  assert.match(outreach, /ensureDraft: async \(\) => \{/);
  assert.match(outreach, /KCosmosUI\?\.notify/);
  assert.match(outreach, /\/api\/manager\/outreach\/current-period/);
  assert.match(outreach, /expected_row_version = currentRowVersion/);
  assert.match(outreach, /stale_submission/);
  assert.match(outreach, /Refresh submission/);
  assert.doesNotMatch(outreach, /parseInt|parseFloat/);
  assert.doesNotMatch(outreach, /new Date/);
  assert.match(outreach, /await KCosmos\.api\(`\/api\/manager\/outreach\/programmes\/\$\{currentProgrammeId\}`\)/);
});

test('reloaded values re-trigger the page calculators on every domain', () => {
  // Page-level calculators (participant/species totals, energy and water
  // sums) listen for `input` on each field. An event dispatched on the form
  // bubbles UP and never reaches those children, which left read-only totals
  // showing 0 after a reload even though the fields held values.
  const outreach = read('outreach-integration.js');
  assert.match(outreach, /form\.querySelectorAll\('input, select, textarea'\)/);
  assert.doesNotMatch(outreach, /^\s*form\.dispatchEvent\(new Event\('input'/m);

  const generic = read('manager-submissions-api.js');
  assert.match(generic, /querySelectorAll\('#entry-form input'\)\.forEach\(input => input\.dispatchEvent/);
});

test('evidence failures report the actual reason, not a bare failure', () => {
  const evidence = read('evidence-manager.js');
  // A draft-not-saved problem must not look identical to a rejected file.
  assert.match(evidence, /status === 404/);
  assert.match(evidence, /Save the draft before adding evidence/);
  assert.match(evidence, /status === 413/);
  assert.match(evidence, /status === 401/);
  assert.match(evidence, /requestId/);
  // Still no internals leaked.
  assert.doesNotMatch(evidence, /error\.stack|Traceback|storage_key/);
});

test('every submission context exposes the SUBMISSION id, which evidence upload requires', () => {
  // evidence-manager.js posts to /submissions/{submission.id}/evidence, so a
  // context whose `id` is anything else (outreach returns a programme from
  // saveDraft, carrying a different id) makes evidence upload 404.
  const evidence = read('evidence-manager.js');
  assert.match(evidence, /const submission = await context\(\)\?\.ensureDraft\(\)/);
  assert.match(evidence, /uploadManager\(domain, submission\.id/);
  assert.match(evidence, /listManager\(domain, submission\.id\)/);
  assert.match(evidence, /removeManager\(domain, submission\.id, evidenceId\)/);

  // Execute the real outreach context block with stubbed module state.
  const outreach = read('outreach-integration.js');
  const block = outreach.match(/const submissionRef = [\s\S]*?\n  \};/);
  assert.ok(block, 'outreach must define its submission context');

  const SUBMISSION_ID = 'submission-uuid';
  const PROGRAMME_ID = 'programme-uuid';
  let savedCalled = false;
  const context = vm.runInNewContext(
    `let currentSubmissionId = ${JSON.stringify(SUBMISSION_ID)};
     let currentStatus = 'draft';
     const saveDraft = async () => { savedCalled(); return { id: ${JSON.stringify(PROGRAMME_ID)}, submission_id: ${JSON.stringify(SUBMISSION_ID)} }; };
     const window = {};
     ${block[0]}
     window.KCosmosSubmissionContext;`,
    { savedCalled: () => { savedCalled = true; } }
  );

  assert.equal(context.domain, 'outreach');
  assert.equal(context.getSubmission().id, SUBMISSION_ID);
  return context.ensureDraft().then(result => {
    assert.ok(savedCalled, 'ensureDraft must still persist the draft');
    assert.equal(result.id, SUBMISSION_ID, 'ensureDraft must return the submission id');
    assert.notEqual(result.id, PROGRAMME_ID, 'ensureDraft must not return the programme id');
    assert.equal(result.status, 'draft');
  });
});

test('active frontend contains no private filesystem evidence URL', () => {
  const sources = [...activePages, 'evidence-api.js', 'evidence-manager.js', 'admin-evidence.js'].map(read).join('\n');
  assert.doesNotMatch(sources, /(?:[A-Z]:\\|\/app\/|\/data\/evidence|private-evidence)/i);
});

test('active code has no browser-storage authentication or submission persistence', () => {
  const activeScripts = ['app.js', 'auth-client.js', 'role-auth.js', 'role-login.js', 'manager-submissions-api.js', 'manager-history.js', 'outreach-api.js', 'outreach-integration.js', 'evidence-api.js', 'evidence-manager.js', 'admin-evidence.js', 'admin-overview-api.js', 'admin-users.js', 'admin-audit.js'];
  const sources = [...activePages, ...activeScripts].map(read).join('\n');
  assert.doesNotMatch(sources, /localStorage\.(?:getItem|setItem|removeItem)\(["'](?:currentUser|submissions)["']|sessionStorage\.(?:getItem|setItem|removeItem|clear)/);
  assert.doesNotMatch(sources, /transport-login\.broken-backup|broken-login-backup/);
});

// --- Release candidate rehydration --------------------------------------
// Runs the real inline script of admin-queue.html against a minimal DOM and a
// stubbed backend, simulating a fresh page load (i.e. a refresh or
// back-navigation: nothing survives in memory, only the database does).

const PERIOD_ID = 'f0810f03-bb61-4ac9-a803-395c5ffca4b6';
const RELEASE_ID = 'b5579654-50c1-47da-9e91-a2ae8aaa0cb6';
const REQUEST_ID = '11111111-2222-3333-4444-555555555555';
const CANDIDATE = {
  id: RELEASE_ID, version: 'sustainability-2026-09-v1', status: 'candidate',
  checksum_sha256: 'f'.repeat(64), reporting_period_id: PERIOD_ID,
  created_at: '2026-09-23T14:02:18Z', published_at: null
};
const READY = {
  reporting_period: { label: 'September 2026' }, approved_domains: 6, required_domains: 6,
  ready_to_publish: true, blockers: [],
  domains: Object.fromEntries(['transport', 'energy', 'lpg', 'water', 'outreach', 'waste'].map(d => [d, { status: 'approved', revision_number: 1 }]))
};

function fakeElement(id) {
  const listeners = {};
  return {
    id, textContent: '', innerHTML: '', value: '', className: '', disabled: false,
    dataset: {}, style: {}, classList: { add() {}, remove() {} },
    addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
    async fire(type, event = {}) { for (const fn of listeners[type] || []) await fn({ target: this, ...event }); }
  };
}

async function loadAdminQueue({ releases, prepare }) {
  const html = read('admin-queue.html');
  const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
  const elements = new Map();
  for (const [, id] of html.matchAll(/id="([^"]+)"/g)) elements.set(id, fakeElement(id));
  elements.get('prepare-release').disabled = true;
  elements.get('open-release').disabled = true;
  const calls = [];
  let ready;
  const document = {
    getElementById: id => elements.get(id) || null,
    querySelectorAll: () => [],
    addEventListener: (type, fn) => { if (type === 'DOMContentLoaded') ready = fn; }
  };
  const window = { location: { search: '', pathname: '/admin-queue.html', href: 'admin-queue.html' } };
  const api = async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET' });
    if (url === '/api/admin/periods') return [{ id: PERIOD_ID, year: 2026, month: 9, label: 'September 2026' }];
    if (url.startsWith('/api/admin/review-queue')) return [];
    if (url.includes('/publication-readiness')) return READY;
    if (url === `/api/admin/releases?reporting_period_id=${PERIOD_ID}`) return releases();
    if (url === '/api/admin/releases/prepare') return prepare();
    throw new Error(`unexpected request ${url}`);
  };
  vm.runInNewContext(inline, {
    document, window, history: { replaceState() {} }, URLSearchParams, Intl, Date, JSON, Map, Set, Promise, String, Number, Array, Object, Math,
    console: { error() {} }, KCosmos: { requireRole: async () => {}, api },
    showToast: () => {}
  });
  await ready();
  return { el: id => elements.get(id), calls, window };
}

test('a prepared candidate is rediscovered from the backend on a fresh page load', async () => {
  const page = await loadAdminQueue({ releases: () => [CANDIDATE], prepare: () => { throw new Error('must not prepare'); } });
  assert.ok(page.calls.some(c => c.url === `/api/admin/releases?reporting_period_id=${PERIOD_ID}`));
  assert.equal(page.el('release-state-version').textContent, 'sustainability-2026-09-v1');
  assert.equal(page.el('release-state-badge').textContent, 'CANDIDATE');
  assert.equal(page.el('prepare-release').disabled, true, 'Prepare must be disabled while a candidate waits');
  assert.equal(page.el('open-release').disabled, false, 'Open release preview must be enabled');
  await page.el('open-release').fire('click');
  assert.equal(page.window.location.href, `admin-preview.html?release_id=${RELEASE_ID}`);
  assert.ok(!page.calls.some(c => c.method === 'POST'), 'loading the page must never prepare a release');
});

test('an active release shows as published and its version is not offered again', async () => {
  const active = { ...CANDIDATE, status: 'active', published_at: '2026-09-24T09:00:00Z' };
  const page = await loadAdminQueue({ releases: () => [active], prepare: () => { throw new Error('must not prepare'); } });
  assert.equal(page.el('release-state-badge').textContent, 'ACTIVE / PUBLISHED');
  assert.equal(page.el('release-version').value, 'sustainability-2026-09-v1');
  assert.equal(page.el('prepare-release').disabled, true, 'the published version must not be prepared again');
  page.el('release-version').value = 'sustainability-2026-09-v2';
  await page.el('release-version').fire('input');
  assert.equal(page.el('prepare-release').disabled, false, 'a new version stays possible for a later correction');
});

test('a duplicate Prepare recovers the existing candidate instead of dead-ending', async () => {
  // The list is empty at first (a stale view); then the backend reports the
  // version exists. The page must rediscover it, not show a bare error.
  let listed = [];
  const page = await loadAdminQueue({
    releases: () => listed,
    prepare: () => {
      listed = [CANDIDATE];
      throw Object.assign(new Error('Release version already exists.'), { status: 409, code: 'http_error', requestId: REQUEST_ID });
    }
  });
  assert.equal(page.el('prepare-release').disabled, false);
  await page.el('prepare-release').fire('click');
  assert.equal(page.calls.filter(c => c.url === '/api/admin/releases/prepare').length, 1);
  assert.match(page.el('release-state-message').textContent, /^Candidate already prepared\./);
  assert.equal(page.el('release-error').textContent, '', 'no red dead-end error');
  assert.equal(page.el('release-state-badge').textContent, 'CANDIDATE');
  assert.equal(page.el('prepare-release').disabled, true);
  await page.el('open-release').fire('click');
  assert.equal(page.window.location.href, `admin-preview.html?release_id=${RELEASE_ID}`);
  assert.doesNotMatch(page.window.location.href, new RegExp(REQUEST_ID), 'a request id is never a release id');
});

test('a request reference is labelled as diagnostic and never opens a preview', async () => {
  const page = await loadAdminQueue({
    releases: () => [],
    prepare: () => { throw Object.assign(new Error('Server error'), { status: 500, requestId: REQUEST_ID }); }
  });
  await page.el('prepare-release').fire('click');
  assert.match(page.el('release-error').textContent, new RegExp(`Request reference: ${REQUEST_ID}`));
  assert.equal(page.el('open-release').disabled, true);
  await page.el('open-release').fire('click');
  assert.equal(page.window.location.href, 'admin-queue.html', 'no navigation without a real release id');
});

test('release rehydration reads the backend, never browser storage', () => {
  const html = read('admin-queue.html');
  assert.match(html, /\/api\/admin\/releases\?reporting_period_id=\$\{encodeURIComponent\(periodId\)\}/);
  assert.doesNotMatch(html, /localStorage|sessionStorage|indexedDB/);
  assert.match(html, /release_id=\$\{encodeURIComponent\(preparedRelease\.id\)\}/);
  assert.doesNotMatch(html, /release_id=\$\{[^}]*requestId/);
});

// ---- DG generator methodology: the Manager enters kWh, never litres ----------
test('Transport entry collects DG generation in kWh and shows the backend derivation as a preview', () => {
  const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
  const html = read('transport-entry.html');
  const api = read('manager-submissions-api.js');
  const preview = read('calculation-preview.js');

  // The input is electricity generated in kWh; the litre input is gone.
  assert.match(html, /<label class="form-label">Diesel Generator Electricity Generated \(kWh\)<\/label>\s*<input type="number" class="form-control" id="dg-generation" min="0" step="0\.01">/);
  assert.doesNotMatch(html, /Diesel Generator Consumed \(Litres\)/);
  assert.doesNotMatch(html, /id="diesel-dg"/);
  assert.match(html, /data-evidence-list="transport-dg" data-evidence-metric="dg_generation_kwh"/);
  // Only the source kWh is sent; derived litres and emissions are never submitted.
  assert.match(api, /'dg-generation': 'dg_generation_kwh'/);
  assert.doesNotMatch(api, /dg_diesel_litres|dg_diesel_emissions/);
  // DG stays on the Transport + DG Manager page (no domain move).
  assert.match(html, /Transport \+ DG Manager/);
  assert.doesNotMatch(read('energy-entry.html'), /dg-generation|dg_generation_kwh/);

  // Read-only derivation block, clearly labelled as a backend preview.
  assert.match(html, /PREVIEW · DG CALCULATION \(BACKEND\)/);
  for (const id of ['prev-dg-kwh', 'prev-dg-sfc', 'prev-dg-litres', 'prev-dg-ef', 'prev-dg-emissions']) {
    assert.match(html, new RegExp(`<span id="${id}">`));
    assert.doesNotMatch(html, new RegExp(`<input[^>]*id="${id}"`));
  }
  assert.match(html, /\['petrol', 'diesel-transport', 'dg-generation'\]\.forEach/);

  // The preview prints the API's derivation; it holds no SFC, no factor and no arithmetic.
  for (const field of ['source_value', 'parameter_value', 'parameter_unit', 'derived_value', 'derived_unit']) {
    assert.match(preview, new RegExp(`derivation\\.${field}`));
  }
  assert.doesNotMatch(preview + html + api, /0\.33\b|2\.701/);
  const block = preview.match(/function renderDgDerivation\(item\) \{[\s\S]*?\n  \}/)[0];
  assert.doesNotMatch(block, /\*|\/ ?1000/);

  // Run the real renderer against a backend response.
  const nodes = {};
  const context = {
    document: { getElementById: id => (nodes[id] ||= { textContent: '' }) }, Number, DEFAULT_RESULT_UNIT: 'tCO2e'
  };
  const render = vm.runInNewContext(`${block}\nrenderDgDerivation`, context);
  render({
    status: 'available', result_value: '8.027318', result_unit: 'tCO2e', factor_value: '2.7010000000', factor_unit: 'kgCO2e/L',
    derivation: { source_value: '9006', source_unit: 'kWh', parameter_value: '0.33', parameter_unit: 'L/kWh', derived_value: '2971.98', derived_unit: 'L' }
  });
  assert.equal(nodes['prev-dg-kwh'].textContent, '9,006 kWh');
  assert.equal(nodes['prev-dg-sfc'].textContent, '0.33 L/kWh');
  assert.equal(nodes['prev-dg-litres'].textContent, '2,971.98 L');
  assert.equal(nodes['prev-dg-ef'].textContent, '2.701 kgCO2e/L');
  assert.equal(nodes['prev-dg-emissions'].textContent, '8.027318 tCO2e');
  // Nothing saved yet, or an unavailable result: dashes, never a client-side figure.
  render({ status: 'unavailable', reason: 'activity_not_submitted' });
  for (const id of ['prev-dg-kwh', 'prev-dg-sfc', 'prev-dg-litres', 'prev-dg-ef', 'prev-dg-emissions']) {
    assert.equal(nodes[id].textContent, '—');
  }
});

test('Admin review shows the Manager-entered kWh and the read-only derivation', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'admin-queue.html'), 'utf8');
  assert.match(html, /<th>Manager-entered activity<\/th><th>Derived activity<\/th><th>Result<\/th>/);
  assert.match(html, /item\.derivation\.source_value\} \$\{item\.derivation\.source_unit\} × \$\{item\.derivation\.parameter_value\} \$\{item\.derivation\.parameter_unit\} \(\$\{item\.derivation\.parameter_code\}\) = \$\{item\.derivation\.derived_value\} \$\{item\.derivation\.derived_unit\}/);
  // The Admin has no input for a derived value; a correction is requested on the source.
  const section = html.slice(html.indexOf('function calculationsHtml'), html.indexOf('function wasteHtml'));
  assert.doesNotMatch(section, /<input|contenteditable/);
  assert.doesNotMatch(section, /0\.33\b|2\.701/);
});

// ---- Renewable electricity excludes the solar water heater (thermal) --------
test('Energy entry separates renewable electricity from solar thermal and never adds them together', () => {
  const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
  const html = read('energy-entry.html');
  const api = read('manager-submissions-api.js');

  // Clear source labels; the solar water heater is not called renewable electricity.
  assert.match(html, /<label class="form-label">On-Campus Renewable Electricity \(kWh\)<\/label>\s*<input type="number" class="form-control ren-input" id="ren-campus" min="0">/);
  assert.match(html, /<label class="form-label">Procured Renewable Electricity \(kWh\)<\/label>\s*<input type="number" class="form-control ren-input" id="ren-procured" min="0">/);
  assert.match(html, /<label class="form-label">Solar Water Heater \/ Solar Thermal \(kWh\)<\/label>\s*<input type="number" class="form-control thermal-input" id="ren-solar" min="0">/);
  assert.match(html, /Section B — Renewable Electricity<\/h3>/);
  assert.match(html, /Section C — Solar Thermal \(not electricity\)<\/h3>/);
  assert.match(html, /Renewable Electricity Total \(kWh\)<\/label>/);
  assert.doesNotMatch(html, /Total Renewable \(kWh\)|Renewable Total:|Section B — Renewable Energy/);
  // The solar field is structurally outside the electricity sum: it is not a .ren-input.
  assert.equal((html.match(/class="form-control ren-input"/g) || []).length, 2);
  assert.doesNotMatch(html, /ren-input"[^>]*id="ren-solar"/);

  // Still three independent source inputs; the legacy total is never sent.
  assert.match(api, /'ren-campus': 'renewable_on_campus_kwh'/);
  assert.match(api, /'ren-procured': 'renewable_procured_kwh'/);
  assert.match(api, /'ren-solar': 'solar_water_heater_kwh'/);
  assert.doesNotMatch(api, /renewable_total_kwh|renewable_electricity_kwh/);

  // Run the page's own calculator: 18595 + 286334 with a 62500 solar water heater.
  const inline = html.slice(html.indexOf('<script>\n    document.addEventListener'), html.lastIndexOf('</script>\n  <script src="evidence-api.js">'));
  const body = inline.slice(inline.indexOf('{', inline.indexOf("'DOMContentLoaded'")) + 1, inline.lastIndexOf('});'));
  const node = (id, value = '', cls = '') => ({ id, value, className: cls, checked: true, readOnly: true, style: {}, textContent: '', listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; } });
  const nodes = {
    'grid-ht': node('grid-ht', '39366', 'grid-input'), 'grid-comm': node('grid-comm', '1261', 'grid-input'),
    'grid-temp': node('grid-temp', '267', 'grid-input'), 'ren-campus': node('ren-campus', '18595', 'ren-input'),
    'ren-procured': node('ren-procured', '286334', 'ren-input'), 'ren-solar': node('ren-solar', '62500', 'thermal-input'),
    'ren-total': node('ren-total'), 'auto-calc': node('auto-calc'), 'grid-total': node('grid-total'),
    'grid-auto-calc': node('grid-auto-calc'), 'prev-grid-total': node('prev-grid-total'),
    'prev-ren-total': node('prev-ren-total'), 'reset-btn': node('reset-btn'), 'entry-form': node('entry-form')
  };
  let stale = 0;
  const document = {
    getElementById: id => nodes[id],
    querySelectorAll: selector => Object.values(nodes).filter(item => item.className === selector.slice(1))
  };
  vm.runInNewContext(body, { document, window: { KCosmosPreview: { markStale: () => { stale += 1; } } }, parseFloat });
  nodes['ren-campus'].listeners.input();
  assert.equal(nodes['ren-total'].value, 304929);
  assert.equal(nodes['prev-ren-total'].textContent, '304929.00 kWh');
  assert.equal(nodes['grid-total'].value, 40894);
  // A huge or zero solar value never moves the electricity total; it only marks the preview stale.
  for (const solar of ['0', '999999999']) {
    nodes['ren-solar'].value = solar;
    const before = stale;
    nodes['ren-solar'].listeners.input();
    assert.equal(stale, before + 1);
    nodes['ren-procured'].listeners.input();
    assert.equal(nodes['ren-total'].value, 304929);
  }
  assert.notEqual(nodes['ren-total'].value, 367429);
});

test('Manager preview prints the backend electrical indicators and shows solar thermal apart', () => {
  const preview = fs.readFileSync(path.join(__dirname, '..', 'calculation-preview.js'), 'utf8');
  const html = fs.readFileSync(path.join(__dirname, '..', 'energy-entry.html'), 'utf8');
  assert.match(html, /PREVIEW · RENEWABLE ELECTRICITY \(BACKEND\)/);
  for (const id of ['prev-re-electricity', 'prev-total-electricity', 'prev-re-share', 'prev-avoided', 'prev-solar-thermal']) {
    assert.match(html, new RegExp(`id="${id}"`));
    assert.doesNotMatch(html, new RegExp(`<input[^>]*id="${id}"`));  // read-only text, never an input
  }
  assert.match(html, /Thermal energy, shown separately\. Not included in any electrical value above\./);

  const block = preview.match(/function renderEnergyIndicators\(energy\) \{[\s\S]*?\n  \}/)[0];
  // The renderer holds no factor and performs no arithmetic on the values.
  assert.doesNotMatch(block, /0\.727|[^=!<>]\s[*/+]\s|solar_thermal\.value\s*[+*]/);
  const nodes = {};
  const render = vm.runInNewContext(`${block}\nrenderEnergyIndicators`, {
    document: { getElementById: id => (nodes[id] ||= { textContent: '' }) }, Number
  });
  render({
    renewable_electricity_kwh: { status: 'available', value: 304929, unit: 'kWh' },
    total_electricity_consumption_kwh: { status: 'available', value: 345823, unit: 'kWh' },
    renewable_share_pct: { status: 'available', value: 88.174875586644, unit: '%' },
    estimated_avoided_grid_emissions_tco2e: { status: 'available', value: 221.683383, unit: 'tCO2e' },
    solar_thermal: { metric_code: 'solar_water_heater_kwh', value: 62500, unit: 'kWh', included_in_electricity: false }
  });
  assert.equal(nodes['prev-re-electricity'].textContent, '3,04,929 kWh');
  assert.equal(nodes['prev-total-electricity'].textContent, '3,45,823 kWh');
  assert.equal(nodes['prev-re-share'].textContent, '88.174876 %');
  assert.equal(nodes['prev-avoided'].textContent, '221.683383 tCO2e');
  assert.equal(nodes['prev-solar-thermal'].textContent, '62,500 kWh (thermal)');
  // The combined figure is never produced.
  assert.doesNotMatch(Object.values(nodes).map(item => item.textContent).join(' '), /3,67,429|367429/);

  // Missing source: unavailable with the backend's reason, never a zero; solar thermal "Not entered".
  render({
    renewable_electricity_kwh: { status: 'unavailable', value: null, unit: 'kWh', reason: 'renewable_electricity_source_missing' },
    solar_thermal: { value: null, unit: 'kWh' }
  });
  assert.equal(nodes['prev-re-electricity'].textContent, 'Unavailable — renewable electricity source missing');
  assert.equal(nodes['prev-solar-thermal'].textContent, 'Not entered');
  // A zero solar water heater is a reported value and is shown as 0.
  render({ solar_thermal: { value: 0, unit: 'kWh' } });
  assert.equal(nodes['prev-solar-thermal'].textContent, '0 kWh (thermal)');
});

test('Admin review separates derived electrical values from solar thermal, read-only', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'admin-queue.html'), 'utf8');
  const source = html.match(/function energyHtml\(energy\) \{[\s\S]*?\n      \}/)[0];
  const energyHtml = vm.runInNewContext(`${source}\nenergyHtml`, { escapeHtml: value => String(value) });
  const out = energyHtml({
    renewable_electricity_kwh: { status: 'available', value: 304929, unit: 'kWh' },
    total_electricity_consumption_kwh: { status: 'available', value: 345823, unit: 'kWh' },
    renewable_share_pct: { status: 'available', value: 88.174875586644, unit: '%' },
    estimated_avoided_grid_emissions_tco2e: { status: 'available', value: 221.683383, unit: 'tCO2e' },
    solar_thermal: { value: 62500, unit: 'kWh' }
  });
  assert.match(out, /<h3>Derived electrical values \(read-only\)<\/h3>/);
  assert.match(out, /Renewable electricity total \(on-campus \+ procured\)<\/td><td>304929 kWh/);
  assert.match(out, /Total electricity \(grid \+ renewable electricity\)<\/td><td>345823 kWh/);
  assert.match(out, /Renewable share<\/td><td>88\.174875586644 %/);
  assert.match(out, /Electrical avoided emissions<\/td><td>221\.683383 tCO2e/);
  assert.match(out, /<h3[^>]*>Solar thermal \(separate from electricity\)<\/h3><p><strong>Solar water heater:<\/strong> 62500 kWh — thermal energy, not included in any electrical value above\./);
  assert.doesNotMatch(out, /367429/);
  assert.doesNotMatch(out, /<input|contenteditable/);  // the Admin cannot edit a derived value
  assert.equal(energyHtml(null), '');  // non-energy submissions render nothing
  // Wired into the review modal, and source rows state what they are.
  assert.match(html, /\$\{energyHtml\(currentSubmission\.energy\)\}\$\{calculationsHtml\(/);
  assert.match(html, /solar_water_heater_kwh: 'Solar thermal \(source\) — not electricity'/);
  assert.match(html, /renewable_total_kwh: 'Legacy total incl\. solar water heater — deprecated, as originally recorded, not used'/);
});

test('Admin review shows diverted waste and waste per person as backend-derived, never editable', () => {
  const queue = fs.readFileSync(path.join(__dirname, '..', 'admin-queue.html'), 'utf8');
  assert.match(queue, /Waste Diverted from Landfill \(derived\)/);
  assert.match(queue, /waste\.waste_diverted_from_landfill_kg/);
  assert.match(queue, /Waste per Person \(derived\)/);
  assert.match(queue, /diverted from landfill = dry/);
  // The Manager form has no input for any calculated waste value.
  const entry = fs.readFileSync(path.join(__dirname, '..', 'waste-entry.html'), 'utf8');
  assert.doesNotMatch(entry, /<input[^>]*(?:diverted|per_capita|total_waste|dry_waste)/i);
});

test('Outreach Manager form, its payload and Admin review carry no gender field', () => {
  const read = name => fs.readFileSync(path.join(__dirname, '..', name), 'utf8');
  const entry = read('community-outreach-entry.html');
  const integration = read('outreach-integration.js');
  const api = read('outreach-api.js');
  const queue = read('admin-queue.html');
  for (const [name, source] of [['community-outreach-entry.html', entry], ['outreach-integration.js', integration], ['outreach-api.js', api], ['admin-queue.html', queue]]) {
    assert.doesNotMatch(source, /gender|male_participants|female_participants|other_not_disclosed|Not Disclosed/i, name);
  }
  // No placeholder zeros are sent in place of the removed fields.
  assert.doesNotMatch(integration, /(?:male|female|other)[\w-]*\s*:\s*0\b/i);
  // The participant total still comes from the six participant categories.
  for (const id of ['participant-school', 'participant-college', 'participant-farmers', 'participant-industrial', 'participant-researchers', 'participant-government']) {
    assert.ok(integration.includes(`nullableInteger('${id}')`), id);
    assert.ok(entry.includes(`id="${id}"`), id);
  }
  assert.match(entry, /id="participant-total" readonly/);
  assert.match(entry, /function calculateParticipants\(\)/);
  assert.doesNotMatch(entry, /function calculateGender/);
  // Admin review lists whatever programme fields the API returns; the API no longer returns gender.
  assert.match(queue, /Object\.entries\(programme\)\.filter\(\(\[key\]\) => !ignored\.has\(key\)\)/);
});

test('Admin has a Certificates page that manages documents through the admin API only', () => {
  const read = name => fs.readFileSync(path.join(__dirname, '..', name), 'utf8');
  const page = read('admin-certificates.html');
  const script = read('admin-certificates.js');
  // Admin-only page, reachable from every Admin page's navigation.
  assert.match(page, /<body data-auth-role="microcosm_admin" data-login-page="admin-login\.html">/);
  for (const name of ['admin-overview.html', 'admin-queue.html', 'admin-evidence.html', 'admin-factors.html', 'admin-preview.html', 'admin-users.html', 'admin-audit.html']) {
    assert.ok(read(name).includes('<a href="admin-certificates.html" class="nav-item">Certificates</a>'), name);
  }
  // Every metadata field of the upload form.
  for (const id of ['cert-domain', 'cert-type', 'cert-year', 'cert-title', 'cert-issuer', 'cert-registration', 'cert-authorization', 'cert-serial', 'cert-date', 'cert-received', 'cert-invoice', 'cert-manifest', 'cert-quantity', 'cert-unit', 'cert-order', 'cert-notes', 'cert-file']) {
    assert.ok(page.includes(`id="${id}"`), id);
    if (id !== 'cert-file') assert.ok(script.includes(`'${id}'`), id);
  }
  assert.match(page, /accept="application\/pdf,image\/png,image\/jpeg"/);
  assert.match(page, /The reporting year is <strong>not<\/strong> taken from the certificate date\./);
  assert.match(page, /never used in any waste, GHG or other sustainability figure/);
  for (const id of ['filter-domain', 'filter-year', 'filter-status']) assert.ok(page.includes(`id="${id}"`), id);
  // Upload (multipart, CSRF), metadata edit, publish, archive and preview go through /api/admin/certificates.
  assert.match(script, /const BASE = '\/api\/admin\/certificates';/);
  assert.match(script, /csrf: !\['GET', 'HEAD'\]\.includes/);
  assert.match(script, /new FormData\(\)/);
  assert.match(script, /body\.append\('file', file\)/);
  assert.match(script, /method: 'PATCH', body: JSON\.stringify\(values\)/);
  assert.match(script, /\$\{BASE\}\/\$\{encodeURIComponent\(item\.id\)\}\/\$\{action\}`, \{ method: 'POST' \}/);
  for (const action of ['preview', 'edit', 'publish', 'archive']) assert.ok(script.includes(`data-action="${action}"`), action);
  assert.match(script, /\/file`\)/);
  // No delete, and nothing about a particular certificate is written into the page.
  assert.doesNotMatch(script, /method: 'DELETE'/);
  assert.doesNotMatch(script + page, /Green India|\b1640\b|\b1390\b|2041-|GIR\/|1718109/);
  assert.doesNotMatch(script, /\b20[2-9]\d\b/);
  // Values from the API are escaped before they are placed in the table.
  assert.match(script, /escapeHtml\(item\.title\)/);
});
