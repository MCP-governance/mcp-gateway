"""Extend the WBS from 40 audited tasks to the 57 of the 2026-10-17 feature specification.

The 40 tasks keep their 10-15 stage scores. G01.05 (runtime worker, 10-15 night) and the 16
planned tasks come from analysis/feature-spec-2026-10-17/feature-spec.json. Every task gains
its POL-01..50 ids, so the board speaks the team's policy numbering. The previous snapshot is
kept as snapshot-before-wbs-1017.json. Run from the repository root:

    python -X utf8 research/development-status-site/extend_1017.py
"""
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WBS = ROOT / "research/llm-wiki/analysis/development-wbs"
SPEC = ROOT / "research/llm-wiki/analysis/feature-spec-2026-10-17/feature-spec.json"
DIST = ROOT / "research/development-status-site/dist/data.json"
STAGES = ["implementation", "regression", "deployment", "real_device", "acceptance_complete"]
# Bundles the owner chose on 2026-10-17 to start now.
P0 = {"G03.05", "G03.08", "G02.06", "G08.05", "G01.06", "G06.05", "G07.05", "G07.06"}

before = WBS / "snapshot-before-wbs-1017.json"
if not before.exists():
    shutil.copyfile(WBS / "snapshot.json", before)
data = json.loads(before.read_text(encoding="utf-8"))
spec = {t["id"]: t for t in json.loads(SPEC.read_text(encoding="utf-8"))["wbs"]}
assert len(data["items"]) == 40 and len(spec) == 57


def pol_ids(text: str) -> list[str]:
    nums = re.findall(r"\d+", text.replace("POL-", ""))
    return [f"POL-{int(n):02d}" for n in nums]


backlog = {}
for line in (ROOT / "research/llm-wiki/status/backlog.md").read_text(encoding="utf-8").splitlines():
    m = re.match(r"\| (DEV-\d+) \| .*\(WBS (G\d\d\.\d\d)\)", line)
    if m:
        backlog[m.group(2)] = m.group(1)

for item in data["items"]:
    item["pol_ids"] = pol_ids(spec[item["id"]]["policies"])
    item["kind"] = "현재 개발"

for tid, t in spec.items():
    if any(i["id"] == tid for i in data["items"]):
        continue
    scores = t["scores"]
    planned = t["kind"] == "추가 개발"
    note = "미착수" if planned else "10-15 밤 DEV-38 보고 기준(D-114)"
    data["items"].append({
        "id": tid, "goal_id": tid[:3], "title": t["task"], "source_pac_ids": [],
        "pol_ids": pol_ids(t["policies"]), "kind": t["kind"], "backlog_id": backlog.get(tid),
        "code_symbols_files": [] if planned else ["full_stack_lab/runtime/", "full_stack_lab/gateway/app/agent_service.py::runtime*"],
        "regression_test_candidates": [], "actual_evidence_paths": [],
        "known_gap": t["remaining"], "completion_condition": t["completion"],
        "stage_weights": {s: 0.2 for s in STAGES}, "evidence_as_of": ["2026-10-17" if planned else "2026-10-15"],
        "implementation_assessment": "planned" if planned else "complete",
        "stage_notes": {s: (note if scores[s] else "미확인") for s in STAGES},
        "stage_scores": scores,
        "progress": round(sum(scores.values()) * 20, 1),
        "complete": all(v == 1 for v in scores.values()),
        "priority": "P0" if tid in P0 else ("P1" if planned else "P2"),
        "planned_weeks": t["planned_weeks"],
        "evidence": [] if planned else [{"path": "research/llm-wiki/status/reports/2026-10-15-dev38-runtime.md"}],
    })
data["items"].sort(key=lambda i: i["id"])

items = data["items"]
n = len(items)
data["schema_version"] = 2
data["as_of"] = datetime.now(timezone.utc).isoformat()
data["summary"] = {
    "progress": round(sum(i["progress"] for i in items) / n, 1),
    "complete": sum(i["complete"] for i in items), "total": n,
    "stage_equivalent_counts": {s: sum(i["stage_scores"][s] for i in items) for s in STAGES},
    "implementation_full": sum(i["stage_scores"]["implementation"] == 1 for i in items),
    "implementation_partial": sum(i["stage_scores"]["implementation"] == 0.5 for i in items),
    "implementation_missing": sum(i["stage_scores"]["implementation"] == 0 for i in items),
}
for g in data["goals"]:
    rows = [i for i in items if i["goal_id"] == g["id"]]
    g.update(progress=round(sum(i["progress"] for i in rows) / len(rows), 1),
             complete=sum(i["complete"] for i in rows), total=len(rows))
current = [i for i in items if i["kind"] == "현재 개발"]
data["scope_change"] = {"before": 40, "after": n, "planned": n - len(current),
                        "current_progress": round(sum(i["progress"] for i in current) / len(current), 1),
                        "note": "10-17 기능명세서의 추가 개발 16개와 실행기 G01.05를 더했다. 기존 40개 점수는 10-15 그대로."}
data["source_snapshot"] = {"path": "research/llm-wiki/analysis/development-wbs/snapshot-before-wbs-1017.json",
                           "as_of": json.loads(before.read_text(encoding="utf-8"))["as_of"],
                           "historical_progress": None, "note": data["scope_change"]["note"]}
data["rubric"]["formula"] = "작업 각각의 5단계 점수(0/0.5/1) × 20%, 작업 동일 가중 평균. 기능 수·공수·일정·외부 인증 완료율이 아님."

text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
(WBS / "snapshot.json").write_text(text, encoding="utf-8", newline="\n")
DIST.write_text(text, encoding="utf-8", newline="\n")
print(json.dumps({"items": n, "summary": data["summary"], "current_progress": data["scope_change"]["current_progress"]}, ensure_ascii=False))
