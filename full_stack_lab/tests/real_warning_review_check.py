"""Opt-in real Notion metadata review: no ack refused, exact ack ready, bad hash blocked.

Run as the Gateway runtime UID in its image, after the seven-server check finishes.
stdin: {"requester": {email,password}, "approver": {email,password}} (D-57 intake, two people).
This modifies only its own temporary registry entry and removes it in finally.
No mock MCP, model, or invocation of the provider's flagged helper on the passing path.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from app import registry
from intake_register import _call, login, register


async def run(args):
    identities = json.load(sys.stdin)
    requester, approver = login(args.console, identities['requester']), login(args.console, identities['approver'])
    row = next(r for r in json.loads(Path(args.reviewed).read_text()) if r['server'] == 'notion')
    assert row.get('warning_review') and len(row['warning_tools']) == 1
    tool = row['warning_tools'][0]
    assert tool['name'] == 'notion-check-mcp-next-steps'
    server = 'review-check-' + uuid4().hex[:10]
    scope = {'server_id': server, 'endpoint': row['endpoint'], 'catalog_hash': row['catalog_hash'],
             'tools': {tool['name']: 'r'}, 'data_class': 'important', 'valid_days': 1, 'poisoning_ack': False}
    who = _call(args.console, 'GET', '/auth/me', requester)
    # The server, not this client, must refuse a review that selects a flagged tool unacknowledged.
    pending = _call(args.console, 'POST', '/api/mcp-requests', requester, {
        'display_name': 'Live metadata review verification', 'intake_kind': 'remote-endpoint',
        'endpoint_url': row['endpoint'], 'requested_transport': 'streamable-http',
        'purpose': 'Authorized metadata review check; provider helper is not executed on success'})['request']
    async with httpx.AsyncClient(timeout=90, trust_env=False) as console:
        denied = await console.post(f"{args.console}/api/mcp-requests/{pending['id']}/review-contract",
                                    headers={'Authorization': 'Bearer ' + approver},
                                    json={**scope, 'allowed_principals': [who['user_id']], 'review_note': 'no acknowledgement on purpose'})
        await console.post(f"{args.console}/api/mcp-requests/{pending['id']}/reject",
                           headers={'Authorization': 'Bearer ' + approver}, json={'note': 'warning review check cleanup'})
    assert denied.status_code == 409, 'flagged selected tool accepted without review'
    registered = False
    async with httpx.AsyncClient(base_url=args.url, timeout=90, trust_env=False,
                                 headers={'Authorization': 'Bearer ' + approver}) as api:
        try:
            accepted = register(args.console, requester, approver, endpoint=row['endpoint'], server_id=server,
                                name='Live metadata review verification', tools=scope['tools'], data_class='important',
                                valid_days=1, allowed=[who['user_id']], ack_warnings=True,
                                purpose='Authorized metadata review check; provider helper is not executed on success',
                                review_note='Read the flagged description; selected for the review-binding check only.',
                                risk_acceptance='One-day verification of the review binding; the helper is not run on success.')
            registered = True
            assert accepted['status'] == 'READY', accepted
            doc = registry.runtime()
            approved = doc['servers'][server]['poisoning_review'][tool['name']]
            assert approved == registry.tool_hashes(tool), 'review was not bound to real tool hashes'
            doc['servers'][server]['poisoning_review'][tool['name']] = {**approved, 'description_sha256': '0' * 64}
            registry.save_runtime(doc)
            refreshed = await api.post('/api/catalog/refresh');refreshed.raise_for_status()
            async with httpx2.AsyncClient(timeout=90, headers={'Authorization': 'Bearer ' + requester}) as transport:
                async with Client(streamable_http_client(args.url + '/mcp/' + server + '/', http_client=transport)) as client:
                    await client.list_tools()
                    answer = await client.call_tool(tool['name'], {})
            meta = (answer.meta or {}).get('gateway') or {}
            assert meta['decision'] == 'Block' and meta['policy_id'] == 'MCP-CATALOG-001', meta
            assert meta['upstream_attempted'] is False and meta['upstream_executed'] is False, meta
            print(json.dumps({'real_warning_review_check': 'PASS', 'server': 'notion', 'tool': tool['name'],
                              'no_ack_status': denied.status_code, 'exact_review_status': 'READY',
                              'mismatched_review': meta, 'model_invoked': False, 'mock_server_used': False}))
        finally:
            if registered:
                removed = await api.delete('/api/registry/servers/' + server);removed.raise_for_status()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--console', default='http://agent-service:8000')
    parser.add_argument('--reviewed', required=True)
    asyncio.run(run(parser.parse_args()))
