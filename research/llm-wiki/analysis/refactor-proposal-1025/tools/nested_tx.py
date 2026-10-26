import ast, os, sys, collections
root = sys.argv[1]
DBFUNCS = {'fetch_one','fetch_all','execute','transaction','pool'}
mods = {}
for f in sorted(os.listdir(root)):
    if f.endswith('.py'):
        src = open(os.path.join(root,f),encoding='utf-8').read()
        mods[f[:-3]] = (ast.parse(src), src.splitlines())
# imports mapping alias -> module (from . import a, b)
def local_imports(tree):
    alias = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level == 1 and not n.module:
            for a in n.names:
                alias[a.asname or a.name] = a.name
    return alias
# function table: (mod, func) -> node
funcs = {}
for m,(tree,_) in mods.items():
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            funcs.setdefault((m,n.name),[]).append(n)
def calls_in(node, skip_nested_funcs=True):
    # yield Call nodes directly in node's body (not in nested defs)
    stack = list(ast.iter_child_nodes(node))
    while stack:
        c = stack.pop()
        if isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda,ast.ClassDef)) and skip_nested_funcs:
            continue
        if isinstance(c, ast.Call):
            yield c
        stack.extend(ast.iter_child_nodes(c))
def callee(call, m, alias):
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        base = f.value.id
        if base == 'db' or alias.get(base) == 'db':
            return ('db', f.attr)
        if base in alias:
            return (alias[base], f.attr)
        return None
    if isinstance(f, ast.Name):
        return (m, f.id)
    return None
def passes_conn(call):
    return any(k.arg in ('connection','conn') for k in call.keywords) or any(isinstance(a,ast.Name) and a.id in ('connection','conn') for a in call.args)
# direct acquirers: functions whose body (not nested) calls db.<DBFUNC>
direct = {}
alias_of = {m: local_imports(t) for m,(t,_) in mods.items()}
for (m,name),nodes in funcs.items():
    for fn in nodes:
        for c in calls_in(fn):
            ce = callee(c,m,alias_of[m])
            if ce and ce[0]=='db' and ce[1] in DBFUNCS:
                direct.setdefault((m,name),[]).append((ce[1],c.lineno))
# also "connection" param: functions that take connection param & use it are not acquirers for those calls
# transitive
acq = set(direct)
changed=True
edges = collections.defaultdict(set)
for (m,name),nodes in funcs.items():
    for fn in nodes:
        for c in calls_in(fn):
            ce = callee(c,m,alias_of[m])
            if ce and ce in funcs and not passes_conn(c):
                edges[(m,name)].add(ce)
while changed:
    changed=False
    for k,vs in edges.items():
        if k not in acq and any(v in acq for v in vs):
            acq.add(k); changed=True
# but a function that accepts connection= param and uses it conditionally (connection is None -> db) is a conditional acquirer; keep as acquirer only when passes_conn false
def is_tx(item):
    e = item.context_expr
    return isinstance(e,ast.Call) and isinstance(e.func,ast.Attribute) and e.func.attr=='transaction' and isinstance(e.func.value,ast.Name) and (e.func.value.id=='db' or alias_of_cur.get(e.func.value.id)=='db')
results=[]
for m,(tree,lines) in mods.items():
    alias_of_cur = alias_of[m]
    for n in ast.walk(tree):
        if isinstance(n,(ast.AsyncWith,)):
            for item in n.items:
                if is_tx(item):
                    # find calls in body (include nested but not defs)
                    body = ast.Module(body=n.body, type_ignores=[])
                    for c in calls_in(body):
                        ce = callee(c,m,alias_of_cur)
                        if not ce: continue
                        if ce[0]=='db' and ce[1] in DBFUNCS:
                            results.append(('DEFINITE',m,c.lineno,n.lineno,f"db.{ce[1]}",lines[c.lineno-1].strip()[:110]))
                        elif ce in acq and not passes_conn(c):
                            results.append(('PROBABLE',m,c.lineno,n.lineno,f"{ce[0]}.{ce[1]}",lines[c.lineno-1].strip()[:110]))
for r in sorted(results):
    print(*r, sep=' | ')
print("TOTAL", len(results))
# also: raw pool().connection() usage

print("\n--- functions that take a connection/lock param but still acquire another pool connection ---")
for (m,name),nodes in sorted(funcs.items()):
    for fn in nodes:
        params = [a.arg for a in fn.args.args + fn.args.kwonlyargs]
        connparams = [p for p in params if p in ('connection','conn','lock','snapshot','cursor')]
        if not connparams: continue
        lines = mods[m][1]
        for c in calls_in(fn):
            ce = callee(c,m,alias_of[m])
            if not ce: continue
            if ce[0]=='db' and ce[1] in DBFUNCS:
                # conditional on connection None? show line
                print(f"DB   {m}:{c.lineno} in {name}({','.join(connparams)}) -> db.{ce[1]} | {lines[c.lineno-1].strip()[:100]}")
            elif ce in acq and not passes_conn(c) and ce != (m,name):
                print(f"CALL {m}:{c.lineno} in {name}({','.join(connparams)}) -> {ce[0]}.{ce[1]} | {lines[c.lineno-1].strip()[:100]}")
print("\n--- raw pool connection / psycopg connect use ---")
for m,(tree,lines) in mods.items():
    for i,l in enumerate(lines,1):
        if 'db.pool()' in l or '.connection()' in l or 'psycopg.connect' in l or 'AsyncConnection' in l:
            print(f"{m}:{i}: {l.strip()[:120]}")
