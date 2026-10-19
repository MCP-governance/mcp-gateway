# 2026-10-20 원장 보존 정책과 만료 구간 봉인

- 작업자: Claude Opus
- 브랜치: `10/20-ledger-retention`
- 코드 기준: `770542be07cf1bcc4de90690b395be2ec4300d2f`, 시작 시 워킹 트리 깨끗함. 변경 파일: `full_stack_lab/gateway/app/retention.py`(신규)·`contract.py`·`core.py`·`disposal.py`·`main.py`, `full_stack_lab/tests/ledger_retention_check.py`(신규), `docs/ai/LEDGER_RETENTION.md`(신규)·`DECISIONS.md`(D-141)·`SECURITY_BOUNDARIES.md`(10장)·`README.md`(문서 지도), 이 보고서, `status/backlog.md`의 DEV-67 상태 칸.
- 시작 근거: DEV-67, [규제 근거 개발 계획](../../analysis/compliance/dev-plan/README.md) 2장·4장 RQ-01~03·7장, POL-38·48·49, DEV-63(D-123)
- 해결할 문제와 완료 조건: 보존 기간 설정이 관할 하한 미만을 거부하고, 만료 구간 폐기 뒤에도 봉인 해시로 사슬 검증이 통과하며 복원 후 폐기 구간이 되살아나지 않는다.

## 결과

- **보존 기간 설정**: `GET/PUT /api/audit/retention`(관리자 인증). `{days, jurisdictions}`를 `gateway_settings.ledger_retention`에 두고 변경을 `approval_events`(`ledger-retention`)에 남긴다. 하한은 선택한 관할 팩 중 가장 긴 값(EU·CN 184일, US-FED·IN 366일, KR-CREDIT·US-CO 1096일), 미선택이면 366일이다. 미만·알 수 없는 관할·정수가 아닌 값은 422.
- **봉인**: 만료 구간 폐기 결정은 D-123 서명 폐기 목록에 `kind="ledger"` 기록으로 남는 형식을 정했다. 읽을 때(`retention.validate_seal`) 요청자≠확인자, 사유, 하한 이상, `last_created_at + retention_days ≤ 기록 시각`, `last_id` 증가를 확인하고 어기면 손상으로 본다.
- **사슬 검증**: 루프를 순수 함수 `contract.walk_chain`으로 옮겼다(동작 동일, `verify_audit_chain`이 호출). 최신 봉인의 해시에서 시작하고, 봉인 이하 행이 다시 있으면 `intact=false`("되살아났을 수 있습니다")다. 폐기 목록을 읽지 못하면 봉인이 없는 것으로 보아 앞부분 누락은 기존처럼 끊김이다. 결과에 `sealed_through`가 더해졌다.
- `disposal.reconcile`은 `ledger` 기록을 건너뛴다. 건너뛰지 않으면 일반 분기로 떨어져 `mcp_servers`를 끄려 한다.
- **구현하지 않음 — 행 삭제**: README 원칙 5가 "판정 기록을 고치거나 **지우는** 코드를 쓰지 않습니다"이고 append-only 트리거 예외는 추가형 DB 변경 규칙 밖이라 불변식 충돌로 판단했다. 요청·다른 관리자 확인·봉인 선행 기록·`approvals.executed_decision_id` FK 정리·삭제·복원 후 재삭제 절차는 [설계 문서](../../../../docs/ai/LEDGER_RETENTION.md) 2장에만 있다. 지금은 봉인을 쓰는 제품 경로가 없어 원장 행은 지워지지 않고, 봉인 검증은 시험에서만 동작한다.

완료 조건 대비: 하한 미만 거부는 구현됐다. 봉인 뒤 사슬 통과, 복원 되살아남 탐지, 봉인 위조 탐지는 검증 쪽만 구현됐다. 폐기 실행과 복원 후 재삭제는 미구현이다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 단위 시험 | `python full_stack_lab/tests/ledger_retention_check.py -v`, Windows Python 3.12.10·cryptography 50.0.0·jsonschema 4.25.1, 2026-10-20 | 12건 중 11 통과, 1 건너뜀(`GatewayVerify`: psycopg 없음) | 하한·최장 하한·미선택 기본값·잘못된 입력, 봉인 뒤 통과(봉인 10까지·남은 행 0 포함), 복원 되살아남, 봉인 없는 삭제 끊김, 봉인 밖 삭제, 다른 해시로 서명된 봉인, 폐기 목록 편집, 규칙 위반 봉인 5종, 역순 봉인, 서버 차단 오인 없음 |
| 정적 검사 | `python -m pyflakes gateway/app/{core,contract,retention,disposal,main}.py tests/ledger_retention_check.py`, `python -m py_compile` 같은 파일 | 통과 | — |
| 인증 라우트 | `python full_stack_lab/tests/open_endpoints.py` | 통과(인증 필요 73→75) | — |
| 기존 사슬 시험 | `tests/security_edges_check.py` | 미실행(게이트웨이 이미지 필요) | — |
| 기기 배포·API | `field up` 후 `PUT /api/audit/retention` | 미실행 | — |
| 실제 DB 복원 | — | 미실행 | — |

## 실패·미완료·한계

- 행 삭제 실행은 보류다(위 결과). 그래서 "만료 구간 폐기 뒤" 상태는 시험에서 행을 빼서 흉내 냈다.
- 키 없는 SHA-256 사슬이라 DB 쓰기 권한자가 봉인 뒤 행을 전부 다시 계산하는 것은 막지 못한다. DB와 폐기 볼륨·키를 함께 되돌리면 탐지하지 못한다(D-123과 같은 한계).
- 폐기 목록을 읽지 못하면 봉인 이하 행이 되살아나도 `verify_audit_chain`은 찾지 못한다. 폐기 목록 손상 자체는 `disposal.watch`가 경보한다.
- 하한 일수는 문서별 하한이고 고객 법무가 확인한다. 삭제 의무(최대 보존)·주변 표(`approval_events`·`siem_outbox`·`audit_annotations`) 보존은 다루지 않았다.
- 계획서의 "원장에 개인정보 본문을 넣지 않는다" 원칙은 D-131(원장 `request_payload`에 원문 보관)과 맞지 않는다. 고정 시험은 만들지 않았다.
- 콘솔 화면은 만들지 않았다(관리 API만).

## 다음 작업

- 소유자 결정: README 원칙 5에 "서명·두 사람 확인된 봉인 구간의 만료 삭제" 예외를 둘지, RQ-03의 암호 삭제(키 폐기)를 고를지.
- 결정 뒤 DEV-67 나머지: 삭제 운영 명령(설계 2장), `reconcile`의 복원 후 재삭제, 보존 설정 콘솔 화면, 기기에서 실제 백업 복원 시험.
- 관할 팩을 레지스트리 구성으로 옮기기(RQ-02, DEV-66·69와 함께).

## 사용자에게 필요한 입력

- 원장 행 삭제를 허용할지(원칙 5 예외) 또는 암호 삭제로 갈지 결정.
- 기기 `full_stack_lab`에서 `docker compose run --rm --no-deps --entrypoint python -v "$PWD/tests:/tests:ro" gateway /tests/ledger_retention_check.py`(12건, 건너뜀 0 기대)와 같은 방식의 `/tests/security_edges_check.py` 실행.
