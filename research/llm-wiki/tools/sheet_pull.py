"""Pull published management CSVs; also shared by the read-only collaboration console."""
import argparse
import copy
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

WIKI = Path(__file__).resolve().parents[1]
CONFIG = WIKI.parent / "collaboration-console/runtime/sheet-source.json"
SNAPSHOT = WIKI / "analysis/development-wbs/snapshot.json"
STAGES = dict(zip(("구현", "회귀", "배포", "실기기", "검수"),
                  ("implementation", "regression", "deployment", "real_device", "acceptance_complete")))
FILES = {"wbs": "02-wbs.csv", "backlog": "03-backlog.csv"}
FIELDS = {"담당": "owner", "진행 메모": "memo", "계획 일정": "planned_schedule"}
STATUSES = ("개발 예정", "일부 구현", "검수 완료", "구현 완료(검수 전)")


def read_config(path=CONFIG):
    if not path.exists():
        return {}
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict) or any(not isinstance(config.get(k, ""), str)
                                         for k in ("wbs_csv", "backlog_csv", "sheet_url")):
        raise ValueError("시트 설정은 문자열 URL을 담은 JSON 객체여야 합니다")
    return {k: v.strip() if isinstance(v, str) else v for k, v in config.items()}


def fetch_csv(url):
    if urlsplit(url).scheme not in ("https", "http", "file"):
        raise ValueError("CSV URL은 https/http/file만 지원합니다")
    with urlopen(url, timeout=15) as response:
        return response.read().decode("utf-8-sig")


def parse_csv(text, kind):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff"), newline=""), strict=True)
    required = ({"ID", "목표", "목표명", "작업", "완료 조건", "남은 일", *STAGES, *FIELDS}
                if kind == "wbs" else {"ID", "작업", "상태", "진행", "완료 조건", "WBS", "결정", "근거 자료"})
    headers = reader.fieldnames or []
    if len(set(headers)) != len(headers) or not required.issubset(headers):
        raise ValueError(f"{kind}: CSV 머리글 누락 또는 중복")
    rows, seen = [], set()
    for row in reader:
        if not any(row.values()):
            continue
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f"{kind}: CSV 열 개수 불일치")
        row = {k: v.strip() for k, v in row.items()}
        if not row["ID"] or row["ID"] in seen:
            raise ValueError(f"{kind}: 빈 ID 또는 중복 ID")
        seen.add(row["ID"])
        if kind == "wbs":
            scores_for(row)
        rows.append(row)
    return headers, rows


def scores_for(row):
    scores = {key: float(row[column] or 0) for column, key in STAGES.items()}
    if any(value not in (0, 0.5, 1) for value in scores.values()):
        raise ValueError(f"{row['ID']}: 점수는 0/0.5/1이어야 합니다")
    return scores


def summarize(items):
    total = len(items)
    return {
        "total": total, "complete": sum(item["complete"] for item in items),
        "progress": round(sum(item["progress"] for item in items) / total, 1) if total else 0,
        "stage_equivalent_counts": {key: sum(item["stage_scores"][key] for item in items) for key in STAGES.values()},
        "implementation_full": sum(item["stage_scores"]["implementation"] == 1 for item in items),
        "implementation_partial": sum(item["stage_scores"]["implementation"] == 0.5 for item in items),
        "implementation_missing": sum(item["stage_scores"]["implementation"] == 0 for item in items),
        "status_counts": {status: sum(item["status"] == status for item in items) for status in STATUSES},
    }


def overlay_wbs(snapshot, rows, add_new=True):
    data = copy.deepcopy(snapshot)
    items = {item["id"]: item for item in data["items"]}
    changed = []
    goal_titles = {goal["id"]: goal["title"] for goal in data.get("goals", [])}
    for row in rows:
        item = items.get(row["ID"])
        if item is None:
            if not add_new:
                continue
            item = {"id": row["ID"], "goal_id": row["목표"], "title": row["작업"],
                    "completion_condition": row["완료 조건"], "known_gap": row["남은 일"],
                    "priority": row.get("우선") or "P2", "kind": row.get("구분", ""),
                    "stage_notes": {key: "" for key in STAGES.values()}}
            data["items"].append(item)
            items[item["id"]] = item
        before = copy.deepcopy(item)
        item["stage_scores"] = scores_for(row)
        item.update({field: row[column] for column, field in FIELDS.items()})
        if item != before:
            changed.append(item["id"])
        goal_titles.setdefault(row["목표"], row["목표명"])
    for item in data["items"]:
        scores = item["stage_scores"]
        item["progress"] = round(sum(scores.values()) * 20, 1)
        item["complete"] = item["progress"] == 100
        implementation = scores["implementation"]
        item["status"] = STATUSES[0] if implementation == 0 else STATUSES[1] if implementation < 1 else STATUSES[2] if item["complete"] else STATUSES[3]
    data["summary"] = summarize(data["items"])
    data["goals"] = []
    for goal_id, title in goal_titles.items():
        group = summarize([item for item in data["items"] if item["goal_id"] == goal_id])
        data["goals"].append({"id": goal_id, "title": title, **group})
    for stage, key in zip(data.get("pipeline", []), STAGES.values()):
        stage["state"] = f"{data['summary']['stage_equivalent_counts'][key]:g} / {len(data['items'])}"
    return data, changed


