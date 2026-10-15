# E11 — 종료 즉시 차단 및 회수 상태 증거

2026-10-13 실제 상용/OSS MCP만 사용하는 계획으로 정정. **미실행**.

대상 ID: `MCP-GITEA` · [실제 대상](../analysis/mcp-candidates.json) · [사전 조건](preflight.md)

이용 관계 종료부터 actual target 상태까지 C1~C4와 최소 등급을 확인한다.

자체 제작/mock MCP를 사용하지 않는다. 합성 입력 데이터·계정·파일은 실제 OSS/상용 서버에서 사용한다.

## 사전 조건

- 전용 이용 관계와 시험 token·managed config target 등록
- 서버·endpoint·provider-held credential 회수 대상 목록 작성
- 다른 사용자의 종료 케이스·자격을 건드리지 않음
- 실제 공개 OSS/상용 MCP의 판본·라이선스·tools/list·승인 계약 고정
- 독립 수신/효과 증거와 정상/음성/경계·원복 조건을 기록; 미확인은 통과 금지
- 공식 Gitea MCP·전용 계정/repo/PAT·이용 관계·provider access evidence 준비

## 입력

```json
{
  "server": "gitea-test",
  "tool": "list_my_repos",
  "arguments": {}
}
```

입력은 설계 데이터다. arguments_template는 실제 고정 tools/list로 확정해야 하며 바로 실행할 수 있는 계약이 아니다.

## 절차

1. 정상 기준선 후 전용 관계 종료 케이스 생성
2. 회수 전 즉시 도구 호출 차단 확인
3. 삭제 API 응답만 제출한 상태와 실제 token 거부·설정 잔존 제거 후 상태를 각각 assess
4. C1~C4 target별 충족과 전체 최소 등급·report 대조

## 기대 결과

```json
{
  "decision": "Block",
  "policy_id": "MCP-DECOMM-001",
  "upstream_attempted": false,
  "upstream_executed": false,
  "effect": "종료 케이스 시작 직후 도구 실행 0; 부족한 target 상태 증거로 T1 금지"
}
```

정확한 policy_id·attempted/executed·응답 상태와 독립 수신/효과를 대조한다. 다른 이유의 차단·provider 오류·증거 부재는 통과가 아니다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash
- 실제 서버 package/image digest·provider 판본 및 독립 접속/효과 로그

## 원복

- finally로 본인 시험 서버·관계·자격만 복구
- 공유 UR-GITEA-DEV/UR-EMAIL-ASSIST에 기존 termination_flow 전체 실행 금지

## 코드 출발점

- [full_stack_lab/tests/termination_flow.py](../../../full_stack_lab/tests/termination_flow.py)
- [docs/ai/TERMINATION_MODEL.md](../../../docs/ai/TERMINATION_MODEL.md)
- [full_stack_lab/opa/policy.rego](../../../full_stack_lab/opa/policy.rego)

## 결과

미실행. 실제 판본·하네스·모델·시각·IDs·원본 hash·정상/음성 결과·원복을 runs에 기록한 뒤 상태를 변경한다.
