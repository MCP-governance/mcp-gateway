# 하네스 진입 파일·설치 연결부·모델 인증 표시 수정 — 2026-10-28

- 작업자: Codex
- 코드 기준: `10/27-bugfix-round1`, 시작 `bf6782631e98de21f4c6e2247634ded4d7c65b5a`. 기존 작업 줄기의 후속 수정이므로 새 브랜치·PR을 만들지 않는다. 작업 단위로 커밋하며 push·병합·배포는 하지 않는다.
- 시작 근거: `BRIEF-fix3.md`, `R3-REVIEW.md`, `R3-TEST-RESULT.md`. 두 문서는 제공된 검토·pj2 관찰이고 이번 작업의 실기기 실행 증거가 아니다.
- 완료 조건: 두 탐지 누락 반례의 수정 전 실패·수정 후 통과, 실제 설치/점검 함수 연결 시험, 모델 인증 실패와 최종 JSON의 일치, 결정·현황·백로그·결과 파일 기록.

## 결과

| 요구 | 원인·구현 위치 | 결과 |
| --- | --- | --- |
| 중첩 MCP와 동명 실행 파일 탐지 | `agent.py:703`, `:706`, `:979` | 패키지 진입 스크립트까지 경로를 한정했다. native는 설치 경로 목록과 실경로를 대조한다. 파일 이름만으로 제외하지 않으며 initialize는 계속 확정 증거다(D-273). |
| 설치 경로의 수집기 전달 | `managed-linux.py:480`, `:913`, `managed-windows.py:838`, `:916`, `managed-macos.py:326` | 기존 보호 설정을 재사용한다. macOS는 Linux 보고 루프를 재사용한다. 새 의존성·서버 정책·인가 변경은 없다. |
| D-271 연결 시험 | `linux_kit_reinstall_check.py:70`, `:145`, `:220` | Linux는 실제 설치 함수의 중간 반환값부터 점검·최종 JSON까지, macOS는 실제 설치와 완료 JSON·문구를 임시 파일로 검사한다(D-274). |
| 만료된 모델 로그인 표시 | `bootstrap.py:573`, `:624`, `:643`, `:653`, `:878` | 자격 파일의 존재로 만든 로그인 값을 실제 인증 실패가 정정한다. Claude·Codex에 맞는 로그인 명령을 표시한다. 일반 연결 시간 초과는 자격 만료로 바꾸지 않는다(D-275). |

## 검증

Windows Python 3.10에서 `python -B -X utf8`로 실행했다. 합성 프로세스·등록/정책·모델 전송 대역을 사용한 단위 시험이며 실제 OSS MCP 실행을 주장하지 않는다. 설치 시험의 파일 입출력·JSON·공용 `wait_summary`·상태 변환은 실제 코드다. 임시 HOME·CODEX_HOME을 사용했다.

| 확인 | 결과 | 증거 |
| --- | --- | --- |
| 검토 반례의 이전 코드 비교 | 기준 `bf678263`에서 2개 시험 실패(소켓 켬/끔 포함 실패 지점 3개), 현재 2개 통과 | `baseline-d273.log`, `fixed-d273.log` |
| D-271 퇴행 변이 | Linux·macOS 설치 반환을 등록 응답으로 되돌리면 각각 실패, 현재 각각 통과 | `mutation-d271.log`, `fixed-d271.log` |
| 모델 인증 이전 코드 비교 | 이전 bootstrap에서 OAuth 만료·Codex 401 각각 실패, 현재 각각 통과 | `baseline-model-auth.log`, `fixed-model-auth.log` |
| 관련 Python 7개 스위트 | 125건 중 123건 통과·POSIX 2건 생략 | `endpoint_collector_check` 15, `kit_simple_mode_check` 13, `linux_kit_reinstall_check` 32, `windows_kit_reinstall_check` 10, `kit_screen_check` 19, `kit_continuity_check` 25(2 생략), `macos_kit_check` 11 |
| Windows 경로 저장·수집기 전달 보완 | 2건 통과. 모듈 검색 경로를 추가하고 상태 대기는 대역으로 처리했다 | `windows-targeted.log`, 기존 Windows 설치·서비스 함수 실행 |
| Node 다운로드 회귀 | 4건 통과 | `node --test full_stack_lab/tests/kit-download-console.test.mjs`, `extra-0.log` |
| 정적 검사 | 수정 Python 10개 컴파일, 결정 분할 검사, `deploy/check.py`, `git diff --check` 통과 | 명령 실행 결과 |
| 위키 추적 검사 | `check_trace.py` 오류 0·경고 5 | `check_trace.log` |
| 위키·분석 전체 검사 | 실패. `check_wiki.py` 원문 누락 29·코드 매핑 해시 29, `check_enterprise_analysis.py` 코드/연동 해시 54 | 각각의 `.log`, 생성물 재생성 금지 범위와 구분 |
| 정밀 린트 | `pyflakes` 미설치로 실행 불가 | 통과로 세지 않음 |
| 실기기·실제 모델·MCP·배포 | 미실행 | 기존 pj2 시험과 이번 단위 결과를 구분 |

