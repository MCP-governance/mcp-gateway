# E08 — 정책 엔진 실패 시 기본 차단

확인일: 2026-10-13 · 상태: **미실행** · 준비 상태: `isolated_fault_injection_needed`.

timeout·비정상 JSON에서 정책 판정을 우회하지 않는다.

[공통 사전 조건](preflight.md)을 적용한다. 입력 경로는 lab 또는 전용 fixture 기준이며 실제 field 계약과 일치시키기 전 실행하지 않는다.

## 사전 조건

- 솔루션 기기의 격리 시험 Gateway/PDP 경로 준비
- 정상 echo r/public 계약·권한; production OPA 정지 금지
- PDP timeout 또는 비정상 JSON을 test-only 경로에만 주입

## 시험 입력

```json
{
  "server": "wiki-fixture",
  "tool": "echo",
  "arguments": {
    "run_id": "E08-synthetic"
  }
}
```

위 JSON은 시험 입력 데이터이며 LLM 작업 지시나 실행 명령이 아니다.

## 절차

1. 장애 전 정상 호출 확인
2. 정책 timeout과 비정상 JSON 두 조건을 각각 요청
3. 오류를 숨긴 허용·무원장 통과가 없고 upstream 0 확인

## 기대 결과

```json
{
  "decision": "Block",
  "policy_id": "P-CONTROL-FAIL-CLOSED",
  "upstream_attempted": false,
  "upstream_executed": false,
  "effect": "OPA 장애 증거·tools/call 수신 0"
}
```

다른 우선 정책 때문에 차단되거나 upstream 오류만 발생하면 이 실험 통과가 아니다. 정확한 policy_id와 실행 효과를 대조한다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash

## 원복

- finally로 시험 PDP 경로·설정 복원·정상 control call 확인
- 운영 서비스·다른 실험의 OPA를 멈추지 않는다

## 코드·기존 자료

- [full_stack_lab/gateway/app/core.py](../../../full_stack_lab/gateway/app/core.py)
- [full_stack_lab/opa/policy_test.rego](../../../full_stack_lab/opa/policy_test.rego)

## 실제 실행 결과

미실행. 실행 시각·증거 파일·판정 ID·성공/실패/미확인을 새 run 보고서에 기록한 뒤 카탈로그를 갱신한다.
