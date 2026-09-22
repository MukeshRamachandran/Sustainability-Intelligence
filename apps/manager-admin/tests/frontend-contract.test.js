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
  'outreach-login.html': { role: 'manager', domain: 'outreach', destination: 'community-outreach-entry.html' }
};

const managerContracts = {
  'transport-entry.html': ['transport', 'petrol', 'diesel-transport', 'active-vehicles-petrol', 'active-vehicles-diesel', 'ev-consumption', 'diesel-dg', 'active-dg'],
  'energy-entry.html': ['energy', 'grid-ht', 'grid-comm', 'grid-temp', 'ren-campus', 'ren-procured', 'ren-solar', 'grid-total', 'ren-total'],
  'lpg-entry.html': ['lpg', 'lpg-cylinders', 'lpg-kg'],
  'water-entry.html': ['water', 'water-twad', 'water-borewell', 'water-priv', 'water-waste', 'water-recycled', 'water-consumed']
};
const evidenceInputs = {
  'transport-entry.html': ['evidence-petrol', 'evidence-diesel', 'evidence-dg'],
  'energy-entry.html': ['evidence-energy'],
  'lpg-entry.html': ['evidence-lpg'],
  'water-entry.html': ['evidence-water'],
  'community-outreach-entry.html': ['evidence-file']
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
  // Avoided emissions stay declared-unavailable, now owned by the single
  // preview renderer rather than duplicated into the entry page.
  assert.match(calculations, /Methodology review required/);
  assert.match(factors, /code: 'LPG'/);
  assert.match(factors, /unit: 'kg'/);
  assert.doesNotMatch(`${read('lpg-entry.html')}\n${read('manager-submissions-api.js')}`, /lpg_consumption_litres|lpg-litres|Litres\/Kg/);
});

test('calculation-preview.js is the only writer of governed emission preview nodes', () => {
  const calculations = read('calculation-preview.js');
  // The renderer labels every figure with the backend's own result unit and
  // never rescales a component to fit a hardcoded label.
  assert.match(calculations, /item\.result_unit/);
  assert.doesNotMatch(calculations, /toFixed\(2\)\}\s*kgCO2e/);

  // Entry pages may echo typed activity, but must never write the nodes that
  // hold a governed server result.
  const owned = ['prev-scope2', 'prev-avoided', 'prev-emission', 'prev-factor', 'prev-total', 'prev-petrol', 'prev-diesel-t', 'prev-diesel-dg'];
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
  assert.match(outreach, /ensureDraft: \(\) => saveDraft\(false\)/);
  assert.match(outreach, /KCosmosUI\?\.notify/);
  assert.match(outreach, /\/api\/manager\/outreach\/current-period/);
  assert.match(outreach, /expected_row_version = currentRowVersion/);
  assert.match(outreach, /stale_submission/);
  assert.match(outreach, /Refresh submission/);
  assert.doesNotMatch(outreach, /parseInt|parseFloat/);
  assert.doesNotMatch(outreach, /new Date/);
  assert.match(outreach, /await KCosmos\.api\(`\/api\/manager\/outreach\/programmes\/\$\{currentProgrammeId\}`\)/);
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
