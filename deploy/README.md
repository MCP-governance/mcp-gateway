# MINT 운영 배포

고객 서버 한 대에 MINT를 올리는 묶음입니다. 실습용 직원 PC·시나리오·MCP 서버·추적 수집기·메일 수신기는 들어 있지 않습니다.

## 요구 사항

| 항목 | 값 |
| --- | --- |
| 서버 | Linux x86_64, Docker Engine 24 이상, Docker Compose v2, `git`, `openssl`, `python3` |
| 자원 | 4 vCPU · 16 GB 메모리 · 40 GB 디스크(GitHub `ubuntu-latest` 실행기에서 설치를 검증) |
| 네트워크 | 관리형 직원 PC만 닿는 사내 IPv4 하나(VPN·사설 구간). 이미지 빌드와 도입 심사에 인터넷 출구 |
| 게시 포트 | 그 주소의 `443`(HTTPS: 콘솔·MCP·IdP·내부 Git)과 `3128`(관리형 하네스의 모델 API 프록시) |

## 설치

```bash
git clone --branch v0.9.0 https://github.com/MCP-governance/mcp-gateway.git
cd mcp-gateway/deploy
./install.sh --bind <사내 IPv4> [--name <DNS 이름>]
```

1. `.env`를 만들고 비밀 값·서명 키를 생성합니다(`.env.example` 참고).
2. 이미지를 `mcpgw/*:<판본>`으로 빌드하고 게이트웨이·콘솔·검사기를 올립니다.
3. HTTPS를 열기 전에 관리자 `root`의 비밀번호를 임의 값으로 바꿔 `initial-admin-password`에 적습니다.
4. Caddy·모델 프록시를 올리고 사설 루트 인증서를 `ca/root.crt`로 내보냅니다.

설치가 끝나면 `https://<사내 IPv4>/`에서 `root`로 로그인하고 `./mint.sh set-password root`로 비밀번호를 바꿉니다.
브라우저에는 `ca/root.sha256` 지문을 대조한 뒤 `ca/root.crt`를 넣습니다.

## 직원 PC 연결

직원이 콘솔에 로그인 → **내 PC 연결** → 자기 OS의 키트를 받아 실행합니다. 키트에는 루트 인증서와 지문이 들어 있어 따로 배포하지 않습니다.
자세한 내용은 [엔드포인트 키트](../endpoint-agent/README.md)를 봅니다.

## 운영 명령

| 명령 | 하는 일 |
| --- | --- |
| `./mint.sh status` | 서비스 상태, 판본, 준비 여부, 정책 일치 |
| `./mint.sh add-account <아이디> --role 관리자\|직원` | 계정 추가(비밀번호는 프롬프트·표준 입력) |
| `./mint.sh set-password <아이디>` | 비밀번호 변경 |
| `./mint.sh ca` | 루트 인증서·지문 다시 내보내기 |
| `./mint.sh backup [디렉터리]` | DB·폐기 목록·내부 Git·CA·설정 백업 |
| `./mint.sh restore <백업>` | 백업에서 복구 |
| `./mint.sh upgrade` | 백업 뒤 현재 체크아웃 판본으로 재기동 |
| `./mint.sh up [--with-siem]` | 기동·재기동 |
| `./mint.sh logs [서비스]` · `down` | 로그 · 정지(데이터 유지) |
| `./mint.sh litellm enable\|check\|status\|rotate-key\|disable` | LiteLLM 동기화 켜기·점검·상태·관리 키 회전·끄기 |
| `./mint.sh compose <인자>` | 같은 설정으로 `docker compose` |

### LiteLLM 연동(선택)

중앙 AI 게이트웨이(LiteLLM 1.105)를 쓰는 기업은 MINT 승인·철회를 LiteLLM에 자동 반영한다.

```bash
./mint.sh add-account <아이디> --role 직원 --ai-gateway      # PC 키트 없이 LiteLLM으로만 쓰는 직원
./mint.sh litellm enable --url https://<LiteLLM 관리 origin> --bindings 매핑.json --route mint < 관리-키-파일
./mint.sh litellm status
```

`--route mint`(기본)는 LiteLLM의 MCP 서버가 MINT를 거치고, `direct`는 LiteLLM이 원래 서버로 보내며 가드레일이 MINT 판정을 받는다.
LiteLLM 설정 견본과 매핑 형식은 [addons/litellm](../addons/litellm/README.md), 동작과 한계는 [LiteLLM 동기화](../docs/ai/LITELLM_SYNC.md)에 있습니다.

백업·복구·업그레이드·롤백·사설 CA 절차와 그 이유는 [운영 런북 1부](../docs/ai/RUNBOOK.md#1부-운영-배포-deploy)에 있습니다.

## 구성

| 서비스 | 이미지 | 역할 |
| --- | --- | --- |
| `caddy` | `caddy:2.11.4-alpine` (digest 고정) | HTTPS 종단·경로 분기, 사설 CA |
| `gateway` | `mcpgw/gateway:<판본>` | MCP 호출 중계·판정·원장 |
| `agent-service` | `mcpgw/gateway:<판본>` | 운영 콘솔·IdP |
| `opa` | `openpolicyagent/opa:1.20.2-static` (digest 고정) | 정책 판정 |
| `presidio-analyzer` · `presidio-anonymizer` | `mcpgw/presidio-analyzer:<판본>` · Presidio 2.2.364 (digest 고정) | 개인정보 탐지·가림 |
| `db` | `postgres:18.6-alpine3.24` (digest 고정) | 판정·승인 원장 |
| `intake-worker` | `mcpgw/intake-worker:<판본>` | 도입 신청 공급망 검사 |
| `runtime-worker` | `mcpgw/runtime-worker:<판본>` | 승인한 소스 MCP 빌드·격리 실행 |
| `corp-git` | `gitea/gitea:1.27.3-rootless` (digest 고정) | 승인된 소스의 사내 사본 |
| `model-proxy` | `mcpgw/model-proxy:<판본>` | 관리형 하네스의 모델 API 목적지 제한 |
| `siem-worker`(선택) | `mcpgw/gateway:<판본>` | OCSF 이벤트 SIEM 전달 |

추적은 고객의 OpenTelemetry 수집기가 있을 때 `.env`의 `OTEL_SDK_DISABLED=false`와 `OTEL_EXPORTER_OTLP_ENDPOINT`로 켭니다.
`runtime-worker`는 승인한 MCP를 실행하려고 Docker 소켓을 받습니다. 이 서버는 MINT 전용으로 둡니다.
