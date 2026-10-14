#!/usr/bin/env python3
"""Keep the files the browser downloads free of what docs/ai/CONSOLE_UI.md forbids.

The console is a product screen, and two people now edit it (one mostly on design).
The rules - no development traces, no abbreviation badges, the 게이트웨이/엔드포인트
vocabulary, ~합니다 not ~요, no inline style under the CSP - were only written down,
so a slip was caught on the device or not at all. Comments ship to the browser too,
so the whole file is checked, not just string literals.

Static only, no running stack. Vendor bundles and fonts are third-party and skipped.
"""
from __future__ import annotations

import pathlib
import re
import sys

STATIC = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "app" / "agent_static"
SHIPPED = (".html", ".js", ".mjs", ".css")
RULES = [
    (re.compile(r"\bD-\d{1,3}\b"), "결정 번호(D-n)는 화면·주석에 남기지 않습니다"),
    (re.compile(r"\b(WIP|TODO|FIXME|XXX)\b"), "개발 흔적"),
    (re.compile(r"PAC-?15|팀원|실습|(?<![-\w])v[34]\b"), "프로젝트 내부 용어"),
    (re.compile(r"\b(GW|EP|VD)\b"), "약어 표식 대신 게이트웨이·엔드포인트"),
    (re.compile(r"단말|커널"), "용어는 엔드포인트"),
    (re.compile(r"[가-힣](해요|어요|아요|에요|예요|이죠|하죠)(?=[\s.,!?\"'`<)]|$)"), "문장은 ~합니다/~하세요체(~요 금지)"),
    (re.compile(r"\sstyle\s*=\s*[\"']"), "CSP: 인라인 style 금지, 클래스로"),
    (re.compile(r"<script(?![^>]*\bsrc=)[^>]*>"), "CSP: 인라인 스크립트 금지"),
]


def main() -> int:
    problems = []
    for path in sorted(STATIC.rglob("*")):
        if path.suffix not in SHIPPED or "vendor" in path.parts:
            continue
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern, why in RULES:
                for m in pattern.finditer(line):
                    problems.append(f"{path.relative_to(STATIC)}:{no}: {why}: {m.group(0)!r}")
    for p in problems:
        print(p)
    print(f"console copy check: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
