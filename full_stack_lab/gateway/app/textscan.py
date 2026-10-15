"""Tool-text rules on the native PCRE2 engine, deciding exactly as Python's re.

Each rule's parse tree (re._parser) is translated into PCRE2 syntax over a small
canonical alphabet: the characters the rules name, ASCII, and four category stand-ins
(word+decimal, word, space, other). mcpgw_textscan maps every subject character into
that alphabet with CPython's own lowercase/category functions, the ones _sre uses,
so case folding and Unicode classes are CPython's, not PCRE2's. Every single-character
atom is translated by asking re itself which alphabet symbols it accepts.

A rule that uses a construct this translator does not cover stays on re, and so does
everything when the extension is not installed or PCRE2 reports an error: the result
is the same, only slower. tests/textscan_parity_check.py verifies each atom over all
code points and fuzzes whole rules against re.
"""
from __future__ import annotations

import functools
import logging
import re
from re import _constants as C, _parser

try:
    import mcpgw_textscan
except ImportError:  # the image ships it; a source checkout may not
    mcpgw_textscan = None

try:
    from _sre import unicode_tolower as _tolower
except ImportError:  # pragma: no cover - CPython always has it
    _tolower = None

log = logging.getLogger("mcpgw.textscan")

# Canonical stand-ins (plane-16 private use, never named by a rule) and an ordinary
# character of each category that re is asked about on their behalf.
WORD_DECIMAL, WORD, SPACE, OTHER = 0x10FFF0, 0x10FFF1, 0x10FFF2, 0x10FFF3
STANDINS = (WORD_DECIMAL, WORD, SPACE, OTHER)
SAMPLES = {WORD_DECIMAL: "٣", WORD: "一", SPACE: " ", OTHER: "☃"}
MAX_REPEAT = 65535  # PCRE2's limit for a counted repeat


class Unsupported(ValueError):
    pass


def _groups() -> dict[int, int]:
    """The extra IGNORECASE equivalences _sre applies (i/ı, s/ſ, ...): each to its smallest member."""
    try:  # 3.11+: generated table used by re._compiler
        from re._casefix import _EXTRA_CASES as fixes
    except ImportError:  # older layout
        from re import _compiler
        fixes = getattr(_compiler, "_ignorecase_fixes", None)
    if not fixes:
        raise ImportError("re case-fold table not found")
    groups = {}
    for low, others in fixes.items():
        members = (low, *others)
        for member in members:
            groups[member] = min(members)
    return groups


GROUPS = _groups()


def _fold(code: int) -> int:
    low = _tolower(code)
    return GROUPS.get(low, low)


def _class_source(items: list) -> str:
    parts = []
    for op, av in items:
        if op is C.LITERAL:
            parts.append("\\U%08x" % av)
        elif op is C.RANGE:
            parts.append("\\U%08x-\\U%08x" % av)
        elif op is C.NEGATE:
            parts.insert(0, "^")
        elif op is C.CATEGORY:
            parts.append({C.CATEGORY_DIGIT: r"\d", C.CATEGORY_NOT_DIGIT: r"\D", C.CATEGORY_SPACE: r"\s",
                          C.CATEGORY_NOT_SPACE: r"\S", C.CATEGORY_WORD: r"\w", C.CATEGORY_NOT_WORD: r"\W"}[av])
        else:
            raise Unsupported(f"class item {op}")
    return "[" + "".join(parts) + "]"


def _atom_source(op, av) -> str | None:
    if op is C.LITERAL:
        return "\\U%08x" % av
    if op is C.NOT_LITERAL:
        return "[^\\U%08x]" % av
    if op is C.ANY:
        return "."
    if op is C.IN:
        return _class_source(av)
    return None


@functools.lru_cache(maxsize=4096)
def _atom(source: str, flags: int) -> re.Pattern:
    return re.compile(source, flags & (re.I | re.S | re.U))


