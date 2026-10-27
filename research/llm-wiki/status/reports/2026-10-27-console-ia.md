# 2026-10-27 콘솔 메뉴 통합

- 작업자: Codex
- 코드 기준: `10/27-console-ia`, 시작 `5add6ed35184bc091aafa4d51b88a5e9dfb4ae7c`. 시작 시 추적 파일 변경 없음. 기존 미추적 지시 파일·실행 로그는 보존했다.
- 시작 근거: 소유자 확정 작업 지시 `BRIEF-console-ia.md`, D-265, DEV-93.
- 완료 조건: 관리자 메뉴 9개와 직원·협력사 4개, 관리자 탭 분리, 기존 주소·필터·배지·데이터·갱신 훅 유지.

## 결과

승인 대기에 이용 동의, 호출·감사 기록에 감사 원장·사고 보고 기한·보안 관제 전달, MCP 서버에 MCP·커넥터·미등록·잔존·벤더 커넥터, 사용자·엔드포인트에 통제 점검과 MCP 설정, 도입 신청에 공급망 영향을 통합했다. 직원은 호출 기록·이용 동의·도입 신청·내 연결을 유지한다. 관리자 탭을 구성하기 전에 `viewer.admin`을 확인한다.

기존 API·HTML 이스케이프·탭 구성을 재사용했다. 변경 대상은 `agent_static/console.js`, `agent_service.py`의 역할별 메뉴 목록, `i18n-en.mjs`, 신규 `console-ia.test.mjs`, 공급망 페이지 검사를 담은 `sbom_impact_check.py`, 변경 기록·화면 정본·결정·현황·백로그·이 보고서다. 서버 측 API 인가·업무 정책·Git 접근 코드는 변경하지 않았다. 새 의존성·탭 프레임워크를 도입하지 않았다.

기존 감사·통제 범위·공급망·관리자 동의 주소를 새 탭으로 옮기며 쿼리를 보존한다. 직원의 이용 동의 주소는 유지한다. 엔드포인트 MCP 설정은 전체 목록과 미등록·잔존 목록의 다음 페이지 범위를 구분한다. 탭은 상위 화면에서 데이터를 함께 읽으며 기존 `after`와 타이머를 유지한다. 공급망 영향과 새 신청 폼은 도입 신청 자동 갱신에서 제외한다.

## 검증

2026-10-27 KST, 로컬 Windows에서 실행했다. VM·컨테이너·솔루션 스택은 띄우지 않았다. 아래 시험의 API 응답·DOM 객체는 단위 대역이며 실제 MCP 증거가 아니다.

| 확인 종류 | 명령 | 결과 |
| --- | --- | --- |
| JavaScript 문법 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 |
| 콘솔 회귀 | `node --test full_stack_lab/tests/*.mjs` | 88건 통과, 실패·생략 0. 신규 8건 포함 |
| 무인증 라우트 대조 | `python -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과. 무인증 1·인증 필요 103 |
| 배포 묶음 위생 | `python -X utf8 deploy/check.py` | 통과 |
| 화면 문구 | `python -X utf8 full_stack_lab/tests/console_copy_check.py` | 문제 0 |
| 공급망 UI·인가 회귀 | `python -X utf8 full_stack_lab/tests/sbom_impact_check.py` | 8건 통과 |
| 기존 콘솔 연동 회귀 | `python -X utf8 full_stack_lab/tests/dev73_review2_check.py` | 5건 통과 |
| Python 문법 | 변경 Python 2개를 `compile()`로 검사 | 통과 |
| CI 시험 연결 목록 | `python -X utf8 full_stack_lab/tests/run_local_suite.py --inventory` | 고아 0. 신규 Node 시험도 기존 CI glob에 포함 |
| 문서 ID 추적 | `python -X utf8 research/llm-wiki/tools/check_trace.py --no-fetch` | 오류 0, 경고 5 |
| 위키 파일·해시 | `python -X utf8 research/llm-wiki/tools/check_wiki.py` | 실패: 기존 로컬 원본 provenance 파일 누락, `agent_service.py`·`local_jobs.py` 매핑 해시 미동기화. 이번 메뉴 변경도 `agent_service.py` 해시에 영향 |
| 기업 분석 해시 | `python -X utf8 research/llm-wiki/tools/check_enterprise_analysis.py` | 실패: 이번에 변경하지 않은 `compose.yaml`·`console.sh`의 기존 해시 불일치 |
| 추가 이벤트 라벨 검사 | `python -X utf8 full_stack_lab/tests/event_kind_labels_check.py` | 실패: `local-source-download` 라벨 1개 누락. 시작 커밋의 동일 누락을 별도 대조 |
| Python 린트 | `python -m pyflakes ...` | 실행 불가: 모듈 미설치 |
| 프로토콜·실제 모델/하네스·upstream 효과·브라우저·배포 | 실행하지 않음 | 미검증 |

## 실패·미완료·한계

필수 제품 검사는 통과했다. 추가 이벤트 라벨 검사의 기존 실패와 위키 파일·분석 해시 실패를 전체 검사 통과로 계산하지 않았다. pyflakes도 통과로 계산하지 않았다. 작업 범위에 없는 이벤트 종류·API는 수정하지 않았다. 생성물 재생성 금지에 따라 위키 매핑 해시는 고치지 않았다.

`git ls-remote --symref origin HEAD`는 네트워크 연결 실패로 완료하지 못했다. 기존 지정 브랜치를 유지했고 push·병합하지 않았다. 위키 생성물·결정 색인 재생성은 지시대로 생략했다. 이 보고서는 구현·로컬 회귀 결과이며 배포 완료가 아니다.

로컬 `git add`와 `git commit`은 공용 Git 관리 디렉터리의 `.git/worktrees/ks-ui/index.lock` 생성이 `Permission denied`로 거부되어 실패했다. 해당 lock 파일은 존재하지 않았으며 임의 삭제·권한 변경은 하지 않았다. 스테이징된 파일·새 커밋은 없고 HEAD는 시작 커밋 `5add6ed35184bc091aafa4d51b88a5e9dfb4ae7c`다. 수정 파일은 워크트리에 남아 있다. 커밋은 미완료다.

## 다음 작업

DEV-93의 브라우저 검수: 관리자 9개 메뉴와 직원·협력사 4개 메뉴, 통합 탭 전환·옛 즐겨찾기·검색·더 보기·실시간 로그·새 신청 폼을 확인한다. 이후 기존 운영 절차에 따라 솔루션 기기에 배포하고 지정 시험 PC에서 확인한다. 기존 이벤트 라벨 누락과 CI pyflakes 결과도 통합 단계에서 확인한다.

## 사용자에게 필요한 입력

없음. 이번 지시는 로컬 구현·검사·커밋까지다.
