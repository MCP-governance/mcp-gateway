# 2026-10-23 오늘 기능의 수용 시험 항목 추가 (W7)

- 작업자: Claude Code (Sonnet 5.5, 정상 기능 점검 레인)
- 코드 기준: 브랜치 `10/23-w7-acceptance-today`, 기준 `origin/main` c2c8fee. 변경 파일: `full_stack_lab/gateway/app/acceptance.py`(항목 3개), `full_stack_lab/tests/acceptance_w7_check.py`(새 파일, 대역 확인), `.github/workflows/verify.yml`(정적 단계에 한 줄), `docs/ai/TESTING.md`·`docs/ai/DECISIONS.md`(D-209), 위협 목록 해시 갱신 `research/llm-wiki/catalogs/threats.json`, 이 보고서. 미추적 `2026-10-23-latest-refs.md`는 건드리지 않았다.
- 시작 근거: 10-22 W7 결정(기기 콘솔은 비밀번호 로그인을 하지 않으므로 인증이 필요한 기능 점검은 CI 일회용 스택의 수용 시험으로 한다, `2026-10-22-w7-console-check.md`). 오늘 들어온 D-199·D-201·D-206·D-207에 수용 시험 항목이 없었다.
- 해결할 문제와 완료 조건: 위 기능마다 실제 HTTP로 정상 1건·거부 1건 이상을 확인하고, 상태 코드뿐 아니라 응답 본문·원장을 본다. 이 노트북에서는 스택을 띄우지 않으므로 실제 실행은 CI에서 한다.

## 결과

`acceptance.py`에 항목 3개를 추가했다(`console-registration-pins-and-expires` 바로 뒤, 같은 실제 fetch 서버를 해제한 뒤에 쓴다). 기존 항목의 기대값은 바꾸지 않았다. 신청은 합성 직원이, 승인은 합성 관리자가 하며 모든 항목은 `finally`에서 등록을 해제하고 남은 신청을 거부로 정리한다.

| 항목 | 기능 | 정상 | 거부 | 본문·원장 확인 |
| --- | --- | --- | --- | --- |
| `one-click-approval-lowers-tool-class` | D-199 | 원클릭 승인을 제안이 읽기가 아니면 `actions={"fetch":"r"}`로 낮춰 등록(READY) | 올리기 422(`제안값 이하`), 선택하지 않은 도구 분류 변경 422, 직원의 미리보기·승인 403, 바뀐 화면(`proposal_sha256` 불일치) 409, 게이트웨이 `/api/registry/servers` 직접 등록으로 분류를 쓰기로 바꾸기 409(`승인한 범위`) | 거부된 클릭 뒤 서버·신청 상태 불변, `mcp_tools`가 `fetch=r`, `approval_events`의 `intake-one-click/approved` 범위에 `tools`·`actions`, 신청자 `/mcp/<id>/` 도구 목록이 fetch 1개, 원격 신청의 `local_run_preset`·`local_run_status`가 비어 있음 |
| `server-level-consent-decisions` | D-201 | 첫 호출 `P-CONSENT-001` 차단 → 승인 도구 전부가 `PENDING`으로 대기 → 서버 단위 허용(기한 붙음) → 호출 실행(Allow/Alert) → 철회 → 다시 차단·새 대기 | 관리자가 직원의 요청을 결정, 다른 서버 경로, 화면에 없던 번호 포함, 대기 상태의 철회가 모두 409이고 상태 불변, 개별 결정을 남이 하면 409, 빈 목록 422, 서버 단위 거부 뒤 호출은 거부 사유로 차단되며 다시 묻지 않음 | `/api/consents` 본문(서버·도구·상태·기한), `decisions.reason`의 거부 사유, `approval_events`의 `user-consent` 도구별 사건 순서(`rejected`→`approved`→`rejected`)와 행위자 |
| `approval-preview-local-run-values` | D-206·D-207 | 공식 저장소 `src/filesystem`(읽기 마운트 `mcp-docs`)·`src/memory`(쓰기 마운트 `mcp-memory`+`MEMORY_FILE_PATH`)의 기본값, `src/git`·`src/time`은 빈 제안과 「관리 계정으로 실행할 수 없는 이미지」 | 같은 경로라도 다른 저장소는 빈 제안·빈 상태, 실행 계약이 없는 제안(`execution-missing`)의 승인 클릭 409이고 신청은 보류 그대로 | 응답의 `local_run_preset`·`local_run_status` 필드와 `proposal.blockers` |

