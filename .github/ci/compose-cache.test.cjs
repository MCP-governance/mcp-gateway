const assert = require('node:assert/strict');
const { test } = require('node:test');
const path = require('node:path');
const fs = require('node:fs');
const vm = require('node:vm');
const { cachePlan, loadedCompose } = require('../actions/compose-cache/index.cjs');

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
  const input = plan({ gateway, proxy: { context: path.join(root, 'full_stack_lab'),
    dockerfile: 'model-proxy/Dockerfile' }, ignored: { context: root, dockerfile: 'absent' } });
  input.group.default.targets = ['gateway', 'proxy'];
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

test('loaded shared images export once with every service tag and unchanged build inputs', () => {
  const input = plan({ gateway, agent: { ...gateway, tags: ['agent', 'gateway'] } });
  const result = cachePlan([input], root, false, true);
  assert.equal(Object.keys(result.target).length, 1);
  const cached = Object.values(result.target)[0];
  assert.deepEqual(cached.tags, ['gateway', 'agent']);
  assert.deepEqual(cached.output, ['type=docker']);
  assert.deepEqual(cached.args, gateway.args);
  assert.deepEqual(cached['cache-to'], []);
  assert.deepEqual(input.target.gateway, gateway);
  assert.equal(loadedCompose(input),
    'services:\n  "gateway":\n    image: "gateway"\n    build: !reset null\n  "agent":\n    image: "agent"\n    build: !reset null\n');
  assert.throws(() => cachePlan([plan({ gateway: { ...gateway, tags: [] } })], root, false, true));
});

function action(stack, event, ref, failBake = false) {
  const calls = [], writes = new Map();
  const base = plan({ gateway, agent: { ...gateway, tags: ['agent'] } });
  const field = plan({ 'model-proxy': { context: path.join(root, 'full_stack_lab'),
    dockerfile: 'model-proxy/Dockerfile', tags: ['model-proxy'] } });
  const filename = path.join(root, '.github/actions/compose-cache/index.cjs');
  const entry = { exports: {} };
  const env = { GITHUB_WORKSPACE: root, INPUT_STACK: stack, INPUT_BUILDER: 'selected',
    GITHUB_SHA: 'revision', GITHUB_EVENT_NAME: event, GITHUB_REF: ref,
    ACTIONS_RUNTIME_TOKEN: 'test-only', ACTIONS_RESULTS_URL: 'test-only',
    RUNNER_TEMP: '/temporary', GITHUB_ENV: '/env', COMPOSE_PROJECT_NAME: 'mint-ci' };
  const process = { env };
  const mockedRequire = (name) => {
    if (name === 'node:child_process') return { spawnSync(command, args, options) {
      assert.equal(command, 'docker');
      assert.ok(!args.includes('runtime-worker'));
      calls.push({ args, env: options.env });
      return { status: failBake && args[0] === 'buildx' ? 1 : 0,
        stdout: JSON.stringify(args.includes('model-proxy') ? field : base) };
    } };
    if (name === 'node:fs') return { ...fs,
      writeFileSync: (name, value) => writes.set(name, value),
      appendFileSync: (name, value) => writes.set(name, (writes.get(name) || '') + value) };
    return require(name);
  };
  mockedRequire.main = entry;
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'),
    { require: mockedRequire, module: entry, process, console: { log() {}, error() {} } });
  return { calls, writes, process };
}

test('verification action loads images before enabling the base-only overlay', () => {
  const { calls, writes, process } = action('full_stack_lab', 'pull_request', 'refs/pull/1/merge');
  assert.equal(process.exitCode, undefined);
  const bake = calls.find(({ args }) => args[0] === 'buildx');
  assert.ok(bake.args.includes('selected'));
  assert.ok(bake.args.includes('plain'));
  const output = JSON.parse(writes.get(path.join('/temporary', 'mint-cache.json')));
  assert.equal(Object.keys(output.target).length, 2);
  assert.ok(Object.values(output.target).every((target) => target.output[0] === 'type=docker'
    && target['cache-to'].length === 0));
  const overlay = writes.get(path.join('/temporary', 'mint-loaded.yaml'));
  assert.ok(overlay.includes('"gateway"') && overlay.includes('"agent"'));
  assert.ok(!overlay.includes('model-proxy'));
  assert.deepEqual(Array.from(calls[1].args.slice(-3)), ['build', '--print', 'model-proxy']);
  assert.match(writes.get('/env'), /COMPOSE_FILE=compose.yaml:.*mint-loaded.yaml/);
});

test('only main pushes save cache; deployment keeps its existing cache-only path', () => {
  for (const [stack, event, ref, saves] of [
    ['full_stack_lab', 'push', 'refs/heads/main', true],
    ['full_stack_lab', 'push', 'refs/heads/topic', false],
    ['full_stack_lab', 'workflow_dispatch', 'refs/heads/main', false],
    ['deploy', 'pull_request', 'refs/pull/1/merge', false],
  ]) {
    const { writes, process } = action(stack, event, ref);
    assert.equal(process.exitCode, undefined);
    const output = JSON.parse(writes.get(path.join('/temporary', 'mint-cache.json')));
    assert.ok(Object.values(output.target).every((target) => Boolean(target['cache-to'].length) === saves));
    if (stack === 'deploy') {
      assert.ok(Object.values(output.target).every((target) => target.output[0] === 'type=cacheonly'));
      assert.ok(!writes.get('/env').includes('COMPOSE_FILE'));
    }
  }
});

test('failed image loading fails the action without enabling the overlay', () => {
  const { writes, process } = action('full_stack_lab', 'pull_request', 'refs/pull/1/merge', true);
  assert.equal(process.exitCode, 1);
  assert.ok(!writes.has('/env'));
  assert.ok(!writes.has(path.join('/temporary', 'mint-loaded.yaml')));
});
