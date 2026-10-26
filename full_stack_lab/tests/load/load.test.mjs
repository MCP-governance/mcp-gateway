// Offline response fixtures only; this does not run or replace an MCP server.
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Script, createContext } from 'node:vm';
import test from 'node:test';

const source = readFileSync(new URL('./load.js', import.meta.url), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace('export default function (connections)', 'function iteration(connections)')
  .replace(/export (function|const) /g, '$1 ') +
  '\nglobalThis.api = { options, setup, iteration, validCall, handleSummary };';

function fixture(scenario) {
  const calls = [], metrics = {};
  const execution = { vu: { idInTest: 1 }, scenario: { iterationInTest: 0 } };
  let reply = { status: 200, headers: {}, timings: { duration: 10 }, json: () => ({}) };
  const context = createContext({
    __ENV: { LOAD_CASE: scenario }, exec: execution,
    http: { post(url, body, options) { calls.push({ url, body, options }); return reply; } },
    check(value, checks) { return Object.values(checks).every((check) => check(value)); },
    Counter: class { constructor(name) { metrics[name] = []; this.name = name; } add(n) { metrics[this.name].push(n); } },
    Trend: class { constructor(name) { metrics[name] = []; this.name = name; } add(n) { metrics[this.name].push(n); } },
  });
  new Script(source).runInContext(context);
  return { api: context.api, calls, metrics, execution, setReply(value) { reply = value; } };
}

function called(decision, policy, executed) {
  return { jsonrpc: '2.0', id: 1, result: { isError: !executed, content: [{ type: 'text', text: '{}' }],
    _meta: { gateway: { decision, policy_id: policy, upstream_executed: executed,
      upstream_attempted: executed, response_disposition: executed ? 'returned' : 'withheld' } } } };
}

test('100 VUs cover every logical PC/server pair once', () => {
  const f = fixture('list');
  const servers = ['filesystem', 'git', 'fetch', 'memory', 'desktop', 'postgres', 'redis', 'email', 'gitea', 'playwright'];
  const connections = Array.from({ length: 100 }, (_, i) => ({
    token: `test-token-${Math.floor(i / 10)}`, server: servers[i % 10], session: `test-session-${i}`,
  }));
  f.setReply({ status: 200, timings: { duration: 10 }, json: () => ({
    jsonrpc: '2.0', id: 2, result: { tools: [{ name: 'approved' }] },
  }) });
  for (let id = 1; id <= 100; id++) { f.execution.vu.idInTest = id; f.api.iteration(connections); }
  assert.equal(new Set(f.calls.map((c) => `${c.url}|${c.options.headers.Authorization}`)).size, 100);
  assert.equal(f.metrics.mcp_requests.reduce((a, b) => a + b), 100);
  assert.equal(f.metrics.mcp_errors.reduce((a, b) => a + b), 0);
  assert.equal(f.api.options.scenarios.list.vus, 100);
  assert.equal(f.api.options.thresholds.mcp_requests[0], 'count==100');
  f.setReply({ status: 200, timings: { duration: 10 }, json: () => ({ jsonrpc: '2.0', id: 1, result: { tools: [] } }) });
  f.api.iteration(connections);
  assert.equal(f.metrics.mcp_errors.at(-1), 1);
});

test('allow requires exact decision, policy and actual upstream success; reads differ', () => {
  const f = fixture('allow'), body = called('Allow', 'P-AUTHZ-ALLOW-001', true);
  assert.equal(f.api.validCall({ status: 200 }, body), true);
  for (const invalid of [called('Allow', 'other-policy', true), called('Allow', 'P-AUTHZ-ALLOW-001', false),
    { ...body, error: { code: -1 } }, { ...body, id: 2 }, called('Block', 'P-CONTROL-FAIL-CLOSED', false)]) {
    assert.equal(f.api.validCall({ status: 200 }, invalid), false);
  }
  f.setReply({ status: 200, timings: { duration: 10 }, json: () => ({ ...body, id: f.execution.scenario.iterationInTest + 2 }) });
  const connections = [{ token: 'test-token', server: 'memory', session: 'test-session' }];
  for (let i = 0; i < 2; i++) { f.execution.scenario.iterationInTest = i; f.api.iteration(connections); }
  assert.notEqual(JSON.parse(f.calls[0].body).params.arguments.query, JSON.parse(f.calls[1].body).params.arguments.query);
  assert.notEqual(JSON.parse(f.calls[0].body).id, JSON.parse(f.calls[1].body).id);
  assert.equal(f.metrics.mcp_errors.reduce((a, b) => a + b), 0);
  assert.equal(f.api.options.scenarios.allow.executor, 'constant-arrival-rate');
  assert.equal(f.api.options.scenarios.allow.rate, 50);
  assert.equal(f.api.options.scenarios.allow.duration, '1m');
  assert.deepEqual(Object.keys(f.api.options.thresholds), ['mcp_wrong_decision']);
  assert.equal(f.api.options.thresholds.mcp_wrong_decision[0], 'count==0');
});

test('deny rejects other Block reasons and any upstream attempt', () => {
  const f = fixture('deny'), body = called('Block', 'MCP-REGISTRY-002', false);
  assert.equal(f.api.validCall({ status: 200 }, body), true);
  assert.equal(f.api.validCall({ status: 500 }, body), false);
  assert.equal(f.api.validCall({ status: 200 }, called('Block', 'P-CONTROL-FAIL-CLOSED', false)), false);
  body.result._meta.gateway.upstream_attempted = true;
  assert.equal(f.api.validCall({ status: 200 }, body), false);
});

test('malformed JSON counts as an error; summary contains only metrics', () => {
  const f = fixture('deny');
  f.setReply({ status: 200, timings: { duration: 7 }, json() { throw new Error('invalid JSON'); } });
  f.api.iteration([{ token: 'never-write-this-token', server: 'desktop', session: 'test-session' }]);
  assert.equal(f.metrics.mcp_errors[0], 1);
  const summary = f.api.handleSummary({ metrics: {
    mcp_requests: { values: { count: 3000 } }, mcp_errors: { values: { count: 1 } },
    mcp_duration: { values: { med: 3, 'p(95)': 8, 'p(99)': 10 } },
  } });
  assert.match(summary['/out/deny.md'], /3000 \| 1 \| 0 \| 3\.00 \| 8\.00 \| 10\.00/);
  assert.deepEqual(JSON.parse(summary['/out/deny-counts.json']), { requests: 3000, errors: 1, dropped: 0 });
  assert.doesNotMatch(JSON.stringify(summary), /never-write-this-token|test-password|test-session/);
});

test('OAuth setup failures expose no response or credential', () => {
  const f = fixture('allow');
  f.setReply({ status: 403, json: () => ({ detail: 'private-login-detail', access_token: 'private-token' }) });
  assert.throws(() => f.api.setup(), /^Error: Synthetic OAuth setup failed$/);
});

const python = process.platform === 'win32' ? 'python' : 'python3';

test('CI capabilities change only the two capacity ceilings and preserve the reviewed source', () => {
  const directory = mkdtempSync(join(tmpdir(), 'mint-load-profile-'));
  try {
    const source = fileURLToPath(new URL('../../registry/capabilities.json', import.meta.url));
    const original = readFileSync(source, 'utf8');
    const target = join(directory, 'capabilities.json');
    const result = spawnSync(python, [fileURLToPath(new URL('./prepare.py', import.meta.url)), source, target], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    const expected = JSON.parse(original);
    expected.execution_profile.limits.max_calls = 10000;
    expected.execution_profile.limits.max_concurrency = 500;
    assert.deepEqual(JSON.parse(readFileSync(target, 'utf8')), expected);
    assert.equal(expected.execution_profile.production_controls, true);
    assert.equal(readFileSync(source, 'utf8'), original);
  } finally {
    rmSync(directory, { recursive: true });
  }
});

test('arrival counts tolerate ±1; actual ledger and policy counts must still match', () => {
  for (const scenario of ['allow', 'deny']) {
    const thresholds = fixture(scenario).api.options.thresholds;
    // Capacity (requests, drops, timeouts) is measured; only a wrong verdict fails the run.
    assert.deepEqual(Object.keys(thresholds), ['mcp_wrong_decision']);
    assert.equal(thresholds.mcp_wrong_decision[0], 'count==0');
  }
  const runner = readFileSync(new URL('./run.sh', import.meta.url), 'utf8');
  const inline = runner.split('if ! python3 - "$out" "$scenario" <<\'PY\'\n')[1].split('\nPY\n')[0];
  const directory = mkdtempSync(join(tmpdir(), 'mint-load-evidence-'));
  try {
    for (const actual of [2999, 3000, 3001]) {
      const evidence = { ledger_rows: actual, policies: [{ decision: 'Block', policy_id: 'MCP-REGISTRY-002', n: actual }],
        verdicts: [{ n: actual }] };
      writeFileSync(join(directory, 'deny-counts.json'), JSON.stringify({ requests: actual }));
      writeFileSync(join(directory, 'deny-timings.json'), JSON.stringify(evidence));
      let result = spawnSync(python, ['-c', inline, directory, 'deny'], { encoding: 'utf8' });
      assert.equal(result.status, 0, result.stderr);
      assert.match(readFileSync(join(directory, 'deny.md'), 'utf8'), new RegExp(`MCP-REGISTRY-002 \\| ${actual}`));
      for (const invalid of [
        { ...evidence, ledger_rows: actual - 1 },
        { ...evidence, policies: [{ decision: 'Block', policy_id: 'MCP-REGISTRY-002', n: actual - 1 }] },
        { ...evidence, verdicts: [{ n: actual - 1 }] },
      ]) {
        writeFileSync(join(directory, 'deny-timings.json'), JSON.stringify(invalid));
        result = spawnSync(python, ['-c', inline, directory, 'deny'], { encoding: 'utf8' });
        assert.notEqual(result.status, 0);
      }
    }
  } finally {
    rmSync(directory, { recursive: true });
  }
});
