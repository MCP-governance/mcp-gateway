# E10 — 동시 중복 호출 억제

2026-10-13 실제 상용/OSS MCP만 사용하는 계획으로 정정. **미실행**.

대상 ID: `MCP-GITEA` · [실제 대상](../analysis/mcp-candidates.json) · [사전 조건](preflight.md)

첫 호출이 실행 중인 동안 동일 호출의 두 번째 부수효과를 차단한다.

자체 제작/mock MCP를 사용하지 않는다. 합성 입력 데이터·계정·파일은 실제 OSS/상용 서버에서 사용한다.

## 사전 조건

- 동일 검증 principal·서버·도구·인자, 일반 rate/concurrency 상한 미도달
- 두 호출이 겹쳤음을 시각·reservation으로 증명
- 실제 공개 OSS/상용 MCP의 판본·라이선스·tools/list·승인 계약 고정
- 독립 수신/효과 증거와 정상/음성/경계·원복 조건을 기록; 미확인은 통과 금지
- 실제1.7.0 tools/list로 issue_write 입력 필드 확인; 전용 쓰기 권한·공개 시험 repo 승인
- 고정 Gitea1.7.0 source issue_write 정의는 확인했으나 실제 tools/list·서버 인자·승인 hash를 별도 확정
- 전용 proxy와 run UUID를 사용해 latency upstream1000ms/jitter0/toxicity1로 준비; source/destination/원래 설정을 보존
- pilot에서 첫 reservation 활성 뒤 중복 요청이 도착하고 첫 정상 호출이 timeout 없이 완료됨을 확인; 겹침 실패·초기화 오류는 시험 부적합

## 입력

```json
{
  "server": "gitea-test",
  "tool": "issue_write",
  "arguments_template": {
    "method": "create",
    "owner": "test-owner",
    "repo": "test-repo",
    "title": "E10-unique-run-id",
    "body": "public synthetic test data"
  },
  "schema_confirmation_required": true
}
```

입력은 설계 데이터다. arguments_template는 실제 고정 tools/list로 확정해야 하며 바로 실행할 수 있는 계약이 아니다.

## 제어된 통신 지연

전용 경로에 Toxiproxy latency를 **upstream1000ms · jitter0 · toxicity1**로 적용한다. 기본 downstream 지연은 응답 방향만 늦추므로 그대로 복제하지 않는다. 한 쌍의 호출에만 적용하고 unique run UUID/proxy/toxic 이름·전후 설정·추가/제거 시각을 기록한다. 초기화/도구 발견에도 지연이 적용될 수 있어 pilot에서 timeout·다른 정책 없이 첫 정상군과 reservation 겹침을 먼저 확인한다. 내부 handler가 동시에 실행됐다고 추정하지 않는다.

## 절차

1. 무장애 정상군에서 같은 실제 Gitea 도구·principal·repo의 성공/수신/issue 효과를 확인하고 전용 시험 효과만 정리
2. Toxiproxy upstream latency를 한 쌍의 run 동안 적용하고 실제 하네스의 첫 issue 생성 요청·reservation·도구 전송 시각을 포착
3. 첫 reservation 활성 상태에서 같은 principal·서버·도구·정규 인자의 두 번째 protocol 요청을 한 번 보내고 시각·IDs를 기록
4. 첫 Allow/P-AUTHZ-ALLOW-001과 두 번째 Block/P-RATE-003, 독립 MCP 수신 기록과 Gitea API/UUID issue 생성1을 각각 대조
5. 효과1이 실행1을 증명한다고 가정하지 않음; MCP 수신 증거가 없거나 다른 정책/timeout이 개입하면 미확인/실패로 기록
6. 쓰기 자동 재시도 없이 finally 원복하고 toxic/proxy·시험 issue 상태와 정상 읽기 대조군 복구를 확인

## 기대 결과

```json
{
  "first": {
    "decision": "Allow",
    "policy_id": "P-AUTHZ-ALLOW-001",
    "upstream_attempted": true,
    "upstream_executed": true
  },
  "second": {
    "decision": "Block",
    "policy_id": "P-RATE-003",
    "upstream_attempted": false,
    "upstream_executed": false
  },
  "effect": "실제 도구 수신1과 전용 repo의 비멱등 issue 생성1; 각각 독립 확인"
}
```

정확한 policy_id·attempted/executed·응답 상태와 독립 수신/효과를 대조한다. 다른 이유의 차단·provider 오류·증거 부재는 통과가 아니다.

## 증거

- fresh 하네스의 원본 tool-call 이벤트와 모델·하네스 버전
- Gateway decision ID와 request/trace ID, policy_id, principal
- upstream_attempted/upstream_executed 및 upstream 수신 로그
- 부수효과 전후 비교와 원복 결과, 비밀 제거한 파일 hash
- 실제 서버 package/image digest·provider 판본 및 독립 접속/효과 로그
- Toxiproxy version/image digest·proxy/toxic JSON 전후·방향·latency/jitter/toxicity·추가/제거 시각
- 동일 request fingerprint와 첫 reservation 활성/둘째 도착의 겹침 증거; MCP 수신·Gitea HTTP 쓰기·issue UUID는 별도 계수
- source 정의의 입력 필드 확인과 실제 tools/list·계약 hash의 별도 캡처; 원복 뒤 정상군

## 원복

- finally에서 run UUID로 만든 자기 proxy/toxic만 제거하고 원래 endpoint·설정·원래 연결 품질 확인
- 이번 run에서 생성한 자기 issue만 닫거나 전용 repo의 승인된 정리 절차 수행; 공유 repo/기존 issue/계정 건드리지 않음
- 원장/예약 수동 삭제와 쓰기 자동 재시도 금지; 첫 결과가 불명확하면 효과를 독립 조회하고 uncertain 상태로 보존

## 코드 출발점

- [full_stack_lab/opa/policy.rego](../../../full_stack_lab/opa/policy.rego)
- [full_stack_lab/gateway/app/core.py](../../../full_stack_lab/gateway/app/core.py)
- [full_stack_lab/tests/plane_cases_lab.json](../../../full_stack_lab/tests/plane_cases_lab.json)

## 결과

미실행. 실제 판본·하네스·모델·시각·IDs·원본 hash·정상/음성 결과·원복을 runs에 기록한 뒤 상태를 변경한다.

## 고정 소스 확인

[Gitea issue_write 소스](../analysis/evidence/packages/gitea-1.7.0/issue.go.raw.txt)의 정의66~85·분기120~127·생성216~259를 읽었다. 입력 template의 method=create/owner/repo/title/body와 일치한다. 이 정적 확인은 실제 tools/list·승인 계약·실행 성공을 대체하지 않는다. [Toxiproxy 근거](../analysis/evidence/packages/toxiproxy-reviewed-source/README.raw.txt)의 방향·timeout 조건과 [정본 JSON](fixtures/cases.json)에 제어 조건을 함께 보존했다.
