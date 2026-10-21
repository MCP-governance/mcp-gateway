# 도입 승인 위험 시험 기대값 충돌 2건

- 비교 기준: `origin/main`의 로컬 확보 판본 `d3238dccd6a6fb7266a7b9201f5b133e2a025aea` → `10/21-intake-one-click-main` 후보.
- 기존 기대값의 도입 commit: `bbaa8c6a0142169249bdf0ccc45886aed64e4f13` (`feat(v2): DEV-71 도입 신청 위험 등급·영향평가 입력 패키지·기존 승인 유예 (D-143)`). 이 commit이 `risk_tier.py`와 `intake_risk_tier_check.py`를 함께 추가했다.
- 실제 재실행: [10-21 원시 결과](verification-2026-10-21.json)의 `risk_regression`. 25건 중 10 통과·2 실패·13 생략, 종료 코드 1. 생략은 FastAPI/게이트웨이 이미지 의존성 부재이며 통과가 아니다.
- 기존 Python·JavaScript 시험은 원본 main과 바이트 동일하다. 새 시험 3파일만 DEV-73 없는 경로에 맞게 조정했다. 기존 Rego 시험 본문은 보존하고 3사례를 뒤에 추가했다. 확인 결과는 [재배치 증거](rebase-evidence.json)에 있다.

## 충돌 1 — `RiskTierPureCheck.test_approval_method_per_tier`

### (a) 기존 기대값과 근거

`tests/intake_risk_tier_check.py:107`부터의 기존 시험은 다음을 요구한다.

| 호출 | 기존 기대 | 재배치 후보의 실제 값 |
| --- | --- | --- |
| `decide("high", 1, REASON)` | `approve` | `cosign` — 이번 실패가 발생한 첫 assert(114행) |
| `decide("very_high", 2, "")` | `refuse` | `approve` — 같은 시험의 앞 assert가 실패하므로 이 assert까지 진행하지 않음 |
| `decide("very_high", 1, REASON)` | `cosign` | `cosign` |
| `decide("very_high", 2, REASON)` | `approve` | `approve` |

`bbaa8c6`의 commit 본문과 D-143 ③·④는 높음에 **서로 다른 관리자 2명 또는 위험 수용 사유**, 매우 높음에 **2명과 사유**를 명시한다. `risk_tier.APPROVAL`의 `alternative`·`required`, `decide`의 사유 길이 분기가 이를 구현했다. 따라서 기존 시험은 기존 main 정책을 정확히 반영한다.

### (b) 새 동작과 근거

10-20 구현에서 작성된 [D-187](../../../../docs/ai/DECISIONS.md)은 높음/매우 높음 모두 다른 관리자 2명, 사유는 치명적 발견 수용에만 받는 것으로 D-143의 승인 방식 부분을 대체한다. [10-20 보고](../../status/reports/2026-10-20-intake-one-click.md)의 「승인 단계」「사유」「기존 시험 변경 필요」에도 같은 범위가 적혀 있다. 이번 S1 지시는 그 제품 동작 범위를 보존하도록 요청했다.

후보의 `risk_tier.APPROVAL`은 두 등급 모두 `approvers=2, reason="none"`이며 `decide`는 사유로 승인자 수를 대체하지 않는다. `approve_and_register`와 `core.register_server`도 사람 중복을 제거한 2인을 확인한다. 신청자와 같은 사람의 승인은 거부한다. 치명적 발견에는 기존 `review.accept_risk`의 10자 이상 사유·최대 30일과 `intake_gate`를 유지한다.

