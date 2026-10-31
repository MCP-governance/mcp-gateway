const { spawnSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

function cachePlan(plans, root, write, load = false) {
  const targets = {};
  const tags = {};
  for (const plan of plans) {
    for (const targetName of plan.group.default.targets) {
      const target = plan.target[targetName];
      const dockerfile = path.resolve(target.context, target.dockerfile || 'Dockerfile');
      const relative = path.relative(root, dockerfile).split(path.sep).join('/');
      if (relative.startsWith('../') || path.isAbsolute(relative) || !fs.statSync(dockerfile).isFile()) {
        throw new Error('Build Dockerfile must be a repository file');
      }
      const key = createHash('sha256').update(relative).digest('hex').slice(0, 16);
      const name = `image-${key}`;
      // Services sharing a Dockerfile share its layer cache, regardless of their tags.
      const labels = Object.fromEntries(Object.entries(target.labels || {})
        .filter(([label]) => !label.startsWith('com.docker.compose.')));
      const cached = { ...target, labels, tags: [], output: [load ? 'type=docker' : 'type=cacheonly'],
        'cache-from': [`type=gha,version=2,scope=mint-${key},timeout=2m`],
        'cache-to': write ? [`type=gha,version=2,scope=mint-${key},mode=max,timeout=2m`] : [] };
      if (targets[name] && JSON.stringify(targets[name]) !== JSON.stringify(cached)) {
        throw new Error(`Different build definitions share ${relative}`);
      }
      targets[name] = cached;
      tags[name] = [...new Set([...(tags[name] || []), ...(target.tags || [])])];
    }
  }
  if (!Object.keys(targets).length) throw new Error('Compose has no build targets');
  if (load) {
    for (const [name, target] of Object.entries(targets)) {
      if (!tags[name].length) throw new Error('Loaded images must have Compose tags');
      target.tags = tags[name];
    }
  }
  return { group: { default: { targets: Object.keys(targets) } }, target: targets };
}

function loadedCompose(plan) {
  // Build results are already loaded; clearing only build preserves every runtime setting.
  return 'services:\n' + plan.group.default.targets.map((name) =>
    `  ${JSON.stringify(name)}:\n    image: ${JSON.stringify(plan.target[name].tags[0])}\n    build: !reset null\n`).join('');
}

function run() {
  const root = process.env.GITHUB_WORKSPACE;
  const stack = process.env.INPUT_STACK;
  if (!['deploy', 'full_stack_lab'].includes(stack)) throw new Error('Unknown Compose stack');
  const cwd = path.join(root, stack);
  const builder = process.env.INPUT_BUILDER;
  if (!builder) throw new Error('Missing builder');
  if (!process.env.ACTIONS_RUNTIME_TOKEN || !process.env.ACTIONS_RESULTS_URL) {
    throw new Error('GitHub Actions cache v2 runtime is unavailable');
  }
  const revision = process.env.GITHUB_SHA;
  const renderEnv = { ...process.env, MINT_VERSION: fs.readFileSync(path.join(root, 'VERSION'), 'utf8').trim(),
    MCP_BUILD_REVISION: stack === 'deploy'
      ? `${fs.readFileSync(path.join(root, 'VERSION'), 'utf8').trim()}+g${revision.slice(0, 12)}` : revision,
    MINT_BIND: '192.0.2.1', APPLIANCE_BIND: '127.0.0.1', FIELD_TLS_ADDRESSES: 'https://127.0.0.1:8080' };
  const files = stack === 'deploy' ? ['compose.yaml'] : ['compose.yaml', 'compose.field.yaml'];
  // Placeholders only render build plans; they never reach installation or GITHUB_ENV.
  for (const file of files) {
    for (const match of fs.readFileSync(path.join(cwd, file), 'utf8').matchAll(/\$\{([A-Z_][A-Z_0-9]*):\?[^}]*\}/g)) {
      renderEnv[match[1]] ||= 'ci-render-only';
    }
  }
  function docker(args, env, capture = false) {
    const result = spawnSync('docker', args, { cwd, env, encoding: 'utf8',
      stdio: capture ? ['ignore', 'pipe', 'inherit'] : 'inherit' });
    if (result.error) throw result.error;
    if (result.status !== 0) throw new Error(`Docker command failed (${result.status})`);
    return result.stdout;
  }
  const plans = [JSON.parse(docker(['compose', '-f', 'compose.yaml', '--profile', '*', 'build', '--print'], renderEnv, true))];
  if (stack === 'full_stack_lab') {
    plans.push(JSON.parse(docker(['compose', '-f', 'compose.yaml', '-f', 'compose.field.yaml',
      'build', '--print', 'model-proxy'], renderEnv, true)));
  }
  const write = process.env.GITHUB_EVENT_NAME === 'push' && process.env.GITHUB_REF === 'refs/heads/main';
  const load = stack === 'full_stack_lab';
  const plan = cachePlan(plans, root, write, load);
  const filename = path.join(process.env.RUNNER_TEMP, 'mint-cache.json');
  fs.writeFileSync(filename, JSON.stringify(plan));
  console.log(`${load ? 'Loading' : 'Priming'} ${Object.keys(plan.target).length} images; export=${write}`);
  // A JavaScript action receives the runtime cache credentials; an inline shell does not.
  docker(['buildx', 'bake', '--builder', builder, '-f', filename, '--allow', `fs.read=${root}`,
    '--progress', 'plain'], process.env);
  if (load) {
    const overlay = path.join(process.env.RUNNER_TEMP, 'mint-loaded.yaml');
    fs.writeFileSync(overlay, loadedCompose(plans[0]));
    fs.appendFileSync(process.env.GITHUB_ENV, `COMPOSE_FILE=compose.yaml:${overlay}\n`);
  }
  fs.appendFileSync(process.env.GITHUB_ENV, `BUILDX_BUILDER=${builder}\nCOMPOSE_BAKE=true\n`);
}

module.exports = { cachePlan, loadedCompose };
if (require.main === module) {
  try { run(); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
