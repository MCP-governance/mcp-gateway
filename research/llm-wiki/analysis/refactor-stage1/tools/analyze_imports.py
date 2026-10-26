"""Read-only, stdlib AST inventory. Not a product file or a commit candidate.

Run: python -X utf8 ANALYZE-s1.py [--self-test | --compact]
Default stdout is the complete graph with import sites; no files are written.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import configparser
import fnmatch

ROOT = Path(__file__).resolve().parent
APP = ROOT / "full_stack_lab/gateway/app"

PACKAGE_GROUPS = {
    "mint.gateway.decision": "core classify consent dispatch flow_fingerprint high_impact outcomes output_contract poisoning privacy residency secret_scan selective tool_sunset user_suspend automatic_suspend",
    "mint.gateway.transport": "addon destination mcp_facade mcp_sessions sse_entry stdio_entry upstream upstream_sessions",
    "mint.gateway": "main",
    "mint.policy": "pac replay",
    "mint.ledger": "audit disposal retention siem",
    "mint.control": "activity agent_service artifact_provenance connectors decommission experiments incident_pack incidents intake_proposal integrations litellm_sync ops_response provenance release review risk_tier sbom_impact supplier_assurance system_metrics",
    "mint.identity": "agent_contract idp oidc user_credentials keygen",
    "mint.endpoint": "endpoint_plane event_correlation kit_commands local_jobs server_egress windows_oneclick",
    "mint.shared": "connections contract db textscan",
    "mint.testing": "acceptance",
}
PLANNED_CUTS = {("agent_contract", "oidc"), ("idp", "agent_service"),
                ("endpoint_plane", "local_jobs"), ("endpoint_plane", "idp"),
                ("incidents", "ops_response"), ("registry", "upstream")}


def imports(source, names, package="app"):
    rows = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.functions = []
            self.classes = []

        def visit_FunctionDef(self, node):
            self.functions.append(node.name)
            self.generic_visit(node)
            self.functions.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            self.classes.append(node.name)
            self.generic_visit(node)
            self.classes.pop()

        def add(self, node, target, symbol, binding):
            if target in names:
                rows.append(dict(target=target, line=node.lineno,
                                 end=node.end_lineno, symbol=symbol, binding=binding,
                                 kind="lazy" if self.functions else "eager",
                                 scope=".".join(self.classes + self.functions) or "<module>",
                                 relative=isinstance(node, ast.ImportFrom) and bool(node.level),
                                 statement=ast.get_source_segment(source, node)))

        def visit_ImportFrom(self, node):
            if node.level == 1 and package == "app":
                base = node.module or ""
            elif not node.level and (node.module == "app" or (node.module or "").startswith("app.")):
                base = (node.module or "")[4:] if node.module != "app" else ""
            else:
                return
            for alias in node.names:
                self.add(node, (base or alias.name).split(".")[0],
                         alias.name if base else None, alias.asname or alias.name)

        def visit_Import(self, node):
            for alias in node.names:
                if alias.name.startswith("app."):
                    self.add(node, alias.name.split(".")[1], None, alias.asname or "app")

    Visitor().visit(ast.parse(source))
    return rows


def graph(names, rows, kind=None, removed=()):
    result = {name: set() for name in names}
    for row in rows:
        edge = row["source"], row["target"]
        if (kind is None or row["kind"] == kind) and edge not in removed:
            result[edge[0]].add(edge[1])
    return result


def scc(graph):
    # Tarjan: deterministic ordering makes independent reruns comparable.
    index, low, stack, active, components = {}, {}, [], set(), []

    def visit(node):
        index[node] = low[node] = len(index)
        stack.append(node)
        active.add(node)
        for target in sorted(graph[node]):
            if target not in index:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in active:
                low[node] = min(low[node], index[target])
        if low[node] == index[node]:
            group = []
            while True:
                target = stack.pop()
                active.remove(target)
                group.append(target)
                if target == node:
                    break
            components.append(sorted(group))

    for node in sorted(graph):
        if node not in index:
            visit(node)
    return sorted(components, key=lambda c: (-len(c), c))


def cyclic(graph):
    return [c for c in scc(graph) if len(c) > 1 or c[0] in graph[c[0]]]


def self_test():
    names = {"a", "b", "c"}
    source = "from . import a as aa, b\nif True:\n from .c import x\nclass C:\n from . import a\n def f(self):\n  from .b import z\nasync def g():\n import app.c as cc\n"
    rows = imports(source, names)
    assert [(r["target"], r["kind"]) for r in rows] == [
        ("a", "eager"), ("b", "eager"), ("c", "eager"), ("a", "eager"),
        ("b", "lazy"), ("c", "lazy")]
    assert rows[0]["binding"] == "aa" and rows[-1]["binding"] == "cc"
    assert imports("from app.a import value as v", names)[0]["symbol"] == "value"
    assert not imports("from foreign import a\nfrom .. import b", names)
    g = {"a": {"b"}, "b": {"a", "c"}, "c": set()}
    assert scc(g) == [["a", "b"], ["c"]]
    assert not cyclic({"a": {"b"}, "b": set()})
    assert cyclic({"a": {"a"}}) == [["a"]]
    contract = "[importlinter:contract:check]\nname = fixture\ntype = forbidden\nsource_modules = app.a\nforbidden_modules = app.c\n"
    assert check_contract(contract, g)
    assert not check_contract(contract + "allow_indirect_imports = True\n", g)
    assert check_contract(contract + "allow_indirect_imports = True\n", {**g, "a": {"b", "c"}})
    print("self-test: PASS (import forms, aliases, eager/lazy/class, SCC, self-loop)")


def analyze():
    files = sorted(APP.glob("*.py"))
    names = {p.stem for p in files if p.stem != "__init__"}
    rows, modules, definitions, core_uses = [], {}, {}, []
    sources = {p.stem: p.read_text(encoding="utf-8-sig") for p in files}
    for name in sorted(names):
        source = sources[name]
        tree = ast.parse(source)
        local = imports(source, names)
        rows.extend(dict(source=name, **r) for r in local)
        definitions[name] = [dict(name=n.name, line=n.lineno, end=n.end_lineno,
                                  lines=n.end_lineno - min([n.lineno] + [d.lineno for d in n.decorator_list]) + 1)
                             for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        modules[name] = dict(lines=len(source.splitlines()), sha256=hashlib.sha256(source.encode()).hexdigest())
        if name == "agent_service":
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "core":
                    core_uses.append(dict(symbol=n.attr, line=n.lineno))
    eager, lazy, full = (graph(names, rows, kind) for kind in ("eager", "lazy", None))
    pairs = [(a, b) for a in sorted(names) for b in sorted(full[a])
             if a < b and a in full[b] and not (b in eager[a] and a in eager[b])]
    external, parse_errors, dynamic = [], [], []
    for p in sorted(ROOT.rglob("*.py")):
        if any(part in {".git", ".venv", "venv", "node_modules", "__pycache__"} for part in p.parts):
            continue
        if p.parent == APP or p.name == "ANALYZE-s1.py":
            continue
        try:
            source = p.read_text(encoding="utf-8-sig")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeError) as exc:
            parse_errors.append(dict(path=p.relative_to(ROOT).as_posix(), error=str(exc)))
            continue
        external.extend(dict(path=p.relative_to(ROOT).as_posix(), **r)
                        for r in imports(source, names, package="external"))
    for name, source in sorted(sources.items()):
        for i, line in enumerate(source.splitlines(), 1):
            if any(token in line for token in ("import_module(", "__import__(", 'globals().get(', 'getattr(core', 'getattr(registry')):
                dynamic.append(dict(module=name, line=i, text=line.strip()))
    for name in sorted(names):
        incoming = {(r["source"], r["line"]) for r in rows if r["target"] == name}
        outgoing = {(r["source"], r["line"]) for r in rows if r["source"] == name and r["relative"]}
        ext = {(r["path"], r["line"]) for r in external if r["target"] == name}
        modules[name].update(incoming_sites=len(incoming), outgoing_relative_sites=len(outgoing),
                             affected_app_sites=len(incoming | outgoing), external_incoming_sites=len(ext),
                             fan_out=len(full[name]))
    removed = PLANNED_CUTS
    baseline = "\n".join(f"{p.name}:{hashlib.sha256(p.read_bytes()).hexdigest()}" for p in files)
    packages = {name: package for package, group in PACKAGE_GROUPS.items() for name in group.split()}
    packages["registry"] = "mint.registry"
    assert set(packages) == names, (set(packages) - names, names - set(packages))
    for name in names:
        modules[name]["target_package"] = packages[name]
    return dict(scope="full_stack_lab/gateway/app/*.py", files=len(files), modules=modules,
                source_manifest_sha256=hashlib.sha256(baseline.encode()).hexdigest(),
                counts=dict(import_sites=len({(r['source'], r['line']) for r in rows}),
                            eager_sites=len({(r['source'], r['line']) for r in rows if r['kind']=='eager'}),
                            lazy_sites=len({(r['source'], r['line']) for r in rows if r['kind']=='lazy'}),
                            eager_edges=sum(map(len,eager.values())), lazy_edges=sum(map(len,lazy.values())),
                            all_edges=sum(map(len,full.values())),
                            occurrence_edges=len(rows)),
                scc_eager=scc(eager), scc_all=scc(full), cyclic_eager=cyclic(eager), cyclic_all=cyclic(full),
                lazy_closed_pairs=[dict(pair=[a,b], sites=[r for r in rows if (r['source'],r['target']) in {(a,b),(b,a)}]) for a,b in pairs],
                core_fanout={kind:sorted(g['core']) for kind,g in [('eager',eager),('lazy',lazy),('all',full)]},
                console_core_uses=sorted(core_uses,key=lambda r:r['line']), imports=rows,
                definitions=definitions, external_imports=external, external_parse_errors=parse_errors,
                dynamic_candidates=dynamic,
                planned_edge_removal_only=dict(removed=sorted(removed), cyclic=cyclic(graph(names,rows,removed=removed))))


def contracts(result, target=False):
    leaf = ["contract", "db", "connections", "destination", "textscan"]
    text = "[importlinter]\nroot_package = app\n\n[importlinter:contract:entry-and-leaves]\nname = Preserve entry and leaf directions\ntype = layers\nlayers =\n    app.main\n    app.agent_service : app.core\n    " + " : ".join("app."+n for n in leaf) + "\n"
    text += "\n[importlinter:contract:leaf-boundary]\nname = Leaves have no internal imports\ntype = forbidden\nsource_modules =\n" + "".join("    app."+n+"\n" for n in leaf)
    text += "forbidden_modules =\n    app.*\nas_packages = False\n"
    text += "\n[importlinter:contract:console-core]\nname = Console uses narrow shared helpers\ntype = forbidden\nsource_modules =\n    app.agent_service\nforbidden_modules =\n    app.core\nallow_indirect_imports = True\n"
    if not target:
        text += "ignore_imports =\n    app.agent_service -> app.core\nunmatched_ignore_imports_alerting = error\n"
        text += "\n[importlinter:contract:core-fanout]\nname = Freeze current direct core dependencies\ntype = forbidden\nsource_modules =\n    app.core\nforbidden_modules =\n    app.*\nas_packages = False\nallow_indirect_imports = True\nignore_imports =\n"
        text += "".join("    app.core -> app."+n+"\n" for n in result['core_fanout']['all'])
        text += "unmatched_ignore_imports_alerting = error\n"
    else:
        for i, (source, dest) in enumerate(sorted(PLANNED_CUTS), 1):
            text += f"\n[importlinter:contract:cut-{i}]\nname = No return edge {source} to {dest}\ntype = forbidden\nsource_modules =\n    app.{source}\nforbidden_modules =\n    app.{dest}\nallow_indirect_imports = True\n"
    return text


def check_contract(text, g):
    """Only the exact flat-module INI subset emitted above; not import-linter."""
    cfg = configparser.ConfigParser()
    cfg.read_string(text)
    issues = []
    for section in cfg.sections():
        if not section.startswith("importlinter:contract:"):
            continue
        c = cfg[section]
        ignored = set()
        for line in c.get("ignore_imports", "").splitlines():
            if line.strip():
                ignored.add(tuple(x.strip().removeprefix("app.") for x in line.split("->")))
        for a, b in ignored:
            assert b in g[a], ("unmatched ignore", a, b)
        local = {a: {b for b in targets if (a,b) not in ignored} for a,targets in g.items()}

        def reachable(a):
            seen, todo = set(), list(local[a])
            while todo:
                b = todo.pop()
                if b not in seen:
                    seen.add(b)
                    todo.extend(local[b] - seen)
            return seen

        def expand(raw):
            patterns = raw.split()
            return {n for n in g if any(fnmatch.fnmatchcase("app."+n,p) for p in patterns)}

        if c['type'] == 'forbidden':
            for a in expand(c['source_modules']):
                actual = local[a] if c.getboolean('allow_indirect_imports', False) else reachable(a)
                issues.extend((section,a,b) for b in expand(c['forbidden_modules']) & actual if a != b)
        else:
            layers = [{x.strip().removeprefix('app.') for x in line.split(':')}
                      for line in c['layers'].splitlines() if line.strip()]
            assert all(layer <= g.keys() for layer in layers)
            for i, layer in enumerate(layers):
                higher = set().union(*layers[:i]) if i else set()
                for a in layer:
                    issues.extend((section,a,b) for b in higher & reachable(a))
    return issues


def report_tables(result):
    lines = ["## 부록 A. 모듈 배치와 이동 영향 실측", "",
             "단독으로 한 단계 아래 패키지에 옮기며 구 경로를 제거할 때의 수치다. `I`는 app 내 inbound import 문 위치 수, `R`은 옮기는 모듈의 상대 import 문 위치 수, `I∪R`은 둘의 합집합, `E`는 app 밖 Python inbound 문 위치 수다. 모든 수는 `(파일, 시작 행)`으로 중복 제거했다. 같은 문이 여러 모듈을 가져오면 행별 수치를 합산할 수 없다. 심볼만 추출하거나 re-export를 유지하면 실제 수정 수는 달라진다. 셸·compose·문자열 로더는 이 수에서 제외하며 §4에서 별도 다룬다.", "",
             "`mint.*`는 최종 논리 이름이다. 첫 PR은 `app.*`를 유지하고 하위 모듈부터 추출한다. `core` 행은 최종 주책임이며 등록/정책/원장 함수는 별도 추출한다. 현재 `registry.py`는 패키지와 이름이 겹치므로 `mint.registry` 전환은 초기 PR 범위 밖이다.", "",
             "| 현재 모듈 / 근거 | 목표 패키지 | LOC | I | R | I∪R | E |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for name,m in result['modules'].items():
        lines.append(f"| `full_stack_lab/gateway/app/{name}.py:1` | `{m['target_package']}` | {m['lines']} | {m['incoming_sites']} | {m['outgoing_relative_sites']} | {m['affected_app_sites']} | {m['external_incoming_sites']} |")
    lines += ["", "`__init__.py`는 패키지 표식으로 위 표에서 제외했다. `mint.snapshot`은 현재 대응 모듈이 없으며 2단계 과제다. `mint.registry`와 `mint.testing`은 제안서 표의 누락 책임을 명시하기 위한 추가 묶음이다. `textscan`은 제안서의 gateway 배치 대신 내부 의존이 없는 공통 검사기로 shared에 둔다. gateway의 입력/출력 검사에서 계속 호출한다.", "", "## 부록 B. 전체 import 인접 목록", "", "E=모듈 실행 시 import(클래스 본문 포함), L=함수/메서드 내부 지연 import. `대상@행` 표기는 같은 대상의 여러 위치를 쉼표로 묶었다. 외부 패키지 import는 제외한다.", "", "| 모듈 | E | L |", "| --- | --- | --- |"]
    for name in result['modules']:
        columns = []
        for kind in ('eager','lazy'):
            targets = sorted({r['target'] for r in result['imports'] if r['source']==name and r['kind']==kind})
            columns.append('; '.join(t+'@'+','.join(map(str,sorted({r['line'] for r in result['imports'] if r['source']==name and r['target']==t and r['kind']==kind}))) for t in targets) or '—')
        lines.append(f"| `{name}` | {columns[0]} | {columns[1]} |")
    lines += ["", "## 부록 C. 현재 고정 계약 초안", "", "```ini", contracts(result).rstrip(), "```", "", "## 부록 D. 6쌍 제거 및 콘솔 직접 의존 제거 후 계약 초안", "", "```ini", contracts(result,True).rstrip(), "```", ""]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--report-tables", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    result = analyze()
    g = graph(result['modules'],result['imports'])
    result['contract_checks'] = dict(current=check_contract(contracts(result),g),
        target_on_current=check_contract(contracts(result,True),g),
        target_on_removed_edges=check_contract(contracts(result,True),graph(result['modules'],result['imports'],removed=PLANNED_CUTS | {('agent_service','core')})))
    assert not result['contract_checks']['current']
    assert not result['contract_checks']['target_on_removed_edges']
    if args.report_tables:
        print(report_tables(result))
        return
    if args.compact:
        result = {k:v for k,v in result.items() if k not in {"imports", "definitions", "external_imports", "modules", "scc_all", "scc_eager"}}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
