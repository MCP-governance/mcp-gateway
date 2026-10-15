# 2026-10-13 결과 반환 경계 독립 검토

- 작업자: Codex 독립 검토 담당 enterprise_mapping
- 코드 기준: `ab6936c64f3578de8360b840f1928681714fa7bb` 이후 `10/13-enterprise-interoperability` 작업 트리. 아래 해시는 CRLF를 LF로 정규화한 SHA-256이다.
- 확인 범위: `core.py`의 dispatch·결과 검사·예외·감사 연결, `privacy.py`의 마스킹과 타입 유지, `mcp_facade.py`의 MCP SDK 반환, 결과 회귀 및 실제 검사기 시험의 단언·저장된 실행 증거.
- 제외: 기존 사용자 미커밋 파일 수정, 새로운 시험 작성, 스택 배포, PJ1 하네스 실행, 경쟁 제품 실행 비교. AST 목록만으로 전체 코드 감사 완료를 주장하지 않는다.

## 검토한 소스

아래 표는 2026-10-13 12:06 UTC에 결과 회귀 17개·실제 검사기 시험 5개와 대조한 최종 검토 스냅샷이다. 검사기 결과에 저장된 세 제품 소스 hash 및 각 시험 파일 hash와 일치한다. 작업 트리 검사본이며 배포본으로 해석하지 않는다.

| 파일 | 정규화 SHA-256 | 검토 심볼·행 |
| --- | --- | --- |
| `full_stack_lab/gateway/app/core.py` | `5bf0f17d55a6779e8632b6e8383cc7723909667d2a5bddfd4ce91db41a08fdba` | `_call_upstream` 1083–1168, `_root_cause` 1171–1176, `_decoded_strings` 1179–1190, `_upstream_failure` 1193–1201, `_guarded_result` 1204–1229, `_inspected_result` 1232–1243, `execute_call` 1433–1677 |
| `full_stack_lab/gateway/app/privacy.py` | `1fdbafb565c0d66ff39431732d3a6c461752cf0fccab6eecd7230569b9500370` | `mask_payload` 122–158와 실제 analyzer/anonymizer 오류 처리 |
| `full_stack_lab/gateway/app/mcp_facade.py` | `1dbd568cc05d491b65cc40ba6cc32d133b8da1a9d735a280a8a4f516fddc2e39` | `_render` 126–170 |
| `full_stack_lab/tests/mcp_result_contract_check.py` | `3a938e79bbefe789d8f6d31dc112695054edac32850623c236aae16698b6719a` | 17개 `test_*` 함수·단언, 25–180 |
| `full_stack_lab/tests/mcp_result_services_check.py` | `34c4deb615f20b2f86f90737ecafb6c66e1c20a414d79688e6a8b768fad7acc2` | 실제 Presidio·Gitleaks 단언 5개, 16–56 |

## 확인한 수정

| 조건 | 소스로 확인한 동작 | 검증 경계 |
| --- | --- | --- |
| 구조화 결과 보존 | `Allow`·`Alert`·`Restrict`이면서 `returned`·`masked`인 결과만 SDK `structuredContent`로 전달한다. text가 비면 같은 검사된 JSON으로 TextContent를 만든다. | SDK 객체·직렬화 회귀. 실제 LiteLLM→MCP 기업 업무 성공은 별도이다. |
| 보류 상태와 잔존 결과 | `_render`는 `Block`·`Approval`·`withheld`·`unknown` 결과를 반환하지 않는다. `_upstream_failure`도 잔존 result를 지우고 실행 상태에 맞는 disposition을 보존한다. | 단위 helper·SDK 반환 검증. 모든 ingress의 통합 오류 시험을 대체하지 않는다. |
| 구조·JSON 형식 | 객체가 아닌 structured 결과, 비문자 rich content, NaN·Inf를 보류한다. 공급자 임의 content type 값을 오류·감사 라벨에 복사하지 않는다. | 지원 범위를 text+JSON object로 명시한다. outputSchema 계약·검증은 별도 공백이다. |
| 개인정보 타입 유지 | 문자열은 Presidio로 마스킹한다. 키와 숫자는 일괄 분석하고 민감 식별자가 있으면 JSON schema를 바꾸지 않고 보류한다. 정상 count·id·boolean·empty 값 보존을 대조한다. | 실제 검사기 5개 시험의 좁은 합성 표본. 일반 숫자·한국어 전체 corpus의 정확도를 입증하지 않는다. |
| Secret·주입의 모든 문자열 경로 | `_decoded_strings`가 dictionary key/value와 list의 decoded 문자열을 함께 수집한다. Gitleaks는 마스킹 완료 JSON의 key/value 문맥과 decoded 문자열을 검사한다. | 자체 MCP 서버를 만들지 않았다. unit doubles는 배선 회귀이며 독립 제품 실행 증거가 아니다. |
| 전체 출력 검사 기한 | 유한 양수 설정의 기본 30초 안에서 검사기 대기·마스킹·Gitleaks를 수행하고 timeout은 실패로 보류한다. | 출력 비동기 검사 범위. 전체 요청·입력 검사 및 동기 CPU 작업의 강제 중단 보장은 별도이다. |
| 공급자 예외의 공개 값 | `_root_cause`는 예외 타입만 남기고 공급자·SDK message 값을 공개 MCP 오류와 감사 error에 복사하지 않는다. | 아래 자동 tracing 경계도 후속 소스에서 수정됐다. |

## 추가 발견

### RBR-01 · P0 · OpenTelemetry 자동 예외 기록

