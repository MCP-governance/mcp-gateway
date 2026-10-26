import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';
import { Counter, Trend } from 'k6/metrics';

const CASE = __ENV.LOAD_CASE || 'list';
if (!['list', 'allow', 'deny'].includes(CASE)) throw new Error('Unknown LOAD_CASE');
const GATEWAY = 'http://gateway:8080';
const IDP = 'http://agent-service:8000';
const SERVERS = ['filesystem', 'git', 'fetch', 'memory', 'desktop', 'postgres', 'redis', 'email', 'gitea', 'playwright'];
const EMPLOYEES = ['ysg@bob.local', 'jwj@bob.local', 'pse@bob.local'];
const PROTOCOL = '2025-11-25';
const requests = new Counter('mcp_requests');
const errors = new Counter('mcp_errors');
// A decision the gateway should never give for this load. Overload (timeouts, fail-closed upstream)
// is measured, not failed: capacity is a stage-2 target, a wrong verdict is a defect at any load.
const wrong = new Counter('mcp_wrong_decision');
const duration = new Trend('mcp_duration', true);

export const options = {
  scenarios: {
    [CASE]: CASE === 'list'
      ? { executor: 'per-vu-iterations', vus: 100, iterations: 1, maxDuration: '40s', gracefulStop: '35s' }
      : { executor: 'constant-arrival-rate', rate: 50, timeUnit: '1s', duration: '1m',
          preAllocatedVUs: 100, maxVUs: 500, gracefulStop: '35s' },
  },
  thresholds: {
    ...(CASE === 'list'
      ? { mcp_requests: ['count==100'], mcp_errors: ['count==0'], checks: ['rate==1'], dropped_iterations: ['count==0'] }
      : { mcp_wrong_decision: ['count==0'] }),
  },
  setupTimeout: '3m', teardownTimeout: '2m',
  summaryTrendStats: ['min', 'med', 'p(95)', 'p(99)', 'max'],
};

function json(response) {
  try { return response.json(); } catch (_) { return null; }
}

function headers(connection, phase) {
  return {
    Authorization: `Bearer ${connection.token}`,
    'Content-Type': 'application/json', Accept: 'application/json, text/event-stream',
    'Mcp-Protocol-Version': PROTOCOL,
    ...(connection.session ? { 'Mcp-Session-Id': connection.session } : {}),
    'X-Agent-Task-Id': `load-${CASE}${phase === 'setup' ? '-setup' : ''}`,
    'User-Agent': 'mint-k6',
  };
}

function rpc(connection, method, params = {}, phase = 'load', id = 1) {
  return http.post(`${GATEWAY}/mcp/${connection.server}/`, JSON.stringify({
    jsonrpc: '2.0', id, method, params,
  }), { headers: headers(connection, phase), timeout: '30s', tags: { phase, name: method } });
}

function validReply(response, body, id = 1) {
  return response.status === 200 && body?.jsonrpc === '2.0' && body.id === id && !body.error && !!body.result;
}

function validCall(response, body, id = 1) {
  const result = body?.result;
  const gateway = result?._meta?.gateway;
  return validReply(response, body, id) && (CASE === 'allow'
    ? result.isError !== true && gateway?.decision === 'Allow' && gateway.policy_id === 'P-AUTHZ-ALLOW-001'
      && gateway.upstream_executed === true && ['returned', 'masked'].includes(gateway.response_disposition)
      && Array.isArray(result.content) && result.content.length > 0
    : result.isError === true && gateway?.decision === 'Block' && gateway.policy_id === 'MCP-REGISTRY-002'
      && gateway.upstream_attempted === false && gateway.upstream_executed === false);
}

function wrongDecision(body) {
  const gateway = body?.result?._meta?.gateway;
  if (!gateway?.decision) return false;
  const verdict = `${gateway.decision} ${gateway.policy_id}`;
  const expected = CASE === 'allow' ? ['Allow P-AUTHZ-ALLOW-001', 'Block MCP-UPSTREAM-001'] : ['Block MCP-REGISTRY-002'];
  return !expected.includes(verdict);
}

