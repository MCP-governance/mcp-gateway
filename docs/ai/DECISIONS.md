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
