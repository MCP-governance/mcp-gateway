# 도입 위험 등급의 승인 방식 — D-143 대 D-187 판단 (D-189)

- 판단자: 메인(통합 담당). 2026-10-21.
- 입력: Codex sol의 기대값 충돌 분석(`analysis/intake-one-click/risk-expectation-conflict.md`, 도입 한 화면 승인 브랜치), `docs/ai/DECISIONS.md`의 D-143·D-187, [root 단독 운영](../root-solo/README.md)(D-188), `AGENTS.md`의 「계약 승인은 사람이」 불변식.
- 판단 기준(소유자 10-21 지시): 정확성 > 편의성 > 작업 효율성.

## 충돌

| | 높음 | 매우 높음 |
| --- | --- | --- |
| D-143 (현재 main) | 다른 관리자 2명 **또는** 위험 수용 사유(1명으로 가능) | 2명 **과** 사유 |
| D-187 (도입 한 화면 승인 후보) | 다른 관리자 2명 필수 | 2명 필수, 사유는 치명적 발견 수용에만 |

## 결론 — 어느 쪽도 그대로 채택하지 않는다

1. **높음: 다른 관리자 2명 필수.** D-143의 "1명 + 서면 사유" 대안을 **폐지**한다(D-187 채택).
2. **매우 높음: 다른 관리자 2명 필수 + 서면 사유 유지.** D-187의 사유 폐지는 **채택하지 않는다**(D-143 유지).
3. 치명적 발견 수용은 `review.accept_risk`의 별도 절차로 남는다. 위험 등급 승인이 이를 대체하지 않는다.

## 근거

- **사유는 사람을 대체할 수 없다.** 한 사람이 글을 써서 "다른 관리자 2명"을 충족한 것으로 기록하면, 원장과 화면이 실제로 없었던 독립 2인 통제를 있었다고 말한다. 측정·기록의 정확성 문제이며, 같은 이유로 root 단독 운영(D-188)에서도 승인자 수를 부풀리지 않기로 했다. 두 판단은 같은 원칙이어야 한다.
- **사유 의무와 2인 요건은 서로 다른 통제다.** 하나가 다른 하나를 대체하지 않으므로, 2인을 필수로 올리는 것이 매우 높음의 서면 사유를 없앨 근거가 되지 않는다. D-187은 이 둘을 한 변경으로 묶어 가장 높은 등급의 기록 의무를 줄였다.
- **공식 명세는 이 수치를 정하지 않는다.** MCP Tools 명세는 사람의 거부 가능성과 annotations 불신만 요구하고 등급별 승인자 수·사유 의무를 정하지 않는다. 이 선택은 MINT의 정책이며 국제 표준의 필수 요구로 적지 않는다.

## 편의에 미치는 영향 (소유자 확인 필요 사항)

높음 이상 등급은 이제 **두 번째 관리자 계정이 반드시 필요하다**. 개발자 1인 운영에서 root 혼자 높음 등급 도입을 승인하던 경로(D-143 대안)가 없어진다.
대체 경로는 D-188과 함께 들어온 `./console.sh field add-account`로 두 번째 관리자 계정을 만들어 승인하는 것이다. 1인이 2인 통제를 충족한다고 기록하는 경로는 복원하지 않는다.
낮음·보통 등급은 그대로 관리자 1명으로 처리된다.

## 구현·검증 조건

- `risk_tier.APPROVAL`은 `high`·`very_high` 모두 `approvers=2`, `very_high`만 `reason="required"`, `high`는 `reason="none"`.
- `decide`는 사유로 승인자 수를 대체하지 않는다. `package`의 표시 문구가 실제 승인 함수와 같아야 한다.
- **기존 시험 기대값 변경 대상**: `test_approval_method_per_tier`, `test_impact_package_maps_the_stated_input_to_assessment_items`, `test_high_tier_one_administrator_with_a_written_reason_completes_it`, `test_very_high_tier_needs_the_reason_and_a_second_administrator`. 이 변경은 **Codex luna 적대 검증을 통과한 뒤에만** 병합한다.
- `risk_tier_gate`·`approve_and_register`·`core.register_server`의 규칙이 서로 같은지, `intake-cosign`·`risk_assessment.approvers` 증거가 이어지는지 확인한다.
- `PAC-13`·`P-X-APPROVAL-001`·`MCP-CATALOG-001`·`P-APPROVAL-EXPIRY-001`은 바꾸지 않는다. 새 정책 ID는 없다.
