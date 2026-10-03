"""MCP 도입 요청의 격리 검증 워커.

제출된 저장소 URL은 "가져와서 실행해도 된다"는 뜻이 아니다. 이 워커는 Gateway와
분리된 컨테이너에서 얕은 복제만 수행하고, 저장소의 코드를 한 줄도 실행하지 않은
채로 SBOM·SCA·SAST 증적을 만든다.

Gateway가 이 일을 하지 않는 이유: Gateway는 정책 집행 경로이고 외부 저장소를
내려받는 프로세스가 아니다. 두 역할이 한 프로세스에 있으면 복제 단계의 결함이
곧바로 정책 집행 프로세스의 결함이 된다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from exit_terms import conclude, investigate, readme

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mcp:demo-only-change-me@db:5432/mcp_governance")
WORK_DIR = Path(os.getenv("INTAKE_WORK_DIR", "/work"))
REPORT_DIR = Path(os.getenv("REPORT_DIR", "/reports"))
RULES = Path(os.getenv("SEMGREP_RULES", "/rules/semgrep-mcp.yml"))
POLL_SECONDS = int(os.getenv("INTAKE_POLL_SECONDS", "5"))
CLONE_TIMEOUT = int(os.getenv("INTAKE_CLONE_TIMEOUT", "120"))
SCAN_TIMEOUT = int(os.getenv("INTAKE_SCAN_TIMEOUT", "600"))
MAX_CHECKOUT_MB = int(os.getenv("INTAKE_MAX_CHECKOUT_MB", "512"))
VALIDATION_LEASE_SECONDS = CLONE_TIMEOUT + SCAN_TIMEOUT * 4 + 300
VALIDATION_MAX_ATTEMPTS = 3

SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

WORKER_ID = os.getenv("INTAKE_WORKER_ID", "intake-worker-1")


def log(message: str) -> None:
    print(f"[intake-worker] {message}", flush=True)


def run(command: list[str], timeout: int, cwd: Path | None = None,
        extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """저장소의 코드가 아니라 스캐너만 실행한다.

    환경을 비워 넘기는 이유: 복제 대상 저장소가 심어둔 git 설정이나 자격증명이
    스캐너 프로세스로 흘러가지 않게 하기 위해서다.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": "/tmp",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
        "GIT_CONFIG_NOSYSTEM": "1",
        "SEMGREP_SEND_METRICS": "off",
        "TRIVY_CACHE_DIR": os.environ.get("TRIVY_CACHE_DIR", "/trivy-cache"),
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(command, cwd=cwd, env=env, timeout=timeout,
                          capture_output=True, text=True, check=False)


SAFE_GIT = [
    "git",
    "-c", "core.hooksPath=/dev/null",
    "-c", "protocol.file.allow=never",
    "-c", "submodule.recurse=false",
    "-c", "core.symlinks=false",
]


