# 검증 — 무엇이 무엇을 보장하나

> 한 번에: 일회용 랩에서 `cd full_stack_lab && TERMINATION_DISPOSABLE_LAB=1 ./console.sh test` (스택이 떠 있어야 한다. CI는 폐기 보관 초기화와 `up --no-llm` 후 실행).
> 결과물은 `full_stack_lab/reports/`에 남는다. 실패 하나라도 있으면 종료 코드 1.

## 1. 층별 구성

D-125·126 오프라인 검사는 `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p response_cap_idempotency_test.py -v`다.
제품 함수 본문과 DB/scanner 대역을 사용하며 MCP 실행 증거가 아니다. `pglast`·`cryptography`가 없으면 SQL 문법·서명 fixture 각 1개는 미실행이다.
실제 DB 경쟁·완료 이력·lease 만료·미확인 복구는 `dispatch_intent_pg_check.py`, 실제 Gitea 재전송 효과·응답 보류는
`dispatch_effect_lab.py`에 있다. [환경 제약과 메인 실행 명령](../../research/llm-wiki/status/reports/2026-10-17-response-cap-idempotency.md)을 따른다.

D-115의 네트워크·DB 없는 단위 시험은 저장소 루트에서
`python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p upstream_session_reuse_test.py -v`로 실행한다.
실제 풀과 선택한 제품 함수 본문을 대역 SDK/DB 객체로 검사한다. 실제 SDK·MCP 서버 실행 증거는 아니며,
[T1–T12 대응과 기기 시험](../../research/llm-wiki/analysis/upstream-session-reuse/stage2.md)을 따로 확인한다.

