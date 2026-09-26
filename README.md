# MCP Gateway — Proxy

`Proxy` 브랜치는 MCP 서버 앞에 두는 작은 **HTTP 리버스 프록시**입니다.
클라이언트는 `/mcp/<서버 이름>/`에 연결하고, 프록시는 설정에 적힌 upstream MCP 엔드포인트로 통신을 전달합니다.

```text
MCP 클라이언트 → /mcp/demo/ → HTTP 스트리밍 프록시 → 실제 MCP 서버 /mcp
```

JSON-RPC 본문을 파싱하거나 MCP 서버를 다시 구현하지 않습니다. 도구 이름·스키마·결과·이미지·리소스·프롬프트,
초기화 응답과 오류는 upstream이 보낸 그대로 전달됩니다. GET/POST/DELETE와 SSE 스트림, `Mcp-Session-Id`,
`MCP-Protocol-Version`, `Last-Event-ID`를 유지하며 세션의 생성·종료·재개는 upstream이 담당합니다.
세션 헤더와 GET 스트림·DELETE 종료는 2025-03-26~2025-11-25 개정판의 방식이고, 세션이 없는 2026-07-28 개정판의
요청도 같은 경로로 전달합니다. 시험은 두 방식을 모두 공식 SDK로 확인합니다.

이 브랜치의 실행 경로에는 DB·OPA·Presidio·승인·감사 원장·Console·직원 PC 실습이 없습니다.
기존 거버넌스 테스트베드와 문서는 `main`과 Git 이력에서 확인할 수 있습니다. `research/`는 멘토님 디렉터리라 그대로 둡니다.

## 로컬에서 실행

