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
from urllib.parse import urlsplit

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

# AI-Infra-Guard mcp-scan은 OpenAI 호환 endpoint를 요구한다. 값이 없으면 작업을
# 만들 수도 없고, 있으면 그 모델·endpoint가 결과와 함께 기록된다.
MCP_SCAN_API_KEY = os.getenv("MCP_SCAN_API_KEY", "")
MCP_SCAN_BASE_URL = os.getenv("MCP_SCAN_BASE_URL", "")
MCP_SCAN_MODEL = os.getenv("MCP_SCAN_MODEL", "")
MCP_SCAN_TIMEOUT = int(os.getenv("MCP_SCAN_TIMEOUT", "900"))
MCP_SCAN_LANGUAGE = os.getenv("MCP_SCAN_LANGUAGE", "en")  # CLI가 지원하는 값은 zh/en
# A.I.G 결과가 실제 모델 판단인지, 배선 검증용 test double인지 구분한다. 후자를
# 통제 증적으로 세면 "연결됐다"가 "안전하다/차단했다"로 바뀌는 착시가 생긴다.
MCP_SCAN_EVIDENCE_MODE = os.getenv("MCP_SCAN_EVIDENCE_MODE", "live").strip().lower()
MCP_SCAN_EVIDENCE_MODES = {"live", "advisory", "test-double"}
SARIF_LEVELS = {"error": "HIGH", "warning": "MEDIUM", "note": "LOW", "none": "LOW"}

WORKER_ID = os.getenv("INTAKE_WORKER_ID", "intake-worker-1")
# lease는 "이 작업을 이 시각까지 들고 있겠다"는 선언이다. 스캔 자체의 상한보다
# 넉넉히 잡되 무한은 아니다. 워커가 죽으면 이 시각 뒤에 다른 워커가 회수한다.
# 회수가 없으면 RUNNING 한 줄이 그 대상을 영구히 감사 불가로 만든다.
SCAN_LEASE_SECONDS = int(os.getenv("MCP_SCAN_LEASE_SECONDS", str(MCP_SCAN_TIMEOUT + 300)))
SCAN_MAX_ATTEMPTS = int(os.getenv("MCP_SCAN_MAX_ATTEMPTS", "3"))


class ScanTimeout(RuntimeError):
    """An expired model scan needs a new configuration, not an immediate retry."""

# 구조적 트리거. 감사는 "관리자가 기억날 때"가 아니라 아래 시점에 걸려야 한다.
#   T1 격리 검증 통과 직후  - 승인을 판단하기 전에 증적이 있어야 한다.
#   T2 승인 게이트          - Gateway API가 집행한다(agent_service).
#   T3 재감사 주기 도래     - 심사한 코드와 지금 도는 코드는 시간이 지나면 갈라진다.
#   T4 catalog drift        - 계약이 바뀌었으면 코드 감사도 다시 해야 한다.
AUTO_ON_VALIDATED = os.getenv("MCP_SCAN_AUTO_ON_VALIDATED", "1") not in ("0", "false", "")
AUTO_JOBS = os.getenv("MCP_SCAN_AUTO_JOBS", "1") not in ("0", "false", "")
RESCAN_DAYS = int(os.getenv("MCP_SCAN_RESCAN_DAYS", "30"))
RESCAN_SWEEP_SECONDS = int(os.getenv("MCP_SCAN_RESCAN_SWEEP_SECONDS", "900"))


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


# mcp-scan의 SARIF 변환기(utils/sarif_formatter.py)는 critical과 high를 둘 다
# level="error"로 접고, 모델이 매긴 원래 등급은 properties.severity에 자유 문자열로
# 남긴다(영문·중문 혼용). 그래서 level만 보면 CRITICAL이 구조적으로 존재할 수 없고,
# MCP-SUPPLY-001이 세는 치명점에 영원히 0으로 기여한다. "AI 코드 감사를 돌렸다"와
# "그 결과가 무언가를 막을 수 있다"가 끊어져 있었다는 뜻이다.
SARIF_SEVERITY_TEXT = {
    "critical": "CRITICAL", "严重": "CRITICAL", "치명": "CRITICAL",
    "high": "HIGH", "高危": "HIGH", "높음": "HIGH",
    "medium": "MEDIUM", "中危": "MEDIUM", "보통": "MEDIUM",
    "low": "LOW", "低危": "LOW", "낮음": "LOW",
    "info": "LOW", "informational": "LOW",
}


