# E06 — 승인 입력 스키마 위반

2026-10-13 실제 상용/OSS MCP만 사용하는 계획으로 정정. **미실행**.

대상 ID: `MCP-FILESYSTEM` · [실제 대상](../analysis/mcp-candidates.json) · [사전 조건](preflight.md)

필수 path가 없는 인자를 transport 시험으로 보내 schema gate를 확인한다.

자체 제작/mock MCP를 사용하지 않는다. 합성 입력 데이터·계정·파일은 실제 OSS/상용 서버에서 사용한다.

## 사전 조건

- 현재 승인 schema에서 path 필수 확인
- 실제 관리형 identity와 같은 endpoint에 연결한 프로토콜 시험
- 모델이 인자를 보정할 수 있어 이 카드는 protocol 시험으로 구분
- 실제 공개 OSS/상용 MCP의 판본·라이선스·tools/list·승인 계약 고정
- 독립 수신/효과 증거와 정상/음성/경계·원복 조건을 기록; 미확인은 통과 금지

## 입력

```json
{
  "server": "filesystem",
  "tool": "read_text_file",
  "arguments": {}
}
```

입력은 설계 데이터다. arguments_template는 실제 고정 tools/list로 확정해야 하며 바로 실행할 수 있는 계약이 아니다.

## 절차

1. Inspector/기존 protocol client로 initialize·tools/list 수행
2. tools/call read_text_file arguments={}를 전송
3. 정상 path의 control call과 오류 응답·원장을 대조

## 기대 결과

```json
{
  "decision": "Block",
  "policy_id": "P-INPUT-SCHEMA-001",
  "upstream_attempted": false,
  "upstream_executed": false,
  "effect": "schema 오류 판정, 도구 실행 0"
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

- 상태 변경 없음

## 코드 출발점

- [full_stack_lab/gateway/app/core.py](../../../full_stack_lab/gateway/app/core.py)
- [full_stack_lab/tests/contracts_check.py](../../../full_stack_lab/tests/contracts_check.py)

## 결과

미실행. 실제 판본·하네스·모델·시각·IDs·원본 hash·정상/음성 결과·원복을 runs에 기록한 뒤 상태를 변경한다.