대상 MCP는 수용 스택이 이미 쓰는 실제 fetch(공개 OSS `mcp-server-fetch`, TLS 경로)뿐이고 새 mock MCP는 없다. 미리보기 항목은 공식 저장소의 URL·경로 메타데이터를 가진 보류 상태 합성 신청 행 5건을 DB에 넣어 응답 필드만 본다(검증 전 행이라 실행·등록은 하지 않으며 워커는 `VALIDATION_QUEUED`만 가져가므로 건드리지 않는다).

도구 목록·호출 판정 같은 게이트웨이 쪽 확인은 기존 `call()`·`list_tools()`를 그대로 썼다. 새 시험 파일 `acceptance_w7_check.py`는 위 항목 함수를 HTTP·DB 대역(서비스의 거부 규칙·상태 전이를 흉내 낸 것) 위에서 돌려 항목 코드가 기대한 요청·응답 모양과 정리 동작을 따르는지 보며 CI 정적 단계(`acceptance_tls_check.py` 다음)에 넣었다. 대역 시험은 서비스가 통과했다는 증거가 아니다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `python -m pyflakes acceptance.py acceptance_w7_check.py`, `node --check console.js`, `python full_stack_lab/tests/open_endpoints.py` (Windows 노트북, 2026-10-23) | 통과 | 로컬 출력 |
| 항목 코드 대역 시험 | `acceptance_w7_check.py` 10건(정상 4: w·x·r 제안, 두 번째 관리자 승인, 동의 흐름, 미리보기+정리 / 잘못된 서비스 대역에서 항목이 실패하는지 3: 올리기 수용·남의 결정 수용·기본값 누락 / 항목 등록 순서 1) | 10건 통과. 이 노트북에는 `httpx2`·새 `mcp` SDK·gateway 의존성이 없어 그 모듈만 빈 대체로 바꿔 실행했다(CI 정적 단계는 의존성을 설치하고 실행) | 로컬 출력 |
| 위키 CI 6단계 | 아래 「위키 검사」 | 아래 | 로컬 출력 |
| 수용 시험 실제 실행 | CI `./console.sh test` | **미실행**(리더가 push 뒤 확인) | — |
| 실제 모델·하네스·기기 | 미실행 | — | — |

### 위키 검사

2026-10-23 로컬(Windows, `PYTHONUTF8=1`)에서 CI 순서대로 실행했고 모두 종료 코드 0이다. 코드가 바뀌어 `map_threats.py`를 먼저 돌리고(위협 목록 해시 갱신), 변경을 커밋한 뒤(0aa5732) `build_enterprise_analysis.py --refresh-code-only`를 돌렸다(`source_commit` 0aa5732, 요구 80·통합 조건 50, 실행 기록 보존). 이 갱신이 `requirements.json`·`integration-cases.json`의 코드 근거 해시를 바꿔 둘째 커밋으로 올렸다.

| 검사 | 결과 |
| --- | --- |
| `check_wiki.py --ci-ignored-local-sources` | 오류 0(무시된 로컬 원본 누락 경고만) |
| `check_trace.py --self-test` | PASS |
| `check_trace.py` | 오류 0, 경고 6(기존 미참조 ID) |
| `check_enterprise_analysis.py` | 오류 0, 경고 0 |
| `test_enterprise_code_refresh.py` | 3건 통과 |
| `PYTHONUTF8=1 python research/collaboration-console/test_console.py` | 32건 통과 |

## CI에서 리더가 볼 항목

`gateway-acceptance-v3` 결과에서 새 3개 항목 이름: `one-click-approval-lowers-tool-class`, `server-level-consent-decisions`, `approval-preview-local-run-values`. 각 `details` 첫 줄이 위 표의 정상 요약이다. 실패 시 메시지가 어느 단계(코드·본문)에서 멈췄는지 말한다. 코드를 읽어도 확정할 수 없어 CI에서 처음 드러날 가능성이 있는 지점:

1. **fetch 도구의 제안 분류**: `mcp-server-fetch 2026.8.18`이 도구에 읽기 힌트를 다는지 코드·락 파일로 확인하지 못했다. 항목은 제안값(r·w·x)에 맞춰 분기한다. 제안이 `r`이면 낮추기는 시험하지 못하고(올리기 422만) details에 `actions={}`로 남는다. `x`이거나 위험 등급이 높음 이상이면 첫 클릭이 `pending`이 되고 합성 두 번째 관리자(`<관리자>-2`)가 같은 범위로 눌러 승인한다. 이 분기는 대역에서만 돌려 봤다.
2. **보류 상태 합성 신청 행의 미리보기**: `approval-preview`가 저장소 신청(보류, 검증 전) 행에서도 200과 `local_run_*`를 돌려준다는 것을 코드로만 확인했다(`agent_service.py` `preview_intake_approval`의 마지막 return). 500이 나오면 이 항목이 먼저 드러난다.
3. **동의 시험의 `decisions.reason`**: 거부 뒤 호출의 사유 문구(`동의하지 않았…`)를 `decisions.reason` 열에서 읽는다. 열 이름은 `/approvals` 조회의 `d.reason`을 근거로 했다.
4. **같은 fetch 경로의 중복 신청**: 같은 엔드포인트의 진행 중(HOLD 등) 신청이 있으면 새 신청이 409다. 앞의 등록 시험이 승인(APPROVED)으로 끝내므로 막지 않지만, 그 시험이 중간에 실패해 신청이 남으면 새 항목이 같이 실패할 수 있다(원인은 앞 항목 쪽).

## 실패·미완료·한계

- **PC 격리 실행 자체는 수용 스택에서 시험할 수 없다**(직원 PC·실행기·Docker 허용 이미지가 없다). D-206·D-207은 미리보기 응답의 `local_run_preset`·`local_run_status` 필드까지만 보며 서명·이미지 digest·컨테이너 기동·`/root` 권한 때문에 git·time이 실패하는 현상은 보지 않는다(PJ1 실사용 증거가 따로 필요).
- **원클릭으로 등록한 fetch는 호출할 수 없다.** 원클릭의 도구 심사는 외부 목적지가 비어 있고 `derived_constraints`가 주소 인자에 항상 거절하는 패턴(`(?!)`)을 붙인다. 그래서 D-199 항목은 등록 상태·원장·도구 목록까지만 보며 분류 낮추기가 호출 판정(쓰기 중복 실행 방지 `P-RATE-003` 회피)에 미치는 효과는 보지 않는다. D-201 항목은 같은 이유로 등록 시험과 같은 계약 검토 경로(`review-contract`→`approve`→`register`)로 `consent: true` 도구를 등록해 쓴다. 즉 동의 항목은 원클릭이 아니라 동의 기능 자체를 본다.
- **「한 서버의 도구 여러 개를 한꺼번에」**는 fetch가 도구 하나라 일괄 구조는 못 본다. 대기·결정·거부 규칙과 감사 사건만 확인하며 다중 도구 일괄은 대역 시험 `consent_per_server_check.py`가 다룬다. TLS 경로가 있는 다른 실제 서버는 이 스택에 없다.
- **관찰(고치지 않음)**: 두 번째 관리자의 승인 미리보기(`one_click_pending` 경로)는 `local_run_preset`·`local_run_status`를 응답에 싣지 않고 일찍 돌아간다(`agent_service.py`의 첫 `return`). 저장소 신청이 2인 승인 대상이고 같은 승인 창이 이 필드로 입력란을 채운다면 두 번째 관리자 화면에서 기본값이 비어 보일 수 있다. 화면 쪽은 확인하지 않았다.
- 합성 신청 행이 최종적으로 `REJECTED`로 남는다(원장 삭제 불가). 일회용 스택이라 영향은 없으나 기기 스택에서 실행하면 신청 목록에 거부된 시험 행이 남는다.
- 위협 목록 `threats.json`의 해시 변경은 `map_threats.py`가 이미 오래된 `worktree_modified` 표식을 현재 커밋 기준으로 정리한 것이다(이번 변경 파일과 무관).

## 다음 작업

- 리더: push 뒤 CI의 새 3개 항목 결과를 확인하고 실패한 단계 메시지를 이 보고서의 「CI에서 리더가 볼 항목」에 대조한다.
- 필요하면 원클릭 도구 심사에 목적지를 줄 수 있게 한 뒤(별도 결정) D-199를 호출 판정까지 확장한다.

## 사용자에게 필요한 입력

없음.
