# 코드 감사 — MINT main `cdef0bb` (2026-10-25)

> 용도: [리팩토링·최적화 제안서](README.md)의 근거. 작성: Claude Code 서브에이전트(Sonnet, 읽기 전용)가 정적 집계하고 리더가 핵심 주장(폐기 목록 동기 재검증·도구별 트랜잭션과 `count(*)`·이중 인증·`/api/overview` 10연결·중첩 연결·원장 전역 락·CI 실측)을 원본 코드·GitHub Actions 기록과 대조해 확인했다. 집계 스크립트는 [tools/](tools/)에 있다(`python -I -B -X utf8 tools/nested_tx.py full_stack_lab/gateway/app` 등, 저장소 루트에서). 라이브 DB·운영 원장에는 접근하지 않았다.


- 대상: main `cdef0bb`의 클린 클론. 저장소 파일은 만들지도 고치지도 않았다(읽기 전용).
- 방법: `grep`·`sed -n`·python `ast`([tools/](tools/)의 `ast_stats.py`·`ast_quality.py`·`nested_tx.py`).
- 근거 등급: 코드를 읽고 센 값은 「정적 집계」, 실제로 돌려 본 값은 GitHub Actions 실행 기록(`gh run view`, 읽기만)과 저장소 안의 기존 보고서에서만 가져와 「실측」으로 표시했다. 추정은 「추정」, 못 본 것은 「미확인」.
- 행 번호는 따로 적지 않으면 `full_stack_lab/gateway/app/` 기준이다. 라이브 DB·운영 원장에는 접근하지 않았다.

## ① 요약

1. **호출 1건의 직렬 비용.** tools/call 한 건이 풀 체크아웃 약 35회(관리형 PC 약 51회)·SQL 약 49문장(약 65문장)·OPA 2~4회·업스트림 3~4회를 한 코루틴에서 순차 `await`한다. 계약·PAC·인증은 같은 값을 두세 번 다시 읽는다. 게이트웨이는 uvicorn 워커 1개·DB 풀 10이다. — `core.py:2255-2640`, `core.py:1682-1881`, `db.py:16-17`, `gateway/Dockerfile` CMD.
2. **폐기 목록 전체 재검증.** 호출 한 건이 서명 달린 폐기 목록(`journal.jsonl`)을 flock으로 잠그고 레코드마다 Ed25519 검증하는 동기 호출을 5회 이상 한다(도구 목록은 도구 수만큼 더). — `disposal.py:70-95,143-152`, `agent_contract.py:166`, `core.py:1216`, `tool_sunset.py:72`+`retention.py:78-86`.
3. **S4-01의 뿌리는 남았다.** D-243은 교착을 풀었지만 `tool_sunset.check`는 tools/list 도구마다 트랜잭션 1건이고, 봉인이 없으면 호출마다 `decisions` 전수 `count(*)`를 한다(봉인 기록을 쓰는 코드가 없어 — `disposal.py:193`은 읽기뿐 — 봉인은 사실상 항상 없음). — `tool_sunset.py:78-82,99-149`, `mcp_facade.py:145`.
4. **풀을 넓게 쥐는 관리 API와 중첩 연결 5곳.** `/api/overview` 한 요청이 풀 연결을 최대 10개 동시에 쥐고(콘솔 탭이 폴링), 트랜잭션 안에서 두 번째 연결을 얻는 곳이 `local_jobs.py:648`, `local_jobs.py:751/756`(`idp.py:235,255,279,307` 경유), `agent_service.py:2466-2625`, `ops_response.py:234`, `user_suspend.py:37`에 남아 있다. — `main.py:514-569`.
5. **시험이 CI 밖에 있다.** 실행 파일 189개 중 144개가 `verify.yml`·`console.sh`에 이름이 없고, PostgreSQL 시험 16개 중 15개(S4-01 회귀 `tool_sunset_pool_pg_check.py` 포함)는 어디에도 연결돼 있지 않다. 로컬 실행기 `run_local_suite.py`(10-25 보고: 통과 115·생략 17·실패 5)는 CI에 없다. — `.github/workflows/verify.yml`, `full_stack_lab/console.sh:581-625`.
6. **그 밖에 큰 것.** Presidio는 JSON 잎 문자열마다 순차 HTTP 1회+요청마다 인식기 약 4.7KB 재전송(`privacy.py:34,117-150,252-269`). 모든 판정이 `audit_chain` 한 행 락 안에서 policy_input 포함 전체를 해시·INSERT하고(`core.py:2104-2147`), `verify_audit_chain`은 전 행을 메모리에 올린다(`core.py:2230-2235`).
7. **실측.** CI 한 번은 15~18분(job: 정적 1~1.5분·배포 설치 3.6분·LiteLLM 5.5분·전체 검증 12.8~15.9분), `console.sh test` 345초, `install.sh` 118초(2026-10-25 실행 기록 2건). 타임아웃 15/60/75/75분은 실측의 4~5배다.
8. **초안과 다른 사실 7건**은 문서 끝 「⑤ 정정 메모」에 모았다(시험 「스택 필요 146」, 「CI 1시간 초과」, 「p50/p95 화면 없음」, 모듈 수, 키트 세 벌, Rego 건수, D-243 잔존 여부).

## ② 영역별 조사

### A. tools/call 한 건의 핫패스 비용 분해

**전제(정적 집계).** 비관리자 직원이 심사된 도구를 호출하고 결과는 Allow인 읽기, 데이터 등급 public, 내부(비공급자) 서버, 사용자 자격 불필요. 결과 JSON의 문자열 잎 수를 k라 한다. 표의 「DB」는 `체크아웃/문장`(풀 연결 획득 수/SQL 문장 수)이다. `db.fetch_*`·`db.execute`는 호출 하나가 체크아웃 하나이고, 풀은 `autocommit`을 켜지 않았으므로(`db.py:31-34`: `kwargs`에 `row_factory`만) 체크아웃마다 BEGIN·COMMIT이 따라붙을 수 있다(추정: psycopg3 기본 동작, 왕복 수는 세지 않았다).

**A-1. 단계별 표(허용 경로 순서)**

| # | 단계 | 함수 | 파일:행 | DB | HTTP | 락 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 인증 1회차 | `RequireBearer` → `authenticated_user` | `main.py:71-79`, `agent_contract.py:153-195` | 2/2 (관리형 +4/+4) | - | 폐기목록 flock | JWT 검증+`disposal.blocked(jti)`(목록 전체 검증, 동기)+`agent_revoked_tokens`+`principals`. 관리형 분기는 `managed_failure`(endpoint_agents 1+managed_policy 3). 현장 모드는 비관리자 전원이 관리형(`agent_service.py:103`) |
| 2 | 세션 확인 | `ServerPath` → `mcp_sessions.active` | `main.py:188-196`, `mcp_sessions.py:21` | 1/1 | - | - | `Mcp-Session-Id`가 있을 때 |
| 3 | 인증 2회차 | `_caller` → `authenticated_user` | `mcp_facade.py:46-56` | 2/2 (+4/+4) | - | 폐기목록 flock | 같은 요청에서 1과 똑같은 작업을 다시 한다 |
| 4 | 분류 | `classify.classify` | `core.py:2270`, `classify.py:810` | 0 | - | - | 동기 CPU: DLP 정규식·pg_query 파서·`registry.*` stat |
| 5 | 중지 만료 | `automatic_suspend.expire` | `core.py:2276`, `automatic_suspend.py:26-37` | 1/2 (tx) | - | advisory(principal) | 만료할 것이 없어도 호출마다 락+UPDATE |
| 6 | 주체 조회 | `db.fetch_one` | `core.py:2280` | 1/1 | - | - | principals+중지 EXISTS |
| 7 | 정책 대장 | `policy_ledger` | `core.py:2310`, `core.py:1619` | 0 | OPA GET(최초 1회) | - | 전역 `_ledger_cache`, 이후 갱신 없음 |
| 8 | 레지스트리·허용 사용자·관리형 | `registry.*`, `managed_failure` | `core.py:2314-2328` | 0 (관리형 4/4) | - | - | `registry.server()` 호출마다 stat 2~4회 |
| 9 | 이용 기한 | `tool_sunset.check` | `core.py:2330`, `tool_sunset.py:86-159` | 2/5 | - | advisory(서버/도구)+폐기목록 flock | `retention.setting()` 1 + tx(lock·last_event·**`count(*) FROM decisions`**·max(created_at)) |
| 10 | 개인 자격(GitHub 등만) | `missing_connection` | `core.py:2342-2349`, `upstream.py:130-138` | 0~2 | - | - | 해당 서버만 |
| 11 | 예약 | `_reserve_call` | `core.py:1492-1560`(호출 2357) | 1/5 | - | advisory(principal), 한 tx | 동시성·분당 상한·차단 연속 집계 |
| 12 | 입력 크기·NUL | `json.dumps` | `core.py:2367-2376` | 0 | - | - | 동기 직렬화 |
| 13 | 도구 행·스키마 | `db.fetch_one`, `Draft202012Validator` | `core.py:2378-2385` | 1/1 | - | - | 검증기를 매 호출 생성 |
| 14 | 입력 검사(외부·쓰기·공급자 호스팅만) | `secret_scan.labels`, `privacy.analyze`, `mask_payload` | `core.py:2410-2420` | 0 | Presidio 1 (마스킹 도구는 2+k) | Semaphore 2·4 | 두 검사는 독립인데 순차 |
| 15 | 흐름 | `_sequence_flags`, `_flow_sources` | `core.py:2430-2437`, `core.py:1385-1427` | 0~2 | - | - | 외부 목적지·쓰기/실행·공급자 호스팅일 때만 |
| 16 | 계약 | `_contract` | `core.py:2438`, `core.py:1174-1237` | 4/4 | OPA GET egress 0~1 | 폐기목록 flock | 쿼리 4개가 서로 독립인데 순차 |
| 17 | 정책 입력 | `shadow_count_for`, `shadow_listener_count_for`, `_relationship_scope`, `catalog_version` | `core.py:2440-2457`, `endpoint_plane.py:487,1537` | 3/3 | - | - | `catalog_version()`은 카탈로그 파일 전체 읽기+SHA-256(`registry.py:70-72`) |
| 18 | PAC 사실 | `pac.build` | `core.py:2470`, `pac.py:247-386` | 3/3 | - | - | 폐기 토큰(1에서 이미 조회)·예약 행·**`decisions` JSONB 비교(`pac.py:336`)**. 디스크: `residency.load_pack` 2파일, `capabilities()` stat |
| 19 | OPA 판정 | `_policy` | `core.py:2475`, `core.py:1668-1679` | 0 | OPA POST 1 | - | 입력 수 KB~수십 KB, OPA 결정 로그 console(`deploy/compose.yaml:93`) |
| 20 | 집행 모드 | `enforcement_mode` | `core.py:2490`, `core.py:1240-1248` | 1/1 | - | - | 설정 1행을 호출마다 조회 |
| 21 | 동의(필요 도구) | `consent.missing` | `core.py:2516`, `consent.py:33-53` | 1/1(+삽입) | - | - | |
| 22 | 예약 갱신 | `db.execute` | `core.py:2573` | 1/1 | - | - | |
| 23 | 업스트림 세션 | `upstream.session` | `core.py:1715`, `upstream.py:391-421` | 0~3 | MCP initialize(+initialized) — 세션 재사용이 안 될 때 | `_sweep_lock`(`upstream.py:249`) | 재사용은 대화 세션 헤더+레거시 규격일 때만(`upstream.py:411-419`). `_sweep` 2초당 1쿼리, 자격 파일 반복 읽기(`upstream.py:92-95`) |
| 24 | 업스트림 tools/list+등록 도구 | `list_all_tools`, `db.fetch_all` | `core.py:1725-1726` | 1/1 | MCP tools/list ≥1 | - | 호출마다 계약 대조. 두 작업은 독립인데 순차 |
| 25 | 전송 직전 재검증 | principals, `_contract`, `pac.build`, `_policy` | `core.py:1772-1810` | 8/8 (관리형 +4/+4) | OPA POST 1 (+GET 0~1) | 폐기목록 flock | 16·17·18·19단계를 한 번 더 |
| 26 | 전송 의도 기록 | `dispatch.record` | `core.py:1813`, `dispatch.py:66-141` | 1/5 (쓰기·승인 시 최대 9) | - | advisory(principal)+FOR SHARE 3행 | |
| 27 | 호출 | `client.call_tool` | `core.py:1855` | 0 | MCP tools/call 1 | - | |
| 28 | 출력 검사 | `_guarded_result`×2, `_validate_output`×2, `mask_payload`, `secret_scan.labels` | `core.py:1881,2589-2592`, `core.py:1966-2032`, `privacy.py:206-271` | 0 | Presidio ≥2+k (+anonymizer) | Semaphore 2·4 | 직렬화·`check_schema`·독성 검사를 두 번씩 |
| 29 | 원장 기록 | `_decision_payload` → `_record_decision` | `core.py:2636`, `core.py:2055-2160` | 1/3 (+트리거 INSERT 1) | - | **`audit_chain` 행 FOR UPDATE**(전역), advisory(principal; 중요 읽기·자동중지 후보) | 해시를 락 안에서 계산 |
| 30 | 예약 해제 | `_release_call` | `core.py:1580-1602` | 1/1 | - | - | |
| 31 | 중요 읽기 지문 | `_remember_flow` | `core.py:2639`, `core.py:1442-1462` | 3/3 | - | - | 중요 읽기만. 만료 지문 삭제를 호출마다 한다 |
| **합** | 위 시나리오 | | | **약 35/49** (관리형 약 51/65) | OPA 2~4, 업스트림 3~4, Presidio ≥2+k | | 정적 집계, 실측 아님 |

