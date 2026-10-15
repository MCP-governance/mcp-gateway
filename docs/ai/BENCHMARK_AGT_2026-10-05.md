# microsoft/agent-governance-toolkit(AGT) 비교 — 2026-10-05

> 대상: `microsoft/agent-governance-toolkit` `5233029`(2026-10-05, v5.0.0, MIT)을 `ref-src/ms-agent-governance-toolkit`에 얕은 복제로 받아 읽었다.
> 입력 문서는 AGT의 [`docs/compliance/mcp-owasp-top10-mapping.md`](https://github.com/microsoft/agent-governance-toolkit/blob/main/docs/compliance/mcp-owasp-top10-mapping.md)(자체 평가, 2026-04 검토, OWASP MCP Top 10 v0.1 beta).
> AGT를 실행하거나 시험하지 않았다. 아래 AGT 쪽 서술은 소스 정적 관찰이고, 우리 쪽 서술은 이 저장소의 코드·문서 근거다.
> 우리 쪽 MCP01~10 대응표는 [PAC_RUNTIME_2026-10-01.md](PAC_RUNTIME_2026-10-01.md) "MCP Top 10 위협 모델"이 정본이다. 이 문서는 그것을 다시 쓰지 않는다.

## 1. 통제 위치가 다르다

| | AGT | 우리 |
| --- | --- | --- |
| 하네스 쪽 | Claude Code·Codex·Antigravity용 **훅 플러그인**(`PreToolUse` 등, 하네스 안에서 실행) | 하네스는 고치지 않음. 관리형 설정 + OS 실행·네트워크 강제 |
| 판정 위치 | 하네스 프로세스 옆(사용자가 같은 권한이면 끌 수 있음) | Gateway(원격) — 우회 경로를 OS가 막는 것이 전제 |
| 라이브러리 | Python/TS/.NET/Rust/Go SDK 안의 스캐너·리댁터 | Gateway 내부 모듈 |

그래서 AGT의 훅 플러그인은 **우리 강제 경로의 대체가 아니라 보조 신호** 정도로만 의미가 있다. 가져올 대상은 SDK 안의 스캐너·규칙이다.

## 2. MCP01~10 — AGT 자체 평가 vs 우리

| # | AGT 자체 평가 | 우리 | 비고 |
| --- | --- | --- | --- |
| 01 비밀 노출 | 부분(정규식 Redactor) | Gitleaks **전체 규칙 카탈로그**(`secret_scan.py`) + 별도 credential broker | 우리가 넓다. AGT `credential_redactor.py`(568줄)는 볼 필요 없음 |
| 02 권한 확대 | 완전(allow-list) | PAC01/09/10/13 + 호출 직전 재확인 | 동등 이상 |
| 03 도구 오염 | 완전(스캐너 + 지문) | `poisoning.py` 3단 규칙(결과/인자/카탈로그) + 계약 해시 고정, 호출 직전 재대조 | AGT 규칙은 우리 것의 부분집합에 가깝다. **빠진 것은 §3 참고** |
| 04 공급망 | 완전(AI-BOM, HMAC 서명) | 도입 검사(Syft CycloneDX SBOM·Semgrep·Gitleaks) + 고정 계약 + AppArmor | AGT의 "HMAC 지문"은 계약 해시와 같은 효과, 서명은 아님 |
| 05 명령 실행 | 완전(메타문자 차단) | PostgreSQL AST(pglast), exact command capability, OS 프로필 | 우리가 의미 단위로 더 깊다 |
| 06 의도 흐름 | 부분(패턴) | 입력·결과 poisoning + DLP + 변경 불가 정책 | 둘 다 패턴 기반. 우리 표가 "전수 방어 아님"을 명시 |
| 07 인증·인가 | 완전(DID, Ed25519) | 서명 transport identity + PAC04/06/14 + 장치 자격 | 동등. 하네스 원격 증명은 둘 다 없음 |
| 08 감사 | 완전(Merkle) | 원장 해시 체인(`prev_sha256`/`entry_sha256`, `verify_audit_chain`) | 동등 |
| 09 섀도 MCP | 부분(수동 등록) | 관리형 설정 + 미등록 route 차단 + `MCP-SHADOW-001` + OS 강제 | 우리가 앞섬. AGT `agent-discovery`는 `mcp.json`·프로세스 목록을 훑는 **발견 스캐너**(우리는 PC에서 설정 인벤토리를 보고받음) |
| 10 컨텍스트 과공유 | 완전(PII·세션 격리) | Presidio + 자원 등급 + 열람→반출 연쇄(`P-CHAIN-001`) | 동등 이상 |

AGT가 "완전"이라 한 항목도 소스를 보면 라이브러리 함수 수준이고, 강제 경로(우회 불가)는 별개다. 우리 표가 이미 더 보수적이다.

## 3. 반영한 것과 반영하지 않은 것 (같은 날 후속, D-73)

`agent-os/src/agent_os/mcp_security.py`의 `MCPSecurityScanner`와 우리 `poisoning.py`를 같은 입력으로 대조했다. 오탐은 기기 DB에 등록된
실제 도구 165개(원격 SaaS 서버 8개)에 걸어 먼저 쟀다.

| AGT 검사 | 결과 |
| --- | --- |
| 같은 이름 도구 = 사칭(`_check_cross_server`) | **안 가져옴.** 서버마다 엔드포인트가 따로고(`/mcp/<서버>/`) 통합 엔드포인트는 `<서버>__<도구>`라 호출이 섞이지 않는다. 실제 카탈로그에도 같은 이름이 정상으로 있어(`list_branches`: github·supabase, `search_issues`: github·sentry) 오탐 2건 |
| 비슷한 이름(편집거리 ≤ 2) | **안 가져옴.** 실제 카탈로그에 그런 쌍이 0건이라 지금 잡을 것이 없다 |
| 숨긴 HTML·마크다운 주석, 빈 줄 아래 꼬리, base64 | **가져옴**(`숨긴 주석`·`공백 아래 숨은 문장`·`인코딩된 문장`). 우리 규칙은 이 셋을 놓쳤다. 카탈로그 적중 0건 |
| 필수 인자 이름(`system_prompt`·`callback_url`…) | **가져오되 바꿈**(`정보 전달용 인자`). 부분 문자열 규칙은 Notion 수정 도구 2개(enum `command`)를 오탐하므로 전달용 이름과 정확히 일치할 때만 |
| `instead of the above`·`do not follow`·`you must`·URL 전부 | **안 가져옴.** 오탐이 크고 우리 규칙이 이미 더 좁게 잡는다 |

근거와 한계는 [DECISIONS.md](DECISIONS.md)의 D-73. 라이선스는 MIT지만 코드는 가져오지 않고 규칙만 새로 썼다.

## 4. 가져오지 않을 것

- Redactor·응답 스캐너: Gitleaks·Presidio가 이미 더 넓다.
- DID·메시지 서명·Merkle: 우리 서명 토큰·해시 체인과 중복.
- 하네스 훅 플러그인: 사용자가 끌 수 있어 강제 수단이 못 된다. 훅은 비강제 신호로만 가치가 있고, 추가하면 하네스를 고치지 않는다는 방향과 어긋난다.
- Server Card(SEP-2127)와 MCP09 로드맵: AGT 쪽도 "계획 중"이라 참고할 구현이 없다.

## 5. 확인 못 한 것

- AGT의 시험 결과·성능 주장은 시험하지 않았다.
- 새 규칙은 랩 서버(filesystem·git 등)의 도구 원문으로는 재지 못했다. 기기 DB에 있는 서버는 원격 SaaS 8개뿐이다.
- 서버 이름 없이 도구 이름만 합치는 하네스(Gemini CLI 등)에서 같은 이름의 도구가 모델을 헷갈리게 하는지는 확인하지 않았다.
