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
| `POST /mcp/` | 사용자 | Streamable HTTP MCP(집계). 토큰 없음/무효 → `401` + `WWW-Authenticate: Bearer resource_metadata="…"`. 도구 이름 `<server>__<tool>`, 결과 `_meta.gateway`에 판정(decision·policy_id·decision_id·approval_id·trace_id) |
| `POST /mcp/<server>/` | 사용자 | 서버 하나만 스코프한 같은 MCP 앱 — 하네스 관리형 설정이 서버당 이 URL 하나를 쓴다. 도구는 서버 고유 이름. 인증·판정 경로는 `/mcp/`와 동일(같은 401 챌린지). 등록되지 않은 서버 이름은 집계 엔드포인트로 새지 않고 `404` |
| `GET /.well-known/oauth-protected-resource` | 공개 | RFC 9728 보호 자원 메타데이터(인가 서버 = IdP) |

하네스 신원(`claude-code`, `codex-mcp-client`, `gemini-cli-mcp-client`, `opencode`, `inspector-cli`)은 MCP
`initialize`의 `clientInfo`와 `User-Agent`에서 자동으로 기록된다(헤더 불필요). 선택 헤더(여전히 클라이언트
보고, 감사 기록에 그대로): `X-Workstation-Id`, `X-Agent-Name`, `X-Agent-Task-Id` — 없으면 `X-Workstation-Id`는
토큰의 `client_id`(=워크스테이션)로 대신한다.

## 3. IdP (agent-service)

| 경로 | 인증 | 설명 |
| --- | --- | --- |
| `GET /.well-known/oauth-authorization-server` | 공개 | RFC 8414 메타데이터 |
| `POST /oauth/token` | 공개 | `grant_type=password|refresh_token`, `client_id`(워크스테이션 id) — Ed25519 JWT(10분) + refresh(8시간, 회전) |
| `POST /oauth/revoke` | 공개 | RFC 7009. **항상 200**(무효 토큰도) — E1의 핵심 |
| `POST /oauth/introspect` | 사용자 | RFC 7662 |
| `POST /auth/mock-login` | 공개 | Console 로그인(30분). 실패 제한 있음. 같은 토큰을 `/git` 경로 전용 HttpOnly 쿠키 `mcpgw_git`로도 줌(D-48) |
| `GET /auth/me` · `POST /auth/logout` | 사용자 | 역할·볼 수 있는 화면(field: 내부 Git 주소·`kit` 키트 주소와 setup 한 줄) / 즉시 폐기(쿠키도 지움) |
| `POST /auth/signup` | 공개 | 가입 신청. 아이디는 Gitea 이름 규칙(영문·숫자 사이의 기호 하나). 시도 제한 있음 |
| `GET /auth/gitea` | 쿠키 또는 Basic | Caddy `forward_auth` 전용(D-48). 통과 200 + `X-WEBAUTH-USER`, 브라우저 미로그인 302 `/login?next=/git/…`, 그 밖 401 Basic |

## 4. Console 전용 (agent-service)

| 경로 | 인증 | 설명 |
| --- | --- | --- |
| `GET/POST/PUT/DELETE /gw/<path>` | 사용자 | Gateway `/api/<path>` 프록시. 관리자: `overview, activity, registry, health, termination/, approvals/, catalog/, enforcement, monitor/, audit/, policy/, endpoint/, supply-chain/, risk-catalog, lab/` · 그 외: `activity, health`만 |
| `GET /approvals` · `POST /approvals/{id}/approve|reject` | 관리자 | `{approvals, history}` — 대기 중(요청자·도구·인자·판정 맥락)과 처리·만료된 최근 50건 |
| `GET /api/accounts` · `PUT /api/accounts/{user_id}/status` | 관리자 | 신원 관리대장, 계정 사용/중지/잠금 |
| `GET /api/mcp-requests` · `POST /api/mcp-requests` | 사용자 | 도입 신청 목록(관리자=전체) / 신청 `{display_name, repository_url, requested_transport, purpose}` — 종료 조건 필드를 보내면 422 |
| `PUT /api/mcp-requests/{id}/exit-terms` | 관리자 | 제공자 문서로 확인한 종료 조건 기록 `{provider_credential_disclosure, revocation_evidence, audit_access_retained, evidence_url(https), note}` → 검증 주체·시각과 함께 저장. 승인 전(HOLD~VALIDATED)만 |
| `POST /api/mcp-requests/{id}/queue-validation|approve|reject` | 관리자 | 격리 검증 대기열(HOLD·FAILED·VALIDATED)·승인·거부(승인 전 모든 단계). 원격(HTTP·SSE) 서버의 승인은 ① 종료 조건 결론 T1 ② 관리자 증거 기록 ③ `approve` 본문 `{risk_acceptance}`(10자 이상, 수용자·시각·결론 등급과 함께 저장) 중 하나가 있어야 함(아니면 409, D-50). 승인은 저장소를 Gitea `mcp` 조직으로 가져옴 |
| `POST /api/mcp-requests/{id}/register` | 관리자 | APPROVED 신청을 Gateway에 등록(D-49) `{server_id, endpoint, catalog_hash, tools:{이름:r|w|x}, data_class, valid_days, poisoning_ack}` — 저장소·검증 커밋·목적·종료 조건은 신청에서 실음. 설명 경고가 있는 도구를 고르면 `poisoning_ack: true` 필요(D-52) |
| `POST /api/pc/inventory` | 사용자(키트) | 직원 PC 키트의 하네스 보고(D-51) `{workstation, harnesses:[claude|codex], items:[{harness, kind(connector·plugin·server·app·feature), name, target(scheme://host[:port]·stdio·앱 id·기능 값), status, active}]}` → `{accepted, policy, review}`. 이번에 읽은 하네스의 이전 항목은 '없음'으로 내림 |
| `GET /api/connectors[?summary=1]` · `PUT /api/connectors/decision` | 관리자 | 하네스 커넥터 목록(상태 pending·expired·denied·approved·default, 켜진 PC 수, 보고한 PC) / 결정 `{key, decision: approved|denied|reset, note}` — 거부는 사유 필수 |
| `GET /api/connectors/policy` | 관리자 | 거부 목록을 하네스 키로: `claude.deniedMcpServers`·`allowAllClaudeAiMcps`, `codex.apps_disabled`·`features_disabled` — `mcpgw_pc.py managed --connectors`가 관리형 파일로 바꿈 |
| `GET /api/mcp-catalog/search?q=` | 사용자 | 이미 신청·등록된 서버인지 |
| `GET /api/mcp-scan` 외 `/api/mcp-scan/*` | 관리자 | AI 코드 감사(격리 워커) 작업 |
| `GET /api/readiness` · `GET /health` | 공개 | 준비 상태(Gateway·LLM 게이트웨이) |

