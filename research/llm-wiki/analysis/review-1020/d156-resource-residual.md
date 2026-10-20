# D-156 (DEV-08) 자원 잔존 적대 검토

- 검토자: Codex luna
- 코드 기준: `10/20-resource-residual-review`, 시작 `877a5138574308fd18ee72817f3d9712f6af114e`, 시작 작업 트리 clean
- 대상: Codex sol의 D-156 변경 및 새 시험. 별도 제품 코드 수정 없음.
- 원격 HEAD: `git ls-remote --symref origin HEAD`를 시도했으나 github.com:443 연결 실패. 최신 원격 상태는 확인하지 못함.

## 검토 결론

확인한 코드·시험 범위에서 D-156이 새로 만든 확실한 결함은 재현하지 못했다. 제품 코드와 기존 시험의 실행 기대값은 변경하지 않았다. 로컬 13건 시험은 통과했다. PostgreSQL/Gitea 시험과 실제 기기·PJ1 시험은 미실행이므로 배포 동작이나 실제 자원 서버 효과를 입증한 결론은 아니다.

## 반박 항목

| 반박 | 확인 | 판정·한계 |
| --- | --- | --- |
| 1. 이미 종결된 케이스를 재판정해 등급이 바뀌거나 append-only 원장이 수정되는가 | `decommission.assess`는 `CLOSED`를 거부한다. `reopen_case`는 사유를 남기고 현재 grade/criteria를 초기화한 뒤 `REOPENED`로 바꾼다. 새 사실은 `add_evidence`의 새 행으로 기록되고, `_invalidate`는 현재 판정 스냅샷을 무효화한다. | 종결 케이스는 재개 절차 없이는 등급이 바뀌지 않는다. 재개 후 등급은 유지된 기존 증거와 새 증거로 다시 산정될 수 있다. 증거 원장은 append-only지만 케이스의 현재 판정·상태는 갱신되는 스냅샷이다. 기존 판정의 별도 불변 이력 테이블은 확인하지 못했다. 이는 이번 D-156 변경에서 도입한 회귀가 아니다. |
| 2. 활성 계정의 갱신 토큰을 관리형 전환 중 또는 OIDC 공급자에서 오판하는가 | `idp.introspection`은 refresh 행의 폐기·회전·만료를 먼저 확인하고, 매 조회에서 현재 계정 존재·활성 및 `managed_required`를 검사한다. `AUTH_PROVIDER=oidc`이면 로컬 갱신 토큰을 비활성으로 반환한다. DB 오류는 이전 활성 응답으로 대체하지 않고 전파된다. `/oauth/token`은 두 grant 모두 `local_login_allowed()`를 거친다. | 기존 계정 활성 정상군, 정지 후 복구, 계정 없음, 관리형 전환, OIDC 전환, 폐기·회전·만료·서명 목록·DB 실패 분기가 새 13건에 있다. 경쟁 중 계정 상태 변경의 원자적 일관성이나 실제 OIDC 공급자 연동은 이 대역 시험으로 입증되지 않는다. |
| 3. resource-rejection가 없어도 정상 종료가 C3에서 영원히 막히는가 | `_judge_target`은 대상에 연결된 최신 상태 증거를 사용한다. 폐기 후 `introspection(active=false)` 또는 유효한 credential/provider 증거가 확인되면 C3의 전파 미확인 조건을 해소한다. 자원 수락 증거는 C3 미충족/T2로 우선한다. 상태 비저장 토큰의 폐기~만료 공백은 별도로 C3 미충족/T2다. 자원 증거 자동 수집은 고지된 Gitea server-held-credential 경로이고, 일반 대상에는 관리자 증거 등록 API가 있다. | 자원 거부 증거는 필수 조건이 아니므로 정상적인 상태 저장 토큰이 이것 없다는 이유만으로 T1을 영원히 얻지 못하지 않는다. 임의 토큰을 자동 열거·시험하는 경로는 없다. 관리자 증거 등록은 수동 입력이고 증거의 외부 진위는 별도 확인이 필요하다. 외부 서버가 비활성 introspection을 반영하는지까지 자동 확인하지는 않는다. |
| 4. 종료 문서와 코드 규칙이 어긋나는가 | 문서는 토큰 대상에도 resource-rejection을 상태 증거로 인정하고, 폐기 뒤 수락은 T1을 막고, 폐기 전 증거는 제외한다고 설명한다. 코드 `STATE_EVIDENCE_FOR`, `_judge_target`의 수락 우선·`revoked_at` 필터와 일치한다. | 코드와 설명 사이의 불일치는 확인하지 못했다. 등록된 자원 전체나 복제·외부 캐시 토큰을 다 조사했다고 보지 않는 문서의 한계도 코드 범위와 맞는다. |

## 시험 및 기록

- `python -B -X utf8 full_stack_lab/tests/resource_residual_check.py -v`: 13/13 통과.
- `python -m py_compile full_stack_lab/gateway/app/idp.py full_stack_lab/gateway/app/decommission.py full_stack_lab/tests/resource_residual_check.py full_stack_lab/tests/resource_residual_pg_check.py full_stack_lab/tests/termination_flow.py`: 통과.
- `python -m pyflakes ...`: 실행 불가. 현재 `python`은 Python 3.10이고 `pyflakes` 모듈이 설치되어 있지 않음. 새 pyflakes 경고 0이라고 주장하지 않음.
- `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources`: 오류 0. ignored local-sources 누락 경고는 기존 자료 목록 범위이며 이번 검토로 수정하지 않음.
- `git diff --check`: 통과.
- 미실행: `resource_residual_pg_check.py`, 기존 전체 `termination_flow.py` 랩 실행, 솔루션 기기 배포, PJ1 하네스, 실제 외부 자원 서버·컨테이너 제거. 기존 시험 기대값 변경 없음.

## 기존 시험 변경 필요

없음. 추가 회귀 시험도 확실한 신규 결함이 확인되지 않아 만들지 않았다. D-156의 `resource_residual_check.py` 13건은 변경 전 결함 재현 및 수정 후 회귀 근거로만 확인했다.

## 남은 한계

- 외부 자원 서버의 introspection 캐시 TTL·토큰 복제 여부·미고지 자격은 이 코드만으로 확인할 수 없다. RFC 7662 §4도 자원 서버의 introspection 응답 캐시가 최신성(liveness)과 성능 사이의 교환임을 설명한다.
- 평가 등급은 케이스의 현재 상태이며, 불변 감사 원장에 과거 등급 전체를 별도 버전으로 저장하지 않는다. 이번 변경은 기존 생명주기 방식을 바꾸지 않았다.
- PG 시험은 격리 랩에서, 실제 자원 서버·MCP 효과는 지정 기기와 PJ1에서 이어서 확인해야 한다.
