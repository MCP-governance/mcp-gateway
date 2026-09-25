# API 요약 (v2)

> 기계용 명세: `cd full_stack_lab && ./console.sh openapi` → `docs/openapi/gateway.json`, `agent-service.json`.
> 인증 수준: **공개** · **사용자**(유효한 Bearer 토큰) · **관리자** · **장치**(`X-Endpoint-Key`, 범위 제한).
> 무인증 목록은 `tests/open_endpoints.py`가 `full_stack_lab/README.md`의 문장과 대조한다.

## 1. 서비스 경계

| 서비스 | 호스트 포트(기본) | 누가 부르나 |
| --- | --- | --- |
| agent-service (Console·IdP) | `127.0.0.1:${CONSOLE_PORT:-8000}` | 브라우저, 워크스테이션(IdP) |
| gateway (API + MCP) | `127.0.0.1:${GATEWAY_PORT:-8080}` | 워크스테이션(`/mcp/`), 운영 스크립트, Console 프록시 |
| gateway-sse | 없음(내부 `:8081/sse`) | 구형 SSE 클라이언트 |

## 2. MCP ingress (Gateway)

| 경로 | 인증 | 설명 |
| --- | --- | --- |
| `POST /mcp/` | 사용자 | Streamable HTTP MCP. 토큰 없음/무효 → `401` + `WWW-Authenticate: Bearer resource_metadata="…"`. 도구 이름 `<server>__<tool>`, 결과 `_meta.gateway`에 판정(decision·policy_id·decision_id·approval_id·trace_id) |
| `GET /.well-known/oauth-protected-resource` | 공개 | RFC 9728 보호 자원 메타데이터(인가 서버 = IdP) |

선택 헤더(클라이언트 보고, 감사 기록에 그대로): `X-Workstation-Id`, `X-Agent-Name`, `X-Agent-Task-Id`.

## 3. IdP (agent-service)

| 경로 | 인증 | 설명 |
| --- | --- | --- |
| `GET /.well-known/oauth-authorization-server` | 공개 | RFC 8414 메타데이터 |
| `POST /oauth/token` | 공개 | `grant_type=password|refresh_token`, `client_id`(워크스테이션 id) — Ed25519 JWT(10분) + refresh(8시간, 회전) |
| `POST /oauth/revoke` | 공개 | RFC 7009. **항상 200**(무효 토큰도) — E1의 핵심 |
| `POST /oauth/introspect` | 사용자 | RFC 7662 |
| `POST /auth/mock-login` | 공개 | Console 로그인(30분). 실패 제한 있음 |
| `GET /auth/me` · `POST /auth/logout` | 사용자 | 역할·볼 수 있는 화면 / 즉시 폐기 |

## 4. Console 전용 (agent-service)

| 경로 | 인증 | 설명 |
| --- | --- | --- |
| `GET/POST/PUT/DELETE /gw/<path>` | 사용자 | Gateway `/api/<path>` 프록시. 관리자: `overview, activity, registry, health, termination/, approvals/, catalog/, enforcement, monitor/, audit/, policy/, endpoint/, supply-chain/, risk-catalog, lab/` · 그 외: `activity, health`만 |
| `GET /approvals` · `POST /approvals/{id}/approve|reject` | 관리자 | 승인 대기(요청자·도구·인자·판정 맥락) |
| `GET /api/accounts` · `PUT /api/accounts/{user_id}/status` | 관리자 | 신원 관리대장, 계정 사용/중지/잠금 |
| `GET /api/mcp-requests` · `POST /api/mcp-requests` | 사용자 | 도입 신청 목록(관리자=전체) / 신청(종료 조건 포함) |
| `POST /api/mcp-requests/{id}/queue-validation|approve|reject` | 관리자 | 격리 검증 대기열·승인·거부 |
| `GET /api/mcp-catalog/search?q=` | 사용자 | 이미 신청·등록된 서버인지 |
| `GET /api/mcp-scan` 외 `/api/mcp-scan/*` | 관리자 | AI 코드 감사(격리 워커) 작업 |
| `GET /api/readiness` · `GET /health` | 공개 | 준비 상태(Gateway·LLM 게이트웨이) |

