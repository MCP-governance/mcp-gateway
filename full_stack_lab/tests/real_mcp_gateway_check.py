"""Review seven live contracts, then test only explicitly selected reads through Gateway.

python /tests/real_mcp_gateway_check.py --url http://gateway:8080 --review-out /output/review.json
python /tests/real_mcp_gateway_check.py --url http://gateway:8080 --reviewed /output/review.json
Both commands read {"requester": {email,password}, "approver": {email,password}} from stdin
(D-57: the requester never approves). No vendor credentials enter this client.
The second command registers temporary, expiring, read-only entries through the intake
(request -> contract review -> approval -> activation) and removes them.
"""
import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from intake_register import login, register
from real_mcp_check import SERVERS, SMOKE


async def run(args):
    identities = json.load(sys.stdin)
    approver = login(args.console, identities["approver"])
    async with httpx.AsyncClient(timeout=90, headers={'Authorization': 'Bearer ' + approver}) as api:
        if args.review_out:
            review = []
            for name, endpoint in SERVERS.items():
                response = await api.post(args.url + '/api/registry/discover', json={'endpoint': endpoint})
                response.raise_for_status()
                catalog = response.json()
                tool = SMOKE[name][0]
                selected = next(t for t in catalog['tools'] if t['name'] == tool)
                review.append({'server': name, 'endpoint': endpoint, 'catalog_hash': catalog['catalog_hash'],
                               'version': catalog['version'], 'selected_tool': selected,
                               'warning_tools': [t for t in catalog['tools'] if t['warnings']],
                               'catalog_warnings': {t['name']: t['warnings'] for t in catalog['tools'] if t['warnings']}})
            Path(args.review_out).write_text(json.dumps(review, ensure_ascii=False, indent=2))
            print(json.dumps({'review': args.review_out, 'servers': len(review),
                              'warnings': {r['server']: r['catalog_warnings'] for r in review}}, ensure_ascii=False))
            return
        requester = login(args.console, identities["requester"])
        who = (await api.get(args.console + '/auth/me', headers={'Authorization': 'Bearer ' + requester})).json()
        review = {r['server']: r for r in json.loads(Path(args.reviewed).read_text())}
        prefix = 'probe-' + uuid4().hex[:8] + '-'
        results = []
        for name, endpoint in SERVERS.items():
            row = review[name]
            tool, arguments = SMOKE[name]
            assert row['endpoint'] == endpoint and row['selected_tool']['name'] == tool
            assert not row['catalog_warnings'] or row.get('warning_review'), (
                'Warnings need an explicit content review in the pinned review file; do not auto-acknowledge')
            server_id = prefix + name
            registered = False
            try:
                register(args.console, requester, approver, endpoint=endpoint, server_id=server_id,
                         name='Live verification ' + name, tools={tool: 'r'}, data_class='important', valid_days=1,
                         parameter_constraints=row['parameter_constraints'],
                         allowed=[who['user_id']], ack_warnings=bool(row['catalog_warnings'] and row.get('warning_review')),
                         purpose='Authorized live vendor read verification; no writes, messages, or production enrollment',
                         review_note='Pinned review file: selected read tool only, one-day verification window.',
                         risk_acceptance='Provider-hosted service; only the selected read tool runs for one day.')
                registered = True
                async with httpx2.AsyncClient(timeout=90, headers={'Authorization': 'Bearer ' + requester}) as http:
                    async with Client(streamable_http_client(args.url + '/mcp/' + server_id + '/', http_client=http)) as client:
                        # The SDK learns x-mcp-header annotations from tools/list and
                        # then emits matching Mcp-Param-* headers on modern calls.
                        listed = await client.list_tools()
                        assert [t.name for t in listed.tools] == [tool], 'unapproved tool exposed by temporary entry'
                        answer = await client.call_tool(tool, arguments)
                meta = (answer.meta or {}).get('gateway') or {}
                data = json.dumps([c.model_dump(mode='json') for c in answer.content]).encode()
                result = {'server': name, 'server_id': server_id, 'tool': tool, 'gateway_traversed': True,
                          'model_invoked': False, 'mcp_is_error': answer.is_error,
                          'decision': meta.get('decision'), 'policy_id': meta.get('policy_id'),
                          'decision_id': meta.get('decision_id'), 'response_bytes': len(data),
                          'upstream_attempted': meta.get('upstream_attempted'),
                          'upstream_executed': meta.get('upstream_executed'),
                          'response_sha256': hashlib.sha256(data).hexdigest()}
                assert result['decision'] in {'Allow', 'Alert', 'Restrict'} and not answer.is_error, result
                assert result['upstream_attempted'] is True and result['upstream_executed'] is True, result
                results.append(result)
                print(json.dumps(result), flush=True)
            finally:
                if registered:
                    removed = await api.delete(args.url + '/api/registry/servers/' + server_id)
                    removed.raise_for_status()
        assert len(results) == 7


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--console', default='http://agent-service:8000')
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--review-out')
    choice.add_argument('--reviewed')
    asyncio.run(run(parser.parse_args()))