def sarif_severity(item: dict, rules: dict) -> str:
    """SARIF 결과 하나의 심각도를 정한다.

    우선순위는 (1) 도구가 남긴 원래 등급 문자열, (2) SARIF 표준 수치
    security-severity, (3) 마지막으로 3단계 level이다. 앞의 둘이 없을 때만
    level로 내려가므로 다른 SARIF 생산자도 그대로 받는다.
    """
    properties = item.get("properties") or {}
    rule_properties = (rules.get(str(item.get("ruleId") or "")) or {}).get("properties") or {}

    text = str(properties.get("severity") or rule_properties.get("severity") or "").strip().lower()
    if text in SARIF_SEVERITY_TEXT:
        return SARIF_SEVERITY_TEXT[text]

    raw = properties.get("security-severity", rule_properties.get("security-severity"))
    if raw is not None:
        try:
            score = float(raw)
        except (TypeError, ValueError):
            score = None
        if score is not None:
            if score >= 9.0:
                return "CRITICAL"
            if score >= 7.0:
                return "HIGH"
            if score >= 4.0:
                return "MEDIUM"
            return "LOW"

    return SARIF_LEVELS.get(str(item.get("level", "note")).lower(), "LOW")


# AI-Infra-Guard가 분류하는 위험 범주. 스캐너는 규칙 ID와 메시지에 범주를 담아
# 보내지만 형태가 일정하지 않아(영문 코드, 한/중/영 제목) 그대로 집계할 수 없다.
# 범주로 접지 못하면 발견 목록은 "뭔가 13건"이 되고, 그 13건이 이 조직의 어느
# 통제에 해당하는지 아무도 대조하지 않는다.
#
# 대조표의 정본은 DB의 aig_risk_catalog이고, 여기 있는 것은 문자열에서 범주를
# 추출하는 규칙뿐이다. 둘을 한곳에 두면 매핑을 바꿀 때 워커 이미지를 다시 빌드해야 한다.
RISK_PATTERNS = (
    ("MCP01", ("mcp01", "token exposure", "secret exposure", "credential leak", "hardcoded")),
    ("MCP02", ("mcp02", "privilege escalation", "scope creep", "excessive permission")),
    ("MCP03", ("mcp03", "tool poisoning", "poisoned tool", "malicious description")),
    ("MCP04", ("mcp04", "supply chain", "dependency confusion", "typosquat")),
    ("MCP05", ("mcp05", "command injection", "rce", "arbitrary execution", "code execution")),
    ("MCP06", ("mcp06", "prompt injection", "indirect injection", "instruction hijack")),
    ("MCP07", ("mcp07", "auth", "authorization", "authentication bypass")),
    ("MCP08", ("mcp08", "audit", "telemetry", "logging")),
    ("MCP09", ("mcp09", "shadow mcp", "unregistered server")),
    ("MCP10", ("mcp10", "context injection", "over-sharing", "oversharing", "data leak")),
    ("NAME-CONFUSION", ("name confusion", "namespace confusion", "impersonat")),
    ("RUG-PULL", ("rug pull", "rugpull", "silent update")),
    ("TOOL-SHADOWING", ("tool shadowing", "shadowing attack", "override tool")),
)


def risk_category(item: dict, rules: dict) -> str:
    """발견 하나를 13개 범주 중 하나로 접는다. 모르면 'UNMAPPED'로 남긴다.

    모르는 것을 임의의 범주에 넣으면 그 범주의 통제가 실제보다 많은 것을 막는
    것처럼 보인다. 매핑되지 않은 발견이 몇 건인지가 매핑 규칙의 품질 지표다.
    """
    rule = rules.get(str(item.get("ruleId") or "")) or {}
    haystack = " ".join([
        str(item.get("ruleId") or ""),
        str(((item.get("message") or {}).get("text") or "")),
        str(rule.get("name") or ""),
        str(((rule.get("shortDescription") or {}).get("text") or "")),
        str(((rule.get("properties") or {}).get("category") or "")),
        " ".join(str(tag) for tag in ((rule.get("properties") or {}).get("tags") or [])),
    ]).lower()
    for category, needles in RISK_PATTERNS:
        if any(needle in haystack for needle in needles):
            return category
    return "UNMAPPED"


def sarif_findings(report: Path, root: Path) -> tuple[dict[str, int], list[dict], str]:
    """mcp-scan의 SARIF와 현재 CLI의 native JSON 결과를 모두 읽는다."""
    counts = {level: 0 for level in SEVERITY_ORDER}
    findings: list[dict] = []
    if not report.exists():
        return counts, findings, "no-output"
    document = json.loads(report.read_text(encoding="utf-8") or "{}")
    # Pinned A.I.G CLI는 --output에 native JSON(results/level/risk_type)을 쓰고,
    # 일부 배포판은 SARIF를 쓴다. 확장자가 .sarif.json이라고 해서 결과를 버리면
    # 실제 검사가 0건으로 보이는 위험한 거짓 음성이 된다.
    native_results = document.get("results")
    if isinstance(native_results, list):
        for item in native_results:
            severity = SARIF_SEVERITY_TEXT.get(str(item.get("level") or "").strip().lower(), "LOW")
            counts[severity] += 1
            title = str(item.get("title") or item.get("description") or "mcp-scan")[:400]
            evidence = {
                "ruleId": item.get("risk_type") or "mcp-scan",
                "message": {"text": title + " " + str(item.get("description") or "")},
            }
            findings.append({
                "severity": severity,
                "id": item.get("risk_type") or "mcp-scan",
                "title": title,
                "target": relative(str(item.get("file") or ""), root),
                "risk_category": risk_category(evidence, {}),
            })
        return counts, findings[:200], "native-json"

    runs = document.get("runs") or []
    note = "unknown"
    for run in runs:
        note = ((run.get("properties") or {}).get("scanNote")
                or (run.get("properties") or {}).get("scannote") or note)
        driver = ((run.get("tool") or {}).get("driver") or {})
        rules = {str(rule.get("id")): rule for rule in (driver.get("rules") or []) if rule.get("id")}
        for item in run.get("results") or []:
            severity = sarif_severity(item, rules)
            counts[severity] += 1
            location = ""
            for entry in item.get("locations") or []:
                uri = (((entry.get("physicalLocation") or {}).get("artifactLocation") or {}).get("uri") or "")
                if uri:
                    location = relative(uri, root)
                    break
            findings.append({
                "severity": severity,
                "id": item.get("ruleId") or "mcp-scan",
                "title": ((item.get("message") or {}).get("text") or "")[:400],
                "target": location,
                "risk_category": risk_category(item, rules),
            })
    return counts, findings[:200], note


