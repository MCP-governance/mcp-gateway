# DEV-48 결과 4갈래 기록 적대 검토

- 검토자: Codex luna
- 범위: `git diff c002fbd..HEAD` (HEAD `9edfff54c93ceb445822c889edfc305df14634d0`, 기준 `c002fbd5fcf5f928e5ad68c57fa05edb1f76b1a6`); 병합 대상 `origin/main` `48eda394d2963846635a25b675005d5008e57482`
- 작업 방식: 읽기 전용. 구현·시험·기존 파일은 수정하지 않았다. 이 보고서만 새로 작성한다.

## 결론

**수정 후 병합.** 403 상태를 한도·인증 실패와 분리하고, 제안한 시험 대역 주입을 기존 시험 담당자가 반영·확인한 뒤 병합한다. 코드에서 append-only 위반이나 체인 8판의 명백한 과거 판 호환 파손은 찾지 못했다.

## 발견 사항

| 번호 | 심각도 | 문제 | 근거 파일:행 | 수정안 |
|---|---|---|---|---|
| 1 | 중간 | 업스트림 HTTP 403은 RFC 의미상 서버가 요청을 이해했지만 허용하지 않은 응답이다. 이를 `제공자 한도·인증 실패`로 단정하면 권한 거부가 인증 오류나 할당량 오류로 집계된다. | `full_stack_lab/gateway/app/outcomes.py:34-41`; 상태 추출 `full_stack_lab/gateway/app/core.py:1472-1473`; D-136 범위 `docs/ai/DECISIONS.md` D-136 | 401은 인증 실패, 429는 한도 초과로 분리하고 403은 `제공자 접근 거부` 같은 별도 값으로 표시한다. 기존 시험 기대값을 바꾸지 말라는 규칙에 따라 수정은 제안만 한다. 새 시험 파일에 403 경계를 추가한다. |
| 2 | 높음(병합 차단) | 기존 AST 대역 시험 두 건은 새 심볼이 namespace에 없어 `NameError`로 종료한다. 자격정보 비노출 검증 자체가 실행되기 전에 실패하므로 현재 브랜치로는 해당 회귀 확인이 완료되지 않았다. | `full_stack_lab/tests/dest_pin_credential_redaction_check.py:214-218,277-282`; 실패를 기록한 `research/llm-wiki/status/reports/2026-10-20-result-outcomes.md` | 아래 diff처럼 실제 `outcome_axes` 함수와 실제 `httpx` 모듈을 대역 namespace에 주입한다. assertion·테스트 입력·비밀 비노출 조건은 그대로 둔다. |
| 3 | 중간(병합 충돌) | 기준 이후 양쪽이 `docs/ai/DECISIONS.md`의 같은 끝 위치에 D-136과 D-137/D-141을 삽입했다. 세 기록을 모두 보존하고 순번대로 정렬하는 수동 병합이 필요하다. | `docs/ai/DECISIONS.md` 끝의 D-136, `origin/main` 끝의 D-137·D-141 | D-136, D-137, D-141 모두 보존하고 번호 순으로 배열한다. 아래 겹침 경로 중 나머지는 서로 다른 hunk로 보이며 자동 병합 가능성이 높다. |

## 분류·원장·체인·화면 확인

- **정책 거부와 통제 장애:** `P-CONTROL-*`, `P-DATA-INSPECTION-001`, `MCP-CATALOG-001`, `INPUT_CONTRACT`, `POLICY_BUNDLE`을 통제 장애 차단으로 분류한다. 그 외 Block은 정책 거부다. 출력 검사기 장애는 실행 경로에서 `control_failure=True`를 세우고 기존 `MCP-OUTPUT-001`과 응답 보류를 유지한다. 사용자 정책 거부를 통제 장애로 올려 잡는 직접 반례는 보이지 않았다.
- **관찰 모드:** `would_decision`은 outcome 축의 실효 판정을 덮어쓰지 않는다. D-136이 관찰값으로만 유지한다고 명시하므로 관찰 모드의 허용 기록은 의도된 동작이다. 새 시험도 `would_decision=Block`인 경우 실효 허용을 기대한다.
- **전송·독립 효과:** MCP 호출 직전의 `upstream_attempted`는 MCP 세션이 열린 뒤에만 세워지고, 세션 진입 이후 `upstream_connected`가 기록된다. 독립 효과는 관리자 확인 상태만 반영하며 pending/uncertain/resolved는 미확인으로 남긴다. 연결 플래그가 과거 행에 없어 과거 연결 단계는 복구할 수 없다는 한계가 문서에 적혀 있다.
- **append-only:** `v2_tables.sql`은 nullable 열 추가만 한다. `core._record_decision`은 새 outcome을 `INSERT`하고 지문에 포함한다. 이전 행을 `UPDATE`하는 경로는 변경분에서 찾지 못했다. 감사 투영은 과거 `error`를 내부 분류에만 사용하고 반환 전에 제거한다.
- **체인 8판 및 D-141:** `AUDIT_COLUMN_SETS[1..7]` 정의는 보존되고 8판에만 `outcome`이 추가된다. D-141의 `walk_chain`은 각 행의 `chain_version`으로 지문을 계산하므로 7판 뒤 8판이 이어지는 혼합 체인과 봉인 시작점을 설계상 수용한다. 병합 때 `origin/main`의 `walk_chain`, `retention` import, `verify_audit_chain(..., seal)` 위임을 모두 보존해야 한다. 실 DB의 혼합 체인·봉인 시험은 이 검토에서 실행하지 않았다.
- **콘솔 규칙:** 새 축 이름과 알려진 값은 한국어 라벨·값이며, 결과 상세의 영어 enum 원문 JSON 출력도 제거됐다. 설명 문단·개발 흔적·약어 혼용은 변경 hunk에서 발견하지 못했다. 실제 브라우저 렌더링은 미검증이다.

