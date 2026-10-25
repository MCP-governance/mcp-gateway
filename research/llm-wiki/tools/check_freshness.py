"""check_wiki.py가 보지 않는 「낡음」을 잰다: 현황·백로그·진입점이 코드·결정·보고서보다 늦은지. 표준 라이브러리만 쓴다.

기본은 경고만 출력하고 종료 코드 0이다(--strict이면 낡음이 있을 때 1). 기준일은 시스템 시계가 아니라 저장소 마지막 커밋이다.
"""
import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import decisions_layout as dl

REPO = dl.REPO
WIKI = "research/llm-wiki"
CODE = ["full_stack_lab/gateway/app", "full_stack_lab/opa", "endpoint-agent"]
DAY = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, encoding="utf-8").stdout.strip()


def last_day(*paths):
    return git("log", "-1", "--format=%cs", "--", *paths)


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def doc_date(path, pattern):
    text = (REPO / path).read_text(encoding="utf-8-sig") if (REPO / path).exists() else ""
    m = re.search(pattern, text, re.M)
    return m[1] if m else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    head = git("log", "-1", "--format=%cs")
    code_day = last_day(*CODE)
    decisions = [s["num"] for s in dl.sections()]
    newest_decision = max(decisions)
    rows = []

    def add(name, ok, detail):
        rows.append((name, ok, detail))

    stamped = {
        f"{WIKI}/status/current.md": r"^# .*?(20\d{2}-\d{2}-\d{2})",
        f"{WIKI}/status/backlog.md": r"^## 먼저 볼 것 \((20\d{2}-\d{2}-\d{2})\)",
        f"{WIKI}/README.md": r"^## 지금 상태 \((20\d{2}-\d{2}-\d{2})\)",
        f"{WIKI}/START_HERE.md": r"기준일[: ]+(20\d{2}-\d{2}-\d{2})",
    }
    for path, pattern in stamped.items():
        stamp = doc_date(path, pattern)
        if not stamp:
            add(path, False, "기준일 표기를 찾지 못했다")
            continue
        lag = days(stamp, code_day) if code_day else 0
        add(path, lag <= 0, f"기준일 {stamp}, 제품 코드 마지막 변경 {code_day} ({lag:+d}일)")

    current = (REPO / WIKI / "status/current.md").read_text(encoding="utf-8-sig")
    cited = [int(n) for n in re.findall(r"\bD-(\d+)\b", current)]
    gap = newest_decision - max(cited) if cited else newest_decision
    add("current.md가 인용한 최신 결정", gap <= 0, f"current.md 최대 D-{max(cited) if cited else '—'}, 결정 기록 최대 D-{newest_decision} (차이 {gap})")

    cur_day = doc_date(f"{WIKI}/status/current.md", stamped[f"{WIKI}/status/current.md"])
    newer = [p.name for p in (REPO / WIKI / "status/reports").glob("20*.md") if cur_day and p.name[:10] > cur_day]
    add("current.md 이후에 쓴 작업 보고서", not newer, f"{len(newer)}건" + (f" ({', '.join(sorted(newer)[:4])})" if newer else ""))

    behind = git("rev-list", "--count", f"{git('log', '-1', '--format=%H', '--', f'{WIKI}/status/current.md')}..HEAD", "--", *CODE)
    add("current.md 이후 제품 코드 커밋", behind in ("", "0"), f"{behind or 0}개")

    pulled = last_day(f"{WIKI}/sheet/pulled")
    add("시트 당겨오기(sheet/pulled) 마지막 반영", bool(pulled) and days(pulled, head) <= 3,
        f"{pulled or '없음'} (저장소 마지막 커밋 {head}, {days(pulled, head) if pulled else '—'}일 차이). "
        "sheet_pull.py는 사람이 돌리는 도구이고 CI·정기 실행이 없다")

    for name, cmd in (("보고서 색인", ["build_report_index.py", "--check"]), ("결정 색인", ["split_decisions.py", "index", "--check"])):
        res = subprocess.run([sys.executable, str(Path(__file__).with_name(cmd[0])), *cmd[1:]], capture_output=True, text=True, encoding="utf-8")
        add(name, res.returncode == 0, (res.stdout or res.stderr).strip().splitlines()[-1] if (res.stdout or res.stderr).strip() else "")

    stale = [r for r in rows if not r[1]]
    for name, ok, detail in rows:
        print(f"{'정상' if ok else '낡음'}  {name}: {detail}")
    print(f"낡음 {len(stale)}건 / 점검 {len(rows)}건 (기준: 저장소 마지막 커밋 {head})")
    return 1 if stale and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
