# 2026-10-21 직원별 MCP 서버 이용 중지·재개 (DEV-79, D-181)

- 작업자: Claude Code (Opus 5 레인)
- 코드 기준: 브랜치 `10/21-dev79-stop`, 시작 `d3238dc`(origin/main), 시작 작업 트리 clean. 변경은 이 브랜치에 1개 commit으로 남겼다(push 없음).
- 시작 근거: 백로그 DEV-79, [방향 갱신 10-20](../../analysis/direction-1020/README.md) 3장, [통제 검토](../../analysis/direction-1020/control-review.md) 105행, TC260 4.2.3(b)-(c)(REQ-M31-07), M05 제2항(REQ-M05-03).
- 해결할 문제와 완료 조건: 콘솔 계정은 두고 한 직원의 한 MCP 서버 이용만 관리자가 즉시 멈추고 되돌린다. **중지 다음 호출부터 거부, 재개 후 정상**, 진행 중 호출 처리 기록, 기존 계정 중지·서버 중지와 상태 구분.

## 결과

구현·로컬 대역 시험·로컬 일회성 PostgreSQL 확인까지 했다. 배포·활성화·기기·PJ1 실제 하네스 검증은 하지 않았다.

1. **상태**: `user_server_suspensions`(`ops_tables.sql`). 직원 토큰×서버 조합당 활성 행은 부분 유일 인덱스로 1개. 재개는 복귀 필드를 채우는 갱신이고 이력은 행으로 남는다(D-122 `ops_suspensions`와 같은 모양).
2. **조작**: 관리자 전용 `GET·POST /api/suspensions`, `POST /api/suspensions/{id}/resume`(`main.py`, `Depends(admin_caller)`), 콘솔 중계 접두 `suspensions`. 중지·재개는 같은 트랜잭션에서 `approval_events`(`user-server-suspend`/`held`, `user-server-resume`/`approved`)에 조작자·직원·서버·사유를 남기고 시각은 `created_at`이다. 중지 시점의 전송 전 예약 수·전송했으나 미응답 수를 사건 범위에 넣었다(진행 중 호출 처리 기록). 원장을 고치는 코드는 없다.
3. **집행 두 겹**: ① `core.execute_call`이 신원 행을 읽을 때 같은 조합의 활성 중지를 한 문장으로 함께 읽어, MCP-REGISTRY-003 뒤·호출 예약 전에 `P-SUSPEND-001`로 차단한다. 관찰 모드에서도 집행된다. ② 전송 직전 `dispatch._INSERT`에 `NOT EXISTS user_server_suspensions`를 더하고 `record()`의 사유 분류에 `user-suspended`를 더해 `core._call_upstream`이 같은 정책 ID로 매핑한다. `suspend()`는 최종 dispatch가 쓰는 직원별 advisory lock을 첫 문장으로 잡아, 이미 전송 트랜잭션을 지난 호출은 진행 중으로 남고 그 뒤 호출은 모두 거부된다.
4. **구분되는 정책 ID**: 새 `P-SUSPEND-001`(priority 2014, 게이트웨이 로컬, 차단)을 `policy_ledger.json`에 추가했다. 기존 `P-INPUT-001`(계정 비활성)·`MCP-REGISTRY-002`(서버 자동 중지)·`ENDPOINT-MANAGED-001`(엔드포인트)과 섞이면 구분이 안 되어 재사용하지 않았다. Rego 변경 없음.
5. **실패는 차단으로**: 상태가 신원 조회와 같은 문장이라 읽지 못하면 호출이 실행되지 않는다(기존 신원 조회 실패와 같은 예외 경로). 전송 직전 조회 실패는 기존대로 `P-CONTROL-FAIL-CLOSED`로 기록된다.
6. **콘솔**: 사용자·엔드포인트 → 「사용자」 행의 「MCP 이용 중지」(서버 선택·사유 제안값 채움), 새 탭 「이용 중지」(사용자·서버·사유·중지·상태·재개, 활성 행에 「재개」, 메모 제안값 채움). 설명 문단·D-번호·영어 값 없음.
7. 새 의존성 없음. 한 번 쓰는 추상화 없음(새 모듈 `user_suspend.py` 1개, 함수 3개).

변경 파일: `full_stack_lab/gateway/app/{user_suspend.py(신규),core.py,dispatch.py,main.py,agent_service.py,ops_tables.sql,agent_static/console.js}`, `full_stack_lab/opa/policy_ledger.json`, `full_stack_lab/tests/user_server_suspend_check.py`(신규), `docs/ai/{DECISIONS.md(D-181),POLICY.md,DATA_MODEL.md,ARCHITECTURE.md}`, [원자 요구사항·근거](../../analysis/user-server-suspend/README.md)(+`local-pg-probe.py`·`.out.txt`), 이 보고서. `status/current.md`·`backlog.md`는 건드리지 않았다(메인 통합).

