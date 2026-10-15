"""Digest of the scanned source tree. Must stay identical to gateway/app/provenance.py:
the Gateway recomputes it from the copy employees use (tests/provenance_check.py compares them)."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path


def manifest_digest(entries: Iterable[tuple[str, str]]) -> str:
    body = "".join(f"{digest}  {path}\n" for path, digest in sorted(entries))
    return hashlib.sha256(body.encode()).hexdigest()


def _file_digest(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def tree_digest(root: Path) -> dict:
    entries, total = [], 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" in relative.parts or path.is_symlink() or not path.is_file():
            continue
        digest, size = _file_digest(path)
        entries.append((relative.as_posix(), digest))
        total += size
    return {"sha256": manifest_digest(entries), "files": len(entries), "bytes": total}
