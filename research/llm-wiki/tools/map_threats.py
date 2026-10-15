"""Build reviewed candidate links; source PAC numbers are not runtime PAC IDs."""
import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]

# Candidate associations based on each source row's control meaning, never its number.
MAPPING = [
    ("PAC01", "도입·공급망", ["MCP-SUPPLY-001"], ["full_stack_lab/tests/intake_validation_test.py"], "라이선스·배포처·SBOM·취약점과 실제 도입 승인 증거 필요"),
    ("PAC02", "계약·권한 범위", ["PAC-01", "PAC-08"], ["full_stack_lab/gateway/app/agent_service.py", "full_stack_lab/gateway/app/pac.py"], "도구 계약과 실제 자원·인자의 승인 범위 독립 검토"),
    ("PAC03", "승인·유효기간", ["P-APPROVAL-EXPIRY-001", "PAC-01"], ["full_stack_lab/gateway/app/core.py"], "사용자 동의와 서버 사용 승인은 별도 증거"),
    ("PAC04", "시험·환경", ["PAC-03"], ["full_stack_lab/opa/pac15.rego"], "환경 사실 입력과 실기기 관찰값 결합 검증"),
    ("PAC05", "목적지·SSRF", ["MCP-EGRESS-001", "MCP-EGRESS-002"], ["full_stack_lab/gateway/app/classify.py", "full_stack_lab/gateway/app/upstream.py"], "OAuth discovery·DNS 재결합 등 최종 접속 대상의 별도 경계"),
    ("PAC06", "도구 계약", ["MCP-CATALOG-001", "PAC-08"], ["full_stack_lab/gateway/app/contract.py", "full_stack_lab/gateway/app/core.py"], "동명 도구·설명·스키마 변경과 승인 이후 변형 시험"),
    ("PAC07", "엔드포인트 우회", ["MCP-SHADOW-*", "ENDPOINT-MANAGED-001"], ["endpoint-agent/enforce-linux.py", "endpoint-agent/managed-linux.py", "endpoint-agent/managed-windows.py", "endpoint-agent/agent.py", "full_stack_lab/gateway/app/endpoint_plane.py"], "로컬 MCP 실험·코드 회귀와 현재 관리 기기의 OS 집행을 구분; Windows loopback·실행 통제 공백 유지"),
    ("PAC08", "신원", ["PAC-04"], ["full_stack_lab/gateway/app/idp.py", "full_stack_lab/gateway/app/core.py"], "transport 신원과 사용자 자기 선언 필드 분리"),
    ("PAC09", "위임", ["PAC-05"], ["full_stack_lab/gateway/app/pac.py", "full_stack_lab/opa/pac15.rego"], "위임 근거·교집합·철회·만료 시험; 하네스 이름은 인증 근거 아님"),
    ("PAC10", "토큰", ["PAC-06"], ["full_stack_lab/gateway/app/idp.py", "full_stack_lab/gateway/app/upstream.py"], "audience·scope·issuer·만료·직원 토큰 미전달의 독립 검증"),
    ("PAC11", "호출별 권한", ["PAC-09"], ["full_stack_lab/gateway/app/core.py", "full_stack_lab/opa/pac15.rego"], "이전 허용·캐시 결과를 범위가 다른 요청에 재사용하는지 시험"),
    ("PAC12", "행위 구분", ["PAC-09"], ["full_stack_lab/gateway/app/classify.py"], "도구 이름이 아닌 실제 SQL·명령·수신자 효과로 분류"),
    ("PAC13", "스키마·인자", ["P-INPUT-SCHEMA-001", "PAC-10"], ["full_stack_lab/gateway/app/core.py", "full_stack_lab/gateway/app/classify.py"], "정책 전과 실행 직전 입력 검사 및 정규화 우회 시험"),
    ("PAC14", "자산·등급", ["P-CLASSIFICATION-001", "PAC-11"], ["full_stack_lab/gateway/app/classify.py", "full_stack_lab/gateway/app/pac.py"], "미분류를 낮은 등급으로 허용하지 않는지 확인"),
    ("PAC15", "외부 전송", ["MCP-DATA-EGRESS-001", "PAC-12"], ["full_stack_lab/gateway/app/classify.py", "full_stack_lab/gateway/app/privacy.py"], "실제 최종 목적지·데이터 조합과 프롬프트/모델 경로는 따로 검증"),
    ("PAC16", "개별 승인", ["PAC-13"], ["full_stack_lab/gateway/app/core.py", "full_stack_lab/tests/reservation_effect_check.py"], "nonce·canonical fingerprint·자가 승인·동시 승인 재사용 시험"),
    ("PAC17", "호출·동시성", ["P-RATE-001", "P-RATE-002", "P-RATE-003"], ["full_stack_lab/gateway/app/core.py", "full_stack_lab/tests/reservation_effect_check.py"], "호출량 상한과 모든 upstream의 실행 시간 제한을 동일시하지 않음"),
    ("PAC18", "비신뢰 콘텐츠", ["P-UNTRUSTED-CONTENT-001", "P-UNTRUSTED-CONTENT-002"], ["full_stack_lab/gateway/app/poisoning.py"], "패턴 검사와 의미적 주입 탐지 구분; 정상 대조군·다국어 표본 필요"),
    ("PAC19", "입력 PII·Secret", ["P-DATA-INSPECTION-001"], ["full_stack_lab/gateway/app/privacy.py", "full_stack_lab/gateway/app/secret_scan.py"], "불필요 수집 제한과 탐지 성공은 다른 통제; scanner 장애 시험"),
    ("PAC20", "출력 PII·Secret", ["MCP-OUTPUT-001"], ["full_stack_lab/gateway/app/core.py", "full_stack_lab/gateway/app/privacy.py"], "응답 보류·마스킹은 upstream 미실행을 뜻하지 않음"),
    ("PAC21", "변경 재승인", ["MCP-CATALOG-001", "PAC-02"], ["full_stack_lab/gateway/app/contract.py", "full_stack_lab/gateway/app/core.py"], "자동 최초 신뢰 금지; 사람이 승인한 계약과 호출 시 관찰 해시 대조"),
    ("PAC22", "감사", ["append-only audit"], ["full_stack_lab/gateway/app/audit.py", "full_stack_lab/tests/oss_audit_test.py", "full_stack_lab/gateway/app/endpoint_plane.py"], "체인 검증과 장치 상태/감사 이벤트의 transaction 원자성·DB 소유자 변조·보존 정책은 별도"),
    ("PAC23", "철회·종료", ["MCP-DECOMM-001", "PAC-14"], ["full_stack_lab/gateway/app/decommission.py", "full_stack_lab/tests/termination_flow.py"], "C1~C4와 자원 서버 재접근의 현재 증거 필요"),
    ("PAC24", "잔존 자격", ["PAC-14", "C3/C4"], ["full_stack_lab/gateway/app/idp.py", "full_stack_lab/gateway/app/decommission.py"], "설정 삭제는 외부 토큰·키 회수 증거 아님"),
]