| 순서 | 무엇 | 파일 | 보장 | 소요 |
| --- | --- | --- | --- | --- |
| 0 | 망 대역·콘솔 상태 | `scripts/network_prefix.py --self-check`, `tests/console-state.test.mjs` (node, 7건) | 대역 선택이 점유 대역을 피하고 소진 시 실패 / 활동 로그 병합(중복·잘못된 id)·검색·상태 문장(실패를 최신처럼 보이지 않음)·**시간대별 판정 버킷(`hourBuckets`), 그룹별 집계(`splitBy`), 하네스×서버 상키 데이터(`sankeyData`)** | 수 초 |
| 1 | Rego 단위 시험 | `opa/policy_test.rego` (96건) | 27칸 기본 판정 기준선, 권한 번들이 비면 전부 차단·번들 변경이 판정을 바꿈, MCP-* 통제, 예외(유효기간·범위·자가승인·보완통제), 승인형 예외, 민감정보 반출·연쇄(v2 입력), 관리대장 필수 항목, 충돌 우선순위 | 수 초 |
| 2 | 분류기 self-check | `gateway/app/classify.py` (`python -m app.classify`) | 경로·SQL·URL·메일·Redis 키 분류, DLP(주민번호·카드 Luhn·휴대폰·AWS 키·개인키·비밀번호), 행위 승격 | 수 초 |
| 2a | 도구 설명·커넥터 정책 self-check | `gateway/app/poisoning.py`(`python -m app.poisoning`), `gateway/app/connectors.py`(agent-service `python -m app.connectors`) | 공개된 tool poisoning 예시와 정상 설명(D-52), **세 묶음(계약·인자·결과)이 각자의 결과 무게에 맞는 규칙만 쓰는지와 정상 문장 대조군**(D-54) / 벤더 출처와 무관하게 처음부터 미승인 거부 대상, 승인 하나가 전체 계정 커넥터를 열지 않음, URL 비밀값 제거, 집행 상태는 미검증(D-53) | 수 초 |
| 3 | Gateway 인수 시험 | `gateway/app/acceptance.py` (스위트 `gateway-acceptance-v3`) | `/mcp/` 401+RFC 9728 챌린지, 역할별 도구 목록, OPA가 내어주는 권한 번들(`LAB-AUTHZ-001`), 허용 호출은 `P-AUTHZ-ALLOW-001`, 미승인·미등록 도구 차단, 스키마 검증, 계약 드리프트 차단→복구, 승인 1회 실행, 관찰 모드 기록, **결과 개인정보 마스킹, 개인정보 외부 발송 차단(MCP-DATA-EGRESS-001), 열람→반출 연쇄(P-CHAIN-001)**, 감사 체인, **`per-server-endpoint-for-harness-configs`(`/mcp/git/`의 도구 목록=승인 목록, `git_log` 허용, `client.endpoint=git`, `/mcp/nope/` 404), `tool-hidden-from-partner-still-decided`(협력사 목록에 없는 도구도 직접 호출하면 판정된다), `usage-relationship-scope-alerts`(이용 관계 밖 `hr.employees` → `P-SCOPE-001` 경보, 안 `sales.orders` → 허용, D-39), `server-check-changes-nothing`(연결 확인이 서버 상태·감사 원장을 바꾸지 않음, 없는 서버 404, 직원 403, D-40)** · **`console-registration-pins-and-expires`(랩 fetch를 다른 id로 Console 등록 — 검토하지 않은 계약 해시 409, `/mcp/<id>/`에 승인 도구만, 호출, 기한 지나면 `P-APPROVAL-EXPIRY-001`, 해제 후 404, D-49)** | ~40초 |
| 4 | 하네스 연결 확인 | `workstation/bin/harness-check`(`./console.sh harnesses`, `reports/harnesses.txt`) | PC 4대 × 하네스 4종이 관리형 MCP 서버 10종 전부에 Gateway로 붙는지 — 모델 호출 없이(`claude/gemini/opencode mcp list`, Codex는 `app-server` `mcpServerStatus/list`) | 수 초 |
| 5 | 직원의 하루 | `workstation/scenarios/*.toml` (21건, scripted) | 각 직원 PC에서 **MCP Inspector CLI**가 하네스와 같은 Gateway URL·SSO 토큰으로 실제 서버에 보내는 업무 21건이 기대 판정(Allow/Alert/Approval/Block)과 일치(판정은 Gateway `/api/activity`에서 직원 토큰으로 대조 — 하네스 출력 형식과 무관) | ~1분 |
| 6 | 종료 판정 흐름 | `tests/termination_flow.py` (21건) | UR-GITEA-DEV T3→T2→T1·종결, UR-EMAIL-ASSIST T3·위험 수용 없는 종결 거부·고지 요청서, 복원 | ~1분 |
| 7 | 보안 회귀 | `tests/security_regression.sh` (55건) | 망 분리(실제 소켓, Presidio 포함), loopback 게시, 읽기 API 토큰, Console 역할 경계, 로그아웃 즉시 효력, **원격 MCP 종료 조건(신청자 자기 신고 422·직원 기록 403·검증 없는 승인 409·위험 수용 사유로도 격리 검증 전 승인 불가·http 근거 422·관리자 기록 200·검증 뒤에도 격리 검증 전 승인 불가)**, OPA 정지→`P-CONTROL-FAIL-CLOSED`, 상위 서버 정지→미실행, **Presidio 분석기 정지→`P-DATA-INSPECTION-001`, 마스킹기 정지→실행됨·`MCP-OUTPUT-001`**, 감사 변조 탐지, 계약 잠금 일치, 격리 워커 검사기 | ~1.5분 |
| 7a | 적대적 회귀 | `tests/adversarial_check.py` | 통제를 **우회하는 방법**을 실제 ingress로 보낸다: 내부 주소의 다른 표기(10진·8진·16진·축약·IPv4-mapped·wildcard DNS·FQDN), 텍스트로는 읽기처럼 보이는 SQL(SELECT INTO·CTE DELETE·pg_read_file·COPY TO PROGRAM), 인자에 실린 지시문(영·한·보이지 않는 문자), 경로 회피 표기, 메일·URL로 나가는 자격 증명(GitHub·Slack·`sk-`·JWT). **정상 업무 대조군**(커밋 해시가 든 사내 메일, 창 함수·`extract` 분석 쿼리 포함)으로 오탐을 함께 센다 — 전부 막는 통제는 공격 점수가 만점이어도 쓸 수 없다. 2026-10-01: 공격 42/42 · 정상 16/16 | ~1분 |
| 7b | 주입 탐지율(요청 시) | `tests/injection_corpus_check.py` | PyRIT 고정 커밋의 garak latent-injection 지시문 시드로 `poisoning` 규칙의 탐지 수를 잰다(26건 중 21, 기준 미달이면 exit 1). 네트워크가 필요해 `console.sh test`에는 넣지 않는다 | 수 초 |
| 7b2 | 텍스트 규칙 코퍼스 측정(요청 시) | `tests/inspection_corpus_eval.py build\|run` | 고정·SHA-256 공개 코퍼스 9,463건으로 결과·인자·계약 규칙의 오탐·미탐을 dev/held-out으로 잰다. 인자 크기·스키마·경로 게이트는 `--gates`. 네트워크는 `build`만 | 수십 초 |
| 7b3 | 한국어 PII·Secret 측정(요청 시) | `tests/korean_pii_eval.py` | 합성 한국어 식별자·자격을 일회성 Presidio 컨테이너로 마스킹해 값이 남는지, 정상 유사 46건이 가려지는지, 지연·100 KB 병리 입력을 잰다 | 1분 |
| 7c | 팀원 PAC-15 초안 검토(요청 시) | `research/pac15-review/run.sh` | 원본과 수정본을 같은 300건으로 — 원본 정상 200/200·결함 59, 수정본 200/200·0 | 수 초 |
| 7d | 규격 세대 확인(요청 시) | `tests/protocol_versions_check.py` | 실제 facade가 옛 규격(`initialize`+세션 ID, 2025-11-25)과 2026-07-28(`server/discover`, 세션 없음)을 모두 받고, 도구 목록 힌트가 `private`·`ttlMs 0`이며, 공급자가 되묻는 요청(`InputRequiredResult`)에는 답하지 않는다(D-74). gateway 이미지 안에서 loopback으로, DB·정책 대체 | 수 초 |
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