**교차 확인.** 10-25 PJ1 실측(초안 1.3)의 자격 미연결 차단 21~26ms는 이 표의 1~9단계+자격 확인+원장 기록 약 31문장 경로이고, 동의 거절 108~164ms는 1~21단계+원장 약 52문장에 OPA 1회가 붙은 경로다. 문장당 약 0.8ms로 앞의 경로는 설명되지만 뒤의 경로는 60~120ms가 남는다(추정: OPA 입력 직렬화·결정 로그·분류 CPU). 모든 판정 행에 단계별 시간이 남으므로(`decisions.timings`, `core.py:166-181`) `GET /api/latency`(`main.py:599`)나 같은 JSONB의 `percentile_cont` 집계로 남은 몫을 곧바로 가를 수 있다(미실행).

**A-2. tools/list (`mcp_facade.py`)**

| 단계 | 함수 | 파일:행 | DB | 락/HTTP | 비고 |
| --- | --- | --- | --- | --- | --- |
| 인증 2회 | `RequireBearer` + `_caller` | `main.py:79`, `mcp_facade.py:238-244` | 4/4 (관리형 +8) | 폐기목록 flock×2 | tools/call과 같다 |
| 승인 도구 전체 조회 | `_approved_tools` | `mcp_facade.py:121-137` | 1/1 | - | 활성 도구의 `input_schema`·`output_schema` 전부+도구마다 상관 EXISTS(최신 카탈로그 스냅숏) |
| 주체 | `db.fetch_one` | `mcp_facade.py:138` | 1/1 | - | |
| **도구마다 이용 기한** | `tool_sunset.check` | `mcp_facade.py:145`(순차 `await`) | 도구당 2/5 | advisory(서버/도구), 폐기목록 flock, `count(*) FROM decisions` | 도구 수 N이면 `5N+6`문장. 하네스가 서버 10개에 동시에 열면 서버당 N개씩 동시 |
| 가시성 | `pac.visible` | `mcp_facade.py:154` | 0 | - | `capabilities()` stat |

도구가 서버당 10개, 서버 10개를 하네스가 동시에 열면 약 560문장(5N+6=56 × 10)·약 260 체크아웃(2N+6=26 × 10)이 풀 10개를 놓고 경쟁한다(정적 집계). `tool_sunset.check`를 빼면 목록 하나는 6문장이다.

**A-3. 락 종류와 범위**

| 락 | 종류 | 파일:행 | 점유 범위 | 영향 |
| --- | --- | --- | --- | --- |
| principal advisory(`hashtext(user_token)`) | PostgreSQL xact | `automatic_suspend.py:36`, `core.py:1513`, `dispatch.py:82`, `core.py:2096-2102`(조건부) | 호출 하나가 **서로 다른 짧은 트랜잭션 4곳**에서 건다 | 같은 사용자의 동시 호출은 네 곳에서 직렬화. 다른 사용자끼리는 대기 없음 |
| 도구 advisory(`서버/도구`) | PostgreSQL xact | `tool_sunset.py:101` | 이용 기한 확인 tx 동안 | 같은 도구의 동시 호출·목록 직렬화 |
| 감사 체인 | 행 락 `FOR UPDATE` | `core.py:2104` | 해시 계산+INSERT+트리거+UPDATE+COMMIT까지 | **모든 사용자의 모든 판정**(차단·연결 거부 포함)이 직렬화. 상한 ≈ 1/(락 점유 시간)(추정) |
| 행 공유 락 | `FOR SHARE` | `dispatch.py:91-97`(mcp_servers·mcp_tools·principals) | 의도 기록 tx 동안 | 관리자 UPDATE와 의도적으로 충돌 |
| 폐기 목록 | 파일 `flock` | `disposal.py:47-67` | `read()`마다 | 프로세스 간 공유. 이벤트 루프에서 동기 대기 |
| asyncio 락 | `_sweep_lock` | `upstream.py:249-278` | 2초에 한 번 DB 질의를 쥔 채 | 모든 디스패치가 이 락을 지난다 |
| asyncio 조건 | `Pool.changed` | `upstream_sessions.py:90-189` | 세션 키당 1개 | 같은 (사용자·대화·서버) 호출 직렬 |
| asyncio 락 | `REGISTER_LOCK`, `INTAKE_APPROVAL_LOCK`, `_pool_lock` | `core.py:551`, `agent_service.py:55`, `db.py:23` | 등록·원클릭 승인·풀 초기화 | 관리 경로 |
| 세마포어 | Presidio 2, Gitleaks 4, 수동 작업 `POOL_MAX//2`, 소스 내려받기 | `privacy.py:34`, `secret_scan.py:27`, `user_suspend.py:19`, `agent_service.py:2067` | 프로세스 전체 | 사용자 수와 무관한 전역 상한 |
| DB 풀 | 최대 10, 대기 10초, 대기열 상한 없음 | `db.py:16-17,31-34` | 프로세스 전체 | 초과 시 10초 뒤 `PoolTimeout` |

**A-4. 서로 독립인데 순차 `await`인 구간**

| # | 구간 | 파일:행 | 합치는 방법 |
| --- | --- | --- | --- |
| 1 | `_contract`의 쿼리 4개(server·tool·latest 스냅숏·critical) | `core.py:1175-1202` | 단일 CTE 또는 `gather` |
| 2 | `shadow_count_for`·`shadow_listener_count_for`·`_relationship_scope`·`_sequence_flags`·`_flow_sources` | `core.py:2430-2457` | `gather` 또는 단일 쿼리 |
| 3 | `pac.build`의 폐기 토큰·예약 행·미해결 변경 조회 3개 | `pac.py:256,316,336` | `gather` (폐기 토큰은 1단계 결과 재사용) |
| 4 | `secret_scan.labels`와 `privacy.analyze` | `core.py:2410,2413` | `gather` |
| 5 | `privacy.mask_payload`의 잎 문자열 k개 분석 | `privacy.py:252-269` | 잎을 구분자로 합쳐 1회 분석(이미 `joined` 방식 사용, `privacy.py:239`)하거나 `gather`+세마포어 |
| 6 | 업스트림 `list_all_tools`와 `mcp_tools` 조회 | `core.py:1725-1726` | `gather` |
| 7 | 전송 직전 재검증의 principals·`_contract`·`pac.build` | `core.py:1772-1791` | 요청 컨텍스트로 재사용, 변경 감지는 `dispatch.record`(FOR SHARE)에 맡김 |
| 8 | `RequireBearer`와 `_caller`의 인증 | `main.py:79`, `mcp_facade.py:55` | 요청 범위에 한 번만 저장 |
| 9 | tools/list의 도구별 이용 기한 | `mcp_facade.py:145` | 서버 단위 한 쿼리(`GROUP BY tool_name`)+캐시 |
| 10 | 카탈로그 갱신의 서버별 점검 | `core.py:503-516` | 서버별 `gather`(타임아웃 격리). 느린 서버 하나가 나머지를 늦춘다 |

**A-5. 디스크 읽기(레지스트리 TOML/JSON 포함)**

| 대상 | 호출당 횟수 | 파일:행 | 크기·비고 |
| --- | --- | --- | --- |
| 폐기 목록 `journal.jsonl`+`head.json` | 5회 이상(인증 2·`_contract` 2·이용 기한 1, 도구 목록은 도구 수만큼 더) | `disposal.py:70-95`, `disposal.py:143-152` | 크기=폐기 기록 수(토큰 폐기마다 1줄, 추가 때마다 전체를 두 번 읽음 `disposal.py:97-114`). 매번 서명 검증 |
| `catalog.toml`·`servers.json` stat | 15회 이상 × 2~4 syscall | `registry.py:36-62` | 파싱은 mtime 캐시라 호출마다 아님 |
| `catalog_version()` | 1회(전체 읽기+SHA-256) | `registry.py:70-72`, `core.py:2453` | `catalog.toml` 12.8KB+런타임 서버 파일 |
| `residency.load_pack` | 2회×파일 2개 | `pac.py:306`, `residency.py:48-57` | 약 0.9KB, 호출마다 JSON 파싱+검증 |
| `capabilities.json` stat | 약 6회 | `pac.py:55-63` | 내용은 캐시 |
| 업스트림 자격 파일(`MCP_UPSTREAM_CREDENTIALS_FILE` 설정 시) | 3회 이상(읽기+JSON 파싱+권한 stat) | `upstream.py:92-95` | |
| 정책 번들 파일(헬스) | `/api/health` 호출마다 약 150KB 읽기+해시 | `release.py:60-71` | 무인증 엔드포인트(`field/Caddyfile:63,102`) |

**A-6. 감사 원장.** 호출 1건당 `decisions` INSERT 1건+`audit_chain` UPDATE 1건(`core.py:2110,2144`), `siem_outbox` 트리거 INSERT 1건(`siem_tables.sql`: SIEM을 켜지 않아도 쌓이고 삭제 코드가 없다), 예약 INSERT·갱신·해제 3건, 의도 INSERT·종결 2건, 중요 읽기면 `flow_fingerprints` 1건. 즉 호출 하나가 행 쓰기 8건 이상이다. 해시 체인은 `sha256(prev + canonical_hash(41개 열 레코드))`(`core.py:2108`, `contract.py:87-108`)를 `audit_chain` 행 락 안에서 계산하고, 레코드에는 `policy_input`(OPA에 보낸 입력 전체)이 들어 있다(`contract.py` `AUDIT_COLUMN_SETS[6]`). 연결 거부 기록도 같은 락을 쓰므로 분당 20건으로 막아 둔다(`core.py:2179-2213`). 검증은 `verify_audit_chain`이 전 행을 `fetchall()`로 올려 CPU로 해시한다(`core.py:2230-2235`; 호출처 `main.py:1024`, `audit.py:85-89`, `incidents.py:178`).

**A-7. 이벤트 루프를 막을 수 있는 동기 호출**

| 호출 | 파일:행 | 비고 |
| --- | --- | --- |
| `disposal.blocked/read/locked`(flock+파일 읽기+Ed25519) | `agent_contract.py:166`, `core.py:1216,1762`, `tool_sunset.py:72` | 호출당 5회 이상, 기록 수에 비례. 코드에 `shortcut` 주석이 있다(`disposal.py:71`) |
| `disposal.remember/_append`(전체 읽기 2회+fsync 3회) | `disposal.py:97-114`, `idp.py:257,259,281,283,308` | DB 트랜잭션 안에서 토큰마다 |
| `classify.classify`(`dlp_scan`·`sql_facts`) | `core.py:2270`, `classify.py:157-168,485-512` | 문자열 ≤20,000자×≤200개×정규식 약 15종 |
| `json.dumps/loads`·`canonical_hash` | `core.py:2367,1966,2108`, `privacy.py:223,260` | 결과 최대 256KB를 3~4회 직렬화 |
| `Draft202012Validator(...)` 생성+`check_schema` | `core.py:2382,1748,1975-1980`, `pac.py:264` | 호출당 3~5회, 캐시 없음 |
| 파일 stat/읽기 | A-5 표 | |
| `secret_scan.scan_text`의 URL 정규식 | `secret_scan.py:61-68,81` | 스레드로 넘기기 전에 이벤트 루프에서 실행 |
| `upstream.credential_choice` | `upstream.py:75-116` | 자격 파일 읽기 |
| subprocess | 핫패스에는 없음 | Gitleaks는 C-ABI `ctypes`+`to_thread`(`secret_scan.py:85`) |