## 5. Gateway 운영 API

| 경로 | 인증 | 설명 |
| --- | --- | --- |
| `GET /api/health` | 공개 | 구성요소·MCP 서버 준비 수 |
| `POST /api/session` | 공개 | 로그인 프록시(IdP로 전달) |
| `GET /api/activity?after&limit&decision&server&person` | 사용자 | 판정을 읽는 문장으로(비관리자는 자기 것만) |
| `GET /api/overview` | 관리자 | 개요 화면 한 번에 — `series`(24시간 시간대별 판정 수), `flows`(하네스×서버×판정 수), 워크스테이션별 `harness`·`calls` 포함 |
| `GET /api/state` · `GET /api/registry` | 관리자 | 원시 상태 / 카탈로그+계약+이용 관계, `registrations`(Console 등록 서버의 사용 기한·등록자) |
| `POST /api/catalog/refresh` | 관리자 | 모든 서버 계약 재확인 |
| `POST /api/registry/{server}/approve-contract` | 관리자 | 검토한 계약 변경을 승인본으로(`note` 필수) |
| `POST /api/registry/{server}/check` | 관리자 | MCP 세션만 협상해 연결 확인 — `state`(healthy·unhealthy·retired)·지연·서버 정보. 계약·상태·감사는 그대로(D-40) |
| `POST /api/registry/discover` | 관리자 | 등록 전 검토 `{endpoint}` → 광고 도구·권장 행위·`catalog_hash`, 도구별 `warnings`(설명 속 숨은 지시, D-52). 아무것도 기록하지 않음(D-49) |
| `POST /api/registry/servers` | 관리자 | Console 등록. `catalog_hash`가 지금 서버 계약과 다르면 409. 결과 `status`·`valid_until`·`gateway_path` |
| `POST /api/registry/servers/{id}/extend` · `DELETE /api/registry/servers/{id}` | 관리자 | 사용 기한을 오늘부터 다시(`valid_days`) / 등록 해제(서버는 DISABLED로 남음). Console 등록 서버만 |
| `POST /api/approvals/{id}/approve|reject` | 관리자 | 승인 → 1회 실행 |
| `GET /api/policy/matrix` · `GET /api/policy/ledger` | 사용자 | 역할×등급×행위 27칸을 지금 배포된 번들로 OPA에 질의한 결과 / 관리대장·예외·`authorization`(권한 번들)·`deployed_rego`(배포 정책 묶음 digest) |
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

### 도입 검증 보고서
- `POST /api/mcp-requests`: 인증한 신청자의 요청을 VALIDATION_QUEUED로 접수합니다.
- `GET /api/mcp-requests/{request_id}/report`: 관리자 전용 신청 상세·검사 요약·종료조건 조사·다운로드 목록입니다.
- `GET /api/mcp-requests/{request_id}/artifacts/{kind}`: 관리자 전용 JSON 첨부 다운로드입니다. kind는 sbom, trivy, semgrep, exit-terms만 허용합니다.
- `POST /api/mcp-requests/{request_id}/queue-validation`: 관리자 전용 HOLD·FAILED·VALIDATED 재검증입니다(VALIDATED는 새 규칙으로 종료 조건 결론을 다시 낼 때). 이미 진행 중인 요청은 409입니다.
