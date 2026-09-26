# Proxy 브랜치 작업 규칙

이 브랜치는 MCP Streamable HTTP 리버스 프록시다. 사용자가 정한 범위(D-36 단순 프록시, D-38 "프록시의 선을 넘지 않는"
인증·기록·콘솔)가 기준이다.
거버넌스 테스트베드는 `main`에 있으며 여기의 런타임이나 시험에 의존시키지 않는다.

먼저 [README.md](README.md)와 [docs/ai/DECISIONS.md](docs/ai/DECISIONS.md)를 읽는다.
메인 에이전트가 직접 작업한다. 다른 작업 트리나 실행 중인 서비스를 멈추지 않는다.

## 동작 경계

- 전달하는 바이트를 바꾸지 않는다. JSON-RPC를 재직렬화하지 않고, 도구 이름·결과·오류·세션을 새로 만들지 않는다.
  응답 본문을 고치는 기능(tools/list 거르기, 도구 이름 접두어, 여러 서버 합치기)은 프록시의 선 밖이다.
- 기록은 요청·응답의 **사본**만 읽는다. 관찰용이라 실패해도 중계를 막지 않고, 버린 건수를 드러낸다.
  세션 ID 원문·헤더 값·응답 본문은 남기지 않고, 도구 인자는 `record_arguments`일 때만 남긴다.
- 거부(인증·키별 서버·속도 제한·Origin)는 전달 **전에만** 한다. 인증 백엔드(LiteLLM)에 닿지 못하면 거부한다.
- URL은 기동 시 읽은 설정의 서버별 고정 목적지다. 요청 본문·추가 경로에서 목적지를 정하지 않는다.
- 클라이언트 자격 헤더(`Authorization`, `x-litellm-api-key`)는 인증을 켜지 않았어도 어떤 upstream에도 전달하지 않는다.
  upstream 자격은 서버별 설정에서 별도로 공급한다.
- hop-by-hop 헤더 제거와 목적지 Host 변경을 제외한 응답 상태·헤더·본문을 보존한다.
- 자동 재시도·리다이렉트 추적 금지. 쓰기 호출을 중복 실행할 수 있다.
- 정상 완료·오류·연결 해제 모두 upstream 연결을 정리한다. 대기 중인 SSE에도 적용한다.
- 기본 바인딩과 Compose 게시 주소는 loopback. 사내망 게시는 `compose.field.yaml`의 Caddy(TLS 443) 하나뿐이고
  그 설정은 키 인증을 켠다(D-43). 평문 HTTP를 사내망에 게시하지 않는다.
- 직원 PC 키트(`field/pc/mcpgw_pc.py`)는 표준 라이브러리만, Python 3.9 문법으로. 키 원문을 하네스 설정·환경 변수·로그에
  쓰지 않고, 사용자의 기존 하네스 설정을 덮어쓰지 않는다. 시험은 임시 HOME·CODEX_HOME에서만 한다.
- 콘솔·관리 API는 관리자 토큰이 있을 때만 생기고 MCP를 호출하지 않는다. 도달 확인은 HTTP GET이지 MCP 요청이 아니다.
- 정책 엔진·응답 변형·MCP SDK 런타임 의존성을 더하려면 먼저 사용자의 범위를 확인한다
  (기록·인증·콘솔은 D-38에서 사용자가 범위를 넓혔다).
- 연결 풀은 서버별로 둔다. 한 서버의 열린 SSE가 다른 서버의 연결을 막지 않게 한다.
- `research/`는 멘토님 디렉터리다. 내용이 README 하나여도 수정하거나 지우지 않는다.

## 검증과 Git

```bash
uv sync --frozen
uv run --frozen python -m pyflakes mcp_gateway tests examples field
uv run --frozen pytest -q
node --test tests/console-state.test.mjs
MCP_PROXY_ADMIN_TOKEN=local-console-token-0123 docker compose -p mcpgw-proxy-check up --build --wait
uv run --frozen python tests/container_smoke.py --url http://127.0.0.1:8080 --admin-token local-console-token-0123
docker compose -p mcpgw-proxy-check down -v
git diff --check
```

포트가 겹치면 `MCP_PROXY_PORT`로 피하고 자기 Compose 프로젝트만 정리한다.
변경한 실행 경로에 맞는 시험과 문서를 갱신한다. 잠금 파일은 `uv lock`으로 갱신한다.
`proxy` 또는 `proxy-<주제>`에서 작업한다. `proxy/...`는 Windows·macOS에서 `proxy` ref와 충돌한다.
`main`에 직접 푸시하거나 Proxy를 `main`에 병합하지 않는다. 병합은 사용자가 정하며 D-37의 되돌리기 커밋을 먼저 revert해야 한다.
