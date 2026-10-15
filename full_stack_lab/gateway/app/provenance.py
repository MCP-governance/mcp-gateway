"""Where an intake came from, and whether the artifact in use is the artifact that was scanned (D-90).

The intake worker records a digest of the source tree it scanned; the Gateway side recomputes it
from the copy employees will actually use and compares. Provider-hosted servers have no artifact
to hash: they are recorded as "not applicable" with their endpoint, never with a made-up digest.

supply_chain/provenance.py carries the same two functions for the worker (its image has a
separate build context); tests/provenance_check.py fails if the two ever disagree.
"""
from __future__ import annotations

import hashlib
import os
import re
import tarfile
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

VULN_DB_MAX_AGE = timedelta(days=7)
MAX_ARCHIVE_BYTES = int(os.getenv("INTAKE_MAX_CHECKOUT_MB", "512")) * 1_048_576
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NOT_APPLICABLE = "해당 없음"


def manifest_digest(entries: Iterable[tuple[str, str]]) -> str:
    """sha256 over `<file sha256>  <relative path>` lines, ordered by path."""
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
    """Digest of the regular files under root (the .git directory is not part of the artifact)."""
    entries, total = [], 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" in relative.parts or path.is_symlink() or not path.is_file():
            continue
        digest, size = _file_digest(path)
        entries.append((relative.as_posix(), digest))
        total += size
    return {"sha256": manifest_digest(entries), "files": len(entries), "bytes": total}


def archive_digest(source: BinaryIO, limit: int = MAX_ARCHIVE_BYTES) -> dict:
    """The same digest from a git archive (tar, optionally gzip) with its top-level directory.

    A symlink counts as a file holding its target: that is how the worker's checkout
    (core.symlinks=false) writes it.
    """
    entries, total = [], 0
    with tarfile.open(fileobj=source, mode="r|*") as archive:
        for member in archive:
            parts = Path(member.name).parts[1:]
            if not (member.isfile() or member.issym()):
                continue
            if not parts or ".." in parts or member.name.startswith("/"):
                raise ValueError("보관본에 허용되지 않는 경로가 있습니다.")
            if member.issym():
                data = member.linkname.encode()
                entries.append(("/".join(parts), hashlib.sha256(data).hexdigest()))
                total += len(data)
                continue
            digest, reader = hashlib.sha256(), archive.extractfile(member)
            for block in iter(lambda: reader.read(1 << 20), b""):
                digest.update(block)
                total += len(block)
                if total > limit:
                    raise ValueError("보관본이 크기 상한을 넘었습니다.")
            entries.append(("/".join(parts), digest.hexdigest()))
    return {"sha256": manifest_digest(entries), "files": len(entries), "bytes": total}


def missing(record: dict | None, *, intake_kind: str, source_url: str = "") -> list[str]:
    """What a provenance record still lacks. Empty means complete, not verified."""
    record = record or {}
    problems = []
    if record.get("kind") != ("provider-hosted" if intake_kind == "remote-endpoint" else "source"):
        return ["출처 기록 없음"]
    if not record.get("source_url") or (source_url and record["source_url"] != source_url):
        problems.append("공급 주소")
    artifact = record.get("artifact") or {}
    if record["kind"] == "provider-hosted":
        if not record.get("version"):
            problems.append("제공자 버전")
        if artifact.get("applicable") is not False or artifact.get("sha256"):
            problems.append("배포 파일 구분")
        return problems
    if not COMMIT.fullmatch(str(record.get("version") or "")):
        problems.append("고정 커밋")
    if not (record.get("license") or {}).get("spdx"):
        problems.append("라이선스")
    if not SHA256.fullmatch(str(artifact.get("sha256") or "")):
        problems.append("배포 파일 해시")
    return problems


def verification(record: dict | None) -> dict:
    return (record or {}).get("verification") or {}


def vuln_db_age(updated_at: datetime | None, now: datetime | None = None) -> timedelta | None:
    return None if updated_at is None else (now or datetime.now(UTC)) - updated_at
