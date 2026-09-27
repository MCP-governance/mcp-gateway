"""Bounded document investigation; repository content is never executed or trusted."""
from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import re
from urllib.parse import quote

MAX_FILES = 200
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024
MAX_EVIDENCE = 8
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "vendor", "dist", "build"}
CRITERIA = {
    "C1": ("보유 자격·대상 고지", "provider_credential_disclosure",
           r"credential|access.token|refresh.token|api.key|secret|보유.{0,10}자격|자격.{0,10}고지"),
    "C2": ("회수 수행 권한", "revocation_evidence",
           r"revok|revocation|deauthoriz|permission|administrator|권한|폐기|회수"),
    "C3": ("회수·만료 연속성", None,
           r"expir|time.to.live|\bttl\b|refresh|session.{0,15}(end|terminat)|만료|갱신|세션.{0,10}종료"),
    "C4": ("회수 증거·감사 접근", "audit_access_retained",
           r"audit|introspect|revocation.{0,20}(log|evidence)|retention|감사|회수.{0,10}증거|로그.{0,10}보존"),
}


def investigate(root: Path, repository_url: str, commit: str) -> dict:
    """Return commit-pinned candidate evidence, never verified flags or a T grade."""
    results = {key: {"label": label, "review_field": field, "status": "NOT_FOUND", "evidence": []}
               for key, (label, field, _) in CRITERIA.items()}
    patterns = {key: re.compile(spec[2], re.I) for key, spec in CRITERIA.items()}
    scanned = 0
    size = 0
    skipped = 0
    limited = False
    visited = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        visited += len(files) + 1
        if visited > 5000:
            limited = True
            break
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or path.suffix.lower() not in {".md", ".rst", ".txt", ".adoc"}:
                continue
            if scanned >= MAX_FILES or size >= MAX_TOTAL_BYTES:
                limited = True
                break
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    skipped += 1
                    continue
                # Bound the actual read as well as stat (the checkout may change).
                with path.open("rb") as stream:
                    content = stream.read(MAX_FILE_BYTES + 1)
                if len(content) > MAX_FILE_BYTES or size + len(content) > MAX_TOTAL_BYTES:
                    skipped += 1
                    limited = True
                    continue
                text = content.decode("utf-8")
            except (OSError, UnicodeError):
                skipped += 1
                continue
            scanned += 1
            size += len(content)
            relative = path.relative_to(root).as_posix()
            for number, line in enumerate(text.splitlines(), 1):
                for key, pattern in patterns.items():
                    result = results[key]
                    if len(result["evidence"]) < MAX_EVIDENCE and pattern.search(line):
                        result["status"] = "CANDIDATE"
                        result["evidence"].append({
                            "path": relative, "line": number, "excerpt": line.strip()[:300],
                            "url": f"{repository_url}/blob/{commit}/{quote(relative)}#L{number}",
                        })
        if scanned >= MAX_FILES or size >= MAX_TOTAL_BYTES:
            limited = True
            break
    return {
        "method": "repository-document-search", "status": "REVIEW_REQUIRED",
        "repository_url": repository_url, "commit": commit,
        "investigated_at": datetime.now(UTC).isoformat(), "criteria": results,
        "scanned_files": scanned, "skipped_files": skipped, "truncated": limited,
        "limitations": "문서의 후보 근거입니다. 제공자 고지의 완전성·실제 회수 권한·회수 후 상태·감사 접근은 관리자가 확인해야 합니다.",
    }
