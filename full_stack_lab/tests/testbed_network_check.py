#!/usr/bin/env python3
"""Fresh Docker testbed: real gateway via fixed Caddy relay, direct vendor TLS blocked.

Run on the SSH test VM with the native test image already built. The restriction
applies to this container, not to every process on the host. No mock MCP or model.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mcpgw/native-clean:20260930')
    parser.add_argument('--gateway', default='http://100.83.175.111:443')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    gateway = urlsplit(args.gateway)
    assert gateway.scheme == 'http' and gateway.hostname and gateway.port and not gateway.username
    names = ['mcpgw-network-clean-relay', 'mcpgw-network-clean-client']
    network = 'mcpgw-network-clean-office'
    created = []
    code = '''import json,socket,ssl,urllib.request
from urllib.parse import urlsplit
from pathlib import Path
import importlib.util
spec=importlib.util.spec_from_file_location('probe','/validation/tests/real_mcp_check.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
result={}
for name,url in probe.SERVERS.items():
    host=urlsplit(url).hostname
    try:
        with socket.create_connection((host,443),timeout=3) as sock:
            with ssl.create_default_context().wrap_socket(sock,server_hostname=host):pass
        result[name]=True
    except (OSError,TimeoutError):result[name]=False
with urllib.request.urlopen('http://relay/api/health',timeout=10) as response:
    health=json.load(response)
print(json.dumps({'vendor_tls_connected':result,'real_gateway_status':health['status']}))
'''
    try:
        docker('network', 'create', '--internal', network)
        with tempfile.TemporaryDirectory(prefix='mcpgw-network-clean-') as temp:
            config = Path(temp) / 'Caddyfile'
            config.write_text(':80 {\n reverse_proxy ' + f'{gateway.hostname}:{gateway.port}' + '\n}\n')
            docker('run', '-d', '--name', names[0], '--network', network, '--network-alias', 'relay',
                   '-v', f'{config}:/etc/caddy/Caddyfile:ro', 'caddy:2.10.2')
            created.append(names[0])
            docker('network', 'connect', 'bridge', names[0])
            docker('run', '-d', '--name', names[1], '--network', network, '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges', args.image)
            created.append(names[1])
            docker('network', 'connect', 'bridge', names[1])
            positive = json.loads(docker('exec', names[1], 'python3', '-c', code))
            assert all(positive['vendor_tls_connected'].values()), 'real vendor TLS positive control failed'
            docker('network', 'disconnect', 'bridge', names[1])
            restricted = json.loads(docker('exec', names[1], 'python3', '-c', code))
            state = json.loads(docker('inspect', names[1]))[0]
            assert set(state['NetworkSettings']['Networks']) == {network}
            assert json.loads(docker('network', 'inspect', network))[0]['Internal'] is True
            assert not any(restricted['vendor_tls_connected'].values()), 'direct vendor TLS escaped internal network'
            assert restricted['real_gateway_status'] in {'ok', 'healthy'}, 'fixed real gateway relay failed'
            report = {'testbed': 'fresh SSH VM Docker internal network, fixed real gateway relay',
                      'positive': positive, 'restricted': restricted, 'native_image': state['Image'],
                      'network_internal': True, 'client_networks': list(state['NetworkSettings']['Networks']),
                      'client_cap_drop': state['HostConfig']['CapDrop'], 'network_check': 'PASS',
                      'model_invoked': False, 'mock_server_used': False,
                      'scope': 'disposable container only; host processes and untested destinations are outside this proof'}
            Path(args.out).write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report))
    finally:
        for name in reversed(created):
            docker('rm', '-f', name)
        if created:
            docker('network', 'rm', network)


if __name__ == '__main__':
    main()
