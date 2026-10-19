# 2026-10-20 결과 네 축 기록 (DEV-48 / D-136)

- 작업자: Codex sol
- 코드 기준: 시작 `c002fbd5fcf5f928e5ad68c57fa05edb1f76b1a6`, 깨끗한 작업 트리, 브랜치 `10/20-result-outcomes`. 원격 HEAD 재확인은 github.com:443 연결 실패로 미확인.
- 변경 파일: `full_stack_lab/gateway/app/{outcomes.py,core.py,contract.py,activity.py,audit.py,v2_tables.sql,agent_static/console.js,agent_static/console.css}`, 새 시험 2개, 설계·화면·결정 문서, 분석, 이 보고서, 백로그 DEV-48 상태만 변경. `status/current.md`와 기존 시험 파일은 변경하지 않음.
- 시작 근거: [재설계](../../analysis/oss-deep/redesign-2026-10-15.md), [ContextForge 분석 및 정정](../../analysis/oss-deep/contextforge-hooks.md), 사용자 10-15 원장·화면 분리 결정.
- 해결할 문제와 완료 조건: 연결·정책 판정·업무 결과·독립 효과를 분리하고 검사기 장애와 정책 거부·제공자 실패를 구분. 구현을 작성했으나 기존 시험 대역 변경 필요로 중단했으며 검수 미완료.

## 결과

순수 함수가 한국어 네 축을 생성한다. 새 JSONB 스냅샷은 체인 8판에 포함하고 1~7판은 그대로 검증한다. 과거 원장은 조회 시 투영만 하며 업무 증거 부족을 성공으로 추정하지 않는다. 관리자 실행 확인은 조회 투영의 독립 효과만 바꾸며 저장 스냅샷은 그대로다. HTTP 예외에서는 코드만 읽고 응답 원문은 추가 저장하지 않는다.

도구 호출 목록·상세와 감사 목록·상세에 네 축 칩을 연결했다. 감사 상세의 영어 enum 원문 JSON 노출은 한글 라벨·값으로 바꿨다. 새 정책·의존성·MCP 서버는 추가하지 않았다. 구현·로컬 확인 범위이며 설정 활성화·기기 배포·실제 MCP·하네스·독립 효과 실측은 수행하지 않았다.

[원자 요구·코드 심볼·시험·반례·출처·한계 정본](../../analysis/outcome-axes-d136.md).

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 순수 함수·DB/HTTP 대역 | `python -B -X utf8 full_stack_lab/tests/outcome_axes_check.py`, Windows Python 3.10, 2026-10-20 | 8건 통과, 대표 입력 17개 및 경계·지문·원본 불변 확인 | 해당 새 시험, 실행 stdout |
| 화면 함수 | `node --test full_stack_lab/tests/outcome-console.test.mjs` | 2건 통과, 네 라벨·누락값·실제 html 이스케이프 확인 | 해당 새 시험, 실행 stdout |
| 기존 콘솔 회귀 | `node --test full_stack_lab/tests/console-state.test.mjs` | 15건 통과, 기존 파일 변경 없음 | 기존 시험, 실행 stdout |
| 정적 검사 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | 실행 exit 0 |
| 화면 문구 검사 | `python -B -X utf8 full_stack_lab/tests/console_copy_check.py` | 위반 0건 | 실행 stdout |
| Python 구문 | `python -m py_compile` 변경 Python 6개 | 통과 | 실행 exit 0 |
| diff 공백 | `git diff --check` | 통과 | 실행 exit 0 |
| 기존 자격정보 경계 | `python -B -X utf8 full_stack_lab/tests/dest_pin_credential_redaction_check.py` | **실패: 16건 중 2건 NameError**, 아래 절 참조 | 두 시험 traceback, exit 1 |
| 실제 모듈 import·조회 대역 | `python -B -X utf8 full_stack_lab/tests/outcome_axes_check.py --gateway` | **실패: psycopg 미설치**, 순수 시험 8건은 통과 | ModuleNotFoundError, 해당 실행은 성공으로 세지 않음 |
| Python lint | `python -m pyflakes` 변경 Python 파일 | **실행 불가: pyflakes 미설치** | No module named pyflakes |

## 기존 시험 변경 필요

`dest_pin_credential_redaction_check.py`는 production 함수를 AST로 추출하여 import 없이 실행한다. 새 참조에 맞춰 아래 namespace 주입이 필요하다. 기존 기대값은 변경할 필요가 없으며 사람의 적대 검증 전에는 대역 구성도 수정하지 않았다.

