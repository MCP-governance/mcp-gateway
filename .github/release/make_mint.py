"""Prepare a release of the deployment repository (MCP-governance/mint) from a tag of this repository.

usage: python .github/release/make_mint.py vX.Y.Z <mint checkout>

The release holds what an organisation runs: the production bundle (deploy/) and the server components it builds
and mounts, the employee PC kit, the LiteLLM add-on and the policy-as-code package. The lab, tests and development
material stay here. User documentation comes from .github/release/mint/ (README files, CHANGELOG, assets).
The result must have no development traces (traces.py) and no relative link outside itself; it is staged with the
executable bits, and the CHANGELOG section of the version is written to .git/mint-release-notes.md.
Commit, tag, push and the GitHub release stay manual (AGENTS.md 「릴리스」).
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

INCLUDE = (
    "VERSION", ".gitattributes",
    "deploy/", "endpoint-agent/", "addons/litellm/", "policy/pac/",
    "full_stack_lab/gateway/", "full_stack_lab/opa/", "full_stack_lab/privacy/", "full_stack_lab/supply_chain/",
    "full_stack_lab/model-proxy/", "full_stack_lab/field/", "full_stack_lab/registry/field/",
    "full_stack_lab/registry/provenance-trust-keys.json", "full_stack_lab/db/init.sql", "full_stack_lab/db/002-litellm.sql",
    "full_stack_lab/corp/gitea-entrypoint.sh",
)
# deploy/check.py checks this repository's documents; the OPA replay cases are test fixtures, not policy data;
# acceptance.py and experiments.py run the lab's checks and nothing in the gateway imports them.
EXCLUDE = ("endpoint-agent/tests-windows/", "deploy/check.py", "full_stack_lab/opa/replay_cases",
           "full_stack_lab/gateway/app/acceptance.py", "full_stack_lab/gateway/app/experiments.py")
TEST = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.(rego|py)|[^/]*\.test\.[cm]?js)$")
OVERLAY = Path(__file__).resolve().parent / "mint"
LINK = re.compile(r'(?:\]\(|(?:src|href)=")([^)"\s]+)')


def shipped(path):
    return (path.startswith(INCLUDE) and not path.startswith(EXCLUDE) and not TEST.search(path)
            and not path.endswith(".md"))


def notes(changelog, version):
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", changelog, re.S | re.M)
    if not match:
        raise SystemExit(f"CHANGELOG.md has no [{version}] section")
    return match.group(1).strip() + "\n"


def broken_links(out):
    bad = []
    for page in out.rglob("*.md"):
        if ".git" in page.parts:
            continue
        for target in LINK.findall(page.read_text(encoding="utf-8")):
            if "MCP-governance/mcp-gateway" in target:
                bad.append(f"{page.relative_to(out)} -> {target}")
            if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:|#|/", target):
                continue
            if not (page.parent / target.split("#", 1)[0]).exists():
                bad.append(f"{page.relative_to(out)} -> {target}")
    return bad


def main(tag, out):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from traces import hits

    out = Path(out)
    if not (out / ".git").exists():
        raise SystemExit(f"{out} is not a git checkout")
    archive = subprocess.check_output(["git", "-c", "core.autocrlf=false", "archive", "--format=tar", tag])
    modes = {}
    for line in subprocess.check_output(["git", "ls-tree", "-r", "-z", tag]).decode().split("\0"):
        if line:
            meta, path = line.split("\t", 1)
            modes[path] = meta.split()[0]
    files = {p for p in modes if shipped(p)}
    for child in out.iterdir():
        if child.name != ".git":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            if not member.isfile() or member.name not in files:
                continue
            data = tar.extractfile(member).read()
            if member.name == ".gitattributes":
                # Rules for the lab's own files and the research wiki name paths the release does not have.
                data = b"".join(line for line in data.splitlines(True) if not line.startswith((b"full_stack_lab/", b"research/"))
                                and "통합 시트".encode() not in line)
            target = out / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if modes[member.name] == "100755":
                os.chmod(target, 0o755)
    for source in OVERLAY.rglob("*"):
        if source.is_file():
            target = out / source.relative_to(OVERLAY)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    problems = broken_links(out)
    for path in out.rglob("*"):
        if path.is_file() and ".git" not in path.relative_to(out).parts:
            name = path.relative_to(out).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            problems += [f"{name}:{number}: {line[:120]}" for number, line, _ in hits(name, text)]
    if problems:
        print("\n".join(problems))
        raise SystemExit(f"{len(problems)} traces or broken links; nothing staged")
    subprocess.check_call(["git", "-C", str(out), "-c", "core.autocrlf=false", "add", "-A"])
    for path in sorted(p for p in files if modes[p] == "100755"):
        subprocess.check_call(["git", "-C", str(out), "update-index", "--chmod=+x", "--", path])
    (out / ".git" / "mint-release-notes.md").write_text(
        notes((out / "CHANGELOG.md").read_text(encoding="utf-8"), tag.removeprefix("v")), encoding="utf-8")
    count = len(subprocess.check_output(["git", "-C", str(out), "ls-files"]).splitlines())
    print(f"{count} files staged in {out}; release notes in .git/mint-release-notes.md")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
