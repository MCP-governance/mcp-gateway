# IBM ContextForge와 CPEX 소스 분석 — 2026-09-30 정정본

이 문서는 Gateway 저장소 하나를 검색한 결과를 IBM 전체 제품의 부재로 해석하지 않는다.
아래는 다운로드한 공개 소스의 정적 분석이다. IBM 스택을 띄운 통합·부하 시험 결과가 아니며,
플러그인이 존재한다는 사실과 실제 배포에서 enforce로 활성화되었다는 사실을 구분한다.

## 분석 기준과 이전 보고서 정정

| 저장소 | 검토 커밋 | 범위 |
| --- | --- | --- |
| [IBM/mcp-context-forge](https://github.com/IBM/mcp-context-forge/tree/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324) | `5735c9db7f8f50cd5a55eb7fefe83ecde00b5324` | 인증·토큰 교환·스코프, 플러그인 설정과 PDP 연결 |
| [IBM/cpex-plugins](https://github.com/IBM/cpex-plugins/tree/ae26938128cb438a268e7f3217603bc39b9dd18f) | `ae26938128cb438a268e7f3217603bc39b9dd18f` | 공개 Rust/Python 탐지·호출 제한 구현 |

최초 Claude 보고서는 `cpex-*` 코드를 ContextForge 저장소에서 찾지 못해 **비공개**라고 기록했다.
이는 잘못된 결론이다. CPEX 플러그인은 위의 별도 공개 저장소에 있다. 탐지 로직의 재사용이
불가능하다거나 IBM의 원자성이 확인되지 않았다는 기존 비교를 설계·영업 근거로 사용하면 안 된다.
플러그인 프레임워크 전체의 예외 처리와 실제 운영 설정은 이번 실행 검증 대상이 아니므로 미확인이다.

우리 Gateway가 사용자 SSO 토큰을 upstream으로 패스스루한다는 기존 기술도 잘못됐다.
입구 사용자 토큰과 벤더 자격은 분리되어 있다. 이번 개선에서는 정확한 HTTPS resource와 등록 주체에
결합한 별도 자격 파일을 읽는다. 이것은 RFC 8693 token exchange나 사용자별 OAuth 수명주기 구현은 아니다.

## 소스에서 확인한 통제

### 신원, 자원 스코프, 대리 실행

`mcpgateway/middleware/rbac.py`, `utils/token_scoping.py`는 역할 외에 토큰·팀·소유권을 판정한다.
이는 “하네스 이름 승인”보다 신뢰할 수 있는 서버 측 인가 근거다. 사용자가 보낸 `clientInfo`는 인증된 앱 신원이 아니다.

[`services/oauth_manager.py`](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/mcpgateway/services/oauth_manager.py)는
`token-exchange` grant를 별도로 처리한다. subject token이 없으면 거부하고, target audience와 scope를
교환 요청에 넣으며, Bearer 응답 유형을 검증한다. `utils/subject_token.py`의 입력 보호도 함께 봐야 한다.
코드의 존재만으로 모든 SaaS가 교환을 지원한다고 결론 내릴 수 없다. 발급자·audience·교환 서버의
정책을 연결하는 실제 IdP 시험이 추가로 필요하다.

우리 PAC-05는 사용자 역할에 하네스 자기 신고를 교차시키지 않는다. 검증 가능한 장치·앱 신원과
교환 가능한 IdP가 없는 현재 배치에서 위임을 흉내 내는 필드를 추가하지 않는다.

### 호출량의 원자성

[`rate_limiter/src/redis_backend.rs`](https://github.com/IBM/cpex-plugins/blob/ae26938128cb438a268e7f3217603bc39b9dd18f/plugins/rust/python-package/rate_limiter/src/redis_backend.rs)는
여러 제한 차원을 하나의 Lua 배치에서 검사·반영한다. `SCRIPT LOAD`/`EVALSHA`와 `NOSCRIPT` 시 `EVAL`
경로가 실제 구현되어 있다. 따라서 “설정 주석에 Redis만 있고 원자성 소스가 없다”는 비교는 틀렸다.
메모리 백엔드의 프로세스 범위와 Redis 백엔드의 공유 범위는 구분해야 한다.

호출량 제한과 **실행 중인 작업의 자리·중복·응답 유실**은 다른 요구사항이다. 우리 구현은 기존
PostgreSQL에 주체별 advisory lock과 `call_reservations`를 두고, 먼저 도착한 요청을 함께 센다.
실행 여부가 불명인 작업은 응답을 잃었다고 자리를 즉시 풀지 않는다. lease 만료 뒤 원격 작업의
정확히 한 번 실행까지 보장하는 설계는 아니다. IBM 구현도 같은 시나리오로 실행 시험하기 전에는
어느 쪽이 더 강하다는 순위를 붙이지 않는다.

### 내용 탐지와 URL 검사

| 공개 소스 경로 (`cpex-plugins`) | 확인한 역할 | 우리 쪽에 가져올 관점 |
| --- | --- | --- |
| `plugins/rust/python-package/pii_filter/` | 중첩 payload 개인정보 탐지·마스킹 | 입력과 결과의 처리 결과를 구분하고 정상 데이터 대조군을 둔다 |
| `plugins/rust/python-package/secrets_detection/` | 자격·비밀 패턴 탐지 | 단순 키워드보다 유형별 정밀도를 측정한다 |
| `plugins/rust/python-package/encoded_exfil_detection/src/lib.rs` | base64/base64url/hex/escaped hex, entropy·suspicion, decode depth 한도 | 인코딩 우회를 별도 공격군으로 평가한다; 무제한 재귀 디코딩은 피한다 |
| `plugins/rust/python-package/sql_sanitizer/` | SQL 위험 문장·변경 분석 | 읽기라는 도구 이름을 신뢰하지 않는다 |
| `plugins/rust/python-package/url_reputation/` | allow/block/pattern/heuristic URL 판정 | URL 평판과 DNS·리디렉션·네트워크 격리의 보장을 혼동하지 않는다 |

우리 `poisoning.py`의 정규식은 알려진 지시문 신호의 검사다. 완전한 프롬프트 주입 방어라고 주장하지 않는다.
인코딩 탐지를 즉시 전체 도구 결과에 붙이지 않은 이유는 임계값·성능·정상 base64 데이터의 오탐이
검증되지 않았기 때문이다. 공개 소스를 분석·참조할 수 있지만, 새 Rust 실행 의존성을 지금 추가하지 않는다.

### 정책 훅과 실패 처리

ContextForge의 `plugins/config.yaml`과 `plugins/unified_pdp/engines/opa_engine.py`,
`plugins/external/opa/opapluginfilter/plugin.py`는 내용·자원·도구 훅을 정책 엔진과 연결한다.
기본 disabled 항목과 선택적으로 켠 항목을 구분해야 한다. PDP timeout, 플러그인 오류, 외부 서비스
장애가 실제 ingress에서 어떤 실행 효과를 내는지에는 런타임 시험이 필요하다.

## 우리 구조에 적용한 결론

1. 승인 대상은 설치 가능한 모든 확장 프로그램이 아니라 **등록된 resource·도구 계약·주체·유효기간**이다.
2. endpoint agent와 native managed policy는 직접 MCP 경로를 제한한다. 셸·브라우저·독립 앱의 API 호출은
   네트워크·OS·IdP 통제가 필요하다. Gateway가 통제했다는 로그가 없는 경우를 “허용”으로 집계하지 않는다.
3. SQL AST는 문법을 판정할 뿐 DB의 view·함수·operator 부작용까지 증명하지 못한다. 검토되지 않은 함수는
   고위험으로 분류하고, 실서비스는 DB 권한과 읽기 전용 계정을 함께 적용해야 한다.
4. 경쟁 제품의 부재를 차별점으로 내세우기 전에 공개 별도 저장소와 외부 PDP 구성을 조사한다.
5. 재사용할 것은 입력 검증·분리된 자격·원자적 제한·장애 시 효과 시험이다. 플랫폼 전체를 이식하지 않는다.

## 후속 비교 시험의 조건

IBM을 실행 비교할 때는 플러그인 버전과 mode, Redis 실제 연결, 실패 정책을 고정한다. 동일한 주체로
동시 burst를 보내고 Gateway 응답뿐 아니라 별도 DB 변화·호스트 패킷을 관측한다. 입력 공격과 정상
대조군은 동일 프로토콜을 쓴다. 결과에 미확인 상태, 사후 마스킹, 실행 전 거부를 따로 기록한다.
이번 우리 클린 테스트 결과와 범위는 [OVERHAUL_VALIDATION_2026-09-30.md](OVERHAUL_VALIDATION_2026-09-30.md)에 기록한다.
