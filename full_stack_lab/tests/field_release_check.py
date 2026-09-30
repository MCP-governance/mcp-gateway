"""Run on the clean SSH VM: verify field release and a real Microsoft Learn read.

Receives {email,password} on stdin. Prints only release, scope status, decision and
response digest; no token, provider response body or model invocation.
"""
import argparse
import asyncio
import hashlib
import json
import sys

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def run(args):
    identity = json.load(sys.stdin)
    async with httpx.AsyncClient(base_url=args.url, timeout=90, trust_env=False) as api:
        health = (await api.get('/gw/api/health')).json()
        ready = (await api.get('/api/readiness')).json()
        assert health['status'] == 'ok' and ready['status'] == 'ready'
        assert health['build']['revision'] == args.expected_revision
        assert ready['build']['console']['revision'] == args.expected_revision
        assert ready['build']['consistent'] and ready['policy']['matches']
        response = await api.post('/gw/api/session', json=identity)
        response.raise_for_status()
        console_token = response.json()['access_token']
        api.headers['Authorization'] = 'Bearer ' + console_token
        registry = (await api.get('/gw/api/registry')).json()
        # The operator specifies the already-approved server; no automatic enrollment.
        server_ids = [s['id'] for s in registry['servers']]
        assert args.server in server_ids, server_ids
        grant = await api.post('/oauth/token', data={'grant_type': 'password', 'username': identity['email'],
                                                   'password': identity['password'], 'client_id': 'clean-ssh-verification'})
        grant.raise_for_status()
        token = grant.json()['access_token']
        try:
            denied = await api.get('/gw/api/state', headers={'Authorization': 'Bearer ' + token})
            assert denied.status_code == 403, 'MCP token reached field control plane'
            async with httpx2.AsyncClient(timeout=90, trust_env=False, headers={
                    'Authorization': 'Bearer ' + token, 'X-Agent-Name': 'clean-ssh-sdk',
                    'X-Workstation-Id': 'ssh-test-vm'}) as transport:
                async with Client(streamable_http_client(args.url + '/mcp/' + args.server + '/',
                                                        http_client=transport)) as client:
                    tools = (await client.list_tools()).tools
                    selected = next(t for t in tools if t.name == 'microsoft_docs_search')
                    assert 'query' in selected.input_schema['properties']
                    result = await client.call_tool(selected.name, {'query': 'Microsoft MCP security documentation'})
            meta = (result.meta or {}).get('gateway') or {}
            assert meta['decision'] in {'Allow', 'Alert', 'Restrict'} and not result.is_error
            assert meta['upstream_attempted'] and meta['upstream_executed']
            body = json.dumps([c.model_dump(mode='json') for c in result.content]).encode()
            report = {'field_release_check': 'PASS', 'vm': '100.110.81.60', 'gateway': args.url,
                      'build': health['build'], 'policy': health['policy'], 'mcp_admin_status': denied.status_code,
                      'server': args.server, 'tool': selected.name, 'decision_id': meta['decision_id'],
                      'decision': meta['decision'], 'policy_id': meta['policy_id'],
                      'upstream_attempted': True, 'upstream_executed': True,
                      'response_bytes': len(body), 'response_sha256': hashlib.sha256(body).hexdigest(),
                      'model_invoked': False, 'mock_server_used': False}
            print(json.dumps(report))
        finally:
            await api.post('/oauth/revoke', data={'token': token, 'token_type_hint': 'access_token'})
            await api.post('/oauth/revoke', data={'token': grant.json()['refresh_token'], 'token_type_hint': 'refresh_token'})
            await api.post('/gw/api/logout')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--server', required=True)
    parser.add_argument('--expected-revision', required=True)
    asyncio.run(run(parser.parse_args()))
