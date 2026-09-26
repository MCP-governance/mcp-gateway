# 운영 런북 — 이 랩을 띄우고, 돌리고, 되돌리는 법

> 단일 진입점은 `full_stack_lab/console.sh`. 모든 명령은 `full_stack_lab/`에서 실행한다.

## 1. 작업 환경 (이 노트북 기준)

| 항목 | 값 |
| --- | --- |
| 호스트 | Windows 11 + WSL2 `kali-linux` (Docker Desktop 없음, WSL 안의 Docker Engine 28) |
| 자원 | WSL VM 메모리 7.6GB, 호스트 15.4GB, 16 논리 CPU (Intel Ultra 7 255H, P/E/LP-E 하이브리드) |
| 저장소 | WSL `/home/kali/mcpgw-v2` = Windows `\\wsl.localhost\kali-linux\home\kali\mcpgw-v2` |
| 브랜치 | `feat/2026-09-v3.0-harness-gateway` |
| 비밀번호 | **WSL sudo를 포함해 로컬 비밀번호는 전부 `1111`** (sudo는 무암호 설정) |
| 랩 계정 비밀번호 | `test-password` (`.env`의 `MOCK_SSO_PASSWORD`) |
| 호스트 포트 | 이 노트북은 `.env`에 `CONSOLE_PORT=18000`, `GATEWAY_PORT=18080`, `GITEA_PORT=13000` |

이 노트북에 있던 다른 작업 트리의 v1 랩 스택은 2026-09-25에 사용자 승인을 받아 내렸다. 지금은 이
저장소의 `mcpgw-v2` 스택만 떠 있다. 프로젝트 이름은 `.env`의 `MCP_COMPOSE_PROJECT`.

### 망 대역 (주소 풀 소진 방지)
한 Docker 호스트에 랩 복제본이 여러 개 뜰 수 있다(이 노트북도 한때 그랬다). 랩은 처음 실행할 때 겹치지 않는
`/16`을 골라 `.env`의 `MCP_NET_PREFIX`에 고정하고 12개 망에 `/24`를 명시하므로 Docker 기본 주소 풀을 쓰지 않는다
(D-24). 이 방식 이전에 만든 스택은 `./console.sh down` 뒤 `up`. 후보 대역이 모두 겹친다는 오류가 나면 쓰지 않는
**자기** 복제본만 내린다. 남의 스택 네트워크를 지우지 않는다.

### 실제 PC에 단말 에이전트 설치
랩의 직원 PC는 `endpoint-agent/agent.py`를 이미지에 복사해 쓴다. 실제 PC(Linux·Windows)에는 저장소 루트의
[`endpoint-agent/README.md`](../../endpoint-agent/README.md) 절차(장치 키 발급 → 설치기 → 1회 보고 확인 → 제거)를 따른다.

### WSL이 유휴로 꺼지는 문제
WSL VM은 열린 프로세스가 없으면 몇 분 뒤 종료되고 컨테이너도 같이 죽는다. 작업 중에는 백그라운드로
`wsl.exe -d kali-linux -- sleep infinity`를 하나 띄워 둔다. 모든 장기 서비스는 `restart: unless-stopped`라
VM이 다시 뜨면 스스로 올라온다.

### Git Bash에서 WSL 명령을 부를 때 (Claude Code 작업자용)
- Git Bash의 heredoc·따옴표가 백슬래시와 `$변수`를 망가뜨린다. 여러 줄 스크립트는 **파일로 쓴 뒤**
  (`\\wsl.localhost\kali-linux\tmp\x.sh`) `export MSYS_NO_PATHCONV=1; wsl.exe -d kali-linux -- bash /tmp/x.sh`로 실행.
- `wsl.exe -- bash -c '…'` 안의 for 루프 변수(`$f`)가 비는 일이 있었다. 루프는 파일로.
- 파일 편집은 UNC 경로(`\\wsl.localhost\…`)로 Read/Edit/Write 도구를 쓰면 된다.

## 2. console.sh 명령