def _named(tree, out: set[int]) -> None:
    for op, av in tree:
        if op in (C.LITERAL, C.NOT_LITERAL):
            out.add(av)
        elif op is C.IN:
            for item_op, item_av in av:
                if item_op is C.LITERAL:
                    out.add(item_av)
                elif item_op is C.RANGE:
                    low, high = item_av
                    if high - low > 4096:
                        raise Unsupported("range too wide for the alphabet")
                    out.update(range(low, high + 1))
        elif op is C.BRANCH:
            for alternative in av[1]:
                _named(alternative, out)
        elif op is C.SUBPATTERN:
            _named(av[3], out)
        elif op in (C.MAX_REPEAT, C.MIN_REPEAT):
            _named(av[2], out)
        elif op in (C.ASSERT, C.ASSERT_NOT):
            _named(av[1], out)


def _code_class(codes: set[int], universe: list[int]) -> str:
    if not codes:
        return "(*FAIL)"
    if len(codes) == len(universe):
        return "(?s:.)"
    ordered, parts, start, prev = sorted(codes), [], None, None
    for code in ordered + [None]:
        if code is not None and prev is not None and code == prev + 1:
            prev = code
            continue
        if start is not None:
            parts.append("\\x{%x}" % start if start == prev else "\\x{%x}-\\x{%x}" % (start, prev))
        start = prev = code
    return "[" + "".join(parts) + "]"


class _Translator:
    def __init__(self, alphabet: frozenset[int], folded: bool, flags: int):
        self.folded = folded
        self.flags = flags
        symbols = {_fold(code) for code in alphabet} if folded else set(alphabet)
        self.universe = sorted(symbols | set(STANDINS))
        word = _atom(r"\w", re.U)
        self.word = _code_class({s for s in self.universe if word.fullmatch(self.sample(s))}, self.universe)

    @staticmethod
    def sample(symbol: int) -> str:
        return SAMPLES.get(symbol) or chr(symbol)

    def single(self, op, av) -> str:
        pattern = _atom(_atom_source(op, av), self.flags)
        return _code_class({s for s in self.universe if pattern.fullmatch(self.sample(s))}, self.universe)

    def at(self, code) -> str:
        multiline = self.flags & re.M
        newline = "\\x{a}"
        if code is C.AT_BEGINNING_STRING or (code is C.AT_BEGINNING and not multiline):
            return r"\A"
        if code is C.AT_BEGINNING_LINE or code is C.AT_BEGINNING:
            return rf"(?:\A|(?<={newline}))"
        if code is C.AT_END_STRING:
            return r"\z"
        if code is C.AT_END and not multiline:
            return rf"(?={newline}?\z)"
        if code is C.AT_END_LINE or code is C.AT_END:
            return rf"(?={newline}|\z)"
        w = self.word
        if code in (C.AT_BOUNDARY, C.AT_UNI_BOUNDARY):
            return f"(?:(?<={w})(?!{w})|(?<!{w})(?={w}))"
        if code in (C.AT_NON_BOUNDARY, C.AT_UNI_NON_BOUNDARY):
            return rf"(?:(?!\A\z)(?:(?<={w})(?={w})|(?<!{w})(?!{w})))"
        raise Unsupported(f"anchor {code}")

    def emit(self, tree) -> str:
        out = []
        for op, av in tree:
            if op in (C.LITERAL, C.NOT_LITERAL, C.ANY, C.IN):
                out.append(self.single(op, av))
            elif op is C.AT:
                out.append(self.at(av))
            elif op is C.BRANCH:
                out.append("(?:" + "|".join(self.emit(alternative) for alternative in av[1]) + ")")
            elif op is C.SUBPATTERN:
                _group, add_flags, del_flags, body = av
                if add_flags or del_flags:
                    raise Unsupported("scoped inline flags")
                out.append("(?:" + self.emit(body) + ")")
            elif op in (C.MAX_REPEAT, C.MIN_REPEAT):
                low, high, body = av
                unbounded = high == C.MAXREPEAT
                if low > MAX_REPEAT or (not unbounded and high > MAX_REPEAT):
                    raise Unsupported("repeat count")
                count = "{%d,}" % low if unbounded else "{%d,%d}" % (low, high)
                out.append("(?:" + self.emit(body) + ")" + count + ("?" if op is C.MIN_REPEAT else ""))
            elif op in (C.ASSERT, C.ASSERT_NOT):
                direction, body = av
                kind = ("=" if op is C.ASSERT else "!")
                out.append("(?" + ("<" if direction < 0 else "") + kind + self.emit(body) + ")")
            else:
                raise Unsupported(f"op {op}")
        return "".join(out)


