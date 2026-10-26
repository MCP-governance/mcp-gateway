"""Local regression runner for full_stack_lab/tests (standard library only).

Runs every non-Postgres *_check.py / *_test.py with the PYTHONPATH the gateway needs and
judges each file by exit code. unittest-based files run as `python -m unittest <module>` and
must report at least one test, so a file that defines tests but never runs them cannot pass.
EXTERNAL records services and platform-specific skips. --pg runs all *_pg_check.py in
separate disposable databases. --inventory fails when a test has no CI/runner/skip owner.

Usage (from the repository root, with the venv interpreter):
    python full_stack_lab/tests/run_local_suite.py [--out result.json]

Output: JSON object with results (one entry per file) and counts (each status separately).
status is one of 통과, 실패, 외부 의존 생략, 검토 갱신 대기. Exit code 1 if any file is 실패.
Triage details: research/llm-wiki/status/reports/2026-10-21-test-triage.md
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[1]
PYTHONPATH_DIRS = ["full_stack_lab", "full_stack_lab/gateway", "full_stack_lab/supply_chain",
                   "full_stack_lab/runtime", "full_stack_lab/gateway/app"]
TIMEOUT_S = 600
WORKERS = 4

# 플랫폼 제약만 있는 시험을 Linux CI에서도 생략하지 않도록 범위를 명시한다.
EXTERNAL = {
    "adversarial_check": (("all",), "실행 중인 게이트웨이 HTTP·사내 시험망·DB 필요"),
    "credential_binding_check": (("win32",), "Windows에서 POSIX 파일 권한 0o600을 검증할 수 없음"),
    "field_release_check": (("all",), "--url --server --expected-revision과 운영 대상·자격 필요"),
    "intake_validation_test": (("win32",), "Windows 심볼릭 링크 생성 권한 필요"),
    "intake_worker_scanners_check": (("all",), "intake-worker 이미지의 Syft·Trivy·Semgrep·Gitleaks와 Trivy DB 캐시 필요"),
    "managed_enforcement_check": (("win32",), "Linux 전용 grp 모듈 필요"),
    "managed_enrollment_check": (("all",), "실행 중인 게이트웨이·agent-service·공유 DB 필요"),
    "mcp_result_services_check": (("all",), "이미지 빌드 산출물 libmcpgw_gitleaks.so와 실제 Presidio 서비스 필요"),
    "oss_audit_test": (("all",), "게이트웨이 이미지 빌드 산출물 libmcpgw_gitleaks.so 필요"),
    "output_credential_span_check": (("all",), "실제 Presidio analyzer·anonymizer 필요; verify job의 게이트웨이 이미지에서 실행"),
    "pac_boundary_check": (("all",), "게이트웨이 이미지의 /registry/field 마운트 필요"),
    "policy_replay_lab_check": (("all",), "부트스트랩된 게이트웨이 DB와 실제 OPA 필요"),
    "provenance_gitea_check": (("all",), "격리 Gitea와 GITEA_USER·GITEA_PASSWORD 필요"),
    "real_warning_review_check": (("all",), "운영 대상·검토한 계약 파일·신청자와 승인자 자격 필요"),
    "reservation_effect_check": (("all",), "실행 중인 docker compose corp-db·gateway 필요"),
    "secret_engine_parity_check": (("all",), "게이트웨이 이미지 빌드 산출물 libmcpgw_gitleaks.so와 Gitleaks 실행 파일 필요"),
    "testbed_network_check": (("all",), "하네스가 설치된 테스트베드 이미지와 --out 인자 필요"),
    "textscan_parity_check": (("all",), "게이트웨이 이미지에서 빌드하는 PCRE2 확장 mcpgw_textscan 필요"),
}

# 자동 실행하면 운영 상태를 바꾸거나 별도 승인·코퍼스가 필요한 진입점이다.
INVENTORY_EXTERNAL = {
    "dispatch_effect_lab.py": "격리 PostgreSQL·OPA·Presidio·실제 Gitea MCP와 공급자 자격 필요",
    "inspection_corpus_eval.py": "build/run 모드와 해시 검증된 공개 코퍼스·분할 인자 필요",
    "korean_pii_eval.py": "실제 Presidio 서비스와 이미지의 네이티브 Gitleaks 라이브러리 필요",
    "managed_kernel_proof.py": "관리 등록된 Linux 기기·root·콘솔 자격·서비스 중지 승인 필요",
    "plane_evidence.py": "실제 하네스·관리자 자격·검토한 업무 케이스 파일 필요",
    "plane_sequence.py": "실제 하네스·운영 대상·계약 변경과 원복 명령·관리자 자격 필요",
    "real_mcp_check.py": "공식 공급자 MCP 계정 자격과 명시적 live probe 인자 필요",
    "real_mcp_gateway_check.py": "실행 중인 게이트웨이·검토한 계약·별도 신청자와 승인자 자격 필요",
    "termination_dispatch_lab.sh": "격리 랩을 만드는 원격 기기 접속과 명시적 up/run/down 인자 필요",
    "termination_dispatch_remote.sh": "솔루션 기기의 격리 랩·기존 이미지·명시적 기동 인자 필요",
    "termination_lab.py": "격리 PostgreSQL·OPA·Presidio·실제 Gitea MCP·공급자 자격 필요",
}

# 독립 시험이 아닌 재사용 모듈·자식 프로세스·운영 도우미를 고아 시험으로 세지 않는다.
SUPPORT = {
    "dispatch_crash_child.py": "dispatch_effect_lab.py가 중단시키는 자식 프로세스",
    "i18n-extract.mjs": "i18n.test.mjs가 가져오는 텍스트 추출 모듈",
    "intake_fixture.py": "도입 승인 합성 데이터",
    "intake_register.py": "검토한 입력으로 실제 도입 신청을 수행하는 운영 도우미",
    "run_local_suite.py": "시험 실행기",
    "siem_tls_receiver.py": "TLS 시험이 사용하는 HTTPS 수신 fixture",
    "termination_dispatch_provision.py": "격리 랩 계정·저장소 준비 도우미",
    "tool_scope_review.py": "관리자의 도구 범위 검토를 기록하는 운영 도우미",
}

# 실패를 생략하지 않고 검토 기록의 갱신과 실행 도구 장애를 구분한다(D-252).
REVIEW_PENDING = {
    "threat_trace_mapping_check.py": "독립 검토 기록(threat-trace-review-1020/review.json)의 고정 해시가 현재 코드와 다름. "
                                     "0단계 병합 뒤 독립 재검토로 갱신(D-252)",
}
KNOWN = {}

UNITTEST_RAN = re.compile(r"^Ran (\d+) tests?", re.M)
UNITTEST_FAILURES = re.compile(r"^FAILED \(failures=[1-9]\d*(?:, skipped=\d+)?\)\r*$", re.M)


def discover(pg: bool = False) -> list[Path]:
    if pg:
        return sorted(TESTS.glob("*_pg_check.py"))
    files = []
    for path in sorted(TESTS.iterdir()):
        name = path.name
        if not (name.endswith("_check.py") or name.endswith("_test.py")):
            continue
        if "_pg_check" in name or "real_mcp" in name or "e2e" in name:
            continue
        files.append(path)
    return files


def skip_reason(path: Path, platform: str = sys.platform) -> str:
    platforms, reason = EXTERNAL.get(path.stem, ((), ""))
    return reason if "all" in platforms or platform in platforms else ""


def inventory() -> dict:
    callers = "\n".join(path.read_text(encoding="utf-8") for path in
                        (REPO / ".github/workflows/verify.yml", TESTS.parent / "console.sh"))
    # lint의 tests/*.py는 실행 증거가 아니며 Node 시험 명령의 glob만 확장한다.
    patterns = [pattern for line in callers.splitlines() if "node --test" in line
                for pattern in re.findall(r"tests/([\w*./-]+)", line)]
    local, pg = set(discover()), set(discover(pg=True))
    entries, excluded = [], []
    for path in sorted(TESTS.rglob("*")):
        if path.suffix not in {".py", ".mjs", ".sh"} or not path.is_file():
            continue
        relative = path.relative_to(TESTS).as_posix()
        if (set(path.relative_to(TESTS).parts) & {"fixtures", "__pycache__"}
                or path.name == "__init__.py" or path.name.endswith("_support.py") or relative in SUPPORT):
            excluded.append({"file": relative, "note": SUPPORT.get(relative, "지원 파일(_support.py·__init__.py·fixtures·캐시)")})
            continue
        note = ""
        if (re.search(r"(?<![\w.-])" + re.escape(relative) + r"(?![\w.-])", callers)
                or any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns)):
            category = "ci"
        elif path in pg:
            category = "pg-suite"
        elif path in local and not skip_reason(path, "linux"):
            category = "local-suite"
        else:
            note = skip_reason(path, "linux") or INVENTORY_EXTERNAL.get(relative, "")
            category = "external" if note else "orphan"
        entries.append({"file": relative, "category": category, "note": note})
    counts = {category: sum(e["category"] == category for e in entries)
              for category in ("ci", "local-suite", "pg-suite", "external", "orphan")}
    return {"scanned": len(entries) + len(excluded), "total": len(entries),
            "counts": counts, "files": entries, "excluded": excluded}


def child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.pathsep.join(str(REPO / d) for d in PYTHONPATH_DIRS)
    return env


def run_one(path: Path, env: dict | None = None) -> dict:
    stem = path.stem
    entry = {"file": path.name, "status": None, "rc": None, "seconds": 0.0, "ran": None,
             "last_line": "", "note": KNOWN.get(stem, "")}
    reason = skip_reason(path)
    if reason:
        entry.update(status="외부 의존 생략", note=reason)
        return entry
    env = child_env() if env is None else dict(env)
    if stem == "mcp_result_contract_check":
        # 메모리 span의 누출 검사는 실제 SDK가 기록해야 하므로 이 자식만 중지를 해제한다.
        env["OTEL_SDK_DISABLED"] = "false"
    source = path.read_text(encoding="utf-8", errors="replace")
    unittest_mode = "unittest.TestCase" in source
    cmd = [sys.executable, "-m", "unittest", stem] if unittest_mode else [sys.executable, str(path)]
    if path.name.endswith("_pg_check.py"):
        # 서명 폐기 저장소가 없는 CI에서도 실제 서명·초기화·임시 디렉터리 정리를 거친다.
        cmd = [sys.executable, "-c", "import runpy, sys\nfrom termination_lab_support import isolated_disposal\n"
               "with isolated_disposal():\n    runpy.run_path(sys.argv[1], run_name='__main__')\n", str(path)]
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=TESTS, env=env,
                              capture_output=True, timeout=TIMEOUT_S)
        rc, raw = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        rc, raw = "TIMEOUT", (exc.stdout or b"") + (exc.stderr or b"")
    except OSError as exc:
        rc, raw = "ERROR", str(exc).encode("utf-8")
    text = raw.decode("utf-8", "replace")
    lines = [line for line in text.splitlines() if line.strip()]
    ran = None
    if unittest_mode:
        match = UNITTEST_RAN.search(text)
        ran = int(match.group(1)) if match else 0
    ok = rc == 0 and (ran is None or ran > 0)
    entry.update(status="통과" if ok else "실패", rc=rc, seconds=round(time.time() - started, 1),
                 ran=ran, last_line=lines[-1][:200] if lines else "", output=text)
    # 완료된 assertion 불일치만 대기다. import·시험 예외·0개 실행·도구 종료는 실패로 남긴다.
    if path.name in REVIEW_PENDING and rc == 1 and ran and UNITTEST_FAILURES.search(text):
        entry.update(status="검토 갱신 대기", note=REVIEW_PENDING[path.name])
    if unittest_mode and rc == 0 and not ran:
        entry["note"] = (entry["note"] + "; " if entry["note"] else "") + "시험 0개 실행"
    return entry


def run_pg(path: Path) -> dict:
    entry = {"file": path.name, "status": "실패", "rc": "ERROR", "seconds": 0.0,
             "ran": None, "last_line": "", "note": ""}
    started = time.monotonic()
    database = f"t_{path.stem}_py_{uuid.uuid4().hex[:12]}"
    created = False
    try:
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo

        # 원래 접속 DB에는 스키마를 적용하지 않고 직접 만든 DB만 삭제한다.
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, connect_timeout=10) as admin:
            try:
                admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database)))
                created = True
                target = make_conninfo(os.environ["DATABASE_URL"], dbname=database)
                if path.stem != "endpoint_evidence_pg_check":
                    with psycopg.connect(target, autocommit=True, connect_timeout=10) as connection:
                        for name in ("init.sql", "seed-lab.sql"):
                            connection.execute((TESTS.parent / "db" / name).read_text(encoding="utf-8"))
                with tempfile.TemporaryDirectory(prefix="mint-pg-") as folder:
                    env = child_env()
                    env.update(DATABASE_URL=target, EVIDENCE_LAB="isolated", OTEL_SDK_DISABLED="true",
                               IDP_ISSUER="https://gateway.lab.test", ENDPOINT_GATEWAY_IPS="127.0.0.1",
                               REGISTRY_DIR=str(TESTS.parent / "registry"), REGISTRY_RUNTIME_DIR=folder,
                               REPORT_DIR=folder)
                    entry = run_one(path, env)
            finally:
                if created:
                    admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
    except Exception as exc:
        # 접속 문자열에 자격이 있으므로 드라이버 오류 원문은 결과물에 남기지 않는다.
        entry.update(status="실패", rc="ERROR", note=f"PostgreSQL 준비·정리 실패: {type(exc).__name__}")
    entry["seconds"] = round(time.monotonic() - started, 1)
    return entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="JSON 결과 파일 경로(없으면 표준 출력)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--pg", action="store_true", help="DATABASE_URL의 서버에 파일별 전용 DB를 만들어 PostgreSQL 시험 실행")
    mode.add_argument("--inventory", action="store_true", help="CI·실행기·생략 표에 없는 시험이 있으면 실패")
    args = parser.parse_args()
    if args.inventory:
        data = inventory()
        encoded = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
        if args.out:
            Path(args.out).write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.buffer.write(encoded.encode("utf-8"))
        print(f"inventory {data['total']} {data['counts']} excluded={len(data['excluded'])}", file=sys.stderr)
        return int(bool(data["counts"]["orphan"]))
    files = discover(pg=args.pg)
    if args.pg:
        # OPA 정책을 교체하는 시험이 있으므로 PostgreSQL 시험끼리도 순서를 보장한다.
        results = [run_pg(path) for path in files]
    else:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(run_one, files))
    counts = {status: 0 for status in ("통과", "실패", "외부 의존 생략", "검토 갱신 대기")}
    for entry in results:
        counts[entry["status"]] += 1
    data = json.dumps({"results": results, "counts": counts}, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        Path(args.out).write_text(data, encoding="utf-8")
    else:
        sys.stdout.buffer.write(data.encode("utf-8"))
    print(f"total {len(results)} " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())), file=sys.stderr)
    return 1 if not results or counts.get("실패") else 0


if __name__ == "__main__":
    sys.exit(main())