def risk_breakdown(findings: list[dict]) -> dict:
    """범주별 건수와 최고 심각도. 화면이 "무엇이 몇 건"을 바로 말할 수 있어야 한다."""
    order = {level: index for index, level in enumerate(SEVERITY_ORDER)}
    table: dict[str, dict] = {}
    for finding in findings:
        category = finding.get("risk_category") or "UNMAPPED"
        entry = table.setdefault(category, {"count": 0, "worst": "LOW"})
        entry["count"] += 1
        if order.get(finding["severity"], 9) < order.get(entry["worst"], 9):
            entry["worst"] = finding["severity"]
    return table


def scan_target(connection, job: dict) -> dict:
    """작업이 가리키는 대상을 "저장소 URL + 고정 커밋 + 귀속 source_ref"로 푼다.

    도입 요청과 등록 서버는 감사해야 할 이유가 다르다. 도입 요청은 아직 들어오지
    않은 코드이고, 등록 서버는 이미 호출되고 있는 코드다. 후자를 감사 대상에서
    빼두면 "심사한 코드"와 "지금 도는 코드"가 갈라져도 아무도 모른다.
    """
    if job["target_kind"] == "intake":
        row = connection.execute(
            "SELECT id, display_name, repository_url, commit_sha, source_ref"
            " FROM mcp_intake_requests WHERE id=%s", (job["target_id"],)).fetchone()
        if not row:
            raise RuntimeError("도입 요청을 찾을 수 없습니다.")
        if not row["commit_sha"]:
            raise RuntimeError("격리 검증을 먼저 통과해야 합니다. 고정된 commit이 없습니다.")
        return {
            "label": row["display_name"],
            "repository_url": row["repository_url"],
            "commit": row["commit_sha"],
            "ref": None,
            # 도입 요청 결과는 그 요청에만 귀속된다. 아직 Registry의 어떤 서버도
            # 아니므로 MCP-SUPPLY-001의 치명점 집계에 들어가지 않는다.
            "source_ref": row["source_ref"] or "intake:" + str(row["id"]),
            "blocks": False,
        }

    row = connection.execute(
        "SELECT id, display_name, source_url, source_ref, status FROM mcp_servers WHERE id=%s",
        (job["target_id"],)).fetchone()
    if not row:
        raise RuntimeError("등록 서버를 찾을 수 없습니다.")
    if not str(row["source_url"] or "").startswith("https://github.com/"):
        raise RuntimeError(
            "국소 감사 대상이 아닙니다: source_url=" + repr(row["source_url"]) +
            ". 원격 전용 서버는 공급자의 증적으로 대신해야 합니다.")
    ref = row["source_ref"]
    # Never fall back to the default branch when the approved ref is absent.
    return {
        "label": row["display_name"],
        "repository_url": row["source_url"],
        "commit": job.get("commit_sha") or None,
        "ref": ref,
        "source_ref": row["source_ref"],
        # 운영 중인 서버의 치명점은 실제로 호출을 막아야 한다. 막지 않는 감사는
        # 대시보드 숫자일 뿐이다.
        "blocks": True,
    }


_CLI_HELP: str | None = None


def cli_supports(flag: str) -> bool:
    """고정한 커밋의 CLI가 이 플래그를 실제로 갖고 있는가.

    문서에 있는 플래그와 설치된 버전의 플래그는 다를 수 있다. 없는 플래그를 붙여
    실행하면 argparse가 사용법을 출력하고 exit 2로 끝나는데, 그 실패는 "스캔했는데
    발견이 없었다"와 화면에서 구분되지 않는다. 먼저 물어보고 없으면 그 사실을
    오류로 말한다.
    """
    global _CLI_HELP
    if _CLI_HELP is None:
        try:
            probe = run(["aig-mcp-scan", "--help"], timeout=60)
            _CLI_HELP = (probe.stdout or "") + (probe.stderr or "")
        except Exception:
            _CLI_HELP = ""
    return flag in _CLI_HELP