def clone(repository_url: str, target: Path, commit: str | None = None) -> str:
    """얕은 복제 + hook·submodule 비활성. 체크아웃 후 .git을 지운다.

    commit을 주면 그 커밋만 가져온다. 재검사가 "그때 검증한 코드"가 아니라
    "지금의 기본 브랜치"를 보면 두 결과를 나란히 둘 수 없다.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if commit:
        target.mkdir(parents=True, exist_ok=True)
        steps = [
            (SAFE_GIT + ["init", "--quiet"], target),
            (SAFE_GIT + ["remote", "add", "origin", repository_url], target),
            (SAFE_GIT + ["fetch", "--depth", "1", "--no-tags", "origin", commit], target),
            (SAFE_GIT + ["checkout", "--quiet", "FETCH_HEAD"], target),
        ]
        for command, cwd in steps:
            result = run(command, timeout=CLONE_TIMEOUT, cwd=cwd)
            if result.returncode != 0:
                raise RuntimeError(f"git {command[len(SAFE_GIT)]} 실패: {result.stderr.strip()[:300]}")
    else:
        result = run(SAFE_GIT + [
            "clone", "--depth", "1", "--single-branch", "--no-tags",
            repository_url, str(target),
        ], timeout=CLONE_TIMEOUT)
        if result.returncode != 0:
            raise RuntimeError(f"git clone 실패: {result.stderr.strip()[:300]}")
    head = run(["git", "rev-parse", "HEAD"], timeout=30, cwd=target)
    commit = head.stdout.strip() if head.returncode == 0 else (commit or "unknown")
    shutil.rmtree(target / ".git", ignore_errors=True)
    size_mb = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) / 1_048_576
    if size_mb > MAX_CHECKOUT_MB:
        raise RuntimeError(f"체크아웃이 {size_mb:.0f}MB로 상한({MAX_CHECKOUT_MB}MB)을 넘었습니다.")
    return commit


def relative(path: str, root: Path) -> str:
    """증적에는 저장소 안의 경로만 남긴다. 워커의 임시 체크아웃 경로는
    검토자에게 의미가 없고 요청 ID까지 노출한다."""
    prefix = str(root).rstrip("/") + "/"
    return path[len(prefix):] if path.startswith(prefix) else path


def trivy_counts(report: Path, root: Path) -> tuple[dict[str, int], list[dict]]:
    if not report.exists():
        return {level: 0 for level in SEVERITY_ORDER}, []
    document = json.loads(report.read_text(encoding="utf-8") or "{}")
    counts = {level: 0 for level in SEVERITY_ORDER}
    findings: list[dict] = []
    for result in document.get("Results") or []:
        target = result.get("Target", "")
        for group, title_key in (("Vulnerabilities", "Title"), ("Misconfigurations", "Title"), ("Secrets", "Title")):
            for item in result.get(group) or []:
                severity = str(item.get("Severity", "UNKNOWN")).upper()
                if severity in counts:
                    counts[severity] += 1
                findings.append({
                    "severity": severity,
                    "id": item.get("VulnerabilityID") or item.get("ID") or item.get("RuleID") or group,
                    "title": item.get(title_key) or item.get("Message") or group,
                    "target": relative(target, root),
                    "package": item.get("PkgName"),
                    "installed_version": item.get("InstalledVersion"),
                    "fixed_version": item.get("FixedVersion"),
                    "reference": item.get("PrimaryURL"),
                })
    return counts, findings[:200]


def semgrep_counts(report: Path, root: Path) -> tuple[dict[str, int], list[dict]]:
    if not report.exists():
        return {level: 0 for level in SEVERITY_ORDER}, []
    document = json.loads(report.read_text(encoding="utf-8") or "{}")
    mapping = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}
    counts = {level: 0 for level in SEVERITY_ORDER}
    findings: list[dict] = []
    for item in document.get("results") or []:
        extra = item.get("extra") or {}
        severity = mapping.get(str(extra.get("severity", "INFO")).upper(), "LOW")
        counts[severity] += 1
        findings.append({
            "severity": severity,
            "id": item.get("check_id", "semgrep"),
            "title": (extra.get("message") or "")[:200],
            "target": relative(item.get("path", ""), root),
        })
    return counts, findings[:200]


def gitleaks_counts(report: Path, root: Path) -> tuple[dict[str, int], list[dict]]:
    document = json.loads(report.read_text(encoding="utf-8"))
    if not isinstance(document, list) or any(not isinstance(item, dict) or not item.get("RuleID") for item in document):
        raise ValueError("Gitleaks 결과가 올바르지 않습니다.")
    # Strip source snippets even from the downloadable artifact; --redact alone may
    # leave the rest of a sensitive line in Match.
    findings = [{"severity": "HIGH", "id": str(item["RuleID"]), "title": str(item.get("Description") or "Secret 발견")[:200],
                 "target": relative(str(item.get("File") or ""), root), "line": item.get("StartLine")}
                for item in document]
    report.write_text(json.dumps(findings, ensure_ascii=False), encoding="utf-8")
    return {level: len(findings) if level == "HIGH" else 0 for level in SEVERITY_ORDER}, findings[:200]


def sbom_components(report: Path) -> int:
    if not report.exists():
        return 0
    document = json.loads(report.read_text(encoding="utf-8") or "{}")
    return len(document.get("components") or [])


def sbom_inventory(report: Path) -> dict:
    document = json.loads(report.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("bomFormat") != "CycloneDX" or not isinstance(document.get("components", []), list):
        raise ValueError("Syft가 유효한 CycloneDX SBOM을 생성하지 않았습니다.")
    components = document.get("components") or []
    if not all(isinstance(component, dict) for component in components):
        raise ValueError("SBOM 구성요소 형식이 올바르지 않습니다.")
    return {"components": len(components), "truncated": len(components) > 200,
            "inventory": [{"name": c.get("name"), "version": c.get("version"),
                           "type": c.get("type"), "purl": c.get("purl"),
                           "licenses": c.get("licenses", [])} for c in components[:200]]}


def store_report(connection, scanner: str, version: str, source_ref: str, path: Path,
                 counts: dict[str, int], summary: dict) -> None:
    connection.execute(
        """INSERT INTO supply_chain_reports(
             scanner, scanner_version, source_ref, report_path, status,
             critical_count, high_count, medium_count, summary)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (scanner, version, source_ref, str(path), "IMPORTED",
         counts.get("CRITICAL", 0), counts.get("HIGH", 0), counts.get("MEDIUM", 0), Jsonb(summary)),
    )


