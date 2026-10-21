미커밋
# D-189 도입 승인 변경 적대 검증

## 기준과 실행 범위

- 비교 기준: `origin/main` = `4c22360d2ee7a879196e2990befc31433132d78b`, 대상 `d189-target` = `eb71d5194018716a4e966507d674ebfe7e05e873`. `origin/10/21-intake-d189`도 같은 대상 SHA다. 현재 `HEAD`는 `origin/main`이며 체크아웃·브랜치 변경은 하지 않았다.
- 수행: 위키 지침·현재 상태·D-189 판단 및 구현 보고를 읽었다. `git diff origin/main origin/10/21-intake-d189 -- '*/tests/*'`와 동등 SHA인 `d189-target`의 전체 테스트 diff, 제품 코드 diff, `git show`·`git grep`, 정책 ID 집합 비교를 확인했다. `git diff --check`는 종료 코드 0, 출력 없음이다.
- 미실행: Python·Node·OPA 시험, DB/게이트웨이, 솔루션 기기 배포, PJ1 하네스. 대상 ref를 체크아웃하거나 임시 복사본을 만들지 않았으므로 구현자의 과거 시험 결과를 이번 실행 결과로 세지 않았다.

## 판정

**C — 반려.** D-189 승인 판정 규칙은 여섯 경로에서 서로 맞고 기대값 변경도 정당하다. 그러나 대상 diff가 현재 기준에 있던 D-176 자동 중지와 SBOM 영향 조회 기능을 제거하고, 세 기존 회귀시험 파일도 삭제한다. 추가로 보류 판정은 차단 사유가 있는 불완전 제안에서 목록 표시가 다시 등급으로 바뀌는 경로가 있다. 이 상태는 D-189 변경만의 병합으로 승인할 수 없다.

## 1. 기존 시험 기대값 diff 전체

기존 시험 파일 중 내용이 바뀐 것은 `intake_risk_tier_check.py`, `root_solo_check.py`, `supplier_assurance_check.py` 세 개다. diff에서 실제 기대값을 바꾼 다섯 시험 메서드는 아래와 같다. 모두 구현 보고서의 두 표에 기록되어 있으며, 이 다섯 건 외에 기존 단언의 변경은 찾지 못했다.

| 시험과 근거 | 변경 전 → 변경 후 | 고정하던 통제 | 판정 |
| --- | --- | --- | --- |
| `full_stack_lab/tests/intake_risk_tier_check.py:114` `test_approval_method_per_tier` | 높음·승인자 1명·사유 있음: `approve` → `cosign` | 사유가 두 번째 관리자를 대신하지 못함 | **정당함** — D-189의 높음 2인 필수와 일치 |
| `full_stack_lab/tests/intake_risk_tier_check.py:235` `test_high_tier_one_administrator_with_a_written_reason_does_not_complete_it` | 한 사람의 완료 응답 → 대기, 전환 없음, 1차 승인 사건 기록 | 한 화면 승인도 두 번째 사람 전에는 등록하지 않음 | **정당함** — 코드가 `risk_tier.decide`를 사용 |
| `full_stack_lab/tests/root_solo_check.py:51` `test_risk_tier_still_requires_second_approver_where_required` | 단독 운영에서 높음·사유 있음: `approve` → `cosign` | root 단독 설정으로 승인자 수를 부풀리지 않음 | **정당함** — D-188과 D-189의 대체 관계에 맞음 |
| `full_stack_lab/tests/supplier_assurance_check.py:61` `test_approval_endpoint_holds_when_assurance_is_missing` | 공급자 법인명·취약점 정책 누락 메시지 → 두 누락 메시지 없음, 다음 검증 관문 메시지 | 공급자 보증 선택 입력; 누락만으로 승인 보류하지 않음 | **정당함** — D-185와 추가 판단 3의 조건부 선택 입력에 맞음 |
| `full_stack_lab/tests/supplier_assurance_check.py:76` `test_approval_without_body_returns_korean_missing_field_reason` | 본문 생략 시 공급자 필수 항목 오류 → 다음 검증 관문 오류 | 요청 본문 생략이 보증 허위 입력이나 보류 사유가 되지 않음 | **정당함** — 아래 표시·기록 조건을 함께 확인함 |