# 모델에게 이 조직의 판단 기준을 함께 준다. AI-Infra-Guard의 -p/--prompt는 검사
# 지시를 덧붙이는 자리이고, 비워 두면 도구의 일반 기준으로만 판단한다. 조직이
# "무엇을 위험으로 보는가"를 스캐너에 전달하지 않으면, 그 스캐너의 결과를 조직의
# 판단 근거로 쓰는 것이 어렵다.
SCAN_PROMPT = os.getenv("MCP_SCAN_PROMPT", "").strip()


def scan_command(job: dict, report: Path, checkout: Path | None, server_url: str | None) -> list[str]:
    command = [
        "aig-mcp-scan", "--output", str(report),
        "--model", MCP_SCAN_MODEL,
        "--base_url", MCP_SCAN_BASE_URL, "--language", MCP_SCAN_LANGUAGE,
    ]
    if checkout is not None:
        command += ["--repo", str(checkout)]
    if server_url:
        if not cli_supports("--server_url"):
            raise RuntimeError(
                "설치된 aig-mcp-scan에 --server_url이 없습니다. 동적 점검을 쓸 수 없습니다.")
        command += ["--server_url", server_url]
        for header in [h for h in os.getenv("MCP_SCAN_HEADERS", "").split("\n") if h.strip()]:
            if cli_supports("--header"):
                command += ["--header", header.strip()]
    if SCAN_PROMPT and cli_supports("--prompt"):
        command += ["--prompt", SCAN_PROMPT]
    return command


def listener_target(connection, job: dict) -> dict:
    """엔드포인트 평면이 망에서 찾아낸 미등록 MCP 리스너.

    Registry에 없는 서버라 복제할 코드도 승인된 source_ref도 없다. 있는 것은
    주소뿐이고, 그래서 동적 점검만 가능하다. 결과는 그 관측에 귀속되며 호출을
    막지 않는다 - 게이트웨이를 통과하지 않는 서버의 호출은 게이트웨이가 막을 수
    있는 대상이 아니다. 막는 것은 네트워크 평면의 몫이고 여기서는 증적을 만든다.
    """
    row = connection.execute(
        "SELECT id, address, port, server_name, classification, mcp_evidence, fingerprint"
        " FROM endpoint_listeners WHERE id=%s", (int(job["target_id"]),)).fetchone()
    if not row:
        raise RuntimeError("관측된 리스너를 찾을 수 없습니다.")
    if row["mcp_evidence"] != "confirmed" or not row["port"]:
        raise RuntimeError("MCP로 확인되고 포트가 있는 리스너만 점검할 수 있습니다.")
    address = row["address"]
    host = "[" + address + "]" if ":" in address else address
    endpoint = "http://%s:%s/mcp/" % (host, row["port"])
    return {
        "label": row["server_name"] or ("미등록 MCP " + endpoint),
        "repository_url": endpoint,
        "commit": None,
        "ref": None,
        "source_ref": "listener:" + row["fingerprint"][:32],
        "blocks": False,
        "endpoint": endpoint,
    }


def dynamic_target(connection, job: dict) -> dict:
    """동적 점검의 대상. 실행 중인 MCP 서버의 endpoint다.

    정적 감사가 "이 코드가 무엇을 할 수 있는가"를 묻는다면 동적 점검은 "지금 이
    주소에 있는 것이 무엇인가"를 묻는다. 도입 심사 단계에서는 후자를 하지 않는다.
    아직 들이지 않기로 한 코드를 실행해 붙어보는 것은 격리 원칙과 반대다. 이미
    운영 중이거나 종료를 확인하는 서버에만 쓴다.
    """
    row = connection.execute(
        "SELECT id, display_name, endpoint, source_ref, transport, lifecycle"
        " FROM mcp_servers WHERE id=%s", (job["target_id"],)).fetchone()
    if not row:
        raise RuntimeError("등록 서버를 찾을 수 없습니다.")
    endpoint = job.get("server_url") or row["endpoint"]
    if not endpoint or not str(endpoint).startswith(("http://", "https://")):
        raise RuntimeError(
            "동적 점검은 HTTP endpoint가 있는 서버에만 적용됩니다: " + repr(endpoint))
    return {
        "label": row["display_name"],
        "repository_url": endpoint,
        "commit": None,
        "ref": None,
        "source_ref": row["source_ref"],
        # 동적 점검 결과는 그 서버에 귀속되고 치명점은 실제 차단으로 이어진다.
        # 지금 그 주소에 있는 것이 위험하다면 그것이 바로 호출되는 대상이다.
        "blocks": True,
        "endpoint": endpoint,
    }