## WBS 불일치

| 항목 | 백로그·작업 지시 | 위키 원문 | 이번 처리 |
| --- | --- | --- | --- |
| 단위 | 직원×MCP 서버 | 「그 직원·장치의 MCP 호출만」 | 작업 지시대로 직원×서버. 장치 단위는 구현하지 않음(기존 엔드포인트 격리가 따로 있음). |
| 완료 조건 | 중지 다음 호출부터 거부, 재개 후 정상 | 위 둘 + **진행 중 호출 처리 기록** | 기록은 구현(전송 전/전송 후 건수). 이미 전송된 호출의 취소는 하지 않음. |
| 근거 조항 | M05 제3항(백로그·방향 문서·작업 지시) | 통제 검토 105행: M05 **제2항**이 맞고 제3항은 표준 체계 | 제2항(REQ-M05-03)으로 기록. |
| DEV-74 연계 | (작업 지시에 없음) | 통제 검토 115행: DEV-74 기본값을 「경보 + DEV-79 중지 제안」으로 하고 같은 상태 값 재사용 | 연계하지 않음. 방향 제안 참조. |

## 검증

실행 환경: Windows 11, Python 3.12.10, Node v24.21.0, 2026-10-21 KST. 로컬 PostgreSQL·FastAPI 등은 이 저장소 밖 scratch venv에서만 썼고(저장소·제품 이미지·스택 무변경) 솔루션 스택은 띄우지 않았다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 새 시험 | `python full_stack_lab/tests/user_server_suspend_check.py` (12:59 전후) | 24건 통과 (원장 10·판정 6·전송 직전 경쟁 5·배선 3) | 터미널 출력 |
| 새 시험의 민감도 | 제품 코드를 하나씩 되돌려 시험이 실패하는지 확인: `core` 판정 분기 제거(2건 실패), `core._call_upstream` 매핑 제거(4건), `dispatch.record` 사유 분류 제거(4건), `dispatch._INSERT` 조건 제거(4건), `suspend`의 직원 잠금 제거(1건) | 5가지 모두 시험이 실패했고 원복 후 24건 통과 | 터미널 출력(변경 후 원복) |
| 기존 시험 비교 | `tests/*_check.py`, `*_test.py`, `open_endpoints.py` 전부를 변경 전후 같은 환경(psycopg·fastapi 없음)에서 실행해 종료 코드 비교 | 변경 전 0:42·1:49·2:2 → 후 0:43(새 시험)·1:49·2:2. **기존 시험의 종료 코드 변화 없음.** 실패 49+2건은 변경 전부터 psycopg·fastapi·pglast·네트워크 부재, `threat_trace_mapping_check` 7건 실패 등으로 같음 | scratchpad `baseline.txt`/`after.txt`(저장소 밖) |
| 기존 시험 `--gateway` 실행 | scratch venv(Python 3.12, 요구 파일 판본, pglast만 8.7)에서 `high_impact_check.py --gateway`, `fresh_requester_check.py --gateway`, `flow_fingerprint_check.py`, `mcp_result_contract_check.py`, `dispatch_recheck_check.py`, `ops_response_check.py`, `upstream_session_reuse_test.py`, `output_contract_check.py` 등 | 24·10·34·18·15·23·40·15건 통과(`mcp_result_contract_check`는 OTEL 비활성 환경 변수 때문에 한 번 실패해 해제 후 통과). `mcp_result_services_check`는 네이티브 라이브러리·네트워크 부재로 4건 오류(변경과 무관) | 터미널 출력 |
| 실제 SQL | `local-pg-probe.py`: 제품이 쓰는 문장(`user_suspend`, 코어 신원 조회, `dispatch.record`)을 PostgreSQL 16.2(pgserver, pgcrypto 없음)에서 전체 스키마에 대해 실행 | 24/24 통과: 신원 조회 플래그(대상/다른 서버/다른 직원/없는 토큰), `record()`가 중지 조합만 `user-suspended`로 거부, 재개 후 정상, 중복 중지·재개 거부, 사건 1건씩, 사건 수정 불가(트리거), 직원 잠금 보유 중 `suspend` 대기 | [`local-pg-probe.out.txt`](../../analysis/user-server-suspend/local-pg-probe.out.txt) |
| 정적 검사 | 변경 Python 6개 `python -m py_compile`, `pyflakes`(scratch venv), `node --check console.js`, `git diff --check` | 모두 통과 | 터미널 출력 |
| 콘솔·인증·문구 | `node --test tests/*.test.mjs`, `python tests/open_endpoints.py`, `python tests/console_copy_check.py` | 노드 5개 파일 15·3·1·2·4건 통과, 무인증 1개 문서 일치·인증 필요 87개, 문구 위반 0 | 터미널 출력 |
| OPA | `opa test` | **미실행**(docker 없음). Rego는 바꾸지 않았고 원장 JSON에 항목만 더했다(우선순위 67개 유일은 새 시험이 확인) | |
| 콘솔 화면 | 브라우저 렌더링 | **미확인**(스택 미기동). 문법·문구 검사만 | |
| 배포·정책 해시 | 기기 `field up`, OPA 재시작 | **미실행** | |
| 실제 모델·하네스 | PJ1 관리 하네스로 중지→거부→재개→정상 | **미실행** | |
| upstream 효과 | 실제 MCP 서버에 대한 호출 | **미확인**. 모든 호출 경로 시험은 대역 | |