`test_impact_package_maps_the_stated_input_to_assessment_items`와 `test_very_high_tier_needs_the_reason_and_a_second_administrator`는 변경되지 않았다. 패키지 표시는 매우 높음의 2인·사유를 계속 표시하고, 매우 높음은 사유 없는 2인을 거부하며 사유와 2인을 모두 요구한다. 대상 코드와 맞는다.

기대값 변경과 별개로 기존 시험 파일 3개가 통째로 삭제됐다. 이 삭제는 구현 보고의 변경 목록에 없다. 각 삭제는 **되돌려야 함**이다.

| 삭제된 기존 시험 | 사라진 검증 | 조치 |
| --- | --- | --- |
| `full_stack_lab/tests/user_auto_suspend_check.py` (기준판본 시험 10개; 예: `origin/main:.../user_auto_suspend_check.py:98`) | 반복 위반 임계, 기간·만료, 동시성, dispatch 차단 | **되돌려야 함** — 자동 중지 구현 삭제와 함께 복구 |
| `full_stack_lab/tests/sbom_impact_check.py` (5개; `origin/main:.../sbom_impact_check.py:51-126`) | 취약 패키지 영향 조회, 대상 구분, 부분 실패·중지 원장 | **되돌려야 함** — 영향 조회 기능과 함께 복구 |
| `full_stack_lab/tests/endpoint_offline_arrival_check.py` (8개; `origin/main:.../endpoint_offline_arrival_check.py:241-353`) | 오프라인 재전송, 응답 유실·프로세스 중단, 중복, 버퍼 초과·만료 | **되돌려야 함** — 제품 코드 변경은 확인되지 않았지만 D-182 통합 회귀 증거가 사라짐 |

## 2. 바뀐 기대값이 고정하던 통제와 잔존 여부

- 높음의 사유 대안 폐지는 `risk_tier.APPROVAL`과 `decide`에 반영됐고, 개별 승인·한 화면 승인·등록에서 사유만으로 2인을 채우는 경로는 찾지 못했다.
- 매우 높음의 사유 의무는 유지된다. 개별 승인과 한 화면 승인은 10자 이상 사유가 없으면 거부하고, 등록은 승인 기록의 `written_reason`을 다시 확인한다.
- root 단독 모드는 사건에 `solo_mode`·`solo_operator`만 기록한다. 승인자 수 계산을 바꾸지 않는다.
- 공급자 누락은 명시적으로 미확인 상태가 된다. 예외 경로와 잘못된 기본값은 아래 4절 및 발견 1에서 다룬다.

## 3. D-189 여섯 지점 대조

| 지점 | 대상 코드 | 결론 |
| --- | --- | --- |
| `risk_tier.APPROVAL` | `full_stack_lab/gateway/app/risk_tier.py:48-53` | 높음 `{approvers: 2, reason: none}`, 매우 높음 `{approvers: 2, reason: required}`. 판단과 일치 |
| `decide` | `risk_tier.py:102-112` | 매우 높음은 사유를 먼저 요구하고, 그 다음 승인자 수를 확인한다. 높음은 사유와 관계없이 2명 전 `cosign` |
| `package` | `risk_tier.py:139-170` | 같은 `APPROVAL` 표에서 승인 방식을 만들며 매우 높음은 “관리자 2명 및 위험 수용 사유” |
| `risk_tier_gate` | `agent_service.py:1504-1539` | 입력 해시가 같은 1차 승인자만 세고 같은 사람을 제외한 뒤 `decide` 호출 |
| `approve_and_register` | `agent_service.py:1880-1890, 1961-2049` | 신청자 독립성 확인 후 1차 승인자를 `same_person`으로 중복 제거하고 `decide` 호출. 매우 높음 사유 필수 |
| `core.register_server` | `core.py:670-685` | DB의 신청 입력 해시와 승인 증거를 대조하고 신청자 제외·서로 다른 승인자 수·매우 높음 사유를 재확인 |

