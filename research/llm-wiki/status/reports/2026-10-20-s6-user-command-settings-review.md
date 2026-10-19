# 2026-10-20 S6 사용자 명령 설정 적대 검증

- 작업자: Codex luna
- 코드 기준: `9e597acb13157186a83f6e7fba09eac5090b8258`, 브랜치 `10/20-user-command-settings-review`; 원격 HEAD 재확인은 GitHub 연결 실패로 미실행
- 실제 변경: `endpoint-agent/agent.py` 하드 링크 거부, 신규 `full_stack_lab/tests/user_command_settings_review_check.py`, 적대 분석 정본. 기존 시험·`status/current.md`는 수정하지 않음.
- 시작 근거: DEV-42·D-148·RV-02, [D-147 명령 표면](../../analysis/command-surfaces/README.md), [D-148 사용자 설정 분석](../../analysis/user-command-settings/README.md)
- 목적: 파일시스템 경계·설정 우회·heartbeat 전환 표식·민감 보고값을 반증하고 확실한 결함을 최소 수정한다.

## 결과

실제 임시 파일과 소스 경로로 하드 링크를 재현했다. 열린 파일의 link count가 1이 아니면 명령 값을 읽기 전에 실패하도록 바꾸고 새 시험을 추가했다. 기존 시험 기대값은 바꾸지 않았다.

확인된 미해결 사항은 설정 디렉터리 경로 교체 경쟁, Windows `CODEX_HOME`·`CLAUDE_CONFIG_DIR` 및 Codex `--config`가 검사 범위 밖인 점, Codex 프로필 파일 이름이 보고/DB/격리 사건에 저장되는 점, 아직 새 검사 보고가 없는 기존 장치는 계속 레거시 조건으로 통과하는 점이다. 파일명 익명화는 기존 시험의 정확한 파일명 기대값 수정이 필요하므로 적용하지 않고 **기존 시험 변경 필요**로 남겼다.

JSON 중복 키, 대소문자 구분, TOML 인라인 테이블·점 표기, 중첩 파서 오류, UTF-8, 크기 상한, FIFO 사전 거부, 표식 삭제 병합 및 활성화 조건을 코드와 기존 시험에서 대조했다. 판정별 재현·수정안·범위 한계는 [S6 적대 검토](../../analysis/review-1020/s6-user-command-settings.md)에 기록했다.

## 검증

| 확인 종류 | 명령·환경 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 신규 적대 회귀 | `python -B -X utf8 full_stack_lab/tests/user_command_settings_review_check.py`, Python 3.10.5 | 1 통과 | 신규 시험 |
| 기존 회귀 | `python -B -X utf8 full_stack_lab/tests/user_command_settings_check.py`, Python 3.10.5 | 11 통과, 4 미실행(skip: Pydantic 2·tomllib·Windows 링크 권한) | 기존 파일, 기대값 미변경 |
| Python 구문 | `python -B -X utf8 -m py_compile endpoint-agent/agent.py full_stack_lab/tests/user_command_settings_review_check.py` | 통과 | 로컬 정적 검사 |
| 패치 공백 | `git diff --check` | 통과 | 작업 트리 |
| 하네스·파일 경쟁 | Windows junction·Linux FIFO와 경쟁 재현, PJ1 실제 명령 호출 | 미실행 | 기기 검증 필요 |

## 실패·미완료·한계

- 기존 시험 변경 필요: 파일명 익명화를 적용하려면 `tests/user_command_settings_check.py`의 기존 파일 경로 기대값을 바꿔야 한다. 지시에 따라 수정하지 않았다.
- Windows 링크 생성 권한 부족·Python 3.10.5로 기존 TOML/Pydantic 입력 시험 일부가 실행되지 않았다. 신규 hardlink 시험은 로컬 파일시스템에서 통과했다.
- 디렉터리 핸들 고정, 환경/인자에서의 설정 홈 정규화, 실제 게이트웨이 DB·heartbeat·활성화, 브라우저 화면, 솔루션 배포, PJ1은 미검증이다.
- 원격 HEAD 조회는 GitHub 연결 실패로 수행하지 못했다. 커밋하지 않았다.

## 다음 작업

적대 검토 후 별도 결정으로 파일명 익명화와 등록 하네스 경로 고정을 설계한다. Linux 솔루션 이미지에서 신규 시험과 기존 시험을 실행한 뒤, PJ1에서 실제 Codex·Claude 호출·격리·복구 효과를 확인한다.

## 사용자에게 필요한 입력

없음.
