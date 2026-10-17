# DEV-53·DEV-56 목적지 고정과 오류 인증정보 가림

기준: `9537c0b494a0c4d45c615caa4797674f273d270f`, 기존 브랜치 `10/17-dest-transport`, 시작 시 clean. 브랜치 변경·커밋·푸시 없음. [WBS G03.05·G03.08](../feature-spec-2026-10-17/README.md), [레퍼런스](../../papers/policy50-gap-references.md), [D-116·117](../../../../docs/ai/DECISIONS.md), [보고](../../status/reports/2026-10-17-dest-pin-credential-redaction.md).

## 원자 요구사항과 증거

| ID | 요구사항·실패 조건 | 코드 심볼 | 단위 시험 | 남은 검증 |
| --- | --- | --- | --- | --- |
| A53-01 | 외부 endpoint의 DNS 전체 공인 주소 검사; 혼합·mapped·metadata·실패 차단 | `destination.PinnedBackend.connect_tcp` | `test_every_address_must_be_safe_before_connect`, `test_resolution_failure_empty_and_timeout_are_closed` | 실제 DNS·IPv6 |
| A53-02 | 검사 IP로만 접속, 원래 SNI·인증서 검증·Host | `pin_transport`, `upstream._client` | 공개→loopback resolver 두 응답·숫자 connector | 실제 풀 시험 파일 추가, 의존성 없어 미실행; TLS 미실행 |
| A53-03 | 등록/실행기 단일 라벨 네트워크 위치로 내부 판단; deployment는 사용하지 않음 | `upstream._internal_endpoint` | 실제 catalog email/gitea provider 정상·GitHub private DNS 차단·ACTIVE 실행기·미승인 alias | compose 10종·실행기·건강 확인 |
| A53-04 | OAuth 관련 조회에도 동일 검사 | OIDC `PinnedOAuthApp`, `PinnedOAuthClient`, `http_transport`; refresh/introspection/end_session | 새 backend·redirect/proxy 비활성·실제 compose의 loopback issuer와 keycloak discovery/백채널·미승인 사설 호스트/포트 차단 | Authlib discovery/JWKS/토큰·철회 |
| A53-05 | 정확한 차단 ID와 연결 우회 방지 | `core._upstream_failure`, 종료 HEAD, `experiments.session_termination` | cause의 `Block/MCP-EGRESS-001` | SDK ExceptionGroup·풀 회수·E2 |
| A56-01 | 원장 error와 하네스 error를 저장/반환 전 가림 | `redact_error`, `_record_decision`, `_decision_payload`, `_render` | GitHub/JWT/sk·INSERT 인자·해시 전 값·응답 대조 | 네이티브 검사기·DB 해시·SDK |
| A56-02 | query·Authorization·검사 장애·예외 원문 비반환 | `_CREDENTIAL_CONTEXT`, HTTP 오류·검증 handler, MCP handler | percent query·짧은 자격·장애·예외 | 실제 오류/미탐 및 정상 진단 코퍼스 |
| A56-03 | 키트의 하네스 파일·인자에 토큰 없음 | field renderers, `endpoint_plane.managed_policy`, 양 OS `apply_policy` | 임시 HOME/CODEX_HOME, 전체 CLI 인자와 파일 쓰기 | 실제 설치·하네스 실행·회전/철회 |

메인 검토 후 16개 시험이 production AST의 선택 함수와 실제 field 키트를 실행해 통과했다. 실제 HTTPX 풀 시험 2개는 의존성 부재로 명시적 skip이며 통과로 세지 않는다. DB·네이티브 검사기·OS ACL은 대역이며 실제 MCP 서버를 만들거나 실행하지 않았다. [초기 검증 이력](validation.json)은 보존하며 [검토 수정 검증](review-validation.json)이 현재 코드의 근거다. 초기 deployment 분류·loopback issuer 한정 설명은 D-116 정정으로 대체됐다.

