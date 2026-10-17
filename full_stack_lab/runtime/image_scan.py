"""Periodic scans of the exact local image, with a deadline that survives retries."""
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trivy_scan import database_time, trivy_counts

INTERVAL = int(os.getenv("RUNTIME_SCAN_INTERVAL_SECONDS", "86400"))
DEADLINE_DAYS = int(os.getenv("RUNTIME_CRITICAL_DEADLINE_DAYS", "7"))
TIMEOUT = int(os.getenv("RUNTIME_SCAN_TIMEOUT_SECONDS", "600"))
if min(INTERVAL, DEADLINE_DAYS, TIMEOUT) <= 0:
    raise ValueError("Runtime scan settings must be positive")


def assess(findings, previous, now, days=DEADLINE_DAYS):
    critical = {}
    for finding in findings:
        if finding["severity"] != "CRITICAL":
            continue
        key = json.dumps([finding[k] for k in ("id", "target", "package", "installed_version")])
        critical[key] = previous.get(key, now.isoformat())
    overdue = [key for key, first in critical.items()
               if now >= datetime.fromisoformat(first) + timedelta(days=days)]
    return {"critical": critical, "overdue": overdue, "deadline_days": days}


def scan(image_id, previous, now):
    if not image_id.startswith("sha256:") or len(image_id) != 71:
        raise ValueError("An immutable local image ID is required")
    with tempfile.TemporaryDirectory(prefix="runtime-scan-") as folder:
        report = Path(folder) / "trivy.json"
        result = subprocess.run(
            ["trivy", "image", "--image-src", "docker", "--scanners", "vuln", "--format", "json",
             "--output", str(report), "--exit-code", "0", image_id],
            capture_output=True, text=True, timeout=TIMEOUT, check=False)
        if result.returncode:
            raise RuntimeError("운영 이미지 검사기 실행 실패")
        document = json.loads(report.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or not isinstance(document.get("Metadata"), dict) \
                or document["Metadata"].get("ImageID") != image_id:
            raise ValueError("검사 결과의 이미지 식별자가 실행 이미지와 다름")
        version = subprocess.run(["trivy", "version", "--format", "json"], capture_output=True,
                                 text=True, timeout=60, check=False)
        version_info = json.loads(version.stdout) if version.returncode == 0 else {}
        database = database_time(version_info)
        if database is None or not timedelta(0) <= now - database <= timedelta(days=7):
            raise RuntimeError("취약점 데이터베이스 갱신 기한 초과 또는 확인 불가")
        counts, findings = trivy_counts(report, Path("/"), limit=None)
        return {"status": "checked", "scanner": "Trivy", "scanner_version": version_info.get("Version"),
                "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                "database_at": database.isoformat(), "counts": counts,
                "findings": findings, **assess(findings, previous, now)}


def rescan(connection, runtime, event):
    from psycopg.types.json import Jsonb
    now = datetime.now(timezone.utc)
    acquired = connection.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s)) AS acquired",
                                  ("image-scan:" + runtime["image_id"],)).fetchone()
    if not acquired["acquired"]:
        connection.commit()
        return None
    latest = connection.execute(
        "SELECT * FROM runtime_image_scans WHERE image_id=%s ORDER BY id DESC LIMIT 1",
        (runtime["image_id"],)).fetchone()
    previous = latest["result"].get("critical", {}) if latest else {}
    try:
        overdue = any(now >= datetime.fromisoformat(first) + timedelta(days=DEADLINE_DAYS) for first in previous.values())
    except (ValueError, TypeError, AttributeError):
        overdue = True
    if latest and latest["runtime_id"] == runtime["id"] and latest["result"].get("status") == "checked" \
            and (now - latest["checked_at"]).total_seconds() < INTERVAL and not overdue:
        connection.commit()
        return None
    try:
        result = scan(runtime["image_id"], previous, now)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError, RuntimeError) as exc:
        result = {"status": "failed", "error": str(exc)[:300], "critical": previous}
    connection.execute("INSERT INTO runtime_image_scans(runtime_id,image_id,result) VALUES (%s,%s,%s)",
                       (runtime["id"], runtime["image_id"], Jsonb(result)))
    reason = ("운영 이미지 검사 실패" if result["status"] == "failed" else
              "치명 취약점 조치 기한 초과" if result["overdue"] else None)
    event(connection, runtime, "runtime-image-scan", "held" if reason else "recorded",
          reason=reason, scope={"image_id": runtime["image_id"], "scan": result})
    if reason:
        connection.execute(
            """INSERT INTO ops_suspensions(server_id,source,reason,evidence)
               SELECT registered_server_id,'image-scan',%s,%s FROM mcp_intake_requests
               WHERE id=%s AND registered_server_id IS NOT NULL
               ON CONFLICT (server_id) WHERE resumed_at IS NULL DO NOTHING""",
            (reason, Jsonb({"runtime_id": str(runtime["id"]), "image_id": runtime["image_id"]}), runtime["intake_id"]))
        connection.execute(
            """UPDATE mcp_servers SET status='DISABLED',status_reason=%s
               WHERE id=(SELECT registered_server_id FROM mcp_intake_requests WHERE id=%s)""",
            (reason, runtime["intake_id"]))
    connection.commit()
    return reason
