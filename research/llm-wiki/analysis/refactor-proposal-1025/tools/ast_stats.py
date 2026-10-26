import ast, sys, os, re, collections, json
root = sys.argv[1]
mods = {}
files = sorted(f for f in os.listdir(root) if f.endswith('.py'))
loc = {}
routes = collections.Counter()
route_list = collections.defaultdict(list)
for f in files:
    src = open(os.path.join(root, f), encoding='utf-8').read()
    loc[f] = src.count('\n') + (0 if src.endswith('\n') else 1)
    tree = ast.parse(src)
    mods[f[:-3]] = tree
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ('get','post','put','delete','patch','api_route','websocket'):
                    routes[f] += 1
                    arg = d.args[0].value if d.args and isinstance(d.args[0], ast.Constant) else '?'
                    route_list[f].append((d.func.attr, arg, n.lineno))
print("ROUTES", dict(routes), sum(routes.values()))
json.dump({k: v for k, v in route_list.items()}, open(os.path.join(os.path.dirname(__file__), 'routes.json'), 'w'))
# import graph
names = set(mods)
edges = collections.defaultdict(set)
lazy_edges = collections.defaultdict(set)
for m, tree in mods.items():
    # top-level imports vs function-level imports
    toplevel = set()
    for n in tree.body:
        for sub in ast.walk(n) if isinstance(n, (ast.Try, ast.If)) else [n]:
            pass
    def collect(node, into, lazy_into, in_func=False):
        for ch in ast.iter_child_nodes(node):
            infn = in_func or isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef))
            if isinstance(ch, ast.ImportFrom):
                tgt = None
                if ch.level == 1:
                    if ch.module:
                        tgt = [ch.module.split('.')[0]]
                    else:
                        tgt = [a.name for a in ch.names]
                elif ch.level == 0 and ch.module and ch.module.split('.')[0] == 'app':
                    parts = ch.module.split('.')
                    tgt = [parts[1]] if len(parts) > 1 else [a.name for a in ch.names]
                if tgt:
                    for t in tgt:
                        if t in names and t != m:
                            (lazy_into if infn else into).add(t)
            elif isinstance(ch, ast.Import):
                for a in ch.names:
                    if a.name.split('.')[0] == 'app' and '.' in a.name:
                        t = a.name.split('.')[1]
                        if t in names and t != m:
                            (lazy_into if infn else into).add(t)
            collect(ch, into, lazy_into, infn)
    collect(tree, edges[m], lazy_edges[m])
def cycles(graph):
    # Tarjan SCC
    index = {}; low = {}; stack = []; on = set(); res = []; idx = [0]
    sys.setrecursionlimit(10000)
    def strong(v):
        index[v] = low[v] = idx[0]; idx[0] += 1; stack.append(v); on.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                strong(w); low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop(); on.discard(w); comp.append(w)
                if w == v: break
            if len(comp) > 1: res.append(sorted(comp))
    for v in graph:
        if v not in index: strong(v)
    return res
top = {m: set(e) for m, e in edges.items()}
allg = {m: set(edges[m]) | set(lazy_edges[m]) for m in mods}
print("EDGES top-level:", sum(len(v) for v in top.values()), " lazy:", sum(len(v) for v in lazy_edges.values()))
print("SCC top-level:", cycles(top))
print("SCC all (incl. function-level imports):", cycles(allg))
# find 2-cycles in all
two = []
for a in allg:
    for b in allg[a]:
        if a < b and a in allg.get(b, ()):
            two.append((a, b, 'lazy' if (b in lazy_edges[a] and b not in edges[a]) or (a in lazy_edges[b] and a not in edges[b]) else 'top'))
print("2-cycles:", two)
# fan in/out
fanin = collections.Counter()
for a, bs in allg.items():
    for b in bs: fanin[b] += 1
print("fanin top10:", fanin.most_common(12))
print("fanout top10:", sorted(((a, len(b)) for a, b in allg.items()), key=lambda x: -x[1])[:12])
json.dump({'loc': loc}, open(os.path.join(os.path.dirname(__file__), 'loc.json'), 'w'))
print("TOTAL LOC", sum(loc.values()), "modules", len(loc))
# lazy-only edges list
print("lazy-only edges:")
for a in sorted(lazy_edges):
    for b in sorted(lazy_edges[a] - edges[a]):
        print("  ", a, "->", b)
