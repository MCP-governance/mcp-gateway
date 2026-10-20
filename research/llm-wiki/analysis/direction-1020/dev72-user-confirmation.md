# DEV-72 사용자 확인 단계 설계 (D-174)

- 상태: 설계 초안(2026-10-20, Claude 레인). 적대 검토(luna) 후 구현.
- 기준 commit: `5b5a134`(main). 근거: [방향 갱신 10-20](README.md) 3장 DEV-72, M05 제6항(사용자 결정권, C10 정정: 제5항은 윤리 규범), TC260 6.3.1.
- 완료 조건(방향 문서): 확인 대기 호출이 요청 지문·10분 만료·1회용으로 묶이고, 고위험에서 자기 승인 경로 0, 확인 없이 실행 0.

## 1. 지금 코드(2026-10-20 main)

| 항목 | 위치 | 사실 |
| --- | --- | --- |
| 호출 승인 생성 | `core.execute_call` 2219~2241행 | OPA·로컬 판정이 `Approval`이면 `approvals` 행(`PENDING`, `request_fingerprint=canonical_hash(stored)`, `expires_at=+10분`)을 만든다. |
| 승인 처리 | `core.approve_request` 2319행~ | 관리자만, `review.require_independent`로 본인 승인 거부, 만료·지문 재검증, `UPDATE … WHERE status='PENDING' AND expires_at>now()`로 1회용 점유 후 `execute_call(approval_granted=True)`. |
| OPA 승인 규칙 | `opa/policy.rego` | `P-X-APPROVAL-001`(중요 데이터 실행), `P-VOLUME-001`(중요정보 몰림), `P-UNTRUSTED-CONTENT-001`(신뢰 못 할 표식)은 `not input.approval.granted`로 풀린다. `P-RESIDENCY-002`와 PAC `APPROVAL` 결과는 `pac15.pac13_approved`(승인자≠요청자, 관리자)로만 풀린다. |
| 중대 영향 | `core` 2211행, `high_impact.bound` | 도구 검토의 `high_impact`면 승인 행과 범위 해시가 묶여야 실행. |
| 하네스 안내 | `mcp_facade` 209행 | "관리자 승인이 필요합니다. 승인 ID …(Console → 승인 대기)". |
| 서버 위험 등급 | `core` 649행 이하 | 등록 때 `spec.risk_assessment.tier`(DEV-71: low/medium/high/very_high)를 저장. 이전 등록은 값 없음. |
| 토큰 종류 | `agent_contract` 101행 | 콘솔 로그인 토큰 `scope=console`, 하네스 토큰 `scope=mcp`(장치 결속). |

## 2. 결정

### 2.1 새 승인 종류를 만들지 않고 승인 행에 `kind`를 붙인다

`approvals.kind text NOT NULL DEFAULT 'independent' CHECK (kind IN ('independent','self'))`(ADD COLUMN IF NOT EXISTS).
판정 값은 기존 `Approval` 그대로 쓴다. 새 판정 값(`Confirm`)은 decisions 집계·대시보드·OPA 출력·facade·SIEM 모두를 건드리므로 택하지 않는다.
기존 행·기존 경로는 기본값 `independent`라 동작이 변하지 않는다.

### 2.2 본인 확인은 새 정책 하나에서만 나온다

- 새 OPA 규칙 `P-CONFIRM-001`(결과 `Approval`, `"approver": "requester"`). 관리대장 우선순위 110: 기존 승인 규칙(83~100)·차단보다 낮고 제한(120)·경보(125·132)·허용(140)보다 높다. 다른 승인·차단이 걸리면 그 규칙이 이기고, 제한·경보는 확인 뒤 실행 때 다시 판정된다.
- 조건(모두): 실행될 판정(Allow·Alert·Restrict)이었고, 확인이 아직 없고(`not input.approval.granted`), 다음 중 하나.
  1. 도구 검토에 `confirm: true`(검토자가 지정, `review.py` 정규화에 추가).
  2. `action ∈ {w, x}`이고 서버 `risk_assessment.tier == "medium"`.