2026-09-30 클린 검증은 별도 checkout·Compose 프로젝트·신규 볼륨에서 `reset → up --no-llm → test`로 수행한다.
`tests/reservation_effect_check.py`는 실제 PostgreSQL row lock을 유지한 채 6개 쓰기와 2개 중복 쓰기를 보내고,
Gateway 응답과 **별도 회사 DB의 값 변화**를 대조한다. 시험 값은 finally에서 복원한다.
`tests/credential_binding_check.py`는 private 임시 파일에서 resource·주체·만료·권한 형식을 검증한다.
외부 서비스 응답을 생성하는 mock MCP 서버는 이 실제 서비스 시험에 사용하지 않는다.

실제 서비스 시험은 계정 자격을 별도 private volume에 배치한 뒤 opt-in으로 수행한다.
`tests/real_mcp_check.py`는 일곱 공식 원격 MCP의 직접 연결·대표 읽기와 native CLI 대조군을 검사한다.
`tests/real_mcp_gateway_check.py --review-out /output/review.json`으로 도구·스키마·warning을 먼저 읽고,
같은 파일을 `--reviewed`에 전달한다. warning을 자동 승인하지 않는다. 유효기간 1일의 임시 등록은 finally에서
해제하며, 출력은 결정 ID·전달/실행 상태·내용 digest만 남긴다. mount 출력 경로는 Compose 기본 read-only
`/reports`와 겹치지 않는 `/output`을 쓴다. 두 단계는 `{"requester": {email,password}, "approver": {email,password}}`를
stdin에서 받는다(D-57·D-59). 임시 등록도 `tests/intake_register.py`로 신청 → 계약 검토 → 다른 사람의 승인 → 활성화를
거친다. 관리자 직접 등록은 409다. 같은 도우미를 실기기에서 Console 주소로 직접 실행해 공급자 MCP를 등록한다. 승인은 공급자 보증
(`--supplier-assurance`)과 영향평가 입력(`--impact-input`) JSON을 요구하며 기본값을 쓰지 않는다. 승인 경로를 밟는 시험은 합성 값을
`tests/intake_fixture.py`에서 받는다(D-137·D-143).