| 명령 | 하는 일 |
| --- | --- |
| `./console.sh up` | `.env` 생성(서명 키·LiteLLM 마스터 키·직원별 LLM 키·장치 키) → 이미지 빌드 → 회사 시스템·MCP 10종 → Ollama 모델 확인/받기 → `bob-assistant` 파생 모델 → LiteLLM·키 발급 → Gateway·Console·워커 → 계약 기준선(없으면 생성) → 장치 자격 등록 → 직원 PC 4대(각자 하네스 4종 설치) |
| `./console.sh up --no-llm` | LLM 없이. 직원 PC의 하네스 도구 호출은 **MCP Inspector CLI**가 scripted 모드로 대신한다. CI가 쓴다 |
| `./console.sh workday [ws\|all] [--mode llm\|scripted] [--check]` | 직원 PC의 하루 업무 시나리오(`workstation/scenarios/*.toml`)를 각자의 하네스로 실행. llm=하네스가 자연어 지시로 도구를 고름, scripted=MCP Inspector CLI가 같은 Gateway URL·SSO 토큰으로 직접 호출. `--check`는 scripted에서만 기대 판정과 엄격 대조 |
| `./console.sh ask <ws> "지시" [--servers a,b] [--harness claude\|codex\|gemini\|opencode]` | 한 직원 PC에 설치된 하네스에 헤드리스로 업무 지시(`bob-ask`). PC마다 기본 하네스가 다르다(ws-ysg=claude, ws-jwj=codex, ws-pse=gemini, ws-nkk=opencode). 네 PC 모두 하네스 4종이 다 설치돼 있어 `--harness`로 바꿔 부를 수 있다 |
| `./console.sh harnesses` | 직원 PC 4대의 하네스 4종이 Gateway의 관리형 MCP 서버 10종에 모두 붙는지 확인(모델 호출 없음) |
| `./console.sh watch` | Gateway 판정을 사람이 읽는 한 줄 로그로 계속 출력 (`scripts/watch.py`) |
| `./console.sh contracts [--check\|--update]` | 계약 잠금 대조 / 재생성(재생성 후 diff를 읽고 커밋) |
| `./console.sh experiment e1\|e2\|e3` | 논문 실험 재현, `reports/experiment-*.json` |
| `./console.sh replay [N]` | 기록된 정책 입력 N건 + 합성 라벨 사례를 후보 OPA(`REPLAY_POLICY_DIR`, 기본 `./opa`)에 재생, `reports/policy-replay.json` — MCP 호출 없음 |
| `./console.sh restore <server>` | (실습) 종료·폐기한 서버 복원. gitea면 토큰 재발급까지 |
| `./console.sh restore-token gitea` | 폐기된 gitea-mcp PAT 재발급 + 서버 재시작 |
| `./console.sh test` | 전체 검증 → [TESTING.md](TESTING.md) |
| `./console.sh scan` | Syft·Trivy·Semgrep(프로필 `supply-chain`) 후 결과 반영 |
| `./console.sh openapi` | `docs/openapi/{gateway,agent-service}.json` 생성 |
| `./console.sh status` / `logs [svc]` / `down` / `reset` | 상태·로그·중지·볼륨까지 초기화(잠금 파일은 유지) |

## 3. 계정

| 이메일 | 이름 | 역할 | 부서 | 워크스테이션 |
| --- | --- | --- | --- | --- |
| kkg@bob.local | 김경곤 | admin | 거버넌스팀 | — |
| mks@bob.local | 문광석 | admin | 보안운영팀 | — |
| ysg@bob.local | 양승권 | employee | 플랫폼개발팀 | ws-ysg |
| jwj@bob.local | 정원재 | employee | 데이터분석팀 | ws-jwj |
| pse@bob.local | 박소은 | employee | 보안기술팀 | ws-pse |
| miso@bob.local | 김미소 | employee | 보안기술팀 | — |
| nkk@bob.local | 권노경 | partner | 협력사 A | ws-nkk (섀도 MCP 설정 보유) |

Gitea 관리자: `corpadmin` / `corp-admin-lab-only` (`GITEA_ADMIN_*`). Console은 관리자면 전체, 아니면
자기 활동·도입 신청만 보인다.

## 4. 자주 하는 일

### 처음부터
```bash
cd full_stack_lab && ./console.sh up          # 첫 실행은 모델 다운로드 포함 수십 분
./console.sh workday                          # 네 직원의 하루(LLM 모드)
./console.sh watch                            # 다른 창에서 판정 흐름
```
브라우저: `http://localhost:${CONSOLE_PORT}` → kkg@bob.local.

