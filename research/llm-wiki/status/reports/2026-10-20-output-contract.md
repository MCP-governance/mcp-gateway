# 2026-10-20 도구 출력 계약

- 작업자: Codex sol
- 코드 기준: 시작 `f6c3071535e5f49231cff5b43e140182779700ac`, `10/20-output-contract`. 시작 작업 트리 깨끗함. 커밋·푸시 없음, 아래 변경은 미커밋 작업 트리에 있음.
- 시작 근거: DEV-44 / RV-05, D-109 정정, [기존 검토](../../analysis/review-2026-10-15/README.md).
- 해결할 문제와 완료 조건: 출력 스키마도 사람의 승인 계약으로 잠그고, 승인 스키마로 검증한 구조화 결과를 협상 판본에 맞게 보존한다. 자동 승인·직원 토큰 전달·기존 시험 기대값 변경은 하지 않는다.

## 결과

`output_schema_sha256` 잠금 항목과 DB 출력 스키마/승인·관측 해시를 추가했다. 카탈로그 관찰·재승인, 도구 목록, 정책 계약, 같은 연결의 실행 직전 검사와 최종 전송 SQL에 연결했다. 출력 스키마 추가·변경·제거는 DRIFT이며 재승인 전 해당 도구 호출을 `MCP-CATALOG-001`로 차단한다. 출력 스키마 없는 기존 승인은 유지한다. 출력 스키마가 새로 관측되면 자동 채택하지 않는다.

공식 SDK 공개 요청 API와 기존 JSON Schema 검증기로 결과 수신/계약 검증을 분리했다. 원본과 마스킹 후 structuredContent가 승인 스키마와 맞지 않으면 기존 `MCP-OUTPUT-001`로 결과만 보류한다. 2025-06-18·2025-11-25는 객체, 2026-07-28은 배열·스칼라·명시적 null까지 보존한다. 현대 상위 서버의 비객체 값을 구형 하네스로 반환할 때는 검사된 JSON text로 보존한다. 출력 스키마와 호환되지 않는 구형 목록 광고는 생략한다.

변경 파일: `gateway/app/{output_contract,core,upstream,upstream_sessions,registry,dispatch,mcp_facade,main,selective}.py`, `gateway/app/v2_tables.sql`, `opa/policy_ledger.json`, 새 `tests/output_contract_check.py`, 잠금 비교 CLI `tests/contracts_check.py`, 기존 대역 보강 `tests/{catalog_refresh,dispatch_recheck,selective_restriction_siem}_check.py`(모두 `full_stack_lab/` 아래). 문서는 D-149·POLICY·DEV-44 상태 칸·이 보고와 [요구사항/출처 분석](../../analysis/output-contract-d149/README.md)이다. `status/current.md`와 두 계약 잠금 JSON은 변경하지 않았다.

## 검증

원본은 [validation.json](../../analysis/output-contract-d149/validation.json)에 명령·UTC 시각·종료 코드·출력을 저장했다. 다음은 Windows 샌드박스 Python 3.10에서 실제 실행했다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 출력 승인·전환·판본·전송 대역 | `python -X utf8 full_stack_lab/tests/output_contract_check.py --pure`, 2026-10-20 KST | 8개 통과. 실제 production 함수의 AST 추출 + DB/SDK AsyncMock | `pure-output-contract` |
| 기존 전송 경쟁/실패/취소 대역 | `python -X utf8 full_stack_lab/tests/dispatch_recheck_check.py` | 15개 통과. PostgreSQL 시험과 구분 | `dispatch-recheck` |
| 기존 선택적 제한·보안 관제 | `python -X utf8 full_stack_lab/tests/selective_restriction_siem_check.py` | 14개 통과 | `selective-siem` |
| 오프라인 계약 잠금 비교 | `python -X utf8 full_stack_lab/tests/contracts_check.py` | 기존 self-check 통과. 출력 해시의 구형 잠금 호환/변경은 새 시험에서 추가 검증 | `contract-lock-diff` |
| Python/JS 정적 구문 | 변경 Python 전체 `python -m py_compile`, `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | `python-compile`, `javascript-syntax` |
| 인증 라우트 검사 | `python -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과 | `route-auth` |
| 코드 정적 분석 | `python -m pyflakes ...` | 실행 실패: pyflakes 미설치 | `pyflakes` |
| 전체 출력 계약 시험 시작 | `python -X utf8 full_stack_lab/tests/output_contract_check.py` | import 단계 실패: Python 3.10에 datetime.UTC 없음. SDK/스키마 검증 시험 본문 미실행 | `gateway-full-output-contract` |
| 변경 공백 검사 | `git diff --check` | 통과 | `diff-whitespace` |

