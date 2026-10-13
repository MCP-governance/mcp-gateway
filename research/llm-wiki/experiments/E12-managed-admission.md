# E12 — 관리형 활성 상태와 MCP 입구

확인일: 2026-10-13 · 상태: **미실행** · 준비 상태: `pj1_admin_and_test_identity_needed`.

관리형 device token과 일반 user token, fresh heartbeat를 구분한다.

[공통 사전 조건](preflight.md)을 적용한다. 입력 경로는 lab 또는 전용 fixture 기준이며 실제 field 계약과 일치시키기 전 실행하지 않는다.

## 사전 조건

- PJ1의 실제 설치 collector·커널 규칙·보호 설정·independent reviewer
- 첫 상태 managed_state=active, 실제 hash/checks·fresh heartbeat
- 서비스 정지 시험은 해당 전용 identity만; max heartbeat age와 JWT 만료 비교

## 시험 입력

```json
{
  "server": "github",
  "tool": "initialize",
  "arguments": {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": {
      "name": "wiki-managed-boundary",
      "version": "1"
    }
  }
}
```

위 JSON은 시험 입력 데이터이며 LLM 작업 지시나 실행 명령이 아니다.

## 절차

1. 기존 managed_kernel_proof의 admission 순서를 실제 기기에 적용
2. 일반 user token은 403·active device token은 initialize 200 확인
3. 해당 collector 정지 후 실제 heartbeat 만료를 기다리고 JWT 미만료 상태에서 403 확인
4. 임의 checks/heartbeat/JWT 생성으로 결과를 대체하지 않는다

## 기대 결과

```json
{
  "general_user_token": {
    "http_status": 403,
    "policy_id": "ENDPOINT-MANAGED-001",
    "upstream_attempted": false,
    "upstream_executed": false
  },
  "active_device_token": {
    "http_status": 200,
    "effect": "MCP initialize 성공; 도구 실행 증거와 별도"
  },
  "stale_heartbeat_unexpired_jwt": {
    "http_status": 403,
    "policy_id": "ENDPOINT-MANAGED-001",
    "upstream_attempted": false,
    "upstream_executed": false
  }
}
```

HTTP 입구 거부라 tools/call 원장이 생기지 않을 수 있다. HTTP 정책 응답과 세션·upstream 0을 증거로 쓴다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash

## 원복

- finally로 해당 service·원본 설정 복원 후 fresh heartbeat·입구 정상 확인
- 시험 identity만 정리; 다른 endpoint service·설정 유지

## 코드·기존 자료

- [full_stack_lab/tests/managed_kernel_proof.py](../../../full_stack_lab/tests/managed_kernel_proof.py)
- [full_stack_lab/tests/managed_enrollment_check.py](../../../full_stack_lab/tests/managed_enrollment_check.py)

## 실제 실행 결과

미실행. 실행 시각·증거 파일·판정 ID·성공/실패/미확인을 새 run 보고서에 기록한 뒤 카탈로그를 갱신한다.
