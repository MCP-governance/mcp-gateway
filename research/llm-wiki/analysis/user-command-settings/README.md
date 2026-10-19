# 사용자 명령 헬퍼 준수 검사 (D-148, DEV-42)

2026-10-20, Codex sol. 시작 `a61c7fa71c6f3d09f624b215a582fc05e3b38e3b`, 브랜치 `10/20-user-command-settings`.
선행 [D-147 분석](../command-surfaces/README.md)을 유지하고 관리 설정으로 잠글 수 없는 홈 설정을 준수 검사로 보강한다.
설정의 명령을 실행하거나 자체 MCP 서버를 만들지 않는다.

## 요구사항과 검증 연결

| ID | 요구사항·판정 | 코드 심볼 | 새 시험의 조건 | 증거 범위 |
| --- | --- | --- | --- | --- |
| UCH-01 | 등록 계정 홈만 사용 | `managed-linux.checks`, `managed-windows.checks` | 서비스 HOME을 다른 경로로 두고 등록 홈의 키 탐지 | 두 플랫폼 함수 본문·OS 대역 |
| UCH-02 | Claude 네 키, 두 홈 파일, 값과 무관한 존재 검사 | `agent.user_command_settings` | 각 키×두 파일×명령/빈 문자열/null/false, 여러 키 | 실제 임시 파일 파싱 |
| UCH-03 | Codex notify 및 프로필 파일 | 같은 함수 | config·서로 다른 `*.config.toml`, 빈 배열·인라인 profiles·테이블 profiles·인용 키 | 표준 tomllib 실제 파싱 |
| UCH-04 | 정상/부재 통과, 오류 실패 | 같은 함수 | 정상 JSON/TOML·주석·중첩 env, 깨진 JSON/TOML·NaN·UTF-8 오류·PermissionError·파서 부재·과대 파일·특수 경로·수정 후 복구 | 임시 파일, 읽기 실패만 대역 |
| UCH-05 | 명령 값 미보고 | 같은 함수, `main.UserCommandSetting` | 반환 구조는 file/keys뿐, 임의 키/명령 값 필드·홈 밖 경로 거부 | 실제 함수/입력 모델 |
| UCH-06 | 필수 검사·격리·현재 실패 갱신 | `endpoint_plane.heartbeat`, `MANAGED_CHECKS_BY_PLATFORM` | 두 플랫폼 정상/미보고/false/구형 해시·모순된 true+실패 목록·정상 복구 시 최근 목록 비움 | AsyncMock DB의 SQL·인자 검사 |
| UCH-07 | 구형 설치와 토큰 구분 | `endpoint_plane.managed_policy` | version=2 및 다른 조건이 같아도 version=1과 해시가 다름 | 정책 렌더링 함수 |
| UCH-08 | 한국어 제품 라벨 | `console.js:CHECK_LABEL` | JS 구문·기존 콘솔 상태 회귀 | 브라우저 렌더링 미실행 |
| UCH-09 | 링크는 읽지 않음 | `agent.user_command_settings` | 실제 링크·끊어진 링크 거부 | Windows 링크 생성 권한 부족으로 미실행 |

시험 정본: [user_command_settings_check.py](../../../../full_stack_lab/tests/user_command_settings_check.py).
실행 결과와 기존 회귀 한계는 [작업 보고](../../status/reports/2026-10-20-user-command-settings.md)에 기록한다.
코드 기준과 행은 [로컬 검증 기록](verification.json)에 해시와 함께 고정한다. 실제 PostgreSQL·MCP·기기 집행의 증거로 세지 않는다.

## 판본·공식 근거·채택

- 하네스 표면의 판본/원문/라이선스는 D-147 분석에 고정되어 있다. 이 변경으로 하네스 판본을 올리지 않는다.
- CPython 표준 `json`/`tomllib` 사용. [공식 tomllib 문서](https://docs.python.org/3/library/tomllib.html), [파서 라이선스 고지](https://github.com/python/cpython/blob/main/Lib/tomllib/_parser.py), [CPython 라이선스](https://github.com/python/cpython/blob/main/LICENSE)를 검색·조회했다. 문서 main은 고정 판본 증거로 쓰지 않는다. 실제 기존 실행기는 게이트웨이 Python 3.12 이미지, Windows `windows-python.json`의 3.13.16·SHA-256 고정, 로컬 3.12.14이며 새 의존성은 없다.
- GitHub의 공개 설정/보안 스킬과 Python 파서를 먼저 검색했다. 외부 스킬은 고정 commit·전체 라이선스·유지보수 상태를 검증하지 못해 채택하지 않았다. 코드/스크립트 복사·실행·자격 접근 없음. CPython tag/스킬 commit의 GitHub API 조회는 접근 실패로 기록하며 성공한 고정 원본 조사로 세지 않는다.
- 분석 대상 저장소 코드는 시작 commit과 검증 파일 해시로 고정한다. 자체 코드는 파일 범위 선정·명령 키 판정·기존 준수 보고 연동에 한정한다.

## 구형 설치 전환 (메인 검토로 정정)

처음 안(Codex sol)은 미보고를 허용하지 않아, 배포 즉시 등록된 모든 PC(PJ1·pj3·팀원 장치)가 격리됐다. 관리 에이전트는 원격 갱신 경로가 없어 재설치 전까지 쓸 수 없게 된다.
정정: `managed_checks(device, reported)`는 장치가 검사 항목을 한 번이라도 보고했으면(`detail.command_settings_checked`) 항목을 필수로 하고, 그 전에는 빼고 판정한다.
- 구형 에이전트: 이전 네 항목만으로 준수, 콘솔에 새 항목이 나타나지 않는다. 운영자는 새 키트로 재설치해 검사를 켠다.
- 새 에이전트가 한 번 보고하면 표식이 남아 이후 항목 누락(구형 키트 재설치)은 격리된다.
- 표식은 root/SYSTEM 에이전트 보고에서만 생긴다. 직원 계정이 에이전트 판본을 낮출 경로는 관리 설치 경계(AppArmor·설정 보호) 밖이다.
- 정책 version 1→2는 유지한다. 에이전트가 새 정책을 자동 적용하므로 일시적인 해시 불일치만 생긴다.
- 한계: 재설치하지 않은 장치는 이 검사를 받지 않는다. 장치별 검사 적용 여부는 `detail.command_settings_checked`로 확인한다.

## 한계

프로젝트 설정·대체 홈/설정 인자·클라우드는 모집단 밖이다. heartbeat 사이 파일 교체·실행과 동일 inode 쓰기를 잠그지 않는다.
링크/재분석 지점·특수 파일을 거부하고 파일 열기 전후 식별자를 비교하지만 경로의 모든 경쟁을 제거하지 못한다.
장치 키를 가진 root/SYSTEM을 신뢰하는 기존 경계이며 원격 증명이 아니다. 실제 프로필/독립 효과·기기 복구는 미실행이다.
파일당 1 MiB, Codex 폴더 열거 4,096개, 검사 파일 120개 미만을 초과하면 정상으로 추정하지 않고 실패한다.