def _parts(rule) -> list[re.Pattern]:
    """A rule is a compiled pattern or an object whose .patterns must all match (poisoning._Both)."""
    if isinstance(rule, re.Pattern):
        return [rule]
    patterns = getattr(rule, "patterns", None)
    if isinstance(patterns, list) and all(isinstance(p, re.Pattern) for p in patterns):
        return patterns
    raise Unsupported("rule shape")


class Scanner:
    """Decides rule.search(text) for many rules at once; same answers as re."""

    def __init__(self, rules: list) -> None:
        self.rules = list(rules)
        self.native: dict[int, list[int]] = {}
        self.engine = None
        if mcpgw_textscan is None or _tolower is None:
            return
        try:
            parsed = {}
            named: set[int] = set(range(128))
            for index, rule in enumerate(self.rules):
                try:
                    trees = [(p, _parser.parse(p.pattern, p.flags)) for p in _parts(rule)]
                    for pattern, tree in trees:
                        if not isinstance(pattern.pattern, str):
                            raise Unsupported("bytes pattern")
                        _named(tree, named)
                    parsed[index] = trees
                except (Unsupported, re.error) as exc:
                    log.info("rule %d stays on re: %s", index, exc)
            # Every symbol a folded subject can contain must be in the alphabet as well.
            alphabet = frozenset(named | {_fold(code) for code in named})
            if any(code in alphabet for code in STANDINS) or any(ord(s) in alphabet for s in SAMPLES.values()):
                raise Unsupported("stand-in collides with a named character")
            engine = mcpgw_textscan.Engine("".join(map(chr, sorted(alphabet))),
                                           "".join(map(chr, STANDINS)), dict(GROUPS))
            translators = {}
            for index, trees in parsed.items():
                try:
                    ids = []
                    for pattern, tree in trees:
                        folded = bool(pattern.flags & re.I)
                        key = (folded, pattern.flags & (re.I | re.S | re.M))
                        translator = translators.get(key) or translators.setdefault(
                            key, _Translator(alphabet, folded, pattern.flags))
                        ids.append(engine.add(translator.emit(tree), folded))
                    self.native[index] = ids
                except (Unsupported, ValueError) as exc:
                    log.info("rule %d stays on re: %s", index, exc)
            self.engine = engine
        except (Unsupported, ValueError, MemoryError) as exc:
            log.warning("native text rules disabled: %s", exc)
            self.native, self.engine = {}, None

    def hits(self, text: str, which: list[int] | None = None) -> dict[int, bool]:
        """{index: rule.search(text) is not None} for the requested rules (all by default)."""
        pending = list(range(len(self.rules)) if which is None else which)
        result = dict.fromkeys(pending, False)
        if self.engine is not None and self.native:
            order = [(index, part) for index in pending if index in self.native for part in self.native[index]]
            try:
                matched = self.engine.search(text, [part for _, part in order])
            except ValueError as exc:
                log.warning("native text rules fell back to re: %s", exc)
            else:
                verdict: dict[int, bool] = {}
                for (index, _), hit in zip(order, matched):
                    verdict[index] = verdict.get(index, True) and hit
                for index, hit in verdict.items():
                    result[index] = hit
                pending = [index for index in pending if index not in verdict]
        for index in pending:
            result[index] = all(p.search(text) for p in _parts(self.rules[index]))
        return result
