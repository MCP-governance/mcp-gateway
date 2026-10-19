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
