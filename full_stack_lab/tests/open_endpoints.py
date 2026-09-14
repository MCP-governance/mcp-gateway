#!/usr/bin/env python3
"""Keep the documented list of unauthenticated APIs equal to the code.

README 13절 is the repository's statement of what it deliberately leaves open. That
statement drifted the moment endpoints were added without touching it, and an
incomplete "here is what is open" list is worse than none in a governance project:
a reviewer reads it as exhaustive.

Static only - parses the router and the README, needs no running stack, so CI can run
it before anything is built.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

LAB = pathlib.Path(__file__).resolve().parent.parent
ROUTER = LAB / "gateway" / "app" / "main.py"
README = LAB / "README.md"
DOC_MARKER = "Gateway의 읽기 API는 인증 없이 열려 있습니다:"
CONSOLE_REDIRECT = 'RedirectResponse("http://localhost:8000/workspace")'
# Login has to be reachable without a token or nobody could ever get one; the
# browser console is served by the Agent service and is not an API.
EXEMPT = {"/api/session"}


def route_auth(tree: ast.Module) -> dict[tuple[str, str], str]:
    """Map each (method, path) route to 'open', 'user' or 'admin'.

    Keyed by method as well as path because one path can carry both an open read and
    a guarded write - /api/enforcement does exactly that - and collapsing them hides
    whichever was registered first.
    """
    routes: dict[tuple[str, str], str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        endpoints = [
            (decorator.func.attr, decorator.args[0].value)
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "app"
            and decorator.func.attr in {"get", "post", "put", "delete", "patch"}
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
            and isinstance(decorator.args[0].value, str)
        ]
        if not endpoints:
            continue
        dependencies = {
            argument.args[0].id
            for argument in node.args.defaults + node.args.kw_defaults
            if isinstance(argument, ast.Call)
            and isinstance(argument.func, ast.Name)
            and argument.func.id == "Depends"
            and argument.args
            and isinstance(argument.args[0], ast.Name)
        }
        level = "admin" if "admin_caller" in dependencies else "user" if "caller" in dependencies else "open"
        for method, path in endpoints:
            routes[(method, path)] = level
    return routes


def documented() -> set[str]:
    for line in README.read_text(encoding="utf-8").splitlines():
        if DOC_MARKER in line:
            return set(re.findall(r"`(/api/[^`]+)`", line))
    raise SystemExit(f"FAIL README에서 '{DOC_MARKER}' 문장을 찾지 못했습니다.")


def main() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    if CONSOLE_REDIRECT not in source:
        raise SystemExit("FAIL Gateway 루트가 8000 Console로 이동하지 않습니다.")
    routes = route_auth(ast.parse(source))
    if not routes:
        raise SystemExit("FAIL main.py에서 route를 하나도 읽지 못했습니다.")
    # A path counts as open when any method on it is reachable without a token.
    actual = {path for (_, path), level in routes.items()
              if level == "open" and path.startswith("/api/")} - EXEMPT
    claimed = documented()

    undocumented = sorted(actual - claimed)
    overclaimed = sorted(claimed - actual)
    if undocumented:
        print(f"FAIL 인증 없이 열려 있지만 문서에 없는 API: {undocumented}", file=sys.stderr)
    if overclaimed:
        print(f"FAIL 문서에는 열려 있다고 적혔지만 실제로는 아닌 API: {overclaimed}", file=sys.stderr)
    if undocumented or overclaimed:
        raise SystemExit(1)

    guarded = sorted(f"{method.upper()} {path}" for (method, path), level in routes.items() if level != "open")
    print(f"PASS 무인증 {len(actual)}개가 문서와 일치, 인증 필요 {len(guarded)}개")


if __name__ == "__main__":
    main()
