# E06 — 승인 입력 스키마 위반

확인일: 2026-10-13 · 상태: **미실행** · 준비 상태: `input_ready`.

필수 path가 없는 인자를 transport 시험으로 보내 schema gate를 확인한다.

[공통 사전 조건](preflight.md)을 적용한다. 입력 경로는 lab 또는 전용 fixture 기준이며 실제 field 계약과 일치시키기 전 실행하지 않는다.

## 사전 조건

- 현재 승인 schema에서 path 필수 확인
- 실제 관리형 identity와 같은 endpoint에 연결한 프로토콜 시험
- 모델이 인자를 보정할 수 있어 이 카드는 protocol 시험으로 구분

## 시험 입력

```json
{
  "server": "filesystem",
  "tool": "read_text_file",
  "arguments": {}
}
```

위 JSON은 시험 입력 데이터이며 LLM 작업 지시나 실행 명령이 아니다.

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

다른 우선 정책 때문에 차단되거나 upstream 오류만 발생하면 이 실험 통과가 아니다. 정확한 policy_id와 실행 효과를 대조한다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash

## 원복

- 상태 변경 없음

## 코드·기존 자료

- [full_stack_lab/gateway/app/core.py](../../../full_stack_lab/gateway/app/core.py)
- [full_stack_lab/tests/contracts_check.py](../../../full_stack_lab/tests/contracts_check.py)

## 실제 실행 결과

미실행. 실행 시각·증거 파일·판정 ID·성공/실패/미확인을 새 run 보고서에 기록한 뒤 카탈로그를 갱신한다.
