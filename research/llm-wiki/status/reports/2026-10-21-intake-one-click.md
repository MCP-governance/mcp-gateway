# 2026-10-21 도입 한 화면 승인 — main 기준 재배치 후보

- 작업자: Codex sol S1.
- 시작 코드: 원본 클론 `10/20-intake-one-click`, HEAD `217da74ed4731eb006ce3c167b17fec835b66155`, 미커밋 33파일.
- 기준 main: 다른 로컬 클론의 `origin/main`에서 확보한 `d3238dccd6a6fb7266a7b9201f5b133e2a025aea`. 원본 `git fetch origin main`은 `.git/FETCH_HEAD: Permission denied`, 별도 클론의 같은 원격 fetch는 GitHub 연결 실패. **최신 원격 여부는 확인하지 못했다.**
- 보존 commit: `0717462fee76ce4c0ea7e53740147dce8e2dbde1`, 메시지 `feat(v2): 도입 한 화면 승인 DEV-73 기반, 재배치 전 보존`. 별도 임시 클론의 `10/20-intake-one-click`에 33파일을 원본 바이트 그대로 커밋했다.
- 재배치 후보: 같은 임시 클론의 `10/21-intake-one-click-main`, main에서 직접 분기. 원본 `.git`은 읽기 전용이어서 원본 브랜치 보존 커밋·새 브랜치 생성은 **미완료**다. 검토 가능한 결과는 별도 클론과 두 Git bundle에 있다. 원본 제품 파일은 변경하지 않았다.
- 이 보고는 [10-20 보고](2026-10-20-intake-one-click.md)의 재배치·현행 검증 부분을 대체한다. 구 보고와 [기존 실행 증거](../../analysis/intake-one-click/verification.json)는 당시 판본의 이력으로 보존한다.

## 결과

main에 있는 [D-175 적대 검토](../../analysis/review-1020/d175-local-run.md)와 [메인 판단](../../analysis/review-1020/d175-arbitration.md)을 읽었다. C 반려 유지와 재검토 전 병합·배포·PJ1 금지를 따른다. 도입 화면 변경만 보존 commit의 부모 대비 diff로 옮겼으며 DEV-73 3개 commit은 재배치 브랜치의 조상에 포함하지 않았다.

| 범위 | 재배치 결과 |
| --- | --- |
| 원격 MCP 도입 | 도구 선택·신청 등급 보존·계약/검사/범위 제안·독립 승인·등록 연결 유지 |
| 기존 관리 실행이 있는 저장소 | main의 `mcp_runtimes`에서 동일 소스 commit의 활성 실행 계약을 찾아 기존 승인·게시·등록 연결 유지 |
| 실행 계약 없는 저장소 | 승인 차단 유지. 임의 실행 주소·이미지·도구 계약을 생성하지 않음 |
| DEV-73 대기 | 서명 묶음 입력·매니페스트 초안·로컬 작업 채널·로컬 실행 사유/DB 열·`local:` 계약 조회/등록 제외. 실행 계약 확보 수단 중 반려된 부분만 보류 |
| 공급자·위치·위험 | D-185·186·187의 10-20 범위 유지. 선택 보증·입력 EOL 상한·관할 팩 명시 활성·높은 등급의 2인 승인·치명적 발견 사유 분리 |
| 결정 문서 | D-184~187 및 관련 D-137·138·143의 대체 관계만 이동. D-175 추가/변경 없음 |
| DB | 도입 신청 `requested_tools` JSON 열 하나만 추가. `local_reason`·`local_jobs`·매니페스트 DB 변경 없음 |
| 위협 매핑 | 10-20의 DEV-73 기반 생성물 3파일은 그대로 옮기지 않았다. main 기준 현재 파일로 다시 생성했으며, 과거 검토 대상 8파일은 낡음으로 표시했다. 이전 검토를 현행 통과로 재사용하지 않음 |

제품 기능을 추가하지 않았다. 새 의존성·정책 ID도 없다. `upstream.discover`의 선택적 principal 전달은 기존 직원 토큰을 upstream으로 전달하는 기능이 아니라 기존 공급자 자격의 허용 주체 경계를 재사용한다. 신청자 조회는 전송 토큰의 principal을 사용한다.

## 검증

환경은 Windows의 Python 3.12.14·Node 24.21.0, 실행 위치는 별도 임시 클론 `full_stack_lab/`이다. 실행 시각·실제 argv·종료 코드·stdout/stderr는 [10-21 검증 JSON](../../analysis/intake-one-click/verification-2026-10-21.json)에 있다. 최초 충돌 해소 과정에서 남은 괄호로 실패한 구문/AST 결과도 `prior_attempts`로 보존했고, 수정 뒤 아래 최종 검사를 다시 실행했다.

