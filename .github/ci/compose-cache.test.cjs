const assert = require('node:assert/strict');
const { test } = require('node:test');
const path = require('node:path');
const { cachePlan } = require('../actions/compose-cache/index.cjs');

const root = path.resolve(__dirname, '../..');
const gateway = { context: path.join(root, 'full_stack_lab/gateway'), dockerfile: 'Dockerfile',
  args: { MCP_BUILD_REVISION: 'revision' }, tags: ['gateway'],
  labels: { 'com.docker.compose.service': 'gateway' } };
const plan = (target) => ({ group: { default: { targets: Object.keys(target) } }, target });

test('shared service builds have one image cache; PRs import without exporting', () => {
  const result = cachePlan([plan({ gateway, agent: { ...gateway, tags: ['agent'],
    labels: { 'com.docker.compose.service': 'agent' } } })], root, false);
  assert.equal(Object.keys(result.target).length, 1);
  const cached = Object.values(result.target)[0];
  assert.match(cached['cache-from'][0], /^type=gha,version=2,scope=mint-/);
  assert.deepEqual(cached['cache-to'], []);
  assert.deepEqual(cached.output, ['type=cacheonly']);
  assert.deepEqual(cached.args, gateway.args);
});

test('different Dockerfiles get separate scopes; only selected group targets build', () => {
  const input = plan({ gateway, worker: { context: path.join(root, 'full_stack_lab'),
    dockerfile: 'runtime/Dockerfile' }, ignored: { context: root, dockerfile: 'absent' } });
  input.group.default.targets = ['gateway', 'worker'];
  const result = cachePlan([input], root, true);
  const scopes = Object.values(result.target).map((target) => target['cache-to'][0]);
  assert.equal(new Set(scopes).size, 2);
  assert.ok(scopes.every((scope) => scope.includes('mode=max')));
});

test('scope is stable across service tags; additional contexts stay intact', () => {
  const workstation = { context: path.join(root, 'full_stack_lab'),
    dockerfile: 'workstation/Dockerfile', contexts: { endpoint: path.join(root, 'endpoint-agent') } };
  const before = cachePlan([plan({ workstation })], root, false);
  const after = cachePlan([plan({ other: { ...workstation, tags: ['another'] } })], root, false);
  assert.deepEqual(before, after);
  assert.deepEqual(Object.values(before.target)[0].contexts, workstation.contexts);
});

test('conflicting definitions and missing Dockerfiles fail instead of false success', () => {
  assert.throws(() => cachePlan([plan({ gateway, conflict: { ...gateway, args: {} } })], root, false));
  assert.throws(() => cachePlan([plan({ missing: { context: root, dockerfile: 'absent' } })], root, false));
  assert.throws(() => cachePlan([plan({})], root, false));
});
