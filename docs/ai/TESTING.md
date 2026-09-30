# 검증 — 무엇이 무엇을 보장하나

> 한 번에: `cd full_stack_lab && ./console.sh test` (스택이 떠 있어야 한다. CI는 `up --no-llm` 후 실행).
> 결과물은 `full_stack_lab/reports/`에 남는다. 실패 하나라도 있으면 종료 코드 1.

## 1. 층별 구성

| 순서 | 무엇 | 파일 | 보장 | 소요 |
| --- | --- | --- | --- | --- |
| 0 | 망 대역·콘솔 상태 | `scripts/network_prefix.py --self-check`, `tests/console-state.test.mjs` (node, 7건) | 대역 선택이 점유 대역을 피하고 소진 시 실패 / 활동 로그 병합(중복·잘못된 id)·검색·상태 문장(실패를 최신처럼 보이지 않음)·**시간대별 판정 버킷(`hourBuckets`), 그룹별 집계(`splitBy`), 하네스×서버 상키 데이터(`sankeyData`)** | 수 초 |
| 1 | Rego 단위 시험 | `opa/policy_test.rego` (92건) | 27칸 기본 판정 기준선, 권한 번들이 비면 전부 차단·번들 변경이 판정을 바꿈, MCP-* 통제, 예외(유효기간·범위·자가승인·보완통제), 승인형 예외, 민감정보 반출·연쇄(v2 입력), 관리대장 필수 항목, 충돌 우선순위 | 수 초 |
| 2 | 분류기 self-check | `gateway/app/classify.py` (`python -m app.classify`) | 경로·SQL·URL·메일·Redis 키 분류, DLP(주민번호·카드 Luhn·휴대폰·AWS 키·개인키·비밀번호), 행위 승격 | 수 초 |
| 2a | 도구 설명·커넥터 정책 self-check | `gateway/app/poisoning.py`(`python -m app.poisoning`), `gateway/app/connectors.py`(agent-service `python -m app.connectors`) | 공개된 tool poisoning 예시(숨긴 지시 태그·민감 경로·다른 도구 조종·보이지 않는 문자)는 잡고 평범한 설명은 통과(D-52) / 결정 단위(호스트·앱 id·기능), 벤더 자신의 것 기본 허용, 검토 기한 뒤 거부, 거부 → `deniedMcpServers`·앱·기능 목록, Gateway 호스트와 직원이 붙인 이름은 거부 목록에 넣지 않음(D-51) | 수 초 |
| 3 | Gateway 인수 시험 | `gateway/app/acceptance.py` (스위트 `gateway-acceptance-v3`) | `/mcp/` 401+RFC 9728 챌린지, 역할별 도구 목록, OPA가 내어주는 권한 번들(`LAB-AUTHZ-001`), 허용 호출은 `P-AUTHZ-ALLOW-001`, 미승인·미등록 도구 차단, 스키마 검증, 계약 드리프트 차단→복구, 승인 1회 실행, 관찰 모드 기록, **결과 개인정보 마스킹, 개인정보 외부 발송 차단(MCP-DATA-EGRESS-001), 열람→반출 연쇄(P-CHAIN-001)**, 감사 체인, **`per-server-endpoint-for-harness-configs`(`/mcp/git/`의 도구 목록=승인 목록, `git_log` 허용, `client.endpoint=git`, `/mcp/nope/` 404), `tool-hidden-from-partner-still-decided`(협력사 목록에 없는 도구도 직접 호출하면 판정된다), `usage-relationship-scope-alerts`(이용 관계 밖 `hr.employees` → `P-SCOPE-001` 경보, 안 `sales.orders` → 허용, D-39), `server-check-changes-nothing`(연결 확인이 서버 상태·감사 원장을 바꾸지 않음, 없는 서버 404, 직원 403, D-40)** · **`console-registration-pins-and-expires`(랩 fetch를 다른 id로 Console 등록 — 검토하지 않은 계약 해시 409, `/mcp/<id>/`에 승인 도구만, 호출, 기한 지나면 `P-APPROVAL-EXPIRY-001`, 해제 후 404, D-49)** | ~40초 |
| 4 | 하네스 연결 확인 | `workstation/bin/harness-check`(`./console.sh harnesses`, `reports/harnesses.txt`) | PC 4대 × 하네스 4종이 관리형 MCP 서버 10종 전부에 Gateway로 붙는지 — 모델 호출 없이(`claude/gemini/opencode mcp list`, Codex는 `app-server` `mcpServerStatus/list`) | 수 초 |
| 5 | 직원의 하루 | `workstation/scenarios/*.toml` (21건, scripted) | 각 직원 PC에서 **MCP Inspector CLI**가 하네스와 같은 Gateway URL·SSO 토큰으로 실제 서버에 보내는 업무 21건이 기대 판정(Allow/Alert/Approval/Block)과 일치(판정은 Gateway `/api/activity`에서 직원 토큰으로 대조 — 하네스 출력 형식과 무관) | ~1분 |
| 6 | 종료 판정 흐름 | `tests/termination_flow.py` (21건) | UR-GITEA-DEV T3→T2→T1·종결, UR-EMAIL-ASSIST T3·위험 수용 없는 종결 거부·고지 요청서, 복원 | ~1분 |
| 7 | 보안 회귀 | `tests/security_regression.sh` (55건) | 망 분리(실제 소켓, Presidio 포함), loopback 게시, 읽기 API 토큰, Console 역할 경계, 로그아웃 즉시 효력, **원격 MCP 종료 조건(신청자 자기 신고 422·직원 기록 403·검증 없는 승인 409·위험 수용 사유로도 격리 검증 전 승인 불가·http 근거 422·관리자 기록 200·검증 뒤에도 격리 검증 전 승인 불가)**, OPA 정지→`P-CONTROL-FAIL-CLOSED`, 상위 서버 정지→미실행, **Presidio 분석기 정지→`P-DATA-INSPECTION-001`, 마스킹기 정지→실행됨·`MCP-OUTPUT-001`**, 감사 변조 탐지, 계약 잠금 일치, 격리 워커 검사기 | ~1.5분 |
| 8 | 정책 재생 | `gateway/app/replay.py` + `tests/replay_check.py` | 기록된 정책 입력을 현재 정책에 다시 넣은 결과(보고)와 합성 라벨 10사례의 공격 미탐·정상 차단 0 | 수 초 |
| 9 | 논문 실험 | `gateway/app/experiments.py` + `tests/experiments_check.py` | E1·E2·E3 findings가 논문 주장과 같다 | ~30초 |