### B. S4-01·S4-10이 main에서 어떻게 됐는지, 같은 패턴이 어디에 남았는지

**B-1. 보고된 결함의 main 상태**

| 항목 | main 상태 | 근거 | 남은 것 |
| --- | --- | --- | --- |
| S4-01 풀 교착 | 고쳐짐: 보존 설정을 트랜잭션 **전에** 읽고 `_coverage`에 넘긴다. 확인 하나=연결 하나 | `tool_sunset.py:96-98,108`, D-243(`docs/ai/decisions/D-201-250.md:518`) | (a) `retention.current_seal()`의 파일 I/O(전체 서명 검증)가 트랜잭션·advisory 락을 쥔 채 이벤트 루프에서 실행(`tool_sunset.py:72,99-108`). (b) 도구 수만큼 순차 확인(`mcp_facade.py:145`). (c) 풀 10·대기 10초 그대로 |
| S4-10 호출마다 연장 이벤트 | 고쳐짐: 도구마다 하루 1건 | `tool_sunset.py:137-148`, D-247 | `tool-sunset-check`(자료 없음) 기록은 `window_start`를 `now − N일`(마이크로초 단위)과 비교하므로 거의 항상 달라 **커버리지가 성립하지 않는 동안 호출마다 INSERT**된다(`tool_sunset.py:109-116`). 조건: 봉인과 관측 창 겹침, `entries ≠ retained`. 기본 설정(보존 366일)에서는 도달하지 않는다(추정). 그리고 `approval_events`·`decisions` INSERT는 모두 `siem_outbox` 트리거로 1행을 더 쓴다(`siem_tables.sql`) |
| S4-05 1000건 상한 | 고쳐짐: JSON 레코드(배열)만 센다 | `classify.py:572-596`, D-246 | 상한 값 자체는 환경변수 기본 1000(`core.py:59`) |
| S4-06 카드번호 마스킹이 JSON을 깨뜨림 | 고쳐짐: 텍스트 속 JSON은 구조로 검사하고, 숫자는 값 자체로 검증(주민번호·Luhn) | `privacy.py:178-269`, D-246 | 위험 판단은 구조화 값에서 보류(InspectionUnavailable)로 fail-closed. 잎마다 순차 HTTP라는 비용은 그대로(A-4 5번) |

**B-2. 풀·타임아웃 기본값.** `DB_POOL_MAX=10`, `DB_POOL_TIMEOUT=10`초(`db.py:16-17`), `min_size=1`, `max_waiting` 미설정(대기열 무제한), `statement_timeout`·`lock_timeout` 미설정. 프로세스마다 풀이 따로이므로(`db.py:22`) 게이트웨이와 콘솔(`agent-service`)이 각각 최대 10개, 워커 컨테이너 2개가 별도로 DB에 붙는다. `deploy/compose.yaml`·`.env.example`은 `DB_POOL_MAX`를 설정하지 않는다(grep 결과 0건).

**B-3. 「`db.transaction()` 블록 안에서 두 번째 연결을 얻는 곳」 전수 조사.** 방법: `nested_tx.py`가 모든 `async with db.transaction()` 본문의 호출을 AST로 따라가 (1) `db.fetch_*/execute/transaction` 직접 호출, (2) 연결을 넘기지 않은 채 풀 연결을 얻는 함수(전이적으로 추적)를 찾고, 거기에 (3) 연결을 인자로 받는데 안에서 `db.`를 다시 부르는 함수를 따로 훑었다. 오탐(`core.py:2229`: 스냅숏 연결을 위치 인자로 넘김)은 제외했다.

| # | 파일:행 | 함수(트랜잭션 시작 행) | 두 번째 연결을 얻는 호출 | 점유 시간 | 심각도 |
| --- | --- | --- | --- | --- | --- |
| 1 | `local_jobs.py:648` | `validate_job`(600) | `db.fetch_all('SELECT * FROM mcp_tools ...')` — `connection.execute`로 바꾸면 되는 단순 중첩 | 한 쿼리 | 중. 로컬 MCP 호출·갱신마다 지나는 경로 |
| 2 | `local_jobs.py:751`, `local_jobs.py:756` | `prepare_token_revocation`(연결을 받지만 `db.execute`·`db.fetch_one` 사용). 호출처 `idp.py:235`(`_revoke_family`), `idp.py:255`(`revoke_principal_tokens`), `idp.py:279`(`revoke_device_tokens`), `idp.py:307`(`revoke`, RFC 7009) | `db.execute` 1회+**`while await db.fetch_one(...)` 폴링을 `asyncio.sleep(.1)`로 최대 25초**(`RUN_SECONDS+5`) | 첫 연결과 `local:token:<jti>` advisory 락을 쥔 채 최대 25초 | 상. 로그아웃·계정 종료·기기 폐기가 이 경로. 같은 토큰의 `lock_execution`(`local_jobs.py:559`)을 부르는 경로는 이 락에 막힌다(추정) |
| 3 | `agent_service.py:2466-2625` | `approve_and_register`: `async with INTAKE_APPROVAL_LOCK, db.transaction() as lock` 안에서 `approval_row`(2468), `resolve_audience`(2493), `review.intake_gate`(2533), `review.same_person`(2546-2549), `review.transition`(2562,2608), `review.accept_risk`(2572), `review.record_event`(2622), `register_mcp_request`(2625) | 모두 연결을 넘기지 않아 각자 새 연결을 얻는다. `register_mcp_request`는 게이트웨이로 HTTP(`agent_service.py:2183`)를 보낸다 | 첫 연결과 advisory 락을 쥔 채 수 초~수십 초 | 중. 프로세스 락으로 동시 1건이라 풀 교착은 어렵지만 장시간 트랜잭션 |
| 4 | `ops_response.py:234` | `tick` | `incidents.check_deadlines`, `observed_alerts`, `contain_repeated`, `self_test`(OPA HTTP·재생)가 각자 연결 획득 | 주기 실행 동안 연결 1개 상주 | 하. 락 임대용 트랜잭션이 작업 전체를 감싼다 |
| 5 | `user_suspend.py:37` | `suspend`: `local_jobs.quiesce`(50) | 별도 트랜잭션을 의도적으로 연다(주석 `user_suspend.py:47-49`) | 장치 응답 대기 동안 연결 1개 | 하. 슬롯으로 `POOL_MAX//2`개로 제한(`user_suspend.py:19`) |
| 6 | `oidc.py:260` | `_refresh_upstream`(238) | 트랜잭션(행 락 `FOR UPDATE`) 안에서 **외부 IdP로 HTTP**(타임아웃 10초) | 최대 10초 | 하. 관리자 세션 갱신만 |
| 7 | `siem.py:132` | `deliver_one`(116) | 트랜잭션(`FOR UPDATE SKIP LOCKED`) 안에서 SIEM으로 HTTP | 전송 시간 | 하. 의도된 설계(문서화됨) |
| 8 | `idp.py:257,259,281,283,308` | 위 2번 호출처들 | 트랜잭션 안에서 **동기** `disposal.remember*`(전체 읽기 2회+fsync 3회)를 토큰마다 | 토큰 수 × 수 ms 이상 | 중. 계정 종료 시 토큰이 많으면 길어진다 |

**B-4. 한계.** 위 표는 정적 분석이다. 연결을 클래스 속성이나 클로저로 넘기는 호출, `getattr`로 부르는 호출(`core.py:2272` `globals().get("user_suspend")`)은 따라가지 못했다. `litellm_sync.py:500`은 세션 락 연결(`pool().connection()`)을 쥔 채 `_reconcile`이 자기 연결을 쓰므로 풀이 2 미만이면 교착이라는 점을 코드가 이미 검사한다(`litellm_sync.py:90`). 이 둘은 위 표에 넣지 않았다.

### C. 구조·결합도

**C-1. 모듈별 LOC와 책임**(`full_stack_lab/gateway/app/*.py` 68파일 = `__init__` 1 + 모듈 67, 24,451줄. 전체 표는 `ast_stats.py` 출력)

| 묶음 | 모듈(줄) | 소계 | 한 문장 책임 |
| --- | --- | --- | --- |
| 판정 코어 | `core` 2907, `classify` 1003, `poisoning` 485, `textscan` 311, `pac` 389, `privacy` 271, `tool_sunset` 225, `dispatch` 206, `consent` 165, `user_suspend` 164, `contract` 143, `residency` 114, `secret_scan` 112, `retention` 110, `flow_fingerprint` 109, `db` 99, `output_contract` 97, `automatic_suspend` 78, `outcomes` 74, `destination` 57, `high_impact` 52, `selective` 34 | 22개 7,205 | 신원→분류→예약→검사→OPA→전송→출력 검사→원장(`core.execute_call`)과 그 부품 |
| 업스트림·세션·로컬 실행 | `local_jobs` 783, `upstream` 506, `user_credentials` 279, `upstream_sessions` 189, `mcp_sessions` 67, `connections` 31 | 6개 1,855 | 등록 서버와의 MCP 연결·세션 풀·직원 자격·직원 PC 실행기 |
| 인그레스 | `main` 1942, `mcp_facade` 294, `agent_contract` 199, `addon` 62, `sse_entry` 30, `stdio_entry` 15 | 6개 2,542 | 게이트웨이 API 106 라우트+MCP 파사드(HTTP·SSE·stdio)+공유 인증 경계 |
| 콘솔·IdP | `agent_service` 2876, `oidc` 428, `idp` 387, `integrations` 380, `activity` 276, `connectors` 268, `system_metrics` 118, `audit` 96, `release` 94, `windows_oneclick` 43, `kit_commands` 41, `keygen` 29 | 12개 5,036 | 콘솔 화면 API·로그인/IdP·키트 배포·감사 읽기 투영 |
| 도입·등록·수명주기 | `decommission` 985, `litellm_sync` 649, `review` 424, `registry` 315, `artifact_provenance` 232, `experiments` 233, `risk_tier` 171, `sbom_impact` 148, `supplier_assurance` 144, `intake_proposal` 141, `provenance` 114 | 11개 3,556 | 도입 심사·카탈로그·종료·외부 AI 게이트웨이 동기화 |
| 운영·증거·엔드포인트 | `endpoint_plane` 1552, `acceptance` 1347, `incidents` 285, `disposal` 263, `ops_response` 254, `siem` 177, `incident_pack` 125, `replay` 112, `server_egress` 99, `event_correlation` 42 | 10개 4,256 | 직원 PC 보고 수신·인수 시험 스위트·사건·폐기 장부·SIEM·재생 |

상위 5개(`core` 2907, `agent_service` 2876, `main` 1942, `endpoint_plane` 1552, `acceptance` 1347)가 10,624줄로 43%다. `acceptance.py`는 제품 이미지 안의 시험 스위트다(`console.sh test`가 `python -m app.acceptance`로 실행, `console.sh:606`). 정적 파일은 `agent_static/` 5,951줄(console.js 3,347·i18n-en 1,389), SQL 7개 1,517줄, OPA Rego 1,257줄(+시험 1,486줄).

**C-2. import 그래프와 순환**(`ast_stats.py`, 모듈 간 간선 256개: 모듈 최상위 199, 함수 안 57)
- 모듈 최상위 import만 보면 **순환 없음**(강연결 성분 0).
- 함수 안 import(지연 import)를 포함하면 **31개 모듈이 하나의 강연결 성분**이다: agent_contract, agent_service, audit, automatic_suspend, classify, connectors, consent, core, decommission, dispatch, endpoint_plane, experiments, idp, incidents, integrations, litellm_sync, local_jobs, oidc, ops_response, pac, privacy, registry, release, retention, review, sbom_impact, secret_scan, tool_sunset, upstream, user_credentials, user_suspend.
- 지연 import로만 닫히는 2-사이클 6쌍: `agent_contract↔oidc`, `agent_service↔idp`, `endpoint_plane↔local_jobs`, `endpoint_plane↔idp`, `incidents↔ops_response`, `registry↔upstream`. `retention→db/review`, `disposal→db`, `siem→db`, `server_egress→db`도 순환을 피하려는 지연 import다(`retention.py:90,99`).
- 팬인 상위: `db` 37, `registry` 16, `review` 15, `agent_contract` 10, `local_jobs` 10, `disposal` 9, `core` 8, `endpoint_plane` 8. 팬아웃 상위: `core` 33, `agent_service` 29, `main` 29, `decommission` 12.
- `core`는 모듈 최상위에서 33개 모듈을 직접 가져오고(`core.py:29-38`), 선택 호출을 `globals().get("user_suspend")`·`getattr`로 한다(`core.py:2272-2273`).

