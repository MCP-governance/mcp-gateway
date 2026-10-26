"""Hold the app-internal import boundaries; stdlib ast only, product modules are never imported.

Edges are importer -> imported among gateway/app/*.py, eager and lazy (inside a function) together.
Class bodies and top-level if/try count as eager. A contract here reads like import-linter's
layers/forbidden types, but this is not that engine: only the shapes below are checked.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

LEAVES = ('contract', 'db', 'connections', 'destination', 'textscan')
# Higher layers may import lower ones; same-layer imports are free.
LAYERS = (('main',), ('agent_service', 'core'), LEAVES)
# core's remaining direct dependencies are frozen; one that disappears is a failure so the list must shrink with it.
CORE_FANOUT = frozenset((
    'classify connections consent contract db destination dispatch disposal endpoint_plane flow_fingerprint '
    'high_impact intake_proposal litellm_sync local_jobs mcp_sessions ops_response outcomes output_contract pac '
    'poisoning privacy registry residency retention review risk_tier secret_scan selective supplier_assurance '
    'tool_sunset upstream user_credentials user_suspend').split())
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def scan(sources):
    """{module: source} -> {(importer, imported): {'E', 'L'}}"""
    modules, edges = set(sources), {}
    for importer, source in sources.items():
        def add(target, lazy):
            if target in modules and target != importer:
                edges.setdefault((importer, target), set()).add('L' if lazy else 'E')

        def walk(node, lazy):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.Import):
                    for item in child.names:
                        parts = item.name.split('.')
                        if parts[0] == 'app' and len(parts) > 1:
                            add(parts[1], lazy)
                elif isinstance(child, ast.ImportFrom):
                    base = child.module.split('.') if child.module else []
                    if child.level == 1:
                        package = base
                    elif child.level == 0 and base[:1] == ['app']:
                        package = base[1:]
                    else:
                        continue
                    if package:
                        add(package[0], lazy)
                    else:
                        for item in child.names:
                            add(item.name, lazy)
                else:
                    walk(child, lazy or isinstance(child, FUNCTIONS))
        walk(ast.parse(source, filename=importer + '.py'), False)
    return edges


def reachable(edges, start):
    out = {}
    for src, dst in edges:
        out.setdefault(src, set()).add(dst)
    seen, stack = set(), [start]
    while stack:
        for nxt in out.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def check(edges):
    """-> (violations, stale exceptions)"""
    pairs = set(edges)
    bad = []
    for i, layer in enumerate(LAYERS):
        above = {m for upper in LAYERS[:i] for m in upper}
        for module in layer:
            bad += [f'layers: {module} reaches {m}' for m in sorted(reachable(pairs, module) & above)]
    bad += [f'leaf-boundary: {s} -> {d}' for s, d in sorted(pairs) if s in LEAVES]
    bad += ['console-core: agent_service -> core'] * (('agent_service', 'core') in pairs)
    bad += [f'core-fanout: core -> {d}' for s, d in sorted(pairs) if s == 'core' and d not in CORE_FANOUT]
    stale = [f'core-fanout: core -> {d}' for d in sorted(CORE_FANOUT) if ('core', d) not in pairs]
    return bad, stale


def self_test(edges, modules):
    cases = {
        'from . import b\n': {('a', 'b'): {'E'}},
        'from .b import x, y\n': {('a', 'b'): {'E'}},
        'from app.b import x\n': {('a', 'b'): {'E'}},
        'from app import b\n': {('a', 'b'): {'E'}},
        'import app.b as bb\n': {('a', 'b'): {'E'}},
        'class K:\n    from . import b\n': {('a', 'b'): {'E'}},
        'try:\n    from . import b\nexcept ImportError:\n    pass\n': {('a', 'b'): {'E'}},
        'def f():\n    from . import b\n': {('a', 'b'): {'L'}},
        'async def f():\n    def g():\n        from .b import x\n': {('a', 'b'): {'L'}},
        'from . import b\ndef f():\n    from . import b\n': {('a', 'b'): {'E', 'L'}},
        'import os\nfrom . import zzz\nfrom .a import q\nfrom ..b import x\nfrom other import b\n': {},
    }
    for source, expected in cases.items():
        assert scan({'a': source, 'b': ''}) == expected, source
    # An empty or misrooted scan must not read as "no violations".
    assert len(modules) > 50 and len(edges) > 200, (len(modules), len(edges))
    named = set(CORE_FANOUT) | {m for layer in LAYERS for m in layer}
    assert named <= modules, sorted(named - modules)

    def with_edge(src, dst):
        return {**edges, (src, dst): {'E'}}
    expect = [
        ('contract', 'core', 'leaf-boundary: contract -> core'),
        ('contract', 'core', 'layers: contract reaches core'),
        ('db', 'audit', 'leaf-boundary: db -> audit'),
        ('core', 'audit', 'core-fanout: core -> audit'),
        ('agent_service', 'core', 'console-core: agent_service -> core'),
        ('core', 'main', 'layers: core reaches main'),
        ('destination', 'agent_service', 'layers: destination reaches agent_service'),
    ]
    for src, dst, message in expect:
        assert message in check(with_edge(src, dst))[0], (src, dst, message)
    for pair in sorted(('core', d) for d in CORE_FANOUT):
        without = {k: v for k, v in edges.items() if k != pair}
        assert check(without)[1], pair
    print(f'PASS import_contract self-test ({len(cases) + len(expect) + 2} cases)')


def main():
    root = Path(__file__).resolve().parents[1] / 'gateway/app'
    sources = {p.stem: p.read_text(encoding='utf-8') for p in sorted(root.glob('*.py')) if p.stem != '__init__'}
    edges = scan(sources)
    self_test(edges, set(sources))
    bad, stale = check(edges)
    for line in bad:
        print('FAIL ' + line)
    for line in stale:
        print('STALE exception ' + line)
    print(f'import_contract: modules={len(sources)} edges={len(edges)} violations={len(bad)} stale_exceptions={len(stale)}')
    return int(bool(bad or stale))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'FAIL import_contract: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