class SheetSource:
    def __init__(self, config_path=CONFIG):
        self.config_path = Path(config_path)
        self.cache = {}
        self.lock = threading.Lock()

    def get(self, kind):
        meta = {"source": "snapshot", "fetched_at": None, "error": None, "url": ""}
        try:
            config = read_config(self.config_path)
            meta["url"] = config.get("sheet_url", "")
            url = config.get(kind + "_csv", "")
            if not url:
                return None, meta
        except (OSError, ValueError) as exc:
            meta["error"] = str(exc)
            return None, meta
        # One fetch per source, including failed attempts, even with concurrent viewers.
        with self.lock:
            key = (kind, url)
            entry = self.cache.get(key)
            now = time.monotonic()
            if entry is None or now - entry["checked"] >= 300:
                rows = entry["rows"] if entry else None
                fetched_at = entry["fetched_at"] if entry else None
                error = None
                try:
                    _, rows = parse_csv(fetch_csv(url), kind)
                    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                except (OSError, ValueError, csv.Error) as exc:
                    error = str(exc)
                entry = {"rows": rows, "fetched_at": fetched_at, "error": error, "checked": time.monotonic()}
                self.cache[key] = entry
            meta.update(source="sheet" if entry["rows"] is not None else "snapshot",
                        fetched_at=entry["fetched_at"], error=entry["error"])
            return copy.deepcopy(entry["rows"]), meta


def pull(config_path=CONFIG, wbs_csv=None, backlog_csv=None, from_dir=None, apply_snapshot=False,
         wiki=WIKI, snapshot_path=SNAPSHOT):
    config = {} if from_dir or (wbs_csv and backlog_csv) else read_config(Path(config_path))
    manifest = json.loads((wiki / "sheet/manifest.json").read_text(encoding="utf-8"))
    pending = {}
    for kind, filename in FILES.items():
        url = {"wbs": wbs_csv, "backlog": backlog_csv}[kind] or config.get(kind + "_csv")
        if not from_dir and not url:
            continue
        text = ((Path(from_dir) / filename).read_text(encoding="utf-8-sig") if from_dir else fetch_csv(url))
        headers, rows = parse_csv(text, kind)
        tab = next(tab for tab in manifest["tabs"] if tab.get("slug") == kind)
        expected = [column["name"] for column in tab["columns"]]
        if set(headers) != set(expected):
            raise ValueError(f"{kind}: manifest와 CSV 머리글 불일치")
        pending[kind] = (text, rows)
    if not pending:
        raise ValueError("CSV URL 또는 --from-dir가 필요합니다")
    changed, data = [], None
    if apply_snapshot:
        if "wbs" not in pending:
            raise ValueError("--apply-snapshot에는 WBS CSV가 필요합니다")
        data, changed = overlay_wbs(json.loads(snapshot_path.read_text(encoding="utf-8")), pending["wbs"][1], add_new=False)
    # Validate every source and the snapshot before overwriting any repository copy.
    # 시드(sheet/tabs)는 저장소 원천에서 만든 것이라 덮지 않고, 시트 값은 sheet/pulled에 따로 둔다.
    (wiki / "sheet/pulled").mkdir(parents=True, exist_ok=True)
    for kind, (text, _) in pending.items():
        (wiki / "sheet/pulled" / FILES[kind]).write_text(text, encoding="utf-8", newline="")
    if data is not None:
        snapshot_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        wiki = Path(directory)
        (wiki / "sheet/tabs").mkdir(parents=True)
        (wiki / "sheet/manifest.json").write_bytes((WIKI / "sheet/manifest.json").read_bytes())
        snapshot = wiki / "snapshot.json"
        snapshot.write_bytes(SNAPSHOT.read_bytes())
        source = wiki / "input"
        source.mkdir()
        for filename in FILES.values():
            (source / filename).write_bytes((WIKI / "sheet/tabs" / filename).read_bytes())
        path = source / FILES["wbs"]
        headers, rows = parse_csv(path.read_text(encoding="utf-8"), "wbs")
        rows[0].update({"구현": "0.5", "담당": "시험 담당", "진행 메모": "메모,\n두 줄", "계획 일정": "10/20"})
        rows.append({**rows[0], "ID": "SELF-TEST-NEW"})
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, list(reversed(headers)))
            writer.writeheader()
            writer.writerows(rows)
        changed = pull(from_dir=source, apply_snapshot=True, wiki=wiki, snapshot_path=snapshot)
        result = json.loads(snapshot.read_text(encoding="utf-8"))
        assert result["items"][0]["stage_scores"]["implementation"] == 0.5
        assert result["items"][0]["memo"] == "메모,\n두 줄"
        assert result["items"][0]["planned_schedule"] == "10/20"
        assert result["items"][0]["status"] == "일부 구현"
        assert result["summary"]["total"] == len(result["items"])
        assert "G01.01" in changed
        assert "SELF-TEST-NEW" not in {item["id"] for item in result["items"]}
        changed = pull(wbs_csv=path.as_uri(), backlog_csv=(source / FILES["backlog"]).as_uri(),
                       apply_snapshot=True, wiki=wiki, snapshot_path=snapshot)
        assert not changed
        original = (wiki / "sheet/pulled/02-wbs.csv").read_bytes()
        path.write_text(path.read_text(encoding="utf-8-sig").replace("시험 담당", "적용 금지"), encoding="utf-8")
        path = source / FILES["backlog"]
        headers, rows = parse_csv(path.read_text(encoding="utf-8"), "backlog")
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, headers + ["틀린 열"])
            writer.writeheader()
            writer.writerows(rows)
        try:
            pull(from_dir=source, wiki=wiki, snapshot_path=snapshot)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid headers were accepted")
        assert (wiki / "sheet/pulled/02-wbs.csv").read_bytes() == original
    print("sheet_pull self-test: passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--wbs-csv")
    parser.add_argument("--backlog-csv")
    parser.add_argument("--from-dir", type=Path)
    parser.add_argument("--apply-snapshot", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            changed = pull(args.config, args.wbs_csv, args.backlog_csv, args.from_dir, args.apply_snapshot)
            print("변경 ID: " + (", ".join(changed) or "없음"))
    except (OSError, ValueError, csv.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