## 실패·미완료·한계

- 미실행: 기기 배포(`ops_tables.sql`은 기동 때 멱등 적용), **OPA 재시작**(원장 JSON 변경 반영 전에는 `P-SUSPEND-001` 판정의 정책 이름·버전이 비어 나옴), PJ1 실제 하네스, 콘솔 렌더링, `opa test`.
- 이미 전송된 호출(`sent`)은 취소하지 않는다. `tools/list`는 그대로 보이고 호출만 거부한다. 업스트림 세션 풀은 비우지 않는다.
- 재개에 독립 승인은 요구하지 않는다. 장치 단위 중지는 없다. 한 직원의 모든 서버 일괄 중지는 없다(서버마다 실행).
- 새 시험의 판정·경쟁 시험은 대역(SQL을 실행하지 않음)이고 SQL 자체는 로컬 일회성 PostgreSQL 16.2에서만 확인했다. 제품 DB 판본·pgcrypto·실제 동시 부하는 다르다. 신원 조회는 모든 호출이 지나가는 문장이라 기기에서 조회 지연이 늘지 않는지 확인이 필요하다(실측 없음).
- 기존 시험의 기대값·AST는 변경하지 않았다. 변경이 필요한 곳도 없었다(신원 조회는 같은 `principals` 문장을 확장했고 기존 대역은 새 열이 없으면 거짓으로 본다. 전송 직전 사유 분류는 `.get`).
- `python research/llm-wiki/tools/check_wiki.py`가 「Code changed after mapping: core.py … run map_threats.py」를 낸다(위협 매핑·스냅샷 재생성은 메인 통합 때). 다른 항목(없는 파일 3건)은 이번 변경과 무관한 기존 상태다.
- 로컬 환경에서 `pytest`는 쓰지 않았다(저장소 시험은 `unittest`). 이미지 환경의 Python 3.10에서는 실행하지 않았다.

## 다음 작업

1. 메인: 기기 배포(OPA 재시작 포함) 후 PJ1 관리 하네스로 중지→같은 도구 호출 차단(`P-SUSPEND-001`)→다른 서버 호출 정상→재개→정상, 원장 두 사건 확인. 콘솔 두 화면 렌더링 확인.
2. DEV-74(반복 위반 자동 일시 중지)가 이 테이블을 재사용할지 결정(방향 제안 2).

## 사용자에게 필요한 입력

없음.

## 방향 제안

1. **한 직원의 모든 서버를 한 번에 멈추는 조작.** 근거: 원문은 「직원·장치의 MCP 호출만 즉시 중지」이고 사고 때 서버가 10종이면 10번 눌러야 한다(편의 우선 지침과 TC260 4.2.3(c) 「원클릭 통제」). 대안: ① API가 서버를 비우면 운영 중인 모든 서버로 전개해 조합 행 N개를 만든다(상태 모델·집행 코드 불변, 새로 등록된 서버는 포함되지 않음), ② `server_id='*'` 행을 도입해 신원 조회를 `IN (서버, '*')`로 넓힌다(신규 서버 자동 포함, 조회·인덱스·dispatch 조건 수정). 영향: ①은 `main.py` 1개 분기와 콘솔 폼, ②는 `core`·`dispatch` SQL과 시험 변경. ①을 권한다.
2. **DEV-74와 상태 공유.** 근거: 통제 검토 115행. 대안: 테이블에 `source`('admin'/'auto') 열을 더하고 자동 중지가 같은 조회·같은 정책 ID를 쓰되 사건 종류만 다르게 한다. 영향: 열 하나·사건 종류 하나, 집행 코드 불변. 사유 문구가 「관리자가 중지했습니다」로 고정이라 자동 중지에는 사유 문구를 상태 행에서 읽도록 바꿔야 한다.
3. **재개 독립 승인(선택).** D-172의 재활성화처럼 중지한 관리자와 다른 관리자가 재개하게 하는 안은 1인 운영에서 막힐 수 있어 넣지 않았다. 관리자 2인 이상 운영이 확정되면 `resume`에 `review.require_independent`를 거는 한 줄 변경이다.