**C-3. `main.py`(게이트웨이)와 `agent_service.py`(콘솔·IdP)의 분리**
- 같은 이미지 `mcpgw/gateway`, 진입만 다르다: `uvicorn app.main:app :8080`(Dockerfile CMD)과 `uvicorn app.agent_service:app :8000`(`deploy/compose.yaml:152`). 라우트는 게이트웨이 `main.py` 106개, 콘솔 `agent_service.py` 62개+라우터로 포함하는 `idp.py` 6·`connectors.py` 4·`integrations.py` 2(`agent_service.py:137-139`)이고 `oidc.py` 7은 콘솔 로그인에 쓰인다. 합계 187.
- 공유 모듈: `db, registry, review, disposal, agent_contract, contract, pac, endpoint_plane, local_jobs, upstream(풀 닫기만)`. 콘솔은 `core` 전체를 불러오면서(`agent_service.py:34`) 쓰는 것이 `core.canonical_hash`와 `core.registration_endpoint` 둘뿐이다(`contract.canonical_hash`로 직접 가져올 수 있다).
- 중복 ① 스키마 부트스트랩의 SQL 실행 순서가 두 곳에 복제돼 있다(`agent_service.py:112-118`은 6개 파일, `core.py:470-478`은 7개+`litellm_sync.initialize`). ② 같은 이름의 최상위 정의 7개(`admin_caller, approve, caller, health, lifespan, reject, risk_catalog`)와 같은 경로 `GET /api/risk-catalog`(`main.py:1925`, `agent_service.py:2647`)·`GET /`. ③ 콘솔→게이트웨이 `/gw/{path}` 중계(`agent_service.py:2857-2876`)가 먼저 `current_identity`로 인증하고 게이트웨이가 `authenticated_user`로 한 번 더 인증한다. ④ 제품 코드 안의 실습 시드: 실습 장치 4대 폐기(`agent_service.py:100`), 기동마다 `root`/`user` 기본 계정 생성(`agent_service.py:91-98`), 비밀번호 환경변수 기본값 `test-password`(`agent_service.py:83`).

**C-4. 설정 흩어짐.** `os.getenv`/`os.environ` 호출 207곳, 33개 파일, 서로 다른 변수 130개(`ast_quality.py`). 상위: `agent_service` 44, `core` 29, `oidc` 17, `acceptance` 16, `litellm_sync` 14. 대부분 모듈 최상위에서 `int(os.getenv(...))`로 임포트 시점에 평가된다(`core.py:40-110`). 중앙 설정 객체·검증은 없다. `deploy/.env.example`에는 40개가 있고 그중 코드가 읽는 이름은 28개다. 값 오류는 임포트 때 예외로 프로세스를 멈추는 방식이다(`core.py:61,64,122`).

**C-5. 스키마 생성 방식과 마이그레이션 부재**
- `core.bootstrap`(`core.py:470-478`)이 기동 때마다 SQL 7개(1,517줄)를 `db.execute(파일 전체)`로 실행한다. 게이트웨이와 콘솔이 동시에 올라올 때는 파일 첫머리의 `pg_advisory_xact_lock(hashtext('mcp_governance_schema_migration'))`로 직렬화한다(`agent_tables.sql:4`, `lifecycle_tables.sql:12`). `ops_tables.sql`·`siem_tables.sql`은 다른 락 번호를 쓴다(각 1행).
- 마이그레이션 도구·버전 테이블은 없다(alembic·yoyo·flyway·schema_migrations 검색 0건). 변경은 `CREATE TABLE IF NOT EXISTS`+`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`로 쌓인다(`ALTER TABLE` 문 182개). 해시 체인만 열 집합 버전(`CHAIN_VERSION=8`, `contract.py:82`)으로 호환을 관리하고, 옛 판본 DB는 `./console.sh reset`을 요구한다(`contract.py:73-79`).
- **CHECK 제약 함정.** (1) `CREATE TABLE IF NOT EXISTS` 안의 인라인 CHECK는 기존 테이블에 반영되지 않는다. `approval_events.outcome`의 허용값은 5개뿐인데(`v2_tables.sql:221`) 허용 목록에 없는 `failed`를 쓰던 코드가 매번 INSERT 실패였다(D-243). (2) 매 기동 `DROP CONSTRAINT`→`ADD CONSTRAINT`가 15쌍 실행된다(`agent_tables.sql` 6, `lifecycle_tables.sql` 6, `v2_tables.sql` 3 — 하나만 DO 블록으로 보호, `v2_tables.sql:178-182`). 대상은 principals, mcp_intake_requests, scan_jobs(5회), mcp_servers, endpoint_agents, revocation_targets, termination_evidence이고, 매번 ACCESS EXCLUSIVE 락과 기존 행 전수 검증이 든다. (3) 같은 제약이 두 파일에서 다르게 정의된다(`scan_jobs_target_kind_check`: `agent_tables.sql:233` → `lifecycle_tables.sql:237`). 앞 파일이 좁히면 기존 행 때문에 재기동이 실패하므로 `tests/schema_check.py`가 파일 사이 일치를 검사한다(`docs/ai/TESTING.md:44-45`).
- 정리 기능이 없는 테이블: `call_reservations`(해제만 함), `dispatch_intents`, `siem_outbox`(전달 완료 행도 삭제 없음), `approval_events`·`decisions`(추가 전용 트리거). `DELETE FROM`은 만료 토큰·세션·지문 등에만 있다(grep).
- 인덱스: `decisions`는 `(request_id)`, `(user_token, created_at DESC)`, `(server_id, created_at DESC)`, `(created_at DESC)` 4개뿐이다(`agent_tables.sql:129-130`, `v2_tables.sql:33-34`). `tool_name`·`client->>'workstation'`·`upstream_attempted` 조건에는 인덱스가 없는데 `tool_sunset.py:119-124`, `main.py:525-537`(엔드포인트마다 상관 서브쿼리 3개), `pac.py:336-341`이 이 열들로 조회한다. 이력이 커지면 O(이력) 스캔이 된다(추정: 행 수는 미확인).

**C-6. 전역 가변 상태**(모두 프로세스 로컬 — 복수 워커·복제에서는 일관성이 깨진다)

| 이름 | 파일:행 | 용도 | 비고 |
| --- | --- | --- | --- |
| `_ledger_cache` | `core.py:1601` | 정책 관리대장 | 기동 후 갱신 없음, `local_verdict`가 읽음 |
| `registry._cache` | `registry.py:40` | 카탈로그+런타임 서버 | mtime 키 |
| `pac._capabilities` | `pac.py:52` | 권한 명세 | mtime 키 |
| `upstream._pool`, `_sessions`, `_connected`, `_swept`, `_sweep_lock` | `upstream.py:154-155,43,248-249` | 업스트림 HTTP 클라이언트·세션 풀·직원 자격 사본 | 풀 크기 32. 다른 프로세스에는 `upstream_pool_events` 표로 알림(`upstream.py:207-218`) |
| `connections._clients` | `connections.py:14` | 이벤트 루프별 httpx 클라이언트 | |
| `classify._browser_page` | `classify.py:776` | 사용자별 마지막 브라우저 페이지 | 만료·상한 없음(사용자 수만큼) |
| `privacy._slots`, `secret_scan._slots` | `privacy.py:34`, `secret_scan.py:27` | Presidio 2·Gitleaks 4 동시 상한 | 전역 |
| `db._pool`, `_pool_lock` | `db.py:22-23` | 풀 | |
| `agent_service._login_attempts` | `agent_service.py:54` | 로그인 시도 제한 | 프로세스 로컬 |
| `user_credentials._flows` | `user_credentials.py:205` | 장치 코드 흐름 | 프로세스 로컬 |
| `REGISTER_LOCK`, `INTAKE_APPROVAL_LOCK`, `_gitea_lock`, 슬롯들 | `core.py:551`, `agent_service.py:55,594,2067`, `user_suspend.py:19` | 관리 작업 직렬화 | |
| `evidence_context`, `transport_context`, `registering`, `downstream`(ContextVar) | `local_jobs.py:45-55`, `upstream_sessions.py:13` | 요청 범위 값 | 이쪽은 안전 |

**C-7. 예외 처리**(`ast_quality.py`: `except` 처리기 310개)
- 넓은 `except Exception/BaseException` 82개, 맨몸 `except:` 0개, 본문이 `pass`뿐인 처리기 16개. 그중 `except Exception: pass`는 3곳이다 — `core.py:204`(추적 설정), `core.py:1160`(`catalog_watch`의 갱신·만료·유예·재승인 전체를 삼킴), `core.py:2618`(드리프트 뒤 카탈로그 재조회).
- 넓은 except 중 본문이 `pass`가 아닌 것(로그·값 변환·반환)은 「pass뿐」 열에 세지 않았다. 판정 경로의 넓은 except는 대부분 의도된 fail-closed 변환이다(`P-CONTROL-FAIL-CLOSED`).

| 파일 | 처리기 | 넓은 except | pass뿐 | 비고 |
| --- | --- | --- | --- | --- |
| `main.py` | 72 | 7 | 2 | `main.py:174`, `742` |
| `agent_service.py` | 43 | 2 | 2 | `agent_service.py:995`, `2127` |
| `core.py` | 32 | 21 | 3 | `core.py:204`, `1160`, `2618` |
| `litellm_sync.py` | 18 | 6 | 1 | `litellm_sync.py:77` |
| `upstream.py` | 11 | 6 | 0 | |
| `user_credentials.py` | 9 | 1 | 0 | |
| `oidc.py` | 8 | 5 | 0 | |
| `classify.py` | 7 | 3 | 1 | `classify.py:243` |
| 나머지 파일 | 110 | 31 | 7 | `acceptance`·`endpoint_plane`·`idp`·`poisoning`·`release` 각 1, `system_metrics` 2 |

**C-8. 함수 길이 상위 10**(`ast_quality.py`; 1,118개 함수 중 100줄 초과 14개, 60줄 초과 41개)

| 순위 | 파일:행 | 함수 | 줄 수 |
| --- | --- | --- | --- |
| 1 | `core.py:2255` | `execute_call` | 386 |
| 2 | `core.py:622` | `register_server` | 273 |
| 3 | `core.py:1682` | `_call_upstream` | 203 |
| 4 | `litellm_sync.py:223` | `_propagate` | 171 |
| 5 | `core.py:219` | `refresh_catalog` | 164 |
| 6 | `agent_service.py:2463` | `approve_and_register` | 163 |
| 7 | `agent_service.py:1746` | `approve_mcp_request` | 150 |
| 8 | `pac.py:247` | `build` | 143 |
| 9 | `endpoint_plane.py:867` | `managed_policy` | 125 |
| 10 | `integrations.py:173` | `snapshot` | 119 |

`core.py` 한 파일에 상위 5개 중 4개가 있다. `execute_call`은 `await` 49개·조기 반환 15곳(`return await _decision_payload`)이다.

**C-9. `console.js`(3,347줄) 구조**(`agent_static/`)

