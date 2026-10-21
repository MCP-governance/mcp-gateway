"""Local regression runner for full_stack_lab/tests (standard library only).

Runs every non-Postgres *_check.py / *_test.py with the PYTHONPATH the gateway needs and
judges each file by exit code. unittest-based files run as `python -m unittest <module>` and
must report at least one test, so a file that defines tests but never runs them cannot pass.
Files in EXTERNAL need a service or platform this PC does not have; they are skipped, not run.

Usage (from the repository root, with the venv interpreter):
    python full_stack_lab/tests/run_local_suite.py [--out result.json]

Output: JSON list, one entry per file: {file, status, rc, seconds, ran, last_line, note}.
status is one of 통과, 실패, 외부 의존 생략. Exit code 1 if any file is 실패.
Triage details: research/llm-wiki/status/reports/2026-10-21-test-triage.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[1]
PYTHONPATH_DIRS = ["full_stack_lab", "full_stack_lab/gateway", "full_stack_lab/supply_chain",
                   "full_stack_lab/runtime", "full_stack_lab/gateway/app"]
TIMEOUT_S = 600
WORKERS = 4

# (C) 외부 의존: 이 PC(Windows)에서는 돌릴 수 없어 실행하지 않는다.
EXTERNAL = {
    "adversarial_check": "게이트웨이 HTTP(127.0.0.1:8080)와 DATABASE_URL 필요",
    "credential_binding_check": "POSIX 파일 권한 0o600 검사, Windows에서는 항상 실패",
    "field_release_check": "--url --server --expected-revision 인자의 운영 대상 점검",
    "intake_validation_test": "Windows 심볼릭 링크 권한 없음(WinError 1314)",
    "intake_worker_scanners_check": "Trivy 캐시 환경변수 TRIVY_CACHE_DIR 필요",
    "managed_enforcement_check": "Linux 전용 모듈 grp 필요",
    "managed_enrollment_check": "컨테이너 호스트 agent-service:8000 필요",
    "mcp_result_contract_check": "PostgreSQL 필요",
    "mcp_result_services_check": "libmcpgw_gitleaks.so(Linux)와 PII 분석기 호스트 필요",
    "oss_audit_test": "libmcpgw_gitleaks.so(Linux) 필요",
    "pac_boundary_check": "게이트웨이 이미지의 /registry/field 경로 필요",
    "policy_replay_lab_check": "PostgreSQL 필요",
    "provenance_gitea_check": "Gitea 서버와 GITEA_USER·GITEA_PASSWORD 필요",
    "real_warning_review_check": "--url --reviewed 인자의 운영 대상 점검",
    "reservation_effect_check": "docker compose 컨테이너(corp-db, gateway) 필요",
    "secret_engine_parity_check": "docker exec 게이트웨이 컨테이너 필요",
    "testbed_network_check": "--out 인자와 테스트베드 이미지 필요",
    "textscan_parity_check": "네이티브 엔진 libmcpgw_gitleaks.so(Linux) 필요",
}

# 실패 중 분류 보고서에서 (D)·(E)로 표시한 항목. 상태는 그대로 실패이며 note로만 구분한다.
KNOWN = {
    "field_account_git_test": "(D) 수리 후 실행 시작: 미대역 DB 호출(revoke_principal_tokens)에서 PoolTimeout, 그 뒤 단언은 미확인",
    "threat_trace_mapping_check": "(E) 독립 검토 고정 해시 낡음, 설계상 실패",
}

UNITTEST_RAN = re.compile(r"^Ran (\d+) tests?", re.M)


def discover() -> list[Path]:
    files = []
    for path in sorted(TESTS.iterdir()):
        name = path.name
        if not (name.endswith("_check.py") or name.endswith("_test.py")):
            continue
        if "_pg_check" in name or "real_mcp" in name or "e2e" in name:
            continue
        files.append(path)
    return files


def child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.pathsep.join(str(REPO / d) for d in PYTHONPATH_DIRS)
    return env


def run_one(path: Path) -> dict:
    stem = path.stem
    entry = {"file": path.name, "status": None, "rc": None, "seconds": 0.0, "ran": None,
             "last_line": "", "note": KNOWN.get(stem, "")}
    if stem in EXTERNAL:
        entry.update(status="외부 의존 생략", note=EXTERNAL[stem])
        return entry
    source = path.read_text(encoding="utf-8", errors="replace")
    unittest_mode = "unittest.TestCase" in source
    cmd = [sys.executable, "-m", "unittest", stem] if unittest_mode else [sys.executable, str(path)]
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=TESTS, env=child_env(), capture_output=True, timeout=TIMEOUT_S)
        rc, raw = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        rc, raw = "TIMEOUT", (exc.stdout or b"") + (exc.stderr or b"")
    text = raw.decode("utf-8", "replace")
    lines = [line for line in text.splitlines() if line.strip()]
    ran = None
    if unittest_mode:
        match = UNITTEST_RAN.search(text)
        ran = int(match.group(1)) if match else 0
    ok = rc == 0 and (ran is None or ran > 0)
    entry.update(status="통과" if ok else "실패", rc=rc, seconds=round(time.time() - started, 1),
                 ran=ran, last_line=lines[-1][:200] if lines else "")
    if unittest_mode and rc == 0 and not ran:
        entry["note"] = (entry["note"] + "; " if entry["note"] else "") + "시험 0개 실행"
    return entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="JSON 결과 파일 경로(없으면 표준 출력)")
    args = parser.parse_args()
    files = discover()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(run_one, files))
    data = json.dumps(results, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        Path(args.out).write_text(data, encoding="utf-8")
    else:
        sys.stdout.buffer.write(data.encode("utf-8"))
    counts = {}
    for entry in results:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    print(f"total {len(results)} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())), file=sys.stderr)
    return 1 if counts.get("실패") else 0


if __name__ == "__main__":
    sys.exit(main())
