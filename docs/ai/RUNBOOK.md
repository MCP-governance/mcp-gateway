# 운영 런북 — 이 랩을 띄우고, 돌리고, 되돌리는 법

> 단일 진입점은 `full_stack_lab/console.sh`. 모든 명령은 `full_stack_lab/`에서 실행한다.

## 1. 작업 환경 (이 노트북 기준)

| 항목 | 값 |
| --- | --- |
| 호스트 | Windows 11 + WSL2 `kali-linux` (Docker Desktop 없음, WSL 안의 Docker Engine 28) |
| 자원 | RAM 7GB, 16 논리 CPU (Intel Ultra 7 255H, P/E/LP-E 하이브리드) |
| 저장소 | WSL `/home/kali/mcpgw-v2` = Windows `\\wsl.localhost\kali-linux\home\kali\mcpgw-v2` |
| 브랜치 | `feat/2026-09-v2.0-workforce-real-mcp` |
| 비밀번호 | **WSL sudo를 포함해 로컬 비밀번호는 전부 `1111`** (sudo는 무암호 설정) |
| 랩 계정 비밀번호 | `test-password` (`.env`의 `MOCK_SSO_PASSWORD`) |
| 호스트 포트 | 이 노트북은 `.env`에 `CONSOLE_PORT=18000`, `GATEWAY_PORT=18080`, `JAEGER_PORT=26686`, `GITEA_PORT=13000` |

같은 WSL에서 다른 작업 트리(`C:\Users\bobysg\bob\프로젝트\mcp-gateway-pdf-integration`, Compose 프로젝트
`mcpgw-23ffc0f4e9`)가 v1 랩을 8000/8080으로 띄운다. **그 컨테이너를 멈추지 말 것** — 포트를 나눠
공존한다(D-14). 프로젝트 이름은 `.env`의 `MCP_COMPOSE_PROJECT`(여기서는 `mcpgw-v2`).

### Docker 주소 풀 소진
이 WSL에는 랩이 여러 개(v2, v1 pdf-integration 트리, 또 다른 복제본) 떠 있어 `all predefined address pools have been
fully subnetted`가 날 수 있다. 새 망을 추가하지 말고(D-20), 쓰지 않는 **자기** 복제본을 `./console.sh down`으로 내린다.
남의 스택 네트워크를 지우지 않는다.

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
| `./console.sh up` | `.env` 생성(서명 키·LiteLLM 마스터 키·직원별 LLM 키·장치 키) → 이미지 빌드 → 회사 시스템·MCP 10종 → Ollama 모델 확인/받기 → `bob-assistant` 파생 모델 → LiteLLM·키 발급 → Gateway·Console·워커 → 계약 기준선(없으면 생성) → 장치 자격 등록 → 직원 PC 4대 |
| `./console.sh up --no-llm` | LLM 없이(직원 PC는 scripted 모드). CI가 쓴다 |
| `./console.sh workday [ws\|all] [--mode llm\|scripted] [--check]` | 직원 PC의 하루 업무 시나리오(`workstation/scenarios/*.toml`). `--check`는 기대 판정과 대조 |
| `./console.sh ask <ws> "지시" [--servers a,b]` | 한 직원 AI 어시스턴트에게 지시 |
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
