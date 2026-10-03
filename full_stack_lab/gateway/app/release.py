"""Report the code in this image and the policy actually loaded by OPA."""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

import httpx


@lru_cache(maxsize=1)
def build_info() -> dict:
    root = Path(__file__).parent
    kit = root / 'agent_static/kit/mcpgw_pc.py'
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        # The field PC kit is published by a Console-only bind mount, not baked into this app image.
        if path == kit:
            continue
        if path.is_file() and path.suffix in {'.py', '.sql', '.js', '.mjs', '.html', '.css'}:
            digest.update(str(path.relative_to(root)).encode() + b'\0' + path.read_bytes())
    return {'revision': os.getenv('MCP_BUILD_REVISION', 'unknown'), 'code_sha256': digest.hexdigest(),
            'pc_kit_sha256': hashlib.sha256(kit.read_bytes()).hexdigest() if kit.is_file() else None}


# Compare all PAC/routing modules and policy data. Reviewed capability scopes have a
# separate hash because they are enforced by the Gateway adapter, not OPA data documents.
POLICY_DATA_FILES = ('data.json', 'policy_ledger.json')


def _canonical(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


async def policy_info(opa_url: str) -> dict:
    root = Path('/policy')
    modules = ('policy.rego', 'pac15.rego', 'decision.rego')
    expected = _canonical({name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in modules})
    documents: dict = {}
    for name in POLICY_DATA_FILES:
        documents.update(json.loads((root / name).read_text(encoding='utf-8')))
    result = {'expected_sha256': expected, 'loaded_sha256': None,
              'expected_data_sha256': _canonical(documents), 'loaded_data_sha256': None,
              'rules_match': False, 'data_match': False, 'matches': False}
    from . import registry
    result['capabilities_sha256'] = hashlib.sha256((registry.REGISTRY_DIR/'capabilities.json').read_bytes()).hexdigest()
    base = opa_url.split('/v1/')[0]
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(base + '/v1/policies')
            response.raise_for_status()
            rules = {p['id'].rsplit('/',1)[-1]: p['raw'] for p in response.json()['result']
                     if p['id'].rsplit('/',1)[-1] in modules}
            if set(rules) == set(modules):
                result['loaded_sha256'] = _canonical({name: hashlib.sha256(rules[name].encode()).hexdigest() for name in modules})
                result['rules_match'] = result['loaded_sha256'] == expected
            loaded = {}
            for key in documents:
                answer = (await client.get(f'{base}/v1/data/{key}')).json()
                if 'result' not in answer:
                    break  # a document the files define and OPA does not serve
                loaded[key] = answer['result']
            else:
                result['loaded_data_sha256'] = _canonical(loaded)
                result['data_match'] = result['loaded_data_sha256'] == result['expected_data_sha256']
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        pass
    result['matches'] = result['rules_match'] and result['data_match']
    return result