def run_mcp_scan(connection, job: dict) -> None:
    """정적 감사는 고정 커밋을 다시 복제해서, 동적 점검은 실행 중인 endpoint에 붙어서.

    검증 때 쓴 체크아웃을 남겨두지 않는 이유는 외부 저장소 사본을 계속 들고 있을
    이유가 없어서다. 커밋이 고정돼 있으므로 다시 복제해도 같은 코드다.
    """
    dynamic = (job.get("mode") or "static") == "dynamic"
    job_id = str(job["id"])
    report = REPORT_DIR / ("mcp-scan-" + job_id + ".sarif.json")

    if dynamic:
        target = (listener_target(connection, job) if job["target_kind"] == "endpoint"
                  else dynamic_target(connection, job))
        # Release the registry read lock before a potentially long model call.
        connection.commit()
        checkout = None
        commit = None
        log("mcp-scan(dynamic) " + job_id + " 시작: " + target["endpoint"])
        command = scan_command(job, report, None, target["endpoint"])
    else:
        target = scan_target(connection, job)
        # A remote clone/scan can take minutes; schema startup must not wait on it.
        connection.commit()
        checkout = WORK_DIR / ("scan-" + job_id)
        shutil.rmtree(checkout, ignore_errors=True)
        pinned = target.get("commit") or target.get("ref")
        log("mcp-scan " + job_id + " 시작: " + target["repository_url"] + " @ " + str(pinned)[:12])
        commit = clone(target["repository_url"], checkout, commit=pinned)
        command = scan_command(job, report, checkout, None)

    # The pinned CLI reads LLM_API_KEY. Keep the live key out of process arguments.
    try:
        result = run(command, timeout=MCP_SCAN_TIMEOUT,
                     extra_env={"LLM_API_KEY": MCP_SCAN_API_KEY})
    except subprocess.TimeoutExpired as exc:
        raise ScanTimeout(
            f"A.I.G 검사 제한 시간 {MCP_SCAN_TIMEOUT}초를 초과했습니다. "
            "모델 응답 속도나 검사 설정을 확인하세요.") from exc
    if result.returncode != 0 or not report.exists():
        output = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError("aig-mcp-scan(exit %s): " % result.returncode + " | ".join(output[-3:])[:400])

    counts, findings, note = sarif_findings(report, checkout or WORK_DIR)
    if MCP_SCAN_EVIDENCE_MODE not in MCP_SCAN_EVIDENCE_MODES:
        raise RuntimeError("MCP_SCAN_EVIDENCE_MODE must be live, advisory or test-double")
    # 배선 stub으로 돌린 결과가 "발견 0건"으로 보이면 그게 곧 깨끗하다는 뜻이
    # 된다. 어떤 종류의 endpoint였는지를 결과에 박아 둔다.
    endpoint_kind = "wire-stub" if urlsplit(MCP_SCAN_BASE_URL).hostname == "llm-stub" else (
        "local-model" if urlsplit(MCP_SCAN_BASE_URL).hostname == "ollama" else MCP_SCAN_EVIDENCE_MODE)
    # test double 결과는 어떤 경우에도 차단 집계에 들어가지 않는다. 배선 확인이
    # 통제처럼 보이기 시작하면 그 순간부터 통제가 아니라 착시다.
    blocks = bool(target["blocks"]) and MCP_SCAN_EVIDENCE_MODE == "live" and endpoint_kind != "wire-stub"
    breakdown = risk_breakdown(findings)
    summary = {
        "endpoint_kind": endpoint_kind,
        "evidence_mode": MCP_SCAN_EVIDENCE_MODE,
        "target_kind": job["target_kind"],
        "mode": "dynamic" if dynamic else "static",
        "blocks_calls": blocks,
        "findings": findings,
        "total": sum(counts.values()),
        "levels": counts,
        # 범주별 집계. 13개 범주 중 무엇이 나왔고 무엇이 나오지 않았는지가
        # "발견 0건"보다 훨씬 많은 것을 말한다.
        "risk_breakdown": breakdown,
        "unmapped": breakdown.get("UNMAPPED", {}).get("count", 0),
        "scan_note": note,
        "repository": target["repository_url"],
        "commit": commit,
        "trigger": job.get("trigger") or "manual",
    }
    source_ref = target["source_ref"]
    stored = dict(counts)
    if not blocks:
        # 귀속은 그대로 두되 치명점 집계에는 넣지 않는다. 화면에서는 같은
        # source_ref로 모이고, _contract()의 차단 계산에는 기여하지 않는다.
        stored["CRITICAL"] = 0
    # A later advisory/test-double run must not erase a previous blocking live
    # report. A new live run replaces only the previous live result.
    connection.execute(
        """DELETE FROM supply_chain_reports
           WHERE scanner='AI-Infra-Guard mcp-scan' AND source_ref=%s
             AND COALESCE(summary->>'evidence_mode', 'live')=%s""",
        (source_ref, MCP_SCAN_EVIDENCE_MODE),
    )
    store_report(connection, "AI-Infra-Guard mcp-scan", MCP_SCAN_MODEL, source_ref, report, stored, summary)
    connection.execute(
        """UPDATE scan_jobs SET status='DONE', report_path=%s, summary=%s, commit_sha=%s,
                  repository_url=%s, source_ref=%s, risk_breakdown=%s, lease_expires_at=NULL,
                  error=NULL, finished_at=now()
           WHERE id=%s""",
        (str(report), Jsonb(summary), commit, target["repository_url"], source_ref,
         Jsonb(breakdown), job["id"]),
    )
    if checkout is not None:
        shutil.rmtree(checkout, ignore_errors=True)
    log("mcp-scan %s(%s) 완료 · 발견 %d건 · 치명 %d건 · 차단연결 %s · 범주 %s · note %s"
        % (job_id, summary["mode"], summary["total"], counts["CRITICAL"], blocks,
           ",".join(sorted(breakdown)) or "-", note))