function callParams(query = 'load-preflight') {
  // Distinct read arguments avoid the existing duplicate-in-flight policy.
  return { name: CASE === 'allow' ? 'search_nodes' : 'get_config',
    arguments: CASE === 'allow' ? { query } : {} };
}

export function setup() {
  const connections = [];
  for (let pc = 0; pc < 10; pc++) {
    const login = http.post(`${IDP}/oauth/token`, {
      grant_type: 'password', client_id: `load-pc-${pc + 1}`,
      username: EMPLOYEES[pc % EMPLOYEES.length], password: 'test-password',
    }, { timeout: '20s', tags: { phase: 'setup', name: 'oauth/token' } });
    const grant = json(login);
    if (login.status !== 200 || typeof grant?.access_token !== 'string' || !grant.access_token
        || !(Number(grant.expires_in) >= 300)) {
      throw new Error('Synthetic OAuth setup failed');
    }
    for (const server of CASE === 'list' ? SERVERS : [CASE === 'allow' ? 'memory' : 'desktop']) {
      const connection = { token: grant.access_token, server };
      const init = rpc(connection, 'initialize', { protocolVersion: PROTOCOL, capabilities: {},
        clientInfo: { name: 'mint-k6', version: '1' } }, 'setup');
      connection.session = init.headers['Mcp-Session-Id'];
      if (!validReply(init, json(init)) || !connection.session) throw new Error('MCP initialize failed');
      const notified = http.post(`${GATEWAY}/mcp/${server}/`, JSON.stringify({
        jsonrpc: '2.0', method: 'notifications/initialized',
      }), { headers: headers(connection, 'setup'), timeout: '20s', tags: { phase: 'setup' } });
      if (notified.status !== 202) throw new Error('MCP initialized notification failed');
      connections.push(connection);
    }
  }
  if (CASE !== 'list') {
    // A changed seed or policy must fail before it becomes a misleading load result.
    const probe = rpc(connections[0], 'tools/call', callParams(), 'setup');
    if (!validCall(probe, json(probe))) throw new Error('Expected seed decision/upstream execution not observed');
  }
  return connections;
}

export default function (connections) {
  const id = exec.scenario.iterationInTest + 2;
  const connection = connections[(CASE === 'list' ? exec.vu.idInTest - 1 : exec.scenario.iterationInTest) % connections.length];
  const response = rpc(connection, CASE === 'list' ? 'tools/list' : 'tools/call',
    CASE === 'list' ? {} : callParams(`load-${exec.scenario.iterationInTest}`), 'load', id);
  const body = json(response);
  const ok = CASE === 'list'
    ? validReply(response, body, id) && Array.isArray(body.result.tools) && body.result.tools.length > 0
    : validCall(response, body, id);
  check(ok, { 'expected MCP result and execution': (value) => value });
  requests.add(1);
  errors.add(ok ? 0 : 1);
  if (CASE !== 'list') wrong.add(wrongDecision(body) ? 1 : 0);
  duration.add(response.timings.duration);
}

export function teardown(connections) {
  for (const connection of connections) {
    const response = http.del(`${GATEWAY}/mcp/${connection.server}/`, null, {
      headers: headers(connection, 'setup'), timeout: '10s', tags: { phase: 'teardown' },
    });
    check(response, { 'MCP session closed': (r) => [200, 202, 204].includes(r.status) });
  }
}

export function handleSummary(data) {
  const count = (name) => data.metrics[name]?.values.count || 0;
  const stats = data.metrics.mcp_duration?.values || {};
  const ms = (name) => typeof stats[name] === 'number' ? stats[name].toFixed(2) : '—';
  const line = `| ${CASE} | ${count('mcp_requests')} | ${count('mcp_errors')} | ${count('dropped_iterations')} | ${ms('med')} | ${ms('p(95)')} | ${ms('p(99)')} |`;
  return {
    [`/out/${CASE}-counts.json`]: JSON.stringify({ requests: count('mcp_requests'),
      errors: count('mcp_errors'), dropped: count('dropped_iterations') }),
    [`/out/${CASE}.md`]: `| scenario | requests | errors | dropped | p50 ms | p95 ms | p99 ms |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n${line}\n`,
    stdout: `${line}\n`,
  };
}
