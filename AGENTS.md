# Proxy 브랜치 작업 규칙

이 브랜치는 MCP Streamable HTTP 리버스 프록시다. 사용자가 요청한 단순 프록시 범위가 기준이다.
거버넌스 테스트베드는 `main`에 있으며 여기의 런타임이나 시험에 의존시키지 않는다.

먼저 [README.md](README.md)와 [docs/ai/DECISIONS.md](docs/ai/DECISIONS.md)를 읽는다.
메인 에이전트가 직접 작업한다. 다른 작업 트리나 실행 중인 서비스를 멈추지 않는다.

## 동작 경계

- MCP 본문을 파싱·재직렬화하지 않고 스트리밍한다. 도구 이름·결과·오류·세션을 새로 만들지 않는다.
- URL은 기동 시 읽은 설정의 서버별 고정 목적지다. 요청 본문·추가 경로에서 목적지를 정하지 않는다.
- 클라이언트 Authorization을 upstream에 전달하지 않는다. upstream 자격은 서버별 설정에서 별도로 공급한다.
- hop-by-hop 헤더 제거와 목적지 Host 변경을 제외한 응답 상태·헤더·본문을 보존한다.
- 자동 재시도·리다이렉트 추적 금지. 쓰기 호출을 중복 실행할 수 있다.
- 정상 완료·오류·연결 해제 모두 upstream 연결을 정리한다. 대기 중인 SSE에도 적용한다.
- 기본 바인딩과 Compose 게시 주소는 loopback. 공유 배포의 인증은 별도 앞단에서 구성한다.
- 새 정책·DB·로그인·콘솔·MCP SDK 런타임 의존성을 더하려면 먼저 사용자의 범위를 확인한다.
- 연결 풀은 서버별로 둔다. 한 서버의 열린 SSE가 다른 서버의 연결을 막지 않게 한다.
- `research/`는 멘토님 디렉터리다. 내용이 README 하나여도 수정하거나 지우지 않는다.

## 검증과 Git

```bash
uv sync --frozen
uv run --frozen python -m pyflakes mcp_gateway tests examples
uv run --frozen pytest -q
docker compose -p mcpgw-proxy-check up --build --wait
uv run --frozen python tests/container_smoke.py --url http://127.0.0.1:8080
docker compose -p mcpgw-proxy-check down
git diff --check
```

포트가 겹치면 `MCP_PROXY_PORT`로 피하고 자기 Compose 프로젝트만 정리한다.
변경한 실행 경로에 맞는 시험과 문서를 갱신한다. 잠금 파일은 `uv lock`으로 갱신한다.
`Proxy` 또는 `proxy-<주제>`에서 작업한다. `proxy/...`는 Windows·macOS에서 `Proxy` ref와 충돌한다.
`main`에 직접 푸시하거나 Proxy를 `main`에 병합하지 않는다. 병합은 사용자가 정하며 D-37의 되돌리기 커밋을 먼저 revert해야 한다.
