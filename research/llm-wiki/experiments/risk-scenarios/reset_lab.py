import json
from pathlib import Path
import secrets
import subprocess
import time

root = Path('/home/user/mcp-gateway/full_stack_lab/reports/risk-scenarios-20261014')
root.mkdir(mode=0o700, exist_ok=True)
network = 'mcpgw-risk-20261014'
container = network + '-postgres'
dbname = 'risk_scenarios_20261014'

def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout

existing = run(['docker', 'ps', '-a', '--filter', 'name=^/' + container + '$', '--format', '{{.Names}}']).strip()
if existing:
    assert run(['docker', 'inspect', '-f', '{{index .Config.Labels "mcpgw.task"}}', container]).strip() == network
else:
    run(['docker', 'network', 'create', '--label', 'mcpgw.task=' + network, network])
    password = secrets.token_urlsafe(32)
    pg_env = root / 'postgres.env'
    pg_env.write_text('POSTGRES_USER=risk_owner\nPOSTGRES_PASSWORD=' + password + '\nPOSTGRES_DB=' + dbname + '\n')
    pg_env.chmod(0o600)
    env = root / 'scenario.env'
    env.write_text('SCENARIO_DATABASE_URL=postgresql://risk_owner:' + password + '@risk-postgres:5432/' + dbname + '\n')
    env.chmod(0o600)
    image = run(['docker', 'inspect', '-f', '{{.Image}}', 'mcpgw-55e075465e-db-1']).strip()
    run(['docker', 'run', '-d', '--name', container, '--label', 'mcpgw.task=' + network,
         '--network', network, '--network-alias', 'risk-postgres', '--env-file', str(pg_env), image])
for _ in range(30):
    ready = subprocess.run(['docker', 'exec', container, 'pg_isready', '-U', 'risk_owner', '-d', dbname], capture_output=True)
    if ready.returncode == 0:
        break
    time.sleep(1)
else:
    raise RuntimeError('Dedicated lab PostgreSQL not ready')
assert run(['docker', 'inspect', '-f', '{{index .Config.Labels "mcpgw.task"}}', container]).strip() == network
# This exact task-owned container has no published ports and no product mounts.
inspect = json.loads(run(['docker', 'inspect', container]))[0]
assert not inspect['HostConfig']['PortBindings']
assert not any('/registry' in m['Destination'] or 'field_db' in m.get('Name', '') for m in inspect['Mounts'])
marker = "CREATE TABLE reset_marker(value text); INSERT INTO reset_marker VALUES ('reset-me');"
run(['docker', 'exec', container, 'psql', '-U', 'risk_owner', '-d', dbname, '-v', 'ON_ERROR_STOP=1', '-c', marker])
before = run(['docker', 'exec', container, 'psql', '-U', 'risk_owner', '-d', dbname, '-Atc', 'SELECT count(*) FROM reset_marker']).strip()
assert before == '1'
run(['docker', 'exec', container, 'psql', '-U', 'risk_owner', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', 'DROP DATABASE ' + dbname])
run(['docker', 'exec', container, 'psql', '-U', 'risk_owner', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', 'CREATE DATABASE ' + dbname])
after = run(['docker', 'exec', container, 'psql', '-U', 'risk_owner', '-d', dbname, '-Atc', "SELECT to_regclass('public.reset_marker') IS NULL"]).strip()
assert after == 't'
evidence = dict(database_reset=True, database_name=dbname, container=container,
    container_task_label=network, marker_count_before=1, marker_absent_after=True,
    published_ports=False, product_mounts=False, pg_image=inspect['Image'], at=time.time())
(root / 'reset.json').write_text(json.dumps(evidence, indent=2) + '\n')
print(json.dumps(evidence))
