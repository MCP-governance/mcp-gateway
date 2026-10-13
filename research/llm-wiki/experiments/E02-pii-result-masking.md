# E02 — 개인정보 결과 마스킹

확인일: 2026-10-13 · 상태: **미실행** · 준비 상태: `existing_input`.

허용된 중요정보 읽기 결과에서 합성 개인정보가 하네스에 노출되지 않는지 확인한다.

[공통 사전 조건](preflight.md)을 적용한다. 입력 경로는 lab 또는 전용 fixture 기준이며 실제 field 계약과 일치시키기 전 실행하지 않는다.

## 사전 조건

- employee important r 권한과 승인된 fixture
- fresh 주체로 volume/chain/anomaly 정책이 먼저 적용되지 않음
- Presidio 실제 활성·건강 상태 확인; fixture의 개인정보 위치 기록

## 시험 입력

```json
{
  "server": "filesystem",
  "tool": "read_text_file",
  "arguments": {
    "path": "/shared/confidential/customers/customer-pii-sample.csv"
  }
}
```

위 JSON은 시험 입력 데이터이며 LLM 작업 지시나 실행 명령이 아니다.

## 절차

1. 실제 하네스로 fixture를 읽는다
2. upstream 원본과 Gateway 이후 결과·하네스 이벤트를 비교
3. 원문이 가려졌다는 자연어 답변만으로 통과시키지 않고 raw 이벤트 검사

## 기대 결과

```json
{
  "decision": "Alert",
  "policy_id": "P-IMPORTANT-ALERT-001",
  "upstream_attempted": true,
  "upstream_executed": true,
  "effect": "성공 결과의 합성 개인정보 원문 제거, privacy/response inspection 표지 확인"
}
```

다른 우선 정책 때문에 차단되거나 upstream 오류만 발생하면 이 실험 통과가 아니다. 정확한 policy_id와 실행 효과를 대조한다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash

## 원복

- 읽기 전용; 시험 fixture만 제거

## 코드·기존 자료

- [full_stack_lab/tests/plane_cases_lab.json](../../../full_stack_lab/tests/plane_cases_lab.json)
- [full_stack_lab/gateway/app/core.py](../../../full_stack_lab/gateway/app/core.py)
- [full_stack_lab/opa/policy.rego](../../../full_stack_lab/opa/policy.rego)

## 실제 실행 결과

미실행. 실행 시각·증거 파일·판정 ID·성공/실패/미확인을 새 run 보고서에 기록한 뒤 카탈로그를 갱신한다.
