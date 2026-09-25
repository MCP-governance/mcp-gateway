# AGENTS.md — 이 저장소에서 일하는 AI 에이전트를 위한 규칙

이 저장소는 **MCP 거버넌스 게이트웨이 테스트베드**다. 사내망 직원 PC의 AI 에이전트가 실제 MCP 서버
10종을 쓰고, Gateway가 모든 도구 호출을 실행 전에 판정하며, 종료·폐기는 논문(CISC-W'26)의 C1~C4 /
T1~T3 모델로 판정한다.

## 먼저 읽을 것
1. [docs/ai/README.md](docs/ai/README.md) — 문서 지도
2. [docs/ai/ARCHITECTURE.md](docs/ai/ARCHITECTURE.md) — 정본 설계
3. [docs/ai/RUNBOOK.md](docs/ai/RUNBOOK.md) — 환경·명령·계정 (로컬 비밀번호는 전부 `1111`)
4. 손댈 영역의 문서(POLICY / TERMINATION_MODEL / MCP_SERVERS / CONSOLE_UI / DATA_MODEL)

## 명령
```bash
cd full_stack_lab
./console.sh up            # 전체 기동 (--no-llm: LLM 없이)
./console.sh test          # 전체 검증 — 고친 뒤 반드시
./console.sh workday       # 직원 업무 시나리오
./console.sh watch         # 판정 흐름
```
정적 검사만: `pyflakes gateway/app/*.py tests/*.py …`, `node --check gateway/app/agent_static/console.js`,
`python3 tests/open_endpoints.py`, Rego는 `docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy`.

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

## 시험을 쓰는 법
- 판정은 `decision`과 `policy_id`까지 확인한다(다른 이유의 차단을 통과로 세지 않게).
- 검사 도구가 죽으면 **실패**여야 한다(거짓 통과 금지).
- 상태를 바꾸는 시험은 `trap`/`finally`로 원복한다.
- 다른 사람이 연 종료 케이스·실행 중인 다른 랩을 되돌리거나 멈추지 않는다.

## 환경 주의
- 같은 WSL에 다른 작업 트리의 v1 랩이 8000/8080을 쓸 수 있다. **멈추지 말고** `.env`의 `*_PORT`로 피한다.
- WSL은 유휴 시 꺼진다 → `wsl.exe -d kali-linux -- sleep infinity`를 백그라운드로.
- Windows Git Bash에서 WSL로 여러 줄 스크립트를 보낼 때는 파일로 써서 실행한다(따옴표·`$`·`\` 손실).

## 코드 스타일
- 주석은 "무엇"이 아니라 **왜**. 주변 코드의 언어(한국어/영어)와 밀도를 따른다.
- 새 의존성보다 표준 라이브러리·이미 있는 코드. 한 번 쓰는 추상화 금지.
- 결정을 내리면 `docs/ai/DECISIONS.md`에 D-번호로 남긴다.

## Git
- 기능 브랜치(`feat/…`)에서 작업, `main` 직접 푸시 금지. PR 본문에 검증 결과를 붙인다.
- 커밋 메시지: 첫 줄 `feat|fix|docs|test(v2): …`, 본문에 이유.
