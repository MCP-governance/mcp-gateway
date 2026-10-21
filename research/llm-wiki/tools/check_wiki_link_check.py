"""Self-check for check_wiki's link rule: file ok, tracked directory ok, missing path fails.

Runs check() against a throwaway wiki and Git repository so the real wiki is not read for these links.
"""
import contextlib
import io
import json
import subprocess
import tempfile
from pathlib import Path

import check_wiki


def run_check(repo, wiki):
    check_wiki.REPO, check_wiki.ROOT = repo, wiki
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        check_wiki.check()
    return json.loads(out.getvalue())["errors"]


def demo():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        repo = Path(tmp).resolve()
        wiki = repo / "wiki"
        (wiki / "docs").mkdir(parents=True)
        (wiki / "docs/a.md").write_text("# a\n", encoding="utf-8")
        (wiki / "pkg").mkdir()
        (wiki / "pkg/x.txt").write_text("x\n", encoding="utf-8")
        (wiki / "sources/live").mkdir(parents=True)
        (wiki / "sources/live/acquisition-2026-10-13.json").write_text("[]", encoding="utf-8")
        (wiki / "solutions/evidence").mkdir(parents=True)
        (wiki / "solutions/evidence/manifest.json").write_text("[]", encoding="utf-8")
        (wiki / "README.md").write_text(
            "[file](docs/a.md)\n[dir](pkg/)\n[missing](nope/)\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "wiki/pkg/x.txt"], check=True)

        errors = run_check(repo, wiki)
        assert "Missing local file: docs/a.md" not in errors, errors
        assert "Missing local file: pkg/" not in errors, errors
        assert "Missing local file: nope/" in errors, errors
    print("check_wiki link rule: ok")


if __name__ == "__main__":
    demo()
