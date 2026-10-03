# 오픈소스 채택과 Audit API / UI 정리

## 채택과 대체 경계

| 영역 | 채택 | 변화 | 유지할 책임 |
| --- | --- | --- | --- |
| 조직 로그인 | Keycloak 26.8.0 + Authlib 1.6.12 | 자체 비밀번호 검증 대신 OIDC Code + PKCE. state·nonce·서명·issuer·audience 검증은 Authlib | 사용자 관리대장, 독립 관리자 활성화, 단말 인증, 논문 실험용 합성 IdP |
| Secret 탐지 | Gitleaks 8.30.1 기본 규칙 | Gateway 전송 인자·마스킹 후 응답·도입 저장소 검사, 실패 시 통과 불가 | 기존 보수적 패턴, Presidio 개인정보/응답 마스킹, OPA 인가 |
| 감사 조회 | 기존 FastAPI/PostgreSQL Audit API | 필터·페이지·상세·검증·내보내기. 원장과 head를 동일 스냅샷으로 읽음 | append-only 원장, 실행/응답 미확인 보존 |

Authlib 1.6.12는 확인한 BSD-3-Clause 보안 수정 버전으로 고정한다. Keycloak Apache-2.0, Gitleaks MIT.
Envoy는 현재 MCP/계약/OPA 판단을 그대로 대체하지 못하고 OpenSearch는 공식 원장을 대체하지 않는다.
현재 제어점에서 위 엔진을 사용한다. 운영 SSO 자격·MFA/디렉터리 연결을 임의로 설정하지 않는다.

## Keycloak 로컬 기동과 전환

1. 기존 스택을 `./console.sh up --no-llm`으로 기동한다. 별도 검증 설치는 포트를 먼저 .env에 지정한다.
2. `python3 scripts/keycloak_env.py`로 .env에 무작위 자격을 생성한다. 값은 출력하지 않으며 기존 값은 보존한다.
3. `docker compose -f compose.yaml -f compose.keycloak.yaml up -d --build keycloak agent-service gateway gateway-sse`.
   기본 Keycloak은 loopback 18090, 콜백은 Console 18000이다. 다른 Console 포트는 `OIDC_REDIRECT_URI`를 지정한다.
   오버레이는 로컬 검증용 start-dev/내장 DB다. field 운영 설정이 아니다.
4. Keycloak 관리자 화면의 mcpgw realm에 사용자를 생성한다. 사용자나 관리자 binding을 자동 생성하지 않는다.
5. 기존 관리자가 Console **정책 → 조직 SSO → SSO 신원 연결**에서 Keycloak 사용자 id(sub)와 기존 사용자 id를 연결한다.
   이메일/공급자 role로 자동 연결하지 않는다. 관리자 신원도 먼저 연결한 뒤 전환한다.
6. 운영자가 .env의 `AUTH_PROVIDER=oidc`를 지정하고 같은 오버레이로 agent-service/gateway/gateway-sse를 재기동한다.
   로그인은 SSO 버튼만 표시한다. 로컬 Console/OAuth password·refresh grant/Git Basic 비밀번호와 기존 비장치 토큰은 거부한다.
   기존 관리형 단말의 장치 인증은 유지한다. OIDC Git clone에는 별도 Gitea 자격이 필요하다.

issuer/callback은 HTTPS만 허용하고 loopback만 HTTP 예외다. Keycloak backchannel dynamic 설정으로
브라우저 issuer를 고정하고 token/JWKS/introspection은 내부 주소를 사용한다. TLS 검증은 끄지 않는다.
Keycloak 26.8의 introspection audience 검사를 위해 client에 `console-audience` mapper를 둔다.
기존 realm은 import로 덮어쓰지 않으므로 클라이언트에 같은 mapper를 별도로 적용해야 한다.
원격 도입은 운영자가 주소·client·자격·TLS·DB를 설정해야 한다.

인증 후 60초짜리 HttpOnly handoff를 한 번 소비해 조직 세션을 발급한다. 외부 access token은 AES-GCM으로
암호화해 서버에 보관하고 요청마다 introspection을 확인한다. 확인 실패는 503, 폐기·만료는 401이다.
binding 해제와 조직 계정 중지도 차단한다. 조직 세션은 외부 access token 수명을 넘지 않는다.
외부 refresh token은 보관하지 않는다. Console 로그아웃이 벤더의 다른 앱 세션까지 종료한다고 주장하지 않는다.
단말 키는 별도의 조직 관리대장·device epoch로 검증한다. Keycloak 사용자 삭제/binding 해제가 단말 키까지
자동 회수하지 않는다. 단말 접근 종료는 기존 사용자 중지·장치 회수 절차로 수행한다. callback의 code/state는
Uvicorn access log에서 제거한다.

## Secret 검사

