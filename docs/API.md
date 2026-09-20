# API 명세

개발 중인 구성요소를 합칠 때 쓰는 인터페이스 정본입니다. 기계가 읽는 명세는
`./console.sh openapi`가 코드에서 생성하는 [`docs/openapi/`](openapi/)이고, 이
문서는 **그 명세가 말하지 않는 것** — 경계, 인증 주체, 실패의 의미 — 을 적습니다.

```bash
cd full_stack_lab && ./console.sh openapi
# docs/openapi/gateway.json, docs/openapi/agent-service.json
```

---

## 0. 서비스 경계 한눈에

```
브라우저 ─┐
          ├─► Agent Service :8000 ──(사용자 JWT + 60초 Agent Assertion)──► Gateway :8080
CLI ──────┘        │                                                          │
                   └── Console 화면·세션·도입 요청·AI 코드 감사                 ├─► OPA :8181
                                                                              ├─► PostgreSQL
엔드포인트 에이전트 ─────────────(사용자 JWT)───────────────────────────────►  └─► upstream MCP
```

| 서비스 | 포트 | 무엇의 정본인가 | 브라우저 노출 |
| --- | --- | --- | --- |
| **Agent Service** | `127.0.0.1:8000` | 로그인·세션·Console 화면·도입 요청·AI 코드 감사 작업 | ○ (유일) |
| **Gateway** | `127.0.0.1:8080` | 정책 집행·Registry·승인·감사 체인·종료 판정·엔드포인트 인벤토리 | × (API 경계) |
| **Gateway MCP** | `127.0.0.1:8080/mcp/` | Streamable HTTP MCP ingress | × |
| **Gateway SSE** | 내부 `gateway-sse:8081` | 구형 client 호환 ingress | × |

**합칠 때의 규칙 하나**: 판정과 관리대장은 Gateway가 정본입니다. Agent Service의
같은 이름 경로는 **대리 호출**이며 조작 논리를 복제하지 않습니다. 새 기능을 붙일
때 이 방향을 뒤집지 마세요 — 정책 원본이 둘로 갈라지면 어느 쪽이 정본인지 저장소가
답하지 못합니다.

---

## 1. 인증

### 1.1 토큰 받기

```http
POST /auth/mock-login            (Agent Service :8000)
POST /api/session                (Gateway :8080)
Content-Type: application/json

{"email": "miso@bob.local", "password": "test-password"}
```

```json
{"access_token": "<Ed25519 서명 JWT>", "token_type": "bearer", "expires_in": 1800}
```

- 서명은 **Ed25519**. 개인키는 Agent Service만 보유하고 Gateway는 공개키만 갖습니다.
  검증자가 발급자가 될 수 없게 하는 것이 이 분리의 전부입니다.
- 실패한 로그인이 같은 출처에서 `LOGIN_ATTEMPT_LIMIT`(기본 10)회를 넘으면 `429`.
  존재하지 않는 주소도 같이 제한합니다 — 그러지 않으면 제한 자체가 계정의 존재를
  알려줍니다.
- 역할과 계정 상태는 토큰이 아니라 `principals` 관리대장에서 **매 요청** 읽습니다.
  `disabled`로 바꾸면 이미 발급된 토큰도 다음 요청에서 `403`입니다.

### 1.2 토큰 쓰기

```http
Authorization: Bearer <access_token>
```

### 1.3 인증 수준

| 수준 | 의미 | 표기 |
| --- | --- | --- |
| **열림** | 토큰 없이 호출 가능 (loopback 바인딩 전제) | — |
| **사용자** | 서명된 토큰 필요, 역할 무관 | 🔑 |
| **관리자** | `admin` 역할 필요 | 🔒 |

무인증으로 열린 Gateway API 목록은 `full_stack_lab/README.md` 13절이 정본이고,
[`tests/open_endpoints.py`](../full_stack_lab/tests/open_endpoints.py)가 코드와
대조합니다. 목록을 늘리면 그 테스트가 실패합니다.

### 1.4 Agent Assertion (내부 전용)

