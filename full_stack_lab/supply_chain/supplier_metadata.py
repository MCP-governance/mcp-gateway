"""Read metadata as data in the scanner checkout; never import or execute a package."""
from __future__ import annotations

import json
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None


def collect(root: Path, source_url: str, commit: str) -> dict:
    values = {}
    sources = {}

    def read(name):
        path = root / name
        if (any(part.is_symlink() for part in [path, *path.parents] if part != root.parent)
                or root.resolve() not in path.resolve().parents or not path.is_file() or path.stat().st_size > 256 * 1024):
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    def take(key, value, source, limit=300):
        if isinstance(value, str) and value.strip() and key not in values:
            values[key] = value.strip()[:limit]
            sources[key] = {"path": source, "commit": commit}

    try:
        package = json.loads(read("package.json") or "{}")
        author = package.get("author") or {}
        take("legal_entity", author.get("name") if isinstance(author, dict) else author, "package.json", 200)
        take("supplier_contact", author.get("email") if isinstance(author, dict) else None, "package.json")
        take("homepage", package.get("homepage"), "package.json", 500)
    except (ValueError, AttributeError, TypeError):
        pass
    try:
        project = (tomllib.loads(read("pyproject.toml")) if tomllib else {}).get("project") or {}
        for author in project.get("authors") or []:
            take("legal_entity", author.get("name"), "pyproject.toml", 200)
            take("supplier_contact", author.get("email"), "pyproject.toml")
        take("homepage", (project.get("urls") or {}).get("Homepage"), "pyproject.toml", 500)
    except (ValueError, AttributeError, TypeError):
        pass
    for name in ("SECURITY.md", ".github/SECURITY.md"):
        security = read(name)
        # Only the exact pinned file is proposed; statements about support/EOL are never guessed.
        if security:
            take("vulnerability_policy_url", f"{source_url}/blob/{commit}/{name}", name, 500)
            emails = re.findall(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", security)
            if emails:
                take("security_contact", emails[0], name)
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        text = read(name)
        owner = re.search(r"(?im)^copyright[^\n]*?\b\d{4}(?:\s*[-,]\s*\d{4})?\s+(.+)$", text)
        if owner:
            take("legal_entity", owner.group(1), name, 200)
    return {**values, "sources": sources}
