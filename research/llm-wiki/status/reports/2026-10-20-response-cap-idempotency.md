# 2026-10-20 response cap 멱등성 시험 대역 보정

- 작업자: Codex luna
- 코드 기준: `bac155a8b78222fc878ff642ea1aa177ddb82fba`, 브랜치 `10/20-response-cap-pg`; 시작 시 dirty. 기존 D-155 문서·위협목록과 `response_cap_boundary_check.py`는 유지.
- 시작 근거: DEV-44, D-149, `full_stack_lab/tests/response_cap_idempotency_test.py`
- 해결할 문제와 완료 조건: 기기 게이트웨이 이미지에서 발생한 두 `NameError`를 시험 AST 이름공간에 실제 출력 검증 정의와 그 의존성으로 해결한다. 기존 assert는 바꾸지 않는다.

## 결과

`guard()`가 `core.py`의 `_validate_output`과 실제 `output_contract.py`의 프로토콜·스키마 경계 함수/상수를 AST로 추출한다. `jsonschema`·`referencing`이 설치된 게이트웨이 이미지에서는 해당 검증 의존성도 연결하고, 로컬에 없을 때 스키마 없는 기존 response-cap 검사는 계속 실행되도록 선택 import했다. 제품 코드, 정책, DB, 라우트, 정책 ID는 변경하지 않았다.

DEV-44 backlog의 마지막 상태 칸만 `시험 대역 보정 완료; 게이트웨이 이미지·PJ1 시험 대기`로 바꿨다. 현재 현황 파일은 수정하지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 단위 시험 | `cd full_stack_lab && python -X utf8 -m unittest discover -s tests -p response_cap_idempotency_test.py -v` | 10건 통과, 2건 skip (총 12건) | 로컬 Python 3.10 출력; `pglast`, `cryptography` 미설치 |
| 적대 검증 | Codex sol, 변경 시험 대역·assert·보고서 검토 | 대역 의존성·assert 불변 확인; 시험 집계 표기를 정정 | Codex sol 검토 결과 |
| 정적 검사 | `python -m py_compile tests/response_cap_idempotency_test.py` | 통과 | 로컬 Python 3.10 |
| 정적 검사 | `node --check gateway/app/agent_static/console.js` | 통과 | 로컬 Node |
| 회귀 | `node --test tests/console-state.test.mjs` | 15건 통과 | 로컬 Node |
| 정적 검사 | `python tests/open_endpoints.py` (`python3` 별칭 없음) | 통과 | 84개 라우트 점검 |
| 정적 검사 | `python -m pyflakes gateway/app/*.py tests/*.py supply_chain/*.py ../endpoint-agent/*.py field/pc/mcpgw_pc.py` | 미실행 | `pyflakes` 모듈 없음 |
| 위키 검사 | `python -X utf8 research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 오류 0; ignored local source 누락 경고 | 검사 JSON 출력 |
| 이미지·하네스 | 게이트웨이 이미지 및 PJ1 | 미실행 | 기기 담당자 실행 대기 |

## 실패·미완료·한계

로컬 시험에서 전체 12개 중 10개 실행 통과, `cryptography` 서명 저장소 시험과 `pglast` 네이티브 SQL 시험은 환경상 skip이다. `pyflakes`는 설치되지 않아 CI 동등 검사가 미완료다. 위키 검사는 오류 없이 끝났으나 ignored local source 누락 경고가 있다. 실기기 이미지에서 원래의 두 오류가 사라지는지와 PJ1 기능 확인은 아직 확인되지 않았다. 원격 HEAD 조회는 네트워크 연결 실패로 확인하지 못했다. 커밋하지 않았다.

## 다음 작업

기기 게이트웨이 이미지에서 `python -m unittest discover -s tests -p response_cap_idempotency_test.py -v`를 실행하고 PJ1 실제 하네스 확인 결과를 DEV-44에 연결한다.

## 사용자에게 필요한 입력

없음. 게이트웨이 이미지와 PJ1 시험은 소유자 규칙에 따라 기기 담당자가 실행한다.

## 기존 시험 대역 보정

- `guard()`의 AST 선택 목록에 `_validate_output`을 추가했다. D-149 이후 `_guarded_result()`가 이 검증을 직접 호출하는데, 기존 시험 namespace에 정의가 없어 이미지에서 12건 중 2건이 `NameError`로 끝났다.
- `output_contract.py`에서 필요한 `check_schema_bounds`, `for_protocol`, 프로토콜 상수, 크기 상한, `OutputSchemaTooComplex`를 AST로 추출하고 `math`를 제공했다. 호출되는 실제 함수가 기대한 계약 동작을 수행하게 연결했다.
- `_validate_output`이 참조하는 `Draft202012Validator`, `validator_for`, `Registry`를 namespace에 넣었다. 로컬에는 이 패키지가 없으므로 선택 import로 처리했다. schema 없는 response-cap 검사는 검증자 인스턴스를 참조하지 않아 로컬에서도 실행된다. schema 검증은 게이트웨이 이미지 의존성으로 확인해야 한다.
- 기존 시험의 기대값과 assert는 수정하지 않았다. 실제 변경은 import 7줄과 `guard()` AST 추출·namespace 연결이다.
