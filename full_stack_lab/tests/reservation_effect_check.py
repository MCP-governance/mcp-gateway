"""Hold a real corporate DB row lock, race Gateway writes, count independent effects.

Run from full_stack_lab after a clean up: python3 tests/reservation_effect_check.py
No server double: execute_sql is the installed postgres MCP; psql observes its DB.
"""
import concurrent.futures
import json
import os
import subprocess
import time
import urllib.request

GATEWAY = os.getenv('LAB_GATEWAY_URL', 'http://127.0.0.1:8080')
PSQL = ['docker', 'compose', 'exec', '-T', 'corp-db', 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-U', 'corp_owner', '-d', 'corp']


def sql(query):
    return subprocess.check_output(PSQL + ['-c', query], text=True, timeout=15).strip()


def post(path, body, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(GATEWAY + path, json.dumps(body).encode(), headers)
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def mcp_write(token, statement):
    code = """import asyncio,json,sys
from app import acceptance
request=json.load(sys.stdin)
acceptance.TOKENS['race']=request['token']
out=asyncio.run(acceptance.call('race','execute_sql',{'sql':request['sql']},'http://127.0.0.1:8080/mcp/postgres/'))
print(json.dumps({k:out.get(k) for k in ('decision','policy_id','decision_id')}))
"""
    output = subprocess.check_output(['docker', 'compose', 'exec', '-T', 'gateway', 'python', '-c', code],
                                     input=json.dumps({'token': token, 'sql': statement}), text=True, timeout=45)
    result = json.loads(output)
    row_id = int(result['decision_id'])
    query = f"SELECT json_build_object('upstream_attempted',upstream_attempted,'upstream_executed',upstream_executed) FROM decisions WHERE id={row_id}"
    flags = subprocess.check_output(['docker','compose','exec','-T','db','psql','-X','-qAt','-U','mcp','-d','mcp_governance','-c',query],text=True,timeout=15)
    return {**result, **json.loads(flags)}


def race(token, duplicate=False):
    before = sql('SELECT price FROM public.products WHERE id=1')
    holder = subprocess.Popen(PSQL, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        holder.stdin.write("BEGIN; UPDATE public.products SET price=price WHERE id=1; SELECT 'locked';\n")
        holder.stdin.flush()
        assert holder.stdout.readline().strip() == 'locked', 'Could not establish the independent row lock'
        count = 2 if duplicate else 6
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
            calls = [pool.submit(mcp_write, token, 'UPDATE public.products SET price=price+1 WHERE id=1' +
                                 ('' if duplicate else f' /* slot-{i} */')) for i in range(count)]
            # Accepted writes wait on the real DB lock. Refusals must finish while it is held.
            deadline = time.monotonic() + 15
            expected_blocks = 1 if duplicate else 2
            while sum(f.done() for f in calls) < expected_blocks and time.monotonic() < deadline:
                time.sleep(0.1)
            blocked_while_locked = [f.result() for f in calls if f.done()]
            holder.stdin.write('COMMIT;\n')
            holder.stdin.close()
            holder.wait(timeout=10)
            results = [f.result() for f in calls]
        expected_policy = 'P-RATE-003' if duplicate else 'P-RATE-002'
        assert len(blocked_while_locked) == expected_blocks, results
        assert all(r['policy_id'] == expected_policy and not r['upstream_attempted'] for r in blocked_while_locked), results
        executed = [r for r in results if r['upstream_executed']]
        expected_effects = 1 if duplicate else 4
        assert len(executed) == expected_effects and all(r['decision'] == 'Allow' for r in executed), results
        delta = float(sql('SELECT price FROM public.products WHERE id=1')) - float(before)
        assert delta == expected_effects, f'Independent DB effect {delta} != {expected_effects}'
        return {'case': 'duplicate' if duplicate else 'concurrency', 'requests': count,
                'blocked_before_unlock': len(blocked_while_locked), 'policy_id': expected_policy,
                'independent_db_effects': delta, 'passed': True}
    finally:
        if holder.poll() is None:
            holder.terminate()
            holder.wait(timeout=10)
        sql(f'UPDATE public.products SET price={before} WHERE id=1')


if __name__ == '__main__':
    # A reviewed, finite SQL capability belongs to this lab actor, not the admin
    # role. It permits exactly seven increments of this public fixture row.
    setup = """import asyncio
from app import db
asyncio.run(db.execute(\"\"\"INSERT INTO principals(token,email,display_name,role,synthetic,department,password_hash,user_id)
SELECT 'reservation-check','reservation-check@bob.local','reservation-check','employee',true,department,password_hash,'reservation-check'
FROM principals WHERE email='ysg@bob.local' ON CONFLICT(token) DO UPDATE SET status='active'\"\"\"))
"""
    subprocess.check_call(['docker', 'compose', 'exec', '-T', 'gateway', 'python', '-c', setup])
    try:
        token = post('/api/session', {'email': 'reservation-check@bob.local', 'password': os.getenv('MOCK_SSO_PASSWORD', 'test-password')})['access_token']
        before = sql('SELECT price FROM public.products WHERE id=1')
        denied = mcp_write(token, 'UPDATE public.products SET price=0 WHERE id=1')
        assert denied['decision'] == 'Block' and denied['policy_id'] == 'PAC-01' and not denied['upstream_attempted'], denied
        assert sql('SELECT price FROM public.products WHERE id=1') == before, 'Out-of-scope SQL changed the independent database'
        print(json.dumps([race(token), race(token, duplicate=True)], indent=2))
    finally:
        subprocess.check_call(['docker', 'compose', 'exec', '-T', 'db', 'psql', '-X', '-q', '-v', 'ON_ERROR_STOP=1',
                               '-U', 'mcp', '-d', 'mcp_governance', '-c',
                               "UPDATE principals SET status='deleted' WHERE token='reservation-check'"])
