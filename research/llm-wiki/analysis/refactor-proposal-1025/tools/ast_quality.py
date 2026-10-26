import ast, os, sys, collections, re
root = sys.argv[1]
files = sorted(f for f in os.listdir(root) if f.endswith('.py'))
env_calls = collections.Counter(); env_names = collections.defaultdict(set)
exc_pass = collections.Counter(); exc_broad = collections.Counter(); exc_bare = collections.Counter(); exc_total = collections.Counter()
exc_pass_lines = collections.defaultdict(list)
funcs = []
globals_mut = []
asyncfn = collections.Counter(); syncfn = collections.Counter()
for f in files:
    src = open(os.path.join(root, f), encoding='utf-8').read()
    tree = ast.parse(src)
    lines = src.splitlines()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            fn = n.func
            # os.getenv / os.environ.get / os.environ[...]
            if isinstance(fn, ast.Attribute) and fn.attr == 'getenv' and isinstance(fn.value, ast.Name) and fn.value.id == 'os':
                env_calls[f] += 1
                if n.args and isinstance(n.args[0], ast.Constant): env_names[f].add(n.args[0].value)
            elif isinstance(fn, ast.Attribute) and fn.attr == 'get' and isinstance(fn.value, ast.Attribute) and fn.value.attr == 'environ':
                env_calls[f] += 1
                if n.args and isinstance(n.args[0], ast.Constant): env_names[f].add(n.args[0].value)
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Attribute) and n.value.attr == 'environ':
            env_calls[f] += 1
            if isinstance(n.slice, ast.Constant): env_names[f].add(n.slice.value)
        if isinstance(n, ast.ExceptHandler):
            exc_total[f] += 1
            t = n.type
            name = ast.unparse(t) if t is not None else None
            if t is None:
                exc_bare[f] += 1
            elif name in ('Exception', 'BaseException'):
                exc_broad[f] += 1
            body = n.body
            if len(body) == 1 and isinstance(body[0], (ast.Pass,)) or (len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and body[0].value.value is Ellipsis):
                exc_pass[f] += 1
                exc_pass_lines[f].append((n.lineno, name))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append((n.end_lineno - n.lineno + 1, f, n.lineno, n.name))
            if isinstance(n, ast.AsyncFunctionDef): asyncfn[f] += 1
            else: syncfn[f] += 1
    # module-level mutable globals
    for n in tree.body:
        targets = []
        if isinstance(n, ast.Assign): targets = n.targets; val = n.value
        elif isinstance(n, ast.AnnAssign) and n.value is not None: targets = [n.target]; val = n.value
        else: continue
        for t in targets:
            if not isinstance(t, ast.Name): continue
            v = val
            kind = None
            if isinstance(v, (ast.Dict, ast.List, ast.Set)): kind = type(v).__name__.lower()
            elif isinstance(v, ast.Call):
                cn = ast.unparse(v.func)
                if cn in ('dict', 'list', 'set', 'OrderedDict', 'collections.OrderedDict', 'defaultdict', 'collections.defaultdict', 'Counter') : kind = cn
                elif cn.endswith(('Lock', 'Semaphore', 'Condition', 'Event')): kind = cn
                elif cn.endswith(('Pool', 'AsyncClient', 'Pool')): kind = cn
                elif 'ContextVar' in cn: kind = cn
            if isinstance(n, ast.AnnAssign) and kind is None and re.match(r'(dict|list|set|OrderedDict)', ast.unparse(n.annotation)) and isinstance(val, (ast.Dict, ast.List, ast.Set)):
                kind = 'annotated'
            if kind and not t.id.isupper() or (kind and kind in ('dict','list','set') and t.id.isupper() and False):
                globals_mut.append((f, n.lineno, t.id, kind))
            elif kind and t.id.isupper() and kind.endswith(('Lock','Semaphore','Condition','Event','Pool','AsyncClient')):
                globals_mut.append((f, n.lineno, t.id, kind))
        # `global x` statements counted separately
glob_stmt = collections.Counter()
for f in files:
    tree = ast.parse(open(os.path.join(root, f), encoding='utf-8').read())
    for n in ast.walk(tree):
        if isinstance(n, ast.Global): glob_stmt[f] += len(n.names)
print("OS.GETENV total", sum(env_calls.values()), "files", len(env_calls), "distinct vars", len(set().union(*env_names.values())))
for f, c in env_calls.most_common(15): print("  ", f, c)
print("EXCEPT total", sum(exc_total.values()), "broad(Exception/BaseException)", sum(exc_broad.values()), "bare", sum(exc_bare.values()), "pass-only", sum(exc_pass.values()))
print("per file (total/broad/bare/pass):")
for f in sorted(exc_total, key=lambda x: -exc_total[x])[:20]:
    print("  %-26s %3d %3d %3d %3d" % (f, exc_total[f], exc_broad[f], exc_bare[f], exc_pass[f]))
print("pass-only handlers:")
for f in sorted(exc_pass_lines):
    print("  ", f, exc_pass_lines[f])
print("FUNC length top 12:")
for l, f, ln, name in sorted(funcs, reverse=True)[:12]: print("  ", f, ln, name, l)
print("functions total", len(funcs), "async", sum(asyncfn.values()), "sync", sum(syncfn.values()))
print("functions > 100 lines:", sum(1 for x in funcs if x[0] > 100), "> 60:", sum(1 for x in funcs if x[0] > 60))
print("GLOBAL mutable/lock objects:")
for g in globals_mut: print("  ", g)
print("global stmts:", dict(glob_stmt))
