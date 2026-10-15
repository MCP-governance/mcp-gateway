# E02 — 개인정보 결과 마스킹

2026-10-13 실제 상용/OSS MCP만 사용하는 계획으로 정정. **미실행**.

대상 ID: `MCP-FILESYSTEM` · [실제 대상](../analysis/mcp-candidates.json) · [사전 조건](preflight.md)

허용된 중요정보 읽기 결과에서 합성 개인정보가 하네스에 노출되지 않는지 확인한다.

자체 제작/mock MCP를 사용하지 않는다. 합성 입력 데이터·계정·파일은 실제 OSS/상용 서버에서 사용한다.

## 사전 조건

- employee important r 권한과 승인된 fixture
- fresh 주체로 volume/chain/anomaly 정책이 먼저 적용되지 않음
- Presidio 실제 활성·건강 상태 확인; fixture의 개인정보 위치 기록
- 실제 공개 OSS/상용 MCP의 판본·라이선스·tools/list·승인 계약 고정
- 독립 수신/효과 증거와 정상/음성/경계·원복 조건을 기록; 미확인은 통과 금지

## 입력

```json
{
  "server": "filesystem",
  "tool": "read_text_file",
  "arguments": {
    "path": "/shared/confidential/customers/customer-pii-sample.csv"
  }
}
```

입력은 설계 데이터다. arguments_template는 실제 고정 tools/list로 확정해야 하며 바로 실행할 수 있는 계약이 아니다.

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

정확한 policy_id·attempted/executed·응답 상태와 독립 수신/효과를 대조한다. 다른 이유의 차단·provider 오류·증거 부재는 통과가 아니다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash
- 실제 서버 package/image digest·provider 판본 및 독립 접속/효과 로그

## 원복

- 읽기 전용; 시험 fixture만 제거

## 코드 출발점

- [full_stack_lab/tests/plane_cases_lab.json](../../../full_stack_lab/tests/plane_cases_lab.json)
- [full_stack_lab/gateway/app/core.py](../../../full_stack_lab/gateway/app/core.py)
- [full_stack_lab/opa/policy.rego](../../../full_stack_lab/opa/policy.rego)

## 결과

미실행. 실제 판본·하네스·모델·시각·IDs·원본 hash·정상/음성 결과·원복을 runs에 기록한 뒤 상태를 변경한다.