## 5. Gateway 운영 API

| 경로 | 인증 | 설명 |
| --- | --- | --- |
| `GET /api/health` | 공개 | 구성요소·MCP 서버 준비 수 |
| `POST /api/session` | 공개 | 로그인 프록시(IdP로 전달) |
| `GET /api/activity?after&limit&decision&server&person` | 사용자 | 판정을 읽는 문장으로(비관리자는 자기 것만) |
| `GET /api/overview` | 관리자 | 개요 화면 한 번에 |
| `GET /api/state` · `GET /api/registry` | 관리자 | 원시 상태 / 카탈로그+계약+이용 관계 |
| `POST /api/catalog/refresh` | 관리자 | 모든 서버 계약 재확인 |
| `POST /api/registry/{server}/approve-contract` | 관리자 | 검토한 계약 변경을 승인본으로(`note` 필수) |
| `POST /api/approvals/{id}/approve|reject` | 관리자 | 승인 → 1회 실행 |
| `GET /api/policy/matrix` · `GET /api/policy/ledger` | 사용자 | 333 행렬(OPA 질의) / 관리대장·예외 |
| `GET/PUT /api/enforcement` | 사용자/관리자 | 집행·관찰 모드 |
| `GET /api/monitor/summary?hours` | 관리자 | 관찰 모드에서 "집행했다면" 통계 |
| `GET /api/audit/verify` | 관리자 | 해시 체인 전체 검증, 끊긴 행 id |
| `GET /api/supply-chain/coverage` · `POST /api/supply-chain/import` | 관리자 | 공급망 증적 |
| `GET /api/risk-catalog` | 사용자 | AI-Infra-Guard 위험 범주 ↔ 통제 |

### 종료·폐기 (관리자)
`GET /api/termination/relationships` · `GET|POST /api/termination/cases` · `GET /api/termination/cases/{id}` ·
`POST …/cases/{id}/targets` · `PUT /api/termination/targets/{id}` · `POST /api/termination/targets/{id}/revoke-credential` ·
`POST …/cases/{id}/evidence` · `POST …/cases/{id}/collect {kinds}` · `POST …/cases/{id}/probe` ·
`POST …/cases/{id}/assess` · `POST …/cases/{id}/close {note, risk_acceptance}` · `POST …/cases/{id}/reopen {reason}` ·
`GET …/cases/{id}/report` · `GET …/cases/{id}/disclosure-request` · `GET /api/termination/drill/{server}` ·
`POST /api/lab/restore/{server}`(실습). 의미는 [ai/TERMINATION_MODEL.md](ai/TERMINATION_MODEL.md).

### 엔드포인트 평면
관리자: `POST|GET /api/endpoint/devices`, `DELETE /api/endpoint/devices/{id}`, `GET /api/endpoint/inventory`,
`GET /api/endpoint/scan-policy/admin`, `PUT /api/endpoint/scan-policy`.
장치: `POST /api/endpoint/enroll`, `POST /api/endpoint/inventory`, `POST /api/endpoint/listeners`, `GET /api/endpoint/scan-policy`.

## 6. 오류의 의미
- `401` 토큰 없음·무효·폐기(로그아웃 포함). `/mcp/`는 RFC 9728 챌린지를 붙인다.
- `403` 역할 부족 또는 계정 중지/잠금(사유 문장 포함).
- `409` 절차 순서 위반(예: 판정 전 종결, T3를 위험 수용 없이 종결, 이미 처리된 승인).
- `503` Console 프록시가 Gateway에 닿지 못함(재시작 중 등).
- 도구 호출의 차단·승인 대기는 HTTP 오류가 아니라 MCP 결과(`isError=true`, `_meta.gateway.decision`)다.
