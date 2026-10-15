# E07 — 승인 후 도구 계약 변경

2026-10-13 실제 상용/OSS MCP만 사용하는 계획으로 정정. **미실행**.

대상 ID: `MCP-GITHUB-LOCAL` · [실제 대상](../analysis/mcp-candidates.json) · [사전 조건](preflight.md)

승인된 도구 설명 또는 schema가 바뀌면 실제 실행을 막는다.

자체 제작/mock MCP를 사용하지 않는다. 합성 입력 데이터·계정·파일은 실제 OSS/상용 서버에서 사용한다.

## 사전 조건

- 원본 description/schema hash와 계약 lock 기록
- 실제 공개 OSS/상용 MCP의 판본·라이선스·tools/list·승인 계약 고정
- 독립 수신/효과 증거와 정상/음성/경계·원복 조건을 기록; 미확인은 통과 금지
- 공식 GitHub MCP의 전용 자기 소유 시험 repo/인스턴스·read-only toolsets
- 공식 toolset/description override 설정으로 A→B→A 변경; MCP 소스 수정 금지

## 입력

```json
{
  "server": "github-contract-test",
  "tool": "list_commits",
  "arguments": {
    "owner": "test-owner",
    "repo": "test-repo",
    "perPage": 1
  }
}
```

입력은 설계 데이터다. arguments_template는 실제 고정 tools/list로 확정해야 하며 바로 실행할 수 있는 계약이 아니다.

## 절차

1. repos toolset 정상군과 승인 hash를 기록
2. 공식 toolset repos→issues 또는 description override로 계약 변경; lock 유지
3. catalog refresh 전/후 실제 하네스 호출을 나눠 각 policy_id·도구 미수신 확인
4. A 설정으로 복귀 후 최신 관찰·재승인 내용 A 확인; 시험 인스턴스만 복구

## 기대 결과

```json
{
  "catalog_refreshed_before_policy": {
    "decision": "Block",
    "policy_id": "MCP-CATALOG-001",
    "upstream_attempted": false,
    "upstream_executed": false
  },
  "drift_detected_only_at_dispatch": {
    "decision": "Block",
    "policy_id": "P-CONTROL-FAIL-CLOSED",
    "upstream_attempted": false,
    "upstream_executed": false
  },
  "effect": "tools/list 재관찰은 가능하나 tools/call 실행 수신 0"
}
```

정확한 policy_id·attempted/executed·응답 상태와 독립 수신/효과를 대조한다. 다른 이유의 차단·provider 오류·증거 부재는 통과가 아니다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash
- catalog 사전 관찰과 dispatch 시점 재관찰을 구분한 시각·DB observed hash·승인 hash
- 실제 서버 package/image digest·provider 판본 및 독립 접속/효과 로그

## 원복

- 공식 서버의 원래 toolset/override 설정과 hash 복원; 전용 등록만 정리

## 코드 출발점

- [full_stack_lab/tests/contracts_check.py](../../../full_stack_lab/tests/contracts_check.py)
- [full_stack_lab/gateway/app/core.py](../../../full_stack_lab/gateway/app/core.py)
- [full_stack_lab/opa/policy.rego](../../../full_stack_lab/opa/policy.rego)

## 결과

미실행. 실제 판본·하네스·모델·시각·IDs·원본 hash·정상/음성 결과·원복을 runs에 기록한 뒤 상태를 변경한다.