def scan_configured() -> bool:
    return bool(MCP_SCAN_API_KEY and MCP_SCAN_BASE_URL and MCP_SCAN_MODEL
                and MCP_SCAN_EVIDENCE_MODE in MCP_SCAN_EVIDENCE_MODES)


def heartbeat(connection) -> None:
    """"설정이 있다"와 "실행할 사람이 있다"는 다른 질문이다.

    이 신호가 없으면 Console은 워커가 죽은 것과 작업이 오래 걸리는 것을 구분하지
    못하고, 큐에 쌓이기만 하는 상태를 "진행 중"으로 보여준다.
    """
    connection.execute(
        """INSERT INTO worker_heartbeats(worker, role, seen_at, detail)
           VALUES (%s, 'intake', now(), %s)
           ON CONFLICT (worker) DO UPDATE SET seen_at=now(), detail=EXCLUDED.detail""",
        (WORKER_ID, Jsonb({
            "mcp_scan_configured": scan_configured(),
            "model": MCP_SCAN_MODEL,
            "base_url": MCP_SCAN_BASE_URL,
            "evidence_mode": MCP_SCAN_EVIDENCE_MODE,
            "poll_seconds": POLL_SECONDS,
            "lease_seconds": SCAN_LEASE_SECONDS,
            "auto_on_validated": AUTO_ON_VALIDATED,
            "auto_jobs": AUTO_JOBS,
            "rescan_days": RESCAN_DAYS,
        })),
    )


def reclaim_expired(connection) -> None:
    """lease가 만료된 RUNNING 작업을 회수한다.

    이전 판에는 이 경로가 없었다. 워커가 스캔 도중에 죽으면 그 행은 영원히
    RUNNING으로 남고, 재실행 API는 QUEUED·RUNNING을 409로 막으므로 그 대상은
    다시는 감사할 수 없었다. 통제가 한 번 실패하면 영구히 꺼지는 구조였다.
    """
    rows = connection.execute(
        """UPDATE scan_jobs
           SET status = CASE WHEN attempts >= %s THEN 'FAILED' ELSE 'QUEUED' END,
               error = CASE WHEN attempts >= %s
                            THEN '워커가 응답하지 않아 재시도 한도에서 중단했습니다.'
                            ELSE '워커 lease 만료로 회수했습니다. 다시 대기열에 넣습니다.' END,
               finished_at = CASE WHEN attempts >= %s THEN now() ELSE NULL END,
               lease_expires_at = NULL
           WHERE status='RUNNING' AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
           RETURNING id, attempts, status""",
        (SCAN_MAX_ATTEMPTS, SCAN_MAX_ATTEMPTS, SCAN_MAX_ATTEMPTS),
    ).fetchall()
    for row in rows:
        log("lease 만료 회수: %s (시도 %s회) -> %s" % (row["id"], row["attempts"], row["status"]))


def drop_cancelled(connection) -> None:
    """취소 요청된 대기 작업은 워커가 집기 전에 정리한다.

    취소가 없으면 잘못 건 감사를 되돌릴 방법이 재시작밖에 없다.
    """
    rows = connection.execute(
        """UPDATE scan_jobs SET status='CANCELLED', finished_at=now(), lease_expires_at=NULL
           WHERE cancel_requested AND status='QUEUED' RETURNING id""").fetchall()
    for row in rows:
        log("취소 요청 반영: " + str(row["id"]))


def enqueue(connection, target_kind, target_id, label, trigger, requested_by, mode="static"):
    """같은 대상·방식에 살아 있는 작업이 없을 때만 큐에 넣는다.

    유일 인덱스가 정본이고 이 조회는 흔한 경우의 잡음을 줄일 뿐이다. 정적 감사와
    동적 점검은 서로 다른 질문이라 한쪽이 대기 중이어도 다른 쪽은 걸려야 한다.
    """
    live = connection.execute(
        "SELECT id FROM scan_jobs WHERE target_kind=%s AND target_id=%s AND mode=%s"
        " AND status IN ('QUEUED','RUNNING')",
        (target_kind, target_id, mode)).fetchone()
    if live:
        return False
    connection.execute(
        """INSERT INTO scan_jobs(id, kind, target_kind, target_id, target_label,
                                 requested_by, trigger, mode)
           VALUES (%s,'mcp-scan',%s,%s,%s,%s,%s,%s)
           ON CONFLICT DO NOTHING""",
        (uuid.uuid4(), target_kind, target_id, str(label)[:200], requested_by, trigger, mode))
    return True


