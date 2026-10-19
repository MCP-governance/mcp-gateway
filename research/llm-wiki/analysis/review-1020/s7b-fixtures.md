# S7b 기존 시험 대역 보정 적대 검토

- 검토자: Codex luna
- 기준: `321fa5655261378c6900dafba9b87be3072448f4`, 브랜치 `10/20-output-contract-fixtures-review`
- 범위: `git show HEAD -- full_stack_lab/tests/`의 7개 변경 hunk. 제품 코드와 기존 assert는 수정하지 않았다.
- 결론: 7개 hunk 모두 A(채택). 기대값·검사 범위 감소는 발견하지 않았다. 출력 검사·렌더 대역은 이 시험들의 세션/실패 분류 목적에 한정한 대역이며 별도 출력 계약 시험이 해당 동작을 실제 함수로 검사한다.

## Hunk 판정

| Hunk | 판정 | 적대 검토와 근거 |
| --- | --- | --- |
| `dest_pin_credential_redaction_check.py:221` | A | `_upstream_failure`에서 새로 평가하는 `output_contract.WireRejected`·`OutputSchemaTooComplex` 타입 이름을 `selected()`가 실제 `output_contract.py` AST에서 추출한다. 나머지 테스트는 `DestinationBlocked`의 중첩 원인 → `Block/MCP-EGRESS-001`, 시도·실행 false를 그대로 assert한다. 타입만 제공하여 실패 분기를 우회하지 않는다. |
| `outcome_axes_check.py:160` | A | 같은 두 예외 클래스를 실제 모듈 AST에서 가져온다. 중첩 HTTP 429 원인의 `MCP-UPSTREAM-001` 및 결과 축의 제공자 한도 초과 기대값은 유지된다. 합성하는 것은 HTTP 상태 예외와 주변 서비스뿐이며 새 제품 예외 타입을 가짜로 정의하지 않았다. |
| `upstream_session_reuse_test.py:269` | A | `ContractClient`는 `upstream.py`의 실제 `ClassDef`를 `functions()`가 AST로 선택한다. 이 이름은 `_session` 반환 경로를 구성하기 위한 것이고 클래스 메서드를 대체하지 않는다. 기존 세션 재사용·회수 assert는 바뀌지 않았다. |
| `upstream_session_reuse_test.py:511` | A | `_render(outcome, protocol_version)`의 실제 두 인자 호출 형태를 받게 했다. 반환을 그대로 하는 대역은 이 시험의 대상인 오류 봉투와 `sessions.downstream` 문맥 초기화·복구만 분리한다. 판본별 출력 형식·실제 MCP 응답은 이 시험에서 assert하지 않으며 `mcp_result_contract_check.py`와 `output_contract_check.py`가 실제 렌더 함수를 검사한다. |
| `upstream_session_reuse_test.py:562-566` | A | `canonical_hash`, `approved_hash`, `matches`, `tool_hashes`, `review_matches`는 각각 실제 제품 AST 정의다. canonical null 해시는 실제 함수로 계산한다. 등록부의 `canonical_hash=lambda value: value`만 기존 입력/설명 해시 fixture의 표현을 보존한다. 실제 `review_matches`는 승인 출력 해시가 빠진 구 계약을 null 해시로 정규화하고 비교한다. 조건을 항상 참으로 만드는 대역이 아니다. |
| `upstream_session_reuse_test.py:572` | A | 기존 fake 등록부에 실제 `review_matches`를 연결한다. 그 함수가 비교할 `tool_hashes`는 실제 AST 함수이며 fixture 해시 관례와 null 출력 계약에 맞는 대역 입력을 쓴다. 계약 불일치 시 전송하지 않고 세션을 해제하는 기존 assert는 유지된다. |
| `upstream_session_reuse_test.py:582-583` | A | `output_contract` 네임스페이스의 `approved_hash`·`matches`는 실제 AST 함수, null 상수는 실제 canonical hash 결과다. `_guarded_result`는 결과값을 반환하는 인자 형태 대역이므로 이 dispatch 시험에서 출력 스키마 검증을 수행하지 않는다. 이 시험의 정상 호출은 세션 동일 연결·정책 재판정·원장 intent, 음성 호출은 철회·실패 차단·미전송과 재시도 범위가 목적이다. D-149 결과 검증 자체는 `output_contract_check.py`가 `_guarded_result`에 승인 스키마, 유효/무효 결과, 오류 결과 및 판본 변환을 넣어 직접 검사한다. 따라서 이 대역은 이 시험의 대상 범위를 축소하지 않으며 두 검증 책임은 분리되어 있다. |

## 기대값 및 범위 검사

- 커밋 diff는 대역/AST 이름공간 구성만 바꾸며 `assert`, `self.assert*`, 테스트 입력, 예상 정책 ID·결정, 호출 횟수 기대값 변경은 없다.
- 세션 시험의 중요한 음성 경로는 계약 변경·OPA 실패·종료/철회에서 SDK 호출이 없고 세션 해제가 이뤄지는지 검사한다. T10은 목록 조회만 한 번 재시도하고 도구 호출은 재시도하지 않으며 시도 상태를 보존하는지 검사한다.
- 출력 동작 전용 직접 검사 위치는 `full_stack_lab/tests/output_contract_check.py`의 승인 스키마 검증 및 `_guarded_result`, `_render` 판본별 검사와 `mcp_result_contract_check.py`다. 이 검토에서는 이 시험들을 실행하지 않았다.

## 검증 범위와 한계

검증은 HEAD diff, 관련 제품 AST 정의, 테스트 본문/assert 및 D-149 분석·결정 기록의 정적 대조다. 이 검토 턴에서 시험을 실행하지 않았고, SDK 이미지·실제 DB·MCP 서버·PJ1에서의 실행을 주장하지 않는다. 따라서 A는 이 세 시험의 의도된 범위와 대역 정확성에 대한 채택이며 출력 계약 전체의 런타임 적합성 승인은 아니다.
