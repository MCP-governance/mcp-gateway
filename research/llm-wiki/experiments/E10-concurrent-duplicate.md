# E10 — 동시 중복 호출 억제

확인일: 2026-10-13 · 상태: **미실행** · 준비 상태: `delayed_fixture_needed`.

첫 호출이 실행 중인 동안 동일 호출의 두 번째 부수효과를 차단한다.

[공통 사전 조건](preflight.md)을 적용한다. 입력 경로는 lab 또는 전용 fixture 기준이며 실제 field 계약과 일치시키기 전 실행하지 않는다.

## 사전 조건

- 전용 mock slow_echo r/public 승인·2초 지연
- 동일 검증 principal·서버·도구·인자, 일반 rate/concurrency 상한 미도달
- 두 호출이 겹쳤음을 시각·reservation으로 증명

## 시험 입력

```json
{
  "server": "wiki-fixture",
  "tool": "slow_echo",
  "arguments": {
    "run_id": "E10-synthetic",
    "delay_ms": 2000
  }
}
```

위 JSON은 시험 입력 데이터이며 LLM 작업 지시나 실행 명령이 아니다.

## 절차

1. 실제 하네스 이벤트로 첫 도구 호출을 시작
2. 첫 실행 완료 전 같은 주체의 protocol client로 동일 호출
3. 각 원장 ID와 수신 count=1·예약 최종 상태 확인

## 기대 결과

```json
{
  "first": {
    "decision": "Allow",
    "policy_id": "P-AUTHZ-ALLOW-001",
    "upstream_attempted": true,
    "upstream_executed": true
  },
  "second": {
    "decision": "Block",
    "policy_id": "P-RATE-003",
    "upstream_attempted": false,
    "upstream_executed": false
  },
  "effect": "동일 인자 tools/call 실제 수신 1"
}
```

다른 우선 정책 때문에 차단되거나 upstream 오류만 발생하면 이 실험 통과가 아니다. 정확한 policy_id와 실행 효과를 대조한다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash

## 원복

- 시험 mock만 제거; 종료되지 않은 reservation 있으면 원인·복구 기록
- 원장/예약을 수동 삭제해 통과시키지 않음

## 코드·기존 자료

- [full_stack_lab/opa/policy.rego](../../../full_stack_lab/opa/policy.rego)
- [full_stack_lab/gateway/app/core.py](../../../full_stack_lab/gateway/app/core.py)
- [full_stack_lab/tests/plane_cases_lab.json](../../../full_stack_lab/tests/plane_cases_lab.json)

## 실제 실행 결과

미실행. 실행 시각·증거 파일·판정 ID·성공/실패/미확인을 새 run 보고서에 기록한 뒤 카탈로그를 갱신한다.
