# 2026-10-21 직원 단위 MCP 전체 중지·재개 (D-181 편의 기능)

- 작업자: Claude Code (Haiku 5.5 실행, 커밋 트레일러는 지시대로 Opus 5 표기)
- 기준 commit: `7151de4`(origin/main), 브랜치 `10/21-suspend-all`. push 없음. 다른 브랜치·main·stash 미사용.
- 배경: D-181은 직원×서버 조합 하나씩만 중지한다. 서버가 10종이면 한 직원을 멈추려고 10번 눌러야 했다.

## 결과

한 직원의 운영 중 서버 전체를 한 번의 요청으로 중지·재개한다. 일괄 조작은 조합마다 기존 단일 조작 `suspend()`·`resume()`을 따로 호출한다(새 판정 경로·새 정책 ID 없음, 단일 API·`P-SUSPEND-001` 불변).

- 신규 라우트: `POST /api/user-suspensions/stop-all`, `POST /api/user-suspensions/resume-all`, 둘 다 `Depends(admin_caller)`. 경로를 `/api/suspensions/…`로 두지 않은 이유: 기존 시험 `user_server_suspend_check.py`가 그 접두의 라우트를 3개로 고정하고 있다.
- 기록: 조합마다 `user_server_suspensions` 행 1개와 `approval_events` 1건이 기존 형식 그대로 남는다. 같은 일괄 조작의 기록은 `scope.batch`(같은 값)로 잇는다. 단일 조작 기록에는 `batch` 키가 없다.
- 응답: `batch`, `suspended`(성공 조합), `skipped`(이미 중지·이미 재개, 사유 포함), `failed`(조합별 예외 종류). 성공과 실패를 합산하지 않는다. 사용자가 없으면 404, 운영 서버가 0건이면 빈 결과.
- 콘솔: 사용자 행에 「전체 중지」「전체 재개」. 완료 알림은 「중지 N건 · 건너뜀 N건 · 실패 N건」(재개도 같은 형식), 실패가 있으면 붉은 알림.
- 대상 서버 정의: `status IN ('READY','DRIFT') AND lifecycle='OPERATING'`. 엔드포인트 측이 서버 목록을 줄 때 쓰는 기준과 같다. 등록 예정·중단된 서버와 나중에 등록될 서버는 대상이 아니다.

## 변경 파일

| 파일 | 내용 |
| --- | --- |
| `full_stack_lab/gateway/app/user_suspend.py` | `suspend`·`resume`에 선택 인자 `batch` 추가, 신규 `operating_servers`·`suspend_all`·`resume_all` |
| `full_stack_lab/gateway/app/main.py` | 신규 라우트 2개와 요청 모델 2개 |
| `full_stack_lab/gateway/app/agent_service.py` | 콘솔 중계 접두 `user-suspensions/` 추가 |
| `full_stack_lab/gateway/app/agent_static/console.js` | 사용자 행 버튼 2개와 핸들러 2개 |
| `full_stack_lab/tests/user_suspend_all_check.py` | 신규 시험 13건 |
| `docs/ai/DECISIONS.md` | D-181 항목에 「일괄」 한 줄 추가 |
| `research/llm-wiki/status/reports/2026-10-21-suspend-all.md` | 이 보고서 |

기존 `user_server_suspend_check.py`, `ops_tables.sql`, `policy_ledger.json`, `core.py`, `dispatch.py`는 건드리지 않았다. 새 의존성·새 테이블 없음.

## 실행한 명령과 결과

| 명령 (작업 디렉터리 `full_stack_lab`) | 결과 |
| --- | --- |
| `python tests/user_suspend_all_check.py` | 13건 통과 (일괄 중지 기록, 건너뜀, 일괄 재개, 중지 0건 재개, 중지 일부 실패, 재개 일부 실패, 재개와 경쟁한 중지 건너뜀, 없는 사용자 거부, 운영 서버 0건, 라우트 관리자 전용, 중계 접두, 기록·테이블 쓰기 범위, 콘솔 동작·실패 표시) |
| `python tests/user_server_suspend_check.py` | **기존 24건 전부 통과**, 기대값·AST 무변경 |
| 민감도 확인 (파일 원복 후 재실행) | 실패 보고 제거 → 1건 실패, 배치 id 제거 → 1건 실패. 둘 다 시험이 잡음 |
| `python -m py_compile` (변경 Python 4개) | 통과 |
| `python -m pyflakes` (변경 Python 4개) | 경고 0건 |
| `node --check gateway/app/agent_static/console.js` | 통과 |
| `python tests/open_endpoints.py` (UTF-8) | PASS. 무인증 1개 문서 일치, 인증 필요 89개 (새 관리자 라우트 2개 포함) |
| `python tests/console_copy_check.py` | 위반 0건 |
| `node --test tests/console-state.test.mjs` | 15건 통과 |

## 미완료·한계

- 미완료: 기기 배포, PJ1 실제 하네스 시험, 브라우저에서 콘솔 버튼 렌더링·알림 확인, HTTP 계층 실제 호출(라우트 응답 형식은 코드 검토와 대역 시험만).
- 운영 서버 정의는 엔드포인트 기준을 따른다. 상태가 DISABLED·PENDING인 서버는 중지 행이 생기지 않으며, 그 뒤 서버가 READY가 되어도 기존 중지 조작을 다시 해야 한다. 「이후 등록 서버 자동 포함」은 D-181 방향 제안 1의 대안 ②(`server_id='*'`)로 남긴다.
- 이미 전송된 호출은 취소하지 않는다(D-181과 같은 한계).
