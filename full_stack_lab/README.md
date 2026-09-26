# full_stack_lab — BoB Corp MCP 거버넌스 랩 (v2)

사내망 직원 PC의 AI 에이전트 → Gateway(`/mcp/`) → 실제 MCP 서버 10종 → 회사 시스템.
설계는 [../docs/ai/ARCHITECTURE.md](../docs/ai/ARCHITECTURE.md), 운영은 [../docs/ai/RUNBOOK.md](../docs/ai/RUNBOOK.md).

## 1. 실행

```bash
./console.sh up            # 전체 (첫 실행: 빌드 + qwen3.5:2b-q4_K_M 다운로드)
./console.sh up --no-llm   # LLM 없이 — 직원 PC의 하네스 도구 호출은 MCP Inspector CLI가 대신(scripted)
./console.sh status        # 서비스 상태와 MCP 서버 준비 수
```

| 주소(기본 포트) | 내용 |
| --- | --- |
| `http://localhost:8000` | Console (`CONSOLE_PORT`) |
| `http://localhost:8080/api/health` | Gateway (`GATEWAY_PORT`) |
| `http://localhost:16686` | Jaeger (`JAEGER_PORT`) |
| `http://localhost:3000` | 회사 Gitea — 제공자 콘솔 역할 (`GITEA_PORT`, `corpadmin`) |

모두 `127.0.0.1`에만 게시됩니다. 계정(비밀번호 `test-password`): 관리자 `kkg@bob.local`·`mks@bob.local`,
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

## 3. Console

관리자로 로그인하면: **개요**(오늘 판정·서버·직원 PC·많이 걸린 정책) · **활동 로그**(한 줄이 호출 하나,
누르면 판정 근거·분류·정책·trace, 실시간) · **승인 대기** · **MCP 서버**(계약 일치/불일치, 승인본 갱신) ·
**직원·단말**(계정 상태, 단말의 MCP 설정과 섀도 MCP) · **도입 신청**(원격 서버의 종료 조건은 관리자가 제공자
문서로 검증해야 승인) · **종료·폐기** · **정책**(배포된 권한 번들과 그 번들로 OPA에 물은 27칸, 관리대장, 예외,
집행/관찰 모드). 직원·협력사는 자기 활동 로그와 도입 신청만 봅니다. 활동 로그는 불러온 기록 안에서 사람·단말·
도구·대상·정책·trace로 찾고, 일시정지해도 새 판정 수를 셉니다.
구조: [../docs/ai/CONSOLE_UI.md](../docs/ai/CONSOLE_UI.md).

## 4. 종료·폐기 시연

1. **종료·폐기** → 이용 관계 카드마다 "지금 끊으면 도달할 수 있는 최선 등급"(UR-EMAIL-ASSIST는 제공자
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
./console.sh test
./console.sh replay 100                               # 기록된 정책 입력 100건 + 합성 사례를 후보 정책에 재생
REPLAY_POLICY_DIR=./candidate-opa ./console.sh replay  # 후보 정책 디렉터리 지정 (MCP 호출 없음)
```
망 대역 self-check → 콘솔 상태(node) → Rego → 분류기 → Gateway 인수 시험 → 업무 시나리오 대조 → 종료 판정 흐름 →
보안 회귀 → 정책 재생 → E1~E3. 결과는 `reports/`. 층별 설명: [../docs/ai/TESTING.md](../docs/ai/TESTING.md).

망 12개는 모두 `.env`의 `MCP_NET_PREFIX`(처음 실행 때 다른 Docker 망·라우트와 겹치지 않는 `10.200`~`10.249` 중
하나를 자동 선택) 아래 `/24`를 명시해 만들므로, 한 호스트에 랩을 여러 벌 띄워도 Docker 기본 주소 풀이 소진되지
않습니다. 이 방식 이전에 만든 복제본은 `./console.sh down` 뒤 `up`하면 새 대역으로 옮겨집니다(볼륨 유지).

## 6. 열려 있는 API

Gateway API 중 토큰 없이 열려 있는 것은 다음뿐입니다: `/api/health` (구성요소 상태와 준비된 MCP 서버 수).
로그인(`/api/session`)과 보호 자원 메타데이터(`/.well-known/oauth-protected-resource`)는 토큰을 받기 위한
경로라 제외합니다. 나머지는 사용자 토큰(`Depends(caller)`), 관리자(`admin_caller`), 또는 범위가 제한된
장치 키가 필요합니다. `tests/open_endpoints.py`가 이 문장과 코드를 대조합니다.
워크스테이션이 `/mcp/` 때문에 Gateway와 같은 망에 있으므로, 읽기 API를 열어 두면 프롬프트 주입된
에이전트가 전체 감사 기록을 읽을 수 있습니다(D-16).

## 7. 파일 지도

| 경로 | 내용 |
| --- | --- |
| `console.sh` | 단일 진입점 |
| `compose.yaml` | 전체 스택 (프로필 `llm`, `llm-download`, `supply-chain`, `llm-stub`) |
| `gateway/` | Gateway·IdP·Console(FastAPI) 이미지와 `app/` 코드 |
| `registry/catalog.toml`, `registry/contracts.lock.json` | 승인 서버·도구·분류·이용 관계 / 계약 해시 |
| `opa/` | Rego 정책·시험·관리대장·예외·값 |
| `mcp/` | MCP 런타임 이미지와 실행 스크립트 |
| `corp/` | 회사 시드(파일·저장소·DB·메일·Redis·인트라넷·Gitea) |
| `workstation/` | 직원 PC 이미지(하네스 4종), `bin/{bob-ask,workday,harness-check,bob-sso}`, 시나리오, `managed/render.py`(카탈로그 → 하네스별 관리형 설정), 섀도 설정 |
| `llm/` | LiteLLM 설정 |
| `../endpoint-agent/` | 단말 에이전트(표준 라이브러리만). 직원 PC 이미지가 빌드 때 복사하고, 실제 PC에는 설치기로 배포 |
| `supply_chain/` | 도입 신청 격리 검증 워커 |
| `db/` | Gateway DB 초기화 |
| `scripts/watch.py` · `scripts/network_prefix.py` | 판정 한 줄 로그 · 망 대역 선택 |
| `tests/` | 보안 회귀·종료 흐름·검사기·무인증 API 대조·콘솔 상태 모듈(node) |
| `reports/` | 검증 결과(커밋하지 않음) |

## 8. 한계
- 합성 로그인, 합성 회사 데이터. Compose 내부망은 방화벽이 아니다.
- LLM 모드의 결과는 작은 로컬 모델(기본 `qwen3.5:2b-q4_K_M`) 품질에 좌우된다. 판정 대조는 scripted 모드로 한다.
- 섀도 MCP는 발견·증적까지. 차단은 네트워크 평면 몫.
- 제공자가 보유 자격을 고지하지 않으면 종료 판정은 T3에 머문다 — 논문이 특정한 구조적 한계.