def auto_enqueue_validated(connection) -> None:
    """T1 · 격리 검증을 통과한 요청은 승인 판단 전에 감사가 걸린다.

    이전 판은 승인한 뒤에야 관리자가 따로 눌러야 했다. 순서가 뒤집혀 있으면
    감사는 승인의 근거가 아니라 승인 뒤의 기록이 된다.
    """
    if not (AUTO_ON_VALIDATED and scan_configured()):
        return
    rows = connection.execute(
        """SELECT r.id::text AS id, r.display_name
           FROM mcp_intake_requests r
           WHERE r.status='VALIDATED' AND r.commit_sha IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM scan_jobs j
                             WHERE j.target_kind='intake' AND j.target_id = r.id::text
                               AND j.status IN ('QUEUED','RUNNING','DONE')
                               AND (j.status <> 'DONE' OR j.commit_sha = r.commit_sha))
           ORDER BY r.validated_at LIMIT 5""").fetchall()
    for row in rows:
        if enqueue(connection, "intake", row["id"], row["display_name"],
                   "validated", "system:validated"):
            log("검증 통과 자동 감사 큐잉: " + row["id"])


def sweep_rescans(connection) -> None:
    """T3 · 등록 서버의 재감사 주기.

    심사 시점의 코드와 지금 돌고 있는 코드는 시간이 지나면 갈라진다. 승인에는
    기한(approval_valid_until)이 있는데 그 승인의 근거인 감사에는 기한이 없다면,
    기한이 지난 것은 승인이 아니라 근거다.
    """
    if not (RESCAN_DAYS > 0 and scan_configured()):
        return
    rows = connection.execute(
        """SELECT s.id, s.display_name
           FROM mcp_servers s
           WHERE s.status <> 'DISABLED' AND s.source_url LIKE 'https://github.com/%%'
             AND NOT EXISTS (
                   SELECT 1 FROM scan_jobs j
                   WHERE j.target_kind='server' AND j.target_id = s.id
                     AND (j.status IN ('QUEUED','RUNNING')
                          OR (j.status='DONE'
                              AND j.finished_at > now() - make_interval(days => %s))))
           ORDER BY s.id LIMIT 5""", (RESCAN_DAYS,)).fetchall()
    for row in rows:
        if enqueue(connection, "server", row["id"], row["display_name"],
                   "rescan", "system:rescan"):
            log("재감사 주기 도래 큐잉: " + row["id"])


def sweep_drift(connection) -> None:
    """T4 · catalog 드리프트가 관측된 서버의 재감사.

    v1.5는 scan_jobs.trigger에 'drift' 값만 예약해 두고 구현하지 않았다. 예약된
    값은 통제가 아니다. 계약이 바뀌었다는 것은 승인 당시 심사한 코드와 지금 도는
    코드가 갈라졌다는 뜻이고, 그 순간이야말로 코드 감사를 다시 해야 하는 시점이다.

    드리프트 시각이 마지막 감사보다 뒤일 때만 건다. 그러지 않으면 드리프트 상태가
    해소되기 전까지 매 회전마다 같은 작업이 큐에 들어간다.
    """
    if not scan_configured():
        return
    rows = connection.execute(
        """SELECT s.id, s.display_name
           FROM mcp_servers s
           WHERE s.drift_observed_at IS NOT NULL
             AND s.lifecycle='OPERATING'
             AND s.source_url LIKE 'https://github.com/%%'
             AND NOT EXISTS (
                   SELECT 1 FROM scan_jobs j
                   WHERE j.target_kind='server' AND j.target_id = s.id AND j.mode='static'
                     AND (j.status IN ('QUEUED','RUNNING')
                          OR (j.status='DONE' AND j.finished_at > s.drift_observed_at)))
           ORDER BY s.drift_observed_at LIMIT 5""").fetchall()
    for row in rows:
        if enqueue(connection, "server", row["id"], row["display_name"],
                   "drift", "system:drift"):
            log("catalog 드리프트 감지 재감사 큐잉: " + row["id"])


