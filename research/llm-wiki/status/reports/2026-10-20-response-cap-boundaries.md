# 2026-10-20 DEV-54 응답 상한 경계 보강

- 작업자: Codex luna
- 코드 기준: `bac155a8b78222fc878ff642ea1aa177ddb82fba`, 시작 시 워킹 트리 clean, 브랜치 `10/20-response-cap-pg`
- 시작 근거: DEV-54 / WBS G03.06 / POL-35 / D-125, `analysis/response-cap-idempotency/README.md`, 기존 `tests/response_cap_idempotency_test.py`
- 해결할 문제와 완료 조건: 기존 시험의 경계 빈틈을 새 파일에서 보강하고 상한 초과 보류 및 실행 사실 유지, 정상 상한 통과를 로컬에서 확인한다. native parser·실제 MCP·기기 검수는 별도다.

## 결과

영향 경로를 확인했다. 요청 전 `classify.bulk_read_reason`이 알려진 전체 선택자, 일반 건수 매개변수, 단일 SELECT의 고정 SQL LIMIT을 검사한다. 응답 후 `core._guarded_result`가 원문 전체 UTF-8 JSON 바이트와 `classify.result_items` 건수를 검사하고, `_inspected_result`가 마스킹 뒤 표현에도 두 상한을 재검사한다. 응답 거부 경로는 `MCP-OUTPUT-001` Block, 결과 없음, `withheld`, `upstream_executed=true`로 기록한다. 기존 구현이 요구한 동작을 만족해 제품 코드는 변경하지 않았다.

새 `full_stack_lab/tests/response_cap_boundary_check.py`에 바이트·건수 정확 상한/+1, 한글 UTF-8 바이트, structured와 content 동시 크기, 중첩 배열, 마스킹 후 크기 증가, 대소문자·공백·glob 변형 및 실행/보류 결과 경로 확인을 추가했다. native PostgreSQL 문법은 주석·공백·대소문자 변형을 포함하고 모듈이 있을 때 실행한다.

PJ1 실제 MCP 절차(사람이 실행):

1. 솔루션 기기에서 `cd full_stack_lab && ./console.sh field up`으로 배포한다. 이 노트북에서 스택을 띄우지 않는다.
2. PJ1 관리형 하네스에서 실제 승인된 MarkItDown 서버/도구를 확인하고, 내용이 비민감하며 처리 허가된 작은 문서와 변환 응답이 262144바이트를 넘을 만한 큰 승인 문서를 준비한다. 별도의 mock MCP는 사용하지 않는다.
3. 같은 도구로 작은 문서를 먼저 변환해 정상 반환을 확인한다. 큰 문서는 변환을 요청하고, 원장 `decision=Block`, `policy_id=MCP-OUTPUT-001`, `upstream_executed=true`, `result=null`, `result_evidence.disposition=withheld`를 확인한다. 결과가 부분 반환되지 않는지도 확인한다.
4. 입력 문서 크기·도구/서버 판본·하네스·게이트웨이 판본·시간·원장 식별자를 기록한다. 문서 본문과 결과 본문은 증거에 복사하지 않는다. 큰 문서의 변환된 응답이 실제 설정 상한을 초과하지 않으면 더 큰 승인 문서로 재시도한다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적/함수 시험 | `python -X utf8 full_stack_lab/tests/response_cap_boundary_check.py` (2026-10-20, 로컬) | 통과 5, 건너뜀 1 (pglast 없음) | 명령 종료 출력 |
| 기존 회귀 | `python -X utf8 full_stack_lab/tests/response_cap_idempotency_test.py` | 12건 중 통과 8, 건너뜀 2, 오류 2. 기존 `guard()`의 AST namespace가 `_validate_output`을 제공하지 않아 두 성공 경계에서 `NameError` | 명령 종료 출력; 기존 시험은 변경하지 않음 |
| Python 문법 | `python -m py_compile` 새 경계 시험 및 기존 응답 시험 | 통과 | 명령 종료 코드 0 |
| pyflakes | CI 대상 Python 파일 일괄 검사 | 미실행: 이 PC의 Python에 `pyflakes` 모듈이 없음 | `No module named pyflakes` |
| JavaScript / 무인증 경로 | `node --check .../console.js`; `node --test .../console-state.test.mjs`; `python full_stack_lab/tests/open_endpoints.py` | 통과; JS 15건, 경로 검사 PASS | 명령 종료 코드 0 |
| 위협 매핑 | `python research/llm-wiki/tools/map_threats.py` | 통과, 24개 원천 정책 경로 확인; stale hash 2개가 기록되어 `catalogs/threats.json` 갱신 | 명령 출력·JSON 변경분 |
| 위키 CI 검사 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | `ok=true`, 오류 0; 무시 대상 로컬 원문 누락 경고 존재 | JSON 출력 |
| OPA | 지정한 일회성 컨테이너 시험 | 미실행: `docker` 실행 파일 없음 | PowerShell 명령 오류 |
| 실제 모델·하네스 / upstream 효과 | 솔루션 기기 배포 후 PJ1 MarkItDown | 미실행, 위 절차로 사람 검수 대기 | 없음 |

## 실패·미완료·한계

native pglast 문법은 모듈이 없어 실행하지 못했다. 기존 시험 파일은 수정하지 않았다. 기존 회귀에서 나온 두 오류는 그 시험의 AST 추출 helper가 `_guarded_result`의 `_validate_output` 의존성을 전달하지 않는 문제이며, 새 시험은 해당 helper를 명시적으로 제공한다. 시험은 AST로 제품 함수를 추출하고 대역 의존성을 연결하는 오프라인 함수 시험이며, 실제 MCP 응답이나 배포 효과를 증명하지 않는다. pyflakes와 OPA도 실행 도구 부재로 미검증이다. 위키 검사는 오류 0이지만 무시 대상 로컬 원문 누락 경고를 보고했다. 제한은 SDK가 응답을 받은 뒤 검사한다는 D-125의 범위와 같다.

## 다음 작업

DEV-54: 위 솔루션 기기 배포와 PJ1 MarkItDown 정상/초과 문서 실행을 수행하고 원장 판정 및 실행 사실을 대조한다. native parser 검증도 모듈 설치된 시험 환경에서 수행한다.

## 사용자에게 필요한 입력

없음. 실제 기기 검수는 담당자가 승인된 비민감 문서를 사용해 수행한다.