`POST /tool-call`은 사용자 JWT에 더해 `X-Agent-Assertion`을 요구합니다.
Agent Service가 `agent:<id>`, 사용자 actor, `mcp:tools/call`, 그리고 Tool Call
envelope의 SHA-256을 **다른 audience로 60초** 서명한 값입니다.

| 조작 | 결과 |
| --- | --- |
| 사용자 JWT만 제시 | `401` |
| 다른 actor·agent의 assertion | `401` |
| envelope를 바꾼 뒤 재사용 | `401` |
| 같은 `tool_call_id`로 재시도 | 기존 receipt 반환 (중복 실행 없음) |

---

## 2. 공통 규약

### 2.1 오류

FastAPI 표준 형태입니다. Agent Service의 대리 호출은 Gateway의 상태 코드와
`detail`을 **그대로 전달**합니다.

```json
{"detail": "판정하지 않은 케이스는 종결할 수 없습니다."}
```

| 코드 | 의미 | 예 |
| --- | --- | --- |
| `400` | 요청 형식 오류 | — |
| `401` | 인증 실패·만료·로그아웃·관리대장에 없는 신원 | 위조 토큰 |
| `403` | 인증은 됐으나 권한 없음 / 정지·잠금 계정 | 직원이 승인 시도 |
| `404` | 대상 없음 | 없는 케이스 ID |
| `409` | 상태 충돌 | 이미 종료 절차 중인 서버 |
| `422` | 검증 실패 | 사유 없는 거부, 잘못된 시각 형식 |
| `429` | 요청량 초과 | 로그인 시도 상한 |
| `503` | 하위 서비스 연결 실패 | Gateway 미기동 |

**`409`와 `422`를 구별하는 이유**: 전자는 "지금은 안 된다", 후자는 "이 입력으로는
안 된다"입니다. 둘을 같은 코드로 주면 클라이언트가 재시도해야 할지 고쳐야 할지
모릅니다.

### 2.2 멱등성

| 키 | 범위 | 동작 |
| --- | --- | --- |
| `request_id` | Agent Service `/chat` | 같은 값이면 저장된 응답 반환 |
| `tool_call_id` | Gateway `/tool-call` | 같은 값이면 기존 receipt 반환 |
| `request_fingerprint` | 승인 | 원 요청과 지문이 다르면 승인 무효 |

timeout이나 연결 단절 뒤에는 upstream 실행 여부가 불확실할 수 있습니다. **자동
재시도하기 전에 receipt를 먼저 확인하세요.**

### 2.3 판정 응답 (모든 도구 호출의 공통 형태)

```json
{
  "request_id": "…", "trace_id": "…", "decision_id": 412,
  "decision": "Alert",
  "policy_id": "P-IMPORTANT-ALERT-001",
  "policy_version": "1.0.0",
  "policy_status": "운영",
  "reason": "직원의 중요정보 열람은 허용하되 경보와 증적을 남깁니다.",
  "restrictions": {},
  "obligations": ["evidence.enhanced"],
  "exception": null,
  "conflicts": [{"policy_id": "P-333-ALLOW-001", "decision": "Allow", "priority": 140}],
  "risk_ids": ["RSK-005"], "control_ids": ["CTL-005"],
  "environment": "prod",
  "enforcement": "enforce",
  "would_decision": null, "would_policy_id": null,
  "upstream_executed": true,
  "upstream_attempted": true,
  "effect_before": 17, "effect_after": 18,
  "result": {"…": "…"}
}
```

| 필드 | 왜 있는가 |
| --- | --- |
| `decision` | `Allow` / `Alert` / `Approval` / `Restrict` / `Block` |
| `conflicts` | 동시에 성립했으나 우선순위에서 진 정책. 없으면 정책 충돌을 관측할 수 없다 |
| `would_decision` | 관찰 모드에서 "집행 모드였다면" |
| `upstream_executed` | 판정과 **실제 효과**는 다른 증적이다 |
| `upstream_attempted` | 실행을 시도했는지 기록. `true`인데 `upstream_executed=false`이면 실행 여부 미확인이므로 자동 재실행 금지 |
| `effect_before/after` | upstream의 독립 효과 카운터. 차단이 정말 멈췄는지 대조 |

