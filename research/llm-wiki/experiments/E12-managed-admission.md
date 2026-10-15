# E12 — 관리형 활성 상태와 MCP 입구

2026-10-13 실제 상용/OSS MCP만 사용하는 계획으로 정정. **미실행**.

대상 ID: `MCP-GITHUB-REMOTE` · [실제 대상](../analysis/mcp-candidates.json) · [사전 조건](preflight.md)

관리형 device token과 일반 user token, fresh heartbeat를 구분한다.

자체 제작/mock MCP를 사용하지 않는다. 합성 입력 데이터·계정·파일은 실제 OSS/상용 서버에서 사용한다.

## 사전 조건

- PJ1의 실제 설치 collector·커널 규칙·보호 설정·independent reviewer
- 첫 상태 managed_state=active, 실제 hash/checks·fresh heartbeat
- 서비스 정지 시험은 해당 전용 identity만; max heartbeat age와 JWT 만료 비교
- 실제 공개 OSS/상용 MCP의 판본·라이선스·tools/list·승인 계약 고정
- 독립 수신/효과 증거와 정상/음성/경계·원복 조건을 기록; 미확인은 통과 금지

## 입력

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

입력은 설계 데이터다. arguments_template는 실제 고정 tools/list로 확정해야 하며 바로 실행할 수 있는 계약이 아니다.

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

정확한 policy_id·attempted/executed·응답 상태와 독립 수신/효과를 대조한다. 다른 이유의 차단·provider 오류·증거 부재는 통과가 아니다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash
- 실제 서버 package/image digest·provider 판본 및 독립 접속/효과 로그

## 원복

- finally로 해당 service·원본 설정 복원 후 fresh heartbeat·입구 정상 확인
- 시험 identity만 정리; 다른 endpoint service·설정 유지

## 코드 출발점

- [full_stack_lab/tests/managed_kernel_proof.py](../../../full_stack_lab/tests/managed_kernel_proof.py)
- [full_stack_lab/tests/managed_enrollment_check.py](../../../full_stack_lab/tests/managed_enrollment_check.py)

## 결과

미실행. 실제 판본·하네스·모델·시각·IDs·원본 hash·정상/음성 결과·원복을 runs에 기록한 뒤 상태를 변경한다.
