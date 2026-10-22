# 2026-10-21 로컬 회귀 입력과 플랫폼 조건 정정

- 작업자: Codex
- 코드 기준: 공용 브랜치 `10/21-sheet-runtime-completion`. 변경 파일은 `full_stack_lab/tests/intake_one_click_check.py`, `dev73_rework_check.py`, `data_residency_check.py`와 이 보고서다.
- 시작 근거: 10-21 로컬 전체 회귀의 세 파일 실패. DEV-73 로컬 마운트 검증, 도입 승인, 데이터 위치 검증의 기존 기대값을 유지한다.
- 해결할 문제: 제품 동작을 검증하기 전에 macOS 임시 경로와 Linux 전용 파일 시스템 가정, 누락된 요청 필드 때문에 시험이 오류로 끝났다.

## 결과

`intake_one_click_check.py`의 공급자 파일 시험은 `TemporaryDirectory` 경로를 정규 경로로 바꾼다. macOS의 `/var`는 `/private/var` 심볼릭 링크라 기존 미해결 임시 경로를 제품의 안전한 파일 읽기가 거부했다. 동일한 통제된 임시 폴더를 정규 경로로 주자 `legal_entity`와 보안 연락처 등 기존 단언이 그대로 통과했다. 제품의 심볼릭 링크 거부 코드는 바꾸지 않았다.

`dev73_rework_check.py`의 반복 마운트 시험은 Linux `/proc/<pid>/fd`가 있어야 끝까지 검증된다. macOS에서 `/var` 문제를 제거하고 다시 실행했을 때도 `/proc` 부재로 실패하는 것을 확인했다. 이 단일 시험에 `/proc/self/fd` 존재 조건을 붙여 procfs가 없는 환경에서 건너뛴다. 다른 마운트 경합 시험 2개를 포함한 나머지 시험은 그대로 실행된다. Linux 파일 설명자 결속은 이 macOS 결과로 통과했다고 주장하지 않는다.

`data_residency_check.py --gateway`의 두 요청 fixture에 기존 정상 등급인 `nonimportant`를 명시했다. 제품 등록 경로가 필수 `data_class`를 읽기 전에 KeyError가 나서 위치 대체 및 같은 신청 재사용 차단 단언에 도달하지 못하던 문제다. 두 시험은 수정 후 기존 기대 메시지와 네트워크 호출 없음 단언을 통과했다. 게이트웨이 제품 코드는 수정하지 않았다.

## 검증

| 확인 종류 | 환경과 범위 | 결과 | 증거 |
| --- | --- | --- | --- |
| 도입 승인 | macOS Python 3.13.7, 로컬 venv | 19건 실행, 통과 19, 오류 0, 건너뜀 0 | `intake_one_click_check.py` 출력 |
| DEV-73 로컬 검사 | 같은 환경 | 21건 실행, 통과 20, 오류 0, 건너뜀 1 | `dev73_rework_check.py` 출력 |
| 데이터 위치 검증 | 같은 환경, `--gateway` | 15건 실행, 통과 15, 오류 0, 건너뜀 0 | `data_residency_check.py` 출력 |
| 구문과 공백 | 변경 시험 파일 | 통과 | 로컬 검사 결과 |
| Linux `/proc` 실제 검증 | 솔루션 기기 | 미실행 | 해당 없음 |
| 제품 배포와 PJ1 | 솔루션 기기와 실제 하네스 | 미실행 | 해당 없음 |

## 실패, 미완료, 한계

전체 55건 중 macOS에서 실제 통과한 것은 54건이며 1건은 Linux 전용으로 건너뛰었다. 파일 단위 종료 코드가 모두 0이어도 Linux `/proc` 시험이 통과했다는 뜻은 아니다. 이번 작업은 시험 입력과 플랫폼 조건만 정정했고, 제품 코드나 기존 차단 기대값은 완화하지 않았다. `threat_trace_mapping_check.py`와 `user_command_settings_review`의 고정 해시는 건드리지 않았다.

## 다음 작업

DEV-73: Linux 솔루션 기기에서 건너뛴 반복 마운트 시험을 실행하고, 실제 경합 및 차단 근거를 별도로 남긴다. 통합 회귀에서 파일 단위 통과와 사례 단위 건너뜀을 함께 집계한다.

## 사용자에게 필요한 입력

없음.
