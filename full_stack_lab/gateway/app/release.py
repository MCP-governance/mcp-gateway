"""Report the code in this image and the policy actually loaded by OPA."""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

import httpx

from . import cache, connections


# The files a Linux install copies to the PC (endpoint-agent/managed-linux.py PROGRAM_FILES). The digest of their
# text is the kit version: the PC's status command prints the digest of what it installed, /api/health this one.
KIT_PROGRAMS = ('managed-linux.py', 'enforce-linux.py', 'broker_binding.py', 'agent.py', 'os-observer.py',
                'offline_buffer.py', 'local-runner.py', 'stdio_source.py', 'stdio_windows.py', 'kit_screen.py', 'kit_access.py')


def kit_sha256() -> str | None:
    folder = Path(os.getenv('ENDPOINT_KIT_DIR', '/endpoint-kit'))
    digest = hashlib.sha256()
    try:
        for name in KIT_PROGRAMS:
            digest.update(name.encode() + b'\0' + (folder / name).read_bytes().replace(b'\r\n', b'\n'))
    except OSError:
        return None
    return digest.hexdigest()


@lru_cache(maxsize=1)
def _code_info() -> dict:
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


def build_info() -> dict:
    # The kit is a bind mount that changes without a restart, so its version is read per call, not cached.
    info = dict(_code_info())
    info['pc_kit_sha256'] = kit_sha256() or info['pc_kit_sha256']
    return info


# Compare all PAC/routing modules and policy data. Reviewed capability scopes have a
# separate hash because they are enforced by the Gateway adapter, not OPA data documents.
POLICY_DATA_FILES = ('data.json', 'policy_ledger.json', 'residency.json')


def _canonical(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


# /api/health is unauthenticated and reads every file below on every call. Keyed by
# (mtime_ns, size) rather than a TTL: these are reviewed files that change on deploy,
# not on a clock, so a correct answer never has to wait out a cache window.
_file_cache: dict[Path, tuple[tuple[int, int], object]] = {}


def _cached(path: Path, loader):
    stat = path.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    cached = _file_cache.get(path)
    if cached is not None and cached[0] == key:
        return cached[1]
    value = loader(path)
    _file_cache[path] = (key, value)
    return value


# The other half of the same call is two round trips to OPA (rules + one per data
# document). OPA's loaded policy does not change between two /api/health calls a
# few seconds apart, so that half is worth a short TTL on top of the file cache above.
_opa_query_cache = cache.TTLCache(5)


async def _query_opa(opa_url: str, modules: tuple[str, ...], document_keys: tuple[str, ...]) -> dict:
    base = opa_url.split('/v1/')[0]
    client = connections.shared('opa', lambda: httpx.AsyncClient(timeout=5))
    result = {'loaded_sha256': None, 'loaded_data_sha256': None}
    response = await client.get(base + '/v1/policies', timeout=3)
    response.raise_for_status()
    rules = {p['id'].rsplit('/', 1)[-1]: p['raw'] for p in response.json()['result']
             if p['id'].rsplit('/', 1)[-1] in modules}
    if set(rules) == set(modules):
        result['loaded_sha256'] = _canonical({name: hashlib.sha256(rules[name].encode()).hexdigest() for name in modules})
    loaded = {}
    for key in document_keys:
        answer = (await client.get(f'{base}/v1/data/{key}', timeout=3)).json()
        if 'result' not in answer:
            break  # a document the files define and OPA does not serve
        loaded[key] = answer['result']
    else:
        result['loaded_data_sha256'] = _canonical(loaded)
    return result


async def policy_info(opa_url: str, *, cached: bool = False) -> dict:
    # Only the unauthenticated health view may reuse answers. The policy self-test swaps OPA's
    # policy and must see the change at once, and must not trust (mtime, size) to detect edits.
    read = _cached if cached else (lambda path, loader: loader(path))
    root = Path('/policy')
    modules = ('policy.rego', 'pac15.rego', 'decision.rego')
    expected = _canonical({name: read(root / name, lambda p: hashlib.sha256(p.read_bytes()).hexdigest())
                           for name in modules})
    documents: dict = {}
    for name in POLICY_DATA_FILES:
        documents.update(read(root / name, lambda p: json.loads(p.read_text(encoding='utf-8'))))
    result = {'expected_sha256': expected, 'loaded_sha256': None,
              'expected_data_sha256': _canonical(documents), 'loaded_data_sha256': None,
              'rules_match': False, 'data_match': False, 'matches': False}
    from . import registry
    result['capabilities_sha256'] = read(registry.REGISTRY_DIR / 'capabilities.json',
                                            lambda p: hashlib.sha256(p.read_bytes()).hexdigest())
    try:
        query = lambda: _query_opa(opa_url, modules, tuple(documents))  # noqa: E731
        loaded = await (_opa_query_cache.get(opa_url, query) if cached else query())
        result['loaded_sha256'] = loaded['loaded_sha256']
        result['rules_match'] = loaded['loaded_sha256'] == expected
        result['loaded_data_sha256'] = loaded['loaded_data_sha256']
        result['data_match'] = loaded['loaded_data_sha256'] == result['expected_data_sha256']
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        pass
    result['matches'] = result['rules_match'] and result['data_match']
    return result