SSH VM의 새 native Docker 이미지에는 공식 Claude Code 2.1.282·Codex 0.158.0을 설치한다. 임시 profile의
일곱 실제 MCP 연결과 managed 정책 적용을 비교하되 host SYN 관측을 따로 기록한다. SYN은 전체 interface
capture에서 중복될 수 있으며 MCP 호출 횟수가 아니다. `tests/testbed_network_check.py --out report.json`은
동일 이미지의 fresh internal network에서 일곱 실제 destination의 TLS 실패와 고정 relay를 통한 실제 field
Gateway health 성공을 대조한다. 이는 해당 disposable container의 경계이며 host 전체의 보장은 아니다.
재현 이미지 정의는 `tests/native_testbed.Dockerfile`이며 `full_stack_lab`을 context로 빌드한다. npm cache는
같은 layer에서 정리한다. 테스트 VM의 20GB 디스크에서 중복 설치 layer가 공간을 소진한 실패를 확인했기 때문이다.
field 배포 후에는 같은 이미지의 `tests/field_release_check.py`로 SSH VM에서 release 일치·MCP 관리 API 403·
기존 승인 Microsoft Learn 도구의 실제 호출을 검증한다. 자격은 stdin으로 주고 생성한 토큰·refresh를 폐기한다.

`tests/real_warning_review_check.py`는 별도 opt-in이다. 실제 Notion의 경고 도구를 도입 신청으로 임시 등록해 명시적
검토 없는 계약 검토는 서버가 409, hash에 결합한 검토는 READY, 검토 hash를 무효화하면 `MCP-CATALOG-001`·전달 전
차단인지 확인한다. stdin은 위와 같은 requester·approver 두 사람이다.
통과 경로에서 해당 공급자 helper는 실행하지 않으며 임시 레코드만 finally에서 해제한다.
`PYTHONPATH=/app`으로 runtime 사용자에게 실행하며 일곱 서비스 시험과 동시에 registry를 바꾸지 않는다.

서명·scope 시험과 scripted 업무에는 일반 단위 검사가 포함된다. 이것을 외부 벤더의 실제 업무 효과 증명과
섞지 않는다. Supabase docs, Sentry 조직 목록, Figma 신원, Zapier action 발견은 DB 쓰기·디자인 수정·action
실행을 검증한 것이 아니다. LLM을 호출하지 않으며 검증 결과는 [보고서](OVERHAUL_VALIDATION_2026-09-30.md)에 기록한다.

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
docker compose run --rm --no-deps --entrypoint python -e LAB_GATEWAY_URL=http://gateway:8080 \
  -v "$PWD/tests:/tests:ro" gateway /tests/adversarial_check.py
```

호스트에서 도는 스크립트(`termination_flow.py`, `security_regression.sh`, `watch.py`)는
`LAB_CONSOLE_URL`·`LAB_GATEWAY_URL`로 포트를 받는다. `console.sh`가 `.env`의 포트로 export한다.
직접 돌릴 때는 `export LAB_CONSOLE_URL=http://127.0.0.1:18000 LAB_GATEWAY_URL=http://127.0.0.1:18080`.

## 게이트웨이 이미지 단독 실행 대상 아님

아래 파일들은 `python full_stack_lab/tests/<파일>`만으로 끝나는 독립 검사가 아니다. 실패 로그를 제품 회귀로 읽기 전에 표의 실행 조건과 해당 스크립트 상단의 실행 설명을 확인한다. `console.sh test`에서 실행되는 파일도 있으나, 그 명령은 이미 기동된 일회용 랩과 Docker Compose 서비스가 필요하다.

