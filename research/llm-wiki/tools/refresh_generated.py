"""코드·결정·보고서를 바꾼 뒤 위키의 생성물을 한 번에 다시 만들고 검사한다. 표준 라이브러리만 쓴다.

CI가 코드 기준 해시(위협 매핑·요구사항·연동 조건)와 색인을 대조하므로, 제품 코드나 docs/ai를 고친 커밋은 끝에 이걸 돌린다.
  python research/llm-wiki/tools/refresh_generated.py             # 재생성 + 검사
  python research/llm-wiki/tools/refresh_generated.py --dry-run   # 실행할 명령만 출력
  python research/llm-wiki/tools/refresh_generated.py --skip-code-pointers   # 코드를 안 바꿨을 때(색인만)
생성물은 직접 고치지 않는다. 재생성 결과의 변경을 읽고 같은 커밋에 넣는다.
"""
import argparse
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[2]

CODE_POINTERS = [
    ("위협 매핑·코드 해시", ["map_threats.py"]),
    ("요구사항·연동 조건의 코드 위치", ["build_enterprise_analysis.py", "--refresh-code-only"]),
    ("저장소 스냅샷", ["capture_status.py"]),
]
INDEXES = [
    ("보고서 색인", ["build_report_index.py"]),
    ("결정 색인", ["split_decisions.py", "index"]),
]
CHECKS = [
    ("위키 검사", ["check_wiki.py", "--ci-ignored-local-sources"]),
    ("ID 추적", ["check_trace.py"]),
    ("기업 분석 해시", ["check_enterprise_analysis.py"]),
    ("신선도(경고)", ["check_freshness.py"]),
]


def run(label, cmd, dry):
    full = [sys.executable, "-B", "-X", "utf8", str(TOOLS / cmd[0]), *cmd[1:]]
    print(f"[{label}] {' '.join(cmd)}")
    if dry:
        return 0
    res = subprocess.run(full, cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    tail = (res.stdout + res.stderr).strip().splitlines()[-3:]
    print("\n".join("    " + line[:200] for line in tail))
    return res.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-code-pointers", action="store_true")
    args = parser.parse_args()
    steps = ([] if args.skip_code_pointers else CODE_POINTERS) + INDEXES
    failed = [label for label, cmd in steps if run(label, cmd, args.dry_run)]
    failed += [label for label, cmd in CHECKS[:-1] if run(label, cmd, args.dry_run)]
    run(*CHECKS[-1], args.dry_run)
    if failed:
        print("실패: " + ", ".join(failed))
        return 1
    print("완료" if not args.dry_run else "계획만 출력함")
    return 0


if __name__ == "__main__":
    sys.exit(main())
