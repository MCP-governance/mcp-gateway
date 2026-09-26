# MCP Gateway — Proxy

`Proxy` 브랜치는 MCP 서버 앞에 두는 작은 **HTTP 리버스 프록시**입니다.
클라이언트는 `/mcp/<서버 이름>/`에 연결하고, 프록시는 설정에 적힌 upstream MCP 엔드포인트로 통신을 전달합니다.

```text
MCP 클라이언트 → /mcp/demo/ → HTTP 스트리밍 프록시 → 실제 MCP 서버 /mcp
```

JSON-RPC를 재직렬화하거나 MCP 서버를 다시 구현하지 않습니다. 도구 이름·스키마·결과·이미지·리소스·프롬프트,
초기화 응답과 오류는 upstream이 보낸 그대로 전달됩니다. GET/POST/DELETE와 SSE 스트림, `Mcp-Session-Id`,
`MCP-Protocol-Version`, `Last-Event-ID`를 유지하며 세션의 생성·종료·재개는 upstream이 담당합니다.
세션 헤더와 GET 스트림·DELETE 종료는 2025-03-26~2025-11-25 개정판의 방식이고, 세션이 없는 2026-07-28 개정판의
요청도 같은 경로로 전달합니다. 시험은 두 방식을 모두 공식 SDK로 확인합니다.

프록시가 더하는 것은 중계의 **앞과 옆**에만 있고, 전달하는 바이트는 바꾸지 않습니다.

| 어디 | 무엇 | 기본값 |
| --- | --- | --- |
| 전달 전 | 미등록 서버·Origin 거부, 클라이언트 인증(프록시 키 또는 LiteLLM 가상 키), 키별 서버 허용, 분당 한도 | 인증 없음 |
| 전달 중 | 요청·응답 **사본**에서 JSON-RPC 메서드·도구 이름·결과(성공·도구 오류·프로토콜 오류)를 읽어 SQLite에 기록 | 예시 설정에서 켬 |
| 옆 | 웹 콘솔(`/console/`), 관리 API, Prometheus 지표, upstream 도달 확인 | 관리자 토큰이 있을 때만 |

