# E13 — PJ1 로컬 stdio·loopback 우회

2026-10-13 실제 상용/OSS MCP만 사용하는 계획으로 정정. **미실행**.

대상 ID: `MCP-FILESYSTEM` · [실제 대상](../analysis/mcp-candidates.json) · [사전 조건](preflight.md)

Gateway 뒤 자체 운영 MCP와 PJ1 직접 로컬 실행을 구분하고 관리형 OS 경계의 거부·독립 효과를 검증한다.

자체 제작/mock MCP를 사용하지 않는다. 합성 입력 데이터·계정·파일은 실제 OSS/상용 서버에서 사용한다.

## 사전 조건

- PJ1의 fresh 실제 관리형 launcher·UID·AppArmor profile·설정 hash·active heartbeat 확인
- 다운로드 없는 고정 stdio marker fixture와 IPv4/IPv6 localhost HTTP fixture 준비
- 일반 계정 대조군에서 실제 수신·marker 효과를 먼저 확인
- 시험 identity 또는 기존 작업과 충돌하지 않는 전용 세션; root/admin 침해는 범위 밖
- 실제 공개 OSS/상용 MCP의 판본·라이선스·tools/list·승인 계약 고정
- 독립 수신/효과 증거와 정상/음성/경계·원복 조건을 기록; 미확인은 통과 금지
- 공식 filesystem 실제 고정 배포판을 일반 계정 대조군에 설치·hash 확인; 자체 MCP 작성 금지
- localhost는 공식 mcp-proxy 뒤 같은 실제 filesystem을 사용

## 입력

```json
{
  "cases": [
    "direct_stdio",
    "loopback_ipv4",
    "loopback_ipv6",
    "unmanaged_control"
  ],
  "package": "@modelcontextprotocol/server-filesystem@2026.8.31",
  "tools": [
    "read_text_file",
    "write_file"
  ],
  "data": "public synthetic marker in disposable directory",
  "http_bridge": "mcp-proxy==0.12.0",
  "managed_launcher_required": true,
  "expected_gateway_tool_ledger": false
}
```

입력은 설계 데이터다. arguments_template는 실제 고정 tools/list로 확정해야 하며 바로 실행할 수 있는 계약이 아니다.

## 절차

1. 일반 계정 대조군의 정상 protocol·파일 효과를 기록하고 fixture 초기화
2. 관리형 하네스에서 비승인 stdio 설정·직접 실행·별도 interpreter·localhost 접속을 실제 시도
3. UID/PID/profile의 거부 증거와 fixture 수신·파일 효과를 대조; 도구 미시도는 미확인
4. 승인 Gateway 경로의 정상 읽기 성공을 확인하고 전용 fixture만 finally 정리

## 기대 결과

```json
{
  "managed_direct_stdio": {
    "enforcement_plane": "endpoint",
    "denied": true,
    "tool_effect_count": 0
  },
  "managed_loopback": {
    "ipv4_denied": true,
    "ipv6_denied": true,
    "receiver_request_count": 0
  },
  "unmanaged_control": {
    "fixture_works": true,
    "scope": "control_only"
  },
  "approved_gateway_control": {
    "decision": "Allow",
    "policy_id": "P-AUTHZ-ALLOW-001",
    "upstream_attempted": true,
    "upstream_executed": true
  },
  "effect": "실제 시도·엔드포인트 거부·독립 수신 및 파일 효과 대조; Gateway 밖 거부에 policy_id를 만들지 않음"
}
```

정확한 policy_id·attempted/executed·응답 상태와 독립 수신/효과를 대조한다. 다른 이유의 차단·provider 오류·증거 부재는 통과가 아니다.

## 증거

- fresh 관리 하네스 버전·실제 도구 시도·설치 실행 파일 hash·UID/PID/profile
- 엔드포인트 OS 거부 이벤트·collector 마지막 성공/실패와 시험 시각 상관관계
- stdio/localhost fixture의 독립 수신 로그·marker 전후 상태
- 승인 Gateway 정상 대조군의 request/trace·policy_id·attempted/executed 및 원복 결과
- 실제 서버 package/image digest·provider 판본 및 독립 접속/효과 로그

## 원복

- finally로 새 fixture·marker·시험 설정만 제거; 보호 서비스·기존 승인 계약·append-only 원장 유지

## 코드 출발점

- [endpoint-agent/enforce-linux.py](../../../endpoint-agent/enforce-linux.py)
- [endpoint-agent/managed-linux.py](../../../endpoint-agent/managed-linux.py)
- [full_stack_lab/tests/managed_kernel_proof.py](../../../full_stack_lab/tests/managed_kernel_proof.py)
- [full_stack_lab/mcp/run-server.sh](../../../full_stack_lab/mcp/run-server.sh)

## 결과

미실행. 실제 판본·하네스·모델·시각·IDs·원본 hash·정상/음성 결과·원복을 runs에 기록한 뒤 상태를 변경한다.

Gateway 밖의 OS 거부에 Gateway policy_id를 만들지 않는다. 일반 계정 대조군 성공은 관리형 성공이 아니다. 모델/CLI 미시도는 OS 차단 증거가 아니다. 설치된 profile·UID·IPv4/IPv6 규칙·collector와 독립 수신0을 확인하며 비지원 Desktop/in-process/admin 범위는 별도다.