`upstream_executed: true`인데 `decision: Block`인 경우가 있습니다
(`MCP-OUTPUT-001`). 호출은 실행됐고 결과만 반환하지 않은 상태입니다. 판정과 효과를
억지로 일치시키는 것보다 증적을 정직하게 두는 쪽을 택했습니다.

`upstream_executed: false`만으로 차단 성공을 판단하면 안 됩니다. 응답 유실·통신 실패는
`upstream_attempted: true`로 남으며 독립 효과 증적을 확인해야 합니다. 실행 직전 계약·승인
검증에서 거부했다면 두 필드 모두 `false`입니다. 구버전 DB 행의 `upstream_attempted=null`은
새 필드가 기록되지 않았다는 뜻이며, 기존 `MCP-UPSTREAM-001` 오류는 보수적으로 미확인으로
표시합니다. 새 감사 체인 v4는 시도 여부도 보호하고 기존 v1~v3 해시를 그대로 검증합니다.

---

## 3. Gateway API (`:8080`)

### 3.1 상태·조회

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| GET | `/api/health` | — | 구성요소별 가용성 |
| GET | `/api/state` | — | Registry·판정·승인·공급망·신원 요약 |
| GET | `/api/integration` | — | Agent Service readiness와 최근 실행 |
| GET | `/api/policy/matrix` | — | 27칸 권한 매트릭스 실측 |
| GET | `/api/policy/ledger` | — | 집행 중인 정책 관리대장 |
| GET | `/api/monitor/summary?hours=168` | — | 관찰 모드에서 막혔을 호출 집계 |
| GET | `/api/enforcement` | — | 현재 집행 모드 |
| GET | `/api/supply-chain/coverage` | — | 스캔 결과가 차단에 연결됐는지 |
| GET | `/api/effects` | — | upstream 독립 효과 로그 |
| GET | `/api/risk-catalog` | — | AI-Infra-Guard 위험 범주 ↔ 이 조직 통제 매핑 |

### 3.2 도구 호출

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| POST | `/api/calls` | 🔑 | 정책 경로 직접 호출 (시연·검증용) |
| POST | `/api/mock-model` | 🔑 | 모의 모델 제안 → 판정 |
| POST | `/tool-call` | 🔑 + Assertion | Agent Service 전용 내부 경로 |

```http
POST /api/calls
{"tool_name": "read_document", "document_id": "secret-001"}
```

`tool_name`은 `read_document` · `write_document` · `send_external` ·
`get_current_time` · `github_get_file` 다섯 개로 고정(Literal)입니다.
**요청자는 서명된 토큰에서만 옵니다** — 본문에 역할이나 principal을 적는 자리는
없습니다.

### 3.3 승인

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| POST | `/api/approvals/{id}/approve` | 🔒 | 지문 확인 → 정책 재평가 → 1회 실행 |
| POST | `/api/approvals/{id}/reject` | 🔒 | 사유 필수(`note`, 1자 이상). 없으면 `422` |

유효기간 10분. 만료된 승인은 `EXPIRED`가 되고 실행되지 않습니다.
거부는 최종입니다 — 같은 승인을 다시 처리하려 하면 `409`.

### 3.4 Registry·공급망

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| POST | `/api/catalog/refresh` | 🔑 | 등록 서버의 catalog를 승인 계약과 재대조 |
| POST | `/api/supply-chain/import` | 🔒 | `reports/`의 스캔 결과를 서버에 귀속 |

### 3.5 집행 모드·감사

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| PUT | `/api/enforcement` | 🔒 | `{"mode": "enforce"\|"monitor"}` |
| GET | `/api/audit/verify` | 🔒 | 해시 체인 무결성. 끊겼으면 행 번호를 준다 |

`monitor`에서도 **무결성 통제는 집행됩니다** — `MCP-`, `P-CONTROL-`, `P-INPUT-`,
`P-RATE-` 접두사 정책은 관찰 대상이 아닙니다.

### 3.6 종료·폐기 (전주기 마지막)

