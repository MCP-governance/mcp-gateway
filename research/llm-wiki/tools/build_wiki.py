"""Inventory the Markdown research wiki; no browser reader is generated."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def markdown_files():
    return [path for path in sorted(ROOT.rglob("*.md"))
            if path.relative_to(ROOT).parts[0] not in ("web", "tools", "local-sources")
            and "__pycache__" not in path.parts]


def build():
    catalogs = {path.stem: len(json.loads(path.read_text(encoding="utf-8-sig")))
                for path in sorted((ROOT / "catalogs").glob("*.json"))}
    result = {"format": "markdown", "pages": len(markdown_files()), "catalogs": catalogs,
              "collaboration_console": "research/collaboration-console/README.md"}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()