## 기존 시험 변경 필요

기대값 변경 필요 없음. 기존 DB/AST 대역에 새 출력 열·계약 helper·검사 인자만 보강했다. 기존 assert/기대 결과는 바꾸지 않았다. 전체 `catalog_refresh_check.py`와 `mcp_result_contract_check.py`는 게이트웨이 이미지에서 회귀 확인해야 한다.

## 실패·미완료·한계

새 시험 중 공식 SDK runner의 null 직렬화, JSON Schema 오류/참조/마스킹 후 검증과 수신 wire 위반의 정책 ID는 이미지에서 실행해야 한다. 실제 DB 전환·경쟁, 실제 공개 OSS MCP, PJ1 하네스의 양성/음성·판본 협상·쓰기 효과·복구는 미실행이다. 배포·정책 해시·오탐/미탐은 확인하지 않았다. Rego 규칙과 정책 ID/우선순위는 바꾸지 않아 OPA 시험은 수행하지 않았다. 기존 전체 위키 생성/스냅샷은 이 작업 범위를 넘어 갱신하지 않았다.

원격 HEAD 재확인 명령 `git ls-remote --symref origin HEAD`는 GitHub 443 연결 실패로 확인 불가였다. 기존 브랜치에서만 작업했다. 커밋 해시는 없으며 시작 커밋은 위와 같다.

## 다음 작업

DEV-44의 기기 검증. 사람은 솔루션 기기에서 현재 변경을 포함한 게이트웨이 이미지를 준비하고 `full_stack_lab`에서 다음을 실행한다. 이 명령은 별도 운영 스택이나 MCP 서버를 띄우지 않는 격리 단위 검사다.

```bash
for check in output_contract catalog_refresh mcp_result_contract dispatch_recheck selective_restriction_siem; do
  docker run --rm --network none -v "$PWD:/validation:ro" "$(docker compose images -q gateway)" \
    python "/validation/tests/${check}_check.py" || exit $?
done
```

그 뒤 소유자 순서대로 솔루션 기기의 `./console.sh field up` → PJ1 실제 하네스에서 승인 전 차단·승인 후 정상·스키마 변경·결과 불일치 보류·판본별 보존·재승인 복구를 원장과 상위 효과로 대조한다. 계약 잠금은 실제 도구 목록을 확인하고 사람이 diff를 읽어 커밋한다.

## 사용자에게 필요한 입력

없음. 실기기 실행·잠금 diff 검토·커밋은 지정된 후속 검증 범위로 남긴다.

## 기존 시험 대역 보정

- 작업자: Codex sol, 2026-10-20. 후속 시작 기준 `bb5583cdb383314fab9c91c5ebd7847fb9855a94`, 브랜치 `10/20-output-contract`, 시작 작업 트리 깨끗함. 위 최초 구현 보고는 당시 이력으로 보존한다. 이번 변경은 아래 세 시험·D-149 후속 결정·DEV-44 상태 칸·이 보고·실행 기록뿐이며 커밋하지 않았다.
- 완료 조건: 실패마다 제품 회귀와 대역 누락을 구별하고 기존 assert를 유지한 최소 보정안을 제시한다. 네 파일의 직접 실행 통과는 로컬 환경 제약으로 아직 충족하지 못했다.
- 근거: 현재 제품의 `core._call_upstream`/`_upstream_failure`, `upstream._session`/`ContractClient`, `registry.review_matches`, `mcp_facade.build_mcp`를 D-149 및 [출력 계약 분석](../../analysis/output-contract-d149/README.md)과 대조했다. 새 기능·의존성·외부 코드는 도입하지 않았다.

### 실패별 판정

