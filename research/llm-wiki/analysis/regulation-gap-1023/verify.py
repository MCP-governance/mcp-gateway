"""Check this research artifact's links, baseline hashes and existing regulation CSV keys."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIKI = HERE.parents[1]
REPO = WIKI.parents[1]


def main():
    doc = json.loads((HERE / "gap.json").read_text(encoding="utf-8"))
    errors = []
    rows = doc["requirements"]
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        errors.append("duplicate row IDs")
    sources = {s["id"] for s in doc["sources"]}
    reqs = {r["req_id"]: r for r in json.loads((WIKI / "analysis/compliance/requirements.json").read_text(encoding="utf-8"))["requirements"]}
    csv_rows = list(csv.DictReader((WIKI / "sheet/tabs/21-reg-requirements.csv").open(encoding="utf-8-sig", newline="")))
    sheet = {r["ID"]: r for r in csv_rows}
    for row in rows:
        if row["source_id"] not in sources or row["validation_profile"] not in doc["validation_profiles"]:
            errors.append(f"{row['id']}: missing source/profile")
        if not row["code"] or any(a not in doc["code"] for a in row["code"]):
            errors.append(f"{row['id']}: missing code evidence")
        if row["current_execution"] != "미실행":
            errors.append(f"{row['id']}: unexpected product execution claim")
        for ref in row["existing_requirements"]:
            original = reqs.get(ref["req_id"], {})
            if original.get("req_key") != ref["req_key"] or original.get("ref") != ref["ref"]:
                errors.append(f"{row['id']}: requirement key/ref mismatch")
            if sheet.get(ref["req_id"], {}).get("조항") != ref["ref"]:
                errors.append(f"{row['id']}: CSV clause mismatch")
    for alias, code in doc["code"].items():
        path = REPO / code["path"]
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != code["sha256"]:
            errors.append(f"{alias}: current code hash changed")
        if data.decode("utf-8").splitlines()[code["line"] - 1] != code["line_text"]:
            errors.append(f"{alias}: line changed")
        baseline = subprocess.run(["git", "show", f"{doc['baseline_commit']}:{code['path']}"], cwd=REPO, capture_output=True)
        if baseline.returncode or hashlib.sha256(baseline.stdout).hexdigest() != code["sha256"]:
            errors.append(f"{alias}: baseline code hash mismatch")
    link_count = 0
    for md in [HERE / "README.md", WIKI / "status/reports/2026-10-23-regulation-gap.md"]:
        for target in re.findall(r"\]\(([^)]+)\)", md.read_text(encoding="utf-8")):
            if target.startswith(("https://", "http://", "#")):
                continue
            target = target.split("#")[0]
            if target and not (md.parent / target).exists():
                errors.append(f"{md.name}: missing link {target}")
            link_count += 1
    original_count = 0
    for source in doc["sources"]:
        for original in source["preserved_files"]:
            path = WIKI / original["path"]
            if original["exists"]:
                original_count += 1
                if hashlib.sha256(path.read_bytes()).hexdigest() != original["sha256"]:
                    errors.append(f"preserved hash changed: {original['path']}")
    csv_inventory = {}
    for name in ["20-reg-docs.csv", "21-reg-requirements.csv", "24-reg-capabilities.csv", "25-reg-proposals.csv", "29-reg-incident-deadlines.csv", "30-reg-retention.csv", "32-reg-clauses.csv"]:
        path = WIKI / "sheet/tabs" / name
        csv_inventory[name] = dict(rows=len(list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    result = dict(checked_at=datetime.now(timezone.utc).isoformat(), ok=not errors,
                  task_id="RES-REGS", baseline_commit=doc["baseline_commit"],
                  requirements=len(rows), sources=len(sources), code_anchors=len(doc["code"]),
                  linked_existing_requirements=sum(len(r["existing_requirements"]) for r in rows),
                  local_links=link_count, present_preserved_files=original_count,
                  csv_inventory=csv_inventory, errors=errors,
                  limitation="Artifact consistency only. Not product tests or official-source completeness.")
    (HERE / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