- `kind='self'`는 **정책 ID가 `P-CONFIRM-001`일 때만** `core`가 붙인다. 다른 모든 `Approval`(OPA·PAC·거주성·중대 영향)은 `independent`.
- 기존 승인 규칙(`P-X-APPROVAL-001`·`P-VOLUME-001`·`P-UNTRUSTED-CONTENT-001`)을 본인 확인으로 내리지 않는다. 낮추는 것은 통제 약화라 별도 결정이 필요하다.
- 위험 등급 `high`·`very_high` 서버의 쓰기·실행은 이번 범위에서 새 승인 규칙을 만들지 않는다(기존 규칙 그대로). 등급 없는 이전 등록은 1번(도구 지정)만 적용한다 — 기본값을 바꾸면 기기의 기존 쓰기 호출이 일제히 멈추므로 재심사 때 등급이 붙는 단계 전환으로 한다.

### 2.3 본인 확인이 독립 승인을 대신하지 못하게

본인 확인으로 실행하는 순간 문맥이 바뀌어(예: 중요정보 몰림) 다른 승인 규칙이 걸릴 수 있다. 이때 `approval.granted=true`만 보면 본인 확인이 독립 승인을 통과시킨다. 그래서:

- `execute_call`의 OPA 입력을 `"approval": {"granted": …, "id": …, "kind": row.kind}`로 넓힌다.
- `policy.rego`에 `independent_approval if { input.approval.granted; object.get(input.approval, "kind", "independent") == "independent" }`를 두고, 기존 세 규칙의 `not input.approval.granted`를 `not independent_approval`로 바꾼다. `kind`가 없는 입력은 `independent`라 **기존 시험 기대값은 그대로**다.
- `P-CONFIRM-001`은 `not input.approval.granted`(종류 무관)로 풀린다.
- PAC·거주성: `pac.py`의 `individual_approval.approver_authorized`를 `kind == 'independent'`일 때만 참으로 둔다. `pac13_approved`는 이미 승인자≠요청자를 요구하므로 이중 차단이다.
- 중대 영향: `high_impact.bound`가 `approved["kind"] == "independent"`를 요구한다. 중대 영향 도구에 `confirm`이 같이 있어도 `P-HIGH-IMPACT-001`이 이긴다(2211행이 OPA 뒤에 덮어씀).

### 2.4 확인은 사람이 콘솔에서, 지문을 보고

- 경로: `POST /api/approvals/{id}/confirm`(게이트웨이 `Depends(caller)`), 본문 `{"request_fingerprint": …}`.
- 거부 조건: 토큰 `scope`에 `console`이 없음(하네스 `mcp` 토큰은 확인 불가 — 에이전트가 자기 호출을 확인하는 경로 차단), `kind != 'self'`, 확인자 ≠ 요청자(`review.same_person`), 지문 불일치, 만료, `PENDING` 아님.
- 처리: `UPDATE approvals SET status='APPROVED', reviewed_by=%s, reviewed_at=now() WHERE id=%s AND kind='self' AND status='PENDING' AND expires_at>now() RETURNING *` 한 문장으로 점유 → `review.record_event("call-confirm", "approved", …)` 같은 트랜잭션 → 지문 재검증 → `execute_call(approval_granted=True)` → 상태 `EXECUTED/UNCONFIRMED/NOT_EXECUTED`. `approve_request`의 뒷부분을 함수로 나눠 같이 쓴다.
- 요청자 취소: `POST /api/approvals/{id}/cancel`(같은 조건, 상태 `REJECTED`, 원장 `call-confirm` `rejected`).
- 관리자: `kind='self'` 행은 승인 불가(남의 이름으로 실행 금지, `approve_request`에서 거부·기록), 거절만 가능.
- 콘솔: 직원·관리자 모두에게 「내 확인」 화면(내 `self` 대기 건: 서버·도구·인자·사유·남은 시간, 확인/취소). 기존 「승인 대기」 목록은 `kind='independent'`만.
- 하네스 안내: `P-CONFIRM-001`이면 "본인 확인이 필요합니다. 확인 ID …(콘솔 → 내 확인). 확인하면 게이트웨이가 이 요청을 그대로 실행합니다."

### 2.5 하네스 안 되묻기(MCP elicitation)는 이번 범위 밖

