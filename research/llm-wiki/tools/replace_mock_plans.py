"""One-time plan correction: actual commercial/OSS MCPs, never inferred execution."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
file = ROOT / "catalogs/experiments.json"
rows = json.loads(file.read_text(encoding="utf-8-sig"))
mapping = {"E01":"MCP-FILESYSTEM", "E02":"MCP-FILESYSTEM", "E03":"MCP-EMAIL", "E04":"MCP-EMAIL",
           "E05":"MCP-FETCH", "E06":"MCP-FILESYSTEM", "E07":"MCP-GITHUB-LOCAL", "E08":"MCP-FILESYSTEM",
           "E09":"MCP-GITHUB-REMOTE", "E10":"MCP-GITEA", "E11":"MCP-GITEA", "E12":"MCP-GITHUB-REMOTE",
           "E13":"MCP-FILESYSTEM"}
for row in rows:
    assert row["status"] == "not_run" and row["executed_on"] is None and row["result"] is None
    row["target_id"] = mapping[row["id"]]
    row["self_written_mcp"] = False
    row["plan_revision"] = "2026-10-13-real-commercial-oss-only"
    row["prerequisites"] = [p for p in row["prerequisites"] if "mock" not in p]
    row["prerequisites"] += ["실제 공개 OSS/상용 MCP의 판본·라이선스·tools/list·승인 계약 고정",
                              "독립 수신/효과 증거와 정상/음성/경계·원복 조건을 기록; 미확인은 통과 금지"]
    row["evidence"] += ["실제 서버 package/image digest·provider 판본 및 독립 접속/효과 로그"]
    if row["id"] == "E07":
        row["readiness"] = "official_github_test_instance_needed"
        row["input"] = {"server":"github-contract-test", "tool":"list_commits",
                        "arguments":{"owner":"test-owner", "repo":"test-repo", "perPage":1}}
        row["prerequisites"] += ["공식 GitHub MCP의 전용 자기 소유 시험 repo/인스턴스·read-only toolsets",
                                  "공식 toolset/description override 설정으로 A→B→A 변경; MCP 소스 수정 금지"]
        row["steps"] = ["repos toolset 정상군과 승인 hash를 기록",
                         "공식 toolset repos→issues 또는 description override로 계약 변경; lock 유지",
                         "catalog refresh 전/후 실제 하네스 호출을 나눠 각 policy_id·도구 미수신 확인",
                         "A 설정으로 복귀 후 최신 관찰·재승인 내용 A 확인; 시험 인스턴스만 복구"]
        row["cleanup"] = ["공식 서버의 원래 toolset/override 설정과 hash 복원; 전용 등록만 정리"]
    elif row["id"] == "E08":
        row["input"] = {"server":"filesystem", "tool":"read_text_file", "arguments":{"path":"/shared/public/company-intro.md"}}
        row["steps"] = ["실제 filesystem 정상 기준선 확인", "전용 요청/격리 환경의 실제 OPA 통신에 Toxiproxy 장애·timeout 주입",
                         "P-CONTROL-FAIL-CLOSED와 filesystem 도구 수신0을 대조", "전용 toxic 제거 후 정상군 복구"]
        row["cleanup"] = ["시험용 Toxiproxy toxic·전용 경로만 복구; 공유 OPA/기존 업무 서비스 중단 금지"]
    elif row["id"] == "E10":
        row["readiness"] = "real_gitea_repo_and_toxiproxy_needed"
        row["input"] = {"server":"gitea-test", "tool":"issue_write",
                        "arguments_template":{"method":"create", "owner":"test-owner", "repo":"test-repo",
                                              "title":"E10-unique-run-id", "body":"public synthetic test data"},
                        "schema_confirmation_required":True}
        row["prerequisites"] += ["실제1.7.0 tools/list로 issue_write 입력 필드 확인; 전용 쓰기 권한·공개 시험 repo 승인",
                                  "Toxiproxy 지연으로 첫 실제 쓰기와 두 번째 동일 요청을 겹치게 함"]
        row["steps"] = ["실제 하네스의 첫 issue 생성 호출", "첫 완료 전 같은 principal·정규 인자의 protocol 호출",
                         "첫 Allow·중복 P-RATE-003과 독립 도구 접속 횟수/생성 issue1개 확인",
                         "쓰기 자동 재시도 금지; 접속 증거가 없으면 효과1만으로 실행1 주장 금지"]
        row["expected"]["effect"] = "실제 도구 수신1과 전용 repo의 비멱등 issue 생성1; 각각 독립 확인"
        row["cleanup"] = ["만든 시험 issue·toxic·전용 repo 관계만 정리; 원장/예약 수동 삭제 금지"]
    elif row["id"] == "E11":
        row["input"] = {"server":"gitea-test", "tool":"list_my_repos", "arguments":{}}
        row["prerequisites"] += ["공식 Gitea MCP·전용 계정/repo/PAT·이용 관계·provider access evidence 준비"]
    elif row["id"] == "E13":
        row["input"] = {"cases":["direct_stdio","loopback_ipv4","loopback_ipv6","unmanaged_control"],
                        "package":"@modelcontextprotocol/server-filesystem@2026.8.31",
                        "tools":["read_text_file","write_file"], "data":"public synthetic marker in disposable directory",
                        "http_bridge":"mcp-proxy==0.12.0", "managed_launcher_required":True,
                        "expected_gateway_tool_ledger":False}
        row["prerequisites"] += ["공식 filesystem 실제 고정 배포판을 일반 계정 대조군에 설치·hash 확인; 자체 MCP 작성 금지",
                                  "localhost는 공식 mcp-proxy 뒤 같은 실제 filesystem을 사용"]
    # Preserve historical plan in Git; remove superseded mock wording from active records.
    for key in ("summary",):
        row[key] = row[key].replace("mock", "실제 OSS MCP")
    for key in ("steps", "cleanup", "prerequisites", "evidence"):
        row[key] = [p.replace("mock", "실제 OSS MCP") for p in row[key]]
    page = ROOT / row["path"]
    md = [f"# {row['id']} — {row['title']}", "", "2026-10-13 실제 상용/OSS MCP만 사용하는 계획으로 정정. **미실행**.", "",
          f"대상 ID: `{row['target_id']}` · [실제 대상](../analysis/mcp-candidates.json) · [사전 조건](preflight.md)", "",
          row["summary"], "", "자체 제작/mock MCP를 사용하지 않는다. 합성 입력 데이터·계정·파일은 실제 OSS/상용 서버에서 사용한다.", "",
          "## 사전 조건", "", *["- "+p for p in row["prerequisites"]], "", "## 입력", "", "```json",
          json.dumps(row["input"],ensure_ascii=False,indent=2), "```", "", "입력은 설계 데이터다. arguments_template는 실제 고정 tools/list로 확정해야 하며 바로 실행할 수 있는 계약이 아니다.", "",
          "## 절차", "", *[f"{i}. {p}" for i,p in enumerate(row["steps"],1)], "", "## 기대 결과", "", "```json",
          json.dumps(row["expected"],ensure_ascii=False,indent=2), "```", "",
          "정확한 policy_id·attempted/executed·응답 상태와 독립 수신/효과를 대조한다. 다른 이유의 차단·provider 오류·증거 부재는 통과가 아니다.", "",
          "## 증거", "", *["- "+p for p in row["evidence"]], "", "## 원복", "", *["- "+p for p in row["cleanup"]], "",
          "## 코드 출발점", "", *[f"- [{p}](../../../{p})" for p in row["source_paths"]], "",
          "## 결과", "", "미실행. 실제 판본·하네스·모델·시각·IDs·원본 hash·정상/음성 결과·원복을 runs에 기록한 뒤 상태를 변경한다."]
    if row["id"] == "E13":
        md += ["", "Gateway 밖의 OS 거부에 Gateway policy_id를 만들지 않는다. 일반 계정 대조군 성공은 관리형 성공이 아니다. 모델/CLI 미시도는 OS 차단 증거가 아니다. 설치된 profile·UID·IPv4/IPv6 규칙·collector와 독립 수신0을 확인하며 비지원 Desktop/in-process/admin 범위는 별도다."]
    page.write_text("\n".join(md)+"\n",encoding="utf-8")
payload=json.dumps(rows,ensure_ascii=False,indent=2)+"\n"
file.write_text(payload,encoding="utf-8")
(ROOT/"experiments/fixtures/cases.json").write_text(payload,encoding="utf-8")
print("Corrected 13 unexecuted plans to actual commercial/OSS MCPs")