절차와 판정 기준은 [TERMINATION.md](../full_stack_lab/TERMINATION.md)에 있습니다.

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| GET | `/api/termination/cases` | 🔒 | 케이스 목록 + 요약 |
| POST | `/api/termination/cases` | 🔒 | **종료 개시 = 즉시 차단.** 회수 대상 자동 수집 |
| GET | `/api/termination/cases/{id}` | 🔒 | 케이스·회수 대상·증거·차단 후 활동 |
| POST | `/api/termination/cases/{id}/targets` | 🔒 | 회수 대상 추가 (C1) |
| PUT | `/api/termination/targets/{id}` | 🔒 | 회수 상태 변경 (C2) |
| POST | `/api/termination/cases/{id}/evidence` | 🔒 | 증거 첨부 (C4). `subject` 필수 |
| POST | `/api/termination/cases/{id}/probe` | 🔒 | endpoint 도달 확인 (C3) |
| POST | `/api/termination/cases/{id}/assess` | 🔒 | C1~C4 계산 → T1/T2/T3 |
| POST | `/api/termination/cases/{id}/close` | 🔒 | 종결. T3는 `risk_acceptance` 필수 |
| POST | `/api/termination/cases/{id}/reopen` | 🔒 | 재개 (종결된 케이스만) |
| GET | `/api/termination/cases/{id}/report` | 🔒 | 종료 판정서 |
| GET | `/api/termination/cases/{id}/disclosure-request` | 🔒 | 제공자 고지 요청서(마크다운) |
| GET | `/api/termination/drill/{server_id}` | 🔒 | **폐기 드릴.** 끊지 않고 도달 가능한 최선 등급 계산 |

**드릴 응답**

```json
{"server_id": "github", "remote_provider": true,
 "best_attainable_grade": "T3", "best_attainable_label": "판단 불가",
 "blockers": ["제공자의 하위 위임 자격 고지가 계약에 없습니다. …"],
 "would_revoke": {"client_tokens": 2, "endpoint_configs": 1, "provider_held": 1},
 "active_users": [{"user_token": "emp-demo", "display_name": "김미소", "calls": 14}],
 "note": "실제로 차단하지 않았습니다. 종료를 시작하려면 케이스를 여세요."}
```

드릴은 **부작용이 없습니다.** 케이스를 만들지도 `lifecycle`을 건드리지도 않습니다.
답하는 것은 현재 등급이 아니라 증거를 전부 모았을 때 **닿을 수 있는 천장**입니다.

**개시 요청**

```json
{"server_id": "github", "reason": "계약 종료에 따른 이용 중단",
 "engagement_label": "GitHub MCP · 개발팀 코드 조회"}
```

**판정 응답의 `criteria`**

```json
{"C1": {"met": false, "gaps": ["원격 제공자가 하위 위임 자격을 고지하지 않아 …"],
        "targets": 3, "unverifiable": 1, "provider_disclosed": false, "endpoint_residue": 0},
 "C3": {"met": true, "post_cutover_executed": 0, "post_cutover_blocked": 2,
        "max_propagation_seconds": 41.2},
 "grade": "T3", "grade_label": "판단 불가",
 "rationale": "모집단 또는 증거 접근이 성립하지 않아 잔존 범위를 산정할 수 없습니다."}
```

**상태 전이**

```
OPEN ──► REVOKING ──► ASSESSED ──► CLOSED
  ▲          ▲            │            │
  └──────────┴────────────┘            │
     (근거가 바뀌면 판정이 낡는다)      │
                REOPENED ◄─────────────┘
```

근거(회수 대상·증거)를 추가하면 `ASSESSED`는 `REVOKING`으로 돌아가고 등급이
지워집니다. 낡은 판정과 판정 없음 중 위험한 것은 낡은 판정입니다.

### 3.7 엔드포인트 평면

평면 분리의 근거는 [CONTROL_PLANES.md](../full_stack_lab/CONTROL_PLANES.md)입니다.

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| POST | `/api/endpoint/enroll` | 🔒 | 엔드포인트 등록. **사람이 한다** |
| POST | `/api/endpoint/inventory` | 🔑 | 설정 인벤토리 보고. **전체 교체** |
| GET | `/api/endpoint/inventory?classification=` | 🔒 | 커버리지·에이전트·항목 |

