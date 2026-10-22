ACK AIG-01-LITELLM-SYNC

# 2026-10-23 LiteLLM 승인·철회 동기화

- 작업자: Codex. Job `auto-f534baaace057f5362cf`.
- **CHECKED:** baseline `e30be961a9a00d7982dd8565e4412c7289e85f4d`; 실제 브랜치 `10/23-litellm-sync`; cached `origin/main`도 같은 commit. 시작 diff는 비어 있었다. 쓰기 전·검증 중 HEAD를 다시 확인했으며 동일했다. timeout **3600초**.
- **CHECKED:** inbox **8322·8330·8336**은 다른 과거 자동 배정이며 이번 권한으로 해석하지 않았다. **8366**은 이번 P1 배정과 일치한다. 초기 coordinator event **8368**(`2026-10-23T05:08:44+09:00`) 뒤 최신 event **8377**(`2026-10-23T07:09:11+09:00`)을 반영했다. **8370·8371**의 잔여 15%·6% 알림은 과거 관측이며 권한 추가나 실행 중 작업 취소로 해석하지 않았다. 활성/미해결 W5-KIT-MACOS와 task 없는 antigravity 작업은 이번 LiteLLM 범위와 코드 중복이 발견되지 않았다. 시작 당시 다른 미커밋 변경은 없었으며 다른 작업물을 덮어쓰지 않았다.
- 최신 관련 commit: `e30be96` Windows 원클릭 병합, `e9421af` 기업 코드 근거 갱신 병합, `10ffa83` 코드 근거 해시 갱신. Windows 작업은 수정하지 않았다.
- 원격 HEAD 재조회는 `git ls-remote --symref origin HEAD`의 네트워크 연결 실패로 미확인이다. 새 브랜치 생성·커밋·push·기기 접속·스택 기동은 하지 않았다.
- D 번호는 지시된 `py -X utf8 research/llm-wiki/tools/check_trace.py --next D`의 **D-208** 출력을 사용했다. 내부 fetch는 네트워크 제한으로 실패했으며 도구가 표시한 로컬/캐시 끝점 93개 기준이다.

## 완료한 산출물

| 산출물 | 경로·내용 |
| --- | --- |
| 관리 동기화 | `full_stack_lab/gateway/app/litellm_sync.py`: 기본 꺼짐, 관리 API, 승인 범위 재산출, 키·팀 매핑 대조, 재조회, 영속 재시도, G5 사건 |
| 영속 상태 | `full_stack_lab/gateway/app/litellm_sync_tables.sql`: revision·fingerprint·재시도 시각·적용 대상·자격 소유자·모집단 확인불가 상태 |
| 연결 | `core.register_server`·`deregister_server`, `ops_response.suspend`, `decommission.open_case`·`close_case`; 주 워커 lifespan·설치 초기화·선택 환경 변수 |
| 화면 | `main.registry_view`와 `agent_static/console.js`: 동기화 대기·실패·완료, 등록 해제된 관리 대상도 상태 확인 |
| 새 시험 | `full_stack_lab/tests/litellm_sync_check.py`: 실제 loopback HTTP 관리 API 대역 + 메모리 DB. 신규 MCP 서버가 아니며 실제 LiteLLM·MCP 증거로 세지 않음 |
| 설정·계약 | [운영 계약](../../../../docs/ai/LITELLM_SYNC.md), [비밀 없는 예제](../../../../addons/litellm/sync-bindings.example.json), D-208·데이터 모델·기존 애드온 문서 연결 |
| 분석 정본 | [판본·심볼·행·라이선스·한계](../../analysis/litellm-intervention-1023/sync-implementation.md), [원자 요구사항 JSON](../../analysis/litellm-intervention-1023/sync-requirements.json) |
| 재현 증거 | [검증 JSON](../../analysis/litellm-intervention-1023/sync-evidence.json), [수집 스크립트](../../analysis/litellm-intervention-1023/collect_sync_evidence.py): 실제 명령·종료 코드·출력·로컬 파일 SHA-256·심볼 행 |