| 실패 | 원인·판정 | 보정 후 관측 |
| --- | --- | --- |
| 세션 시험 `output_contract` NameError 8건 | AST는 `_call_upstream` 본문만 추출한다. 제품 모듈은 출력 계약을 import하지만 시험 전역에는 없다. 기존 입력/설명 계약이 일치한 다음 출력 계약 분기에서 실패한다. 대역 이름공간 누락이다. | 실제 `approved_hash`·`matches`를 추출하고 canonical null 해시를 제공하자 관련 시험 통과. 무조건 허용 대역을 쓰지 않는다. |
| `ContractClient` NameError 2건 | `_session`이 D-149의 공개 SDK 요청 어댑터로 client를 감싸지만 추출 목록은 옛 함수만 포함한다. 어댑터 도입은 승인 출력 검증/명시적 null 보존을 위한 의도된 변경이다. | 실제 클래스를 추출하자 연결 설정·내부 목적지 전달의 기존 검증 통과. 이 시험은 SDK 전송 본문 검증을 대신하지 않는다. |
| `_render` lambda 인자 TypeError | 제품 `build_mcp`는 협상 판본을 두 번째 인자로 전달한다. 반환 대역은 옛 한 인자만 받는다. | 판본 인자만 추가하고 기존 반환값 유지. 문맥 전달·오류 은닉·항상 문맥 초기화 기대값 모두 통과. |
| `ValueError: expired`가 보이는 예외 사슬 | 첫 목록 조회의 의도된 만료 예외 후 재연결은 수행되지만 두 번째 목록 검사에서 출력 계약 이름 누락으로 실패한다. 오류 사슬에서 처음 만료가 함께 보인 것이다. | 기존 T10 시험의 한 번만 목록 재시도·두 번째 목록 실패 중단·호출 실패 재시도 금지 검증 그대로 통과. |
| 최종 철회 시험 `release.await_count` 0 != 3 | 세 하위 경우 모두 출력 계약 NameError로 중단되어 `dispatch.record`와 `release_pool`까지 도달하지 못한 후속 실패다. 제품의 해제 동작 변경 근거가 아니다. | 기존 3회 기대값 그대로 통과. 종료 판정 `Block/MCP-DECOMM-001`과 상위 미전송도 그대로 확인. |
| 결과 축 `test_nested_http_status_survives_redaction` | `_upstream_failure`의 새 WireRejected/OutputSchemaTooComplex 타입 분기가 먼저 평가되나 출력 계약 모듈 이름이 없다. 대역 누락이다. | 실제 예외 클래스 제공 후 기존 `MCP-UPSTREAM-001`·제공자 한도 초과 기대값 통과. |
| 목적지 `test_egress_failure_has_correct_decision_even_in_cause` | 같은 새 예외 타입 분기의 이름공간 누락이다. 제품의 중첩 원인 순회와 목적지 차단은 유지된다. | HTTP 상태 예외 타입만 대역으로 제공한 실행에서 기존 `Block/MCP-EGRESS-001`, 실행·시도 false 확인. HTTPX 설치 환경의 직접 실행은 미확인. |
| 보정 후 드러나는 `registry.review_matches`·`_guarded_result` 의존성 | D-149의 구 잠금 호환 비교 helper와 판본/승인 스키마 인자가 기존 AST 전역/대역에 없다. 제품 시그니처 변경은 의도된 것이다. | 실제 등록부 비교 helper와 반환 대역 인자만 보강. 제품 코드 변경 없음. |

### 변경 행별 이유

행 번호는 이번 작업 트리 기준이다. 여러 줄로 된 추가 식은 각 줄의 역할을 모두 적었다. 기존 시험 파일의 assert·입력 자료·기대 결과는 변경하지 않았다.

| 파일·변경 행 | 이유 |
| --- | --- |
| `full_stack_lab/tests/upstream_session_reuse_test.py:269` | 추출 집합에 실제 `ContractClient` 클래스 추가. `_session`의 새 전역 이름을 해결한다. |
| 같은 파일 `511` | `_render` 반환 대역이 두 번째 협상 판본 인자를 받게 한다. 반환 동작은 그대로다. |
| 같은 파일 `562` | 실제 `contract.canonical_hash`를 추출하여 출력 계약에는 운영 코드와 같은 해시를 사용한다. |
| 같은 파일 `563` | 실제 `approved_hash`·`matches`를 추출해 속성 접근 가능한 이름공간을 만든다. |
| 같은 파일 `564` | 출력 비교 함수에 실제 canonical hash와 출력 스키마 부재의 null 해시를 주입한다. |
| 같은 파일 `565` | 실제 `registry.tool_hashes`·`review_matches`를 함께 추출한다. |
| 같은 파일 `566` | 기존 설명/입력 시험의 항등 해시 관례와 일치하도록 해당 등록부 이름공간만 항등 해시·null을 주입한다. |
| 같은 파일 `572` | 기존 `tool_hashes` 대역 동작을 유지하면서 새 등록부 속성을 추가할 수 있도록 닫는 괄호를 이동한다. |
| 같은 파일 `573` | 위에서 추출한 `review_matches`를 기존 registry 대역에 주입한다. 출력 해시 없는 구 검토 입력을 보존한다. |
| 같은 파일 `582` | 기존 `dispatch`·`asyncio` 항목은 유지하고 새 전역/호출 대역 항목을 다음 줄로 분리한다. |
| 같은 파일 `583` | 출력 계약 전역을 주입하고 `_guarded_result` 반환 대역에 판본·스키마 인자를 추가한다. 기존 반환값은 유지한다. |
| `full_stack_lab/tests/outcome_axes_check.py:160` | 실제 `WireRejected`·`OutputSchemaTooComplex` 클래스만 추출해 `_upstream_failure`의 타입 분기를 정상 평가한다. |
| `full_stack_lab/tests/dest_pin_credential_redaction_check.py:221` | 같은 실제 예외 클래스 이름공간을 목적지 실패 시험에 주입한다. |