로그와 소스 비교 실행기는 Git 제외 로컬 폴더 `research/collaboration-console/runtime/fix3-checks/`에 있다. 비교는 메모리에서 모듈을 바꾸고 작업 트리 소스는 되돌리지 않았다. 비교 실행기 초안의 모듈 대역 연결 오류로 중단한 실행은 결과에서 제외하고, 수정 후 비교 결과만 기록했다.

## 실패·미완료·한계

- `unittest discover -s endpoint-agent/tests-windows -p test_*.py`: 49건 중 실패 5·오류 4·생략 1. PowerShell 실행 정책의 스크립트 차단 6건(오류 1 포함), `windows_status` 검색 경로 부재 3건이다. 전체 통과라고 보고하지 않는다. 이번에 변경한 경로 저장·전달 부분은 위 보완 실행에서 통과했다. 시스템 실행 정책은 변경하지 않았다.
- `loopback_owner_replies_test.py`: 10건 중 1건은 Windows의 `grp` 부재로 오류다. 나머지 9건 성공과 구분한다. `agent.py --self-check`는 TOML 파서 부재, `bootstrap.py --self-check`는 `grp` 부재로 중단했다. 지원 기기 이미지에서 확인 필요다.
- 원격 HEAD 조회는 GitHub 443 연결 실패로 확인하지 못했다. 기존 브랜치와 시작 commit은 로컬 Git에서 확인했다. 신규 OSS·SDK를 도입할 규모의 기능 추가는 없으며 기존 코드·표준 라이브러리만 썼다.
- 옛 설치에는 native 경로 목록이 없어 이름만으로 제외하지 않는다. 관리형 키트 재설치가 필요하다. 목록에 없는 새 설치 위치와 관측 전용 설치는 별도 구성·검토 대상이다. 경로 대조는 실행 파일 서명·내용 무결성·명령줄 위조 방지나 원격 증명이 아니다.
- 모델 인증 판단은 기존 오류 사유 안의 명시적 인증 표현에 한정된다. 확인하지 않은 하네스와 평상시 서비스 안내의 모델 로그인 유효성을 증명하지 않는다.
- `refresh_generated.py`는 BRIEF 지시에 따라 실행하지 않았다. 결정 색인만 지정 명령으로 갱신했다.
- 전체 위키 검사는 통과하지 못했다. Git 제외 원문 부재와 재생성하지 않은 매핑(이번에 바꾼 `managed-windows.py` 포함)이 남는다. 분석 검사에서 지적한 코드는 이번 변경에 없는 `gateway/app/core.py`·`pac.py`·`console.sh`다. 위키 원문 복원·생성물 정합성은 병합 전 별도 확인 대상이다.

## 다음 작업

[S4 후속](../backlog.md#s4-후속-2026-10-27)에 연결한다. 지원 이미지의 환경 제약 시험을 마치고, 키트 재설치 후 승인 하네스 프롬프트 오탐 0·별도 실제 OSS MCP 탐지 유지·모델 재로그인 및 자연어 도구 선택을 지정 시험 PC에서 확인한다. 이 작업에서는 스택을 띄우거나 기존 시험 PC를 조작하지 않는다.

## 사용자에게 필요한 입력

이번 코드 수정·단위 시험에는 없음. 후속 실제 모델 시험에는 지정 시험 PC의 유효한 모델 로그인과 키트 갱신이 필요하다. 비밀값을 저장소에 기록하지 않는다.