도입 워커는 운영자 소유 gitleaks.toml에서 기본 규칙을 확장한다. 제출 저장소의 자체 설정/ignore 파일과
gitleaks:allow 주석으로 검사를 우회하지 못하게 한다. 파일 스냅샷 검사이며 Git 전체 이력 검사는 아니다.
발견은 HIGH로 기록하고 기존 위험 검토 절차를 따른다. 탐지가 자격의 유효성/실제 유출을 증명하지 않는다.
다운로드 보고서는 규칙·파일·행 정보만 남기고 Secret/Match를 제거한다. Gateway는 stdin 검사로 규칙 id만
OPA에 전달한다. 응답 개인정보 마스킹은 Presidio가 담당한다.
URL 쿼리는 기본 규칙의 구분자 제한을 보완하기 위해 디코딩한 값도 별도로 검사한다.
마스킹 후에도 Gitleaks가 Secret을 발견하면 실행 후 응답을 보류한다(`MCP-OUTPUT-001`).
기존 낮은 엔트로피의 토큰·회사 가상 키 패턴은 Presidio의 응답 마스킹에도 쓰이므로 유지한다.

## Audit API

관리자 Console scope가 필요하다. events는 최신부터 최대 500건, before는 이전 페이지 경계다.
decision/server/principal/policy/event_kind/execution/since/until/trace_id 필터와 시간대를 포함한 시각을 사용한다.
execution=unknown은 실행 시도는 있었지만 효과는 미확인인 기록이다. 차단/미전송으로 바꾸지 않는다.
export는 최대 5000건 페이지, has_more/next_before, 전체 체인 검증 결과를 read-only REPEATABLE READ
스냅샷에서 반환한다. manifest SHA-256은 payload의 UTF-8 compact JSON·키 정렬 결과다.
검증은 DB 원문을 대상으로 한다. 민감 필드를 뺀 내보내기만으로 원문 체인을 재구성할 수 없다.
독립 서명·외부 보관·위변조 불가능성 증명으로 설명하지 않는다.

## UI

| 화면 | 변화 |
| --- | --- |
| 로그인 | provider에 따라 로컬 폼/SSO 버튼. 설정 실패 시 로컬 로그인으로 자동 후퇴하지 않음 |
| 정책 → 조직 SSO | 발급자·콜백·전환 상태, 관리자 연결 기록, 연결/해제 |
| 정책 → 구성요소 | 설치/설정/실행 확인 및 각 엔진의 적용 범위 |
| 도입 검증 보고서 | Gitleaks 단계, 별도 Secret 탭, 정제 보고서 다운로드 |
| 감사 증거 | 필터·상세·이전 기록·검증·내보내기 |

기존 CSP/escape/native dialog/색상·폼 토큰을 유지한다. Gateway와 Linux 관리형 계정의 통제 범위를 확대했다고 주장하지 않는다.

## 검증

2026-10-03, 별도 WSL checkout/Compose 프로젝트 `mcpgw-oss-20261003`의 loopback 설치에서 확인했다.

- 필수 `./console.sh test` 전체 통과: Rego 103개, 공격 42/42 차단, 정상 16/16 허용,
  하네스 4종 × MCP 10종, 실제 DB 효과 검사, 정책 재생 192/192 일치, E1/E2/E3.
- 추가 검사 10/10 통과: 관리자 API 경계·시간대·페이지·민감 본문 제외, 로컬 인증 우회 거부,
  handoff·암호화·로그 보호, 실제 Gitleaks의 URL 쿼리/allow 주석 검사. 일부 경계 검사는 모의 DB를 사용한다.
- 실제 Keycloak Code + PKCE 로그인/API 검사 24개 통과: 관리자·직원 권한 분리, 미연결 신원 거부,
  handoff 재사용 거부, 기존 토큰/password/refresh 거부, state 검증, 공급자 로그아웃 후 접근 거부.
  Keycloak 중지 중 503 차단도 확인했다. Chrome에서도 SSO 로그인 후 정책·조직 SSO·감사 화면을 확인했다.
- 실제 Gitleaks 워커 이미지: 제출 저장소의 allow 설정/ignore/주석 우회 거부와 정제 보고서를 확인했다.
  실제 Gateway/MCP에서는 URL Secret 탐지, 미전송, 읽기 실행 후 응답 보류, 검사기 장애 차단을 확인했다.
  테스트 HTTP 수신 서버 로그에 차단 요청이 없었다. 테스트 파일·검사기·합성 사용자 상태는 원복했다.
- 실제 Chrome 감사 JSON 다운로드: manifest SHA-256 일치, 체인 정상, 민감 본문 제외 확인.
  UI의 필터·상세·키보드 열기/닫기·체인 검증과 구성요소/SSO 연결 화면을 확인했다.
- Python lint, JS 문법, 무인증 경계 검사 통과. OpenAPI는 실행 이미지에서 재생성해 새 경로를 확인했다.

로컬 검증 후 로그인 모드는 `local`로 원복했다. 위 결과는 운영 디렉터리/MFA/실기기 SSO 배포 증거가 아니다.
실행 보고서는 해당 검증 설치의 `full_stack_lab/reports/oss-*.json`에 있다. 자격과 토큰은 커밋하지 않는다.

## 근거

- [Keycloak Docker](https://www.keycloak.org/getting-started/getting-started-docker)
- [Authlib Starlette OIDC](https://docs.authlib.org/en/v1.5.2/client/starlette.html)
- [Authlib 1.6.12 검증 구현](https://github.com/authlib/authlib/blob/v1.6.12/authlib/integrations/base_client/async_openid.py)
- [Gitleaks 사용법](https://github.com/gitleaks/gitleaks/blob/master/README.md)