승인 성공 응답으로 끝내지 않고 서버·키/팀 도구·자격·열거한 워커의 서버/세션 상태를 다시 읽는다. 실패한 승인 경로는 가능한 경우 삭제한다. 기존 OAuth/BYOK 설정은 갱신 때 보존하며 자격 값은 복제하지 않는다. 철회 시 자격 소유자를 삭제 전에 열거하여 cascade 삭제 뒤 세션 대상을 잃지 않게 했다. 열거 실패로 모집단을 잃었으면 재시도 뒤 빈 목록만으로 완료하지 않는다.

관리 키는 파일/환경 변수 참조로 요청마다 다시 읽는다. 직원 MINT 토큰을 새 관리 동기화 경로로 보내지 않는다. 사건 원장에 재조회 시각·기대 범위·관측·실패만 덧붙이고 판정 행을 수정하지 않는다. 기본 설정은 꺼짐이다. 기존 `tests/ai_gateway_addon_check.py`와 기대값을 수정하지 않았다.

## 실제 검증

DB 검토에는 제공된 `supabase:supabase-postgres-best-practices` 스킬과 PostgreSQL 18 공식 세션 잠금 계약을 적용했다. HTTP 전파 동안 트랜잭션·행 잠금을 유지하지 않고, 별도 연결의 세션 advisory lock으로 워커만 직렬화한다. 원장과 결과 기록은 짧은 트랜잭션이며 새 revision의 즉시 재시도를 보존한다. `DB_POOL_MAX>=2`가 필요하다. 대역에서 취소·경쟁 조건을 확인했으며 실 DB의 동시성 검증은 미완료다.

Windows 로컬 Python **3.10.5**·Node에서 수행했다. 다음 명령들의 최종 출력과 바이트 근거는 `sync-evidence.json`이 정본이다.

