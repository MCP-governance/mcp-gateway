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