def build():
    verified_on = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    local_risks = ROOT / "catalogs/local-tool-risks.json"
    risks = json.loads(local_risks.read_text(encoding="utf-8")) if local_risks.is_file() else []
    source = json.loads((ROOT / "threats/extracted/policies.json").read_text(encoding="utf-8"))
    rows = {p["source_id"]: p for p in source["policies"] if p["sheet"] == "정책 최종본"}
    assert set(rows) == {m[0] for m in MAPPING}, "Source policy set changed; review mapping first"
    output, markdown = [], ["# 원본 24개 정책 → 통제·코드 후보 매핑", "",
       f"{verified_on} 정적 연구 매핑입니다. 코드 경로 존재와 로컬 바이트 해시를 확인했고 해당 통제의 전체 구현·실기기 집행을 증명하지 않습니다.",
       "원본 PAC01~24와 런타임 PAC-01~15는 별도 번호 체계입니다. 50개 확장표는 별도 검토 목록으로 보존합니다.", "",
       "| 원본 ID·셀 | 위협·통제 | 런타임 후보 | 코드 후보 | 남은 검증 |", "| --- | --- | --- | --- | --- |"]
    for source_id, boundary, runtime, files, limitation in MAPPING:
        row = rows[source_id]
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
                  "verification": "static-candidate-mapping", "verified_on": verified_on,
                  "limitations": limitation, "experiment_index": "experiments/README.md",
                  "local_tool_risk_ids": [risk["id"] for risk in risks if source_id in risk["source_controls"]]}
        output.append(record)
        links = "<br>".join(f"[{e['path'].split('/')[-1]}](../../../{e['path']})" for e in evidence)
        markdown.append(f"| {source_id} · A{row['row']} | {boundary}: {record['threat']} | {', '.join(runtime)} | {links} | {limitation} |")
    (ROOT / "catalogs").mkdir(exist_ok=True)
    (ROOT / "catalogs/threats.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown += ["", "JSON에는 로컬 파일의 원래 바이트 hash와 LF 정규화 hash, HEAD의 commit 파일 hash를 함께 기록했습니다. 코드의 CRLF/LF 차이는 실제 코드 변경과 구분합니다. 자료 원본 hash는 줄바꿈까지 그대로 보존합니다. `worktree_modified=true`인 기존 미커밋 파일은 위키 커밋에 포함하지 않습니다. 다른 PC의 HEAD 코드와 이 매핑의 로컬 관찰값이 다를 수 있으므로 실제 변경 파일을 다시 확인합니다."]
    if risks:
        markdown += ["", "[로컬 도구·MCP 위험매핑](local-tool-map.md)의 실제 스키마·호출·반례를 연결했습니다. 원본 24개 정책은 유지하며 로컬 실험 결과를 관리 엔드포인트 집행 완료로 승격하지 않습니다."]
    (ROOT / "threats/control-map.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(f"Mapped {len(output)} source policies; all code paths exist; runtime verification pending")


if __name__ == "__main__":
    build()