| 항목 | 값 |
| --- | --- |
| 규모 | `console.js` 3,347줄·263KB(비압축 원문), `console-state.mjs` 360, `charts.mjs` 193, `i18n.mjs` 142, `i18n-en.mjs` 1,389(영어일 때만 적재), `vendor/echarts.min.js` |
| 모듈 방식 | ES 모듈 1개(import 3개). export 없음. 번들러·`package.json`·minify·타입 검사 없음 |
| 함수 | 최상위 함수 선언 84개(async 13)+화살표 상수 59개+최상위 `const` 155·`let` 21. 페이지는 `ROUTES.<이름> = async ...` 12개(`console.js` `ROUTES.`) |
| 상태 관리 | 모듈 최상위 `let` 변수(`viewer`, `current`, `registry`, `approvalRows` 등)와 `localStorage`(15회 참조). 스토어·구독 없음 |
| 렌더링 | `html` 태그드 템플릿(자동 이스케이프 `Raw`, `console.js:44-52`)+`innerHTML` 19곳·템플릿 리터럴 509개. 직접 `createElement`는 7곳 |
| 네트워크 | 공통 `api()`(`console.js:64-80`)로 58회 호출, 직접 `fetch(` 6회. 모든 호출이 `/gw/*` 중계 또는 콘솔 API. 토큰을 `localStorage`에 저장해 Bearer로 붙임(`console.js:64-67`) |
| 폴링 | 지표 10초(`console.js:635`), 배지 30초(`console.js:3345`: `/api/consents`+`gw("overview")`+`/api/connectors?summary=1`), 활동 라이브 피드, 도입 상태, 세션 유지. 관리자 탭 하나가 30초마다 `overview`(풀 연결 최대 10개)를 부른다 |
| 국제화 | 한국어 원문이 기준, 영어는 사전(`i18n-en.mjs`)을 렌더 뒤에 DOM 전체를 훑어 정규식 패턴으로 치환(`i18n.mjs:1-60`). 번역 호출 `t(`은 3곳뿐 |
| 시험 | `node --test tests/*.test.mjs` 10개 파일 968줄은 `console-state`·`i18n`·`charts` 등 분리된 모듈만 검사. `console.js` 자체는 `node --check` 구문 검사뿐(`verify.yml:56-59`) |

### D. 시험 체계

**D-1. `full_stack_lab/tests/` 분류**(파일 197개+하위 폴더 `data`·`fixtures` 2개, 38,821줄)

| 종류 | 파일 | 줄 | CI·`console.sh`에 이름이 있는 파일 | 설명 |
| --- | --- | --- | --- | --- |
| `*_check.py`(스크립트, PG 제외) | 130 | 26,611 | 24 | 종료 코드로 판정하는 단독 스크립트. 대부분 제품 모듈을 직접 임포트하고 DB·네트워크는 대역으로 대체 |
| `*_test.py`(unittest) | 9 | 2,100 | 4 | `python -m unittest` |
| `*_pg_check.py`(실제 PostgreSQL) | 16 | 4,135 | **1** (`oauth_rotation_pg_check.py`, `console.sh:609`) | `DATABASE_URL`이 가리키는 빈 DB 필요(`termination_lab_support.py`). 나머지 15개는 수동 실행뿐(예: `tests/termination_dispatch_lab.sh run <파일>`) |
| `*.test.mjs`(node:test) | 10 | 968 | 10 (`node --test tests/*.test.mjs`, `verify.yml:61`) | 콘솔의 분리된 모듈만 |
| `.mjs` 스크립트 | 3 | 277 | 2 | `intake_*_ui_check.mjs`, `i18n-extract.mjs` |
| `*_eval.py`(코퍼스 측정) | 2 | 841 | 0 | 요청 시 실행(외부 코퍼스) |
| `.sh` | 3 | 370 | 1 (`security_regression.sh`) | 스택 필요 |
| 지원·기타(py 17, Dockerfile 1) | 18 | 2,480 | 3 | 하니스·픽스처·실험 실행기 |
| JSON 데이터 | 6 | 1,039 | - | 코퍼스 매니페스트 등 |
| **합** | **197** | **38,821** | **45** | 실행 파일 189개 중 144개는 이름이 없다(`.mjs`·`.sh` 포함) |

시험 줄 수(38.8k)가 게이트웨이 앱(24.5k)보다 많다. OPA Rego 시험은 `policy_test.rego`가 1,415줄·`test_` 규칙 122개(+`residency_review_test.rego` 8개)다(문서는 96건, `docs/ai/TESTING.md:21`).

**D-2. 스택 없이 도는 비율.** 정규식 추정이 빗나가기 쉬워서(예: `http://localhost` 문자열이 들어 있어도 대역으로 도는 시험) 저장소가 이미 갖고 있는 판정을 썼다. `run_local_suite.py`(`full_stack_lab/tests/run_local_suite.py:1-47`)는 「PG를 쓰지 않는 `*_check.py`·`*_test.py` 전부」를 한 PC에서 돌린다.
- 대상 137개 = 통과 115 + 실패 5(당시 기준선) + 외부 의존 생략 17(`EXTERNAL`, 같은 파일 35-47행: 게이트웨이 HTTP, POSIX 권한, `libmcpgw_gitleaks.so`, Trivy, Gitea 등). 근거: `research/llm-wiki/status/reports/2026-10-25-gw-bugfix.md:39`(통과 115·생략 17·실패 5), `2026-10-21-test-triage.md`.
- 따라서 비-PG 시험 137개 중 스택 없이 도는 것은 120개(88%), 전체 `*_check`/`*_test`/`*_pg_check`(155개) 대비 77%다. 스택이 정말 필요한 것은 생략 17개+`security_regression.sh` 등 `.sh` 2개+PG 16개 안팎이다(미확인: 사람이 직접 센 값 아님, 위 보고서의 분류를 따름).
- **문제는 필요 자원이 아니라 연결이다.** 이 실행기는 CI에 없다(`.github` 검색 0건). CI가 이름으로 부르는 시험은 45개뿐이고(`verify.yml`·`console.sh`), 144개는 어디에서도 자동 실행되지 않는다. 그중 109개가 `*_check.py`/`*_test.py`이고 `tool_sunset_check.py`·`tool_sunset_paths_check.py`·`tool_sunset_pool_pg_check.py`(S4-01·S4-10 회귀), `upstream_session_reuse_test.py`, `flow_fingerprint_check.py`, `ledger_retention_check.py`, `output_credential_span_check.py`가 포함된다.

**D-3. CI(`.github/workflows/verify.yml`, 463줄)**

| job | 타임아웃 | 실측(2026-10-25 실행 2건) | 내용 |
| --- | --- | --- | --- |
| `static` 정적 검사 | 15분 | 67~88초 | pyflakes(`gateway/app`·`tests`·키트 등), `bash -n`, `node --check`, `node --test`, 검사기 자체 점검 스크립트 10여 개, compose 망·포트·키 경계, `deploy/check.py`, gitleaks, Rego 시험(`verify.yml:21-178`) |
| `deploy` 운영 배포 설치 검증 | 60분 | 217~223초 | `./install.sh --bind` 118초, 기동·인증서·첫 관리자, 재기동·백업·복구 77초(`:179-234`) |
| `litellm` LiteLLM 애드온 | 75분 | 328~330초 | LiteLLM 1.105 기동, 동기화·A/B 경로·회전·철회 e2e(`:236-347`) |
| `verify` 완료 조건 전체 | 75분 | 768~956초 | `console.sh up --no-llm` 262초, **`console.sh test` 345초**, 네이티브 엔진 동등성 49초, 실기기 오버레이 `field up` 53초, 직원 PC 키트 26초(`:349-463`) |

- 한 번 실행의 벽시계: **15~18분**(최근 push 5건 실측: 14m56s, 15m48s, 17m09s, 17m28s, 17m31s). `static`이 끝나야 나머지 3개가 병렬로 시작한다(`needs: static`).
- 타임아웃은 실측의 4~5배다. 트리거는 `push: branches ["**"]`와 `pull_request`를 모두 켜서 PR을 쓰면 같은 커밋이 두 번 돈다(최근 8건은 모두 push — 이 저장소는 로컬 병합 뒤 push). `concurrency`로 같은 ref의 이전 실행은 취소한다(최근 8건 중 3건이 취소).
- **Docker 레이어 캐시 없음**(`buildx`·`cache-from` 검색 0건): `deploy`·`litellm`·`verify` 세 job이 게이트웨이 이미지(Go CGO+gcc+pip+Windows Python 내려받기)와 나머지 이미지를 각자 처음부터 빌드한다.
- Windows·macOS 러너 job은 없다(`ubuntu-latest`만). Windows 키트 시험 2개(`endpoint-agent/tests-windows/`, 987줄)는 사람이 pj3에서 돌린다.
- 그 밖의 워크플로: `codeql.yml`(99줄), `research-wiki.yml`(24줄).

**D-4. `console.sh test` 소요.** 실측 345초(CI 2026-10-25). 문서 값을 더하면 인수 시험 ~40초+직원의 하루 ~1분+종료 흐름 ~1분+보안 회귀 ~1.5분+적대 회귀 ~1분+논문 실험 ~30초에 수 초짜리 항목이므로 약 6~7분이라 실측과 맞는다(`docs/ai/TESTING.md:25-45`). 스택 기동까지 합하면 약 10분.

**D-5. 커버리지·정적 도구.** 커버리지 측정 도구 없음(`coverage`·`pytest-cov`·`c8` 검색 0건). 시험 러너는 pytest가 아니라 `python 파일.py`/`unittest`(`unittest`를 가져오는 파일이 128개이고, 실행은 파일별 `python 파일.py` 또는 `unittest discover`다). `pyproject.toml`·`pytest.ini`·`tox.ini`·개발용 requirements 없음. 정적 검사는 pyflakes뿐이고 타입 검사·ruff 없음. 이미 `field_account_git_test.py`가 `__main__` 블록이 없어 시험 0개를 실행하고도 종료 코드 0인 사례가 있었다(`2026-10-21-test-triage.md`).

### E. 배포 묶음 (`deploy/`)

**E-1. `deploy/compose.yaml`(380줄)**

| 항목 | 값 |
| --- | --- |
| 서비스 | 12개: `db`, `opa`, `presidio-analyzer`, `presidio-anonymizer`, `gateway`, `agent-service`, `intake-worker`, `runtime-worker`, `corp-git`, `caddy`, `model-proxy` (11개 기본)+`siem-worker`(프로필 `siem`) |
| 이미지 | 직접 빌드 5개: `mcpgw/gateway`(gateway·agent-service·siem-worker 공유), `mcpgw/presidio-analyzer`, `mcpgw/intake-worker`, `mcpgw/runtime-worker`, `mcpgw/model-proxy`. 내려받기 5개(모두 `@sha256` 고정): postgres 18.6-alpine, opa 1.20.2-static, presidio-anonymizer 2.2.364, gitea 1.27.3-rootless, caddy 2.11.4-alpine |
| 게시 포트 | 2개: `${MINT_BIND}:443→caddy:8080`, `${MINT_BIND}:${MODEL_PROXY_PORT:-3128}→model-proxy:3128`(`:300-330`) |
| 망·볼륨 | 망 7개(`edge, policy, privacy, tools, data, scanner, ops`; `scanner`·`edge` 외 5개는 `internal`), 고정 /24 대역과 Caddy 고정 IP `.1.250`(`MINT_NET_PREFIX` 기본 10.246), 볼륨 10개 |
| 헬스체크 | 5개: db, opa, presidio-analyzer, presidio-anonymizer, corp-git. **gateway·agent-service·caddy·model-proxy·워커 3개는 없음**(`depends_on: service_started`) |
| 자원 제한 | **없음**(`mem_limit`·`cpus`·`pids_limit`·`deploy.resources` 검색 0건). 로그 회전 옵션도 없음(기본 json-file) |
| 하드닝 | `no-new-privileges`+`cap_drop: ALL`는 6개(presidio 2·gateway·agent-service·intake-worker·siem-worker). `runtime-worker`는 `/var/run/docker.sock`을 마운트한다 |
| 프로세스 | 게이트웨이 uvicorn 워커 1개(`gateway/Dockerfile` CMD) |
| 로그 노이즈 | OPA `--set=decision_logs.console=true`(`compose.yaml:93`): 모든 판정이 입력 포함 stdout로 나가고 회전이 없다(실습 스택도 동일 `full_stack_lab/compose.yaml:68`) |

**E-2. `deploy/mint.sh install`(451줄)**