사람 구분은 `review.same_person`이 동일 토큰 또는 같은 `user_id`를 비교한다(`review.py:53-61`). 한 화면 승인 진입 때 신청자와 승인자를 `require_independent`로 검사하고(`agent_service.py:1880-1890`, `review.py:64-79`), 2차 승인자는 앞선 승인자와 같은 사람인지 다시 제거한다(`agent_service.py:2014-2021`). 신청자 본인, 같은 사람의 다른 토큰, 같은 사람의 두 번째 클릭이 단독으로 승인자 수를 채우는 경로는 확인하지 못했다.

## 4. 공급자 보증 선택 입력

- 화면: 미제공 문자열·하위 처리자·SBOM/VEX 값은 한 화면 승인 및 등록 상세에서 `확인 안 됨`으로 보인다(`console.js:1680-1689, 1698-1714`). 빈 정책 주소에 `undefined` 링크를 만들지 않는다.
- 기록: 승인 증거, `approval_events.scope`, 등록부에는 `supplier_assurance_unconfirmed` 필드명 목록을 저장한다(`agent_service.py:1603-1616, 1671-1685, 2050-2080`, `core.py:720`). 값 칸에 사용자 문자열을 억지로 넣는 대신 미확인 필드를 구조화해 기록한다.
- 내보내기: JSON/CSV는 제공되지 않은 각 필드 값을 `확인 안 됨`으로 쓴다(`supplier_assurance.py:18-19, 74-108, 118-125`).
- 기본값: SBOM/VEX는 `IntakeApproval`에서 `None`이며 명시적 `False`만 “제출하지 않았다”로 처리한다(`agent_service.py:1475-1487`, `supplier_assurance.py:74-81`). 같은 두 항목을 `False`로 초기화하는 다른 제품 기본값은 찾지 못했다. `False`는 확인된 미제출이고 누락·빈 문자열·`미확인`은 미확인이다.

따라서 두 공급자 기대값 변경은 보류 사유를 바꿨지만, 미제공을 “미제출” 또는 “제출”로 거짓 기록하는 대상 경로는 찾지 못했다. 기록은 문구 대신 미확인 필드명 목록으로 명시되어 있다.

## 5. 근거 없는 신청과 우회 입력

직접 입력 검증은 통과한다. `risk_tier.assess`는 빈 문자열·공백·잘못된 선택·`users=0`을 오류로, `null`·누락은 결측으로, 배열 같은 비객체 입력은 전체 결측으로 처리한다(`risk_tier.py:65-89`). 목록은 입력과 제안이 모두 없으면 보류 칩과 `승인 —`를 보여 주고 점수는 `—`로 표시한다(`agent_service.py:955-965`, `console.js:1654-1669`; 신규 UI 시험 `intake_d189_ui_check.mjs:54-61`). 승인 경로도 등급이 없으면 거부한다(`agent_service.py:2022-2023`).

다만 이 보류는 **쓸 수 있는 제안이 없는 경우**에만 유지된다. `with_risk`는 저장된 `approval_proposal`의 위험 결과를 가져올 때 `blockers`나 실제 도구 목록을 확인하지 않는다. 6절 발견 2의 재현으로 목록이 보류에서 “높음 · 승인 0/2”로 바뀐다. 잘못된 입력 자체가 점수를 내는 우회는 아니지만, 실행 근거가 없는 차단 제안을 유효한 위험 제안으로 표시한다.

## 6. 발견

### 1. D-176 반복 위반 자동 중지가 제거됨 — 치명적