### 검증

[후속 실행 원본](../../analysis/output-contract-d149/test-double-validation.json)에 HEAD 원본을 메모리에서 실행한 실패와 보정본 실행, 명령·UTC 시각·종료 코드·stdout/stderr·소스 해시를 저장했다. 기본 환경은 Windows Python 3.10이다. HTTP 대역 실행과 직접 실행을 구분한다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 재현 | HEAD의 세 시험을 원래 `__file__`로 메모리 실행, 2026-10-20 KST | 세션 40건 중 1 failure/11 errors, 결과 축 8건 중 1 error, 목적지 16건 중 1 error. 목적지에는 HTTPStatusError 타입 대역만 제공 | `baseline-*` |
| 세션 | `python -X utf8 full_stack_lab/tests/upstream_session_reuse_test.py`와 같은 소스 실행 | 40건 통과 | `corrected-upstream_session_reuse_test.py` |
| 결과 축 | `python -X utf8 full_stack_lab/tests/outcome_axes_check.py`와 같은 소스 실행 | 8건 통과 | `corrected-outcome_axes_check.py` |
| 목적지·자격정보 HTTP 타입 대역 | 기존 시험 소스 전체 실행, HTTPX 대신 HTTPStatusError 예외 타입만 임시 제공 | 16건 통과. 파일·assert 수정 없음, 실제 HTTPX 통합 증거 아님 | `corrected-dest_pin_credential_redaction_check.py`의 정확한 실행 명령 |
| 목적지 직접 실행 | `python -X utf8 full_stack_lab/tests/dest_pin_credential_redaction_check.py` | 시작 실패: HTTPX 미설치 | 해당 직접 명령 |
| 출력 계약 전체 | `python -X utf8 full_stack_lab/tests/output_contract_check.py` | 시작 실패: Python 3.10에 datetime.UTC 없음. 본문 미실행 | 해당 직접 명령 |
| 출력 계약 순수 | `python -X utf8 full_stack_lab/tests/output_contract_check.py --pure` | 9건 통과 | 해당 명령 |
| 기대값 불변 | HEAD와 작업 트리의 `ast.Assert`·`assert*` 호출 AST 비교 | 세션 120·결과 축 30·목적지 70개, 총 220개 완전 동일 | `assertions_unchanged: true` |
| 정적 구문 | 변경 세 Python 파일 `python -m py_compile`, 콘솔 `node --check` | 통과 | 해당 명령 |
| 변경 공백 | `git diff --check` | 통과 | 해당 명령 |

### 기존 시험 변경 필요 여부와 남은 한계

기존 기대값 변경 필요 없음. 이번 변경안은 이름공간·대역 인자 보정만이며 Codex luna의 적대 검증은 미실행이다. 제품 회귀로 판정한 실패는 없다. 이 결론은 위 실패와 실행한 경로에 한정하며 S7 전체 품질을 뜻하지 않는다.

로컬 기본 Python은 3.10이며 HTTPX가 없다. 발견한 별도 로컬 Python 3.12에도 HTTPX·MCP·psycopg·pglast·jsonschema가 없었다. 저장소 내 임시 의존성 경로를 대상으로 고정 HTTPX 0.28.1 설치를 시도했으나 `No matching distribution found`로 확보하지 못했다. WSL 조회는 접근 거부였다. 시스템 Python·저장소 의존성·시험의 생략 조건을 바꾸지 않았다. 따라서 사용자가 요구한 **네 파일 모두의 직접 실행 통과는 미완료**이며 아래 이미지 실행이 필요하다. 로컬 스택·배포·DB·실제 MCP·PJ1 시험은 미실행이다. `status/current.md`는 사용자 지시대로 유지했다. 원격 HEAD는 GitHub 443 연결 실패로 확인하지 못했다.

사람은 솔루션 기기의 현재 변경을 포함한 이미지에서 다음을 실행한다(`full_stack_lab` 기준, 자체 MCP·스택 기동 없음).

```bash
image=$(docker compose images -q gateway)
for file in upstream_session_reuse_test.py outcome_axes_check.py dest_pin_credential_redaction_check.py output_contract_check.py; do
  docker run --rm --network none -v "$PWD:/validation:ro" "$image" \
    python -X utf8 "/validation/tests/$file" || exit $?
done
```

사용자에게 필요한 추가 입력: 없음. 후속 범위는 luna 검토·기기 이미지 직접 실행·사람의 커밋이다.
