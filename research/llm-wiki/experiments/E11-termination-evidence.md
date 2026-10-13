# E11 — 종료 즉시 차단 및 회수 상태 증거

확인일: 2026-10-13 · 상태: **미실행** · 준비 상태: `disposable_relationship_needed`.

이용 관계 종료부터 actual target 상태까지 C1~C4와 최소 등급을 확인한다.

[공통 사전 조건](preflight.md)을 적용한다. 입력 경로는 lab 또는 전용 fixture 기준이며 실제 field 계약과 일치시키기 전 실행하지 않는다.

## 사전 조건

- 전용 이용 관계와 시험 token·managed config target 등록
- 서버·endpoint·provider-held credential 회수 대상 목록 작성
- 다른 사용자의 종료 케이스·자격을 건드리지 않음

## 시험 입력

```json
{
  "server": "wiki-fixture",
  "tool": "echo",
  "arguments": {
    "run_id": "E11-synthetic"
  }
}
```

위 JSON은 시험 입력 데이터이며 LLM 작업 지시나 실행 명령이 아니다.

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

다른 우선 정책 때문에 차단되거나 upstream 오류만 발생하면 이 실험 통과가 아니다. 정확한 policy_id와 실행 효과를 대조한다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash

## 원복

- finally로 본인 시험 서버·관계·자격만 복구
- 공유 UR-GITEA-DEV/UR-EMAIL-ASSIST에 기존 termination_flow 전체 실행 금지

## 코드·기존 자료

- [full_stack_lab/tests/termination_flow.py](../../../full_stack_lab/tests/termination_flow.py)
- [docs/ai/TERMINATION_MODEL.md](../../../docs/ai/TERMINATION_MODEL.md)
- [full_stack_lab/opa/policy.rego](../../../full_stack_lab/opa/policy.rego)

## 실제 실행 결과

미실행. 실행 시각·증거 파일·판정 ID·성공/실패/미확인을 새 run 보고서에 기록한 뒤 카탈로그를 갱신한다.