| 단계 | 내용 | 행 |
| --- | --- | --- |
| 준비 | `preflight`(docker·compose·openssl·`docker info`) → `.env` 복사 → `--bind`·`--name` 기록 → `prepare_dirs` → `generate_secrets`(openssl로 값 7개: 비밀번호·펩퍼·암호 키 5+매니페스트 키쌍 2) | `mint.sh:65-87,206-223` |
| 준비 | 게이트웨이 이미지 빌드(자리표시 키로) → `generate_keys`(`dc run`×2로 Ed25519 두 쌍) → 폐기 목록 `init` | `:89-99,224-233` |
| 1/4 | `dc build -q`(이미지 5개) | `:190-191` |
| 2/4 | `up -d --force-recreate opa gateway` → 나머지 7개 기동 → `wait_ready`(3초 간격 최대 120회=6분) → `first_admin`(root 비밀번호 무작위 교체, 기본 직원 계정 중지) | `:192-197`, `:106-117`, `:144-160` |
| 3/4 | `up -d --force-recreate caddy` → `model-proxy` (+`--with-siem`) | `:198-201` |
| 4/4 | Caddy 루트 인증서 내보내기 | `:202-203`, `:162-174` |

- 출력 단계는 5개(준비+1/4~4/4), 내부 동작은 약 14개다.
- 외부 의존(설치 시점): Docker Hub·ghcr.io(이미지), github.com(Trivy·Syft 릴리스, spaCy 모델 `analyzer.Dockerfile:10`, `intake-worker.Dockerfile:14-16`), python.org(Windows embeddable Python `windows-python.json`), PyPI, Go 모듈(gitleaks C-ABI 빌드), apt(gcc 등). 오프라인 설치는 불가능하다. 서버에 필요한 명령은 `docker`·`docker compose`·`openssl`·`python3`(`mint.sh:109,244`)·`git`(판본 표기용, 없어도 `|| true`)이다.
- **`preflight`가 `python3`을 검사하지 않는다**(`mint.sh:65-71` vs `:109`). 없으면 `wait_ready`가 6분을 기다린 뒤 「게이트웨이·콘솔이 준비되지 않았습니다」로 끝나 원인이 가려진다.
- 실측: CI 호스티드 러너에서 `./install.sh --bind` 118초(이미지 빌드 포함), 이어 재기동·백업·복구 77초(2026-10-25). 고객 서버의 설치 시간은 미확인(`deploy/README.md`는 16GB·40GB 디스크를 요구).

**E-3. `.env.example`(40개 변수)**: 자동 생성 비밀 11개(`POSTGRES_PASSWORD`, `GITEA_ADMIN_PASSWORD`, `MOCK_SSO_PASSWORD`, `FLOW_FINGERPRINT_PEPPER`, `USER_CREDENTIAL_KEY`, `AGENT_JWT_*` 2, `DISPOSAL_*` 2, `LOCAL_MANIFEST_*` 2), 사용자 입력 2개(`MINT_BIND` 필수·`MINT_PUBLIC_NAME` 선택), 기본값이 있는 조정 변수 14개, 선택 연동 13개(SIEM 3·LiteLLM 6·OTel 2·GitHub OAuth 1·Typesafe 1).

**E-4. 설치 중 사용자 입력 횟수(코드 기준).** 대화형 입력 **0회**. 필수 인자는 `--bind <사내 IPv4>` 하나(`--name`은 선택). 비밀번호 입력 `read`는 `set-password`·`add-account`에만 있다(`mint.sh:128-142`, 호출처 `:326,334`). 설치 뒤 사람이 해야 하는 일: root 비밀번호 변경, CA 지문 대조와 브라우저·PC 신뢰 등록, 직원 PC 키트 배포(`mint.sh` 끝 안내문). 고정 대역(`10.246.x`)이 사내망과 겹치면 `MINT_NET_PREFIX`를 직접 고쳐야 한다(추정: 겹침 검출은 설치기에 없음).

### F. 엔드포인트 키트 (`endpoint-agent/`)

**F-1. 파일별 LOC·언어**(합계 10,379줄 = py 7,194 + ps1 1,616 + sh 87 + cmd 4 + Dockerfile 14 + README 338 + Windows 시험 1,126)

| 파일 | 언어 | 줄 | 역할 |
| --- | --- | --- | --- |
| `managed-linux.py` | py | 1,256 | Linux 관리형 코어(설치·정책 수신·헤더 헬퍼·보고·롤백). macOS도 이 파일을 불러 쓴다 |
| `agent.py` | py | 1,242 | 관측 에이전트(옛 관측 전용 키트) |
| `managed-windows.py` | py | 1,053 | Windows 관리형 구현(Linux와 별도 구현) |
| `bootstrap.py` | py | 856 | Linux 설치기(간편·격리 모드) |
| `local-runner.py` | py | 727 | 로컬 MCP 실행기(전 OS) |
| `enforce-linux.py` | py | 524 | Linux 격리(AppArmor·nftables) |
| `os-observer-windows.py` / `os-observer.py` | py | 419 / 196 | OS 관측 |
| `managed-macos.py` | py | 367 | macOS 래퍼(`managed-linux.py`를 불러 실행, `managed-macos.py:123`) |
| `offline_buffer.py`, `install.py`, `broker_binding.py`, `windows_status.py`, `runtime-check.py` | py | 229 / 135 / 79 / 73 / 38 | 공용·보조 |
| `setup.ps1`, `windows-worker.ps1`, `tray.ps1`, `windows-common.ps1`, `windows-trust.ps1`, `windows-oneclick.ps1.in`, `install-windows.ps1` | ps1 | 290 / 330 / 321 / 279 / 258 / 129 / 9 | Windows GUI 설치·작업자·트레이·공통·신뢰 검사 |
| `install.sh`, `install-linux.sh`, `install-macos.sh`, `install.cmd` | sh/cmd | 26 / 32 / 29 / 4 | 진입 스크립트 |

**F-2. 공유와 중복.** 설치기는 OS별로 다르다: Linux `install.sh`→`bootstrap.py`→`managed-linux.py install`, macOS `install.sh`→`install-macos.sh`(python.org pkg 서명 확인 후 설치)→`managed-macos.py`→`managed-linux.py`, Windows `install.cmd`→`setup.ps1`(WinForms)→`windows-worker.ps1`→`managed-windows.py`. 공유되는 것은 macOS가 `managed-linux.py`를 불러 쓰는 부분(`managed-macos.py:31,78,123,205`)과 `agent.py`·`offline_buffer.py`·`local-runner.py` 정도다.

`ast`로 최상위 함수명이 겹치는 것을 비교한 결과(`managed-*.py`·`bootstrap.py`): 같은 이름 17개 중 본문이 같은 것은 `ours`(3줄) 하나뿐이다. Linux↔Windows에서 이름만 같고 따로 구현된 것: `apply_policy`(9/12줄), `ca_environment`(3/9), `checks`(39/48), `header`(18/31), `host_report`(17/8), `install`(123/102), `protected`(2/8), `request`(14/14), `rollback`(46/34), `serve`(171/126), `verify_transport`(9/12), `place_harnesses`(`bootstrap.py` 39/`managed-windows.py` 28). Windows 쪽에는 PowerShell이 안내 문구 사전(`windows-common.ps1:260` `Get-EndpointText`)과 신뢰·ACL 검사(`windows-trust.ps1`)를 따로 갖는다. 즉 중복은 세 벌이 아니라 **Linux(+macOS 래퍼)와 Windows(Python+PowerShell) 두 벌**이다. 옛 관측 전용 키트(`install-linux.sh`·`install.py`·`agent.py`·`os-observer*.py`·`install-windows.ps1`)가 관리형 키트와 함께 남아 있다.

**F-3. 설치 단계.** Linux `bootstrap.py`의 `step()`은 8곳이다: 「구성요소 확인」→「필수 구성요소 설치/컨테이너 엔진 설치」→「승인 하네스 배치」(격리) 또는 「하네스 찾기」(간편)→「직원 계정에서 바로 실행되게 연결」(격리)→「<하네스> 모델 로그인」(하네스마다)→「설치 확인」(`bootstrap.py:184,575,644,805-827`). 간편 모드의 화면 단계는 약 4~5개, 격리는 약 6개다. Windows는 `Set-EndpointResult`로 진행률 7단계(5·15·30·50·60·85·100%, `windows-worker.ps1:129-295`). macOS의 단계 표시는 미확인.

**F-4. 실패 시 롤백.** 보상 동작 방식이다. `connect()`가 설치 중 `Failed`를 만나면 `rollback(account)`을 부르고(`bootstrap.py:804-841`), 설치 전에도 기존 설치를 먼저 `rollback`한 뒤 새로 깐다(재설치·복구·모드 전환이 같은 경로). 롤백은 백업 파일 복원·서비스 `disable`·파일 삭제(`managed-linux.py:1151-1210`, `managed-macos.py:217`, `managed-windows.py:934`)로, 스테이징 후 교체가 아니므로 재설치 중 연결이 잠시 끊긴다. 전송 계층 검증(`verify_transport`)은 설치 전에 한다(`bootstrap.py:775`).

**F-5. 키트 자체 갱신.** 자동 갱신 경로는 없다. 업데이트는 「새 키트로 같은 PC에 재설치」이고 게이트웨이는 같은 직원·같은 PC의 직전 활성 장치를 대체한다(`endpoint-agent/README.md:31,88`, `endpoint_plane.py:804`). 서비스는 키트 파일 해시(`kit_version`, `managed-linux.py:65-69`)를 계산해 보고하지만(`managed-linux.py:1044`), 게이트웨이가 이를 최신 키트와 비교해 알리는 코드는 찾지 못했다(미확인: 검색 한계). Python 런타임은 Windows는 키트에 동봉(embeddable 3.13.16), macOS는 설치 때 python.org pkg(3.14.9)를 받아 설치한다.

## ③ 리팩토링 후보

심각도: 상 = 사용자가 겪거나 이미 사고(S4-xx)로 드러난 것 또는 구조 전체를 막는 것, 중 = 규모가 커지면 사고가 되는 것, 하 = 위생·비용. 「예상 효과」의 수치는 정적 집계에 기댄 추정이며, 실제 값은 `GET /api/latency`·`decisions.timings`로 먼저 재야 한다(미실행).

