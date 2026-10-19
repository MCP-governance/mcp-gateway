# 원장 보존 정책과 만료 구간 폐기 (DEV-67, D-141)

근거: [규제 근거 개발 계획](../../research/llm-wiki/analysis/compliance/dev-plan/README.md) 2장 DEV-67·4장 RQ-01~03·7장 보존 기간 대조표, POL-38·48·49, DEV-63(D-123 서명 폐기 목록).

## 1. 구현한 것 (2026-10-20)

**보존 기간 설정** — `GET/PUT /api/audit/retention`(관리자). `gateway_settings.ledger_retention`에 `{days, jurisdictions}`를 두고,
변경은 `approval_events`(`ledger-retention`, `recorded`)에 남는다. 하한은 선택한 관할 팩의 **가장 긴** 값이고, 아무것도 고르지 않으면 366일(RQ-01: 12개월).
하한 미만·알 수 없는 관할은 422로 거부한다.

| 관할 팩 | 하한 | 근거 |
| --- | --- | --- |
| `EU` | 184일 | LIB-M01 Art. 19(1)·26(6) (6개월 이상) |
| `CN` | 184일 | LIB-M10 제23조제3호 (6개월 이상) |
| `US-FED` | 366일 | LIB-M18 부록 B 1 (조회 가능 1년) |
| `IN` | 366일 | LIB-M44 규칙 8(3) (최소 1년, 채택·미시행) |
| `KR-CREDIT` | 1096일 | LIB-L02 제20조제2항 (개인신용정보 처리기록 3년) |
| `US-CO` | 1096일 | LIB-M15 6-1-1702(4)·6-1-1703 (3년, 채택·미시행) |

개월·연은 가장 긴 달력 구간 일수로 올려 잡는다(6개월=184일, 1년=366일, 3년=1096일). 구속력 있는 의무 조항만 넣었고 권고(LIB-M31·M41)는 뺐다.
값은 `gateway/app/retention.py`의 `FLOORS`다. RQ-02(관할 팩을 레지스트리 구성으로)는 DEV-66·69가 팩 파일을 만들 때 옮긴다.

**구간 봉인(seal)** — 만료 구간을 폐기한다는 결정은 D-123 서명 폐기 목록(DB 밖 볼륨, Ed25519 서명·연쇄 해시·서명된 head)에
`kind="ledger"`, `subject="decisions:<last_id>"` 기록으로 남긴다. DB 백업 복원으로 되돌릴 수 없게 하려는 것이다. `detail`:

| 필드 | 뜻 |
| --- | --- |
| `last_id`, `last_sha256` | 이 id까지(누적) 폐기, 그 행의 `entry_sha256` |
| `last_created_at` | 그 행의 기록 시각 |
| `retention_days`, `jurisdictions` | 봉인 당시 설정 |
| `reason`, `requested_by`, `approved_by` | 사유와 두 사람(서로 달라야 함) |

읽을 때 `retention.validate_seal`이 다시 확인한다: 두 사람·사유, 하한 이상, `last_created_at + retention_days ≤ 기록 시각`(보존 기간 안 구간 봉인 거부),
`last_id`는 앞 봉인보다 커야 한다. 하나라도 어기면 폐기 목록 손상으로 보고 봉인이 없는 것으로 취급한다.

**사슬 검증** — `contract.walk_chain`(순수 함수, `verify_audit_chain`이 호출)은 최신 봉인의 `last_sha256`에서 시작한다.

| 상황 | 결과 |
| --- | --- |
| 봉인 이하 행이 없고 다음 행의 `prev_sha256` = 봉인 해시 | 통과, `sealed_through` 표시 |
| 봉인 이하 행이 다시 있음(백업 복원) | `intact=false`, 그 행 id, "되살아났을 수 있습니다" |
| 봉인 밖까지 지워짐, 또는 봉인 해시가 사슬과 다름 | `intact=false`, 첫 남은 행 id |
| 폐기 목록을 읽을 수 없음·서명 불일치·규칙 위반 | 봉인 없음 → 앞부분이 없으면 기존처럼 끊김(실패는 차단) |

`disposal.reconcile`은 `ledger` 기록을 건너뛴다(서버 폐기로 오인해 서버를 끄지 않게).

## 2. 구현하지 않은 것: 행 삭제 (소유자 결정 필요)

README 원칙 5는 "판정 기록을 고치거나 **지우는** 코드를 쓰지 않습니다"이고, `decisions_append_only` 트리거가 DELETE를 막는다.
봉인 구간 삭제는 남은 판정 기록을 고치지 않는다는 점에서 AGENTS.md 문구("고치는 코드")와는 구분되지만, README 문구의 "지우는 코드"에는 그대로 걸린다.
DB 변경도 추가형(`CREATE TABLE IF NOT EXISTS`·`ADD COLUMN IF NOT EXISTS`)만 허용되어 트리거 예외를 넣을 수 없다. 그래서 삭제는 설계만 남긴다.
계획서 RQ-03도 "DEV-67 설계 승인"을 선행 조건으로 둔다.

승인되면(원칙 5에 "서명·두 사람 확인된 봉인 구간의 만료 삭제는 예외"를 소유자가 명시한 뒤) 할 일:

1. **요청(관리자 A)**: `cutoff = now - days`. `created_at < cutoff`인 연속 앞부분의 마지막 id를 `L`로 잡고 사슬이 온전한지 확인한다. `approval_events`에 `ledger-purge`/`held`.
2. **확인(다른 관리자 B)**: 사슬·만료·하한을 다시 확인하고 **봉인을 먼저** 폐기 목록에 쓴다(D-123처럼 선행 기록). 이어서 한 트랜잭션에서
   `approvals.executed_decision_id` 참조(`db/init.sql`의 FK)를 정리하고 `id ≤ L` 행을 삭제한다. 트리거는 "세션 표지 + 봉인 범위 안"만 통과하도록 바꾼다.
   `ledger-purge`/`approved`를 남긴다. 운영 명령은 `./console.sh field ledger-purge` 또는 관리 API 두 단계로 둔다.
3. **복원 대조**: `reconcile`이 봉인 이하 행을 다시 보면 같은 봉인으로 다시 지우고 `disposal-reconciled` 경보를 남긴다.
   지금은 `verify_audit_chain`이 되살아남을 찾아 실패로 보고하는 데까지만 한다.

다른 방법(RQ-03 암호 삭제): 행은 남기고 개인정보 열만 키로 암호화한 뒤 만료 시 키를 폐기한다. 원칙 5와 충돌하지 않지만
사슬 지문 열이 바뀌어 `CHAIN_VERSION` 8과 쓰기 경로 변경이 필요하다.

## 3. 한계

- 사슬은 키 없는 SHA-256이다. DB 쓰기 권한이 있으면 봉인 뒤 행을 전부 다시 계산할 수 있다. 봉인이 DB 밖에 고정하는 것은 봉인 지점까지다.
- DB와 폐기 볼륨·키를 함께 되돌린 호스트 관리자는 통제하지 못한다(D-123과 같은 한계).
- 표의 일수는 문서별 하한이고 고객 법무가 최종 확인한다. 삭제 의무(최대 보존) 규칙은 구현하지 않았다.
- `approval_events`·`siem_outbox`·`audit_annotations` 등 원장 주변 표의 보존은 다루지 않았다.
- 계획서의 "원장에 개인정보 본문을 넣지 않는다" 원칙과 달리, D-131에 따르면 `request_payload`에는 직원이 보낸 원문이 남는다. 이 원칙을 고정하는 시험은 만들지 않았다.
