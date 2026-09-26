# Proxy 설계 결정

## D-36 서버별 고정 목적지에 HTTP 바이트 스트림을 전달 (2026-09-26)

사용자 요청: `Proxy` 브랜치를 만들고 단순 프록시 형태로 리팩토링해 푸시한다.
기준 커밋은 `main`의 `dacc1ce`다. D-01~D-35의 거버넌스 설계와 전체 랩은 `main` 및 Git 이력에 보존한다.

기존 `mcp_facade`가 MCP 서버 역할을 대신하고 DB·신원·분류·개인정보 검사·OPA·계약·감사에 의존하던 구조를
서버별 TOML 목적지와 HTTP 스트리밍 전달로 교체한다. 해당 목적지의 MCP 구현이 초기화·협상·도구·리소스·프롬프트·세션을 책임진다.
프록시는 JSON-RPC를 파싱하지 않아 임의 메서드·결과 유형을 전달하고 HTTP(S) upstream만 연결한다.

`/mcp/<서버>/` 경로는 유지한다. upstream URL의 경로와 쿼리를 설정에서 고정하고 요청 쿼리만 뒤에 이어 붙인다.
추가 경로·집계 서버·stdio·legacy HTTP+SSE 변환·OAuth URL 재작성은 범위에 넣지 않는다.

클라이언트 Authorization을 제거하고 upstream 자격을 서버별 환경 변수 헤더로 공급한다.
고정 목적지, Origin 검사, loopback 기본값, 환경 프록시 무시, 리다이렉트 추적과 재시도 없음은 작은 HTTP 전달 경계에 남긴다.
공유 AsyncClient에는 매 요청 새 Request를 전달해 쿠키 저장소가 다른 클라이언트의 자격을 자동으로 붙이지 못하게 한다.

응답은 raw byte stream으로 전달해 압축·Content-Length·이미지·메타데이터를 보존한다.
중복 헤더는 raw header 목록으로 유지한다. Connection이 지정한 추가 hop 헤더도 양쪽에서 제거한다.
ASGI 버전과 무관하게 disconnect를 감시하고 finally에서 upstream을 닫는다. SSE 읽기 제한은 기본 0(무제한)이다.

시험과 CI도 이 실행 경로로 교체한다. MCP SDK는 공식 클라이언트 호환성 시험과 데모 전용 개발 의존성이다.
프록시 운영 의존성은 AnyIO·HTTPX·Starlette·Uvicorn이며 `uv.lock`으로 고정한다.

## D-37 서버별 연결 풀, 본문 없는 요청, 종료 시간 제한, 브랜치 이름 (2026-09-26)

사용자 요청: 실수로 `main`에 병합된 #27을 되돌리고(#28, 되돌리기 커밋 `b4de4fe`), Proxy 브랜치의 부족한 부분을 채운다.

D-36의 공유 AsyncClient는 HTTPX 기본 한도인 연결 100개를 모든 서버가 나눠 썼다. 열린 SSE 스트림은 연결을 계속 잡고 있어서
한 서버에 스트림 100개가 열리면 다른 정상 서버의 요청까지 연결을 기다리다 "upstream timeout" 504를 받았다.
서버마다 AsyncClient를 따로 두고 `max_connections_per_server`(기본 100)로 한도를 정한다. 한도 초과는 시간 초과와 구분해 503으로 답한다.

`request.stream()`을 그대로 넘기면 HTTPX가 빈 본문도 `Transfer-Encoding: chunked`로 보내 본문 없는 GET·DELETE가
본문 있는 요청으로 바뀌었다. GET 본문을 거부하는 중간 장비나 서버를 거치면 SSE 열기와 세션 종료가 실패한다.
첫 조각을 먼저 읽고 비어 있으면 본문 없이 보낸다. 헤더 대신 실제로 받은 본문으로 판단하므로 ASGI 서버 종류와 무관하다.

Uvicorn은 기본적으로 모든 연결이 끝날 때까지 종료를 기다리는데 SSE는 스스로 끝나지 않는다. 열린 스트림이 하나만 있어도
프록시가 멈추지 않았고 Compose는 SIGKILL까지 기다렸다. `shutdown_timeout_seconds`(기본 5)가 지나면 요청을 취소하며,
RelayResponse의 finally가 upstream 연결을 닫는다.

작업 브랜치 규칙 `proxy/...`는 대소문자를 구분하지 않는 파일 시스템에서 `refs/remotes/origin/Proxy` 파일과
`refs/remotes/origin/proxy/` 디렉터리가 겹쳐 fetch가 실패한다. `proxy-<주제>`로 바꾸고 CI 트리거도 맞춘다.

