"""The native tool-text engine must decide exactly like Python's re.

Run inside a gateway image (the extension is built into it):
    docker exec -i <gateway-container> python - < tests/textscan_parity_check.py

1. Every single-character atom of every rule: the set of code points re accepts, over
   all 0x110000 of them, equals the set the engine accepts after canonical mapping.
2. Whole rules: random subjects mixing rule keywords, case-folding traps (ı İ ſ K ß),
   Unicode spaces, marks, Hangul, invisible characters and newline forms; native
   verdict == re verdict for every rule.
3. poisoning's own self-check, and timing of re vs native on 2 KB-200 KB results.
Exit code 1 on any difference or when the engine is not active.
"""
from __future__ import annotations

import json
import random
import re
import statistics
import sys
import time
from pathlib import Path
from re import _constants as C, _parser

if __file__ != "<stdin>":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
sys.path.append("/app")
from app import poisoning, textscan

ALL = "".join(map(chr, range(0x110000)))


def atoms(tree, out: set) -> None:
    for op, av in tree:
        if op in (C.LITERAL, C.NOT_LITERAL, C.ANY, C.IN):
            out.add((op, av if op is not C.IN else tuple(av)))
        elif op is C.BRANCH:
            for alternative in av[1]:
                atoms(alternative, out)
        elif op is C.SUBPATTERN:
            atoms(av[3], out)
        elif op in (C.MAX_REPEAT, C.MIN_REPEAT):
            atoms(av[2], out)
        elif op in (C.ASSERT, C.ASSERT_NOT):
            atoms(av[1], out)


def atom_check(scanner: textscan.Scanner) -> list[dict]:
    problems, checked = [], 0
    views = {False: scanner.engine.canonical(ALL, False), True: scanner.engine.canonical(ALL, True)}
    translators: dict = {}
    alphabet = None
    for index, rule in enumerate(scanner.rules):
        if index not in scanner.native:
            continue
        for pattern in textscan._parts(rule):
            folded = bool(pattern.flags & re.I)
            tree = _parser.parse(pattern.pattern, pattern.flags)
            found: set = set()
            atoms(tree, found)
            if alphabet is None:
                named: set[int] = set(range(128))
                for r in scanner.rules:
                    for p in textscan._parts(r):
                        textscan._named(_parser.parse(p.pattern, p.flags), named)
                alphabet = frozenset(named | {textscan._fold(c) for c in named})
            key = (folded, pattern.flags & (re.I | re.S | re.M))
            translator = translators.setdefault(key, textscan._Translator(alphabet, folded, pattern.flags))
            for op, av in sorted(found, key=repr):
                source = textscan._atom_source(op, list(av) if op is C.IN else av)
                compiled = textscan._atom(source, pattern.flags)
                accepted = {s for s in translator.universe if compiled.fullmatch(translator.sample(s))}
                table = {s: "1" if s in accepted else "0" for s in translator.universe}
                native = views[folded].translate(table)
                python = bytearray(b"0" * len(ALL))
                for match in compiled.finditer(ALL):
                    python[match.start()] = 0x31
                checked += 1
                if native.encode() != bytes(python):
                    diff = [i for i, (a, b) in enumerate(zip(native.encode(), python)) if a != b][:8]
                    problems.append({"rule": index, "atom": source, "flags": pattern.flags,
                                     "code_points": [hex(c) for c in diff]})
    print(f"atoms checked: {checked}", file=sys.stderr)
    return problems