- **근거:** 기준판본은 `core.py:92-108`에서 정책·임계·창·기간을 정하고 `core.py:1876, 1925-1927`에서 차단 판정과 자동 중지를 같은 기록 트랜잭션에 묶었다. `user_suspend.py:13-24`가 `automatic_suspend`을 연결한다. 대상은 `automatic_suspend.py`와 `user_auto_suspend_check.py`를 삭제했고, `core.py`의 상수·호출도 없다.
- **재현 조건:** `AUTO_SUSPEND_THRESHOLD=5` 기본값 기준, 같은 직원·서버에서 지정된 위반 정책 차단이 600초 안에 5회 발생한 뒤 다음 호출이 개별 정책상 허용될 수 있는 상태가 되어도 자동 중지 상태와 자동 사건이 생성되지 않는다. 실행 중인 요청을 잠그거나 후속 호출을 중지시키던 D-176 통제가 사라진다.
- **수정안:** D-189 승인 변경만 남기고 기준판본의 자동 중지 모듈, 판정 트랜잭션 호출, 만료 처리와 회귀시험을 복구한다. 관련 시험은 재검토 때 실행한다.

### 2. 차단된 제안이 목록에서 등급으로 나타남 — 중간

- **근거:** `agent_service.py:1921-1958`은 저장소 실행 endpoint가 없거나 도구가 비어도 `execution-missing`·`tools-missing` 차단 사유를 넣은 뒤 제안을 저장한다. `intake_proposal.py:32-40`은 도구가 없을 때도 실행 권한 `x`·자율 실행을 기본 제안하고, `risk_tier.py:41-43`은 그 조합을 높음으로 올린다. `with_risk`는 `agent_service.py:955-960`에서 이 제안을 차단 사유 확인 없이 사용한다. UI는 해당 상태를 `console.js:1657-1660`에서 높음과 승인 수로 표시한다.
- **재현 조건:** 검증된 저장소 신청에 활성 runtime이 없어 approval preview의 endpoint가 비고 도구가 없을 때 preview를 열어 보류된 제안을 저장한다. 신청 `risk_input`이 데이터 등급만 있어 미완성인 상태에서 목록을 다시 읽으면, 차단이 남은 제안의 기본값으로 높음이 표시되고 관리자에게 `승인 0/2`가 보일 수 있다. preview의 승인 버튼은 차단으로 비활성이라 이 경로만으로 등록되지는 않는다.
- **수정안:** `with_risk`가 `approval_proposal.risk`를 쓸 때 제안의 차단 목록이 비었고 실제 도구가 있는지 확인한다. 아니면 원래 보류 상태와 `승인 —`를 유지한다. 이 조건을 덮는 새 회귀시험을 추가한다.

### 3. SBOM 영향 조회·중지 화면과 API가 삭제됨 — 높음

- **근거:** 기준판본은 관리자 화면 `agent_service.py:900`, `/api/supply-chain/impact`·`/impact/stop` 경로 `agent_service.py:1442-1455`, 콘솔 `console.js:382, 1660-1672, 2208-2215`를 갖고 있었다. 대상은 `gateway/app/sbom_impact.py`와 `tests/sbom_impact_check.py`를 삭제하고 화면 경로·라우트도 제거했다.
- **재현 조건:** 운영자가 패키지와 취약 판본 범위를 조회하거나 영향 서버 중지를 요청하면 대상에서 기존 두 API가 등록되지 않아 404가 된다. 취약 패키지가 있는 기존 서버를 찾고 기존 중지 경로로 격리하는 기능도 사라진다.
- **수정안:** SBOM 영향 모듈, 관리자 경로·콘솔 화면, 다섯 회귀시험을 기준판본에서 복구한다. D-189 승인 파일과 분리해 범위를 확인한다.

### 4. 오프라인 버퍼 통합 회귀시험이 삭제됨 — 중간