def validate(connection, request: dict) -> None:
    request_id = str(request["id"])
    url = request["repository_url"]
    owner_repo = url.removeprefix("https://github.com/")
    checkout = WORK_DIR / request_id
    shutil.rmtree(checkout, ignore_errors=True)
    log(f"{request_id} 검증 시작: {url}")
    commit = clone(url, checkout)
    source_ref = f"intake:{owner_repo}@{commit[:12]}"
    sbom = REPORT_DIR / f"intake-{request_id}-sbom.cdx.json"
    trivy = REPORT_DIR / f"intake-{request_id}-trivy.json"
    semgrep = REPORT_DIR / f"intake-{request_id}-semgrep.json"
    gitleaks = REPORT_DIR / f"intake-{request_id}-gitleaks.json"
    terms_report = REPORT_DIR / f"intake-{request_id}-exit-terms.json"
    discovery = investigate(checkout, url, commit)
    # D-50: the platform concludes (Jev when TYPESAFE_API_KEY is set, strict rules otherwise);
    # the admin approves on that conclusion or accepts the risk, instead of re-reading the docs.
    conclusion = conclude(discovery, readme(checkout), request.get("requested_transport") or "streamable-http",
                          os.getenv("TYPESAFE_API_KEY", ""))
    discovery["conclusion"] = conclusion
    terms_report.write_text(json.dumps(discovery, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence = {"exit_terms_discovery": discovery, "exit_terms_conclusion": conclusion,
                "reports": [terms_report.name], "scanners": {}}
    # Persist source and investigation before long scanner runs. Failures must
    # not discard evidence already collected by successful stages.
    connection.execute(
        """UPDATE mcp_intake_requests SET commit_sha=%s, source_ref=%s,
                  evidence=%s, updated_at=now() WHERE id=%s AND status='VALIDATING'""",
        (commit, source_ref, Jsonb(evidence), request["id"]))
    connection.commit()
    scans = {
        "syft": (sbom, ["syft", f"dir:{checkout}", "--source-name", owner_repo,
                        "--source-version", commit[:12], "-o", f"cyclonedx-json={sbom}"]),
        "trivy": (trivy, ["trivy", "fs", "--scanners", "vuln,misconfig,secret,license",
                          "--format", "json", "--output", str(trivy), "--exit-code", "0", str(checkout)]),
        "semgrep": (semgrep, ["semgrep", "scan", "--config", str(RULES), "--json",
                              "--output", str(semgrep), "--metrics", "off", "--quiet", str(checkout)]),
        "gitleaks": (gitleaks, ["gitleaks", "dir", str(checkout), "--no-banner", "--redact=100", "--exit-code=0",
                                "--report-format=json", f"--report-path={gitleaks}", "--ignore-gitleaks-allow",
                                "--config=/rules/gitleaks.toml", "--gitleaks-ignore-path=/dev/null"]),
    }
    failures = []
    counts = {level: 0 for level in SEVERITY_ORDER}
    components = 0
    for name, (path, command) in scans.items():
        # An old output must not make a retried failed scanner look successful.
        path.unlink(missing_ok=True)
        try:
            result = run(command, timeout=SCAN_TIMEOUT)
            if result.returncode != 0 or not path.exists():
                output = (result.stderr or result.stdout).strip().splitlines()
                raise RuntimeError(f"exit {result.returncode}: " + " | ".join(output[-3:])[:300])
            levels = {level: 0 for level in SEVERITY_ORDER}
            if name == "syft":
                summary = sbom_inventory(path)
                components = summary["components"]
            else:
                document = json.loads(path.read_text(encoding="utf-8"))
                if name == "semgrep" and (not isinstance(document.get("results"), list) or document.get("errors")):
                    raise ValueError("Semgrep의 검사 결과가 불완전합니다.")
                if name == "trivy" and not document.get("SchemaVersion"):
                    raise ValueError("Trivy 결과의 SchemaVersion이 없습니다.")
                levels, findings = {"trivy": trivy_counts, "semgrep": semgrep_counts, "gitleaks": gitleaks_counts}[name](path, checkout)
                summary = {"findings": findings, "total": sum(levels.values()),
                           "truncated": sum(levels.values()) > len(findings)}
            summary.update({"repository": owner_repo, "commit": commit})
            scanner, version = {"syft": ("Syft", "v1.51.1"), "trivy": ("Trivy", "0.74.0"),
                                "semgrep": ("Semgrep", "1.172.0"), "gitleaks": ("Gitleaks", "8.30.1")}[name]
            connection.execute("DELETE FROM supply_chain_reports WHERE source_ref=%s AND report_path=%s",
                               (source_ref, str(path)))
            store_report(connection, scanner, version, source_ref, path, levels, summary)
            for level in counts:
                counts[level] += levels[level]
            evidence["reports"].append(path.name)
            evidence["scanners"][name] = {"status": "DONE"}
        except (RuntimeError, ValueError, TypeError, AttributeError, OSError, subprocess.TimeoutExpired) as exc:
            error = str(exc)[:400]
            failures.append(f"{name}: {error}")
            evidence["scanners"][name] = {"status": "FAILED", "error": error}
        evidence.update({"sbom_components": components, **{k.lower(): v for k, v in counts.items()}})
        connection.execute(
            """UPDATE mcp_intake_requests SET evidence=%s, updated_at=now()
               WHERE id=%s AND status='VALIDATING'""", (Jsonb(evidence), request["id"]))
        connection.commit()
    critical, high, medium = counts["CRITICAL"], counts["HIGH"], counts["MEDIUM"]
    risk = "UNASSESSED" if failures else "CRITICAL" if critical else "HIGH" if high else "MEDIUM" if medium else "LOW"
    status = "FAILED" if failures else "REJECTED" if critical else "VALIDATED"
    note = (f"격리 검증 완료 · SBOM 구성요소 {components}개 · "
            f"Critical {critical} / High {high} / Medium {medium} · commit {commit[:12]}")
    if critical and not failures:
        note += " · 치명적 발견이 있어 자동 거부했습니다."
    if failures:
        note = "격리 검증 미완료 · " + " · ".join(failures)
    connection.execute(
        """UPDATE mcp_intake_requests
           SET status=%s, risk_level=%s, review_note=%s, commit_sha=%s, source_ref=%s,
               evidence=%s, validated_at=CASE WHEN %s THEN NULL ELSE now() END,
               validation_lease_expires_at=NULL, updated_at=now()
           WHERE id=%s AND status='VALIDATING'""",
        (status, risk, note, commit, source_ref, Jsonb(evidence), bool(failures), request["id"]))
    shutil.rmtree(checkout, ignore_errors=True)
    log(f"{request_id} -> {status} ({risk})")


def heartbeat(connection) -> None:
    """A queue nobody serves must not read as work in progress."""
    connection.execute(
        """INSERT INTO worker_heartbeats(worker, role, seen_at, detail)
           VALUES (%s, 'intake', now(), %s)
           ON CONFLICT (worker) DO UPDATE SET seen_at=now(), detail=EXCLUDED.detail""",
        (WORKER_ID, Jsonb({"poll_seconds": POLL_SECONDS})),
    )


def claim(connection) -> dict | None:
    cursor = connection.execute(
        """UPDATE mcp_intake_requests SET status='VALIDATING', updated_at=now(),
                  validation_attempts=validation_attempts+1,
                  validation_lease_expires_at=now() + make_interval(secs => %s)
           WHERE id = (SELECT id FROM mcp_intake_requests WHERE status='VALIDATION_QUEUED'
                       ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
           RETURNING id, repository_url, display_name, requested_transport""", (VALIDATION_LEASE_SECONDS,))
    return cursor.fetchone()


def reclaim_intake(connection) -> None:
    """A stopped worker must not leave an automatically queued request stuck forever."""
    connection.execute(
        """UPDATE mcp_intake_requests
           SET status=CASE WHEN validation_attempts >= %s THEN 'FAILED' ELSE 'VALIDATION_QUEUED' END,
               validation_lease_expires_at=NULL, updated_at=now(),
               commit_sha=NULL, source_ref=NULL, evidence='{}', validated_at=NULL,
               risk_level='UNASSESSED',
               review_note='검증 워커 lease가 만료되었습니다. 자동 재예약 또는 수동 재검증이 필요합니다.'
           WHERE status='VALIDATING' AND
                 (validation_lease_expires_at IS NULL OR validation_lease_expires_at < now())""",
        (VALIDATION_MAX_ATTEMPTS,))


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    log("대기 중 · worker=%s" % WORKER_ID)
    while True:
        try:
            with psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False) as connection:
                while True:
                    # 매 회전마다 살아 있음을 남기고, 죽은 워커가 들고 있던 작업을
                    # 먼저 회수한다. 이 두 줄이 없으면 실패한 감사가 조용히 영구
                    # 대기 상태로 남는다.
                    heartbeat(connection)
                    reclaim_intake(connection)
                    connection.commit()

                    while True:
                        request = claim(connection)
                        if not request:
                            connection.commit()
                            break
                        connection.commit()
                        try:
                            validate(connection, request)
                            connection.commit()
                        except Exception as exc:  # 검증 실패도 결과다. 조용히 대기열에 남기지 않는다.
                            connection.rollback()
                            log("%s 실패: %s" % (request["id"], exc))
                            connection.execute(
                                """UPDATE mcp_intake_requests
                                   SET status='FAILED', risk_level='UNASSESSED',
                                       review_note=%s, validation_lease_expires_at=NULL,
                                       updated_at=now() WHERE id=%s AND status='VALIDATING'""",
                                ("격리 검증 실패: " + str(exc)[:400], request["id"]),
                            )
                            connection.commit()
                            shutil.rmtree(WORK_DIR / str(request["id"]), ignore_errors=True)

                    time.sleep(POLL_SECONDS)
        except psycopg.Error as exc:
            log("데이터베이스 재연결 대기: %s" % exc)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
