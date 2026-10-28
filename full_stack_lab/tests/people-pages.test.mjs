import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../gateway/app/agent_static/console.js', import.meta.url), 'utf8');
function routes(provider = 'local') {
  const calls = [];
  const context = vm.createContext({
    ROUTES: {}, peopleAccounts: [],
    api: async (path) => {
      calls.push(path);
      if (path === '/api/signup-requests') return { requests: [] };
      if (path === '/api/identity') return { provider, bindings: [] };
      return { accounts: [] };
    },
    gw: async (path) => {
      calls.push(path);
      if (path === 'suspensions') return { suspensions: [] };
      if (path === 'overview') return { workstations: [] };
      return { agents: [], managed_events: [], coverage: { reporting_recently: 0 } };
    },
    planes: async () => ({ devices: [] }),
    covPage: async () => ({ rows: [], total: 0 }), endpointSettings: () => '',
    html: () => '', raw: (v) => v, panel: () => '', empty: () => '', kv: () => '',
    listToolbar: () => '', kpiStrip: (v) => v,
    head: (title) => title, page: (value) => value,
  });
  vm.runInContext(source.slice(source.indexOf('ROUTES.people ='), source.indexOf('\nfunction requestedToolList(')), context);
  return { context, calls };
}

test('user management renders account tabs without endpoint data and shows SSO only when configured', async () => {
  for (const provider of ['local', 'oidc']) {
    const { context, calls } = routes(provider);
    const { html: page } = await context.ROUTES.people('', 'devices');
    assert.equal(page.head, '사용자 관리');
    assert.equal(page.active, 'accounts');
    assert.deepEqual(Array.from(page.tabs, (t) => t.key), ['accounts', 'deleted', 'suspensions', 'signups', ...(provider === 'oidc' ? ['sso'] : [])]);
    assert.ok(!calls.includes('endpoint/inventory'));
  }
});

test('endpoint management retains device and connection history tabs without signup or SSO requests', async () => {
  const { context, calls } = routes();
  const { html: page } = await context.ROUTES.endpoints('', 'managed');
  assert.equal(page.head, '엔드포인트 관리');
  assert.equal(page.active, 'managed');
  assert.deepEqual(Array.from(page.tabs, (t) => t.key), ['devices', 'managed']);
  assert.ok(!calls.includes('/api/signup-requests'));
  assert.ok(!calls.includes('/api/identity'));
});