- **근거:** 대상은 `tests/endpoint_offline_arrival_check.py`를 삭제했다. 기준판본 `origin/main:full_stack_lab/tests/endpoint_offline_arrival_check.py:241-353`에는 재연결 후 도착, Gateway 오류, 프로세스 중단, 응답 유실, 중복 키, 버퍼 초과·만료 등 8개 시험이 있었다. 이번 diff에서 대응 제품 파일 삭제는 보이지 않는다.
- **재현 조건:** 향후 ACK 커서가 저장 응답 전에 이동하거나, 저장 후 응답 유실 재시도가 중복을 만들거나, 오프라인 버퍼가 넘쳐도 이 통합 시험이 더는 실패를 잡지 못한다. 이번 리뷰에서 해당 동작 자체는 실행하지 않았다.
- **수정안:** D-182의 이 파일을 복구한다. 시험 제거를 정당화할 대체 증거는 대상 diff에서 찾지 못했다.

## 7. 정책 ID와 root 단독 운영

- `policy.rego`의 정책 ID 집합을 비교한 결과 추가·삭제 ID는 0개다. `PAC-13`, `P-X-APPROVAL-001`, `MCP-CATALOG-001`, `P-APPROVAL-EXPIRY-001`은 양쪽 ref에 남아 있으며 변경된 D-189 경로에서 새 정책 ID는 확인되지 않았다.
- D-188의 높음 사유 대안은 D-189로 대체됐고(`DECISIONS.md:1831-1834`), `solo_mode`는 기록값일 뿐 승인자 수에 영향을 주지 않는다. `risk_tier_gate`, `approve_and_register`, `core.register_server`가 모두 2인을 확인하므로 root 단독 모드에서 혼자 높음·매우 높음을 통과하는 경로는 없다. 매우 높음에는 여기에 사유도 필요하다.

## 방향 제안

D-189 판단의 “근거 입력도 제안도 없으면 보류”를 UI에 일관되게 적용하려면 저장된 JSON 객체의 존재만으로 제안을 인정하지 말고, 차단이 없고 실제 검토 가능한 도구가 있는 제안만 위험 등급의 표시 근거로 삼아야 한다. 이 제한은 승인 정책이나 등급 계산을 바꾸지 않고 보류 표시만 제안의 유효성에 결속한다.

## 메인 판정 (2026-10-21) — C를 **B**로 정정

- **발견 1·3·4는 사실이 아니다(검토 방법 오류).** 대상 브랜치는 `517d3b7`에서 갈라졌고, 그 뒤 main에 D-176 자동 중지·D-178 SBOM 영향 조회·D-182 도착 시험이 들어왔다. 검토가 쓴 두 점 비교(`origin/main d189-target`)는 **main에만 새로 생긴 파일을 대상이 "삭제"한 것처럼** 보여 준다.
  세 점 비교(`git diff --diff-filter=D origin/main...d189-target`)로 확인한 결과 대상이 지운 파일은 **0개**이고, `sbom_impact.py`는 갈라진 시점(`517d3b7`)에 존재하지 않았다. 병합하면 세 기능은 그대로 남는다. 병합 직후 해당 파일·시험이 남아 있는지 다시 확인한다.
- **발견 2는 맞다 — 수정 후 병합.** 차단 사유가 있거나 실제 도구가 없는 저장 제안을 `with_risk`가 그대로 써서, 보류여야 할 신청이 목록에 「높음 · 승인 0/2」로 보인다. 등록까지 가지는 않지만(승인 버튼 비활성) D-189 추가 판단 2(근거 없는 신청은 보류)와 어긋나는 **표시 정확성 결함**이다. 검토의 방향 제안대로 차단이 없고 도구가 있는 제안만 등급 표시 근거로 쓴다.
- **기존 기대값 변경 5건은 검토가 모두 「정당함」으로 판정했다.** 병합 관문의 핵심 질문이 통과했다.
- root 단독 모드에서 높음·매우 높음을 혼자 통과하는 경로가 없다는 확인, 정책 ID 증감 0도 그대로 받는다.

판정: **B — 발견 2 수정 뒤 병합.** 재검토 없이 수정 diff를 메인이 확인한다(기대값 변경이 아니라 표시 조건 추가이므로).
