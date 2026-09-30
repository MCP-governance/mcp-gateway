"""Report the code in this image and the policy actually loaded by OPA."""
import hashlib
import os
from functools import lru_cache
from pathlib import Path

import httpx


@lru_cache(maxsize=1)
def build_info() -> dict:
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.suffix in {'.py', '.sql', '.js', '.mjs', '.html', '.css'}:
            digest.update(str(path.relative_to(root)).encode() + b'\0' + path.read_bytes())
    return {'revision': os.getenv('MCP_BUILD_REVISION', 'unknown'), 'code_sha256': digest.hexdigest()}


async def policy_info(opa_url: str) -> dict:
    expected = hashlib.sha256(Path('/policy/policy.rego').read_bytes()).hexdigest()
    result = {'expected_sha256': expected, 'loaded_sha256': None, 'matches': False}
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(opa_url.split('/v1/')[0] + '/v1/policies')
            response.raise_for_status()
        rules = [p for p in response.json()['result'] if p['id'].endswith('/policy.rego') or p['id'] == 'policy.rego']
        if len(rules) == 1:
            result['loaded_sha256'] = hashlib.sha256(rules[0]['raw'].encode()).hexdigest()
            result['matches'] = result['loaded_sha256'] == expected
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        pass
    return result
