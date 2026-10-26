"""Reject pool re-entry while a connection is held; no application imports or database needed.

This follows named module/local functions and explicit connection arguments, including
positional ones. Dynamic dispatch, object attributes and runtime SQL are outside this check.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# A reason belongs to the function that needs the extra acquisition, not every caller.
ALLOW = {
    ('local_jobs.py', 'prepare_token_revocation'): '토큰 advisory 잠금은 새 start를 막고, 별도 커밋한 중지 UPDATE는 장치와 complete의 stopped_at 기록에 보여야 한다. 같은 연결의 UPDATE는 완료 행을 잠근다.',
    ('user_suspend.py', 'suspend'): '재개와 중지를 직렬화한 채 quiesce가 별도 커밋으로 중지 요청을 게시하고 장치의 정지 응답을 기다린다. 동시 작업은 풀 절반으로 제한한다.',
    ('litellm_sync.py', 'reconcile'): '세션 잠금으로 외부 동기화 작성자를 직렬화한다. 내부 작업은 독립 커밋하며 설정 검사가 풀 최소 2개를 요구한다.',
    ('ops_response.py', 'tick'): '트랜잭션을 커밋한 세션 잠금 연결로 두 프로세스의 작업 전체를 배제한다. 내부 작업은 독립 커밋하며 finally에서 잠금을 풀거나 연결을 닫는다.',
    ('review.py', 'require_independent'): '본인 승인 거부 기록은 호출자의 롤백 뒤에도 감사 원장에 남아야 하므로 별도 연결로 append한다.',
    ('oidc.py', '_refresh_upstream'): '외부 IdP 갱신과 회전 토큰 저장을 FOR UPDATE로 직렬화해야 같은 refresh token 재사용에 따른 계열 폐기를 막는다.',
    ('siem.py', 'deliver_one'): '기존 스키마에는 소유자와 claimed_until이 없다. SKIP LOCKED를 ACK와 완료 커밋까지 유지해 최소 1회 전달과 동시 중복 배제를 보존한다.',
}
CONNECTIONS = {'connection', 'conn', 'lock', 'snapshot', 'guard'}
DB_CALLS = {'fetch_one', 'fetch_all', 'execute', 'transaction'}
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


class Check:
    def __init__(self, sources):
        self.trees = {m: ast.parse(s, filename=m + '.py') for m, s in sources.items()}
        self.functions = {}
        self.imports = {}
        for module, tree in self.trees.items():
            aliases = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 1:
                    for item in node.names:
                        aliases[item.asname or item.name] = (node.module or item.name, item.name if node.module else None)
            self.imports[module] = aliases
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.functions[module, node.name] = node
        self.pool_names = {module: set() for module in self.trees}
        for module, tree in self.trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    value = node.value.value if isinstance(node.value, ast.Await) else node.value
                    if isinstance(value, ast.Call) and self.target(module, value) == ('db', 'pool'):
                        self.pool_names[module].update(t.id for t in node.targets if isinstance(t, ast.Name))
        self.cache = {}

    def target(self, module, call):
        func = call.func
        if isinstance(func, ast.Name):
            return self.imports[module].get(func.id, (module, func.id))
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            base = func.value.id
            imported = self.imports[module].get(base, (base, None))
            if imported[1] is None:
                return imported[0], func.attr
        return None

    def known(self, node, bound):
        if isinstance(node, ast.Constant) and node.value is None:
            return False
        if isinstance(node, ast.Name) and node.id in bound:
            return True
        return None

    def condition(self, node, bound):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.comparators[0], ast.Constant) and node.comparators[0].value is None:
            value = self.known(node.left, bound)
            if value is not None:
                if isinstance(node.ops[0], (ast.Is, ast.Eq)):
                    return not value
                if isinstance(node.ops[0], (ast.IsNot, ast.NotEq)):
                    return value
        if isinstance(node, ast.Name) and node.id in bound:
            return True
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            value = self.condition(node.operand, bound)
            return None if value is None else not value
        return None

    def supplied(self, call, function, bound):
        params = function.args.posonlyargs + function.args.args
        pairs = [(p.arg, a) for p, a in zip(params, call.args)]
        pairs += [(k.arg, k.value) for k in call.keywords]
        return frozenset(name for name, value in pairs if self.known(value, bound) is True)

    def acquisition(self, module, call, bound):
        target = self.target(module, call)
        if target and target[0] == 'db' and target[1] in DB_CALLS:
            supplied = next((k.value for k in call.keywords if k.arg == 'connection'), None)
            if supplied is not None and self.known(supplied, bound) is True:
                return None
            return 'db.' + target[1]
        if isinstance(call.func, ast.Attribute) and call.func.attr == 'connection':
            value = call.func.value
            if isinstance(value, ast.Await):
                value = value.value
            if isinstance(value, ast.Name) and value.id in self.pool_names[module]:
                return 'db.pool().connection'
            if isinstance(value, ast.Call) and self.target(module, value) == ('db', 'pool'):
                return 'db.pool().connection'
        return None

    def effects(self, key, bound, active=()):
        state = key, bound
        if state in active or key not in self.functions or key[0] == 'db':
            return []
        if state in self.cache:
            return self.cache[state]
        result = self.nodes(key[0], self.functions[key].body, bound, active + (state,))
        self.cache[state] = result
        return result

    def nodes(self, module, nodes, bound, active=()):
        result = []
        for node in nodes:
            if isinstance(node, DEFS):
                continue
            if isinstance(node, ast.If):
                result += self.nodes(module, [node.test], bound, active)
                truth = self.condition(node.test, bound)
                branches = [node.body] if truth is True else [node.orelse] if truth is False else [node.body, node.orelse]
                for branch in branches:
                    result += self.nodes(module, branch, bound, active)
                if truth is not None and branches[0] and isinstance(branches[0][-1], (ast.Return, ast.Raise)):
                    break
                continue
            if isinstance(node, ast.IfExp):
                truth = self.condition(node.test, bound)
                branches = [node.body] if truth is True else [node.orelse] if truth is False else [node.body, node.orelse]
                result += self.nodes(module, [node.test] + branches, bound, active)
                continue
            if isinstance(node, (ast.AsyncWith, ast.With)):
                inner = set(bound)
                for item in node.items:
                    result += self.nodes(module, [item.context_expr], frozenset(inner), active)
                    if isinstance(item.optional_vars, ast.Name) and isinstance(item.context_expr, ast.Call):
                        if self.acquisition(module, item.context_expr, frozenset(inner)) or self.target(module, item.context_expr) == ('db', 'transaction'):
                            inner.add(item.optional_vars.id)
                result += self.nodes(module, node.body, frozenset(inner), active)
                continue
            if isinstance(node, ast.Call):
                found = self.acquisition(module, node, bound)
                here = (module, node.lineno, found or ast.unparse(node.func))
                if found:
                    result.append((here,))
                else:
                    target = self.target(module, node)
                    if target in self.functions and target[0] != 'db':
                        here = (module, node.lineno, '.'.join(target))
                        params = self.supplied(node, self.functions[target], bound)
                        result += [(here,) + path for path in self.effects(target, params, active)]
                # The two retained I/O exceptions must also become stale if the I/O leaves the lock.
                if active and active[-1][0] == ('oidc', '_refresh_upstream') and ast.unparse(node.func) == 'http.post':
                    result.append(((module, node.lineno, 'external IdP HTTP'),))
                if active and active[-1][0] == ('siem', 'deliver_one') and ast.unparse(node.func) == 'asyncio.to_thread' and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == 'send':
                    result.append(((module, node.lineno, 'external SIEM HTTP'),))
            result += self.nodes(module, list(ast.iter_child_nodes(node)), bound, active)
            if isinstance(node, (ast.Return, ast.Raise)):
                break
        return result

    def violations(self):
        found = set()
        for key, function in self.functions.items():
            module, name = key
            if module == 'db':
                continue
            params = function.args.posonlyargs + function.args.args + function.args.kwonlyargs
            bound = frozenset(p.arg for p in params if p.arg in CONNECTIONS)
            if bound:
                for path in self.effects(key, bound):
                    found.add((key, function.lineno, path))
            # Inspect the body of each acquisition, with its actual connection variable bound.
            for node in ast.walk(function):
                if not isinstance(node, ast.AsyncWith):
                    continue
                inner = set(bound)
                held = False
                for item in node.items:
                    if isinstance(item.context_expr, ast.Call) and self.acquisition(module, item.context_expr, frozenset(inner)):
                        if held:
                            path = ((module, item.context_expr.lineno, 'nested connection context'),)
                            found.add((key, node.lineno, path))
                        held = True
                        if isinstance(item.optional_vars, ast.Name):
                            inner.add(item.optional_vars.id)
                if held:
                    for path in self.nodes(module, node.body, frozenset(inner), ((key, frozenset(inner)),)):
                        found.add((key, node.lineno, path))
        return sorted(found)


def classify(violations, allow):
    used, rejected = set(), []
    for key, line, path in violations:
        candidates = [(key[0] + '.py', key[1])]
        # Exempt only the nearest named function responsible for the acquisition.
        candidates += [((label.split('.')[0] if '.' in label else m) + '.py', label.split('.')[-1]) for m, _, label in path[:-1]]
        accepted = next((k for k in reversed(candidates) if k in allow), None)
        if accepted:
            used.add(accepted)
        else:
            rejected.append((key, line, path))
    return rejected, set(allow) - used


def self_test():
    fixtures = [
        ("async def f():\n async with db.transaction() as c:\n  await db.fetch_one('x')\n", True),
        ("async def g(connection):\n await db.execute('x')\nasync def f():\n async with db.transaction() as snapshot:\n  await g(snapshot)\n", True),
        ("async def g(connection=None):\n if connection is None:\n  return await db.fetch_one('x')\n return await connection.execute('x')\nasync def f():\n async with db.transaction() as snapshot:\n  await g(snapshot)\n", False),
        ("async def f():\n async with db.transaction() as c:\n  await c.execute('x')\n", False),
        ("async def g():\n await db.execute('x')\nasync def f():\n async with (await db.pool()).connection() as guard:\n  await g()\n", True),
        ("async def f():\n pool = await db.pool()\n async with pool.connection() as c:\n  await db.execute('x')\n", True),
        ("async def f(connection=None):\n if connection is None:\n  async with db.transaction() as c:\n   return await f(c)\n await connection.execute('x')\n", False),
        ("async def g(connection):\n await db.fetch_one('x', connection=connection)\nasync def f():\n async with db.transaction() as snapshot:\n  await g(snapshot)\n", False),
        ("async def h():\n await db.fetch_one('x')\nasync def g():\n await h()\nasync def f():\n async with db.transaction() as c:\n  await g()\n", True),
        ("async def page(cursor=None):\n return await db.fetch_all('x')\n", False),
    ]
    for source, expected in fixtures:
        assert bool(Check({'sample': source}).violations()) == expected, source
    broken = Check({'sample': fixtures[0][0]}).violations()
    assert classify(broken, {('sample.py', 'f'): '자기 시험'}) == ([], set())
    assert classify([], {('sample.py', 'f'): '낡은 예외'})[1] == {('sample.py', 'f')}
    aliases = {'a': 'from .b import g as h\nasync def f():\n async with db.transaction() as c:\n  await h(c)\n',
               'b': 'async def g(conn):\n await db.execute("x")\n'}
    assert Check(aliases).violations()
    print(f'PASS nested_tx self-test ({len(fixtures) + 3} cases)')


def main():
    self_test()
    root = Path(__file__).resolve().parents[1] / 'gateway/app'
    checker = Check({p.stem: p.read_text(encoding='utf-8') for p in sorted(root.glob('*.py'))})
    rejected, stale = classify(checker.violations(), ALLOW)
    for key, line, path in rejected:
        print(f'{key[0]}.py:{line} {key[1]} -> ' + ' -> '.join(f'{m}.py:{n} {label}' for m, n, label in path))
    for key in sorted(stale):
        print(f'{key[0]}:{key[1]}: stale ALLOW')
    print(f'nested_tx: violations={len(rejected)} stale_allow={len(stale)} allow={len(ALLOW) - len(stale)}')
    return int(bool(rejected or stale))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'FAIL nested_tx: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