```http
POST /api/endpoint/inventory
{"endpoint_id": "endpoint-dev-001",
 "entries": [{"config_path": "~/.claude/claude_desktop_config.json",
              "server_label": "local-notes", "transport": "stdio",
              "endpoint_ref": "npx -y @example/notes-mcp"}]}
```

```json
{"endpoint_id": "endpoint-dev-001", "accepted": 1, "removed": 2,
 "counts": {"registered": 0, "shadow": 1, "retired-residue": 0}}
```

- **보고는 누적이 아니라 교체입니다.** 이번에 없는 항목은 삭제됩니다. 그러지 않으면
  설정에서 지워져도 잔존이 영원히 남아 C1이 확정되지 않습니다.
- 이 본문은 **관측 보고이지 지시가 아닙니다.** 보고 내용으로 Registry를 바꾸거나
  서버를 활성화하는 경로는 없습니다.
- `env`·`headers`는 보내지 마세요. 서버가 저장하지 않으며, 보내면 그 토큰이
  전송 구간에 불필요하게 노출됩니다.

---

## 4. Agent Service API (`:8000`)

### 4.1 인증·세션

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| POST | `/auth/mock-login` | — | 합성 로그인 |
| GET | `/auth/me` | 🔑 | 현재 신원 |
| POST | `/auth/logout` | 🔑 | `jti` 무효화. 모든 ingress에 즉시 반영 |
| GET | `/api/readiness` | — | 모델 모드와 준비 상태 |
| GET | `/sessions` · `/sessions/{id}` | 🔑 | 본인 세션만 |

### 4.2 업무 실행

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| POST | `/chat` | 🔑 | 자연어 → Tool Call 제안 → Gateway 판정 |
| GET | `/approvals` | 🔑 | 승인 대기 (관리자는 전체) |
| POST | `/approvals/{id}/approve` · `/reject` | 🔒 | 승인·거부 |

```http
POST /chat
{"message": "중요 계약 초안을 읽어줘"}
```

모델이 만드는 Tool Call에는 **사용자 역할이나 Gateway용 토큰을 넣을 수 없습니다.**
Gateway가 모델에 노출하는 도구 스키마에는 신원 인자가 하나도 없습니다.

### 4.3 Console

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| GET | `/api/console` | 🔑 | **역할에 없는 화면의 데이터는 응답에서 빠진다** |
| GET | `/api/stream/decisions?after=` | 🔑 | SSE. 2초마다 새 판정만 |
| GET | `/api/mcp-catalog/search?q=` | 🔑 | 카탈로그 검색. 신청자·목적은 반환 안 함 |
| GET | `/api/accounts` · PUT `/api/accounts/{id}/status` | 🔒 | 신원 관리대장 |
| GET | `/api/audit/verify` | 🔒 | 감사 체인 검증 (대리) |
| GET | `/api/risk-catalog` | 🔑 | 위험 범주 매핑 (대리) |

`/api/console`이 화면 목록(`viewer.pages`)과 데이터를 함께 정합니다. 메뉴만
숨기면 개발자 도구를 여는 순간 통제가 사라지므로, **데이터 자체를 뺍니다.**

| 화면 | partner | employee | admin |
| --- | --- | --- | --- |
| `execution` · `intake` | ○ | ○ | ○ |
| `audit` | - | ○ (본인만) | ○ |
| `overview` · `verification` · `risks` · `mcpscan` | - | - | ○ |
| `termination` · `endpoints` · `policy` · `accounts` | - | - | ○ |

### 4.4 도입 요청

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| POST | `/api/mcp-requests` | 🔑 | 저장소 URL + **종료 조건 3개** 제출 → `HOLD` |
| POST | `/api/mcp-requests/{id}/queue-validation` | 🔒 | 격리 검증 실행 |
| POST | `/api/mcp-requests/{id}/approve` | 🔒 | `VALIDATED` → `APPROVED` |
| POST | `/api/mcp-requests/{id}/reject` | 🔒 | 사유 필수 |

