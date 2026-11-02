"""Prepare a release of the deployment repository (MCP-governance/mint) from a tag of this repository.

usage: python .github/release/make_mint.py vX.Y.Z <mint checkout>

Replaces the checkout's files with the tagged code minus the development material (agent rules, research wiki,
design documents, CI), points README links at what was left out to this repository at the same tag, stages the
result with the executable bits, and writes the CHANGELOG section of that version to .git/mint-release-notes.md.
Commit, tag, push and the GitHub release stay manual (AGENTS.md 「릴리스」).
"""
import io
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

DEV = "https://github.com/MCP-governance/mcp-gateway"
RAW = "https://raw.githubusercontent.com/MCP-governance/mcp-gateway"
DROP_DIRS = ("research/", "docs/", ".github/", "endpoint-agent/tests-windows/")
# deploy/check.py checks this repository's documents; the Windows development tests name the test appliance.
DROP_FILES = {"AGENTS.md", "CLAUDE.md", "todo.md", "WINDOWS-RESULT.md", "MANUAL_TEST_WINDOWS.md", "deploy/check.py"}
# Markdown that ships: what users read, and the prompt the workstation image hands to harnesses.
KEEP_MD = {"CHANGELOG.md", "full_stack_lab/workstation/managed/bob/harness-prompt.md"}
LINK = re.compile(r'(!\[[^\]]*\]\(|\]\(|(?:src|href)=")([^)"\s]+)')


def kept(path):
    if path.startswith(DROP_DIRS) or path in DROP_FILES:
        return False
    return not path.endswith(".md") or path in KEEP_MD or posixpath.basename(path).startswith("README")


def rewrite(path, text, shipped, everything, tag):
    def under(paths, target):
        return target in paths or any(p.startswith(target.rstrip("/") + "/") for p in paths)

    def fix(match):
        prefix, target = match.groups()
        if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:|#|/", target):
            return match.group(0)
        file, hashmark, anchor = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), file))
        if under(shipped, resolved) or not under(everything, resolved):
            return match.group(0)
        if prefix.startswith(("!", "src")):
            url = f"{RAW}/{tag}/{resolved}"
        else:
            url = f"{DEV}/{'blob' if resolved in everything else 'tree'}/{tag}/{resolved}"
        return prefix + url + hashmark + anchor

    return LINK.sub(fix, text)


def notes(changelog, version):
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", changelog, re.S | re.M)
    if not match:
        raise SystemExit(f"CHANGELOG.md has no [{version}] section")
    return match.group(1).strip() + "\n"


def main(tag, out):
    out = Path(out)
    if not (out / ".git").exists():
        raise SystemExit(f"{out} is not a git checkout")
    archive = subprocess.check_output(["git", "-c", "core.autocrlf=false", "archive", "--format=tar", tag])
    modes = {}
    for line in subprocess.check_output(["git", "ls-tree", "-r", "-z", tag]).decode().split("\0"):
        if line:
            meta, path = line.split("\t", 1)
            modes[path] = meta.split()[0]
    shipped = {p for p in modes if kept(p)}
    for child in out.iterdir():
        if child.name != ".git":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            if not member.isfile() or member.name not in shipped:
                continue
            data = tar.extractfile(member).read()
            if member.name.endswith(".md"):
                data = rewrite(member.name, data.decode("utf-8"), shipped, modes, tag).encode("utf-8")
            elif member.name == ".gitattributes":
                data = b"".join(l for l in data.splitlines(True) if b"research/" not in l and "통합 시트".encode() not in l)
            target = out / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if modes[member.name] == "100755":
                os.chmod(target, 0o755)
    subprocess.check_call(["git", "-C", str(out), "-c", "core.autocrlf=false", "add", "-A"])
    for path in sorted(p for p in shipped if modes[p] == "100755"):
        subprocess.check_call(["git", "-C", str(out), "update-index", "--chmod=+x", "--", path])
    version = tag.removeprefix("v")
    (out / ".git" / "mint-release-notes.md").write_text(notes((out / "CHANGELOG.md").read_text(encoding="utf-8"), version),
                                                       encoding="utf-8")
    print(f"{len(shipped)} files staged in {out}; release notes in .git/mint-release-notes.md")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
