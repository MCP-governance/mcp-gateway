"""Build reviewed candidate links; source PAC numbers are not runtime PAC IDs."""
import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from threat_trace_review import render_review, review_references

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]

REVIEW = ROOT / 'analysis/threat-trace-review-1020/review.json'


def build():
    verified_on = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    local_risks = ROOT / "catalogs/local-tool-risks.json"
    risks = json.loads(local_risks.read_text(encoding="utf-8")) if local_risks.is_file() else []
    source = json.loads((ROOT / "threats/extracted/policies.json").read_text(encoding="utf-8"))
    rows = {p["source_id"]: p for p in source["policies"] if p["sheet"] == "정책 최종본"}
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    assert review["source_sha256"] == source["sha256"], "Source version changed; review mapping first"
    assert len(rows) == len(review["policies"]) == 24
    assert set(rows) == {p["source_id"] for p in review["policies"]}, "Source policy set changed; review mapping first"
    ledger = json.loads((REPO / "full_stack_lab/opa/policy_ledger.json").read_text(encoding="utf-8"))["policy_ledger"]
    evidence_index = {e["id"]: e for e in review["evidence"]}
    review_hash = hashlib.sha256(REVIEW.read_bytes()).hexdigest()
    output, markdown = [], ["# 원본 24개 정책 → 통제·코드 후보 매핑", "",
       f"{verified_on} 정적 연구 매핑입니다. 코드 경로 존재와 로컬 바이트 해시를 확인했고 해당 통제의 전체 구현·실기기 집행을 증명하지 않습니다.",
       "원본 PAC01~24와 런타임 PAC-01~15는 별도 번호 체계입니다. 50개 확장표는 별도 검토 목록으로 보존합니다.", "",
       "| 원본 ID·셀 | 위협·통제 | 런타임 후보 | 코드 후보 | 남은 검증 |", "| --- | --- | --- | --- | --- |"]
    stale = set()
    for policy in review["policies"]:
        source_id = policy["source_id"]
        boundary = " · ".join(policy["control_locations"])
        runtime, limitation = policy["runtime_candidates"], policy["limitations"]
        assert set(runtime) <= set(ledger), f"Unknown runtime policy: {source_id}"
        files = dict.fromkeys(r["path"] for r in policy["code_references"])
        row = rows[source_id]
        assert row["row"] == policy["source_row"] and row["fields"]["정책 내용"] == policy["source_requirement"]
        changed = sorted({r["path"] for r in review_references(policy, evidence_index)
                          if not (REPO / r["path"]).is_file()
                          or hashlib.sha256((REPO / r["path"]).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                          != r["normalized_sha256"]})
        stale.update(changed)
        evidence = []
        for name in files:
            path = REPO / name
            assert path.is_file(), f"Missing code candidate: {name}"
            current_bytes = path.read_bytes()
            current_hash = hashlib.sha256(current_bytes).hexdigest()
            normalized_hash = hashlib.sha256(current_bytes.replace(b"\r\n", b"\n")).hexdigest()
            committed = subprocess.run(["git", "-C", str(REPO), "show", "HEAD:" + name],
                                       check=True, capture_output=True).stdout
            committed_hash = hashlib.sha256(committed.replace(b"\r\n", b"\n")).hexdigest()
            evidence.append({"path": name, "sha256": current_hash, "committed_sha256": committed_hash,
                             "normalized_sha256": normalized_hash,
                             "worktree_modified": normalized_hash != committed_hash})
        record = {"id": "TH-" + source_id[3:], "source_id": source_id, "title": row["fields"]["정책명"],
                  "threat": row["fields"].get("보안 위협", ""), "sheet": row["sheet"], "row": row["row"],
                  "source_sha256": source["sha256"], "boundary": boundary,
                  "runtime_candidates": runtime, "code_candidates": evidence,
                  "control_locations": policy["control_locations"], "code_references": policy["code_references"],
                  "regression_tests": policy["regression_tests"], "evidence_ids": policy["evidence_ids"],
                  "independent_review": {"path": REVIEW.relative_to(ROOT).as_posix(), "sha256": review_hash,
                      "reviewer": review["reviewer"], "reviewed_commit": review["reviewed_commit"],
                      "files_match_review": not changed, "changed_review_files": changed},
                  "verification": "static-candidate-mapping", "verified_on": verified_on,
                  "limitations": limitation, "experiment_index": "experiments/README.md",
                  "local_tool_risk_ids": [risk["id"] for risk in risks if source_id in risk["source_controls"]]}
        output.append(record)
        links = "<br>".join(f"[{e['path'].split('/')[-1]}](../../../{e['path']})" for e in evidence)
        markdown.append(f"| {source_id} · A{row['row']} | {boundary}: {record['threat']} | {', '.join(runtime)} | {links} | {limitation} |")
    (ROOT / "catalogs").mkdir(exist_ok=True)
    (ROOT / "catalogs/threats.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    markdown += ["", "[24행 독립 검토·정정·근거·결정 필요](../analysis/threat-trace-review-1020/README.md). "
                 "코드 후보는 현재 파일 hash이며 심볼·시험·보고서는 검토 당시 hash를 별도 보존합니다. "
                 "`files_match_review=false`이면 과거 검토를 현재 구현 확인으로 사용하지 않습니다. "
                 "CRLF/LF 차이는 실제 코드 변경과 구분하고 `worktree_modified=true`인 파일을 자동 커밋하지 않습니다."]
    if risks:
        markdown += ["", "[로컬 도구·MCP 위험매핑](local-tool-map.md)의 실제 스키마·호출·반례를 연결했습니다. 원본 24개 정책은 유지하며 로컬 실험 결과를 관리 엔드포인트 집행 완료로 승격하지 않습니다."]
    (ROOT / "threats/control-map.md").write_text("\n".join(markdown) + "\n", encoding="utf-8", newline="\n")
    render_review(REVIEW, review, stale)
    print(f"Mapped {len(output)} source policies; static review only; stale review files: {len(stale)}")


if __name__ == "__main__":
    build()