```
제출(HOLD) → 관리자 실행(VALIDATION_QUEUED) → 격리 워커(VALIDATING)
  → Syft · Trivy · Semgrep → Critical 0이면 VALIDATED, 1건 이상이면 REJECTED
  → 관리자 승인(APPROVED) = Registry 등록 **대상 확정**
```

`APPROVED`는 "Registry에 올려도 된다"까지입니다. 실제 활성화는 endpoint와 catalog
해시를 고정하는 **별도 단계**입니다.

요청 본문의 종료 조건 세 개(`provider_credential_disclosure`,
`revocation_evidence`, `audit_access_retained`)는 그 서버를 나중에 **끊을 수
있는가**를 정합니다. 기록하는 것은 계약 조항의 존재이지 제공자가 실제로 고지했다는
사실이 아닙니다 — 조항은 "요청할 권리가 있다"까지입니다.
`INTAKE_EXIT_TERMS_REQUIRED=1`이면 원격 MCP는 자격 고지 조항 없이 승인되지 않습니다.

### 4.5 AI 코드 감사

| 메서드 | 경로 | 인증 | 설명 |
| --- | --- | --- | --- |
| GET | `/api/mcp-scan` | 🔒 | 설정·워커 생존·대상·작업 이력·결과 |
| POST | `/api/mcp-scan/connection-test` | 🔒 | endpoint 응답 + **워커 생존**을 함께 |
| POST | `/api/mcp-scan/run` | 🔒 | `{"target_kind", "target_id", "mode", "acknowledge_external_model"}` |
| POST | `/api/mcp-scan/jobs/{id}/cancel` · `/retry` | 🔒 | 취소·재시도 |

`mode`는 `static`(고정 commit 복제 후 코드 감사)과 `dynamic`(실행 중인 endpoint에
접속)입니다. 동적 점검은 **등록된 서버에만** 가능하고 — 아직 들이지 않기로 한
도입 요청에 붙는 것은 격리 원칙과 반대입니다 — 대상 서버의 응답이 설정한 모델
endpoint로 나갑니다. 그 endpoint가 외부면 `acknowledge_external_model: true`
없이는 `409`입니다. 폐기 중 서버의 응답에 잔존 데이터가 있을 수 있기 때문입니다.

결과에는 **어떤 모델이 어느 endpoint로 판단했는지**(`model`, `base_url`),
**무엇이 이 작업을 만들었는지**(`trigger`), **이 결과가 차단에 연결되는지**
(`blocks_calls`), **어떤 위험 범주가 나왔는지**(`risk_breakdown`)가 항상 함께
남습니다. 모델을 모르는 보안 결과는 증적이 아닙니다.

---

## 5. MCP ingress

Gateway가 중개하는 MCP 메서드는 다섯뿐입니다.

`initialize` · `server/discover` · `ping` · `tools/list` · `tools/call`

`resources/*`, `prompts/*`, `sampling/*`, `elicitation/*`, `completion/*`,
`logging/*`, `roots/*`는 등록 여부와 무관하게 `MCP-METHOD-001`로 거부합니다.
prompt와 resource 본문은 에이전트로 들어가는 주요 인젝션 경로이고, Gateway는
그것을 **나르지 않는다**고 분명히 말합니다.

| 구간 | 방식 | 신원 출처 |
| --- | --- | --- |
| Client → Gateway | Streamable HTTP `/mcp/` | `Authorization` 헤더 |
| Client → Gateway | stdio (`python -m app.stdio_entry`) | spawn 시점에 고정한 `GATEWAY_STDIO_PRINCIPAL` |
| Client → Gateway | legacy SSE `gateway-sse:8081/sse` | `Authorization` 헤더 |

stdio는 헤더가 없는 transport이므로 신원을 기동 시 한 번 고정하고, **고정되지 않은
stdio ingress는 기본 principal로 넘어가지 않고 거부합니다.**

---

## 6. 정책 ID 사전