변경 전 `core.py`의 `start_as_current_span("mcp.upstream.call")`은 기본 옵션을 사용했다. 설치된 OpenTelemetry SDK의 `Tracer.start_as_current_span`과 `use_span` 구현을 직접 읽었다. 기본 `record_exception=True`, `set_status_on_exception=True`이며, 블록 밖으로 나온 예외를 원문 message와 status description으로 기록한다.

따라서 `execute_call`의 바깥 catch에서 정제한 RuntimeError를 별도로 기록해도, 내부 span에는 먼저 SDK/schema 예외 값이 남을 수 있었다. `mcp.gateway.call` 역시 최종 기록·분류 오류가 블록 밖으로 나가면 같은 문제가 있었다.

**최종 소스 확인:** 두 span 모두 `record_exception=False`, `set_status_on_exception=False`로 변경됐고 명시적으로 기록하는 예외도 정제된 RuntimeError로 바뀌었다. `test_gateway_span_does_not_automatically_export_exception_values` 137–152는 실제 OpenTelemetry in-memory exporter로 gateway span에 비밀 예시값이 자동 기록되지 않음을 검사한다. 저장된 17개 회귀 결과에서 통과를 확인했다. upstream span은 동일 옵션을 소스에서 확인했으며, 실제 공급자 오류와 원격 OTLP 수신을 이 독립 검토가 재실행한 것은 아니다.

증거: 로컬 선언 의존성 환경 `/tmp/mcpgw-metrics-venv-20261013`에서 `inspect.signature(Tracer.start_as_current_span)` 및 `inspect.getsource(use_span)` 확인. tracing collector에 실제 비밀을 보내거나 새 외부 호출을 실행하지 않았다.

### RBR-02 · P1 · 정상 응답 이후 teardown 오류의 실행 상태

변경 전 `_call_upstream`은 `client.call_tool`이 정상 응답을 반환한 뒤 payload를 구성하지만 `upstream_executed=True`는 호출자의 전체 return 이후에만 설정했다. 그 사이 MCP context teardown이 실패하면, 이미 정상 응답을 수신했어도 attempted=true/executed=false의 unknown으로 기록될 수 있었다.

**후속 소스 확인:** `client.call_tool`이 실제로 반환한 직후 `dispatch_state["upstream_executed"] = True`를 설정한다. 이후 teardown·검사 오류는 `_upstream_failure`에서 실행 확인을 유지하고 결과를 지운다. `call_tool` 내부에서 응답을 확정하지 못한 SDK 검증·통신 오류는 계속 unknown이다. 이 항목은 소스상 수정 확인이며 실제 MCP context teardown 장애 주입 실험의 통과를 주장하지 않는다.

### RBR-03 · P0 · 낮은 엔트로피의 자격과 탐지 entity 중첩

key와 value를 각각 검사하면 `password`·`client_secret` 등의 assignment 문맥이 사라지고, Gitleaks entropy 조건을 만족하지 않는 값이 지나갈 수 있었다. 문자열 key/value의 assignment 문맥을 실제 Presidio에 전달하는 보강을 확인했다.

추가 검토에서 `api_key`·`access_token`의 20자 이상 assignment는 `CREDENTIAL`과 더 높은 score의 `SECRET_TOKEN` recognizer가 중첩된다는 점을 지적했다. `CREDENTIAL`만 보류하면 다른 entity로 선택된 동일 자격을 놓칠 수 있었다. 최종 `privacy.py:142–143`은 두 entity를 모두 보류한다. 실제 검사기 `test_low_entropy_assignment_is_withheld_by_real_presidio` 51–56은 password·client_secret·api_key·access_token 네 합성 조건을 각각 실행하며 저장된 결과에서 통과했다. 모든 공급자 자격 형식·임의 길이·모든 entropy의 탐지를 일반화하지 않는다.

## 확인한 실행 증거

| 증거 | 저장된 결과 | 이 검토에서의 확인 수준 |
| --- | --- | --- |
| [단위·SDK 결과](2026-10-13-enterprise-unit-results.json) | 2026-10-13 12:06:34 UTC, 결과 회귀 17개·기존 보안 회귀 6개·LiteLLM 사전 검사 5개 exit 0 | 저장된 실행 출력·소스 hash·단언 대조. 이 검토 담당자가 재실행하지 않았다. |
| [실제 검사기 결과](2026-10-13-real-inspectors-results.json) | 2026-10-13 12:06:28 UTC, 솔루션 기기 격리 프로세스에서 실제 Presidio/Gitleaks 5개 exit 0 | `services_or_deployed_code_modified=false`, `actual_mcp_server_experiment=false`와 입력·검사 단언 확인. 제품 배포나 PJ1 MCP 실행으로 세지 않는다. |

수정 후에는 변경한 소스 hash에 맞는 회귀 결과와 보고를 다시 연결해야 한다. 위 증거는 표에 적힌 소스 상태의 결과이며 이후 변경을 자동으로 포함하지 않는다.

## 남은 공백

- 실제 상용/OSS MCP와 LiteLLM을 통과한 fresh PJ1 자연어 호출·독립 수신/효과·원복 증거.
- outputSchema의 관찰·사람 승인·잠금·반환 결과 검증, 미지원 image/audio/resource의 업무별 보안 계약.
- 한국어·다국어 정상/공격 corpus의 탐지·오탐·미탐·부하 지표.
- 전체 입력·요청 deadline, 동기 처리·프로세스 정지·크래시 durable intent와 서버별 실행 확인.
- 감사 request_payload/policy_input의 별도 민감정보 보존·암호화·접근·retention 검토.

## 사용자에게 필요한 입력

이 독립 소스 검토를 위해 필요한 추가 입력은 없음. 새로운 기업 연동 자격은 대화나 보고서에 값을 기록하지 않는다.
