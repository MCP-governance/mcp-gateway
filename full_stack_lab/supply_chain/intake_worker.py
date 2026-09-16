"""MCP 도입 요청의 격리 검증 워커.

제출된 저장소 URL은 "가져와서 실행해도 된다"는 뜻이 아니다. 이 워커는 Gateway와
분리된 컨테이너에서 얕은 복제만 수행하고, 저장소의 코드를 한 줄도 실행하지 않은
채로 SBOM·SCA·SAST 증적을 만든다. 실행이 필요한 검사(AI-Infra-Guard mcp-scan의
동적 분석 등)는 여기서 하지 않는다.

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
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mcp:demo-only-change-me@db:5432/mcp_governance")
WORK_DIR = Path(os.getenv("INTAKE_WORK_DIR", "/work"))
REPORT_DIR = Path(os.getenv("REPORT_DIR", "/reports"))
RULES = Path(os.getenv("SEMGREP_RULES", "/rules/semgrep-mcp.yml"))
POLL_SECONDS = int(os.getenv("INTAKE_POLL_SECONDS", "5"))
CLONE_TIMEOUT = int(os.getenv("INTAKE_CLONE_TIMEOUT", "120"))
SCAN_TIMEOUT = int(os.getenv("INTAKE_SCAN_TIMEOUT", "600"))
MAX_CHECKOUT_MB = int(os.getenv("INTAKE_MAX_CHECKOUT_MB", "512"))

SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def log(message: str) -> None:
    print(f"[intake-worker] {message}", flush=True)


def run(command: list[str], timeout: int, cwd: Path | None = None) -> subprocess.CompletedProcess:
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
    return subprocess.run(command, cwd=cwd, env=env, timeout=timeout,
                          capture_output=True, text=True, check=False)


def clone(repository_url: str, target: Path) -> str:
    """얕은 복제 + hook·submodule 비활성. 체크아웃 후 .git을 지운다."""
    target.parent.mkdir(parents=True, exist_ok=True)
    result = run([
        "git",
        "-c", "core.hooksPath=/dev/null",
        "-c", "protocol.file.allow=never",
        "-c", "submodule.recurse=false",
        "clone", "--depth", "1", "--single-branch", "--no-tags",
        "--config", "core.symlinks=false",
        repository_url, str(target),
    ], timeout=CLONE_TIMEOUT)
    if result.returncode != 0:
        raise RuntimeError(f"git clone 실패: {result.stderr.strip()[:300]}")
    head = run(["git", "rev-parse", "HEAD"], timeout=30, cwd=target)
    commit = head.stdout.strip() if head.returncode == 0 else "unknown"
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


def sbom_components(report: Path) -> int:
    if not report.exists():
        return 0
    document = json.loads(report.read_text(encoding="utf-8") or "{}")
    return len(document.get("components") or [])


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

    scans = {
        "syft": (sbom, ["syft", f"dir:{checkout}", "--source-name", owner_repo,
                        "--source-version", commit[:12], "-o", f"cyclonedx-json={sbom}"]),
        "trivy": (trivy, ["trivy", "fs", "--scanners", "vuln,misconfig,secret,license",
                          "--format", "json", "--output", str(trivy), "--exit-code", "0", str(checkout)]),
        "semgrep": (semgrep, ["semgrep", "scan", "--config", str(RULES), "--json",
                              "--output", str(semgrep), "--metrics", "off", "--quiet", str(checkout)]),
    }
    # 스캐너 종료코드를 보지 않으면 "출력 파일이 없어서 발견 0건"과 "정말 깨끗해서
    # 0건"이 같은 화면이 된다. 증적 없는 통과가 가장 위험한 결과다.
    failures: list[str] = []
    for name, (path, command) in scans.items():
        result = run(command, timeout=SCAN_TIMEOUT)
        if result.returncode != 0 or not path.exists():
            # 스캐너 오류는 마지막 줄에 있다. 앞에서 자르면 진행 로그만 남는다.
            output = (result.stderr or result.stdout).strip().splitlines()
            failures.append(f"{name}(exit {result.returncode}): " + " | ".join(output[-3:])[:300])
    if failures:
        raise RuntimeError(" · ".join(failures))

    trivy_severity, trivy_findings = trivy_counts(trivy, checkout)
    semgrep_severity, semgrep_findings = semgrep_counts(semgrep, checkout)
    components = sbom_components(sbom)

    store_report(connection, "Syft", "v1.51.1", source_ref, sbom,
                 {level: 0 for level in SEVERITY_ORDER},
                 {"components": components, "repository": owner_repo, "commit": commit})
    store_report(connection, "Trivy", "0.74.0", source_ref, trivy, trivy_severity,
                 {"findings": trivy_findings, "repository": owner_repo, "commit": commit})
    store_report(connection, "Semgrep", "1.172.0", source_ref, semgrep, semgrep_severity,
                 {"findings": semgrep_findings, "repository": owner_repo, "commit": commit})

    critical = trivy_severity["CRITICAL"] + semgrep_severity["CRITICAL"]
    high = trivy_severity["HIGH"] + semgrep_severity["HIGH"]
    medium = trivy_severity["MEDIUM"] + semgrep_severity["MEDIUM"]
    # 치명적 발견이 있으면 사람이 판단할 때까지 활성 Registry 후보가 되지 않는다.
    # 자동 승인은 하지 않는다. 자동으로 올릴 수 있는 것은 "거부"뿐이다.
    risk = "CRITICAL" if critical else "HIGH" if high else "MEDIUM" if medium else "LOW"
    status = "REJECTED" if critical else "VALIDATED"
    note = (f"격리 검증 완료 · SBOM 구성요소 {components}개 · "
            f"Critical {critical} / High {high} / Medium {medium} · commit {commit[:12]}")
    if critical:
        note += " · 치명적 발견이 있어 자동 거부했습니다."

    connection.execute(
        """UPDATE mcp_intake_requests
           SET status=%s, risk_level=%s, review_note=%s, commit_sha=%s, source_ref=%s,
               evidence=%s, validated_at=now(), updated_at=now()
           WHERE id=%s""",
        (status, risk, note, commit, source_ref,
         Jsonb({"sbom_components": components, "critical": critical, "high": high, "medium": medium,
                "reports": [p.name for p in (sbom, trivy, semgrep) if p.exists()]}),
         request["id"]),
    )
    shutil.rmtree(checkout, ignore_errors=True)
    log(f"{request_id} -> {status} ({risk})")


def claim(connection) -> dict | None:
    cursor = connection.execute(
        """UPDATE mcp_intake_requests SET status='VALIDATING', updated_at=now()
           WHERE id = (SELECT id FROM mcp_intake_requests WHERE status='VALIDATION_QUEUED'
                       ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
           RETURNING id, repository_url, display_name""")
    return cursor.fetchone()


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    log("대기 중")
    while True:
        try:
            with psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False) as connection:
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
                        log(f"{request['id']} 실패: {exc}")
                        connection.execute(
                            """UPDATE mcp_intake_requests
                               SET status='FAILED', risk_level='UNASSESSED',
                                   review_note=%s, updated_at=now() WHERE id=%s""",
                            (f"격리 검증 실패: {str(exc)[:400]}", request["id"]),
                        )
                        connection.commit()
                        shutil.rmtree(WORK_DIR / str(request["id"]), ignore_errors=True)
        except psycopg.Error as exc:
            log(f"데이터베이스 재연결 대기: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
