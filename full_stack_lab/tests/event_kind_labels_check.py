#!/usr/bin/env python3
"""Every approval event kind the product writes has a Korean label in the console.

The console shows REVIEW_KIND[kind] in the operator history, so a kind written without a label
reaches the screen as its raw English name. This reads the kinds the product code (gateway/app
and runtime) writes and checks each one against the REVIEW_KIND table in console.js.

Kinds are collected from literal kind arguments of record_event, require_independent,
transition, hold_intake and event(connection, ...), from the default of a `kind` parameter,
and from literal kinds in INSERT INTO approval_events.

Not literal, handled explicitly (each count is an allowance, and extra uses fail):
- a forwarded `kind` variable: review.require_independent passes its kind to record_event, and
  agent_service.hold_intake passes its kind parameter to transition. The values are the
  literals at the call sites and the hold_intake default, which this check collects;
- a bind parameter in an INSERT: review.record_event and runtime/worker.py event() insert the
  kind they were given. Their values are the literals passed by callers, collected above.
Any other dynamic kind (f-string, computed name) fails, so it must be added here with a reason.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRODUCT = [ROOT / "gateway" / "app", ROOT / "runtime"]
CONSOLE = ROOT / "gateway" / "app" / "agent_static" / "console.js"

# Kinds the scan must find, so a refactor that hides the scan cannot pass silently.
CANARIES = {"intake-approve", "user-server-suspend", "auto-suspend-count-failed"}

# Forwarded `kind` uses per file: review.py require_independent -> record_event;
# agent_service.py hold_intake -> transition; worker.py event() helper calls.
FORWARDED_OK = {
    "gateway/app/review.py": 1,
    "gateway/app/agent_service.py": 1,
}
# Bind-parameter kinds in an INSERT per file: review.record_event, worker.py event().
INSERT_PARAM_OK = {
    "gateway/app/review.py": 1,
    "runtime/worker.py": 1,
}

KIND_CALLS = {"record_event", "require_independent", "transition", "hold_intake"}


def product_files():
    for base in PRODUCT:
        for path in sorted(base.rglob("*.py")):
            if "test" not in path.name:
                yield path


def rel(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def kind_values(tree: ast.AST):
    """Yield (lineno, value_node) for every place a kind is supplied."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional = node.args.args
            pos_defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
            pairs = list(zip(positional, pos_defaults)) + list(zip(node.args.kwonlyargs, node.args.kw_defaults))
            for arg, default in pairs:
                is_none = isinstance(default, ast.Constant) and default.value is None
                if arg.arg == "kind" and default is not None and not is_none:
                    yield default.lineno, default
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        if name in ("record_event", "require_independent") and node.args:
            yield node.lineno, node.args[0]
        elif name == "event" and len(node.args) >= 3 and isinstance(node.args[0], ast.Name) \
                and node.args[0].id == "connection":
            yield node.lineno, node.args[2]
        if name in KIND_CALLS:
            for kw in node.keywords:
                if kw.arg == "kind":
                    yield node.lineno, kw.value


def scan():
    literal: dict[str, list[str]] = {}
    dynamic: list[str] = []
    forwarded: dict[str, int] = {}
    bind_params: dict[str, int] = {}
    for path in product_files():
        name = rel(path)
        text = path.read_text(encoding="utf-8")
        for lineno, value in kind_values(ast.parse(text, filename=str(path))):
            where = f"{name}:{lineno}"
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                literal.setdefault(value.value, []).append(where)
            elif isinstance(value, ast.Name) and value.id == "kind":
                forwarded[name] = forwarded.get(name, 0) + 1
            else:
                dynamic.append(f"{where}: kind={ast.unparse(value)}")
        insert = r"INSERT INTO approval_events\s*\([^)]*\)\s*VALUES\s*\(\s*('([^']*)'|%s)"
        for m in re.finditer(insert, text):
            lineno = text[:m.start()].count("\n") + 1
            if m.group(2) is not None:
                literal.setdefault(m.group(2), []).append(f"{name}:{lineno}")
            else:
                bind_params[name] = bind_params.get(name, 0) + 1
                if bind_params[name] > INSERT_PARAM_OK.get(name, 0):
                    dynamic.append(f"{name}:{lineno}: INSERT kind is a bind parameter")
    for name, count in forwarded.items():
        if count > FORWARDED_OK.get(name, 0):
            dynamic.append(f"{name}: forwarded kind used {count} time(s), above the explicit allowance")
    return literal, dynamic


def console_labels() -> set[str]:
    source = CONSOLE.read_text(encoding="utf-8")
    block = re.search(r"const REVIEW_KIND = \{(.*?)\n\};", source, re.S)
    if not block:
        raise SystemExit("REVIEW_KIND table not found in console.js")
    return set(re.findall(r'"([a-z][a-z0-9-]*)":', block.group(1)))


def main() -> int:
    literal, dynamic = scan()
    labels = console_labels()
    problems = [f"dynamic kind not allowed: {item}" for item in dynamic]
    problems += [f"scan did not find canary kind: {kind}" for kind in sorted(CANARIES - set(literal))]
    missing = sorted(set(literal) - labels)
    problems += [f"no console label for {kind} (written at {literal[kind][0]})" for kind in missing]
    for problem in problems:
        print(problem)
    print(f"event kind labels: {len(literal)} kinds written, {len(labels)} labels, "
          f"{len(missing)} missing, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