| 파일 | 이미지 밖/주변 실행 조건 | 근거 |
| --- | --- | --- |
| `adversarial_check.py` | 실행 중인 Gateway, 사내 테스트망, 직원 토큰과 `LAB_GATEWAY_URL` | 실제 `/mcp/<server>/` ingress에 정상·공격 호출을 보냄. `console.sh test` 527–532행은 `docker compose run`과 Gateway 주소를 설정한다. |
| `field_release_check.py` | 배포된 field Gateway, SSH 검증 VM, 서버·리비전 인자와 requester 자격 | 파일 상단이 SSH VM·실제 Microsoft Learn 읽기를 명시하고 `--url`, `--server`, `--expected-revision`을 요구한다. |
| `intake_worker_scanners_check.py` | 격리된 intake-worker 이미지, Syft·Trivy·Semgrep·Gitleaks, Trivy 캐시 | 파일 상단이 worker 이미지 전용 실행과 `TRIVY_CACHE_DIR`를 명시한다. |
| `managed_enrollment_check.py` | 실행 중인 Gateway·agent-service와 공유 DB | 파일 상단 실행 예가 `docker compose exec gateway`이며 실제 IdP/DB 경계를 검사한다. |
| `mcp_result_services_check.py` | Presidio analyzer/anonymizer와 Gitleaks 실행 파일 | 파일 상단이 실제 검사 서비스·실행 파일을 요구하며, 검사 실패 시 차단 계약을 검증한다. Gateway 이미지 하나에는 이 서비스들이 없다. |
| `pac_boundary_check.py` | Gateway에 마운트된 `REGISTRY_DIR/capabilities.json` | `pac.capabilities()`는 파일 누락을 빈 권한으로 간주하지 않고 실패한다. `console.sh test` 520행은 실행 중인 Compose Gateway 안에서 실행한다. |
| `policy_replay_lab_check.py` | PostgreSQL, 실행 중인 Gateway 부트스트랩 및 OPA 연결 | 파일 상단이 일회용 랩 OPA를 명시하고 `core.bootstrap()`으로 DB 초기화를 시작한다. |
| `provenance_gitea_check.py` | 버리는 Gitea 서비스와 `GITEA_URL`, `GITEA_USER`, `GITEA_PASSWORD` | 파일 상단에 필수 환경변수가 있고, Gitea 저장소에 파일을 올려 서버 응답 digest를 비교한다. |
| `real_mcp_check.py` | 외부 인터넷, 일곱 공식 공급자 MCP와 해당 계정 자격 | 파일 상단의 opt-in live vendor probe 설명 및 CLI의 명령 인자가 기준이다. Gateway 집행 검사가 아니다. |
| `real_mcp_gateway_check.py` | 실행 중인 Gateway, reviewed contract, 별도 requester·approver 자격 | 파일 상단에 두 단계 명령과 stdin 자격 형식이 있다. 실제 등록·호출 후 임시 registry 항목을 제거한다. |
| `real_warning_review_check.py` | 실행 중인 Gateway, 앞선 계약 검토 결과, Notion endpoint 및 requester·approver 자격 | 파일 상단이 opt-in, `--url`·`--reviewed`, 별도 두 사람 자격을 요구한다. |
| `reservation_effect_check.py` | Docker Compose 랩, corp PostgreSQL 및 실제 PostgreSQL MCP | 파일 상단은 clean-up 뒤 실행하도록 하고, `docker compose exec corp-db`로 독립 DB 효과를 센다. `console.sh test` 523행에서도 호스트 명령으로 실행한다. |
| `testbed_network_check.py` | SSH 시험 VM, Docker, 사전 빌드 native test 이미지, 실행 중 Gateway와 `--out` | 파일 상단이 fresh Docker testbed를 명시하고 CLI가 `--out`을 필수로 받는다. |

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