Python 3.12 이상과 [uv](https://docs.astral.sh/uv/)가 필요합니다. Windows, Linux, WSL에서 같은 명령을 사용합니다.

```bash
git clone --branch Proxy https://github.com/MCP-governance/mcp-gateway.git
cd mcp-gateway
uv sync --frozen
uv run --frozen python examples/demo_server.py
```

다른 터미널에서:

```bash
uv run --frozen mcp-gateway --config proxy.toml --port 8080
```

- 클라이언트 MCP URL: `http://127.0.0.1:8080/mcp/demo/`
- 프록시 생존 확인: `http://127.0.0.1:8080/api/health` (upstream 정상 여부를 뜻하지 않음)
- 기본 바인딩은 `127.0.0.1`. 데모 서버에는 `echo` 도구, 리소스, 프롬프트가 있습니다.

클라이언트 설정 예시(HTTP MCP를 지원하는 클라이언트):

```json
{
  "mcpServers": {
    "demo": {
      "type": "http",
      "url": "http://127.0.0.1:8080/mcp/demo/"
    }
  }
}
```

프로덕션 프록시만 설치할 때는 `uv sync --frozen --no-dev`를 사용합니다.
MCP SDK는 데모·호환성 시험에만 필요하며 프록시 런타임에는 포함되지 않습니다.

## 서버 연결 설정

`proxy.toml`에 서버별 URL을 적고 재시작합니다. `/mcp/demo`와 `/mcp/demo/` 모두 같은 URL로 전달되며
뒤에 임의 경로를 붙일 수 없습니다. 미등록 서버는 404입니다. 설정 오류는 기동 전에 실패합니다.

```toml
[proxy]
connect_timeout_seconds = 10
read_timeout_seconds = 0  # 0: SSE 읽기 대기 제한 없음; 양수: 읽기 사이의 대기 시간
write_timeout_seconds = 30
shutdown_timeout_seconds = 5       # 종료 시 열린 SSE를 기다리는 최대 시간; 지나면 끊음
max_connections_per_server = 100   # 서버별 upstream 연결 수; 열려 있는 SSE도 하나씩 차지
allowed_origins = []     # Origin 없는 네이티브 클라이언트 허용; 브라우저는 정확한 Origin을 등록

[servers.filesystem]
url = "http://127.0.0.1:9001/mcp"

[servers.remote]
url = "https://mcp.example.com/mcp"
[servers.remote.headers]
Authorization = { env = "REMOTE_MCP_AUTHORIZATION" }
X-Api-Key = { env = "REMOTE_MCP_API_KEY" }
```

환경 변수의 Authorization 값은 `Bearer ...`까지 포함합니다. 변수는 실행 환경에 직접 주입합니다.
`.env` 파일을 자동으로 읽지 않습니다. 컨테이너에서 자격이 필요하면 Compose의 `environment` 또는 `env_file`로 주입하세요.
설정 파일 경로는 `--config` 또는 `MCP_PROXY_CONFIG`로 지정할 수 있습니다.

클라이언트의 `Authorization`은 upstream에 넘기지 않습니다. upstream 자격은 해당 서버 설정의 별도 헤더로 공급합니다.
설정된 헤더는 같은 이름의 클라이언트 헤더보다 우선합니다. `Host`는 목적지에 맞게 만들고 hop-by-hop 헤더는 제거합니다.
응답의 중복 헤더와 압축 본문을 보존하며, 연결 풀의 쿠키를 다른 요청에 자동으로 재사용하지 않습니다.
본문 없이 온 GET·DELETE는 본문 없이 전달합니다(빈 chunked 본문을 만들지 않습니다).

연결 풀은 서버마다 따로 둡니다. MCP 클라이언트는 보통 세션마다 GET SSE 스트림을 하나씩 열어 두므로,
한 서버의 스트림이 `max_connections_per_server`에 닿으면 그 서버의 새 요청만 `connect_timeout_seconds`만큼
빈 연결을 기다린 뒤 503을 받고, 다른 서버는 영향을 받지 않습니다.

이 프록시에는 자체 로그인·권한 판정이 없습니다. 기본 실행은 로컬용이며 공유 배포의 인증과 TLS는 앞단에서 구성합니다.
upstream이 요구하는 자격도 별도로 구성해야 합니다. OAuth 로그인·메타데이터 URL을 프록시 경로로 바꾸는 기능은 없습니다.

## Docker로 실행

```bash
docker compose up --build --wait
```

프록시와 데모 upstream 두 컨테이너만 실행합니다. 프록시는 호스트 `127.0.0.1:8080`에 게시되며 데모는 호스트에 게시하지 않습니다.
다른 랩과 포트가 겹치면 `MCP_PROXY_PORT`를 바꿉니다. Compose의 TOML은 `proxy.docker.toml`입니다.

실제 서버를 연결하는 경우 `MCP_PROXY_CONFIG_FILE`에 자체 TOML 경로를 설정하고 프록시만 실행합니다.
컨테이너 안의 `127.0.0.1`은 컨테이너 자신을 뜻하므로, upstream 주소는 컨테이너에서 접근 가능한 주소여야 합니다.

```bash
docker compose up --build --wait proxy
docker compose down
```

## 검증

```bash
uv sync --frozen
uv run --frozen python -m pyflakes mcp_gateway tests examples
uv run --frozen pytest -q
# Compose 데모가 실행 중인 경우:
uv run --frozen python tests/container_smoke.py --url http://127.0.0.1:8080
```

시험은 공식 MCP SDK 2.2.0의 handshake 연결과 자동 협상 연결에서 tools/resources/prompts를 확인합니다.
실제 소켓에서 동시 세션, SSE 즉시 전달·클라이언트 연결 해제, 요청 스트리밍과 timeout을 확인하고,
회귀 시험은 원문·상태·세션 헤더·압축·중복 헤더·별도 자격·오류·재시도 없음·설정 검증을 확인합니다.
서버별 연결 풀 분리, 본문 없는 요청, 열린 SSE가 있을 때의 종료 시간도 실제 소켓으로 확인합니다.
CI는 `Proxy`와 `proxy-*` 브랜치의 Python 시험 및 컨테이너 데모, CodeQL 분석을 실행합니다.
작업 브랜치는 `proxy-<주제>`로 만듭니다. `proxy/<주제>`는 Windows·macOS처럼 대소문자를 구분하지 않는
파일 시스템에서 `Proxy` ref와 경로가 겹쳐 `git fetch`가 실패합니다.

## 범위

HTTP(S) MCP upstream과 Streamable HTTP의 SSE 응답을 지원합니다.
stdio 변환, 2024-11-05의 별도 `/sse`·메시지 엔드포인트 변환, 여러 서버를 하나로 합치는 `/mcp/`, WebSocket은 제공하지 않습니다.
stdio 서버는 별도 HTTP 어댑터를 앞에 두고 등록할 수 있습니다.

upstream HTTP 오류·리다이렉트는 원래 상태와 본문을 반환합니다. 프록시 자체의 연결 실패는 502, 응답 헤더를 받기 전의
시간 초과는 504, 해당 서버의 연결 한도 초과는 503입니다. 자동 재시도와 리다이렉트 추적은 하지 않습니다.
이미 시작된 스트림의 오류는 연결을 종료합니다. 연결이 끊긴 요청의 실행 여부는 upstream에서 확인해야 합니다.
프록시를 멈추면 열린 SSE를 `shutdown_timeout_seconds`까지 기다린 뒤 끊고 upstream 연결을 닫습니다.
클라이언트는 다시 연결해야 합니다.

구현은 [mcp_gateway/](mcp_gateway/), 설정은 [proxy.toml](proxy.toml), 설계 결정은 [docs/ai/DECISIONS.md](docs/ai/DECISIONS.md)에 있습니다.