## 병합 충돌 경로

`git merge-tree --write-tree origin/main HEAD`는 `.git/objects` 쓰기 권한 거부로 결과 트리를 만들지 못했다. 기준에서 양쪽이 수정한 경로의 교집합을 구하고 변경 hunk를 대조한 결과는 다음과 같다. 이는 파일 경로 중첩과 hunk 비교이며, merge-tree가 산출한 트리 결과라고 주장하지 않는다.

| 경로 | 예상 | 해결 |
|---|---|---|
| `docs/ai/DECISIONS.md` | 충돌 예상: 양쪽 끝 삽입 | D-136·D-137·D-141을 모두 유지, 번호순 정렬 |
| `full_stack_lab/gateway/app/contract.py` | hunk 분리 | HEAD의 8판 열 정의와 main의 `walk_chain`을 함께 유지 |
| `full_stack_lab/gateway/app/core.py` | hunk 분리 | outcome 삽입·기록과 main의 retention 기반 `verify_audit_chain`을 함께 유지 |
| `full_stack_lab/gateway/app/agent_static/console.js` | hunk 분리 | outcome UI와 공급자 보증 UI·등록부 동작을 모두 유지 |
| `research/llm-wiki/status/backlog.md` | 행 분리 | DEV-48 결과와 DEV-67/68 갱신을 모두 유지 |

## 기존 시험 수정 제안 diff

시험의 예상값이나 비밀 비노출 assertion은 변경하지 않는다. AST로 추출한 production 함수에 실제 순수 함수와 제품 의존성 모듈을 주입한다.

```diff
diff --git a/full_stack_lab/tests/dest_pin_credential_redaction_check.py b/full_stack_lab/tests/dest_pin_credential_redaction_check.py
--- a/full_stack_lab/tests/dest_pin_credential_redaction_check.py
+++ b/full_stack_lab/tests/dest_pin_credential_redaction_check.py
@@
 import hashlib
 import importlib.util
+import httpx
@@
 APP = LAB / "gateway" / "app"
 ROOT = LAB.parent
+outcome_spec = importlib.util.spec_from_file_location("outcomes_under_test", APP / "outcomes.py")
+outcome_module = importlib.util.module_from_spec(outcome_spec)
+outcome_spec.loader.exec_module(outcome_module)
@@
         module = selected(APP / "core.py", ["_upstream_failure"],
                           {"DestinationBlocked": destination.DestinationBlocked,
+                           "httpx": httpx,
                            "_root_cause": lambda exc: "safe error",
@@
         env = {"secret_scan": scanned, "db": SimpleNamespace(transaction=transaction), "Jsonb": lambda v: v,
+               "outcome_axes": outcome_module.outcome_axes,
                "datetime": datetime, "UTC": timezone.utc, "hashlib": hashlib, "GENESIS": "0" * 64,
```

**성질 약화 판정:** 약화하지 않는다. 두 namespace에 실행 의존성만 공급한다. `CredentialRedaction`의 토큰 비포함 assertion, 저장·응답 본문 검사, redaction 이전의 해시 입력 검사는 그대로 유지된다. `httpx`는 제품 모듈과 같은 클래스를 사용하므로 `isinstance`의 실제 의존성도 충족한다.

## 병합 후 필수 확인과 남은 한계

- 기존 시험 수정 diff는 제안일 뿐 적용·실행하지 않았다. `.git` 읽기 전용 환경에서 `merge-tree --write-tree`가 실패했고, 요청된 솔루션 기기/PJ1 및 DB 검증은 이 적대 검토 범위 밖이다.
- HTTP 403 분류를 수정하지 않으면 호출은 차단되지 않지만 감사·화면의 도구 업무 축에서 공급자 권한 거부를 인증/한도 실패로 오표시할 수 있다.
- 자연어 결과가 정확히 `Monthly quota exceeded` 또는 `Monthly quota reached`로 시작하면 실제 문서 본문도 공급자 오류로 오인될 수 있다. D-136이 한계로 이미 기록했지만 재현 가능한 경계가 남는다.
- 상태 기록만으로 배포·실제 공급자 응답의 형태·관리자 독립 효과 확인을 입증할 수 없다.