정적 검사(CI `static` job, 스택 불필요): pyflakes(`../endpoint-agent`, `workstation/managed/*.py`,
`workstation/bin/{bob-sso,workday,harness-check}` 포함), `bash -n`(`workstation/bin/bob-ask` 포함),
Node 24로 `node --check`(console.js·**charts.mjs**·login.js는 ES 모듈) + `node --test tests/console-state.test.mjs`,
검사기·단말 에이전트·망 대역·도구 설명 검사(`gateway/app/poisoning.py`)·종료 조건 결론(`supply_chain/exit_terms.py` — 오탐 반례
"Do not include credentials … in queries", 인증 없는 서버 → T2, Jev 확률+근거 문장 규칙) self-check, **`workstation/managed/render.py`로 하네스 4종(Claude Code·Codex·
Gemini CLI·OpenCode) 관리형 설정의 서버 목록이 `registry/catalog.toml`과 같은지 대조**, `tests/open_endpoints.py`
(무인증 API 목록 ↔ `full_stack_lab/README.md` 문장), `tests/schema_check.py`(기동마다 다시 만드는 CHECK 제약이 SQL 파일
사이에서 같은지 — 앞 파일이 좁히면 기존 행 때문에 재기동이 실패한다), compose 망·포트·서명 키 경계(모든 망의 명시 대역, Presidio는
privacy 망만), Rego 시험. → `.github/workflows/verify.yml`

## 2. 개별 실행

```bash
docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy -v
docker compose exec -T gateway python -m app.classify
docker compose exec -T gateway python -m app.acceptance
./console.sh harnesses
./console.sh workday all --mode scripted --check
python3 tests/termination_flow.py
tests/security_regression.sh
./console.sh experiment e1 && python3 tests/experiments_check.py reports/experiment-e1.json
./console.sh replay 100          # 후보 정책: REPLAY_POLICY_DIR=./candidate-opa
```