## OSS·공개 스킬 검토

- 기존 `gateway/requirements.txt`: HTTPX 0.28.1, HTTPX2 2.12.0, Authlib 1.6.12. 새 의존성·외부 코드 복사 없음.
- [HTTPX2 transport](https://github.com/pydantic/httpx2/blob/main/src/httpx2/httpx2/_transports/default.py)·[httpcore2 connection](https://github.com/pydantic/httpx2/blob/main/src/httpcore2/httpcore2/_async/connection.py) 본문에서 origin 유지/TCP backend 위임 구조를 확인했다. [라이선스](https://github.com/pydantic/httpx2/blob/main/LICENSE.md)는 BSD 3-Clause 조건이다. Pydantic이 유지하는 기존 의존성의 backend 연동만 사용한다. 열람판 main의 commit SHA 및 설치된 2.12.0과의 바이트 일치는 미확인(태그/commit 조회 실패). 실제 dependency 환경의 풀 시험을 완료 조건으로 남긴다.
- [Authlib v1.6.12 registry](https://github.com/authlib/authlib/blob/v1.6.12/authlib/integrations/base_client/registry.py)·[Starlette app](https://github.com/authlib/authlib/blob/v1.6.12/authlib/integrations/starlette_client/apps.py)·[metadata](https://github.com/authlib/authlib/blob/v1.6.12/authlib/integrations/base_client/async_app.py)를 확인했다. register의 `client_cls`는 HTTP client가 아닌 app subclass이므로 두 층을 유지했다. 기존 Authlib(BSD) 연동 범위이며 태그 commit SHA는 미확인이다.
- [LIB-K09 SSRF](../../papers/LIB-K09.md)·[LIB-K10 Smokescreen](../../papers/LIB-K10.md)·[LIB-K25 Secrets](../../papers/LIB-K25.md)를 재사용하고 공식 OWASP 본문 및 Smokescreen README를 확인했다. DNS 전체 검사·접속 IP 결속·오류 비밀 비보존을 채택한다. Smokescreen(MIT)은 별도 프록시가 필요해 이번에는 채택하지 않는다. 서버 자체 outbound 해결로 주장하지 않는다.
- GitHub [yaklang SSRF skill](https://github.com/yaklang/hack-skills/blob/main/skills/ssrf-server-side-request-forgery/SKILL.md)은 검색 후보로 확인했다. 공격 시험 중심으로 본 작업에 채택·실행하지 않았다. 후보 commit·라이선스는 미확인이다. 외부 지시·스크립트는 실행하지 않았다.

## 호환성과 한계

`_pool._network_backend`는 비공개 접점이다. URL IP 치환은 SNI/Host/풀 origin 복원이 필요해 선택하지 않았다. 기존 backend에는 숫자 IP만 전달한다. warm socket은 새 DNS가 필요 없고 새 연결에서 다시 검사한다. internal 분류 변경은 풀 키도 바꾼다. 첫 검증 IP 실패 시 다른 IP fallback은 없으므로 가용성을 확인해야 한다.

OIDC는 설정한 issuer/discovery URL의 loopback·단일 라벨 호스트/포트를 내부 예외로 둔다. `keycloak:8080` 동적 백채널은 같은 authority라 허용한다. metadata가 다른 사설 호스트/포트를 지목하면 자동 승인하지 않는다. 외부 FQDN이 private IP로 바뀌는 재바인딩은 계속 차단한다. MCP upstream 자동 OAuth client는 구성되지 않았다. Gateway protected-resource metadata는 응답 생성이며 외부 조회가 아니다.

오류는 500자 초과·Secret 탐지·검사 장애 시 전체 가림이다. 정상 진단 일부도 가려질 수 있다. 과거 원장은 수정하지 않는다. 임의 비밀의 완전 탐지·사용자가 직접 넣은 비밀 제거·MCP 서버 outbound·DEV-64·OS 집행은 완료 범위가 아니다.
