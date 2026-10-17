"""Rows for the shared Google Sheet copy of the WBS board.

Prints a JSON 2D array for the Sheets connector's update_formulas, starting at WBS!A1.
Scores come from snapshot.json; progress, status and the summary are sheet formulas.
`--owners owners.json` maps task ids to {"owner": ..., "memo": ...} for work in flight.

    python -X utf8 research/development-status-site/sheet_rows.py [--owners FILE] > rows.json
"""
import argparse
import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAP = ROOT / "research/llm-wiki/analysis/development-wbs/snapshot.json"
STAGES = ["implementation", "regression", "deployment", "real_device", "acceptance_complete"]
FIRST = 8  # first data row; the summary formulas reference rows FIRST.. open-ended

parser = argparse.ArgumentParser()
parser.add_argument("--owners")
args = parser.parse_args()
owners = json.loads(Path(args.owners).read_text(encoding="utf-8")) if args.owners else {}
data = json.loads(SNAP.read_text(encoding="utf-8"))
goals = {g["id"]: g["title"] for g in data["goals"]}
head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")



def cut(text: str, n: int = 90) -> str:
    # Full text lives in the wiki; the sheet keeps sync calls small.
    return text if len(text) <= n else text[: n - 1] + "…"


rows = [
    ["MINT 개발 WBS"] + [None] * 17,
    [f"기준 저장소 main {head} · 갱신 {now} · 점수는 snapshot.json, 진척률·상태·요약은 시트 수식"] + [None] * 17,
    [None] * 18,
    ["전체 작업", "단계 가중 진척", "구현 완료(검수 전)", "일부 구현", "개발 예정", "검수 완료"] + [None] * 12,
    [f"=COUNTA(A{FIRST}:A)", f"=AVERAGE(M{FIRST}:M)", f'=COUNTIF(N{FIRST}:N,"구현 완료(검수 전)")',
     f'=COUNTIF(N{FIRST}:N,"일부 구현")', f'=COUNTIF(N{FIRST}:N,"개발 예정")', f'=COUNTIF(N{FIRST}:N,"검수 완료")'] + [None] * 12,
    [None] * 18,
    ["ID", "목표", "작업", "구분", "백로그", "정책", "우선", "구현", "회귀", "배포", "실기기", "검수",
     "진척률", "상태", "담당", "진행 메모", "계획 일정", "완료 조건"],
]
for n, it in enumerate(data["items"], start=FIRST):
    s = it["stage_scores"]
    own = owners.get(it["id"], {})
    rows.append([
        it["id"], f'{it["goal_id"]} {goals[it["goal_id"]]}', it["title"], it.get("kind", "현재 개발"),
        it.get("backlog_id") or "", " · ".join(it.get("pol_ids", [])), it["priority"],
        *[s[k] for k in STAGES],
        f"=AVERAGE(H{n}:L{n})",
        f'=IF(H{n}=0,"개발 예정",IF(H{n}<1,"일부 구현",IF(M{n}=1,"검수 완료","구현 완료(검수 전)")))',
        own.get("owner", ""), cut(own.get("memo", "") or it["known_gap"]),
        " ~ ".join(it["planned_weeks"]) if it.get("planned_weeks") else "", cut(it["completion_condition"]),
    ])
print(json.dumps(rows, ensure_ascii=False))
