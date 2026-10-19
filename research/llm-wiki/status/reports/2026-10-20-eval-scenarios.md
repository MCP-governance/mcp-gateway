# 2026-10-20 효과 평가 사례 확장

- 작업자: Claude Sonnet
- 브랜치: `10/20-eval-scenarios`
- 코드 기준: `c002fbd5fcf5f928e5ad68c57fa05edb1f76b1a6`(PR #35 병합), 시작 시 워킹 트리 깨끗함. 변경 파일은 `full_stack_lab/eval/scenarios/controls-2026-10-20.json`(신규), `full_stack_lab/eval/README.md`, 이 보고서, `status/backlog.md`의 DEV-65 상태 칸.
- 시작 근거: DEV-65(통제 적용 전후 효과 비교 평가 도구), [10-18 평가 도구 보고](2026-10-18-eval-tool.md)의 한계(사례가 14건뿐, 전송 목적지 결속과 공급자 호스팅 서버가 사례에 없음)
- 해결할 문제와 완료 조건: 평가 사례에 PAC-12 목적지·등급 결속, 공급자 호스팅 서버의 서버 간 전달, 열람 뒤 외부 전송 연쇄를 추가하고, 각 사례가 현재 Rego에서 기대대로 판정되는 근거를 남긴다. `--self-test`와 `load_cases` 검증이 통과해야 한다.

## 결과

`scenarios/controls-2026-10-20.json`에 10건(공격 6, 정상 4)을 추가했다. 형식은 기존 controls 파일과 같다. 세 입력(`baseline.json`의 `normal-employee-team-write`·`normal-public-read`·`normal-internal-mail`)에서 필요한 필드만 바꿨으며, 이 세 입력은 10-18 기기 실행에서 모두 `Allow`·`P-AUTHZ-ALLOW-001`이었다([before-after.json](../../analysis/controls-1018/before-after.json), 워크트리 `4857adc`, 반복 5회, 흔들림 없음). 이번 사례는 모두 새로 만든 입력이며 OPA 실행은 하지 못했다(아래 검증).

| 사례 id | 구분 | 바탕 입력에서 바꾼 것 | 기대 판정 | 근거 |
| --- | --- | --- | --- | --- |
| normal-transfer-pair-match | 정상 | pac: 전송 사용·목적지 `share.partner.example`, 최종 목적지 검증, 자료 등급 `nonimportant`, 심사 쌍 `(share.partner.example, nonimportant)` | Allow | 아래 A |
| attack-transfer-destination-not-approved | 공격 | 위와 같되 목적지·최종 목적지를 `mirror.other.example`로(심사 쌍은 그대로) | Block `PAC-12` | A |
| attack-transfer-grade-not-approved | 공격 | 심사 쌍 등급을 `public`으로(자료는 `nonimportant`) | Block `PAC-12` | A |
| attack-transfer-final-destination-unverified | 공격 | `facts.transfer.verified`·`final_destination_verified`를 false로 | Block `PAC-12` | A |
| attack-flow-provider-hosted-read-reviewed | 공격 | `tool.provider_hosted=true`, `accepts_from`·`request.flow_sources`에 같은 출처, 읽기 도구 | Block `P-FLOW-001` | B |
| attack-flow-provider-hosted-write-reviewed | 공격 | 위와 같되 쓰기 도구 | Block `P-FLOW-001` | B |
| normal-flow-provider-hosted-no-source | 정상 | `provider_hosted=true`, 열람 출처 없음 | Allow | B |
| normal-flow-reviewed-source-not-hosted | 정상 | `provider_hosted=false`, `accepts_from`과 출처 일치(쓰기 사례와 `provider_hosted` 하나만 다름) | Allow | B |
| attack-chain-external-send | 공격 | `sequence_flags=[sensitive_read_then_send]`, 외부 메일 수신자, 도구 행위 `x` | Block `P-CHAIN-001` | C |
| normal-chain-flag-internal-send | 정상 | 같은 `sequence_flags`, 수신자는 내부 메일(바탕 그대로) | Allow | C |

PAC 문서는 전송 사례 네 건에서 `request.id`·`reservation_request_id`도 사례 id로 바꿨다(두 값이 같아야 PAC-15를 통과한다). 정상 사례의 `expect`에는 `policy_id`를 두지 않았다(기존 사례와 같음).

### 판정 근거(Rego 읽기)

A. PAC-12(`opa/pac15.rego` 267~279행). `transfer.enabled == false`이면 통과하고, 켜져 있으면 `facts.transfer.verified`·`final_destination_verified`가 참이고, `final_destination_id`가 요청의 `destination_id`와 같고, `data_grade`가 `facts.data.grade`와 같고, `approval.transfer_pairs`에 `(destination_id, grade)`가 같은 쌍이 있어야 한다. 입력 계약(`base_valid`, 21행)은 `request.transfer.enabled == classification.transfer_required`를 요구하므로 사례마다 `transfer_required=true`로 맞췄다(빠지면 `INPUT_CONTRACT`로 막혀 PAC-12 사례가 아니게 된다).
- 정상: 네 조건과 쌍이 모두 맞아 PAC-12가 성립한다. 다른 PAC 규칙은 바탕 입력 그대로여서 `findings`가 비고 `has_permission`이 참이라 후보는 `P-AUTHZ-ALLOW-001`(140)뿐이다.
- 목적지 불일치: 쌍의 목적지가 최종 목적지와 달라 `some pair`가 실패한다. 등급 불일치: 쌍 등급 `public`이 `data_grade` `nonimportant`와 달라 실패한다(게이트웨이는 심사 등급 이하의 쌍만 만든다. `gateway/app/pac.py` 162·179행). 미검증: 쌍은 맞지만 `verified` 조건이 실패한다(게이트웨이는 `transfer_ok`로 두 값을 함께 채운다. 298행).
- 세 경우 모두 `deny["PAC-12"]`가 `findings`에 들어가 `policy.rego` 138~146행에서 `PAC-12` 후보(Block)가 된다. `has_permission`이 거짓이라 허용·제한 후보는 없고, 영향을 받는 다른 PAC 규칙이 없어 선택은 `PAC-12`(우선순위 75)다. 이번 편집은 `facts.transfer`·`transfer_pairs`·전송 사용 표시만 건드리며 이 값을 읽는 규칙은 PAC-12와 `base_valid`뿐이다(`approval_binding`의 `bound_destination_id`는 고위험 호출의 개별 승인 때만 평가된다).

B. 서버 간 전달(`opa/policy.rego` 72~87, 509~516행). `unapproved_flow`는 출처가 `accepts_from`에 없거나, 도구가 `provider_hosted == true`이면 출처마다 들어간다. 후보 `P-FLOW-001`(47)은 그 집합이 비어 있지 않을 때 성립한다. 공급자 호스팅이면 `accepts_from`에 출처가 있어도 막히고, 읽기·쓰기를 가리지 않는다. 같은 입력에서 `provider_hosted`만 false로 바꾸면 집합이 비어 `P-AUTHZ-ALLOW-001`만 남는다(정상 쓰기 사례가 대응 공격 쓰기 사례와 `provider_hosted` 한 필드만 다르다). 열람 출처가 없으면 공급자 호스팅이어도 집합이 비고, 개인정보 유형도 없어 `MCP-DATA-EGRESS-001`(490~493행)도 성립하지 않으므로 허용이다. 기존 `policy_test.rego`의 `test_provider_hosted_receiver_cannot_be_reviewed_into_taking_the_flow`·`test_provider_hosted_read_without_pii_is_not_an_egress_block`와 같은 방향이다.

C. 열람→반출 연쇄(497~505행). `P-CHAIN-001`(46)은 `external_transfer`(수신지 중 `external == true`가 있음)이고 `sequence_flags`에 `sensitive_read_then_send`가 있을 때 성립한다. 공격 사례는 외부 메일에 행위 `x`라서 `P-X-RESTRICT-001`(120, 제한 가능 항목 `journal_bcc`)도 후보지만 우선순위 46이 이겨 `P-CHAIN-001`이 선택된다. 자료 등급이 `nonimportant`·개인정보 없음이라 `MCP-DATA-EGRESS-001`(45)은 후보가 아니다. 정상 사례는 수신자가 내부라 `external_transfer`가 거짓이어서 `P-CHAIN-001`이 없고, 행위가 `w`라 `P-X-*`도 없어 `P-AUTHZ-ALLOW-001`만 남아 허용이다(기존 `test_read_then_internal_send_is_not_a_chain`과 같은 방향). 10-18 기기 실행에서 `attack-sensitive-read-then-send`가 같은 규칙으로 `P-CHAIN-001`에 막혔다.

### 예측(실행 전)

`--before d6679fd --after worktree`로 세 파일 24건(공격 15, 정상 9)을 돌리면, `d6679fd`에는 `P-FLOW-001`이 없으므로 공급자 호스팅 공격 두 건이 적용 전 `Allow`(미탐)이고 나머지 공격은 적용 전에도 막힌다. 공격 차단율은 적용 전 11/15(0.733), 적용 후 15/15, 정상 허용률은 9/9 유지, 기대 불일치 없음으로 예측한다. 측정값이 아니라 위 읽기에서 나온 값이다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 도구 자체 검사 | `python -X utf8 full_stack_lab/eval/before_after.py --self-test`(Python 3.12.10, 10-20) | 통과 | 출력 `self-test 통과` |
| 사례 파일 검증 | `load_cases`로 세 파일을 함께 읽음(라벨·`expect.decision`·`input` 객체·id 고유) | 통과, 24건(새 10건: 공격 6, 정상 4) | 터미널 출력 |
| 바탕 입력 대비 변경 필드 | 새 사례 입력을 바탕 입력과 필드 단위로 비교 | 위 표의 변경만 있음 | 터미널 출력 |
| 규칙 직접 읽기와 Python 재현 | `pac15.rego`·`policy.rego`의 해당 규칙을 읽고 PAC-12·`base_valid` 전송 조건·`unapproved_flow`·`P-CHAIN-001`·우선순위만 Python으로 옮겨 10건을 판정 | 10건 모두 위 기대와 일치 | 같은 사람이 읽고 옮긴 것이라 OPA 실행 증거가 아님 |
| 실제 OPA 평가 | `docker`·`opa` 명령 | 미실행: 이 PC에 둘 다 없음 | 결과 JSON·report 미생성 |
| `policy_test.rego` | 규칙을 바꾸지 않아 추가하지 않음 | 해당 없음 | |

## 실패·미완료·한계

- OPA를 돌리지 못해 새 10건의 실제 판정은 확인되지 않았다. 솔루션 기기에서 아래 명령으로 확인해야 하며, 기대와 다른 사례는 결과의 "적용 후 기대와 다른 사례"에 나온다.
- 전송 사례 네 건은 PAC 문서만 바꿨고 정책 입력의 `destinations`는 바탕 그대로 비어 있다. `policy.rego`가 PAC 문서와 `destinations`를 서로 대조하지 않으므로 이 사례는 PAC-12 규칙 자체를 시험하지, 게이트웨이 분류기가 같은 값을 만드는지(`transfer_binding` 결과)는 시험하지 않는다.
- 공급자 호스팅 사례도 PAC 문서와 도구 이름은 파일시스템 도구 그대로다. `policy.rego`가 `tool.server`·`tool.name`을 판정에 쓰지 않아 영향은 없지만 실제 원격 서버의 호출 모양은 아니다.
- 정상 사례의 `expect`에 `policy_id`를 넣지 않았다. 차단 사유 일치율은 공격 사례의 `expect.policy_id`만 센다.
- 지표 정의와 기대 판정·라벨은 여전히 팀 평가계획 확정 전 잠정안이다.

## 다음 작업

DEV-65: 솔루션 기기에서 다음을 실행해 `result.json`·`report.md`를 만들고, 위 예측과 다르면 사례 또는 정책을 점검한다.

```bash
python3 full_stack_lab/eval/before_after.py \
  --cases full_stack_lab/eval/scenarios/baseline.json \
          full_stack_lab/eval/scenarios/controls-2026-10-18.json \
          full_stack_lab/eval/scenarios/controls-2026-10-20.json \
  --before d6679fd --after worktree --out /tmp/eval-1020
```

## 사용자에게 필요한 입력

없음.