### 코드만 바꿨을 때
- Gateway/Console Python·정적 파일: `docker compose build -q gateway agent-service && docker compose up -d gateway gateway-sse agent-service`
  (정적 파일은 이미지에 들어간다 — 볼륨 마운트 아님).
- Rego: `docker compose restart opa` (OPA는 `--watch` 없이 뜬다).
- 카탈로그(`registry/catalog.toml`): Gateway 재시작 시 `registry.sync()`가 반영.
- MCP 서버 이미지: `docker compose build mcp-filesystem && docker compose up -d --force-recreate mcp-…` →
  `./console.sh contracts --check`.

### 종료 판정 시연
Console `#/termination` → 관계 카드 "종료 시작" → 케이스 화면에서 증거 수집 → 판정 → (gitea) 조직
권한으로 폐기 → 증거 수집 → 판정(T1) → 종결 → 실습 복원 → `./console.sh restore-token gitea`.
자동 버전: `python3 tests/termination_flow.py`.

### 누가 연 종료 케이스가 남아 서버가 막혀 있을 때
`TERMINATING` 서버는 모든 호출이 `MCP-DECOMM-001`이다. acceptance는 그런 서버를 SKIP하고, workday
`--check`는 실패한다. 케이스를 종결하거나 `./console.sh restore <server>`로 되돌린다.
**다른 사람이 연 케이스인지 먼저 확인할 것**(Console에서 개시자·사유 확인).

## 5. 초기화
- `./console.sh down` — 컨테이너만 중지(데이터 유지).
- `./console.sh reset` — DB·회사 시스템·모델 볼륨 삭제. 다음 `up`이 시드부터 다시(모델 재다운로드 포함).
- 회사 시드만 다시: `docker compose run --rm corp-seed --force`.

## 6. 실제 PC에서 하네스를 손으로 쓰기
`bob-ask`·`workday`를 거치지 않고, 직원이 평소 쓰듯 하네스를 직접 불러도 된다.

```bash
docker compose exec ws-ysg bash -l
bob-ask "payment-service 최근 커밋 3개 요약해 줘"   # 이 PC의 기본 하네스(HARNESS=claude)로
claude -p "..."                                      # 하네스를 직접 불러도 같은 경로 — Claude는 headersHelper로 토큰을 받고,
                                                     # codex·gemini·opencode는 로그인 셸의 함수(/etc/profile.d/bob-harness.sh)가 실행마다 새 토큰을 채운다
```
다른 하네스도 같은 방식(`codex exec`, `gemini -p`, `opencode run`) — 네 PC 모두 하네스 4종이 다 설치돼 있다.

관리형 설정(IT가 사전 승인한 MCP 서버 10종과 도구)은 `/etc/claude-code/managed-mcp.json`·`managed-settings.json`,
`/etc/codex/managed_config.toml`, `/etc/gemini-cli/settings.json`, `/etc/opencode/opencode.json`
(`OPENCODE_CONFIG`로 지정)에 있다. 전부 `registry/catalog.toml`에서 워크스테이션 이미지 빌드 때
`workstation/managed/render.py`가 생성한 것이라 컨테이너 안에서 손으로 고치지 않는다 — 서버를 추가·변경하려면
카탈로그를 고치고 이미지를 다시 빌드한다.

`BOB_HARNESS_COMPACT=1`(기본)은 CPU 소형 모델을 위해 하네스의 내장 도구를 끄고 프롬프트를
`/etc/bob/harness-prompt.md`로 줄인다. 클라우드 모델을 붙일 때는 `0`으로 하네스 본래 프롬프트를 쓴다.

로컬 모델은 `LOCAL_LLM_MODEL`(기본 `qwen3.5:2b-q4_K_M`, 적재 1.7GB)·`LOCAL_LLM_CONTEXT`(기본 12288)로
바꾼다. 품질이 더 필요하면 `LOCAL_LLM_MODEL=qwen3.5:4b`이지만 16K 컨텍스트에서 +3.4GB가 더 든다 — 이
노트북의 WSL VM은 7.6GB(호스트 15.4GB)뿐이라 스택(~3.6GB) 위에 얹었다가 WSL이 두 번 멎은 적이 있다
(복구는 `wsl --shutdown`). 모델을 여러 개 동시에 올리지 말 것(`OLLAMA_MAX_LOADED_MODELS=1`), 평소엔 2B로 둔다.