| 번호 | 영역 | 심각도 | 현상 | 근거 | 제안 | 예상 효과 / 위험 |
| --- | --- | --- | --- | --- | --- | --- |
| R-01 | 성능·핫패스 | 상 | 호출 1건이 풀 체크아웃 약 35회(관리형 51)·SQL 약 49문장(65)을 순차로 한다. 계약(`_contract`)·PAC(`pac.build`)·인증·관리형 정책을 2~3회 다시 읽는다 | `core.py:2255-2640,1682-1881`, A-1 표 | 요청 범위 `CallContext`를 한 번 조립해 `_call_upstream`이 재사용하고, 변경 감지는 `dispatch.record`의 FOR SHARE 재검증 한 곳에 모은다. 독립 조회는 `gather`/단일 CTE | 문장 49→약 20, 체크아웃 35→약 12(추정). 위험: 전송 직전 재검증(TOCTOU 방지) 의도를 유지해야 한다 — 적대 회귀·`dispatch_recheck_pg_check.py`가 합격선 |
| R-02 | 성능·이벤트 루프 | 상 | 폐기 목록 전체(서명 검증 포함)를 호출당 5회 이상 flock과 함께 동기로 다시 읽는다. 토큰을 폐기할 때마다 전체 읽기 2회+fsync 3회 | `disposal.py:70-95,97-114,143-152`, `agent_contract.py:166`, `core.py:1216`, `tool_sunset.py:72` | (mtime, 크기, head 해시)를 키로 jti·서버 집합을 메모리 색인으로 들고 바뀔 때만 전체 검증한다. 기록 추가는 끝 레코드만 읽는 증분 방식으로. 읽기는 `to_thread` | 호출당 flock·Ed25519 5회 → 0~1회. 위험: 변조 탐지 지연 — head 서명 검증과 기동 시 전체 검증은 유지 |
| R-03 | 성능·S4-01 | 상 | `tool_sunset.check`가 tools/list 도구마다 트랜잭션 1건, 호출마다 `decisions` 전수 `count(*)`+`tool_name` 인덱스 없는 `max(created_at)` | `tool_sunset.py:78-82,99-149`, `mcp_facade.py:145`, `agent_tables.sql:129-130`, `v2_tables.sql:33-34` | (서버, 도구) 상태를 TTL 60초로 캐시(만료 쪽은 즉시 반영), 봉인 없음 판정은 기동 시 1회로 옮기고, 목록은 서버 단위 한 쿼리, `decisions(server_id, tool_name, created_at DESC)` 부분 인덱스(`upstream_executed` 조건) | 목록 트랜잭션 N→1, 호출당 트랜잭션 1건·전수 `count`가 사라진다. 위험: 만료 반영이 TTL만큼 늦다(fail-safe로 만료는 즉시) |
| R-04 | 성능·Presidio | 중 | JSON 결과의 잎 문자열마다 순차 HTTP 1회, 요청마다 인식기 약 4.7KB 재전송, 동시 2 | `privacy.py:34,117-150,252-269`, `core.py:2413-2420,2589` | 잎을 구분자로 합쳐 한 요청으로 분석하고 span을 되돌린다(`joined` 방식이 이미 있음, `privacy.py:239`). 인식기는 Presidio에 사전 등록하거나 분석기를 프로세스 안에서 호출. 동시 상한은 설정값으로 | JSON 결과의 HTTP k+2 → 2~3회. 위험: 구분자에 걸친 오탐 — `tests/korean_pii_eval.py`·`inspection_corpus_eval.py`로 동등성 확인 |
| R-05 | 안정·풀 | 상 | `/api/overview` 한 요청이 풀 연결 최대 10개를 동시에 쥔다(콘솔 탭이 30초마다, 개요 화면은 `latency`·`health`까지 병렬 6개). 판정 경로와 같은 풀 10개를 나눠 쓴다 | `main.py:514-569,605-640`, `console.js:515-527,639`, `db.py:16-17` | 관리 API 전용 작은 풀을 판정 풀과 분리하고, 개요·지연 집계는 단일 CTE 또는 순차 실행+5초 서버 캐시 | 관리 화면이 판정을 굶기지 못한다(S4-01 재발 차단). 위험: DB 연결 총량 증가 |
| R-06 | 안정·중첩 연결 | 중 | 트랜잭션 안 두 번째 연결 획득·장시간 점유 8곳(B-3). 토큰 폐기는 최대 25초 폴링 동안 연결·advisory 락을 쥔다 | `local_jobs.py:648,751,756`, `idp.py:235,255,279,307`, `agent_service.py:2466-2625`, `ops_response.py:234`, `oidc.py:260` | `connection.execute`로 바꾸고, 폴링·HTTP는 트랜잭션 밖으로 뺀다. `nested_tx.py` 같은 AST 린트를 CI에 넣어 재발을 막는다 | 풀 교착류 제거. 위험: 잠금 순서(`dispatch.py:70` 주석)를 지켜야 한다 |
| R-07 | 성능·원장 | 중 | 모든 판정이 `audit_chain` 행 락 안에서 policy_input 포함 41열을 canonical JSON으로 해시하고 큰 JSONB를 INSERT한다. SIEM 트리거가 같은 트랜잭션에서 한 행을 더 쓴다 | `core.py:2104-2147`, `contract.py:87-108`, `siem_tables.sql` | 직렬화·`canonical_hash(record)`를 락 밖에서(`created_at`을 락 전에 부여) 계산하고 락 안에서는 `sha256(prev + fp)`와 INSERT만 한다. policy_input은 요약 해시+재생용 압축 열로 분리(체인 v9) | 락 점유 시간 단축 → 전역 처리량 상한↑(추정), 행 크기↓. 위험: 체인 순서와 시각 순서가 어긋날 수 있다 — 검증기 영향 확인 필요(미확인) |
| R-08 | 확장성·데이터 | 중 | `verify_audit_chain`이 전 행을 메모리에 올린다. `siem_outbox`는 SIEM이 꺼져 있어도 판정마다 쌓이고 삭제가 없다. `call_reservations`·`dispatch_intents`도 정리 없음 | `core.py:2230-2235`, `siem_tables.sql`, `siem.py:114-148`, A-6 | 검증을 서버 측 커서 청크로 스트리밍하고 구간 체크포인트를 남긴다. SIEM 비활성 시 트리거를 만들지 않거나 전달 완료 행을 주기 삭제, 예약·의도는 만료 N일 뒤 삭제 | 메모리 O(행)→O(1), 보조 표 증가 억제. 위험: 보존 정책(D-141)과 정합 확인 |
| R-09 | 성능·인덱스 | 중 | 인덱스 없는 조건으로 매 호출 조회: `pac.build`의 미해결 변경 조회는 읽기에도 실행되고 JSONB 비교(호출당 2회), 개요 화면은 엔드포인트마다 상관 서브쿼리 3개 | `pac.py:336-341`, `main.py:525-537`, `agent_tables.sql:129-130` | 미해결 조회는 쓰기·실행(w, x)일 때만, `dispatch_intents` 기준으로 전환. `decisions`에 client JSON의 workstation 키 표현식 인덱스 추가 | 호출당 O(이력) 스캔 제거(행 수는 미확인). 위험: 인덱스 쓰기 비용(원장이 추가 전용이라 낮음) |
| R-10 | 성능·디스크 | 중 | 호출마다 `catalog_version()` 전체 읽기+해시, `residency.load_pack` 2회×파일 2개, `catalog()` stat 15회 이상, 자격 파일 3회 | `registry.py:36-72`, `core.py:2453`, `pac.py:306`, `upstream.py:92-95` | `registry`에 (mtime, 크기) 키 스냅숏 하나를 두고 버전 해시·잔류 팩·권한 명세·자격 파일을 거기서 서빙 | syscall 약 60 → 약 5, 해시 제거. 위험: 낮음(`catalog()`가 이미 같은 방식) |
| R-11 | 성능·업스트림 | 중 | 호출마다 initialize+tools/list+tools/call과 `mcp_tools` 전체 재조회 | `core.py:1715-1726`, `upstream.py:391-421` | 읽기 도구에 한해 계약 재확인을 서버별 TTL로 캐시하고 `listChanged` 알림에서 무효화한다. 쓰기·실행은 항상 확인. 허용 범위를 문서화(`research/llm-wiki/analysis/upstream-session-reuse/README.md:99`) | 읽기 호출의 업스트림 왕복 3→1. 위험: 계약 변경 후 TTL 동안 지연 |
| R-12 | 성능·CPU | 하 | 출력 검사가 직렬화·`check_schema`·독성 정규식을 두 번씩 하고, 검증기를 매 호출 새로 만든다 | `core.py:1881,2589-2592,1966-2032,2382,1748`, `pac.py:264` | 스키마 해시별 검증기 캐시, 직렬화 1회 재사용, 마스킹 전·후 검사 중 한쪽은 한계 재확인만 | 큰 결과에서 CPU 절반(추정). 위험: 낮음 |
| R-13 | 구조·런타임 | 중 | 워커 1개의 이벤트 루프에서 분류 정규식·폐기 목록·해시가 동기로 돈다. 프로세스 로컬 상태(C-6)가 워커 증설을 막는다 | `gateway/Dockerfile` CMD, `classify.py:157-168`, A-7 | 핫패스 CPU/IO를 `to_thread` 또는 사전 계산으로 옮기고, 부하 시험 뒤 워커 2~4개. 먼저 세션 풀·`_browser_page`·로그인 제한을 공유 저장소로 | 꼬리 지연↓. 위험: 세션 재사용 풀이 워커마다 갈린다 |
| R-14 | 운영·노이즈 | 하 | 무인증 `/api/health`가 호출마다 정책 번들 약 150KB를 읽어 해시하고 OPA `/v1/policies` 전체를 받으며 httpx 클라이언트를 4개 새로 만든다. OPA 판정 로그가 stdout로 모두 나가고 로그 회전이 없다 | `main.py:397-432`, `release.py:60-90`, `field/Caddyfile:63,102`, `deploy/compose.yaml:93` | 정책 해시 mtime 캐시, `connections.shared` 클라이언트, 5초 결과 캐시. compose에 `logging.options.max-size/max-file`, OPA 결정 로그는 끄거나 입력 마스킹 | 외부 모니터링 증폭·디스크 증가 억제. 위험: 낮음(원장이 정본) |
| R-15 | 구조·판정 경로 | 상 | `execute_call` 386줄·`await` 49·조기 반환 15가 한 함수에 있어 병렬화·캐시·단위 시험이 막힌다 | `core.py:2255-2640`, C-8 | 단계 함수(identity·classify·reserve·inspect_in·context·policy·consent·dispatch·inspect_out·record)와 공유 컨텍스트로 쪼개고 `core.py`를 `decision/` 패키지로 | R-01·R-04·R-12의 전제. 위험: 회귀 — 적대 회귀 42/42·정상 16/16, `replay`, `dispatch_*_pg_check`를 합격선으로 |
| R-16 | 구조·의존 | 중 | 지연 import 57곳으로 31개 모듈이 한 강연결 성분, `core` 팬아웃 33, 콘솔이 `core` 전체를 불러 2개 심볼만 쓴다 | C-2, `agent_service.py:34` | `contract`(순수 함수)·원장·`registry` 인터페이스를 분리하고 콘솔은 `contract`만 임포트. 사이클 6쌍부터 끊는다 | 콘솔 기동·시험 대역 단순화. 위험: 중 |
| R-17 | 구조·스키마 | 중 | 매 기동 SQL 7개 재실행·CHECK 15쌍 재생성(ACCESS EXCLUSIVE+전수 검증), 부트스트랩 이중 정의, 인라인 CHECK는 변경 불가, 마이그레이션 도구 없음 | `core.py:470-478`, `agent_service.py:112-118`, `v2_tables.sql:221`, `agent_tables.sql:233`↔`lifecycle_tables.sql:237`, C-5 | `schema_migrations` 표+번호 SQL 파일+작은 러너(또는 yoyo), CHECK는 `NOT VALID`→`VALIDATE`로 분리, 부트스트랩 함수 하나 | 기동 시간·락 단축, S4-01류 CHECK 함정 제거. 위험: 기존 DB 기준선 이행 |
| R-18 | 구조·설정 | 하 | `os.getenv` 207곳/33파일/변수 130개가 임포트 시점에 평가되고, `.env.example`은 40개만 담는다 | C-4, `core.py:40-122` | `settings.py` 하나에 타입·기본값·검증을 모으고 `.env.example`·compose 환경 목록을 거기서 생성 | 설정 오류 조기 발견·문서 일치. 위험: 환경변수를 패치하는 시험 수정 |
| R-19 | 시험·CI | 상 | 실행 파일 189개 중 144개가 CI·`console.sh`에 이름이 없고 PG 시험 15개(S4-01 회귀 포함)는 어디에도 연결돼 있지 않다. 커버리지 측정 없음 | D-1~D-5, `run_local_suite.py:35-47` | CI에 (a) `run_local_suite.py` job, (b) postgres 서비스 컨테이너 job으로 `*_pg_check.py`, (c) `coverage.py` 최초 측정을 추가한다 | 회귀를 PR 단계에서 차단. 위험: 시간 증가 — 병렬 job으로 흡수 |
| R-20 | 시험·CI | 하 | 세 무거운 job이 이미지를 캐시 없이 각자 빌드하고, 타임아웃이 실측의 4~5배이며, `push`와 `pull_request`를 둘 다 켠다 | `verify.yml:7-13,179,236,349` | `buildx`+gha 캐시 또는 사전 빌드 이미지 공유, 타임아웃 30분, 트리거 정리 | 15~18분 → 약 10분(추정). 위험: 낮음 |
| R-21 | 배포 | 중 | 설치가 서버에서의 이미지 5종 빌드(Go·gcc·pip·Windows Python·spaCy 모델 내려받기)이고 `preflight`가 `python3`을 검사하지 않는다 | E-1·E-2, `gateway/Dockerfile`, `mint.sh:65-71,109` | 서명된 사전 빌드 이미지를 pull하고 소스 빌드는 선택으로. `preflight`에 `python3`·디스크·포트·대역 충돌 검사 추가 | 설치 시간·실패 지점 축소, 오프라인 대응. 위험: 이미지 서명·공급망 검증 체계 필요 |
| R-22 | 배포·운영 | 하 | 헬스체크 없는 서비스 6개, 자원 제한 0, 제품 부팅 경로에 실습 시드(기본 `root`/`user` 계정, 실습 장치 폐기, 기본 비밀번호 `test-password`) | `deploy/compose.yaml`, `agent_service.py:83,91-103` | gateway·agent-service·caddy·model-proxy 헬스체크+`mem_limit`·`pids_limit`. 실습 시드는 분리(D-248 취지)하고 기본 계정은 설치기에서만 만든다 | 장애 감지·자원 폭주 방지. 위험: 낮음 |
| R-23 | 키트 | 상 | Linux(+macOS 래퍼)와 Windows(Python+PowerShell)가 이름만 같은 함수 12개를 따로 구현한다. 같은 결함을 두 번 고친다 | F-2, `managed-linux.py`, `managed-windows.py`, `windows-common.ps1:260` | 공통 코어(`kit_core.py`: 정책 수신·헤더 헬퍼·상태 보고·전송 검증·롤백 계약)를 두고 OS별은 서비스 등록·ACL·격리만 남긴다 | 키트 결함 수정이 한 번에. 위험: 높음 — pj2·pj3 실기기 시험이 필요하다 |
| R-24 | 키트 | 중 | 키트 갱신은 「새 키트로 재설치」뿐이고 서버가 키트 해시를 비교해 알리지 않으며, 롤백이 스테이징 없는 보상 방식이라 재설치 중 연결이 끊긴다 | F-4·F-5, `managed-linux.py:65,1044`, `bootstrap.py:804-841` | 서버가 보고된 `kit_version`을 최신과 비교해 「새 키트 필요」를 콘솔에 표시하고 재설치를 안내한다. 새 판을 따로 깔고 교체하는 순서로 | 갱신 가시성·단절 제거. 위험: 자동 갱신은 공급망 위험이 커서 표시·안내부터 |
| R-25 | 콘솔 | 하 | `console.js` 3,347줄 단일 파일, 직접 `fetch` 6곳, 토큰이 `localStorage`, i18n이 렌더마다 DOM 전체를 정규식으로 훑는다 | C-9, `console.js:64-80,44-52` | 페이지별 ES 모듈로 분리(빌드 도구 없이), `api()` 단일화, 토큰은 메모리+HttpOnly 쿠키, 번역은 키 기반으로 | 변경 충돌 감소. 위험: 중(화면 회귀 시험이 `node --check` 수준) |