def corpus(rng: random.Random, count: int) -> list[str]:
    words = ["ignore", "IGNORE", "ıgnore", "İgnore", "ignoRe", "disregard", "bypass", "previous", "all", "the",
             "instructions", "prompt", "system", "System", "SYSTEM", "message", "note", "user", "User", "human",
             "assistant", "ai", "AI", "you are", "act as", "developer mode", "admin", "root", "cause", "dan",
             "do not", "don't", "never", "tell", "mention", "reveal", "show", "policy", "policies", "security",
             "guardrails", "filters", "approval", "print", "repeat", "initial instructions", "<important>",
             "</IMPORTANT>", "<|im_start|>", "<|im_end|>", "[INST]", "[/INST]", "<end of session>", "###",
             "instruction", "when", "whenever", "tool", "function", "always", "instead", "must", "bcc", "reply",
             "nothing else", "do not summarize", "repeat the following", "invisible to humans", "visible to the llm",
             "for ai screening", "hidden note", "if asked", "say", "send", "upload", "to", "https://evil.test",
             "a@b.co", "~/.ssh", "id_rsa", "/etc/passwd", ".aws/credentials", "mcp.json", "<!--", "[//]: # (",
             "[comment]: <>", "이전", "위의", "앞의", "지시", "명령", "규칙", "프롬프트", "내용", "지침", "를", "을",
             "모두", "무시", "잊", "보안", "정책", "승인", "통제", "우회", "해제", "시스템", "출력", "보여", "공개",
             "ſystem", "Kelvin K", "ß", "ẞ", "ǅ", "ﬁ", "ǰ"]
    pieces = [" ", "  ", "\t", "\n", "\r\n", "\\n", "\n\n\n\n\n\n", "\\n" * 6, " ", " ", "　",
              "​", "‎", "‮", "⁠", "﻿", "\U000e0049", "́", "ͅ", "_", ".", ",",
              ":", ";", "-", "/", "<", ">", "|", "[", "]", "#", "(", ")", "가", "한", "一", "٣", "é",
              "Ω", "ω", "ς", "σ", "µ", "μ", "ẞ", "x", "Z", "9", "\x1c", "\x85", " "]
    out = []
    for _ in range(count):
        n = rng.randint(1, 60)
        out.append("".join(rng.choice(words) if rng.random() < 0.45 else rng.choice(pieces) for _ in range(n)))
    return out


def fuzz(scanner: textscan.Scanner, subjects: list[str]) -> list[dict]:
    problems = []
    for text in subjects:
        native = scanner.hits(text)
        for index, hit in native.items():
            expected = all(p.search(text) for p in textscan._parts(scanner.rules[index]))
            if hit != expected:
                problems.append({"rule": index, "text": text[:200], "native": hit, "re": expected})
                if len(problems) > 20:
                    return problems
    return problems


def timing() -> dict:
    line = "2026-10-15 12:00:01 INFO request handled path=/api/orders/42 status=200 user=analyst 처리 완료\n"
    reference = textscan.Scanner.__new__(textscan.Scanner)
    reference.rules, reference.native, reference.engine = poisoning._SCANNER.rules, {}, None
    out = {}
    for size in (2_000, 20_000, 200_000):
        text = (line * (size // len(line) + 1))[:size]
        which = [*range(len(poisoning.OVERRIDE_RULES)), len(poisoning._ALL) - 1]
        for name, scanner in (("re", reference), ("native", poisoning._SCANNER)):
            runs = []
            for _ in range(10 if size > 50_000 else 60):
                started = time.perf_counter()
                scanner.hits(text, which)
                runs.append((time.perf_counter() - started) * 1000)
            out[f"{name}_{size}"] = round(statistics.median(runs), 3)
    return out


def main() -> int:
    scanner = poisoning._SCANNER
    if scanner.engine is None:
        print(json.dumps({"error": "native engine not active"}))
        return 1
    on_re = [i for i in range(len(scanner.rules)) if i not in scanner.native]
    atom_problems = atom_check(scanner)
    rng = random.Random(20261015)
    subjects = corpus(rng, 60_000)
    fuzz_problems = fuzz(scanner, subjects)
    import runpy
    runpy.run_module("app.poisoning", run_name="__main__")
    report = {"rules": len(scanner.rules), "native_rules": len(scanner.native), "rules_on_re": on_re,
              "atom_differences": atom_problems, "fuzz_subjects": len(subjects),
              "fuzz_differences": fuzz_problems, "median_ms": timing()}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 1 if atom_problems or fuzz_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