| 검사 | 최종 결과 |
| --- | --- |
| 변경 Python 13파일 `-m py_compile` | 통과 |
| `node --check gateway/app/agent_static/console.js` | 통과 |
| `node --test tests/console-state.test.mjs tests/intake_one_click_ui_check.mjs` | 21 통과(기존 15·신규 6) |
| `python tests/open_endpoints.py` | 통과: 무인증 1·인증 필요 85. DEV-73 두 작업 API는 포함되지 않음 |
| 새 `intake_one_click_check.py` | 8 통과·11 생략. 정상 게이트웨이 이미지 의존성 없음 |
| 새 `intake_one_click_ast_check.py` | 11 통과. 실제 제품 함수 본문+Pydantic, DB/HTTP 대역이며 실제 MCP 증거 아님 |
| 새 `intake_one_click_ui_check.mjs` | 위 Node 실행에 포함, 6 통과. 브라우저 렌더 검수 아님 |
| 기존 `supplier_assurance_check.py` | 4 통과·2 생략 |
| 기존 `data_residency_check.py` | 8 통과 |
| 기존 `intake_risk_tier_check.py` | **10 통과·2 실패·13 생략**, 기대값/AST 변경 없음 |
| 기준 main의 동일 위험 시험 | 12 통과·13 생략. 후보의 2건이 기존 기준에서는 통과함을 확인 |
| 위협 매핑·위키 검사 | 24개 매핑 재생성. 위키는 **실패: main에도 있는 누락 3건·경고 119개**, 후보가 추가한 오류 0 |

기준 main의 원래 위험 정책/시험 재실행과 파일/계보/DEV-73 제외 검사는 [재배치 증거](../../analysis/intake-one-click/rebase-evidence.json)에 별도 기록한다. 기존 시험의 기대값·AST와 main의 다른 작업 변경을 보존했다. 원자 요구사항의 현재 파일·심볼·행·SHA-256은 [요구사항 정본](../../analysis/intake-one-click/requirements.json), 이전판은 `requirements-2026-10-20.json`이다.

## 기대값 충돌과 WBS 불일치

[충돌 분석](../../analysis/intake-one-click/risk-expectation-conflict.md)에 2건 각각의 기존 기대값·근거 commit `bbaa8c6`, 새 동작·D-187·위키·공식 명세 근거, 판본별 정확성 판단, 영향받는 API 시험·정책 ID를 적었다. 기존 main 기대는 D-143에 맞고, 이번 목표 동작은 D-187에 맞는다. 기존 시험은 바꾸지 않았으며 메인의 정책 채택·적대 검증이 필요하다.

WBS 불일치: DEV-68의 필수 보증, DEV-69의 기본 위치 누락 차단 완료 조건은 D-185·186의 새 기본값과 다르다. 완료 조건을 임의로 바꾸지 않고 후보 상태와 이 차이를 보고했다. DEV-73은 WBS의 한 줄 구현 상태와 관계없이 원문 판단의 C 반려를 따른다.

## 실패·미완료·한계

- **원본 클론의 보존 commit·최신 원격 fetch·새 브랜치 생성은 미완료다.** 환경의 `.git` 읽기 전용과 네트워크 제한 때문에 별도 임시 클론/bundle로 대체 산출물을 만들었다. 완료 조건 전체를 달성했다고 보고하지 않는다.
- 기존 위험 회귀 2건 실패를 유지한다. 이미지 의존 26건(새 11·공급자 2·위험 13)은 생략이며 통과로 세지 않는다. 전체 회귀 통과가 아니다.
- pyflakes 미설치, OPA 실행 도구 없음으로 해당 검사는 미완료다. 실제 게이트웨이 모듈 import·PostgreSQL 잠금/경합·승인/등록 장애 복구·브라우저 렌더링은 미검증이다.
- 위키 검사 실패 3건은 main을 별도 추출한 기준판에서도 재현했다: `dev73-local-isolated-run.md`, `real-env-20261020/install/`, `real-env-20261020/e13/` 링크 대상 누락. 반려된 실행 문서나 실기기 증거를 새로 만들지 않았고 전체 위키 통과로 세지 않는다.
- 솔루션 스택 기동·배포·PJ1/실제 MCP·하네스 실행은 이번에 하지 않았다. 실기기 실행 표본 0, 독립 효과·복구 증거 없음.
- DB 승인과 파일 레지스트리 등록의 분산 원자성 한계, 공급자 자기 기술·키워드 기반 위험 제안의 한계는 10-20과 같다. DEV-73 재설계를 이 도입 화면에 새로 구현하지 않았다.
- 공통 지침에 따라 `status/current.md`는 변경하지 않았다. 백로그의 관련 3항목만 후보 상태·이번 보고로 연결했다.

## 다음 작업

1. 쓰기 가능한 통합 환경에서 원격 main을 다시 fetch하고 두 bundle의 prerequisite/내용을 확인한다. 원본 미커밋 33파일은 보존 commit과 SHA-256 대조 후 처리한다.
2. 메인이 D-187과 기존 기대값 충돌을 적대 검증한다. 채택 전 기존 시험 변경·전체 회귀 통과 표시는 하지 않는다.
3. DEV-73은 별도 수정·재검토를 거친다. 도입 후보는 기존 관리 실행 또는 원격 계약 범위에서 정상 이미지/OPA 검증 후 메인이 솔루션 기기 배포·PJ1 시험을 담당한다.

## 사용자에게 필요한 입력

업무 권한·실사용 데이터·새 자격 입력은 없다. 원본 클론의 Git 변경을 완료하려면 `.git` 쓰기가 가능한 실행 환경과 원격 main 조회가 필요하다. 현재 승인 정책상 권한 요청이나 자동 재실행은 할 수 없어 산출물과 제한을 함께 남긴다.

## 방향 제안

없음. 이번에는 10-20 제품 범위를 보존하고 반려된 의존성만 분리했다.
