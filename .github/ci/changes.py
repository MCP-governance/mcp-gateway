"""Classify NUL-separated git diff paths; unknown paths require all checks."""
import sys
from pathlib import PurePosixPath


def docs_only(paths):
    if not paths:
        return False
    for name in paths:
        path = PurePosixPath(name)
        if path.parts[0] not in ("docs", "research"):
            return False
        if path.suffix.lower() not in (".md", ".rst", ".txt", ".adoc"):
            return False
        if path.name.lower().startswith(("requirements", "constraints")) or path.name == "CMakeLists.txt":
            return False
        if name.startswith("research/llm-wiki/analysis/") or any(
            part in ("generated", "snapshots", "exports") for part in path.parts
        ):
            return False
    return True


if __name__ == "__main__":
    paths = sys.stdin.buffer.read().decode("utf-8").split("\0")
    print(f"code={str(not docs_only([name for name in paths if name])).lower()}")
