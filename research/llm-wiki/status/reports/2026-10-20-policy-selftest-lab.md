# 2026-10-20 정책 배포 후 경보 자체 시험 실험실

- 작업자: Codex luna
- 코드 기준: `07bfed8fa73ca311dfb4e707a4ad44ecb73dae2d`, 브랜치 `10/20-policy-selftest-lab`, 시작 시 dirty. 이번 수정은 시험 파일·D-121 기록·DEV-60 백로그·이 보고서이며 기존 `ops_response.py` 변경은 보존했다. 커밋 없음.
- 시작 근거: DEV-60 / WBS G06.05 / POL-42 / D-121, [기존 작업 E](2026-10-17-ops-response-d120-d123.md), [OPS_RESPONSE.md](../../../../docs/ai/OPS_RESPONSE.md), 기존 `termination_dispatch_lab.sh` 격리 실행기.
- 해결할 문제와 완료 조건: 현재 OPA 정책으로 D-121 자체 시험·합성 경보 저장·호출 통계 분리를 실제 PostgreSQL/OPA에서 확인하고, 규칙 제거와 OPA 장애를 실패 레코드·경보로 남기는 기기 시험을 추가한다.

## 결과

`ops_response.self_test`의 정책 정보 조회 예외도 실패 행으로 보존하고, 모든 자체 시험 실패에 `synthetic=true`인 `policy-self-test-failed` 경보를 남기도록 보강했다. DB 저장 실패는 호출자가 감시 루프에 남기며 다음 주기에 재시도한다. 기존 결정 ID·DB 구조·MCP 요청 경로는 바꾸지 않았다.

새 [policy_selftest_pg_check.py](../../../../full_stack_lab/tests/policy_selftest_pg_check.py)는 기존 랩의 `wbs-c-opa`를 통해 현재 OPA 1.20.2 정책 6건의 판정 ID와 다섯 합성 경보를 검증한다. 이후 `GET /v1/policies`에서 파일 원본과 정확히 일치하는 유일한 모듈 ID를 찾아 그 ID에 `P-ANOMALY-001` 규칙을 제거한 판본을 올리고 실패 행·합성 경보를 확인한다. PUT 오류는 OPA 응답 본문을 예외에 포함한다. 교체 요청 직전부터 `finally` 복구를 시도하며, 복구 실패는 명시적 오류로 시험을 실패시킨다. OPA 연결 불능 역시 실패 행·합성 경보를 확인한다. 매 단계 전후 `decisions` 및 실제 호출 집계가 불변인지 확인하며 MCP 서버는 호출하지 않는다.

실험실의 기존 `termination_dispatch_remote.sh`는 이미 고정 `openpolicyagent/opa:1.20.2-static` 컨테이너를 `wbs-c-opa`로 띄우고 `$SRC/opa`를 `/policy:ro`로 마운트한다. 게이트웨이 시험 컨테이너에도 같은 정책 디렉터리와 `OPA_URL`을 전달하므로 셸 실행기 변경은 불필요했다. 제품 `mcpgw-*` 컨테이너는 건드리지 않는다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 문법 | `python -m py_compile full_stack_lab/gateway/app/ops_response.py full_stack_lab/tests/policy_selftest_pg_check.py` | 통과 | 로컬 실행 |
| 실험실 셸 문법 | `bash -n full_stack_lab/tests/termination_dispatch_remote.sh full_stack_lab/tests/termination_dispatch_lab.sh` | 통과 | 로컬 실행 |
| pyflakes | `cd full_stack_lab && python -m pyflakes gateway/app/*.py tests/*.py supply_chain/*.py ../endpoint-agent/*.py field/pc/mcpgw_pc.py` | 미실행: Python 3.10 환경에 `pyflakes` 모듈 없음 | 터미널 출력 |
| 위협 매핑 | `python research/llm-wiki/tools/map_threats.py` | 이번 수정 후 통과: 정책 24개 매핑, 모든 코드 경로 존재 | 터미널 출력 |
| 위키 CI 검사 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 이번 수정 후 오류 0, `ok=true`; ignored 로컬 원문 누락 경고는 기존 상태 | 터미널 출력 |
| 실제 PostgreSQL·OPA | 솔루션 기기 `tests/termination_dispatch_lab.sh run policy_selftest_pg_check.py` | 미실행, 기기에서 수행 필요 | 없음 |
| 배포·PJ1 | 솔루션 배포·PJ1 하네스 | 미실행 | 없음 |

## 실패·미완료·한계

- 규칙 제거는 OPA 관리 API로 실제 로드된 원본 모듈을 교체한다. 시험 `finally`에서 같은 ID로 원본을 다시 올리며, 강제 종료 시에는 코드의 `finally`가 실행되지 않을 수 있다. 이 OPA와 DB는 `wbs-c-*` 전용이며 랩 `down`으로 폐기한다.
- DB 장애 시 실패 자체를 DB에 저장할 수는 없다. 감시 루프가 예외를 기록하고 다음 주기에 재시도한다.
- 실제 OPA·DB 시험, 배포, 검수 전이므로 DEV-60 완료가 아니다. `check_wiki`의 기존 ignored-source 경고도 오류로 세지 않았으나 원문 확보 상태는 별도 정리 대상이다.
- 원격 HEAD 조회는 GitHub 네트워크 연결 실패로 확인하지 못했다. 현재 브랜치와 기준 커밋은 로컬에서 확인했다.

## 다음 작업

DEV-60 기기 검증: `cd full_stack_lab`, `tests/termination_dispatch_lab.sh up`, `tests/termination_dispatch_lab.sh run policy_selftest_pg_check.py`, 완료 뒤 `tests/termination_dispatch_lab.sh down`. 성공 출력과 PostgreSQL 행·OPA 상태를 보관하고 합성 경보가 실경보 조회 및 대시보드 실호출 집계에 나타나지 않는지 확인한다.

## 사용자에게 필요한 입력

없음. 기존 솔루션 기기와 지정된 격리 랩으로 실행할 수 있다.

## 기기 실행 (Claude, 2026-10-20)

- 격리 실험실 실제 OPA(wbs-c-opa)·PostgreSQL: `policy_selftest_pg_check.py` 7/7. 시험의 규칙 제거 함수가 `candidate[...] := {값} if {본문}`의 본문을 남겨 OPA가 400(구문 오류)을 냈던 것을 Claude가 고쳤다.
- 변이 확인: `ops_response.py` 보강을 빼면 "깨진 정책"·"OPA 불능" 2건이 실패한다 — 정책 정보 조회 오류 때 자체 시험이 실패 기록·경보 없이 끝나던 공백이 실제였다.