elicitation 응답은 클라이언트가 만든다. 자동 승인 모드나 수정된 클라이언트가 사람 없이 수락할 수 있어 "사람이 확인했다"는 증거가 되지 못한다. Claude Code·Codex의 지원과 자동 수락 동작을 PJ1에서 실측한 뒤 편의 경로로만 검토한다(결과 기록은 `확인 경로: 하네스`로 구분).

## 3. 위협과 대응

| 위협 | 대응 | 남는 한계 |
| --- | --- | --- |
| 에이전트가 자기 호출을 확인 | `mcp` 토큰 거부, 콘솔 토큰만 | 같은 PC에서 에이전트가 브라우저 세션을 조작 — 조직 통제 의존(D-170) |
| 본인 확인으로 독립 승인 규칙 통과 | `kind` 입력·`independent_approval`·PAC `approver_authorized`·`high_impact.bound` | — |
| 확인 화면과 다른 내용 실행 | 지문 제출·재검증, `stored` 그대로 실행 | — |
| 재사용·경쟁 | 조건부 UPDATE 1회 점유, 만료 10분 | — |
| 관리자가 남의 본인 확인 건 실행 | `kind='self'` 승인 거부·기록 | — |
| 확인 피로 | 기본은 도구 지정+medium 쓰기만 | 운영 데이터로 임계 조정 |

## 4. 시험 계획

- OPA(`policy_test.rego` 추가만): `P-CONFIRM-001` 발생(도구 지정·medium w), 미발생(r·low·확인 있음), `kind=self`로는 `P-X-APPROVAL-001`·`P-VOLUME-001`·`P-UNTRUSTED-CONTENT-001`이 계속 `Approval`, `kind` 없는 기존 입력 기대값 불변.
- PostgreSQL 격리 랩 `tests/user_confirm_pg_check.py`: 정상 확인 1회 실행·원장 1건, 재확인 거부, 만료 거부, 다른 사용자 거부, `mcp` 토큰 거부, 지문 불일치 거부, 관리자 승인 거부·거절 가능, 취소, 확인 실행 중 문맥이 바뀌면 새 독립 승인 행(실행 0), 중대 영향+confirm 도구는 `independent`.
- PAC-13 자기 승인 금지 시험(`acceptance.self_approval_refused`, `review` 시험)은 고치지 않는다.
- 실기기: PJ1 관리 Claude로 confirm 지정 도구 호출 → 콘솔 「내 확인」 → 실행·원장 확인.

## 5. 구현 순서

1. 스키마·`review.py` `confirm` 정규화·OPA 규칙과 시험(기존 기대값 불변 확인).
2. `core` kind 부여·OPA 입력·`pac.py`·`high_impact.bound`·확인/취소 API·`approve_request` 거부.
3. facade 안내·콘솔 「내 확인」·정책 이름표·위협 매핑(`map_threats.py`).
4. 격리 랩 시험 → 기기 배포 → PJ1.

## 6. 통제 방향 검토(C10) 반영

[control-review](control-review.md) 요약 4~6항을 이 설계에 더한다.

- **확인 직전 재인증**: 하네스와 브라우저가 같은 OS 계정이면(Windows 기본, Linux 데스크톱 사용자) 에이전트가 콘솔 세션으로 스스로 확인할 수 있다. 이 경우는 D-170 목록에 없으므로 제품 안에서 막는다. 확인 API는 최근 대화형 인증(콘솔 로그인 토큰의 `auth_time`이 2분 이내, 아니면 비밀번호 재입력 — 기존 콘솔 로그인 경로 재사용)을 요구한다. WebAuthn은 후속 강화.
- **표시 = 전송**: 확인 화면은 제한·마스킹을 적용한 뒤 실제로 보낼 인자를 잘림 없이 보여 주고, 제출 지문은 그 값(`request_fingerprint`) 그대로 대조한다.
- **순서 고정**: 동의(`P-CONSENT-001`) → 본인 확인 → 독립 승인. 확인 뒤 실행 때 동의가 빠져 있으면 실행하지 않고 동의 차단을 남긴다(지금 코드의 2203행 위치가 이미 이 순서).
- **확인 피로 지표**: 사용자·도구별 확인 요청 수, 확인·취소·만료 비율을 집계한다(운영 화면 지표, 임계 조정 근거).
