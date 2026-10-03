# AGENTS.md — 이 저장소에서 일하는 AI 에이전트를 위한 규칙

이 저장소는 **MCP 거버넌스 게이트웨이 테스트베드**다. 사내망 직원 PC의 AI 에이전트가 실제 MCP 서버
10종을 쓰고, Gateway가 모든 도구 호출을 실행 전에 판정하며, 종료·폐기는 논문(CISC-W'26)의 C1~C4 /
T1~T3 모델로 판정한다.

## 소유자 규칙 (2026-10-03, 다른 모든 문서보다 우선)
1. **솔루션은 솔루션 기기에서만 띄운다**(`user@100.83.175.111`, `./console.sh field up`). 이 노트북 WSL에는 compose 스택을
   띄우지 않는다(대시보드 보기·간단한 데모만). 로컬에서 하는 것은 정적 검사와 일회성 `opa test` 컨테이너까지.
2. **솔루션 시험은 PJ1**(`pj1@100.110.81.60`)의 실제 하네스로 한다.
3. **콘솔은 즉시 판매 가능한 제품 화면이다.** 프로젝트 진행 중이라는 흔적을 남기지 않는다.
   - 설명 문단·도움말·주석 같은 안내문(“~합니다”, “~는 자기 신고”), 브레드크럼, 부제, 중복 로고·중복 사용자 표시 금지. 라벨과 값만.
   - 개발 흔적 금지: D-번호, PAC-15·팀원·실습·v3/v4·WIP, 빌드 SHA·버전 표, 시험 데이터, 참고 제품 이름, 영어 enum 원문.
     브라우저로 내려가는 HTML·CSS·JS에도 이런 주석을 넣지 않는다.
   - 용어는 한글 **게이트웨이 · 엔드포인트**로 통일(`단말`·`커널`·Gateway/Endpoint 혼용 금지). 엔드포인트가 막은 것은 “엔드포인트에서 차단”.
   - GW/EP/VD 같은 약어 표식 금지. 모든 상태값은 한국어로 번역하고 값이 없으면 `—`.
   - 화면에서 설정·조작할 수 없는 기능은 화면과 코드에서 뺀다(예: 예외, 333 잔재). 정책 목록은 번호·정책·결과만.
4. **모호하면 작업 전에 소유자에게 묻는다.** 추측으로 화면·기능을 늘리지 않는다.

## 먼저 읽을 것
1. [docs/ai/README.md](docs/ai/README.md) — 문서 지도
2. [docs/ai/ARCHITECTURE.md](docs/ai/ARCHITECTURE.md) — 정본 설계
3. [docs/ai/RUNBOOK.md](docs/ai/RUNBOOK.md) — 환경·명령·계정 (로컬 비밀번호는 전부 `1111`)
4. 손댈 영역의 문서(POLICY / TERMINATION_MODEL / MCP_SERVERS / CONSOLE_UI / DATA_MODEL)

## 명령
검증 순서(소유자 규칙): ① 로컬 정적 검사 → ② 솔루션 기기에 `field up`으로 배포 → ③ PJ1의 실제 하네스로 기능 확인.
로컬 정적 검사: `pyflakes gateway/app/*.py tests/*.py …`, `node --check gateway/app/agent_static/console.js`,
`node --test tests/console-state.test.mjs`, `python3 tests/open_endpoints.py`,
Rego는 `docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy`.
```bash
cd full_stack_lab
./console.sh field up|ca|status|pc-command|set-password|register-pc|down   # 솔루션 기기에서만 (README "실제 기기로 배치하기")
./console.sh test          # 실습 스택 전체 회귀 — 이 노트북에서는 돌리지 않는다
./console.sh watch         # 판정 흐름
```

## 깨면 안 되는 불변식
- **신원은 transport의 토큰에서만** 정한다. 인자·헤더에 적힌 신원은 기록만 하고 판정에 쓰지 않는다.
- **직원 토큰을 upstream MCP 서버로 넘기지 않는다**(MCP 인가 명세, 토큰 전달 금지).
- **Gateway의 새 라우트에는 `Depends(caller)` 또는 `Depends(admin_caller)`**. 무인증은 `/api/health`·
  로그인뿐이고 `tests/open_endpoints.py`가 README 문장과 대조한다. 워크스테이션이 Gateway와 같은 망에 있다.
- **실패는 차단으로**: OPA 불능 `P-CONTROL-FAIL-CLOSED`, 분류 모르면 important, 계약 확인 불가면 `MCP-CATALOG-001`.
- **계약 승인은 사람이**: 첫 관찰값 자동 승인(TOFU) 금지. `registry/contracts.lock.json`은 diff를 읽고 커밋.
- **Console은 MCP를 호출하지 않는다**. CSP same-origin, 인라인 스크립트·`style=` 금지, 모든 데이터는 `html```로 이스케이프.
- **종료 판정 규칙을 바꾸면** `docs/ai/TERMINATION_MODEL.md`와 `tests/termination_flow.py`를 같이 고친다.
- **감사 원장은 append-only**. 판정 기록을 고치는 코드를 쓰지 않는다.
- **하네스 관리형 설정은 레지스트리에서 렌더링된다**. 이미지 안 `/etc/claude-code`·`/etc/codex`·`/etc/gemini-cli`·
  `/etc/opencode`의 파일을 직접 고치지 않는다 — `registry/catalog.toml`을 고치고 워크스테이션 이미지를 다시 빌드한다.
- **실기기 게시는 `compose.field.yaml`의 Caddy와 모델 프록시 두 개뿐**이다(D-46·D-67). `field` 명령이 찾은 Tailscale IP에만
  바인딩하고, 일반 LAN·전체 인터페이스에는 게시하지 않는다. 기본 `compose.yaml`의 loopback 게시는 그대로 둔다.
- **직원 PC 키트(`field/pc/mcpgw_pc.py`)는 토큰·비밀번호를 하네스 설정·환경 변수·로그에 쓰지 않는다**. 헬퍼 명령만 쓰고,
  리프레시는 잠금 안에서만 한다(IdP가 재사용을 계열 폐기로 처리). 시험은 임시 HOME·CODEX_HOME에서만.
- **Gateway는 하네스 신원을 기록만 한다**. `decisions.client.harness`(clientInfo·User-Agent)는 클라이언트가
  보고한 값이라 판정에 쓰지 않는다.

## 시험을 쓰는 법
- 판정은 `decision`과 `policy_id`까지 확인한다(다른 이유의 차단을 통과로 세지 않게).
- 검사 도구가 죽으면 **실패**여야 한다(거짓 통과 금지).
- 상태를 바꾸는 시험은 `trap`/`finally`로 원복한다.
- 다른 사람이 연 종료 케이스·실행 중인 다른 랩을 되돌리거나 멈추지 않는다.

## 환경 주의
- 스택은 솔루션 기기에서만 돌린다(위 소유자 규칙 1). 기기 접속은 WSL의 `/home/kali/.ssh/id_ed25519` 키로 한다.
- WSL은 유휴 시 꺼진다 → `wsl.exe -d kali-linux -- sleep infinity`를 백그라운드로.
- Windows Git Bash에서 WSL로 여러 줄 스크립트를 보낼 때는 파일로 써서 실행한다(따옴표·`$`·`\` 손실).

## 코드 스타일
- 주석은 "무엇"이 아니라 **왜**. 주변 코드의 언어(한국어/영어)와 밀도를 따른다.
- 새 의존성보다 표준 라이브러리·이미 있는 코드. 한 번 쓰는 추상화 금지.
- 결정을 내리면 `docs/ai/DECISIONS.md`에 D-번호로 남긴다.

## Git
- 사용자 요청 없이 새 브랜치를 만들거나 올리지 않는다. 새 이름은 `MM/DD-branchname`(Git ref에 공백 불가),
  기본 브랜치는 `main`(2026-09-28 `feat/2026-09-v3.1-field-deploy`에서 이름 변경)이고 여기서 이어서 작업한다.
  유지 브랜치는 `main`과 다른 흐름의 field 브랜치 3개뿐이다. PR 본문에 검증 결과를 붙인다.
- 커밋 메시지: 첫 줄 `feat|fix|docs|test(v2): …`, 본문에 이유.
