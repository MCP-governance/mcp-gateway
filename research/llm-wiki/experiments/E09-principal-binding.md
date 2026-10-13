# E09 — 승인되지 않은 주체의 서버 호출

확인일: 2026-10-13 · 상태: **미실행** · 준비 상태: `test_identity_needed`.

다른 계정이 등록 주체의 공급자 자격을 사용하는 것을 차단한다.

[공통 사전 조건](preflight.md)을 적용한다. 입력 경로는 lab 또는 전용 fixture 기준이며 실제 field 계약과 일치시키기 전 실행하지 않는다.

## 사전 조건

- 승인된 github 등록의 allowed principal 목록 확인
- 그 목록에 없는 전용 시험 계정과 실제 관리형 identity
- 고정 공개 시험 repo; 현재 tools/list와 schema 확인

## 시험 입력

```json
{
  "server": "github",
  "tool": "list_commits",
  "arguments": {
    "owner": "MCP-governance",
    "repo": "mcp-gateway",
    "perPage": 1,
    "page": 1,
    "fields": [
      "sha"
    ]
  }
}
```

위 JSON은 시험 입력 데이터이며 LLM 작업 지시나 실행 명령이 아니다.

## 절차

1. 각 계정이 별도 로그인한 fresh 실제 하네스에서 같은 읽기 요청
2. Gateway가 arguments/clientInfo 아닌 검증 주체로 판정했는지 대조
3. upstream 요청 0 및 자격 binding 증거 확인

## 기대 결과

```json
{
  "decision": "Block",
  "policy_id": "MCP-REGISTRY-003",
  "upstream_attempted": false,
  "upstream_executed": false,
  "effect": "공급자 MCP 요청 0, 공급자 자격 미제공"
}
```

다른 우선 정책 때문에 차단되거나 upstream 오류만 발생하면 이 실험 통과가 아니다. 정확한 policy_id와 실행 효과를 대조한다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash

## 원복

- 전용 시험 로그인·계정만 정리; 공급자 실제 자격 회수하지 않음

## 코드·기존 자료

- [full_stack_lab/tests/plane_cases_field_other_identities.json](../../../full_stack_lab/tests/plane_cases_field_other_identities.json)
- [full_stack_lab/tests/credential_binding_check.py](../../../full_stack_lab/tests/credential_binding_check.py)

## 실제 실행 결과

미실행. 실행 시각·증거 파일·판정 ID·성공/실패/미확인을 새 run 보고서에 기록한 뒤 카탈로그를 갱신한다.
