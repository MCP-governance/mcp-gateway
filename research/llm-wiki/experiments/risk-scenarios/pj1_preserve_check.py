"""Root-authorized PJ1 test: preserve DB and restore service in finally.

Uses installed code, truthful kernel checks, real elapsed heartbeat expiry.
Never prints device credentials or JWTs. No synthetic MCP server is used.
"""
import base64
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request


def main():
    assert os.geteuid() == 0
    path = Path('/usr/local/lib/mcpgw-managed/managed-linux.py')
    spec = importlib.util.spec_from_file_location('installed_managed', path)
    managed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(managed)
    config = json.loads(Path('/var/lib/mcpgw-managed/managed-pj1/config.json').read_text())
    managed.verify_transport(config)
    service = 'mcpgw-managed-managed-pj1.service'
    assert subprocess.run(['systemctl', 'is-active', '--quiet', service]).returncode == 0
    evidence = []

    def record(case, **fields):
        item = dict(case=case, at=time.time(), **fields)
        evidence.append(item)
        print(json.dumps(item), flush=True)

    def beat():
        policy = managed.request(config, '/api/endpoint/managed-policy')
        hashes, checks = managed.checks(config, policy)
        assert all(checks.values()) and hashes == policy['configuration_hashes']
        result = managed.request(config, '/api/endpoint/heartbeat', dict(
            policy_hash=policy['policy_hash'], configuration_hashes=hashes,
            checks=checks, host=managed.host_report(config)))
        assert result['state'] == 'active' and result['compliant'] is True
        return policy

    def admission(token):
        request = urllib.request.Request(config['gateway_url'] + '/mcp/github/',
            data=json.dumps(dict(jsonrpc='2.0', id=1, method='initialize', params=dict(
                protocolVersion='2025-03-26', capabilities={}, clientInfo=dict(
                    name='risk-scenarios-preserve', version='1')))).encode(),
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                     'Accept': 'application/json, text/event-stream'})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *unused):
                raise ValueError('No credential forwarding')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=20) as response:
                response.read(131072)
                return response.status, None
        except urllib.error.HTTPError as exc:
            data = json.loads(exc.read(131072))
            return exc.code, data.get('policy_id')

    policy = beat()
    token = managed.request(config, '/oauth/device-token', {})['access_token']
    status, _ = admission(token)
    assert status == 200, status
    record('D01-active-protocol-admission', status=status, kernel_checks=True)
    shell = '/usr/local/lib/mcpgw-enforcement/mcpgw-managed-pj1/login-shell'
    def confined(command):
        return subprocess.run(['sudo', '-u', 'managed-pj1', '--', shell, '-c', command],
                              capture_output=True, text=True, timeout=20)
    profile = confined('cat /proc/self/attr/current')
    assert profile.returncode == 0 and profile.stdout.strip() == 'mcpgw-managed-pj1 (enforce)'
    allowed = confined(': > /dev/tcp/100.83.175.111/443')
    assert allowed.returncode == 0
    blocked = confined('/usr/bin/node --version')
    assert blocked.returncode == 126
    record('D02-executable-boundary', profile=profile.stdout.strip(), gateway_exit=0, node_exit=blocked.returncode)
    with socket.create_connection(('127.0.0.1', 22), timeout=3):
        pass
    loopback = confined(': > /dev/tcp/127.0.0.1/22')
    assert loopback.returncode != 0
    record('D03-loopback-boundary', root_receiver_reachable=True, managed_exit=loopback.returncode)
    try:
        subprocess.run(['systemctl', 'stop', service], check=True)
        started = time.monotonic()
        deadline = started + policy['max_heartbeat_age'] + 8
        while time.monotonic() < deadline:
            print(json.dumps(dict(progress='real-heartbeat-expiry', seconds_remaining=round(deadline-time.monotonic()))), flush=True)
            time.sleep(min(25, max(0, deadline-time.monotonic())))
        claims = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '=='))
        assert claims['exp'] > time.time(), 'Expiry test must use an unexpired JWT'
        status, policy_id = admission(token)
        assert status == 403 and policy_id == 'ENDPOINT-MANAGED-001', (status, policy_id)
        try:
            managed.request(config, '/oauth/device-token', {})
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError('Stale heartbeat minted a token')
        record('D04-stale-heartbeat', waited_seconds=round(time.monotonic()-started, 2),
               token_unexpired=True, admission=status, policy_id=policy_id, mint_status=403)
    finally:
        subprocess.run(['systemctl', 'start', service], check=True)
        beat()
        assert subprocess.run(['systemctl', 'is-active', '--quiet', service]).returncode == 0
    fresh = managed.request(config, '/oauth/device-token', {})['access_token']
    status, _ = admission(fresh)
    assert status == 200
    record('D05-recovery', admission=status, service_restored=True)
    print(json.dumps(dict(result='passed', evidence=evidence, database_reset=False)), flush=True)


if __name__ == '__main__':
    main()