호스트에서 도는 스크립트(`termination_flow.py`, `security_regression.sh`, `watch.py`)는
`LAB_CONSOLE_URL`·`LAB_GATEWAY_URL`로 포트를 받는다. `console.sh`가 `.env`의 포트로 export한다.
직접 돌릴 때는 `export LAB_CONSOLE_URL=http://127.0.0.1:18000 LAB_GATEWAY_URL=http://127.0.0.1:18080`.

## 3. 시험을 쓸 때의 규칙 (여기서 실제로 밟은 것들)

- **거짓 통과 금지.** 검사 도구가 죽으면 실패여야 한다. 예: 포트 검사 파이썬이 문법 오류로 빈 문자열을
  냈고 `${exposed:-none}`이 그걸 "노출 없음"으로 읽었다 → 성공했을 때만 `none`을 출력하게 고침.
- **스스로 원복.** 상태를 바꾸는 시험(OPA 정지, 서버 정지, 감사 트리거 해제, 승인 해시 변조, 관찰 모드)은
  `trap`/`finally`로 되돌린다.
- **남의 절차를 되돌리지 않는다.** 누가 종료 케이스를 열어 둔 서버는 acceptance가 SKIP한다(복원하지 않음).
  workday `--check`는 그 경우 실패한다 — 정상이다. 케이스를 정리한 뒤 다시 돌린다.
- **판정은 결정·정책 id까지 본다.** "Block이면 됨"이 아니라 `MCP-CATALOG-001`인지 본다. 다른 이유로
  막힌 것을 통과로 세면 통제가 사라져도 모른다.
- 새 통제를 넣으면: Rego 시험 + (Gateway 경로면) acceptance 한 건 + (업무 시나리오면) TOML 한 건.

## 4. 알려진 제약
- workday의 llm 모드는 모델 품질에 좌우된다(기본 `qwen3.5:2b-q4_K_M`). 기대 판정 대조는 scripted 모드로만 한다.
- 보안 회귀는 OPA와 mcp-git을 잠깐 멈춘다. 다른 사람이 Console을 쓰는 중이면 몇 초간 차단 판정이 난다.

## 실기기 키트 (`tests/field_kit_check.py`, 16건)
가짜 IdP·Gateway에 대해 키트 전체를 돌린다. D-51 부분: 실제 VM의 `claude mcp list` 줄(계정 커넥터·플러그인·stdio·SSE·Gateway 서버)을
보고 항목으로 바꾸고 경로 속 키를 보내지 않는지, 거부가 오면 사용자 설정의 `deniedMcpServers`에 넣되 직원이 직접 넣은 항목은
남기는지, Codex 블록의 `[apps.<id>]`·`[features]`와 직원 `[features]`가 있을 때 건너뛰는지, `header`가 6시간에 한 번만 보고를
떼어 내는지, `managed --connectors`가 `managed-settings.json`과 루트 키가 앞선 `requirements.toml`을 만드는지. CI의 field 단계는 실제
Claude Code·Codex를 설치한 러너에서 `report`가 "N건 보고"로 끝나는지 본다.

## 계정 삭제·내부 Git 조직 (`tests/field_account_git_test.py`)
`./console.sh test`가 도입 검증 시험과 같은 방식(Gateway 이미지, 네트워크 없음)으로 돌린다. root·본인 삭제 거부와 삭제의 표식
처리, 이미 있는 Gitea 사용자도 조직의 읽기 팀(`Members`)에 들어가는지, 새 팀이 전체 저장소 코드 읽기로 만들어지는지.

## 도입 자동 검증 회귀
`./console.sh test`에 `tests/intake_validation_test.py`를 포함한다. Gateway 이미지의 의존성을 사용하지만 네트워크가 없는 별도 컨테이너에서 실행한다. 자동 대기열 등록, 문서의 commit 고정·범위 제한·symlink 제외, 부분 검사 실패 시 증적 보존, 치명점 자동 거부, 관리자 전용 보고서·파일 allowlist, 문서 조사로 원격 승인 게이트를 우회할 수 없는지를 검증한다. 스캐너 단위 회귀의 출력은 fixture이며 실제 공급망 검사 결과와 구분한다.

보안 회귀의 가상 도입 요청은 워커를 잠시 멈춘 상태에서 승인 경계를 시험하고 원복한다. 존재하지 않는 테스트 저장소가 자동 워커에 잡히는 경쟁을 방지한다.
