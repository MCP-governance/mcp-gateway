"""Bind selected test runs to their source, environment, and unchanged evidence."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path


SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def records(path: Path) -> list[tuple[int, bytes, dict]]:
    rows = []
    for number, raw in enumerate(path.read_bytes().splitlines(keepends=True), 1):
        if raw.strip():
            rows.append((number, raw, json.loads(raw)))
    return rows


def selected_legacy_runs(repo: Path, manifest: dict) -> dict[str, dict]:
    """Reproduce the 10-15 score from explicit historical rows, never a last-row lookup."""
    if manifest.get("schema_version") != 1 or manifest.get("mode") != "historical":
        raise ValueError("historical manifest required")
    path = repo / "research/llm-wiki/analysis/wbs-1015/lab-results.jsonl"
    if sha256(path.read_bytes()) != manifest.get("log_sha256"):
        raise ValueError("historical lab log changed")
    by_line = {number: (raw, row) for number, raw, row in records(path)}
    selected = {}
    for test, reference in manifest["selected"].items():
        number = reference["line"]
        if number not in by_line:
            raise ValueError(f"{test}: selected line missing")
        raw, row = by_line[number]
        if row.get("test") != test or sha256(raw) != reference["row_sha256"]:
            raise ValueError(f"{test}: selected historical row changed")
        selected[test] = {**row, "evidence_status": "historical", "selected_line": number}
    return selected


def _evidence_status(repo: Path, items: list[dict]) -> str:
    if not items:
        return "failed"
    for item in items:
        name = item.get("path", "")
        path = (repo / name).resolve()
        if not name or not path.is_relative_to(repo.resolve()) or not path.is_file():
            return "failed"
        if not SHA256.fullmatch(item.get("raw_sha256", "")):
            return "failed"
        raw = path.read_bytes()
        if sha256(raw) != item["raw_sha256"]:
            return "failed"
        if item.get("transform") == "CRLF->LF":
            if not SHA256.fullmatch(item.get("canonical_lf_sha256", "")):
                return "failed"
            if sha256(raw.replace(b"\r\n", b"\n")) != item["canonical_lf_sha256"]:
                return "failed"
        elif item.get("transform") != "none" or item.get("canonical_lf_sha256") is not None:
            return "failed"
    return "valid"


def _run_metadata_status(row: dict) -> str:
    try:
        started = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(row["finished_at"].replace("Z", "+00:00"))
        if started.tzinfo is None or finished.tzinfo is None or finished < started:
            return "failed"
        counts = [row[key] for key in ("checked", "passed", "failed", "unknown")]
        if any(type(value) is not int or value < 0 for value in counts):
            return "failed"
        if counts[0] != sum(counts[1:]):
            return "failed"
        if counts[0] == 0 or counts[2] != 0 or counts[3] != 0:
            return "failed"
        if not COMMIT.fullmatch(row["source_commit"]):
            return "failed"
        image = row["image_digest"]
        if image != "none" and not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            return "failed"
        if not isinstance(row["environment"], str) or not row["environment"].strip():
            return "failed"
    except (KeyError, TypeError, ValueError, AttributeError):
        return "failed"
    return "valid"


def selected_current_runs(repo: Path, manifest: dict, source_commit: str,
                          image_digest: str, environment: str) -> dict[str, dict]:
    """Return every selected run with an explicit current-validity state."""
    if manifest.get("schema_version") != 2 or manifest.get("mode") != "current":
        raise ValueError("current manifest required")
    if not COMMIT.fullmatch(source_commit) or not image_digest or not environment:
        raise ValueError("current source, image, and environment are required")
    runs_name = manifest.get("runs_path", "")
    runs_path = (repo / runs_name).resolve()
    if not runs_name or not runs_path.is_relative_to(repo.resolve()) or not runs_path.is_file():
        raise ValueError("runs path missing or outside repository")
    if sha256(runs_path.read_bytes()) != manifest.get("runs_sha256"):
        raise ValueError("selected runs log changed")
    all_runs = {}
    for _, _, row in records(runs_path):
        run_id = row.get("run_id", "")
        try:
            if str(uuid.UUID(run_id)) != run_id:
                raise ValueError("noncanonical run ID")
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("invalid run ID") from exc
        if run_id in all_runs:
            raise ValueError(f"duplicate run ID: {run_id}")
        all_runs[run_id] = row
    selected = {}
    for test, run_id in manifest.get("selected", {}).items():
        if run_id not in all_runs:
            raise ValueError(f"{test}: selected run missing")
        row = all_runs[run_id]
        if row.get("test") != test:
            raise ValueError(f"{test}: selected run is for another test")
        if (type(row.get("rc")) is not int or row["rc"] != 0
                or _run_metadata_status(row) != "valid"):
            status = "failed"
        elif _evidence_status(repo, row.get("evidence", [])) != "valid":
            status = "failed"
        elif (row.get("source_commit") != source_commit
              or row.get("image_digest") != image_digest
              or row.get("environment") != environment):
            status = "recheck"
        else:
            status = "valid"
        selected[test] = {**row, "evidence_status": status}
    return selected
