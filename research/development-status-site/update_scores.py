"""Apply evidence-backed WBS score changes to snapshot.json and the hub copy.

    python -X utf8 research/development-status-site/update_scores.py CHANGES.json

CHANGES.json: {"evidence": "<path in repo>", "items": {"G03.05": {"scores": {...}, "notes": {...},
"known_gap": "..."}}}. Only listed stages change; progress and the summary are recomputed.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAP = ROOT / "research/llm-wiki/analysis/development-wbs/snapshot.json"
DIST = ROOT / "research/development-status-site/dist/data.json"
STAGES = ["implementation", "regression", "deployment", "real_device", "acceptance_complete"]

change = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert (ROOT / change["evidence"]).exists(), change["evidence"]
data = json.loads(SNAP.read_text(encoding="utf-8"))
by_id = {i["id"]: i for i in data["items"]}
for tid, c in change["items"].items():
    it = by_id[tid]
    it["stage_scores"].update(c.get("scores", {}))
    it["stage_notes"].update(c.get("notes", {}))
    if "known_gap" in c:
        it["known_gap"] = c["known_gap"]
    it["progress"] = round(sum(it["stage_scores"][s] for s in STAGES) * 20, 1)
    it["complete"] = all(it["stage_scores"][s] == 1 for s in STAGES)
    it["evidence"] = it.get("evidence", []) + [{"path": change["evidence"]}]
    it.setdefault("evidence_as_of", []).append(datetime.now(timezone.utc).date().isoformat())

items = data["items"]
n = len(items)
data["as_of"] = datetime.now(timezone.utc).isoformat()
data["summary"].update({
    "progress": round(sum(i["progress"] for i in items) / n, 1),
    "complete": sum(i["complete"] for i in items),
    "stage_equivalent_counts": {s: sum(i["stage_scores"][s] for i in items) for s in STAGES},
    "implementation_full": sum(i["stage_scores"]["implementation"] == 1 for i in items),
    "implementation_partial": sum(i["stage_scores"]["implementation"] == 0.5 for i in items),
    "implementation_missing": sum(i["stage_scores"]["implementation"] == 0 for i in items),
})
for g in data["goals"]:
    rows = [i for i in items if i["goal_id"] == g["id"]]
    g.update(progress=round(sum(i["progress"] for i in rows) / len(rows), 1), complete=sum(i["complete"] for i in rows))
current = [i for i in items if i.get("kind") == "현재 개발"]
if "scope_change" in data:
    data["scope_change"]["current_progress"] = round(sum(i["progress"] for i in current) / len(current), 1)
text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
SNAP.write_text(text, encoding="utf-8", newline="\n")
DIST.write_text(text, encoding="utf-8", newline="\n")
print(json.dumps({"progress": data["summary"]["progress"], "changed": {t: by_id[t]["progress"] for t in change["items"]}}, ensure_ascii=False))