D-36에서 CI를 교체할 때 함께 지워진 CodeQL 분석과 멘토님 디렉터리 `research/`를 되살린다.
Proxy를 다시 `main`에 병합할지는 사용자가 정한다. 병합한다면 `b4de4fe`를 먼저 revert해야 프록시 변경이 들어간다.

## D-38 프록시의 선 안에서 인증·기록·콘솔 (2026-09-26)

사용자 요청: "프록시라는 선을 넘지 않는 지점에서 할 수 있는 개선을 다 한다. 웹 UI는 main의 것을 가져와도 된다."
LiteLLM 1.89.4의 MCP 게이트웨이를 코드로 대조했다(main의 `docs/ai/BENCHMARK_LITELLM.md`). LiteLLM은 스스로 MCP 서버가 되어
도구 목록을 거르고 이름에 접두어를 붙이고 여러 서버를 합친다 — 본문을 새로 만드는 일이라 그 부분은 가져오지 않았다.

**선**: 전달하는 바이트는 바꾸지 않는다. 프록시는 전달 **전에** 거부할 수 있고, 전달 **중에** 사본을 읽을 수 있고, 중계
**옆에** 관리 화면을 둘 수 있다. 응답을 고치거나 MCP를 대신 말하는 것은 선 밖이다.

- **인증**(`auth.py`): 프록시 키(`mcpp_…`, SHA-256만 저장, 키별 서버·분당 한도·만료·중지)와 LiteLLM 가상 키. LiteLLM 키는
  그 키로 `GET /key/info`를 불러 검증한다 — LiteLLM 소스에서 키가 자기 정보를 조회할 수 있음을 확인했다
  (`key_management_endpoints._can_user_query_key_info`: `api_key == key`). 만료·차단 키는 LiteLLM 인증 단계에서 먼저 거부된다.
  서버 권한은 키 메타데이터 `mcp_proxy_servers`에 둔다. LiteLLM의 `object_permission.mcp_servers`는 LiteLLM에 등록한 서버 id라,
  쓰려면 같은 서버를 LiteLLM에도 등록해야 해서 택하지 않았다. LiteLLM에 닿지 못하면 거부(503) — LiteLLM의 옵트인 fail-open과 반대다.
  클라이언트 자격 헤더는 인증 여부와 상관없이 upstream에 보내지 않는다(MCP 인가 명세의 토큰 전달 금지).
- **기록**(`observe.py`, `store.py`): 요청·응답 사본에서 메서드·도구·결과를 뽑아 SQLite(WAL)에 남긴다. LiteLLM의
  `StandardLoggingMCPToolCall`을 참고하되 도구 인자는 기본으로 남기지 않는다. 쓰기는 백그라운드 큐가 하고, 넘치거나 실패하면
  기록을 버리고 센다 — 관찰 기능이 중계를 멈추게 해서는 안 된다. SSE는 줄 단위로 읽고 gzip·deflate는 사본만 푼다.
- **콘솔**(`admin.py`, `console/`): main 콘솔의 디자인 토큰·차트 래퍼·안전한 HTML 템플릿·탭·드로어를 가져왔다. 판정 5색 대신
  중계 결과 7종을 쓴다. 관리자 토큰이 없으면 라우트 자체가 없다. MCP를 호출하지 않는 원칙(main D-01)을 그대로 따른다 — 서버
  상태는 HTTP GET 도달 확인, 도구 목록은 중계된 호출에서 본 이름이다. 한글 글꼴(3.9MB)은 패키지를 가볍게 두려고 넣지 않았다.
- **도달 확인**: LiteLLM은 MCP 세션을 열어 확인하지만(`health_check_server`), 프록시가 MCP 클라이언트가 되면 선을 넘는다.
  JSON을 달라는 GET을 보내 500 미만이면 정상으로 본다. 요청하지 않은 트래픽이라 기본값은 꺼짐.
- **Windows에서 찾은 결함**: `mimetypes`가 레지스트리를 읽어 `.mjs`를 `text/plain`으로 내보내 브라우저가 모듈 스크립트를
  거부했다. JavaScript MIME을 명시로 등록하고 시험에 넣었다.

가져오지 않은 것: `tools/list` 거르기·의미 기반 도구 선택·도구 이름 접두어·서버 합치기(응답 변형), legacy SSE 변환(재직렬화),
OAuth 메타데이터 합성, `oauth_passthrough`류 토큰 전달, 서버 CRUD(서버는 TOML이 정본이고 바꾸면 재시작).