## 격리 랩: 호출 예약·전송 의도·종료·토큰 폐기 (`tests/termination_dispatch_lab.sh`)
솔루션 기기에 일회용 PostgreSQL·OPA·Presidio·Gitea와 Gitea 프로젝트의 MCP 서버 이미지를 따로 띄워 검사한다(제품 스택은 건드리지 않는다).
WSL에서 `tests/termination_dispatch_lab.sh up` → `run <검사>` → `down`. 종료 검사는 제공자 토큰을 폐기하므로 `run` 사이에 `reset`을 쓴다.
`up`은 3시간 뒤 스스로 지운다. 이미지에 Gitleaks 라이브러리가 없어 비밀 검사만 "아무것도 찾지 못함"으로 바꾼다(단위 수준).

| 검사 | 확인하는 것 | 층 |
| --- | --- | --- |
| `dispatch_intent_pg_check.py` | 동일 호출 24개·서로 다른 호출 12개 동시 예약, 해제·만료 경쟁, 전송 경계의 거부, 승인 소비, 240건 전송과 종료 cutover 경쟁, 풀 닫기 | 실제 PostgreSQL |
| `dispatch_effect_lab.py` | 같은 호출 12개·다른 호출 10개 동시 실행, 호출량 상한, 승인 6명 경쟁, 승인 재사용, 답을 잃은 호출, 계정 중지, SIGKILL | 실제 Gitea MCP 서버, 효과는 Gitea 이슈 수로 센다 |
| `termination_lab.py` | 전송 중 호출과 cutover, 폐기한 토큰의 자원 서버 거부, 물을 수 없을 때, 비밀 값 부재, 자격 파일 재읽기, 폐기 서버 유지 | 실제 Gitea·MCP 서버 |
| `token_revocation_pg_check.py` | 실제 서명 토큰의 계열 폐기, 폐기와 발급 경쟁, 발급 실패 롤백, 장치 폐기 | 실제 PostgreSQL |

## 실기기 키트 (`tests/field_kit_check.py`, 16건)
가짜 IdP·Gateway에 대해 키트 전체를 돌린다. D-51 부분: 실제 VM의 `claude mcp list` 줄(계정 커넥터·플러그인·stdio·SSE·Gateway 서버)을
보고 항목으로 바꾸고 경로 속 키를 보내지 않는지, 거부가 오면 사용자 설정의 `deniedMcpServers`에 넣되 직원이 직접 넣은 항목은
남기는지, Codex 블록의 `[apps.<id>]`·`[features]`와 직원 `[features]`가 있을 때 건너뛰는지, `header`가 6시간에 한 번만 보고를
떼어 내는지, `managed`가 인벤토리 없이도 엄격한 세 파일을 만들고 이전 `allowAllClaudeAiMcps: true`를 무시하는지,
Codex의 name+URL identity·Apps/플러그인·웹 제약과 Claude의 계정 커넥터·마켓플레이스 제한이 있는지. CI의 field 단계는 실제
Claude Code·Codex를 설치한 러너에서 `report`가 "N건 보고"로 끝나는지 본다.

## 실제 공급자 MCP 시험 (opt-in, `tests/real_mcp_check.py`)