def sweep_termination(connection) -> None:
    """종료 케이스가 열린 원격 서버에 동적 점검을 건다.

    폐기를 선언한 뒤에 물어야 하는 것은 "그 주소에 아직 무엇이 있는가"다. 조직이
    자기 쪽 경로를 끊었다는 사실과 제공자 쪽이 회수했다는 사실은 다르고, 후자는
    조직이 확인할 방법이 별로 없다. 동적 점검은 그 몇 안 되는 수단 중 하나다.

    결과는 종료 케이스의 증거가 되지만 판정을 자동으로 바꾸지는 않는다. 무엇을
    증거로 인정할지는 사람이 정한다.
    """
    if not scan_configured():
        return
    rows = connection.execute(
        """SELECT s.id, s.display_name
           FROM mcp_servers s
           JOIN termination_cases c ON c.server_id = s.id
           WHERE c.status IN ('OPEN','REVOKING','REOPENED')
             AND s.endpoint LIKE 'http%%'
             AND NOT EXISTS (
                   SELECT 1 FROM scan_jobs j
                   WHERE j.target_kind='server' AND j.target_id = s.id AND j.mode='dynamic'
                     AND (j.status IN ('QUEUED','RUNNING')
                          OR (j.status='DONE' AND j.finished_at > c.cutover_at)))
           ORDER BY c.opened_at LIMIT 3""").fetchall()
    for row in rows:
        if enqueue(connection, "server", row["id"], row["display_name"],
                   "termination", "system:termination", mode="dynamic"):
            log("종료 확인 동적 점검 큐잉: " + row["id"])


def claim_scan_job(connection) -> dict | None:
    """대기 중인 감사 작업을 lease와 함께 가져온다.

    이전 판은 status='QUEUED'만 집고 lease를 두지 않았다. 그래서 작업을 집은
    워커가 죽으면 그 행은 아무도 회수하지 않는 RUNNING으로 남았다. 여기서
    lease_expires_at을 같이 박아두면 reclaim_expired()가 되돌릴 수 있다.
    """
    cursor = connection.execute(
        """UPDATE scan_jobs
           SET status='RUNNING', started_at=COALESCE(started_at, now()),
               attempts = attempts + 1,
               lease_expires_at = now() + make_interval(secs => %s),
               model=%s, base_url=%s
           WHERE id = (SELECT id FROM scan_jobs
                       WHERE status='QUEUED' AND NOT cancel_requested
                       ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
           RETURNING id, kind, target_kind, target_id, trigger, commit_sha, attempts,
                     mode, server_url""",
        (SCAN_LEASE_SECONDS, MCP_SCAN_MODEL, MCP_SCAN_BASE_URL),
    )
    return cursor.fetchone()


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
    log("대기 중 · worker=%s · mcp-scan 설정 %s" % (WORKER_ID, "있음" if scan_configured() else "없음"))
    last_sweep = 0.0
    while True:
        try:
            with psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False) as connection:
                while True:
                    # 매 회전마다 살아 있음을 남기고, 죽은 워커가 들고 있던 작업을
                    # 먼저 회수한다. 이 두 줄이 없으면 실패한 감사가 조용히 영구
                    # 대기 상태로 남는다.
                    heartbeat(connection)
                    reclaim_expired(connection)
                    drop_cancelled(connection)
                    if AUTO_JOBS:
                        auto_enqueue_validated(connection)
                        now = time.monotonic()
                        if now - last_sweep >= RESCAN_SWEEP_SECONDS:
                            sweep_rescans(connection)
                            last_sweep = now
                        # 드리프트와 종료 확인은 주기가 아니라 사건에 반응한다.
                        sweep_drift(connection)
                        sweep_termination(connection)
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
                                       review_note=%s, updated_at=now() WHERE id=%s""",
                                ("격리 검증 실패: " + str(exc)[:400], request["id"]),
                            )
                            connection.commit()
                            shutil.rmtree(WORK_DIR / str(request["id"]), ignore_errors=True)

                    while True:
                        job = claim_scan_job(connection)
                        if not job:
                            connection.commit()
                            break
                        connection.commit()
                        try:
                            run_mcp_scan(connection, job)
                            connection.commit()
                        except Exception as exc:
                            connection.rollback()
                            log("mcp-scan %s 실패: %s" % (job["id"], exc))
                            # 재시도 여지가 남아 있으면 대기열로 되돌린다. 한도를
                            # 넘겼을 때만 FAILED로 끝낸다. 한 번의 endpoint 장애가
                            # 그 대상을 영구히 감사 불가로 만들면 안 된다.
                            retryable = (not isinstance(exc, ScanTimeout)
                                         and int(job.get("attempts") or 0) < SCAN_MAX_ATTEMPTS)
                            connection.execute(
                                """UPDATE scan_jobs
                                   SET status = CASE WHEN %s THEN 'QUEUED' ELSE 'FAILED' END,
                                       error=%s, lease_expires_at=NULL,
                                       finished_at = CASE WHEN %s THEN NULL ELSE now() END
                                   WHERE id=%s""",
                                (retryable, str(exc)[:600], retryable, job["id"]),
                            )
                            connection.commit()
                            shutil.rmtree(WORK_DIR / ("scan-" + str(job["id"])), ignore_errors=True)
                            if retryable:
                                # 같은 작업을 즉시 다시 집어 실패를 반복하지 않는다.
                                break

                    time.sleep(POLL_SECONDS)
        except psycopg.Error as exc:
            log("데이터베이스 재연결 대기: %s" % exc)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
