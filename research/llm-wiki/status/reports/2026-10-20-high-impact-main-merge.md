# 2026-10-20 DEV-70 main 병합 충돌 해결

- 작업자: Codex sol
- 코드 기준: `10/20-high-impact`, 시작 HEAD `11e09cbe6ebc2eee70ad04aba8e280902625c17e`, 병합 대상 MERGE_HEAD `60afcb1ec8519e3eca4c4e5abae26592efc197df`. 사람이 시작한 `git merge --no-commit origin/main`의 미커밋 작업 트리에서만 수정했다.
- 시작 근거: DEV-70 / D-139, main의 DEV-69 / D-138·DEV-71 / D-143, [중대 영향 요구사항](../../analysis/high-impact/README.md), 사용자 지시의 luna 검토 두 항목.
- 완료 조건: 양쪽 기능·기존 시험을 보존해 충돌 표시를 제거하고, 관찰 모드 중첩 회귀와 처리자 표시 이름을 추가한다. 인덱스 충돌 해제와 병합 커밋은 사람이 수행한다.

## 결과

| 충돌 파일 | 해결 방침 |
| --- | --- |
| `docs/ai/DECISIONS.md` | D-138·139·143 등 양쪽 절의 내용을 보존하고 동시 추가 구간을 D-136·137·138·139·141·143 순으로 정렬. D-139에 병합 보강·근거·한계를 추가 |
| `full_stack_lab/gateway/app/agent_contract.py` | `model_validator`와 `field_validator`를 모두 유지해 중대 영향 라벨·위험 입력 검증을 보존 |
| `full_stack_lab/gateway/app/agent_service.py` | 승인 목록 SQL에 `a.explanation`과 `d.residency_targets`를 함께 유지 |
| `full_stack_lab/gateway/app/agent_static/console.js` | 중대 영향 범위 심사와 위치 재심사 액션을 모두 유지 |
| `full_stack_lab/gateway/app/core.py` | `high_impact`·`residency` import, 두 정책 접두어의 관찰 모드 강제 집행, 등록 사건의 영향 영역·위치를 함께 유지 |
| `full_stack_lab/gateway/app/v2_tables.sql` | 설명·철회 열과 위험 입력 열을 모두 추가형 SQL로 유지 |
| `research/llm-wiki/status/backlog.md` | DEV-69·71은 main의 진행 상태를, DEV-70은 이 레인의 진행 상태를 유지. DEV-70의 마지막 상태 칸만 후속 갱신 |

자동 병합된 `POLICY.md`의 양쪽 기능 설명도 보존하고 주요 정책 표에 48·83의 위치 규칙을 추가해 2013의 중대 영향 규칙과 우선순위 순으로 보인다. `policy_ledger.json`의 66개 정책에 우선순위 중복이 없으며 새 정책 ID·의존성은 추가하지 않았다. 기존 OPA 규칙·시험은 main의 변경을 그대로 보존했다.

설명 증빙 조회는 사건에 나타나는 주체의 현재 `principals.display_name`을 한 번 조회해 `actor_display_name`으로 덧붙인다. 화면은 표시 이름을 HTML 이스케이프해 표시하고, 이름이 없거나 삭제된 주체이면 `—`를 표시한다. 원래 `actor`는 감사 식별자로 내보내기에 유지하며 판정 신원·감사 원장 행은 바꾸지 않는다. 표시 이름은 과거 사건 시점의 이름 스냅샷이 아니다.

추가 시험:

- `tests/high_impact_check.py`: 표시 이름 조회·미등록/이름 없는 주체·감사 식별자 유지 1건. 기존 시험 함수 19개 본문은 AST 대조로 동일함을 확인했다.
- 같은 파일의 이미지용 회귀 4건, 하위 사례 18개: 관찰 모드에서 중대 영향과 `P-RESIDENCY-001` 금지, `P-RESIDENCY-002` 승인 필요, `P-CONSENT-001` 동의 누락, 선택되지 않은 위치 정책 충돌을 대조한다. 유효한 개별 승인·위조 승인, 동의 누락의 동시 조건을 포함하며 `decision`·`policy_id`·관찰 투영 없음·미전송을 확인한다. 위치 승인 대기에는 전송하지 않고, 실행 가능한 재판정에는 동의 누락을 차단한다.
- `tests/high-impact-evidence-console.test.mjs`: 실제 화면 함수 추출로 표시 이름·누락/빈 값의 `—`·HTML 이스케이프·내부 식별자 비표시 1건.

## 검증

2026-10-20 01:27 KST 기록. 원본 명령·종료 코드·출력은 [main-merge-checks.json](../../analysis/high-impact/main-merge-checks.json)에 보존한다. 아래의 통과 수에서 생략한 시험은 제외했다.

