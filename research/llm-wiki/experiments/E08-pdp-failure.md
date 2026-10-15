# E08 — 정책 엔진 실패 시 기본 차단

2026-10-13 실제 상용/OSS MCP만 사용하는 계획으로 정정. **미실행**.

대상 ID: `MCP-FILESYSTEM` · [실제 대상](../analysis/mcp-candidates.json) · [사전 조건](preflight.md)

timeout·비정상 JSON에서 정책 판정을 우회하지 않는다.

자체 제작/mock MCP를 사용하지 않는다. 합성 입력 데이터·계정·파일은 실제 OSS/상용 서버에서 사용한다.

## 사전 조건

- 솔루션 기기의 격리 시험 Gateway/PDP 경로 준비
- 정상 echo r/public 계약·권한; production OPA 정지 금지
- PDP timeout 또는 비정상 JSON을 test-only 경로에만 주입
- 실제 공개 OSS/상용 MCP의 판본·라이선스·tools/list·승인 계약 고정
- 독립 수신/효과 증거와 정상/음성/경계·원복 조건을 기록; 미확인은 통과 금지

## 입력

```json
{
  "server": "filesystem",
  "tool": "read_text_file",
  "arguments": {
    "path": "/shared/public/company-intro.md"
  }
}
```

입력은 설계 데이터다. arguments_template는 실제 고정 tools/list로 확정해야 하며 바로 실행할 수 있는 계약이 아니다.

## 절차

1. 실제 filesystem 정상 기준선 확인
2. 전용 요청/격리 환경의 실제 OPA 통신에 Toxiproxy 장애·timeout 주입
3. P-CONTROL-FAIL-CLOSED와 filesystem 도구 수신0을 대조
4. 전용 toxic 제거 후 정상군 복구

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

정확한 policy_id·attempted/executed·응답 상태와 독립 수신/효과를 대조한다. 다른 이유의 차단·provider 오류·증거 부재는 통과가 아니다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash
- 실제 서버 package/image digest·provider 판본 및 독립 접속/효과 로그

## 원복

- 시험용 Toxiproxy toxic·전용 경로만 복구; 공유 OPA/기존 업무 서비스 중단 금지

## 코드 출발점

- [full_stack_lab/gateway/app/core.py](../../../full_stack_lab/gateway/app/core.py)
- [full_stack_lab/opa/policy_test.rego](../../../full_stack_lab/opa/policy_test.rego)

## 결과

미실행. 실제 판본·하네스·모델·시각·IDs·원본 hash·정상/음성 결과·원복을 runs에 기록한 뒤 상태를 변경한다.
