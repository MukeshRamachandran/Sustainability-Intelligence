const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../..');
const authClient = fs.readFileSync(path.join(root, 'apps/manager-admin/auth-client.js'), 'utf8');
const dataLoader = fs.readFileSync(path.join(root, 'apps/public-dashboard/data-loader.js'), 'utf8');

function loadAuth(location) {
  const calls = [];
  const context = {
    console,
    document: { cookie: '' },
    FormData: class FormData {},
    fetch: async (url) => {
      calls.push(url);
      return {
        ok: true,
        status: 200,
        headers: { get: () => null },
        json: async () => ({ user: { role: 'manager' } })
      };
    },
    window: { location }
  };
  vm.createContext(context);
  vm.runInContext(authClient, context);
  return { context, calls };
}

test('production manager login uses a same-origin /api path', async () => {
  const { context, calls } = loadAuth({
    hostname: 'sustainability.kct.ac.in',
    port: '',
    protocol: 'https:'
  });
  await context.login('waste@kct.ac.in', 'not-stored');
  assert.equal(calls[0], '/api/auth/login');
  assert.doesNotMatch(calls[0], /localhost|127\.0\.0\.1|:8000|:3000/);
});

test('local port 3000 remains a development-only API base', async () => {
  const { context, calls } = loadAuth({
    hostname: '127.0.0.1',
    port: '3000',
    protocol: 'http:'
  });
  await context.login('demo', 'secret');
  assert.equal(calls[0], 'http://127.0.0.1:8000/api/auth/login');
});

test('public dashboard production path is /api/public/dashboard', () => {
  assert.match(dataLoader, /\/api\/public\/dashboard/);
  assert.match(dataLoader, /sustainability\.kct\.ac\.in/);
  assert.doesNotMatch(dataLoader, /file:\/\//);
});

test('manager pages keep stylesheet and script links relative', () => {
  const dir = path.join(root, 'apps/manager-admin');
  const pages = fs.readdirSync(dir).filter(name => name.endsWith('.html'));
  assert.ok(pages.includes('admin-login.html'));
  for (const page of pages) {
    const html = fs.readFileSync(path.join(dir, page), 'utf8');
    assert.doesNotMatch(html, /file:\/\//, page);
    assert.doesNotMatch(html, /(?:src|href)=["']\/(?!\/)/, page);
    assert.doesNotMatch(html, /localhost|127\.0\.0\.1|:8000/, page);
  }
});