| 확인 종류 | 명령·환경 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 구문 | 변경 Python 파일에 `python -m py_compile` | 20파일 통과 | main-merge-checks.json / compile-and-structure |
| JS 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | node-syntax |
| 중대 영향 순수/DB 대역 | `python -X utf8 full_stack_lab/tests/high_impact_check.py` | 17건 통과, 이미지용 7건 생략 | python-units |
| 위치 규칙 순수 함수 | `python -X utf8 full_stack_lab/tests/data_residency_check.py` | 8건 통과 | residency-units |
| 위험 등급 | `python -X utf8 full_stack_lab/tests/intake_risk_tier_check.py` | 12건 통과, 의존성 필요 13건 생략 | risk-units |
| 세션 재사용 | `python -X utf8 full_stack_lab/tests/upstream_session_reuse_test.py` | 40건 통과 | session-units |
| Node 함수 | `node --test`의 console-state·high-impact-console·high-impact-evidence-console·outcome-console·resource-values 5파일 | 25건 통과 | node-units |
| 인증 경계 | `python -X utf8 full_stack_lab/tests/open_endpoints.py` | 공개 API 1개·인증 필요 79개 문서 대조 통과 | auth-routes |
| 위치 팩 정합성 | `python -X utf8 full_stack_lab/registry/render_residency.py --check` | 통과 | residency-render |
| 병합 구조 | 충돌 표시·관리대장 우선순위·결정 순서·기존 중대 영향 시험 함수 대조, `git diff --check` | 충돌 표시 0, 우선순위 중복 0, 결정/기존 시험 대조·공백 검사 통과 | compile-and-structure / diff-whitespace |
| 게이트웨이 import 시도 | `python -X utf8 full_stack_lab/tests/high_impact_check.py --gateway`, Windows Python 3.10 | 실패: `from datetime import UTC` 불가. 게이트웨이 본체/추가 중첩 회귀는 미실행 | gateway |
| 원격 HEAD 조회 시도 | `git ls-remote --symref origin HEAD` | github.com:443 연결 실패. 로컬 MERGE_HEAD만 고정 | 작업 중 도구 출력 |
| 실제 DB·OPA·브라우저 | 스키마·경쟁·트리거·실제 OPA·화면 렌더링 | 미실행 | — |
| 프로토콜·실제 모델/하네스 | 솔루션 기기·PJ1의 공개 OSS MCP | 미실행 | — |
| upstream 효과·배포·정책 해시 | 독립 효과·실제 기기 revision | 미확인·미실행 | — |

## 기존 시험 변경 필요

이번 충돌 해결·보강 때문에 기존 시험 기대값을 바꿔야 한다고 확인된 항목은 없다. 새 메서드와 새 Node 파일만 추가했으며, main에서 이미 병합 대기 중이던 세션·도입 시험 보완은 보존했다. 이 보고는 전체 회귀 통과를 주장하지 않는다.

## 실패·미완료·한계

- 충돌 표시 7파일은 모두 해결했지만 `.git` 쓰기 금지에 따라 `git add`·커밋을 하지 않았다. 인덱스에는 동일한 7파일이 계속 `U`로 남는다. 작업 트리의 내용 해결과 Git의 충돌 해제는 구분한다.
- `s4-high-impact.md`는 작업 트리와 `origin/main` ref 모두에 없다. 사용자 메시지의 두 검토 항목만 반영했으며 검토 원문 전체를 읽었다고 주장하지 않는다.
- Python 순수/대역 시험 77건·Node 25건은 실제 PostgreSQL·OPA·SDK 통합·MCP 호출·독립 효과의 증거가 아니다. 이미지용 새 중첩 회귀는 실행되지 않았다.
- 신규 원문/외부 코드·스킬은 도입하지 않았다. 기존 [D-139의 SDK/OSS 검토](../../analysis/high-impact/README.md#oss공개-스킬-사전-검토)를 재사용했다. 최신 원격 상태 확인은 실패했다.
- `status/current.md`와 다른 작업자의 변경은 수정하지 않았다. 옛 소스 스냅샷·시험 증거를 새 통과 결과로 덮어쓰지 않았다.

## 다음 작업

DEV-70 / D-139: 사람이 인덱스 충돌을 해제하고 병합 커밋한 뒤, **솔루션 기기**에서 `./console.sh field up`으로 반영하고 해당 이미지에서 시험한다. 아래 명령은 이번 PC에서 실행하지 않았다.

```bash
cd full_stack_lab
./console.sh field up
docker compose cp tests/high_impact_check.py gateway:/tmp/high_impact_check.py
docker compose exec -T gateway python -X utf8 /tmp/high_impact_check.py --gateway
docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy
```

DEV-69·71 회귀도 솔루션 기기에서 전체 checkout을 읽는 게이트웨이 이미지로 실행한다.

```bash
docker compose run --rm --no-deps -v "$PWD:/work:ro" -w /work --entrypoint python gateway -X utf8 tests/data_residency_check.py --gateway
docker compose run --rm --no-deps -v "$PWD:/work:ro" -w /work --entrypoint python gateway -X utf8 tests/intake_risk_tier_check.py
```

실제 DB의 승인/범위/철회 경쟁과 append-only, 실제 콘솔 표시·PJ1 하네스의 공개 OSS MCP 호출 및 독립 효과를 이어서 확인한다. 자체 MCP 서버를 만들지 않는다.

## 사용자에게 필요한 입력

없음. 인덱스 충돌 해제·병합 커밋·솔루션 기기/PJ1 검증은 지정된 사람 작업으로 남겼다.