판정에 나타나는 정책 ID와 그 뜻입니다. 정본은
[`opa/policy_ledger.json`](../full_stack_lab/opa/policy_ledger.json)이고, 관리대장에
없는 정책이 판단에 관여하면 `P-CONTROL-LEDGER-001`로 차단됩니다.

| 우선 | ID | 판정 | 조건 |
| --- | --- | --- | --- |
| 1 | `P-CONTROL-LEDGER-001` | Block | 관리대장에 없는 정책이 관여 |
| 5 | `P-CONTROL-INPUT-001` | Block | 판단에 필요한 입력 누락 |
| 10 | `MCP-REGISTRY-001` | Block | 미등록 서버·도구 |
| **15** | **`MCP-DECOMM-001`** | **Block** | **종료·폐기 단계의 이용 관계** |
| 20 | `MCP-REGISTRY-002` | Block | Registry에서 비활성 |
| 30 | `MCP-SUPPLY-001` | Block | 미승인 공급자 또는 치명적 취약점 |
| 50 | `MCP-CATALOG-001` | Block | 설명·스키마·버전·도구 목록 드리프트 |
| 55 | `P-APPROVAL-EXPIRY-001` | Block | 도입·사용 승인 기한 만료 |
| 60 | `P-CLASSIFICATION-001` | Block | 데이터 등급의 출처 없음 |
| 70 | `P-RATE-001` | Block | 호출량 상한 초과 |
| 80 | `P-333-DENY-001` | Block | 27칸 권한표에 없는 조합 |
| 90 | `P-X-APPROVAL-001` | Approval | 중요정보 외부 전송 |
| 100 | `P-VOLUME-001` | Approval | 중요정보 누적 접근 |
| 110 | `P-DEPT-001` | Approval | 소관 부서 아닌 중요정보 (기본 비활성) |
| 120 | `P-X-RESTRICT-001` | Restrict | 비중요 외부 전송의 목적지·길이 축소 |
| 130 | `P-IMPORTANT-ALERT-001` | Alert | 직원의 중요정보 열람 |
| **135** | **`MCP-SHADOW-001`** | **Alert** | **요청자 단말에 미등록 MCP 설정 보고됨** |
| 140 | `P-333-ALLOW-001` | Allow | 권한표와 계약 충족 |
| 9999 | `P-CONTROL-DEFAULT-001` | Block | 성립한 정책 없음 |

Gateway가 직접 내는 판정(우선순위 2001~): `MCP-METHOD-001`, `P-INPUT-001`,
`P-INPUT-SCHEMA-001`, `MCP-REPOSITORY-001`, `MCP-RECEIPT-001`,
`P-CONTROL-FAIL-CLOSED`, `P-MONITOR-001`, `MCP-UPSTREAM-001`, `MCP-OUTPUT-001`.

**숫자가 작은 정책이 이깁니다.** 진 후보는 `conflicts`에 남습니다.

---

## 7. 합칠 때 확인할 것

새 구성요소를 이 Gateway에 붙일 때의 체크리스트입니다.

1. **신원을 본문에서 받지 않는가.** principal을 요청 본문이나 도구 인자에서 받으면
   그것은 통제가 아니라 요청서입니다.
2. **새 도구에 Registry 계약 + ingress 어댑터 + acceptance를 함께 넣었는가.**
   "등록됐으니 자동 통과"는 의도적으로 채택하지 않았습니다.
3. **새 정책 ID를 관리대장에 등록했는가.** 등록하지 않으면
   `P-CONTROL-LEDGER-001`로 모든 호출이 차단됩니다. (그 편이 조용히 통제가 꺼지는
   것보다 낫습니다.)
4. **무인증 경로를 늘렸다면 README 13절을 고쳤는가.**
   `tests/open_endpoints.py`가 실패합니다.
5. **새 상태를 만들었다면 그것을 끄는 방법도 만들었는가.** 도입은 있고 폐기가 없던
   것이 이번 판이 고친 문제입니다.
6. `./console.sh test`가 통과하는가 — Rego 62/62, core acceptance, Agent/API
   acceptance, 회귀 검사.
