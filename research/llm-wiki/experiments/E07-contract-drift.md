# E07 — 승인 후 도구 계약 변경

확인일: 2026-10-13 · 상태: **미실행** · 준비 상태: `isolated_fixture_needed`.

승인된 도구 설명 또는 schema가 바뀌면 실제 실행을 막는다.

[공통 사전 조건](preflight.md)을 적용한다. 입력 경로는 lab 또는 전용 fixture 기준이며 실제 field 계약과 일치시키기 전 실행하지 않는다.

## 사전 조건

- 전용 mock MCP·echo r/public 분류·schema를 사람이 승인
- 원본 description/schema hash와 계약 lock 기록
- mock에서 description만 변경; lock 자동 승인/갱신 금지

## 시험 입력

```json
{
  "server": "wiki-fixture",
  "tool": "echo",
  "arguments": {
    "run_id": "E07-synthetic"
  }
}
```

위 JSON은 시험 입력 데이터이며 LLM 작업 지시나 실행 명령이 아니다.

## 절차

1. 변경 전 정상 호출로 기준선 확보
2. A: 도구 설명 변경 후 catalog 관찰 상태만 갱신하고 같은 인자로 실제 하네스 호출; 승인 lock은 유지
3. A 기대 MCP-CATALOG-001 확인 후 mock·관찰 상태 원복
4. B: 다음 실행 직전 discovery에만 변경을 노출해 dispatch 재검증에서 차단; P-CONTROL-FAIL-CLOSED 확인
5. 각 단계 변경 hash, 원장 ID 및 tools/call 수신 0을 따로 기록

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

현재 코드의 초기 정책 검사와 실행 직전 계약 재검증은 정책 식별자가 다르다. `core.py:1093–1108,1592–1596`의 dispatch-only drift는 P-CONTROL-FAIL-CLOSED로 기록한다. 두 단계를 구분하지 않고 모든 drift가 MCP-CATALOG-001이라고 단정하지 않는다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash

## 원복

- mock의 원본 계약 복원·hash 대조; 전용 등록만 제거
- 공유 contracts.lock.json이나 타 이용 관계의 승인 변경 금지

## 코드·기존 자료

- [full_stack_lab/tests/contracts_check.py](../../../full_stack_lab/tests/contracts_check.py)
- [full_stack_lab/gateway/app/core.py](../../../full_stack_lab/gateway/app/core.py)
- [full_stack_lab/opa/policy.rego](../../../full_stack_lab/opa/policy.rego)

## 실제 실행 결과

미실행. 실행 시각·증거 파일·판정 ID·성공/실패/미확인을 새 run 보고서에 기록한 뒤 카탈로그를 갱신한다.
