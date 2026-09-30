"""Opt-in real Notion metadata review: no ack refused, exact ack ready, bad hash blocked.

Run as the Gateway runtime UID in its image, after the seven-server check finishes.
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


async def run(args):
    identity = json.load(sys.stdin)
    row = next(r for r in json.loads(Path(args.reviewed).read_text()) if r['server'] == 'notion')
    assert row.get('warning_review') and len(row['warning_tools']) == 1
    tool = row['warning_tools'][0]
    assert tool['name'] == 'notion-check-mcp-next-steps'
    server = 'review-check-' + uuid4().hex[:10]
    request = {'server_id': server, 'display_name': 'Live metadata review verification',
               'endpoint': row['endpoint'], 'catalog_hash': row['catalog_hash'],
               'tools': {tool['name']: 'r'}, 'data_class': 'important', 'valid_days': 1,
               'purpose': 'Authorized metadata review check; provider helper is not executed on success'}
    registered = False
    async with httpx.AsyncClient(base_url=args.url, timeout=90, trust_env=False) as api:
        login = await api.post('/api/session', json=identity);login.raise_for_status()
        api.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
        try:
            denied = await api.post('/api/registry/servers', json=request)
            assert denied.status_code == 409, 'flagged selected tool accepted without review'
            accepted = await api.post('/api/registry/servers', json={**request, 'poisoning_ack': True})
            accepted.raise_for_status();registered = True
            assert accepted.json()['status'] == 'READY', accepted.json()
            doc = registry.runtime()
            approved = doc['servers'][server]['poisoning_review'][tool['name']]
            assert approved == registry.tool_hashes(tool), 'review was not bound to real tool hashes'
            doc['servers'][server]['poisoning_review'][tool['name']] = {**approved, 'description_sha256': '0' * 64}
            registry.save_runtime(doc)
            refreshed = await api.post('/api/catalog/refresh');refreshed.raise_for_status()
            async with httpx2.AsyncClient(timeout=90, headers=dict(api.headers)) as transport:
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
            await api.post('/api/logout')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--reviewed', required=True)
    asyncio.run(run(parser.parse_args()))
