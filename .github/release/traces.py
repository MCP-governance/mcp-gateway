"""Development traces in the files a release ships, and a check that cleaning them changed only comments.

usage: python .github/release/traces.py scan [REF]            # traces in the release scope of REF (default HEAD)
       python .github/release/traces.py guard BASE [PATH...]  # changed files differ from BASE only in comments
"""
import ast
import io
import re
import subprocess
import sys
import tokenize

# Anywhere in a shipped file: work-process notes, test machines, internal documents, decision numbers.
STRONG = re.compile(
    r"(?<![\w-])D-\d{2,3}\b|\b[Pp][Jj][1-3]\b|\bwinvm\b|\bkali(?:-linux)?\b|\bDEV-\d+\b|\bW\d{1,2}-[A-Z]\b"
    r"|실측|소유자 (?:지시|규칙)|질책|사용자 지시|팀원|\bWBS\b|Codex가|\bMythos\b|\bastra\b|\bkuku\b"
    r"|docs/ai/|research/|llm-wiki|AGENTS\.md|CLAUDE\.md|DECISIONS\.md|RUNBOOK\.md|github\.com/MCP-governance/mcp-gateway")
# In comments and docstrings only: dates, change-request numbers, model lanes, internal iterations, the lab,
# unfinished-work markers.
SOFT = re.compile(
    r"\bPR ?#\d+|(?<![\w&])#\d{2,3}\b|\b(?:sol|luna|terra|Opus|Sonnet|Haiku)\b|\bv[2-4]\b|\b[Ll]ab\b|실습"
    r"|\bTODO\b|\bFIXME\b|\bXXX\b|\bHACK\b|\bPAC-15\b|팀 룰셋|레인\b")
# A date is a trace unless it names an MCP specification revision.
DATE = re.compile(r"\b(?:20\d\d-)?(?:0?[1-9]|1[0-2])-[0-3]\d\b")
SPEC = re.compile(r"MCP|[Rr]evision|[Ss]pec|transport|Streamable|protocolVersion")

HASH = ("#",)
SLASH = ("//", "/*", "*/")
STYLE = {".py": "py", ".sh": HASH, ".ps1": HASH, ".psm1": HASH, ".yaml": HASH, ".yml": HASH, ".toml": HASH,
         ".rego": HASH, ".conf": HASH, ".in": HASH, ".example": HASH, ".js": SLASH, ".mjs": SLASH, ".cjs": SLASH,
         ".go": SLASH, ".c": SLASH, ".css": SLASH, ".sql": ("--",), ".html": ("<!--",), ".cmd": ("rem ", "::")}


def style(path):
    name = path.rsplit("/", 1)[-1]
    if name in ("Dockerfile", "Caddyfile", ".gitignore", ".gitattributes") or name.endswith((".Dockerfile", ".caddy")):
        return HASH
    for suffix, kind in STYLE.items():
        if name.endswith(suffix):
            return kind
    return None


def _python(text):
    """(line, comment text) for comments and docstrings."""
    found = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            found.append((token.start[0], token.string))
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                for offset, line in enumerate(first.value.value.splitlines()):
                    found.append((first.lineno + offset, line))
    return found


def _segments(kind, text):
    """Split each line into (code, comment) with the line-comment markers and block comments of its language."""
    block = {"/*": "*/", "<#": "#>", "<!--": "-->"}
    opener = None
    out = []
    for line in text.splitlines():
        code, comment, rest = "", "", line
        while rest:
            if opener:
                end = rest.find(block[opener])
                if end < 0:
                    comment += rest
                    rest = ""
                else:
                    comment += rest[:end + len(block[opener])]
                    rest = rest[end + len(block[opener]):]
                    opener = None
                continue
            starts = [(rest.find(o), o) for o in block if (kind is SLASH and o == "/*") or (kind is HASH and o == "<#")
                      or (kind == ("<!--",) and o == "<!--")]
            starts = [(i, o) for i, o in starts if i >= 0]
            line_marks = [m for m in kind if m not in ("/*", "*/", "<!--")]
            singles = [m.start() for m in (re.search(r"(?:^|(?<=[\s;,(){}\[\]]))" + re.escape(mark), rest)
                                           for mark in line_marks) if m]
            first_block = min(starts) if starts else None
            first_line = min(singles) if singles else None
            if first_block is not None and (first_line is None or first_block[0] < first_line):
                code += rest[:first_block[0]]
                opener = first_block[1]
                rest = rest[first_block[0] + len(opener):]
                comment += opener
            elif first_line is not None:
                code += rest[:first_line]
                comment += rest[first_line:]
                rest = ""
            else:
                code += rest
                rest = ""
        out.append((code, comment))
    return out


def comments(path, text):
    kind = style(path)
    if kind == "py":
        return _python(text)
    if not kind:
        return []
    return [(number, comment) for number, (_, comment) in enumerate(_segments(kind, text), 1) if comment.strip()]


def hits(path, text):
    """(line, text, strong) for every trace; strong traces count anywhere, soft ones only in comments."""
    found = {}
    for number, comment in comments(path, text):
        if STRONG.search(comment) or SOFT.search(comment) or (DATE.search(comment) and not SPEC.search(comment)):
            found[number] = (number, comment.strip(), "comment")
    for number, line in enumerate(text.splitlines(), 1):
        if number not in found and STRONG.search(line):
            found[number] = (number, line.strip(), "code")
    return sorted(found.values())


def _no_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                first.value.value = ""
    return ast.dump(tree, include_attributes=False)


def same_code(path, before, after):
    kind = style(path)
    if kind == "py":
        return _no_docstrings(ast.parse(before)) == _no_docstrings(ast.parse(after))
    if not kind:
        return before == after

    def code(text):
        return [c.rstrip() for c, _ in _segments(kind, text) if c.strip()]
    return code(before) == code(after)


def _git(*args):
    return subprocess.check_output(["git", *args])


def _shipped():
    sys.path.insert(0, __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0])
    from make_mint import shipped
    return shipped


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("scan", "guard"):
        raise SystemExit(__doc__)
    shipped = _shipped()
    if sys.argv[1] == "scan":
        ref = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
        total = 0
        for path in _git("ls-tree", "-r", "--name-only", ref).decode().splitlines():
            if not shipped(path):
                continue
            try:
                text = _git("show", f"{ref}:{path}").decode("utf-8")
            except UnicodeDecodeError:
                continue
            for number, line, where in hits(path, text):
                total += 1
                print(f"{path}:{number}: [{where}] {line[:160]}")
        print(f"{total} traces", file=sys.stderr)
        raise SystemExit(1 if total else 0)
    base, paths = sys.argv[2], sys.argv[3:] or _git("diff", "--name-only", sys.argv[2]).decode().split()
    bad = []
    for path in paths:
        try:
            before = _git("show", f"{base}:{path}").decode("utf-8")
        except subprocess.CalledProcessError:
            continue
        with open(path, encoding="utf-8", newline="") as handle:
            after = handle.read()
        try:
            ok = same_code(path, before, after)
        except SyntaxError as error:
            ok, path = False, f"{path} ({error})"
        if not ok:
            bad.append(path)
    for path in bad:
        print("code changed:", path)
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