| 검사 | 실제 명령 | 결과 |
| --- | --- | --- |
| 신규 관리 동기화 | `py -B -X utf8 full_stack_lab/tests/litellm_sync_check.py` | **21건 통과**. 생성·PUT·삭제·재조회 불일치·키/팀 범위·자격/세션 잔존·cascade 전 열거·모집단 소실·HTTP 실패/대기/재시도·전파 중 철회·신규 경로 정리·자격 설정 보존·트랜잭션 밖 HTTP·revision 경쟁·잠금 취소·기본 꺼짐 |
| 기존 운영 대응 | `py -B -X utf8 full_stack_lab/tests/ops_response_check.py` | **23건 통과** |
| 기존 공급망 영향 | `py -B -X utf8 full_stack_lab/tests/sbom_impact_check.py` | **8건 통과**. 초기 함수 추출 시험과 새 상대 import의 충돌을 코드에서 수정한 뒤 통과; 기대값 불변 |
| Python 문법 | 수집 스크립트의 `ast.parse` 명령 | 변경 Python 및 기존 애드온 시험 문법 통과 |
| 화면 문법 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 |
| 기존 화면 상태 | `node --test full_stack_lab/tests/console-state.test.mjs` | **15건 통과** |
| 기존 원클릭 화면 | `node --test full_stack_lab/tests/intake_one_click_ui_check.mjs` | **6건 통과** |
| 인증 라우트 | `py -B -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과. 무인증 1·인증 필요 97, 새 라우트 없음 |
| 기존 애드온 회귀 | `py -B -X utf8 full_stack_lab/tests/ai_gateway_addon_check.py` | 실행 시작 실패: **httpx 미설치**. 통과로 세지 않음 |
| pyflakes | `py -m pyflakes …` | 실행 시작 실패: **pyflakes 미설치** |
| 기존 원클릭 AST | `py -B -X utf8 full_stack_lab/tests/intake_one_click_ast_check.py` | 실행 시작 실패: Python 3.10에 `datetime.UTC` 없음. Python 3.11 이상 필요 |
| 워킹 트리 | `git diff --check` | 통과 |
| 위키 | `map_threats.py`, `capture_status.py`, `build_wiki.py`, `check_wiki.py --ci-ignored-local-sources` | 통과. 변경 소스의 정적 매핑·현황 재생성, 위키 오류 0·경고 119(주로 ignored 원문 부재). 정적 검토의 과거 증거는 새 통과로 바꾸지 않음 |
| ID 추적 | `py -B -X utf8 research/llm-wiki/tools/check_trace.py --no-fetch` | 오류 0·기존 경고 6. D-208 정의·참조 확인 |
| 기존 기대값 | `git diff --exit-code -- full_stack_lab/tests/ai_gateway_addon_check.py` | 차이 없음 |

일괄 재현: `py -B -X utf8 research/llm-wiki/analysis/litellm-intervention-1023/collect_sync_evidence.py`.

일괄 수집기는 시작 실패도 실패로 보존하고 검사 하나라도 실패하면 종료 코드 1을 반환한다. 현재 환경의 세 검사 제한 때문에 전체 검증을 통과로 보고하지 않는다.

최종 일괄 수집 결과는 **16개 명령 중 13개 통과·3개 실행 시작 실패**, 수집기 종료 코드 **1**이다. 수집한 로컬 파일 16개의 SHA-256을 다시 대조하여 불일치가 없음을 확인했다.

## 미완료·한계

- **실제 PostgreSQL·LiteLLM 1.105·PJ1·브라우저는 미실행**이다. DB 대역은 실 DB 잠금·롤백·프로세스 강제 종료를 증명하지 않는다. 실제 키/팀 ACL·캐시·세션 종료와 독립 호출 효과를 확인하지 않았다.
- 신규 자동 생성은 **자격 없는 HTTP upstream**에 한정한다. 로컬 stdio/실행 주소와 URL 안 자격은 실패로 남긴다. 신규 OAuth/BYOK 인증 설정이나 비밀 발급/복제는 구현하지 않았다. 이미 존재하는 인증 설정은 보존하고 저장 자격 철회는 처리한다.
- 이번 P1은 관리 상태 전파다. 과거 D-191의 직원 토큰 전달 방식(P3/P6)을 이번 관리 워커에서 사용하거나 확장하지 않는다. 키·팀 신원 매핑은 LiteLLM ACL 갱신용이며 MINT 호출 판정의 transport 신원을 대체하지 않는다. 실제 호출 경로 검수는 별개로 남는다.
- 전파 대기·외부 관리자 동시 편집·이미 전송된 호출·누락 워커·SSE/stateless 요청·외부 공급자 토큰의 실제 원격 폐기는 보장하지 않는다. 세션 종료는 서버별이 아닌 해당 사용자의 집계 세션 범위다. G5 사건만으로 T1을 부여하지 않는다.
- LiteLLM 릴리스 commit `80b9556dd312d18c535ae06884faa97d1fdb8f46`과 공식 태그의 행을 확인했다. 네트워크 제한으로 **immutable commit 원문 바이트·전체 원문 SHA-256은 확보하지 못했다**. 문서·소스 읽기와 실행 증거를 구분했다.
- 기존 애드온 회귀·pyflakes·Python 3.11 이상 원클릭 시험은 도구 환경을 갖춘 후 실행해야 한다. 로컬 대역 성공을 기업 기능 검수 완료로 보고하지 않는다. 외부 시트나 다른 에이전트에게 메시지를 보내지 않았다.

## 다음 작업

**다음 행동 1개:** 리더가 미커밋 산출물을 검토한 뒤 도구 의존성과 승인된 매핑을 준비하여 솔루션 기기 배포·LiteLLM 1.105/PostgreSQL·PJ1 통합 검증을 수행한다.

## 실행 한도

dispatch 당시 Codex 잔여 **31.0%**와 이전 reset `2026-10-23 07:08:54 KST`는 과거 관측이다. 최신 전달값은 **84%**(epoch `1792706950.1842968`)이며 현재 잔여는 **알 수 없음**. 최신 알려진 reset은 **2026-10-30 02:08:54 KST**(`1793293734`)다. 완료한 산출물·실행 증거·미해결 항목은 위와 같으며 커밋·push·실기기 작업은 리더에게 남겼다.

## 사용자에게 필요한 입력

이번 로컬 구현에 추가 입력은 없음. 실제 검증에는 운영자가 정한 사용자/키 해시/팀/전체 워커 매핑과 비밀 저장소 참조가 필요하다. 비밀 값 자체는 보고서에 수집하지 않는다.
