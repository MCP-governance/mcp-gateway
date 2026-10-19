# 2026-10-20 Windows 관리 계정 환경의 설정 폴더 변수 검사

- 작업자: Claude Sonnet(서브에이전트, 메인이 위임)
- 코드 기준: `ecea5c881c8cf941aea956c577b8b1927cde9585`에서 시작한 `10/20-windows-config-env`, 시작 시 깨끗함. 푸시 없음.
- 실제 변경: `endpoint-agent/managed-windows.py`(`checks`), `endpoint-agent/README.md`(한 문장), `full_stack_lab/gateway/app/main.py`(`UserCommandSetting.file` 표기 3개 추가), 새 `full_stack_lab/tests/windows_config_env_check.py`, 기존 `full_stack_lab/tests/user_command_settings_check.py`(가짜 `winreg` 대역 한 줄, 기대값 무변경), D-151, 이 보고서, 백로그 DEV-42 마지막 칸.
- 시작 근거: DEV-42, D-148, 적대 검토 [S6-03](../../analysis/review-1020/s6-user-command-settings.md).
- 해결할 문제와 완료 조건: 관리 계정의 사용자 환경 `CODEX_HOME`·`CLAUDE_CONFIG_DIR`가 하네스를 기존 검사 밖의 설정 폴더로 보내는 우회를 준수 실패로 보고한다. 값은 보고하지 않는다.

## 결과

Windows `checks`가 `HKEY_USERS\<SID>\Environment`에서 두 변수의 존재만 읽는다. 빈 값도 실패이며 `user_command_helpers`가 false가 되고
발견 항목에 `{"file": "env:CODEX_HOME"|"env:CLAUDE_CONFIG_DIR", "keys": []}`가 더해진다. 키·하이브 없음은 변수 없음으로 본다.
그 밖의 레지스트리 오류와 `winreg` 부재는 `{"file": "env", "keys": []}` 실패다(값 비누출). 게이트웨이 입력 모델은 이 세 표기만 새로 받고 임의 문자열은 거부한다.
구현과 오프라인 대역 시험까지다. 배포·실제 레지스트리·PJ1 하네스 확인은 하지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 신규 시험 | `python -X utf8 full_stack_lab/tests/windows_config_env_check.py` (Python 3.12.10, Windows, 2026-10-20) | 8통과. 구현을 빼면 15건 실패·오류(시험이 실제로 검사함) | 실행 출력 |
| 기존 D-148 시험 | `python -X utf8 full_stack_lab/tests/user_command_settings_check.py` | 15건 중 14통과, 링크 권한 1건 생략. `winreg`가 없는 환경 모의로도 통과 | 실행 출력 |
| 기존 관련 시험 | `managed_helper_unavailable_check.py`, `windows_os_observer_check.py` | 통과(1건 생략) | 실행 출력 |
| 구문 | `python -m py_compile` managed-windows.py, main.py | 통과 | 실행 출력 |
| 기존 Linux 강제 시험 | `managed_enforcement_check.py` | Windows에서 `grp` 모듈 부재로 10건 오류(변경 전도 동일, 기기 이미지에서 실행) | 실행 출력 |
| 실제 레지스트리·PJ1 하네스 | | 미실행 | |
| 배포·정책 해시 | | 미확인 | |

## 실패·미완료·한계

- 프로필 아래 다른 위치(프로젝트 폴더, `--settings`·`-c/--config` 인자, 이미 실행 중인 프로세스의 환경)와 시스템 환경 변수(관리자 권한 경계)는 범위 밖이다.
- 로그아웃 계정은 하이브가 올라와 있지 않아 읽지 못한다. 로그인 후 첫 heartbeat에서 잡힌다. 60초 스냅샷 경쟁은 남는다.
- 기존 시험 파일에는 가짜 `winreg` 한 줄을 더했다. 비Windows(기기 이미지)에서는 `winreg`가 없어 `checks`가 `env` 실패를 내기 때문이며 기대값은 바꾸지 않았다.
- 재설치하지 않은 구형 장치는 D-148 전환 규칙대로 이 검사도 받지 않는다.

## 다음 작업

DEV-42: 솔루션 기기 배포 후 PJ1 Windows 관리 계정에 `CODEX_HOME` 사용자 변수를 넣었을 때 격리·복구를 확인하고, 런처의 `-c/--config`·`--settings` 인자 고정을 이어서 다룬다.

## 사용자에게 필요한 입력

없음