[MCP Tools 2025-11-25 공식 명세](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#user-interaction-model)는 사람이 도구 실행을 거부할 수 있어야 한다는 권고와 도구 표시/확인 UI를 설명한다. 같은 문서의 Tool 절은 annotations를 불신 자료로 취급하도록 요구한다. 2026-10-21 해당 본문을 다시 확인했다. **이 명세는 위험 등급별 승인자 수나 사유 의무를 정하지 않는다.** 두 관리자·치명적 발견 사유의 구체적 구분은 MINT의 D-187 정책 선택이며 국제 표준의 필수 요구처럼 주장하지 않는다.

### (c) 판단

이번 재배치의 목표 동작을 기준으로는 **새 동작이 정확하다**. 사유가 두 번째 사람을 대신하면 D-187의 독립 2인 승인과 등록 단계 검증이 서로 어긋난다. 등급만으로 사유를 요구하면 치명적 발견 수용과 위험 등급 승인을 다시 같은 절차로 합치게 된다. 다만 매우 높음의 비치명 사례에서 사유 의무를 없애는 것은 기존 정책의 변경이다. 이 변경을 보안 강화로만 표현하지 않는다.

기존 main 정책 회귀라는 기준에서는 기존 기대값이 정확하므로 이번 실패는 도구 오류나 단순 오타가 아니다. **D-187을 main 정책으로 채택할지와 기존 시험 수정은 적대 검증 후 메인이 결정한다.** S1은 기대값과 기존 AST를 수정하지 않으며 전체 회귀 통과를 주장하지 않는다.

### (d) 변경할 경우의 영향

| 영향 대상 | 확인할 내용 |
| --- | --- |
| 기존 `RiskTierApprovalCheck.test_high_tier_one_administrator_with_a_written_reason_completes_it` | 사유를 써도 1명은 승인 대기여야 하므로 기존 완료 기대와 충돌한다. 이번에는 이미지 의존성 때문에 생략됨 |
| 기존 `RiskTierApprovalCheck.test_very_high_tier_needs_the_reason_and_a_second_administrator` | 2인·사유 없음의 기존 거부 기대와 충돌한다. 치명적 발견이 없으면 승인 가능, 있을 때는 치명적 발견 수용을 별도로 검증해야 함. 이번에는 생략됨 |
| 기존 1인 낮음/보통, 높은 등급 첫 승인·동일인 재클릭·다른 2인, 입력 누락·수정·30일 유예/만료 시험 | 기대를 유지할 대상. 구현의 회귀가 없는지 정상 게이트웨이 이미지에서 확인 필요 |
| `risk_tier_gate`, `approve_and_register`, `core.register_server` | 개별 승인·통합 승인·등록의 규칙이 같아야 한다. `intake-cosign`, `intake-one-click`, `risk_assessment.approvers` 감사/증거를 연결해야 함 |
| `PAC-13`, `P-X-APPROVAL-001` | 별도 도구 호출의 요청 결속·독립 승인과 중요정보 고위험 실행 승인 정책이다. 도입 등급의 사유 대체 폐지를 이 정책 완화로 바꾸지 않는다 |
| `MCP-CATALOG-001`, `P-APPROVAL-EXPIRY-001` | 계약 변경과 기존 30일 유예/승인 기한은 유지한다. 새 정책 ID는 없음 |
| 치명적 발견 수용 | `review.intake_gate`의 `critical` 차단 항목과 `review.accept_risk`의 독립성·기한·사유를 유지한다. 도입 위험 등급만 보고 치명적 발견을 자동 수용하면 안 됨 |

## 충돌 2 — `RiskTierPureCheck.test_impact_package_maps_the_stated_input_to_assessment_items`

### (a) 기존 기대값과 근거

기존 시험 160행은 민감정보 외부 전송 입력의 패키지를 `("매우 높음", "관리자 2명 및 위험 수용 사유")`로 기대한다. 같은 `bbaa8c6`의 D-143과 `risk_tier.package`가 등급별 `APPROVAL`의 `reason="required"`를 읽어 표시한 결과다. 매우 높음 산정 자체와 2인 수는 양쪽에서 같다.

### (b) 새 동작과 근거

후보의 값은 `("매우 높음", "관리자 2명")`이다. D-187과 10-20 보고의 사유 분리 방침을 적용한다. 위 공식 MCP 명세는 영향평가 패키지 문구나 법정 평가 완료를 정하지 않는다. 이 패키지는 실제 위험 입력과 승인 방식을 옮겨 적는 자료이며 법적 영향평가의 수행·완료 증거가 아니다.

### (c) 판단

**D-187을 적용한 후보에서는 새 표시가 정확하다.** 실제 승인 함수가 사유를 요구하지 않는 경우 화면/보고서만 사유 필수라고 표시하면 사용자가 수행할 절차를 잘못 안내한다. D-143을 유지하기로 결정한다면 표시만 원복할 것이 아니라 충돌 1의 승인·등록 동작도 함께 맞춰야 한다. 기존 main 기준의 기대값은 그 판본에 맞으므로 그대로 보존한다.

### (d) 변경할 경우의 영향

- `risk_tier.package`, `/api/mcp-requests/{id}/report`의 `risk.package`, 콘솔 영향평가/통합 승인 화면의 표시가 같은 정책을 나타내야 한다.
- 충돌 1의 두 기존 API 시험도 함께 재검토해야 한다. 문구 시험 하나만 바꾸어 전체 승인 회귀가 해결됐다고 판단하면 안 된다.
- `risk_tier.assess`의 점수·최소 등급, 신청 입력 해시, 기존 승인 유예, 계약/기한 정책 ID는 바꾸지 않는다. 이 충돌 자체에는 새 OPA 정책 ID가 없다.

## WBS 불일치

DEV-68의 「필수 보증」, DEV-69의 「누락 시 기본 차단」이라는 기존 완료 조건과 D-185·186의 선택 입력/명시 활성 관할 팩은 다르다. DEV-71의 요약만으로 사유 대체 규칙의 채택 여부를 판단할 수 없다. 원래 완료 조건을 임의로 고치지 않았고, 이 후보의 범위와 기존 시험 실패를 보고한다. 새 정책 채택·시험 변경은 메인의 적대 검증 뒤 통합 사항이다.