1. `CredentialRedaction.test_audit_and_returned_payload_share_redacted_error_before_hash`: `_record_decision`의 `outcome_axes` 미정의.
2. `DestinationPin.test_egress_failure_has_correct_decision_even_in_cause`: `_upstream_failure`의 `httpx` 미정의.

사용자의 기존 시험 변경 중단 규칙에 따라 이 실패 확인 뒤 기능 구현·기존 시험 수정은 중단하고 근거 문서를 남겼다. 새 시험의 이미지 경로 선택만 정리하고 로컬 검사를 재확인했다. 이 보고서를 완료·회귀 통과로 해석하지 않는다.

## 실패·미완료·한계

- 기존 시험 2건 오류, 로컬 모듈 import 실패 및 lint 도구 부재는 위 표대로 남는다.
- 과거 정상/도구 오류의 `is_error`·문구가 저장되지 않았다면 업무 미확인이다. 일반 본문이 월 할당량 오류 접두어로 시작하는 오탐 가능성이 있다. 다른 공급자별 문구는 분류하지 않는다.
- 실제 PostgreSQL 스키마 반영·조회 SQL·체인 7/8 혼합 원장·재시작·경쟁/복구, 솔루션 기기 배포, PJ1 실제 하네스·OSS MCP, 브라우저 렌더링은 **미실행**이다.
- 독립 효과의 사람이 한 확인은 기존 dispatch intent 증거다. 자동 외부 효과 검사기는 구현하지 않는다.
- 외부 공개 스킬은 자료로만 읽었고 원격 commit·유지보수 현황 고정은 미완료다. 현재 판본이나 실사용 호환을 주장하지 않는다.
- 커밋 미완료: 이 작업 환경은 `.git` 읽기 전용이다. 지정 파일에 대한 `git add -- ...`가 `.git/index.lock: Permission denied`로 실패했다. 승인 요청이 허용되지 않아 권한 우회나 다른 작업 트리 사용은 하지 않았다. 변경은 미스테이징 작업 트리에 보존되며 푸시하지 않았다.

예정 커밋 메시지:

```text
feat(v2): 호출 결과의 네 축 기록과 조회를 분리

정책 허용·MCP 응답·업무 결과·독립 효과가 섞이지 않도록 outcome 스냅샷과 조회 투영을 추가한다.
새 JSONB는 체인 8판에 포함하고 과거 행은 다시 쓰지 않는다.
검증: Python 순수/대역 8건, 화면 함수 2건, 기존 콘솔 15건, 구문·문구 검사 통과.
기존 자격정보 AST 시험 2건의 의존성 주입 누락으로 중단; 기존 시험 미변경, 기기 검증 미실행.

Co-Authored-By: Codex sol <noreply@openai.com>
```

## 다음 작업

DEV-48: 사람이 기존 시험 대역 변경 여부를 결정하고 적대 검증한 뒤 솔루션 기기에서만 `field up`으로 배포한다. `full_stack_lab` 기준 게이트웨이 이미지에서 다음을 실행한다. 시험 파일은 이미지에 기본 포함되지 않아 `docker compose exec -T gateway python - --gateway < tests/outcome_axes_check.py`와 같은 stdin 실행은 `__file__` 경로를 잃으므로 사용하지 않는다. `docker compose cp tests/outcome_axes_check.py gateway:/app/tests/outcome_axes_check.py`로 전달한 뒤 실행한다.

```bash
docker compose exec -T gateway mkdir -p /app/tests
docker compose cp tests/outcome_axes_check.py gateway:/app/tests/outcome_axes_check.py
docker compose exec -T gateway python /app/tests/outcome_axes_check.py --gateway
node --check gateway/app/agent_static/console.js
node --test tests/console-state.test.mjs tests/outcome-console.test.mjs
```

새 시험의 `APP` 경로는 저장소에서는 `gateway/app`, 이미지에서는 `/app/app`을 선택한다. 배포 후 기존/신규 행을 함께 조회하고 관리자 실행 확인 전후 스냅샷 불변·효과 투영·전체 해시 체인을 확인한다. PJ1 실제 OSS MCP로 정상·정책 거부·할당량 실패·출력 보류를 원장과 대조한다. 검증 실패를 회피하도록 기대값을 완화하지 않는다.

## 사용자에게 필요한 입력

새 업무 권한·실사용 데이터·자격증명 입력은 없음. 기존 시험 변경 검토와 솔루션 기기/PJ1 검증은 사람의 후속 작업이다.
