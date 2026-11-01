# full_stack_lab — MINT 게이트웨이와 실습 스택

사내망 직원 PC의 AI 하네스(Claude Code·Codex CLI·Gemini CLI·OpenCode) → 게이트웨이(`/mcp/<server>/`) → 실제 MCP 서버 10종 → 회사 시스템.
같은 스택을 실제 기기에 올리는 field 모드는 [8절](#8-실제-기기로-배치하기).
설계는 [../docs/ai/ARCHITECTURE.md](../docs/ai/ARCHITECTURE.md), 운영은 [../docs/ai/RUNBOOK.md](../docs/ai/RUNBOOK.md).

> 이 디렉터리는 개발·검증용 실습 스택이다. 고객 서버 운영 배포는 [../deploy/](../deploy/README.md)를 쓴다.

솔루션 기기에서는 `./console.sh field up`으로만 기동한다. 개발 노트북·WSL에서는 스택을 띄우지 않고 정적 검사와 일회성 OPA 시험까지만 한다.
아래 `up`·전체 회귀 명령은 GitHub CI 일회용 스택용이며, 실제 하네스 기능 시험은 지정 시험 PC에서 한다.

## 1. 실행

```bash
./console.sh up            # 전체 (첫 실행: 빌드 + qwen3.5:2b-q4_K_M 다운로드)
./console.sh up --no-llm   # LLM 없이 — 직원 PC의 하네스 도구 호출은 MCP Inspector CLI가 대신(scripted)
./console.sh status        # 서비스 상태와 MCP 서버 준비 수
```

| 주소(기본 포트) | 내용 |
| --- | --- |
| `http://localhost:8000` | 콘솔 (`CONSOLE_PORT`) |
| `http://localhost:8080/api/health` | 게이트웨이 (`GATEWAY_PORT`) |
| `http://localhost:16686` | Jaeger (`JAEGER_PORT`) |
| `http://localhost:3000` | 회사 Gitea — 제공자 콘솔 역할 (`GITEA_PORT`, `corpadmin`) |

CI 기본 스택은 `127.0.0.1`에만 게시됩니다. 합성 계정: 관리자 `kkg@bob.local`·`mks@bob.local`,
직원 `ysg@`(플랫폼개발팀)·`jwj@`(데이터분석팀)·`pse@`(보안기술팀)·`miso@`, 협력사 `nkk@`.

## 2. 직원의 하루

```bash
./console.sh workday                 # 네 명 전원, 각자의 하네스로(LLM 모드)
./console.sh workday ws-jwj --mode scripted --check
./console.sh ask ws-ysg "payment-service 최근 커밋 3개 요약해 줘" --servers git
./console.sh harnesses               # PC 4대 × 하네스 4종이 관리형 서버 10종에 다 붙는지(모델 불필요)
./console.sh watch                   # 판정을 사람이 읽는 한 줄로
```

직원 PC에는 Claude Code·Codex·Gemini CLI·OpenCode 네 하네스가 모두 설치돼 있고(주 하네스는 PC마다
다름), `bob-ask`가 그중 하나를 헤드리스로 부릅니다. 관리형 MCP 설정은 `registry/catalog.toml`에서
이미지 빌드 때 생성됩니다. 시나리오(`workstation/scenarios/*.toml`, 21건)는 실제 업무와 실제 위험을 섞었습니다.

| 직원 | 하는 일 | 보이는 통제 |
| --- | --- | --- |
| 정원재(데이터분석팀) | 주간 매출 집계, 고객 원장 조회, 보고서 작성, 외부 파트너에게 공유 | 중요정보 경보·**결과의 주민번호·전화번호 마스킹**, **열람→외부 전송 연쇄 차단** |
| 권노경(협력사 A) | 작업지시서, 감사 사본(예외 EXC-001), 급여표·코드 수정·외부 업로드 시도 | 예외 경보, 최소권한 차단, 섀도 MCP 증적 강화 |
| 박소은(보안기술팀) | 보안 공지, 협력사 FAQ(**간접 프롬프트 주입** 페이지), 세션 키 점검, Gitea 관리 API 조회 | 주입 표지 차단, **SSRF 차단**, 지식 그래프 기록 |
| 양승권(플랫폼개발팀) | 배포 체크리스트, 커밋·이슈 확인, 샌드박스 테스트 실행, 배포 공지 메일, 비밀 저장소 호기심 | **승인형 예외(EXC-002)**, 중요정보 경보 |

## 3. 콘솔

관리자 메뉴는 **대시보드 · 승인 대기 · 호출·감사 기록 · MCP 서버 · 사용자·엔드포인트 · 정책 · 도입 신청 · 종료·폐기 · 내 연결**의 9개다.
대시보드는 처리할 일·시간대별 판정·서버별 호출·최근 경보를 표시한다. 승인 대기에 이용 동의, 호출·감사 기록에 엔드포인트 호출·경보·감사 원장·사고 기한·관제 전달을 모은다.
MCP 서버에는 커넥터·통제 범위, 정책에는 하네스 기능, 사용자·엔드포인트에는 통제 점검·MCP 설정, 도입 신청에는 엔드포인트 요청·공급망 영향을 둔다. 기본 기능과 기본 커넥터는 기본 승인이고 관리자가 항목별로 차단한다.
호출 상세는 경로·정책 판정·도구 실행·업무 결과를 분리하고 차단·경보에서 근거·해당 기기로 연결한다. 경보는 기간·묶음·미열람 수를 제공하고 엔드포인트 검색·필터와 상세·페이지를 주소에서 복원한다.
직원·협력사는 **호출 기록 · 이용 동의 · 도입 신청 · 내 연결**을 쓴다. 바로가기의 **PC 연결 설정**에서 키트를 받고 **사내 저장소**는 읽기만 한다. 직원의 직접 다운로드·클론·쓰기는 막고 승인 소스는 콘솔·키트로 받는다.
직원 PC의 `mint`·`mint ui`도 상태·MCP 서버·호출 기록·도입 요청을 제공한다. 훅 기록은 호출 전 집행 증거가 아니며 최신 조회 기능의 배포·실기기 검수는 [개발 현황](../research/llm-wiki/status/current.md)에서 확인한다.
구조: [../docs/ai/CONSOLE_UI.md](../docs/ai/CONSOLE_UI.md).

## 4. 종료·폐기 시연

1. **종료·폐기** → 서버 이름으로 된 이용 관계 카드마다 예상 결과를 확인한다. 실제 결과는 **완전 종료·부분 종료·종료 확인 불가**로 구분한다(UR-EMAIL-ASSIST는 제공자
   자격 고지가 없어 **T3**, UR-GITEA-DEV는 **T1**).
2. UR-GITEA-DEV **종료 시작** → 즉시 차단(`MCP-DECOMM-001`), 회수 대상 자동 열거.
3. **증거 수집** → 이용 주체별 차단 확인(상태 증거), Gitea의 mcp-bot 토큰은 **아직 있음**(상태 증거).
4. **판정** → **T2**(모집단·증거는 확정, 제공자 보유 자격 미회수).
5. **조직 권한으로 폐기** → 삭제 응답 204(처리 증거) + 재확인 "자격 없음"(상태 증거) → **판정** → **T1** → **종결**.
6. UR-EMAIL-ASSIST로 반복 → **T3**, 위험 수용 없이는 종결 거부, **제공자 고지 요청서** 생성.
7. 실습 복원 후 `./console.sh restore-token gitea`.

자동 버전: `python3 tests/termination_flow.py`. 논문 실험: `./console.sh experiment e1|e2|e3`.
판정 규칙: [../docs/ai/TERMINATION_MODEL.md](../docs/ai/TERMINATION_MODEL.md).

## 5. 검증

```bash
TERMINATION_DISPOSABLE_LAB=1 ./console.sh test          # CI 일회용 스택에서만, 영구 폐기 시험 포함
./console.sh replay 100                               # 기록된 정책 입력 100건 + 합성 사례를 후보 정책에 재생
REPLAY_POLICY_DIR=./candidate-opa ./console.sh replay  # 후보 정책 디렉터리 지정 (MCP 호출 없음)
```

`tests/protocol_versions_check.py`는 D-116 목적지 보호를 유지한다. `InputRequiredResult` 확인에 쓰는 임시 제공자 URL만 시험 안에서 내부 목적지로 승인하므로 실제 loopback SDK 연결이 가능하고, URL이 다르면 승인되지 않는다. DNS 확인·IP 고정은 계속 적용된다.

망 대역 self-check → 도입 검증 단위 시험(네트워크 없는 컨테이너) → 콘솔 상태(node) → Rego → 실기기 키트·오버레이 검사 →
분류기 → 게이트웨이 인수 시험 → 하네스 연결 점검 → 업무 시나리오 대조 → 종료 판정 흐름 → 보안 회귀 → 정책 재생 → E1~E3.
결과는 `reports/`. 층별 설명: [../docs/ai/TESTING.md](../docs/ai/TESTING.md).

망 12개는 모두 `.env`의 `MCP_NET_PREFIX`(처음 실행 때 다른 Docker 망·라우트와 겹치지 않는 `10.200`~`10.249` 중
하나를 자동 선택) 아래 `/24`를 명시해 만들므로, 한 호스트에 랩을 여러 벌 띄워도 Docker 기본 주소 풀이 소진되지
않습니다. 이 방식 이전에 만든 복제본은 `./console.sh down` 뒤 `up`하면 새 대역으로 옮겨집니다(볼륨 유지).

## 6. 열려 있는 API

게이트웨이 API 중 토큰 없이 열려 있는 것은 다음뿐입니다: `/api/health` (구성요소 상태와 준비된 MCP 서버 수).
로그인(`/api/session`)·키트 로그인(`/auth/kit-enrollment`)과 보호 자원 메타데이터(`/.well-known/oauth-protected-resource`)는 토큰을 받기 위한
경로라 제외합니다. 키트 로그인은 아이디·비밀번호 자체가 인증이며 로그인과 같은 시도 제한을 씁니다. 나머지는 사용자 토큰(`Depends(caller)`), 관리자(`admin_caller`), 또는 범위가 제한된
장치 키가 필요합니다. `tests/open_endpoints.py`가 이 문장과 코드를 대조합니다.
워크스테이션이 `/mcp/` 때문에 Gateway와 같은 망에 있으므로, 읽기 API를 열어 두면 프롬프트 주입된
에이전트가 전체 감사 기록을 읽을 수 있습니다(D-16).

## 7. 파일 지도

| 경로 | 내용 |
| --- | --- |
| `console.sh` | 단일 진입점 |
| `compose.yaml` | 전체 스택 (프로필 `llm`, `llm-download`, `supply-chain`, `llm-stub`, `replay`) |
| `gateway/` | 게이트웨이·IdP·콘솔(FastAPI) 이미지와 `app/` 코드 |
| `registry/catalog.toml`, `registry/contracts.lock.json` | 승인 서버·도구·분류·이용 관계 / 계약 해시 |
| `registry/field/` | field 기본 레지스트리(승인 서버 0개) |
| `opa/` | Rego 정책·시험·관리대장·예외·값 |
| `mcp/` | MCP 런타임 이미지와 실행 스크립트 |
| `corp/` | 회사 시드(파일·저장소·DB·메일·Redis·인트라넷·Gitea) |
| `workstation/` | 직원 PC 이미지(하네스 4종), `bin/{bob-ask,workday,harness-check,bob-sso}`, 시나리오, `managed/render.py`(카탈로그 → 하네스별 관리형 설정), 섀도 설정 |
| `llm/` | LiteLLM 설정 |
| `../endpoint-agent/` | 엔드포인트 에이전트(표준 라이브러리만). 직원 PC 이미지가 빌드 때 복사하고, 실제 PC에는 설치기로 배포 |
| `supply_chain/` | 도입 신청 격리 검증 워커(Syft·Trivy·Semgrep·AI-Infra-Guard mcp-scan, 플랫폼별 wheel 해시 잠금·종료 조건 조사) |
| `db/` | 게이트웨이 DB 초기화 |
| `scripts/watch.py` · `scripts/network_prefix.py` | 판정 한 줄 로그 · 망 대역 선택 |
| `tests/` | 보안 회귀·종료 흐름·검사기·무인증 API 대조·콘솔 상태 모듈(node)·도입 검증·실기기 키트 |
| `reports/` | 검증 결과(커밋하지 않음) |
| `compose.field.yaml`, `field/` | 실기기 배치 오버레이(Caddy, 직원 PC 키트) — `./console.sh field …`로만 얹힘. 아래 8절 |

## 8. 실제 기기로 배치하기

솔루션 기기 한 대에 스택을 올리고 Tailscale IP에만 Caddy(`https://<Tailscale IP>`)를 게시합니다. 관리자 PC는
브라우저로, 직원 PC는 브라우저와 키트(`field/pc/mcpgw_pc.py`)로 접속합니다.

```bash
./console.sh field up                     # MCP 서버 0개, 기본 관리자 root·admin1~3, 회원가입은 관리자 승인
./console.sh field up --with-lab-mcp      # 랩의 회사 시스템·MCP 10종·랩 계정으로
./console.sh field up --with-lab-workstations   # 컨테이너 직원 PC 4대까지
./console.sh field pc-command             # 직원 PC에서 실행할 키트 setup 한 줄(서버 목록은 레지스트리에서)
```

기본 비밀번호는 첫 실행 뒤 바꾼다. 현장의 `ROOT_SOLO_APPROVAL=1`에서는 최고 관리자 root가 본인 신청과 높은 위험 등급의 2인 조건을 강제 집행하고 원장에 별도로 남긴다. 매우 높은 등급의 서면 사유는 유지한다. 운영 배포의 기본은 끔이며 기본 비밀번호가 남은 `admin1`~`admin3`은 중지한다.

그 밖에 `field status`(공개 주소의 `/api/health`), `field set-password <아이디>`, `field register-pc <이름>`(장치 키 발급),
`field down`(Caddy만 멈춤)이 있습니다. field 모드는 별도 DB·Gitea 볼륨(`field_*`)을 쓰므로 랩 데이터는 그대로 남습니다. 경로 분기는 `field/Caddyfile`
(`/mcp/*`·`/api/health`·RFC 9728 메타데이터는 게이트웨이, `/oauth/*`는 IdP, `/git/*`는 솔루션 로그인을 거친 내부 Gitea,
나머지는 콘솔)에 있습니다. Console에서 등록한 서버는 `registry_runtime` 볼륨의 `servers.json`에 남고(D-49), `reset`이면 함께 지워집니다. 전체 절차와 한계는 [FIELD.md](../docs/ai/FIELD.md). 이 랩 자체를
바꾸지 않는 오버레이입니다 — `compose.field.yaml`·`field/`는 `./console.sh field …`로만 얹힙니다.

## 9. 한계
- 합성 로그인, 합성 회사 데이터. Compose 내부망은 방화벽이 아니다.
- LLM 모드의 결과는 작은 로컬 모델(기본 `qwen3.5:2b-q4_K_M`) 품질에 좌우된다. 판정 대조는 scripted 모드로 한다.
- 미등록 MCP 설정·확인된 수신기와 로컬 경로 첫 호출은 경보로 남긴다. 관리형 훅은 호출 후 이름·크기·해시를 보내며 완전한 수집·호출 전 차단을 보장하지 않는다. 게이트웨이 밖 직접 경로 통제는 엔드포인트·벤더·네트워크 통제 범위를 따로 확인한다.
- 승인 소스 stdio MCP는 엔드포인트 프로세스로 실행한다. 솔루션 실행기·실행 관리 API는 제거했으며, 이전 등록은 기존 실행·잔여 자원을 확인하고 엔드포인트 실행으로 재승인해야 한다. 공식 이미지 엔드포인트 컨테이너 경로는 유지한다.
- 제공자가 보유 자격을 고지하지 않으면 종료 판정은 T3에 머문다 — 논문이 특정한 구조적 한계.
- field의 A.I.G 기본 모델(`qwen3.5:0.8b`)은 CPU에서 끝까지 돌지만 탐지력이 낮다. "발견 0 · 로컬 소형 모델"은 안전의 증거가 아니다(D-47).
- field 모드는 사설 CA HTTPS를 사용한다(D-124). `field ca`로 루트·지문을 확인하고 키트로 하네스 범위에 배포한다.
  `/api/endpoint/*`는 게이트웨이로 연결하며 원격 보고는 동일 CA로 검증한다. Windows 통합·기기 배포·실기기 검수는 [보고](../research/llm-wiki/status/reports/2026-10-18-field-tls-d124.md)를 따른다.
