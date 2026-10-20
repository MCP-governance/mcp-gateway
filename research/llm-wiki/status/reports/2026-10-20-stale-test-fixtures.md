# 2026-10-20 낡은 시험 대역 보정

- 작업자: Codex luna
- 코드 기준: `a7aa43a1970333a28aaf9050ebaa476d8673c098`, 브랜치 `10/20-stale-tests`; 기존 분류 작업 변경을 보존하고 `protocol_versions_check.py`, `full_stack_lab/README.md`, backlog 상태와 이 보고서를 후속 변경
- 시작 근거: [오래 실패한 시험 분류](../../analysis/stale-tests-1020/README.md), D-123·D-149·D-116
- 해결할 문제와 완료 조건: D-123·D-149 계약 변경을 세 시험 대역에 반영하고 기대값·검사 범위를 유지한다. 변경 hunk별 이유를 분석 README에 기록한다. 제품 코드는 수정하지 않는다.

## 결과

`oauth_rotation_check.py`에 D-123 계열 조회 커서 대역과 기존 `isolated_disposal()` 도구를 연결했다. `protocol_versions_check.py` 대역이 D-149 네 번째 인자를 받도록 했다. `system_metrics_check.py`의 합성 MCP claims에 `jti`를 더하고 서명 폐기 조회를 false로 고정했다. 세 파일의 assertion 및 제품 코드는 변경하지 않았다.

각 최초 대역 보정 hunk의 근거는 [분류 분석의 적용 hunk별 이유](../../analysis/stale-tests-1020/README.md#적용-hunk별-이유)에 있다. 이 후속 수정은 protocol 협상·도구 목록 호환을 다루는 DEV-44에 연결해 상태 칸만 갱신했고 `status/current.md`는 수정하지 않았다.

후속 수정으로 `protocol_versions_check.py`의 provider 연결 직전에만 `_internal_endpoint`가 해당 실행의 임시 provider URL을 승인하도록 주입했다. 승인 URL은 정확히 일치해야 하고, `upstream.session()`이 만드는 `PinnedBackend`의 목적지 고정과 DNS 확인은 그대로 돈다. 이를 통해 시험이 확인하는 SDK `InputRequiredResult` → `MCPError` 경로는 유지하면서 D-116의 loopback 차단을 끄지 않는다. 근거와 범위는 [실습 README의 검증 절](../../../../full_stack_lab/README.md#5-검증)에 기록했다. DEV-44 백로그 마지막 상태 칸은 게이트웨이 이미지 재실행·PJ1 대기로 갱신했다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 문법 | `python -X utf8 -m py_compile tests/oauth_rotation_check.py tests/protocol_versions_check.py tests/system_metrics_check.py` (로컬 Python 3.10) | 통과 | 명령 종료 코드 0 |
| 기대값·검사 범위 보존 | HEAD와 작업 파일의 assert AST 및 test 메서드 이름 비교 | 세 파일 모두 동일 | AST 비교 스크립트 출력 |
| OAuth 단위 시험 | `python -X utf8 tests/oauth_rotation_check.py` (로컬 Python 3.10) | 시작 실패: `datetime.UTC`를 Python 3.10 표준 모듈에서 import할 수 없음 | 콘솔 출력 |
| 시스템 지표 시험 | `python -X utf8 tests/system_metrics_check.py` (로컬 Python 3.10) | 시작 실패: FastAPI 미설치 | 콘솔 출력 |
| pyflakes | `python -m pyflakes gateway/app/*.py tests/*.py supply_chain/*.py ../endpoint-agent/*.py field/pc/mcpgw_pc.py` (로컬) | 실행 불가: `pyflakes` 모듈 미설치 | 콘솔 출력 |
| 위키 CI 검사 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 통과, `errors: []`; 기존 ignored local-sources 경고 | 명령 JSON 출력 |
| 공백 검사 | `git diff --check` | 통과 | 종료 코드 0 |
| OPA·실제 Gateway·실제 DB·PJ1 | 이번 시험 대역 전용 변경 | 미실행 | 솔루션 기기에서 실행 필요 |

이번 후속 수정에서 실행한 검사는 별도로 아래에 기록한다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 문법 | `python -X utf8 -m py_compile full_stack_lab/tests/protocol_versions_check.py` (로컬) | 통과 | 명령 종료 코드 0 |
| pyflakes | `python -m pyflakes gateway/app/*.py tests/*.py supply_chain/*.py ../endpoint-agent/*.py field/pc/mcpgw_pc.py` (`full_stack_lab`, 로컬) | 실행 불가: `pyflakes` 모듈 미설치 | Python 오류 출력 |
| 위키 CI 검사 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` (로컬) | 통과, `errors: []`; 기존 ignored local-sources 누락 경고 | 명령 JSON 출력 |
| Gateway 이미지의 protocol 시험·PJ1 | 솔루션 기기 | 미실행 | 사용자 제공 이전 실행에서 해당 시험은 실패 상태 |

## 실패·미완료·한계

로컬 Python이 3.10이라 OAuth 실행이 제품 import보다 먼저 `datetime.UTC`에서 멈췄고 FastAPI가 없어 시스템 지표 시험도 실행하지 못했다. 프로토콜 시험은 `/app`의 이미지 모듈을 우선 가져오므로 로컬 실행으로 확인하지 않았다. pyflakes도 설치되지 않았다. 위키 검사에는 저장소에 이미 선언된 ignored local-sources 누락 경고가 있으나 오류는 없다.

## 다음 작업

솔루션 기기 게이트웨이 이미지에서 아래 세 시험을 실행하고 결과를 이 보고서에 추가한다.

```bash
cd full_stack_lab
docker compose run --rm --no-deps --entrypoint python -v "$PWD/tests:/tests:ro" gateway /tests/oauth_rotation_check.py
docker compose run --rm --no-deps --entrypoint python -v "$PWD/tests:/tests:ro" gateway /tests/protocol_versions_check.py
docker compose run --rm --no-deps --entrypoint python -v "$PWD/tests:/tests:ro" gateway /tests/system_metrics_check.py
```

## 사용자에게 필요한 입력

없음.