GitHub·Supabase·Sentry·Notion·Figma·Zapier·Context7의 공식 원격 MCP를 별도 프로필에 등록하고 실제 OAuth/PAT로
연결·읽기 호출을 검사한다. mock으로 대체하거나 로그인 실패를 통과로 세지 않는다. 일반 CI에는 계정 자격을 넣지 않는다.
재실행 방법과 서비스별 조회 범위는 [SECURITY_BOUNDARIES.md](SECURITY_BOUNDARIES.md#6-실제-많이-쓰는-mcp로-시험)에 있다.

`native`는 폐기 가능한 workstation 컨테이너에서 실제 Claude Code·Codex에 일곱 MCP를 먼저 연결한 뒤,
PC 키트의 관리형 정책을 배포하고 같은 직접 연결이 사라지는지 검사한다. 컨테이너에서 외부 목적지로 나가는 HTTPS SYN을
호스트에서 별도로 수집하여 Gateway 로그와 독립적으로 확인한다. 승인된 Gateway 목적지는 이 외부 목적지 집계에서 제외한다.
이것은 해당 CLI·정책·HTTP MCP 경로의 증거이며 현장 OS 전체의 egress, SaaS 쓰기/회수, 웹/클라우드 연결의 증거는 아니다.

## 계정 삭제·내부 Git 조직 (`tests/field_account_git_test.py`)
`./console.sh test`가 도입 검증 시험과 같은 방식(Gateway 이미지, 네트워크 없음)으로 돌린다. root·본인 삭제 거부와 삭제의 표식
처리, 이미 있는 Gitea 사용자도 조직의 읽기 팀(`Members`)에 들어가는지, 새 팀이 전체 저장소 코드 읽기로 만들어지는지.

## 도입 자동 검증 회귀
`./console.sh test`에 `tests/intake_validation_test.py`를 포함한다. Gateway 이미지의 의존성을 사용하지만 네트워크가 없는 별도 컨테이너에서 실행한다. 자동 대기열 등록, 문서의 commit 고정·범위 제한·symlink 제외, 부분 검사 실패 시 증적 보존, 치명점 자동 거부, 관리자 전용 보고서·파일 allowlist, 문서 조사로 원격 승인 게이트를 우회할 수 없는지를 검증한다. 스캐너 단위 회귀의 출력은 fixture이며 실제 공급망 검사 결과와 구분한다.

보안 회귀의 가상 도입 요청은 워커를 잠시 멈춘 상태에서 승인 경계를 시험하고 원복한다. 존재하지 않는 테스트 저장소가 자동 워커에 잡히는 경쟁을 방지한다.

## 승인·출처 회귀 (D-90~D-94, 2026-10-15)
- 로컬 단위: `tests/provenance_check.py`(해시 두 구현의 일치·조작 탐지·출처 누락), `tests/intake_identity_test.py`(검사 신선도·치명 수용·범위 심사·독립성),
  `tests/pac_delegation_check.py`, `tests/intake_validation_test.py`(워커·승인 경로). 모두 DB·네트워크를 대역으로 둔 단위 수준이다.
- Rego: `opa test`(91건) — 위임 4경우(검증됨·클라이언트 보고·사실 없음·위임 아님)를 포함한다.
- 격리 DB 시험(솔루션 기기, 운영 DB·컨테이너를 건드리지 않음): 새 PostgreSQL 18 + 이 저장소의 `opa/`를 서빙하는 OPA + Gateway 이미지.
  `tests/intake_identity_pg_check.py`가 실제 SQL·트리거·정책 판정으로 27건을 확인한다 — 독립성 거부 기록, 출처·검사 신선도 보류, 위험 수용 만료,
  만료·철회·계약 변경 뒤 거부와 갱신 불가, 범위 없는 도구 제외, 하네스 설정의 서버 집합, 위임 거부, 무효 처리와 append-only.
  MCP 서버(tools/list·최종 전달)·PII 분석기·내부 Git 호출·워커 산출물은 대역이므로 실환경 증거가 아니다.
- 실제 스캐너 시험: `tests/intake_worker_scanners_check.py` — 기기의 `intake-worker` 이미지(네트워크 없음, Trivy 캐시 사본)에서 워커 `validate()`를 실제 Syft·Trivy·Semgrep·Gitleaks로 합성 소스 트리에 돌린다. clone만 대역이다.
- 임시 Gitea 컨테이너 시험: `tests/provenance_gitea_check.py` — 실제 Gitea 1.27.3이 내주는 보관본의 해시가 Git 객체에서 계산한 해시와 같은지.
- 재생: `tests/policy_replay_lab_check.py`가 `replay_cases_pac15.json`을 격리 OPA에 돌린다.
