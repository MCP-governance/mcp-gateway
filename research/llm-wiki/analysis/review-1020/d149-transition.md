# D-149 전환 정정 적대 검증

- 기준: 브랜치 `10/20-output-contract-v2-review`, 시작 HEAD `d6af5e8297ed623b40c343fd27d66c79fad9ef5f`; 시작 작업 트리 clean.
- 범위: NULL 출력 승인 해시의 의미, 갱신·승인·lock·도입 경로, 고정 도구 검사·DRIFT, `catalog_refresh_check.py`의 기존 목적.
- 판정: 전환 정정의 주요 집행 경로는 일치한다. 다만 명시적 재승인 이벤트에서 과거 NULL을 “출력 없음” 해시로 기록하는 감사 의미 오류를 확인하고 최소 수정했다.

## 반박 목표별 결과

### 1. 첫 관찰값 자동 승인 여부

`core.refresh_catalog`는 관측 스키마와 `observed_output_schema_hash`만 기록한다. 비교 함수 `output_contract.matches`와 `observed_matches`는 승인 해시가 NULL이면 미고정으로 허용하지만 승인 열을 채우지 않는다. `registry.sync`도 구 lock 항목에 출력 해시가 빠졌으면 DB 승인 열에 NULL을 둔다. 판본 이월 SQL은 NULL을 포함해 기존 미고정 상태를 유지한다.

승인 열을 갱신하는 확인 경로는 다음 두 곳이다.

- `core.approve_contract`: 명시적 사람 재승인. 관측값을 새 승인으로 기록한다.
- `core.register_server`: 승인된 도입 신청으로 등록할 때, 사람이 검토한 도입 계약의 출력 해시를 기록한다. 이후 등록 직후 refresh가 관측값을 대조한다.

관측만으로 승인 해시가 채워지는 TOFU 경로는 찾지 못했다. 이번 검토는 코드 정적 대조와 대역 시험이며 운영 DB의 실제 전환은 확인하지 않았다.

### 2. 신규 도구가 NULL에 고착되는지

도입 등록 경로는 검토된 계약에서 `output_schema_sha256`을 받아 `approved_output_schema_hash`를 기록한다. 저장소 lock 생성은 도구마다 출력 해시 필드를 생성하며, 명시적 출력 스키마가 없는 경우에도 canonical null의 해시를 기록한다. 반대로 출력 해시를 생략한 구 lock 항목은 호환 전환상 미고정으로 남는다. 따라서 신규 lock을 만들고 커밋할 때 출력 해시를 포함해야 새 정본 도구가 고정된다. 구 lock의 해시 생략이 자동 보완되지는 않는다.

### 3. 이미 고정된 도구의 검증·DRIFT

고정 승인 해시는 refresh 카탈로그 비교, 승인 계약의 출력 전용 해시, 하네스 도구목록 SQL, 실행 직전 같은 연결 재확인, 최종 dispatch intent SQL에서 관측 해시와 대조된다. 불일치가 있으면 영향 도구를 제한하고 `MCP-CATALOG-001`로 전송을 막는다. 응답 경로는 고정된 출력 스키마만 검증에 전달하며, 미고정 승인에는 전달하지 않는다. `mcp_facade`는 승인 해시가 NULL일 때 출력 스키마를 광고하지 않는다.

정적 경로 대조와 `output_contract_check.py --pure`의 전송 AsyncMock 사례에서 고정된 “출력 없음” 계약에 스키마가 추가되면 전송 전 차단되고, 동일 스키마가 승인된 경우 호출이 허용되는 것을 확인했다. 실제 PostgreSQL 경합·하네스 응답은 미실행이다.

### 4. 기존 시험 보정의 목적 보존

`catalog_refresh_check.py` fixture의 canonical-null 해시는 명시적으로 출력 스키마가 없는 승인 상태다. 그 시험의 핵심은 입력 계약 A→B→A에서 복귀 뒤 승인 B를 잘못 채택하지 않는지 확인하는 것이며, 기존 설명/입력 해시를 유지해 그 기대값과 assertion을 바꾸지 않았다. 레거시 NULL 출력 승인 뒤 관측값을 자동 승인하지 않는 경우는 `output_contract_check.py`의 `test_legacy_approval_is_unpinned_and_never_adopts_the_observation` 및 `test_schema_drift_reapproval_and_legacy_transition`이 별도로 다룬다.

따라서 fixture 보정은 A→B→A 시험 목적을 약화하지 않는다. 다만 `catalog_refresh_check.py` 자체는 출력 계약의 레거시 NULL 의미를 검증하지 않으며, 해당 보증은 별도 시험 파일에 있다.

## 확인된 결함과 수정

재승인 `changes[].from.output_schema`가 `output_contract.approved_hash(row)`를 사용해 NULL 승인 해시를 canonical-null 해시로 기록했다. D-149 정정 후 NULL은 미고정이므로, 이 감사값은 실제 이전 상태와 다르게 보였다. 제품의 승인 동작은 올바르지만 기록된 이전 상태는 오해를 낳을 수 있다.

`core.approve_contract`가 이전 승인값을 nullable DB 값 그대로 기록하게 바꾸고, `full_stack_lab/tests/d149_transition_check.py`에 재승인 감사 이벤트가 NULL과 명시적 canonical-null 해시를 구별하는 unittest를 추가했다. 새 시험은 생산 함수의 AST 본문을 실행하고 DB·감사·refresh I/O를 AsyncMock 대역으로 제공한다. 기존 시험 기대값은 바꾸지 않았다.

## 검증

| 확인 | 명령·환경 | 결과 |
| --- | --- | --- |
| 출력 계약·전환 대역 | `python -X utf8 full_stack_lab/tests/output_contract_check.py --pure` (Windows Python 3.10) | 9개 통과 |
| 신규 감사 의미 회귀 | `python -X utf8 full_stack_lab/tests/d149_transition_check.py` | 통과 |
| 기존 롤백 회귀 직접 실행 | `python -X utf8 full_stack_lab/tests/catalog_refresh_check.py` | 미실행: Python 3.10에서 `datetime.UTC` import 불가 |
| lock 비교 도구 | `python -X utf8 full_stack_lab/tests/contracts_check.py` | 자체 검사 통과 |
| 구문·공백 | 변경 Python `py_compile`, `git diff --check` | 통과 |
| 원격 기준 | `git ls-remote --symref origin HEAD` | GitHub 443 연결 실패, 원격 HEAD 확인 불가 |

## 남은 한계

- 승인 도입 흐름·lock 적재·실제 DB 마이그레이션·동시 dispatch를 이 PC에서 실행하지 않았다.
- 기존 상용 서버의 실제 outputSchema 부재는 앞선 보고의 현장 관찰을 전제로 하며 이번에는 재측정하지 않았다.
- 게이트웨이 이미지·솔루션 기기 배포·PJ1 실제 하네스 시험이 필요하다.
- 신규 등록에서 생성한 lock을 현장 서버와 대조해 커밋하는 절차는 사람의 lock diff 검토에 달려 있다.