정책 엔진(OPA)·개인정보 검사·승인·해시 체인 감사 원장·직원 PC 실습은 없습니다. 그것은 `main`의 거버넌스 테스트베드입니다.
`research/`는 멘토님 디렉터리라 그대로 둡니다.

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
- 준비 확인: `/api/ready` — 도달 확인에서 `down`인 서버가 있으면 503
- 콘솔: 아래 [콘솔](#콘솔) 참고. `MCP_PROXY_ADMIN_TOKEN`(16자 이상)을 주고 실행하면 `http://127.0.0.1:8080/console/`
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

TLS는 앞단에서 구성합니다. upstream이 요구하는 자격은 서버별 헤더로 따로 공급합니다.
OAuth 로그인·메타데이터 URL을 프록시 경로로 바꾸는 기능은 없습니다(본문을 새로 만드는 일이라 프록시의 선 밖입니다).

## 클라이언트 인증

`[auth] providers`가 비어 있으면 누구나 쓸 수 있으므로 기본 바인딩이 loopback입니다. 공유 배포에서는 인증을 켭니다.
클라이언트는 `Authorization: Bearer <키>` 또는 `x-litellm-api-key`로 키를 보내고, **이 헤더는 어느 upstream에도 전달되지 않습니다**
(인증을 끈 상태에서도 제거합니다 — LiteLLM 키가 실수로 MCP 서버에 새지 않게).

```toml
[auth]
providers = ["keys", "litellm"]        # 둘 중 하나만 써도 됩니다
litellm_url = "http://127.0.0.1:4000"
litellm_cache_seconds = 60
litellm_default_servers = []           # 메타데이터에 서버가 없는 LiteLLM 키가 쓸 서버("*" = 전부)
default_rate_per_minute = 0            # 0 = 무제한
```

- **프록시 키**(`mcpp_…`): 콘솔 "클라이언트 키"에서 발급합니다. 원문은 발급 응답에만 있고 저장소에는 SHA-256만 남습니다.
  키마다 쓸 수 있는 서버, 분당 한도, 만료를 정하고 사용 중지하면 다음 요청부터 거부됩니다. `[store] path`가 필요합니다.
- **LiteLLM 가상 키**(`sk-…`): 프록시가 그 키로 LiteLLM `GET /key/info`를 불러 검증합니다. 직원은 모델과 MCP에 **같은 키 하나**를
  쓰고, 키 발급·차단·만료는 LiteLLM 관리 화면에서 합니다. 쓸 수 있는 서버는 키 메타데이터 `mcp_proxy_servers`(예: `["demo"]`),
  분당 한도는 `mcp_proxy_rate_per_minute`로 정합니다. LiteLLM에 닿지 못하면 **거부(503)**합니다. 가상 키에는 DB가 있는 LiteLLM이 필요합니다.
- 없는 키·중지된 키·만료된 키는 401(`WWW-Authenticate: Bearer`), 허용되지 않은 서버는 403, 한도 초과는 429(`Retry-After`)입니다.
  거부는 전부 전달 **전**에 일어나고, 콘솔에 사유와 함께 기록됩니다.

## 호출 기록

`[store] path`를 두면 중계한 요청마다 한 행을 SQLite(WAL)에 남깁니다. 기록은 관찰용입니다: 큐가 넘치거나 디스크 쓰기에
실패하면 요청을 막지 않고 기록을 버리며, 버린 건수를 콘솔과 지표가 보여줍니다.

- 요청 사본(256KiB까지): JSON-RPC 메서드, `tools/call`의 도구 이름, `resources/read`의 URI, `prompts/get`의 이름,
  `initialize`의 clientInfo(이후 같은 세션의 행에도 클라이언트 이름을 붙임), 프로토콜 버전
- 응답 사본(JSON·SSE, gzip·deflate 해제): 요청 id에 대한 결과 — 성공, `isError` 도구 오류, JSON-RPC 오류(코드·메시지),
  응답이 오기 전에 끊긴 미완료. SSE 이벤트 수와 서버가 보낸 요청·알림 메서드
- 그 밖: 사용자(키 이름·LiteLLM 키 별칭, 인증이 없으면 IP), HTTP 상태, 응답 시작·전체 시간, 주고받은 바이트
- **남기지 않는 것**: 세션 ID 원문(해시만), 헤더 값, 응답 본문. 도구 인자는 개인정보를 담을 수 있어
  `record_arguments = true`일 때만 4KB까지 남깁니다. 보관 기간은 `retention_days`(기본 14일).

결과 분류: 성공 · 도구 오류 · 프로토콜 오류 · 미완료 · upstream 오류(HTTP 4xx·5xx, 스트림 도중 끊김) · 프록시 오류(502·503·504,
LiteLLM 불능) · 거부(401·403·404·429).

## 콘솔

`[admin] token`(예시 설정은 `{ env = "MCP_PROXY_ADMIN_TOKEN" }`)이 있을 때만 `/console/`과 관리 API(`/admin/api/*`),
지표(`/admin/metrics`)가 생깁니다. 토큰이 없으면 이 경로들은 404입니다. 화면은 `main`의 거버넌스 콘솔과 같은 디자인
시스템(토큰·차트 래퍼·안전한 HTML 템플릿·탭·드로어)을 가져왔고, 콘솔은 **MCP를 호출하지 않습니다**.

| 화면 | 보는 것 |
| --- | --- |
| 개요 | 요청·성공률·도구 호출·거부·진행 중·서버 정상·응답 시작 p95, 시간대별 결과, 결과 비율, 메서드·도구 상위, 서버별 결과와 지연, 사용자 → 서버 → 결과 흐름, 클라이언트 비율 |
| 활동 로그 | 3초 실시간(일시정지 가능), 서버·결과·사용자 필터와 검색, 시간 분포, 행을 누르면 요약·요청·응답·원본 |
| MCP 서버 | 도달 확인 상태·지연 추이, 24시간 요청·실패율·p95, 연결 사용량, 서버별 도구와 최근 실패, 즉시 확인 |
| 클라이언트 키 | 발급(원문은 한 번만 표시)·서버 권한·분당 한도·만료·사용 중지, 24시간 요청·거부 |
| 설정 | 적용된 설정(자격 값과 URL 쿼리는 가림), 기록 파일 크기 |

- 관리자 토큰은 브라우저 탭의 `sessionStorage`에만 둡니다. 모든 관리 응답은 CSP(`script-src 'self'; style-src 'self'`),
  `frame-ancestors 'none'`, `nosniff`, `no-store`를 붙이고, 기록 문자열은 이스케이프하며 차트 툴팁은 캔버스로 그립니다.
- 도달 확인은 `[health] interval_seconds`마다 upstream URL에 JSON을 요청하는 **HTTP GET**입니다(MCP 요청이 아님).
  500 미만의 응답이면 정상으로 봅니다. 기본값은 꺼짐이고 예시 설정에서 30초입니다.
- 지표는 Prometheus 텍스트: `mcp_proxy_requests_total{server,outcome}`, `mcp_proxy_active_requests`, `mcp_proxy_upstream_up`,
  `mcp_proxy_records_dropped_total`. 설정에 없는 서버 이름은 `(unknown)` 한 라벨로 묶습니다.

## Docker로 실행

```bash
MCP_PROXY_ADMIN_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(24))") docker compose up --build --wait
```

토큰 없이 실행하면 콘솔만 꺼집니다. 기록은 `proxy-data` 볼륨에 남고 `docker compose down -v`로 지웁니다.
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
node --test tests/console-state.test.mjs          # 콘솔의 DOM 없는 상태 모듈
# Compose 데모가 실행 중인 경우(토큰을 주면 콘솔과 기록까지 확인):
uv run --frozen python tests/container_smoke.py --url http://127.0.0.1:8080 --admin-token "$MCP_PROXY_ADMIN_TOKEN"
```

시험은 공식 MCP SDK 2.2.0의 handshake 연결과 자동 협상 연결에서 tools/resources/prompts를 확인합니다.
실제 소켓에서 동시 세션, SSE 즉시 전달·클라이언트 연결 해제, 요청 스트리밍과 timeout을 확인하고,
회귀 시험은 원문·상태·세션 헤더·압축·중복 헤더·별도 자격·오류·재시도 없음·설정 검증을 확인합니다.
서버별 연결 풀 분리, 본문 없는 요청, 열린 SSE가 있을 때의 종료 시간도 실제 소켓으로 확인합니다.
기록을 켠 상태에서도 요청·응답 바이트가 같은지, 결과 분류·키 인증·LiteLLM 키(가짜 LiteLLM)·장애 시 거부·속도 제한,
관리 API의 토큰·가림·CSP·JavaScript MIME, 지표 라벨, 도달 확인을 시험합니다.
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