## ④ 숫자 요약표

| 구분 | 항목 | 값 | 등급·근거 |
| --- | --- | --- | --- |
| 규모 | 게이트웨이 앱 파이썬 | 68파일(모듈 67+`__init__`), 24,451줄, 함수 1,118개(async 611) | 정적 집계(`ast_stats.py`, `ast_quality.py`) |
| 규모 | 콘솔 정적 파일 | 5,951줄 — `console.js` 3,347·`i18n-en.mjs` 1,389·`console-state.mjs` 360·`charts.mjs` 193·`i18n.mjs` 142 외 | `wc -l` |
| 규모 | SQL | 파일 7개 1,517줄, 테이블 61(+`db/init.sql` 8), 인덱스 57, 트리거 21, `ALTER TABLE` 182 | 정적 집계 |
| 규모 | OPA Rego | 정책 1,257줄(`policy` 771·`pac15` 440·`decision` 46), 시험 1,486줄(규칙 122+8) | `wc -l`, `grep` |
| 규모 | 네이티브 | C 307줄(`textscan`), Go 125줄(`gitleaks`) | `wc -l` |
| 규모 | 결정 기록 | D-001~D-250, 항목 235개 | `docs/ai/decisions/` |
| 라우트 | 합계 | 187 — 게이트웨이 `main` 106, 콘솔 `agent_service` 62, `oidc` 7, `idp` 6, `connectors` 4, `integrations` 2 | 정적 집계(`routes.json`) |
| 핫패스 | 호출당 DB | 풀 체크아웃 약 35(관리형 51), SQL 약 49문장(65), 트랜잭션 5개+단문 30개 | 정적 집계 |
| 핫패스 | 호출당 외부 HTTP | OPA 2~4, Presidio 2+k(마스킹 도구 더), 업스트림 3~4 | 정적 집계 |
| 핫패스 | 호출당 락 | advisory 4~5회(principal 3~4+도구 1), `audit_chain` 행 락 1회, 폐기 목록 flock·검증 5회 이상 | 정적 집계 |
| 핫패스 | tools/list | `5N+6`문장(N=도구 수) | 정적 집계 |
| 핫패스 | 풀·워커 | DB 풀 10·대기 10초·워커 1 | `db.py:16-17`, Dockerfile |
| 안정 | 트랜잭션 안 두 번째 연결 | 5지점(`local_jobs.py:648`, `local_jobs.py:751·756`(호출처 `idp.py` 4곳), `agent_service.py:2466`, `ops_response.py:234`, `user_suspend.py:37`)+트랜잭션 안 외부 I/O·동기 fsync 3지점(`oidc.py:260`, `siem.py:132`, `idp.py` 폐기 기록) | B-3 |
| 구조 | 순환 import | 모듈 최상위 0, 지연 import 포함 31모듈 한 성분, 2-사이클 6쌍, 지연 간선 57 | `ast_stats.py` |
| 구조 | 설정 | `os.getenv` 207곳/33파일/변수 130(`.env.example` 40) | `ast_quality.py` |
| 구조 | 예외 | 처리기 310, 넓은 `except` 82, `pass`뿐 16(`except Exception: pass` 3) | `ast_quality.py` |
| 구조 | 함수 길이 | 100줄 초과 14, 60줄 초과 41, 최장 `execute_call` 386 | `ast_quality.py` |
| 구조 | 전역 가변 상태 | 약 25개(C-6) | `ast_quality.py` |
| 콘솔 | `console.js` | 3,347줄·263KB, 함수 선언 84, 화면 12, `innerHTML` 19, `api()` 58·직접 `fetch` 6 | 정적 집계 |
| 시험 | 파일 | 197(실행 가능 189), 38,821줄 | D-1 |
| 시험 | CI·`console.sh`에 이름이 있는 파일 | 45(144개 없음) | D-1 |
| 시험 | 로컬 실행기 대상(PG 제외) | 137 — 통과 115·실패 5·외부 의존 생략 17 | 기존 보고서 실측(`2026-10-25-gw-bugfix.md:39`) |
| 시험 | PostgreSQL 시험 | 16(CI 연결 1) | D-1 |
| 시험 | 커버리지 도구 | 없음 | D-5 |
| CI | job·타임아웃 | 4개, 15·60·75·75분 | `verify.yml` |
| CI | 실측 | 정적 67~88초·배포 217~223초·LiteLLM 328~330초·전체 768~956초, 한 번 15~18분, `console.sh up` 262초, `console.sh test` 345초 | 실측(2026-10-25 실행 기록) |
| 배포 | 서비스 | 12(기본 11), 직접 빌드 이미지 5, 내려받기 5, 게시 포트 2, 망 7, 볼륨 10 | `deploy/compose.yaml` |
| 배포 | 헬스체크·자원 제한 | 5개 서비스만 헬스체크, 자원 제한 0, 로그 회전 0 | 정적 집계 |
| 배포 | 설치 | 대화형 입력 0, 필수 인자 1(`--bind`), 출력 단계 5, `install.sh` 118초 | 코드 기준 / 실측(CI) |
| 키트 | 규모 | 10,379줄 — py 7,194·ps1 1,616·sh 87·Windows 시험 1,126 | `wc -l` |
| 키트 | 구현 | OS별 구현 2벌(Linux+macOS 래퍼 / Windows), 같은 이름 함수 17개 중 동일 본문 1개 | `ast` 비교 |
| 키트 | 설치 단계 | Linux `step()` 8곳, Windows 진행률 7단계, macOS 미확인 | F-3 |

## ⑤ 정정 메모 — 초안(`research/llm-wiki/analysis/refactor-proposal-1025/README.md`)과 다른 사실

| # | 초안의 서술 | 이 감사의 사실 | 근거 |
| --- | --- | --- | --- |
| 1 | 1.4 D: 「198파일 중 스택이 필요한 스크립트가 146, PG 16, 빠른 단위 시험 9」 | PG를 쓰지 않는 `*_check`/`*_test` 137개 중 120개가 스택 없이 돈다(88%). 필요 자원이 아니라 **CI 미연결**이 문제다(실행 파일 189개 중 144개가 이름 없음) | D-2, `run_local_suite.py:35-47` |
| 2 | 1.4 D: 「PR 1건의 CI가 1시간을 넘긴다」 | 한 번 실행이 15~18분이다. 60·75분은 타임아웃 값이다 | D-3 실측 |
| 3 | 1.3: 「게이트웨이 p50/p95를 운영 원장에서 집계하는 화면·지표는 아직 없다」 | `GET /api/latency`와 콘솔 개요의 「게이트웨이 처리」·「구간별 처리 시간」 카드가 이미 있다. 한계는 24시간 창, 업스트림 4단계(connect·list·call·close)를 뺀 값을 게이트웨이 시간으로 보는 정의 | `main.py:594-660`, `console.js:597-602,710-715` |
| 4 | 1.4 A: 「모듈 59개」 | 앱 파이썬 68파일(모듈 67+`__init__`), 24,451줄 | C-1 |
| 5 | 1.4 G: 「키트가 OS별 세 벌」 | macOS는 `managed-linux.py`를 불러 쓰는 367줄 래퍼다. 실제 중복은 Linux↔Windows 두 벌+PowerShell | F-2, `managed-macos.py:123` |
| 6 | 1.3 마지막 행: 「D-243으로 수정됐으나 같은 패턴이 남아 있는지는 B절」 | **남아 있다.** 트랜잭션 안 두 번째 연결 5지점+트랜잭션 안 외부 I/O·동기 fsync 3지점. S4-01의 비용 구조(도구마다 트랜잭션, `count(*)`)도 남았다 | B-1·B-3 |
| 7 | (문서) `docs/ai/TESTING.md:21`의 「Rego 96건」 | `policy_test.rego`의 `test_` 규칙은 122개(+`residency_review_test.rego` 8개) | `grep` |

초안의 `execute_call` 386줄·`await` 49회(`ast`)와 상위 5개 모듈 10,624줄은 일치한다. 간편 모드 설치 시간(6~15초)과 PJ1 지연 실측(21~164ms 등)은 이 감사에서 다시 확인하지 않았다.

## 부록. 확인하지 못한 것(미확인)과 바로 재볼 수 있는 질의

**미확인**
- 라이브 DB의 `decisions` 행 수·크기, `count(*)` 실제 시간, `siem_outbox` 크기, DB 왕복 시간. 이 감사는 운영 DB에 접근하지 않았다.
- psycopg3 풀에서 체크아웃당 BEGIN·COMMIT이 별도 왕복인지(코드로는 `autocommit`을 켜지 않았다는 사실까지만 확인).
- Presidio가 요청마다 ad-hoc 인식기를 다시 컴파일하는 비용(Presidio 소스 미확인).
- macOS 키트의 단계 수·설치 시간, Windows 키트의 실제 설치 시간(pj3 보고서는 열어 보지 않았다).
- 게이트웨이가 보고된 키트 해시를 최신과 비교하는지(`endpoint_plane.py`에서 찾지 못했으나 전수 확인은 아님).
- R-07의 체인 순서 변경이 `walk_chain`에 미치는 영향, R-03·R-11의 TTL 허용 범위(정책 결정 사항).
- `push`+`pull_request` 중복 실행이 실제로 일어나는지(최근 8건은 모두 push).

**PJ1 원장에서 읽기 전용으로 재볼 질의(미실행)**
```sql
-- 단계별 p50/p95 (콘솔 개요와 같은 정의)
SELECT s.key AS stage, count(*) AS n,
       percentile_cont(0.5)  WITHIN GROUP (ORDER BY s.value::float8) AS p50,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY s.value::float8) AS p95
  FROM decisions d, jsonb_each_text(d.timings) s
 WHERE d.created_at > now() - interval '24 hours' AND d.timings IS NOT NULL AND d.action <> 'connect'
 GROUP BY s.key ORDER BY p95 DESC;
-- 원장 규모와 전수 count 비용
EXPLAIN (ANALYZE, BUFFERS) SELECT count(*) FROM decisions;
SELECT pg_size_pretty(pg_total_relation_size('decisions')) AS decisions_size,
       (SELECT count(*) FROM siem_outbox) AS outbox_rows,
       (SELECT count(*) FROM call_reservations) AS reservation_rows,
       (SELECT count(*) FROM dispatch_intents) AS intent_rows;
-- 풀 점유(게이트웨이+콘솔 연결 상태)
SELECT state, count(*) FROM pg_stat_activity WHERE datname = 'mcp_governance' GROUP BY state;
```
